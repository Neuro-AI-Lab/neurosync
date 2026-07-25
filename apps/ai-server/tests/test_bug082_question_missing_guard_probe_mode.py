"""BUG-082 regression — `question_missing`'s guard was structurally inert
on probe-mode turns (`target_slot is None` whenever `session_state.
probe_instruction`/`risk_question_pending` is set, by
`_resolve_round_robin_target`'s own design), so a zero-question candidate
on an active SI-screen turn was invisible to every guard. Fix: a dedicated
`risk_question_missing` check, scoped to `is_risk_target_turn` (the same
gate `risk_compound_violation` already uses) and independent of
`target_slot` (fix direction (a) from the BUG-082 entry).

No live LLM calls — `LLMAdapter` is stubbed deterministically, same
pattern as `test_dialogue_self_referential_relief.py`.
"""

from __future__ import annotations

import asyncio

import pytest

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.prompts.loader import PromptLoader
from src.schemas.dialogue import DialogueInput

# ── Unit: the computation itself (via a lightweight run() probe) ────────


class _StubSelection:
    adapter_name = "stub"
    model_id = "stub-model"
    supports_json_schema = False
    supports_json_object = True


class _StubRouter:
    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    def select_model(self, agent_name, require_json=True):
        return _StubSelection()

    def get_adapter(self, name):
        return self._adapter

    def record_success(self, name):
        pass

    def record_failure(self, name, exc):
        pass

    def get_fallback(self, agent_name, adapter_name, err):
        return None


class _QuestionlessAdapter(LLMAdapter):
    """Every call ships a zero-question, off-topic candidate — the BUG-082
    live repro's exact shape ("그런 변화가 있었군요.", no "?")."""

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        return ChatResponse(
            content='{"assistant_response": "그런 변화가 있었군요."}',
            model="stub-model",
        )


class _TwoQuestionAdapter(LLMAdapter):
    """Ships a compound (2-question) candidate — must NOT be caught by the
    new `risk_question_missing` check (that's `risk_compound_question`'s
    job); regression guard against the two checks colliding."""

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
                '{"assistant_response": "그런 마음이 드셨군요. 최근 스스로를 '
                '해치고 싶다는 생각이 드셨나요? 아니면 다른 사람을 해치고 '
                '싶으신가요?"}'
            ),
            model="stub-model",
        )


def _probe_turn_input(user_message: str) -> DialogueInput:
    return DialogueInput(
        session_id="test-session-bug082",
        user_message=user_message,
        conversation_history=[
            {
                "role": "assistant",
                "content": "최근 스스로를 해치고 싶거나 죽고 싶다는 생각이 든 적이 있으신가요?",
            },
            {"role": "user", "content": "없다니까 왜 자꾸 물어봐요."},
        ],
        filled_slots={},
        safety_result={"risk_level": "low"},
        # session_state carries the active SI-screen marker — same shape
        # `OrchestratorAgent._resolve_dialogue_probe_instruction` sets.
        session_state={
            "probe_instruction": "안전 확인이 필요합니다.",
            "risk_question_pending": True,
        },
        slot_updates_this_turn=None,
    )


def test_resolve_round_robin_target_is_none_on_probe_mode_turn() -> None:
    """Confirms the BUG-082 repro's precondition still holds — `target_
    slot` is `None` on a probe-mode turn (`question_missing`'s own guard is
    inert here), so `risk_question_missing` (independent of `target_slot`)
    is the only mechanism that can catch a zero-question candidate."""
    inp = _probe_turn_input("자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.")
    assert DialogueAgent._resolve_round_robin_target(inp) is None  # noqa: SLF001


def test_run_forces_si_reask_on_zero_question_probe_turn() -> None:
    """End-to-end guard loop: a question-less candidate on an active
    SI-screen turn is caught by `risk_question_missing` and, on retry-
    budget exhaustion, degraded to a deterministic SI re-ask — never
    shipped unmodified."""
    agent = DialogueAgent(
        model_router=_StubRouter(_QuestionlessAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    inp = _probe_turn_input(
        "자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요."
    )
    output = asyncio.run(agent.run(inp))

    assert "?" in output.assistant_response
    assert output.exhaustion_degrade == "risk_question_missing"
    assert "risk_question_missing" in output.retry_reasons
    # BUG-082 fix note: the composer must not leak the internal
    # "(반드시 한 가지만 물어야 함)" annotation into patient-facing text.
    assert "반드시 한 가지만 물어야 함" not in output.assistant_response


def test_run_does_not_flag_two_question_candidate_as_question_missing() -> None:
    """Regression guard: a compound-question candidate on the same
    probe-mode turn is `risk_compound_question`'s concern, not `risk_
    question_missing`'s — the two checks must not collide."""
    agent = DialogueAgent(
        model_router=_StubRouter(_TwoQuestionAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    inp = _probe_turn_input("아니요, 그런 생각 없어요.")
    output = asyncio.run(agent.run(inp))

    assert output.exhaustion_degrade == "risk_compound_question"
    assert output.assistant_response.count("?") == 1


@pytest.mark.parametrize(
    "target_slot,guide_fragment",
    [
        ("risk_assessment", "스스로를 해치고 싶거나 죽고 싶다는 생각"),
        ("chief_complaint", "오늘 가장 도움받고 싶은"),
    ],
)
def test_force_target_question_strips_instructional_parenthetical(
    target_slot: str, guide_fragment: str
) -> None:
    """Unit: `_force_target_question`'s composed text must never leak a
    trailing internal-instruction parenthetical (only `risk_assessment`'s
    guide entry carries one today, but the strip is generic)."""
    composed = DialogueAgent._force_target_question(  # noqa: SLF001
        "그런 변화가 있었군요.", target_slot,
    )
    assert guide_fragment in composed
    assert "반드시 한 가지만 물어야 함" not in composed
    assert composed.count("?") == 1
