"""BUG-072/073 regression tests — bare-denial direct-compose grounding,
round-robin advancement, and orchestrator/dialogue target-slot consistency.

No LLM calls: `SafetyClassifierAgent` is mocked (orchestrator's own state
machine is rule-based, per its module docstring) and `DialogueAgent`'s
target computation is exercised via its own pure `compute_target_slot`
staticmethod — no `LLMAdapter`/model_router involved either.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.dialogue import DialogueAgent
from src.agents.orchestrator import OrchestratorAgent
from src.grounding import RISK_SLOT_KEY
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.orchestrator import OrchestratorInput, SessionStage, SessionState
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


# ── (a) BUG-072: bare-denial direct-compose grounding ──────────────────


class TestBug072BareDenialDirectCompose:
    def test_unit_bare_denial_grounds_on_first_answer(self) -> None:
        """Unit-level: `_update_asked_slot_tracking` grounds a bare "없어"
        reply on the FIRST answer — the miss counter never engages, so the
        2-miss deferral never fires and no re-ask is needed."""
        state = SessionState(session_id="t-bug072-unit")
        state.pending_target_slot = "personal_social_history"
        state.conversation_history = [
            {"role": "assistant", "content": "주변에 도움을 요청할 수 있는 사람이 있으신가요?"},
            {"role": "user", "content": "없어."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.slot_status.get("personal_social_history") == "denied"
        assert state.slot_data.get("personal_social_history")
        assert "환자 부인" in state.slot_data["personal_social_history"]
        assert state.asked_slot_counts.get("personal_social_history") is None
        assert "personal_social_history" not in state.deferred_slots

    def test_unit_longer_reply_with_negation_is_not_direct_composed(self) -> None:
        """A reply that merely CONTAINS a negation morpheme alongside real
        substantive content must NOT be short-circuited into a bare-denial
        compose — it should fall through to the ordinary miss-counter path
        so the real extractor gets a chance to capture the substantive
        content (BUG-072 scope guard, `_BARE_DENIAL_MAX_CHARS`)."""
        state = SessionState(session_id="t-bug072-unit-long")
        state.pending_target_slot = "personal_social_history"
        state.conversation_history = [
            {"role": "assistant", "content": "주변에 도움을 요청할 수 있는 사람이 있으신가요?"},
            {"role": "user", "content": "그건 없는데 요즘 잠을 잘 못 자요."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert "personal_social_history" not in state.slot_data
        assert state.slot_status.get("personal_social_history") != "denied"
        assert state.asked_slot_counts.get("personal_social_history") == 1

    @pytest.mark.asyncio
    async def test_e2e_three_bare_denials_ground_and_advance_round_robin(
        self,
    ) -> None:
        """End-to-end via `process_turn`: a patient answering "없어" to a
        directly-asked slot question grounds it as "denied" on the FIRST
        reply, round-robin steering advances to the NEXT missing slot, and
        the slot is never re-asked (no miss ever recorded, so the 2-miss
        deferral threshold is never reached)."""
        agent = _make_orchestrator()

        # Only chief_complaint prefilled — 5 more patient-fillable slots
        # (past_psychiatric_history/medical_history/personal_social_history/
        # family_history/substance_use_history) plus history_of_present_
        # illness remain, keeping coverage well under the 0.7 handoff-ready
        # threshold for the turns this test exercises, so dialogue_loop
        # keeps genuinely continuing (round-robin target tracked every
        # turn) instead of exiting into the post-dialogue pipeline.
        state = SessionState(session_id="t-bug072-e2e")
        state.slot_data = {"chief_complaint": "우울감", RISK_SLOT_KEY: "자살/자해 사고 부인"}
        state.risk_grounded = True  # Cluster C is out of this test's scope

        turn1 = await agent.process_turn(
            OrchestratorInput(session_id="t-bug072-e2e", raw_input="시작", session_state=state)
        )
        assert turn1.current_stage == SessionStage.dialogue_loop
        first_target = turn1.session_state.dialogue_target_slot
        assert first_target is not None

        turn2 = await agent.process_turn(
            OrchestratorInput(
                session_id="t-bug072-e2e", raw_input="없어.",
                session_state=turn1.session_state,
            )
        )
        assert turn2.current_stage == SessionStage.dialogue_loop
        # The FIRST target is grounded as "denied" on this single reply —
        # no miss ever recorded for it.
        assert turn2.session_state.slot_status.get(first_target) == "denied"
        assert turn2.session_state.asked_slot_counts.get(first_target) is None
        assert first_target not in turn2.session_state.deferred_slots
        # Round-robin steering moved to a DIFFERENT slot.
        second_target = turn2.session_state.dialogue_target_slot
        assert second_target != first_target
        assert second_target is not None

        turn3 = await agent.process_turn(
            OrchestratorInput(
                session_id="t-bug072-e2e", raw_input="없어요.",
                session_state=turn2.session_state,
            )
        )
        assert turn3.session_state.slot_status.get(second_target) == "denied"
        assert turn3.session_state.asked_slot_counts.get(second_target) is None
        assert second_target not in turn3.session_state.deferred_slots
        # The FIRST target's denied status/value is untouched by later turns.
        assert turn3.session_state.slot_status.get(first_target) == "denied"


# ── (c) BUG-073: orchestrator target == dialogue render target ─────────


class TestBug073TargetConsistency:
    @pytest.mark.asyncio
    async def test_dialogue_target_slot_matches_dialogue_agent_render_target_20_turns(
        self,
    ) -> None:
        """For 20 turns, whatever `DialogueAgent` would independently
        render as its question target (via its own `compute_target_slot`,
        using the SAME `state.slot_data`/`deferred_slots`/
        `conversation_history` inputs `routes/chat.py` threads into it)
        must agree with `state.dialogue_target_slot` — the single source
        of truth BUG-073 introduces. When the probe/mandatory-SI-screen
        path is active instead (DialogueAgent would render the probe
        context, not a round-robin question), `dialogue_target_slot` must
        equal `risk_assessment` (the implicit target of that path)."""
        agent = _make_orchestrator()

        state = SessionState(session_id="t-bug073-consistency")
        session_id = "t-bug073-consistency"

        for turn in range(20):
            # Alternate a plain answer / a bare denial so slots fill up
            # organically over the session, same as a real conversation.
            raw = "네, 그런 편이에요." if turn % 2 == 0 else "없어요."
            result = await agent.process_turn(
                OrchestratorInput(session_id=session_id, raw_input=raw, session_state=state)
            )
            state = result.session_state
            if result.current_stage != SessionStage.dialogue_loop:
                # Session exited the dialogue loop this turn (post-dialogue
                # pipeline / crisis / post-handoff short-circuit) — no
                # round-robin target is computed/rendered on a turn like
                # this, so there is nothing to compare.
                if state.handoff_delivered:
                    break
                continue

            if state.probe_active or state.risk_question_pending:
                assert state.dialogue_target_slot == RISK_SLOT_KEY
                continue

            # Mirror DialogueAgent._build_slot_context's own BUG-056 union
            # (routes/chat.py threads `state.slot_data` into DialogueAgent's
            # session_state dict, unioned with the caller's filled_slots —
            # here the caller map is empty, so the union is just slot_data).
            rendered_target = DialogueAgent.compute_target_slot(
                state.slot_data, state.conversation_history,
                deferred_slots=set(state.deferred_slots),
            )
            assert rendered_target == state.dialogue_target_slot, (
                f"turn {turn}: orchestrator target "
                f"{state.dialogue_target_slot!r} != DialogueAgent render "
                f"target {rendered_target!r}"
            )
