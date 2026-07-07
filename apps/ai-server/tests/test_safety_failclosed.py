"""Issue #19: SafetyClassifier must FAIL CLOSED when the LLM path degrades.

When the LLM safety path is unavailable (total outage) or returns unparsable
output, the classifier previously returned RiskLevel.none — a life-threatening
false negative for any phrasing the deterministic keyword rules do not cover.
The safe-side behaviour is to fail CLOSED (>= CTRS 2 / crisis) so the
orchestrator routes to the crisis flow.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.safety_classifier import SafetyClassifierAgent
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.safety import SafetyInput

# A concrete imminent-suicide phrase using lethal means NOT in the keyword lists
# (투신/한강/뛰어내리 are absent from _CRITICAL_KEYWORDS / _HIGH_KEYWORDS), so the
# rule engine returns `none` and the outcome depends entirely on the LLM path.
_RULE_MISSED = "오늘 밤 한강에서 뛰어내릴 거예요"


def _make_agent() -> SafetyClassifierAgent:
    agent = SafetyClassifierAgent.__new__(SafetyClassifierAgent)
    agent._router = MagicMock()
    # PromptLoader.load_system_prompt must return a real str: ChatMessage
    # (pydantic) rejects a bare MagicMock as `content`.
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = (
        "당신은 안전 분류 AI입니다. JSON으로만 응답하세요."
    )
    return agent


def _wire(agent: SafetyClassifierAgent, adapter: object) -> None:
    agent._router.select_model.return_value = MagicMock(
        adapter_name="test",
        model_id="test",
        supports_json_schema=False,
        supports_json_object=False,
    )
    agent._router.get_adapter.return_value = adapter
    agent._router.record_success = MagicMock()
    agent._router.record_failure = MagicMock()
    agent._router.get_fallback.return_value = None  # no fallback available


@pytest.mark.asyncio
async def test_llm_total_outage_fails_closed() -> None:
    """LLM total outage + rule-missed suicide phrase must trigger crisis, not 'safe'."""
    agent = _make_agent()
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(side_effect=RuntimeError("LLM down"))
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(session_id="t", user_message=_RULE_MISSED, conversation_history=[])
    )

    assert out.crisis_protocol_activated is True, (
        f"fail-open: expected crisis on LLM outage, got "
        f"risk={out.risk_level} ctrs={int(out.ctrs_level)}"
    )
    assert int(out.ctrs_level) <= int(CTRSLevel.HIGH_RISK)


@pytest.mark.asyncio
async def test_llm_parse_failure_fails_closed() -> None:
    """LLM returns unparsable content + rule-missed phrase must trigger crisis."""
    agent = _make_agent()
    resp = MagicMock()
    resp.content = "I'm sorry, I cannot output JSON."
    resp.model = "test"
    resp.latency_ms = 1.0
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(session_id="t", user_message=_RULE_MISSED, conversation_history=[])
    )

    assert out.crisis_protocol_activated is True, (
        f"fail-open: expected crisis on LLM parse failure, got "
        f"risk={out.risk_level} ctrs={int(out.ctrs_level)}"
    )
    assert int(out.ctrs_level) <= int(CTRSLevel.HIGH_RISK)


@pytest.mark.asyncio
async def test_benign_message_stays_safe_when_llm_ok() -> None:
    """Regression: a working LLM returning 'none' keeps a benign message safe."""
    agent = _make_agent()
    resp = MagicMock()
    resp.content = (
        '{"risk_level":"none","categories":[],"flagged_phrases":[],'
        '"confidence":0.9,"reason_summary":"no risk"}'
    )
    resp.model = "test"
    resp.latency_ms = 1.0
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(session_id="t", user_message="오늘 날씨가 좋네요", conversation_history=[])
    )

    assert out.crisis_protocol_activated is False
    assert out.risk_level == RiskLevel.none


# ── ISS-026: total-outage merge semantics ────────────────────────────


@pytest.mark.asyncio
async def test_total_outage_rule_missed_phrase_fails_closed_high() -> None:
    """ISS-026: all adapters fail + phrase NOT in keyword lists.

    Rule engine returns none; the old merge fell back to the rule result
    (risk=none, crisis=False). The final result must instead be at least the
    fail-closed default: risk high/critical, CTRS <= 2, crisis True.
    """
    agent = _make_agent()
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(side_effect=RuntimeError("total outage"))
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(session_id="t", user_message=_RULE_MISSED, conversation_history=[])
    )

    assert out.risk_level in (RiskLevel.high, RiskLevel.critical), (
        f"fail-open: outage + rule-missed phrase produced risk={out.risk_level}"
    )
    assert int(out.ctrs_level) <= 2
    assert out.crisis_protocol_activated is True
    assert out.model_used == "none"


@pytest.mark.asyncio
async def test_total_outage_rule_critical_stays_critical() -> None:
    """ISS-026: outage must not cap a rule-critical hit at the fail-closed high."""
    agent = _make_agent()
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(side_effect=RuntimeError("total outage"))
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(session_id="t", user_message="자살하고 싶어요", conversation_history=[])
    )

    assert out.risk_level == RiskLevel.critical, (
        f"rule critical must win the fail-closed merge, got {out.risk_level}"
    )
    assert out.crisis_protocol_activated is True


@pytest.mark.asyncio
async def test_pre_adapter_failure_fails_closed() -> None:
    """ISS-026: exceptions before the adapter call (prompt loader, model
    selection, message construction) must produce the fail-closed
    classification, not propagate out of the safety agent."""
    agent = _make_agent()
    # Non-FileNotFoundError from the prompt loader — previously propagated.
    agent._prompt_loader.load_system_prompt.side_effect = RuntimeError("loader broken")
    adapter = AsyncMock(spec=LLMAdapter)
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(session_id="t", user_message=_RULE_MISSED, conversation_history=[])
    )

    assert out.crisis_protocol_activated is True
    assert out.risk_level in (RiskLevel.high, RiskLevel.critical)
    assert int(out.ctrs_level) <= int(CTRSLevel.HIGH_RISK)
