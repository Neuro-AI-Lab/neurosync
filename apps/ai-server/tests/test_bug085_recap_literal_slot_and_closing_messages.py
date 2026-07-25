"""BUG-085 regression tests (user directive 2026-07-25, "마무리 멘트
재설계"):

  (a) `infer_literal_target_slot` — live repro (session `de33cf67`):
      a rendered turn that RECAPS the prior answer before asking a NEW
      question (e.g. "...신체질환...복용 중인 약...없으시다고 하셨는데,
      혹시 가족분들 중에서...") must attribute the turn to the slot the
      CLOSING question actually asks about (`family_history`), not to an
      earlier recap clause's slot (`medical_history`) that merely shares
      dict-iteration precedence in `_SLOT_TOPIC_KEYWORDS`. The pre-fix
      first-match-wins scan misattributed this and silently dropped a
      valid "don't know" grounding opportunity, causing the same slot to
      be re-asked repeatedly (observed live: `family_history` asked 3x,
      turns 7/9/13, despite two "모르겠" replies) until the deferral
      counter (2 misses) happened to catch up.

  (b) Stage-1 closing message (slot coverage reached, `handoff_ready`):
      the patient-facing utterance must never say "충분한 정보가
      수집되었습니다" or mention "보고서" — that language is replaced by a
      neutral in-progress phrase per the coordinator's exact wording.
"""

from __future__ import annotations

from src.agents.orchestrator import OrchestratorAgent
from src.grounding import infer_literal_target_slot
from src.schemas.orchestrator import SessionState

# ── (a) BUG-085: rightmost-match literal target-slot inference ─────────


class TestBug085RecapTextLiteralSlotAttribution:
    def test_recap_plus_new_question_attributes_to_the_closing_question(self) -> None:
        """Live-repro text (turn 7, session `de33cf67`): recaps
        `medical_history` (already answered "없어요"), then asks about
        `family_history`. Must resolve to `family_history` — the actual
        new question — not `medical_history`."""
        text = (
            "신체질환이나 복용 중인 약이 없으시다고 하셨는데, 혹시 가족분들 "
            "중에서 비슷한 어려움을 겪으셨던 분이 계신가요? 그런 경험이 "
            "있으셨다면 말씀해 주시겠어요?"
        )
        assert infer_literal_target_slot(text) == "family_history"

    def test_no_recap_still_resolves_correctly(self) -> None:
        """A plain single-topic question (no recap clause) is unaffected
        by the rightmost-match change — still resolves to its one slot."""
        text = "혹시 최근에 스스로를 해치고 싶다는 생각이나 죽고 싶다는 마음이 드신 적이 있나요?"
        assert infer_literal_target_slot(text) == "risk_assessment"

    def test_no_match_returns_none(self) -> None:
        assert infer_literal_target_slot("오늘 날씨가 좋네요.") is None

    def test_empty_text_returns_none(self) -> None:
        assert infer_literal_target_slot("") is None

    def test_dont_know_reply_grounds_on_first_answer_despite_recap_text(self) -> None:
        """Integration-level (mirrors BUG-072's own `_update_asked_slot_
        tracking` unit-test shape): the exact live-repro turn/reply pair
        must now ground `family_history` as "unknown" on the FIRST
        "잘 모르겠습니다" reply — no longer requiring a second unanswered
        ask before the round-robin moves on."""
        state = SessionState(session_id="t-bug085")
        state.slot_data = {
            "medical_history": "없음(환자 부인: '둘 다 없어요')",
        }
        state.slot_status = {"medical_history": "denied"}
        state.pending_target_slot = "family_history"
        state.conversation_history = [
            {
                "role": "assistant",
                "content": (
                    "신체질환이나 복용 중인 약이 없으시다고 하셨는데, 혹시 "
                    "가족분들 중에서 비슷한 어려움을 겪으셨던 분이 계신가요? "
                    "그런 경험이 있으셨다면 말씀해 주시겠어요?"
                ),
            },
            {"role": "user", "content": "잘 모르겠습니다."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.slot_status.get("family_history") == "unknown"
        assert state.slot_data.get("family_history")
        assert "미상" in state.slot_data["family_history"]
        # Grounded immediately — the miss counter must never have engaged.
        assert state.asked_slot_counts.get("family_history") is None
        assert "family_history" not in state.deferred_slots


# ── (b) Stage-1 closing message (handoff_ready, routes/chat.py) ────────


class TestBug085Stage1ClosingMessage:
    def test_handoff_ready_message_is_the_redesigned_neutral_phrase(self) -> None:
        # BUG-086/090 (2026-07-25): the literal moved from `routes/chat.py`
        # (a bare hardcoded string) to `agents/orchestrator.py`'s
        # `_HANDOFF_ACK_MESSAGE` — the single source of truth both the
        # immediate stage-1-ack turn (BUG-090) and the routes/chat.py Step
        # 3 branch (now reading `orch_result.assistant_response` instead
        # of re-declaring the text, BUG-086's "never duplicate" fix) share.
        from src.agents import orchestrator as orchestrator_module
        from src.routes import chat as chat_route

        orch_source = orchestrator_module.__loader__.get_source(  # type: ignore[union-attr]
            orchestrator_module.__name__
        )
        assert (
            "네 알겠습니다. 답변 주신 내용을 토대로 증상 확인 중입니다."
            in orch_source
        )
        assert "충분한 정보가 수집되었습니다" not in orch_source
        assert "사전문진 보고서를 작성하겠습니다" not in orch_source
        # No patient-facing "보고서" mention in actual code/string literals —
        # only the code comments explaining the fix reference the word itself.
        non_comment_lines = [
            line for line in orch_source.splitlines() if not line.strip().startswith("#")
        ]
        assert not any("보고서" in line for line in non_comment_lines)

        # routes/chat.py's own Step 3 branch no longer hardcodes the text —
        # it must read it off `orch_result.assistant_response` instead.
        chat_source = chat_route.__loader__.get_source(chat_route.__name__)  # type: ignore[union-attr]
        assert "네 알겠습니다. 답변 주신 내용을 토대로 증상 확인 중입니다." not in chat_source
        assert "assistant_response=orch_result.assistant_response" in chat_source
