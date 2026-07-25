"""Coordinator directive (2026-07-25, "수집-불가 응답의 즉시-이동 규칙")
regression tests.

A "don't-know"/unanswerable reply ("잘 모르겠습니다") must be recorded
distinctly from an active denial ("없어요") — `slot_status="unknown"`, not
`"denied"` — and, exactly like a bare denial (BUG-072), must resolve the
slot IMMEDIATELY (this turn), never requiring the `_ASK_DEFER_THRESHOLD`
(2-miss) counter to run out before the round-robin moves on.

No live LLM calls — `reply_is_dont_know`/`_update_asked_slot_tracking` are
pure/rule-based.
"""

from __future__ import annotations

import pytest

from src.agents.dialogue import DialogueAgent
from src.agents.orchestrator import OrchestratorAgent
from src.grounding import reply_has_negation, reply_is_dont_know
from src.prompts.loader import PromptLoader
from src.schemas.orchestrator import SessionState

# ── (1) grounding.reply_is_dont_know — detector unit tests ─────────────


class TestReplyIsDontKnow:
    @pytest.mark.parametrize(
        "text",
        ["잘 모르겠습니다", "모르겠어요", "모름", "모르겠어", "잘 몰라요"],
    )
    def test_dont_know_replies_detected(self, text: str) -> None:
        assert reply_is_dont_know(text) is True

    @pytest.mark.parametrize(
        "text",
        ["없어요", "아니요", "안 해요", "그런 건 없습니다"],
    )
    def test_active_denials_not_flagged_as_dont_know(self, text: str) -> None:
        assert reply_is_dont_know(text) is False

    def test_dont_know_text_also_matches_the_broader_negation_check(self) -> None:
        """`reply_has_negation` is unchanged/unaffected — "모르"-rooted
        text still matches it too. Callers distinguishing the two MUST
        check `reply_is_dont_know` FIRST (see
        `OrchestratorAgent._update_asked_slot_tracking`)."""
        assert reply_has_negation("잘 모르겠습니다") is True
        assert reply_is_dont_know("잘 모르겠습니다") is True


# ── (2) orchestrator: immediate-move grounding, distinct status ────────


class TestUpdateAskedSlotTrackingDontKnowImmediateMove:
    def test_dont_know_reply_grounds_as_unknown_not_denied(self) -> None:
        """User-directive worked example: Q약물 -> A"잘 모르겠습니다"."""
        state = SessionState(session_id="t-dontknow-unit")
        state.pending_target_slot = "medical_history"
        state.conversation_history = [
            {"role": "assistant", "content": "기존 처방 약 외 새로 복용 중인 약이 있으신가요?"},
            {"role": "user", "content": "잘 모르겠습니다"},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.slot_status.get("medical_history") == "unknown"
        assert state.slot_data.get("medical_history")
        assert "미상" in state.slot_data["medical_history"]
        assert "환자 부인" not in state.slot_data["medical_history"]

    def test_dont_know_reply_resolves_immediately_no_defer_counter_needed(self) -> None:
        """Immediate-move requirement: the slot is fully resolved on the
        FIRST don't-know answer — the 2-miss `_ASK_DEFER_THRESHOLD` counter
        never even engages, and the round-robin excludes this slot from
        `missing_questionable_slots` on the very next turn."""
        state = SessionState(session_id="t-dontknow-immediate")
        state.pending_target_slot = "medical_history"
        state.conversation_history = [
            {"role": "assistant", "content": "기존 처방 약 외 새로 복용 중인 약이 있으신가요?"},
            {"role": "user", "content": "잘 모르겠습니다"},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.asked_slot_counts.get("medical_history") is None
        assert "medical_history" not in state.deferred_slots
        missing = DialogueAgent.missing_questionable_slots(state.slot_data)
        assert "medical_history" not in missing

    def test_bare_denial_still_grounds_as_denied_unchanged(self) -> None:
        """No-regression: BUG-072's own bare-denial path is unaffected —
        an active denial still grounds with status="denied"."""
        state = SessionState(session_id="t-dontknow-denial-noregress")
        state.pending_target_slot = "personal_social_history"
        state.conversation_history = [
            {"role": "assistant", "content": "주변에 도움을 요청할 수 있는 사람이 있으신가요?"},
            {"role": "user", "content": "없어."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.slot_status.get("personal_social_history") == "denied"
        assert "환자 부인" in state.slot_data["personal_social_history"]

    def test_longer_dont_know_reply_with_substantive_content_not_direct_composed(self) -> None:
        """Same BUG-072 scope guard as bare denial — a longer reply that
        happens to contain a don't-know morpheme alongside substantive
        content must still go through the real extractor path."""
        state = SessionState(session_id="t-dontknow-long")
        state.pending_target_slot = "medical_history"
        state.conversation_history = [
            {"role": "assistant", "content": "기존 처방 약 외 새로 복용 중인 약이 있으신가요?"},
            {
                "role": "user",
                "content": "그건 잘 모르겠는데 요즘 두통약은 자주 먹는 것 같아요.",
            },
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert "medical_history" not in state.slot_data
        assert state.slot_status.get("medical_history") != "unknown"
        assert state.asked_slot_counts.get("medical_history") == 1


# ── (3) dialogue.py: unknown-status ledger section ──────────────────────


class TestDialogueSlotContextUnknownSection:
    def test_unknown_item_rendered_under_its_own_section(self) -> None:
        agent = DialogueAgent(model_router=None, prompt_loader=PromptLoader("prompts"))
        context = agent._build_slot_context(  # noqa: SLF001
            filled_slots={
                "chief_complaint": "잠을 못 잠",
                "medical_history": "미상(환자 응답: '잘 모르겠습니다')",
            },
            session_state={"slot_status": {"medical_history": "unknown"}},
            conversation_history=[],
        )
        assert "모른다고 답함" in context
        assert "짧게" in context and "다음 미수집 주제" in context
        # not miscategorized as either positive or denied.
        assert "환자가 이미 부인" not in context or "medical_history" not in context
