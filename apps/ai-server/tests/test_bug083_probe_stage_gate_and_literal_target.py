"""BUG-083 regression tests — live-reproduced session `b88d740e`.

Two independent defects in the 4-stage graduated Safety Probe:

1. `classify_probe_answer`'s "frequency" stage (stage 0) never checked
   `reply_has_negation` (only "plan"/"means_intent" did) — an
   unambiguous, explicit SI denial arriving at stage 0 was silently
   discarded as "continue", advancing the probe past a denial it never
   captured. Fixed: every stage now checks the denial regardless of
   name, `has_plan_disclosure` still evaluated first/unconditionally so
   escalation is never weakened.

2. `_advance_safety_probe`'s `probe_active` branch had no literal-target
   check (unlike BUG-079's sibling `risk_question_pending` branch) — a
   reply could be scored against a stage the rendered text never
   literally asked about (topic drift). Fixed via
   `safety_probe.infer_literal_probe_stage`, mirroring BUG-079's own
   mechanism exactly (mismatch -> do not accept the reply as answering
   that stage; no-history -> trust unchanged).

No live LLM calls — `classify_probe_answer`/`_advance_safety_probe` are
rule-based (per the modules' own docstrings).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from src.agents.orchestrator import OrchestratorAgent
from src.grounding import RISK_SLOT_KEY
from src.safety_probe import PROBE_STAGES, classify_probe_answer, infer_literal_probe_stage
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.orchestrator import OrchestratorInput, SessionState
from src.schemas.safety import SafetyOutput


def _safe_output() -> SafetyOutput:
    return SafetyOutput(
        model_used="test", prompt_version="v1", latency_ms=1,
        reason_summary="no risk detected", risk_level=RiskLevel.none,
        ctrs_level=CTRSLevel.STABLE, crisis_protocol_activated=False,
        requires_human_review=False, classifications=[],
    )


def _make_orchestrator() -> OrchestratorAgent:
    agent = OrchestratorAgent.__new__(OrchestratorAgent)
    agent._safety_agent = AsyncMock()
    agent._safety_agent.run = AsyncMock(return_value=_safe_output())
    return agent


# ── (1) classify_probe_answer: stage-name-gated denial check ───────────


class TestClassifyProbeAnswerStageGatedDenial:
    def test_frequency_stage_denial_deescalates_reproduces_the_gap_closed(self) -> None:
        """Pre-fix this returned 'continue' (the exact BUG-083 mechanism) —
        now must return 'deescalate'."""
        outcome = classify_probe_answer(0, "자살이나 자해 생각은 전혀 없어요")
        assert outcome == "deescalate"

    def test_frequency_stage_no_denial_still_continues(self) -> None:
        """No-regression: a genuinely ambiguous/affirmative frequency-stage
        answer with no denial/disclosure still continues to the next stage."""
        outcome = classify_probe_answer(0, "가끔 그런 생각이 들어요")
        assert outcome == "continue"

    def test_plan_stage_denial_still_deescalates(self) -> None:
        """No-regression: the pre-existing plan/means_intent behavior is
        unchanged."""
        assert classify_probe_answer(1, "계획 같은 건 전혀 없어요") == "deescalate"
        assert classify_probe_answer(2, "그런 방법은 생각해본 적 없어요") == "deescalate"

    def test_protective_stage_always_deescalates(self) -> None:
        assert classify_probe_answer(3, "가족이 있어서 버틸 수 있어요") == "deescalate"
        assert classify_probe_answer(3, "잘 모르겠어요") == "deescalate"

    def test_plan_disclosure_still_escalates_even_with_a_negation_elsewhere(self) -> None:
        """The escalation check must never be weakened by widening the
        denial check — `has_plan_disclosure` is still evaluated first."""
        outcome = classify_probe_answer(0, "계획을 세워뒀어요. 근데 아직 실행은 않았어요")
        assert outcome == "escalate"


# ── (2) infer_literal_probe_stage ────────────────────────────────────────


class TestInferLiteralProbeStage:
    def test_matches_each_stage_own_hint_phrasing(self) -> None:
        for stage_name, hint in PROBE_STAGES:
            assert infer_literal_probe_stage(hint) == stage_name

    def test_returns_none_for_topic_drifted_text(self) -> None:
        assert infer_literal_probe_stage(
            "그런 변화가 있었군요. 지금은 다른 궁금한 점이나 말씀하고 싶은 것이 "
            "있으신가요?"
        ) is None

    def test_returns_none_for_empty_text(self) -> None:
        assert infer_literal_probe_stage("") is None


# ── (3) _advance_safety_probe: literal-target check parity ─────────────


class TestAdvanceSafetyProbeLiteralTargetCheck:
    def test_reply_not_scored_when_prior_turn_drifted_off_the_current_stage(self) -> None:
        """Live repro shape (`b88d740e` turn 4): the rendered prior turn
        never literally asked stage 0's ('frequency') topic — the reply
        must NOT be scored against it; the probe stays awaiting an answer
        to the SAME stage."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug083-literal-mismatch")
        state.probe_active = True
        state.probe_awaiting_answer = True
        state.probe_stage_idx = 0
        state.probe_trigger_utterance = "그냥 몰라요, 아침에 눈을 안 떴으면 좋겠다는 생각이 들어요."
        state.conversation_history = [
            {
                "role": "assistant",
                "content": "그런 변화가 있었군요. 지금은 다른 궁금한 점이나 말씀하고 싶은 "
                "것이 있으신가요?",
            },
            {"role": "user", "content": "자살이나 자해 생각은 전혀 없어요."},
        ]

        escalated = agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug083-literal-mismatch",
                raw_input="자살이나 자해 생각은 전혀 없어요.",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert escalated is False
        assert state.probe_active is True
        assert state.probe_awaiting_answer is True  # never consumed
        assert state.probe_stage_idx == 0  # never advanced
        assert state.risk_grounded is False
        assert RISK_SLOT_KEY not in state.slot_data

    def test_reply_scored_when_prior_turn_literally_asked_the_current_stage(self) -> None:
        """No-regression companion: when the rendered prior turn DID
        literally ask the current stage's topic, scoring proceeds exactly
        as before."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug083-literal-match")
        state.probe_active = True
        state.probe_awaiting_answer = True
        state.probe_stage_idx = 0
        state.probe_trigger_utterance = "그냥 몰라요, 아침에 눈을 안 떴으면 좋겠다는 생각이 들어요."
        state.conversation_history = [
            {
                "role": "assistant",
                "content": "많이 힘드셨겠어요. 최근에 그런 생각이 얼마나 자주 드는지 "
                "여쭤봐도 될까요?",
            },
            {"role": "user", "content": "자살이나 자해 생각은 전혀 없어요."},
        ]

        agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug083-literal-match",
                raw_input="자살이나 자해 생각은 전혀 없어요.",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert state.probe_awaiting_answer is False
        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data
        assert "자살이나 자해 생각은 전혀 없어요" in state.slot_data[RISK_SLOT_KEY]

    def test_no_conversation_history_falls_back_to_accepting(self) -> None:
        """When the caller never threaded conversation history back,
        `_last_assistant_message` returns "" — trusted unchanged (same
        BUG-079 fallback discipline), so existing callers that don't thread
        history keep passing unchanged."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug083-no-history")
        state.probe_active = True
        state.probe_awaiting_answer = True
        state.probe_stage_idx = 0
        state.probe_trigger_utterance = "그냥 몰라요, 아침에 눈을 안 떴으면 좋겠다는 생각이 들어요."

        agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug083-no-history",
                raw_input="자살이나 자해 생각은 전혀 없어요.",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data


# ── (4) End-to-end: the full `b88d740e` repro no longer fabricates ─────


def test_full_repro_frequency_denial_deescalates_without_fabricating_plan_denial() -> None:
    """The exact live mechanism (`b88d740e`): stage 0 ('frequency')
    receives an explicit, unambiguous SI denial. Pre-fix, this advanced to
    stage 1 ('plan') via 'continue', and a LATER unrelated reply ("특별한
    지병은 없어요") was then fabricated into a false '구체적 계획/의도
    부인' citation. Post-fix, the stage-0 denial itself de-escalates
    immediately — the probe never reaches stage 1 at all, so the
    fabrication chain cannot occur."""
    agent = _make_orchestrator()
    state = SessionState(session_id="t-bug083-full-repro")
    state.probe_active = True
    state.probe_awaiting_answer = True
    state.probe_stage_idx = 0
    trigger = "그냥 몰라요, 아침에 눈을 안 떴으면 좋겠다는 생각이 들어요."
    state.probe_trigger_utterance = trigger
    state.conversation_history = [
        {
            "role": "assistant",
            "content": "많이 힘드셨겠어요. 최근에 그런 생각이 얼마나 자주 드는지 "
            "여쭤봐도 될까요?",
        },
        {
            "role": "user",
            "content": "자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
        },
    ]

    escalated = agent._advance_safety_probe(  # noqa: SLF001
        OrchestratorInput(
            session_id="t-bug083-full-repro",
            raw_input="자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
            session_state=state,
        ),
        state, _safe_output(),
    )

    assert escalated is False
    assert state.probe_active is False  # de-escalated out of the probe
    assert state.risk_grounded is True
    risk_value = state.slot_data[RISK_SLOT_KEY]
    assert "자살이나 자해 생각은 전혀 없어요" in risk_value
    # The fabrication this bug produced never happens: no later unrelated
    # reply is ever scored, because the probe already concluded at stage 0.
    assert "특별한 지병" not in risk_value
