"""BUG-077 regression tests — target-question binding (item A) and
bare-denial ask-evidence attribution to the literally-asked slot, not the
internally-tracked target (item B).

No live LLM calls: item (A)'s end-to-end guard-loop test uses a
deterministic stub adapter (same pattern as
`test_dialogue_self_referential_relief.py`); item (B) exercises
`OrchestratorAgent._update_asked_slot_tracking` directly (rule-based, no
model call per that agent's own module docstring).
"""

from __future__ import annotations

import asyncio

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.agents.orchestrator import OrchestratorAgent
from src.grounding import infer_literal_target_slot
from src.prompts.loader import PromptLoader
from src.schemas.dialogue import DialogueInput
from src.schemas.orchestrator import SessionState

# ── Unit: infer_literal_target_slot (shared primitive) ──────────────────


class TestInferLiteralTargetSlot:
    def test_specific_question_resolves_its_own_slot(self) -> None:
        assert (
            infer_literal_target_slot("혹시 그런 순간에 힘이 되어주는 사람이나 것이 있으신가요?")
            == "personal_social_history"
        )
        assert (
            infer_literal_target_slot("최근 술, 수면제, 진정제 등 사용하신 적 있으신가요?")
            == "substance_use_history"
        )

    def test_generic_catchall_resolves_to_none(self) -> None:
        assert infer_literal_target_slot("혹시 다른 증상이나 걱정되는 부분이 있으신가요?") is None

    def test_empty_text_resolves_to_none(self) -> None:
        assert infer_literal_target_slot("") is None


# ── (B) Orchestrator: bare-denial attribution to the literal slot ───────


class TestBug077DenialAttribution:
    def test_denial_attributed_to_literally_asked_slot_not_internal_target(self) -> None:
        """Repro shape (session `ad0da8c1`, turn 2/3): internal target was
        `history_of_present_illness` but the rendered question literally
        asked about `personal_social_history`. The bare denial must ground
        to the LITERAL slot, and the internal target must NOT be marked
        denied off this reply."""
        state = SessionState(session_id="t-bug077-attrib")
        state.pending_target_slot = "history_of_present_illness"
        state.conversation_history = [
            {
                "role": "assistant",
                "content": "혹시 그런 순간에 힘이 되어주는 사람이나 것이 있으신가요?",
            },
            {"role": "user", "content": "없어요."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.slot_status.get("personal_social_history") == "denied"
        assert "환자 부인" in state.slot_data.get("personal_social_history", "")
        assert state.slot_status.get("history_of_present_illness") != "denied"
        assert state.asked_slot_counts.get("history_of_present_illness") == 1

    def test_denial_not_attributed_when_rendered_question_is_ambiguous_catchall(
        self,
    ) -> None:
        """Repro shape (turns 3-6): rendered text is a generic catch-all —
        the denial must NOT be grounded to the internal target at all
        (over-attribution symptom), and target falls through to its own
        miss counter instead."""
        state = SessionState(session_id="t-bug077-catchall")
        state.pending_target_slot = "medical_history"
        state.conversation_history = [
            {"role": "assistant", "content": "혹시 다른 증상이나 걱정되는 부분이 있으신가요?"},
            {"role": "user", "content": "없어요."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert "medical_history" not in state.slot_data
        assert state.slot_status.get("medical_history") != "denied"
        assert state.asked_slot_counts.get("medical_history") == 1

    def test_same_slot_literal_and_target_unaffected_bug072_regression(self) -> None:
        """BUG-072's own common case (literal == target) is unchanged."""
        state = SessionState(session_id="t-bug077-same")
        state.pending_target_slot = "personal_social_history"
        state.conversation_history = [
            {"role": "assistant", "content": "주변에 도움을 요청할 수 있는 사람이 있으신가요?"},
            {"role": "user", "content": "없어."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.slot_status.get("personal_social_history") == "denied"
        assert state.asked_slot_counts.get("personal_social_history") is None

    def test_missing_assistant_history_falls_back_to_target_no_regression(self) -> None:
        """When no assistant turn is on record at all (caller never
        threaded `add_assistant_turn`), the pre-BUG-077 behavior (trust
        `target` unconditionally) is preserved — this is the exact shape
        the pre-existing BUG-072 e2e tests construct."""
        state = SessionState(session_id="t-bug077-no-history")
        state.pending_target_slot = "personal_social_history"
        state.conversation_history = [
            {"role": "user", "content": "없어."},
        ]

        OrchestratorAgent._update_asked_slot_tracking(state)  # noqa: SLF001

        assert state.slot_status.get("personal_social_history") == "denied"


# ── (A) DialogueAgent: target-binding guard + catch-all session cap ─────


class TestBug077CatchallDetection:
    def test_catchall_question_detected(self) -> None:
        assert DialogueAgent._is_catchall_question(
            "혹시 다른 증상이나 걱정되는 부분이 있으신가요?"
        ) is True

    def test_specific_question_not_catchall(self) -> None:
        assert DialogueAgent._is_catchall_question(
            "최근 술이나 수면제를 드신 적이 있으신가요?"
        ) is False

    def test_non_question_not_catchall(self) -> None:
        assert DialogueAgent._is_catchall_question("네, 알겠습니다.") is False

    def test_count_prior_catchall_turns(self) -> None:
        history = [
            {"role": "assistant", "content": "혹시 다른 증상이나 걱정되는 부분이 있으신가요?"},
            {"role": "user", "content": "없어요."},
            {"role": "assistant", "content": "최근 술이나 수면제를 드신 적이 있으신가요?"},
            {"role": "user", "content": "없어요."},
            {"role": "assistant", "content": "혹시 다른 걱정되는 부분은 없으신가요?"},
        ]
        assert DialogueAgent._count_prior_catchall_turns(history) == 2


class _CatchallAdapter(LLMAdapter):
    """Deterministic stub — every call returns a generic catch-all
    question, forcing the target-binding guard's retry budget to exhaust
    (BUG-077 item A)."""

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        return ChatResponse(
            content=(
                '{"assistant_response": "그렇군요. 혹시 다른 증상이나 '
                '걱정되는 부분이 있으신가요?"}'
            ),
            model="stub-model",
        )


class _StubSelection:
    adapter_name = "stub"
    model_id = "stub-model"
    supports_json_schema = False
    supports_json_object = True


class _StubRouter:
    def select_model(self, agent_name, require_json=True):
        return _StubSelection()

    def get_adapter(self, name):
        return _CatchallAdapter()

    def record_success(self, name):
        pass

    def record_failure(self, name, exc):
        pass

    def get_fallback(self, agent_name, adapter_name, err):
        return None


def _make_dialogue_input(**overrides) -> DialogueInput:
    base = dict(
        session_id="test-session-bug077",
        user_message="네.",
        conversation_history=[],
        filled_slots={"chief_complaint": "우울감"},
        safety_result=None,
        session_state={},
        slot_updates_this_turn=None,
    )
    base.update(overrides)
    return DialogueInput(**base)


def test_run_does_not_intercept_first_catchall_this_session() -> None:
    """State-visibility is the PRIMARY mechanism (user directive
    2026-07-25) — the guard loop is a repeat-only safety net, so a
    session's FIRST generic catch-all is never even intercepted (no retry,
    no degrade): it ships as the model produced it, and only the
    `_build_asked_topic_history` ledger sees it going into the NEXT turn."""
    agent = DialogueAgent(model_router=_StubRouter(), prompt_loader=PromptLoader("prompts"))
    inp = _make_dialogue_input(conversation_history=[])
    output = asyncio.run(agent.run(inp))

    assert output.retry_count == 0
    assert "target_mismatch" not in output.retry_reasons
    assert output.fall_through is False
    assert output.exhaustion_degrade is None
    assert DialogueAgent._is_catchall_question(output.assistant_response) is True


def test_run_force_degrades_repeat_catchall_this_session() -> None:
    """A REPEAT generic catch-all (one already shipped earlier this
    session) is the safety net's trigger condition — force-degraded into a
    deterministic, target-bound question instead of shipping another
    catch-all."""
    agent = DialogueAgent(model_router=_StubRouter(), prompt_loader=PromptLoader("prompts"))
    prior_catchall_history = [
        {"role": "assistant", "content": "혹시 다른 증상이나 걱정되는 부분이 있으신가요?"},
        {"role": "user", "content": "없어요."},
    ]
    inp = _make_dialogue_input(conversation_history=prior_catchall_history)
    output = asyncio.run(agent.run(inp))

    assert output.exhaustion_degrade == "target_mismatch"
    assert DialogueAgent._is_catchall_question(output.assistant_response) is False
    assert output.fall_through is False


# ── (A, primary mechanism) state-visibility ledger ──────────────────────


class TestAskedTopicHistoryLedger:
    def test_specific_and_catchall_turns_labeled_distinctly(self) -> None:
        history = [
            {"role": "assistant", "content": "최근 술이나 수면제를 드신 적이 있으신가요?"},
            {"role": "user", "content": "가끔 맥주 한 캔 정도요."},
            {"role": "assistant", "content": "혹시 다른 증상이나 걱정되는 부분이 있으신가요?"},
            {"role": "user", "content": "딱히 없어요."},
        ]
        lines = DialogueAgent._build_asked_topic_history(history)  # noqa: SLF001
        assert len(lines) == 2
        assert "특정 주제 없는 범용 질문" in lines[1]
        assert "가끔 맥주 한 캔" in lines[0]

    def test_empty_history_yields_no_ledger(self) -> None:
        assert DialogueAgent._build_asked_topic_history([]) == []  # noqa: SLF001
        assert DialogueAgent._build_asked_topic_history(None) == []  # noqa: SLF001

    def test_capped_to_last_six_pairs(self) -> None:
        history: list[dict[str, str]] = []
        for i in range(10):
            history.append({"role": "assistant", "content": f"질문 {i}?"})
            history.append({"role": "user", "content": f"답변 {i}"})
        lines = DialogueAgent._build_asked_topic_history(history)  # noqa: SLF001
        assert len(lines) == 6


class TestSlotContextStateVisibility:
    def test_denied_slot_shown_separately_from_filled(self) -> None:
        """BUG-084b (2026-07-25): this section's item labels now render as
        natural-language topic labels (`_topic_label`), never the raw
        `SLOT_KEY` identifier — updated from the pre-fix assertion, which
        checked for the raw key itself; the separation-into-its-own-
        section behavior this test targets is otherwise unchanged."""
        agent = DialogueAgent(model_router=None, prompt_loader=PromptLoader("prompts"))
        context = agent._build_slot_context(  # noqa: SLF001
            filled_slots={
                "chief_complaint": "우울감",
                "personal_social_history": "없음(환자 부인: '없어요')",
            },
            session_state={
                "slot_status": {"personal_social_history": "denied"},
                "slot_data": {},
            },
            conversation_history=[],
        )
        assert "환자가 이미 부인(denied)함" in context
        assert "personal_social_history" not in context  # BUG-084b: raw key never leaks
        assert "주변 지지체계" in context.split("환자가 이미 부인(denied)함")[1]
        # The positive slot stays under the ordinary "이미 수집 완료" bucket.
        positive_section = context.split("환자가 이미 부인(denied)함")[0]
        assert "오늘 가장 힘든 문제" in positive_section

    def test_qa_history_ledger_present_in_rendered_context(self) -> None:
        agent = DialogueAgent(model_router=None, prompt_loader=PromptLoader("prompts"))
        context = agent._build_slot_context(  # noqa: SLF001
            filled_slots={},
            session_state={},
            conversation_history=[
                {"role": "assistant", "content": "혹시 다른 증상이나 걱정되는 부분이 있으신가요?"},
                {"role": "user", "content": "없어요."},
            ],
        )
        assert "질문-응답 이력" in context
        assert "특정 주제 없는 범용 질문" in context


class TestResolveRoundRobinTarget:
    def test_none_on_opening_turn(self) -> None:
        inp = _make_dialogue_input(session_state={"opening_turn": True})
        assert DialogueAgent._resolve_round_robin_target(inp) is None  # noqa: SLF001

    def test_none_on_probe_turn(self) -> None:
        inp = _make_dialogue_input(session_state={"probe_instruction": "안전 확인 질문"})
        assert DialogueAgent._resolve_round_robin_target(inp) is None  # noqa: SLF001

    def test_matches_compute_target_slot_when_steering(self) -> None:
        inp = _make_dialogue_input(filled_slots={"chief_complaint": "우울감"})
        expected = DialogueAgent.compute_target_slot(
            inp.filled_slots, inp.conversation_history, deferred_slots=set()
        )
        assert DialogueAgent._resolve_round_robin_target(inp) == expected  # noqa: SLF001
