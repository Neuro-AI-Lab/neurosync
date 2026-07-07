"""BUG-008 repro: the "내가 없으면" / "내가없으면" `_MEDIUM_KEYWORDS` entries
added as part of the BUG-007 fix do not function as a rule-engine backstop.

BUG-007's resolution (`error.md`) claims the `safety_classifier.py` keyword
addition gives "내가 없으면 다 편할 텐데" "a deterministic rule-engine
backstop ... independently of the LLM prompt" (see also the docstring of
`tests/repro/test_bug_007.py::test_burden_ideation_phrase_now_has_rule_engine_backstop`,
which repeats the "independently of the LLM prompt" claim).

That claim does not hold under `SafetyClassifierAgent.run()`'s merge logic
(`src/agents/safety_classifier.py:387-399`):

  - `_MEDIUM_KEYWORDS` matches only set `rule_level = RiskLevel.medium`.
  - Rule context is only forwarded to the LLM, and the rule result only
    matters for the final decision, when `rule_level >= RiskLevel.high`
    (`safety_classifier.py:373`, `:389`). For a medium-only rule hit, the
    code takes the `else` branch (`:396-399`) and sets
    `final_level = llm_classification.risk_level` -- the LLM's own
    judgment entirely, with no floor from the rule engine.
  - The medium-level rule match therefore never elevates `risk_level` or
    `crisis_protocol_activated` when the LLM path is available and returns
    a lower risk_level than the keyword would imply -- exactly the failure
    mode ("LLM under-classifies this specific phrase") that a "backstop"
    would need to catch.
  - In the LLM-unavailable path, `_FAIL_CLOSED_LEVEL = RiskLevel.high` is
    already unconditionally applied via `_max_risk(rule_level,
    _max_risk(llm_classification.risk_level, _FAIL_CLOSED_LEVEL))`
    (`:407-410`) regardless of whether any keyword matched at all, so the
    added medium keywords are also redundant in that branch.

Net effect: the keyword addition only affects observability fields
(`rule_triggered`, `categories`, `flagged_phrases` on the output) -- useful
for audit trails, but not a "backstop" against a wrong LLM classification,
contrary to the resolution text and the renamed BUG-007 test's docstring.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.safety_classifier import SafetyClassifierAgent
from src.schemas.common import RiskLevel
from src.schemas.safety import SafetyInput

_BURDEN_PHRASE = "내가 없으면 다 편할 텐데"


def _make_agent() -> SafetyClassifierAgent:
    agent = SafetyClassifierAgent.__new__(SafetyClassifierAgent)
    agent._router = MagicMock()
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
    agent._router.get_fallback.return_value = None


@pytest.mark.asyncio
async def test_medium_keyword_backstop_does_not_elevate_when_llm_available_and_wrong() -> None:
    """BUG-008: if the LLM (available, not erroring) under-classifies the
    burden-ideation phrase as 'none', the new MEDIUM keyword match does NOT
    raise the final risk_level or activate the crisis protocol -- the
    claimed "deterministic rule-engine backstop" is inert whenever the LLM
    path is up, which is the common case and the exact scenario a backstop
    exists for.
    """
    agent = _make_agent()
    resp = MagicMock()
    resp.content = (
        '{"risk_level":"none","categories":[],"flagged_phrases":[],'
        '"confidence":0.9,"reason_summary":"llm judged this as fine"}'
    )
    resp.model = "test"
    resp.latency_ms = 1.0
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(session_id="t", user_message=_BURDEN_PHRASE, conversation_history=[])
    )

    # The rule engine DOES fire (proves the keyword table addition works at
    # the matching level -- this is not in dispute, see test_bug_007.py).
    assert out.rule_risk_level == RiskLevel.medium, (
        f"expected rule engine to flag medium for {_BURDEN_PHRASE!r}, "
        f"got rule_risk_level={out.rule_risk_level} -- if this fails, the "
        f"BUG-007 keyword addition itself has regressed"
    )

    # But the "backstop" does not backstop: an available-but-wrong LLM
    # still wins outright, with no floor from the rule engine.
    assert out.risk_level == RiskLevel.none, (
        "BUG-008 appears fixed: a medium rule-engine hit now influences "
        f"the final decision (got risk_level={out.risk_level}). If this "
        "assertion starts failing because the merge logic was changed to "
        "give MEDIUM-level rule hits a floor, this test should be inverted "
        "the same way test_bug_007's inversion was -- update the BUG-008 "
        "resolution in error.md accordingly."
    )
    assert out.crisis_protocol_activated is False, (
        "expected no crisis activation from a medium-only rule hit "
        "overridden by an available LLM's 'none' judgment"
    )
