"""BUG-076 regression — passive-SI idiom keyword coverage + medium-floor
merge enforcement.

BUG-076's live repro: "아침에 눈을 안 떴으면 좋겠어" (a passive-SI/passive
death-wish idiom — "wish to not wake up") had ZERO `_MEDIUM_KEYWORDS`
coverage, so the rule engine passed no context to the LLM, and the LLM
independently under-scored it `low`/CTRS-4 — one tier below the ADR-006
CTRS-3/medium floor for this idiom family (CVR-055 finding, error.md
BUG-076).

This fix has two parts, both exercised here:
  1. `_rule_classify` now matches the idiom family (`_MEDIUM_KEYWORDS`).
  2. The merge in `run()` now floors `final_level` at `rule_level` when the
     rule is NOT high/critical (previously it discarded the rule's own
     medium-tier verdict outright and used the raw LLM result — the BUG-008
     gap this fix also closes) — so even if the LLM under-scores the SAME
     idiom again, the final result cannot drop below medium.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.safety_classifier import SafetyClassifierAgent
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.safety import SafetyInput

_PASSIVE_SI_LIVE_REPRO = "아침에 눈을 안 떴으면 좋겠어"


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


def _llm_response(risk_level: str) -> MagicMock:
    resp = MagicMock()
    resp.content = (
        f'{{"risk_level":"{risk_level}","categories":[],"flagged_phrases":[],'
        '"confidence":0.7,"reason_summary":"test"}'
    )
    resp.model = "test"
    resp.latency_ms = 1.0
    return resp


@pytest.mark.parametrize(
    "phrase",
    [
        "아침에 눈을 안 떴으면 좋겠어",
        "눈을 뜨지 않았으면 좋겠어요",
        "잠들어서 안 깼으면 좋겠어",
    ],
)
def test_rule_engine_matches_passive_si_idiom_family(phrase: str) -> None:
    """`_rule_classify` must now flag the passive-SI idiom family at
    medium, with the `suicidal_ideation` category — the pre-fix rule
    engine matched none of these (BUG-076 repro: `level=none, flagged=[]`)."""
    agent = _make_agent()
    level, categories, flagged = agent._rule_classify(phrase)
    assert level == RiskLevel.medium, f"{phrase!r} -> {level} (expected medium)"
    assert "suicidal_ideation" in categories
    assert flagged


@pytest.mark.asyncio
async def test_llm_under_score_is_floored_to_medium() -> None:
    """BUG-076 core fix: even when the LLM independently judges the SAME
    passive-SI idiom as `low` (reproducing the exact live miscalibration),
    the rule engine's medium-tier match must floor the final result at
    medium — not silently discard the rule's verdict as the pre-fix merge
    did."""
    agent = _make_agent()
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=_llm_response("low"))
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(
            session_id="t",
            user_message=_PASSIVE_SI_LIVE_REPRO,
            conversation_history=[],
        )
    )

    assert out.risk_level == RiskLevel.medium, (
        f"BUG-076 regression: LLM under-scored 'low' but rule matched medium — "
        f"final should floor at medium, got {out.risk_level}"
    )
    assert out.rule_risk_level == RiskLevel.medium
    assert out.llm_risk_level == RiskLevel.low
    assert int(out.ctrs_level) <= int(CTRSLevel.ACUTE)


@pytest.mark.asyncio
async def test_llm_can_still_escalate_above_rule_floor() -> None:
    """The floor is a MINIMUM, not a cap — if the LLM independently judges
    the same phrase as high/critical, that more severe judgment must still
    win (unchanged behavior, regression guard)."""
    agent = _make_agent()
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=_llm_response("critical"))
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(
            session_id="t",
            user_message=_PASSIVE_SI_LIVE_REPRO,
            conversation_history=[],
        )
    )

    assert out.risk_level == RiskLevel.critical


@pytest.mark.asyncio
async def test_benign_medium_keyword_unaffected_when_llm_agrees_or_exceeds() -> None:
    """Regression guard: an existing `_MEDIUM_KEYWORDS` phrase (unrelated to
    this fix) with an LLM verdict at or above medium is unaffected by the
    new floor logic."""
    agent = _make_agent()
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=_llm_response("medium"))
    _wire(agent, adapter)

    out = await agent.run(
        SafetyInput(
            session_id="t", user_message="요즘 너무 힘들어요", conversation_history=[]
        )
    )

    assert out.risk_level == RiskLevel.medium
