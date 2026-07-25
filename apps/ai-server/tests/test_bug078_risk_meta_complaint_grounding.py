"""BUG-078 regression tests — `_advance_safety_probe`'s `risk_question_
pending` branch must not fabricate a `risk_assessment` SI-denial citation
from a patient meta-complaint about repetitive questioning, and must not
permanently block a later, genuine SI denial from being captured.

Live repro (`experiments/EXP-032_f1_reverify/iteration2`, session
`ef4a2b55-...`): turn 6's meta-complaint ("없다니까 왜 자꾸 물어봐요.")
was composed verbatim into `slot_data["risk_assessment"]` via
`reply_has_negation` alone (no topic-relevance check), and
`risk_grounded=True` then blocked turn 10's genuine, explicit SI denial
from ever being recorded.

No LLM calls: `_advance_safety_probe` is rule-based (per the orchestrator
module's own docstring) — exercised directly as a unit, and once via
`process_turn` for an end-to-end regression check. Mirrors
`test_bug072_073_grounding_and_target.py`'s existing pattern.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.grounding import RISK_SLOT_KEY, is_meta_utterance
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


# ── (a) is_meta_utterance primitive ──────────────────────────────────────


class TestIsMetaUtterance:
    @pytest.mark.parametrize(
        "text",
        [
            "없다니까 왜 자꾸 물어봐요.",
            "몇 번을 말해요.",
            "그만 좀 물어보세요.",
            "아까도 말했잖아요.",
            "방금 말씀드렸는데요.",
        ],
    )
    def test_recognizes_direct_and_indirect_meta_complaints(self, text: str) -> None:
        assert is_meta_utterance(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "없어요.",
            "자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
            "그냥 요즘 계속 피곤한 느낌이에요.",
            "딱히 없어요.",
            "",
        ],
    )
    def test_does_not_flag_genuine_answers(self, text: str) -> None:
        assert is_meta_utterance(text) is False


# ── (b) unit: `_advance_safety_probe`'s risk_question_pending branch ────


class TestBug078MetaComplaintNotGroundedAsSiDenial:
    def test_meta_complaint_does_not_ground_or_set_risk_grounded(self) -> None:
        """Reproduces the live repro directly: `risk_question_pending=True`
        + a meta-complaint reply must NOT compose `risk_assessment` and
        must NOT set `risk_grounded=True` (both assertions fail before the
        fix)."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug078-meta")
        state.risk_question_pending = True

        inp = OrchestratorInput(
            session_id="t-bug078-meta",
            raw_input="없다니까 왜 자꾸 물어봐요.",
            session_state=state,
        )

        escalated = agent._advance_safety_probe(inp, state, _safe_output())  # noqa: SLF001

        assert escalated is False
        assert RISK_SLOT_KEY not in state.slot_data
        assert state.risk_grounded is False

    @pytest.mark.parametrize(
        "text",
        ["몇 번을 말해요.", "그만 좀 물어보세요.", "아까도 말했잖아요."],
    )
    def test_other_meta_complaint_phrasings_also_do_not_ground(self, text: str) -> None:
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug078-meta-variants")
        state.risk_question_pending = True

        inp = OrchestratorInput(
            session_id="t-bug078-meta-variants", raw_input=text, session_state=state,
        )
        agent._advance_safety_probe(inp, state, _safe_output())  # noqa: SLF001

        assert RISK_SLOT_KEY not in state.slot_data
        assert state.risk_grounded is False

    def test_genuine_bare_denial_still_grounds_correctly_no_regression(self) -> None:
        """Companion/regression guard: a genuine short denial actually
        answering the SI screen (no meta-complaint phrasing) must still
        ground exactly as before this fix (BUG-072/073 lineage unaffected)."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug078-genuine")
        state.risk_question_pending = True

        inp = OrchestratorInput(
            session_id="t-bug078-genuine", raw_input="없어요.", session_state=state,
        )
        agent._advance_safety_probe(inp, state, _safe_output())  # noqa: SLF001

        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data
        assert "없어요" in state.slot_data[RISK_SLOT_KEY]

    def test_genuine_explicit_denial_still_grounds_correctly_no_regression(self) -> None:
        """A longer, explicit, unambiguous SI denial (BUG-078 repro turn
        10's own text) must ground correctly when it actually answers a
        pending SI screen — it does not happen to match any meta-utterance
        keyword, so the new gate must not falsely intercept it."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug078-explicit")
        state.risk_question_pending = True

        inp = OrchestratorInput(
            session_id="t-bug078-explicit",
            raw_input="자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
            session_state=state,
        )
        agent._advance_safety_probe(inp, state, _safe_output())  # noqa: SLF001

        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data
        assert "자살이나 자해 생각은 전혀 없어요" in state.slot_data[RISK_SLOT_KEY]

    def test_real_denial_after_meta_complaint_is_captured_on_re_ask(self) -> None:
        """BUG-078's core safety claim: a meta-complaint turn must never
        permanently block a LATER genuine SI denial from being captured —
        once the SI screen is re-armed (mirrors
        `_resolve_dialogue_probe_instruction` re-setting
        `risk_question_pending=True` on the next SI-screen turn), the real
        answer grounds normally."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug078-recapture")

        # Turn N: SI screen pending, patient meta-complains — must not
        # ground and must not poison risk_grounded.
        state.risk_question_pending = True
        inp1 = OrchestratorInput(
            session_id="t-bug078-recapture",
            raw_input="없다니까 왜 자꾸 물어봐요.",
            session_state=state,
        )
        agent._advance_safety_probe(inp1, state, _safe_output())  # noqa: SLF001
        assert state.risk_grounded is False
        assert RISK_SLOT_KEY not in state.slot_data

        # Turn N+k: the SI screen is asked again (re-armed the same way
        # `_resolve_dialogue_probe_instruction` would, since risk_grounded
        # is still False) — this time the patient actually answers.
        state.risk_question_pending = True
        inp2 = OrchestratorInput(
            session_id="t-bug078-recapture",
            raw_input="자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
            session_state=state,
        )
        agent._advance_safety_probe(inp2, state, _safe_output())  # noqa: SLF001

        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data
        assert "자살이나 자해 생각은 전혀 없어요" in state.slot_data[RISK_SLOT_KEY]


# ── (c) e2e via process_turn: risk_question_pending naturally re-arms ───


class TestBug078EndToEndReAsk:
    @pytest.mark.asyncio
    async def test_meta_complaint_leaves_risk_still_missing_and_pipeline_continues(
        self,
    ) -> None:
        """End-to-end: with `risk_question_pending=True` already set on
        entry (mirrors the live repro's turn 6, where the prior turn's SI
        screen render already armed it), a meta-complaint reply must leave
        the session in dialogue_loop with risk_assessment still ungrounded
        — not silently marked answered, not crashing, not escalating."""
        agent = _make_orchestrator()

        state = SessionState(session_id="t-bug078-e2e")
        state.slot_data = {
            "chief_complaint": "우울감",
            "history_of_present_illness": "한달 전부터",
            "medical_history": "없음(환자 부인)",
            "family_history": "없음(환자 부인)",
        }
        state.risk_question_pending = True

        result = await agent.process_turn(
            OrchestratorInput(
                session_id="t-bug078-e2e",
                raw_input="없다니까 왜 자꾸 물어봐요.",
                session_state=state,
            )
        )

        assert RISK_SLOT_KEY not in result.session_state.slot_data
        assert result.session_state.risk_grounded is False
