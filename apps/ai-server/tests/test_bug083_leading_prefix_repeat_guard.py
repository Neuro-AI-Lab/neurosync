"""Regression test — 4연속 verbatim 공감 도입부 반복 (2026-07-25, EXP-032 live
re-verification, session3_denial). `_empathy_repetition_violation` only runs
when `_is_empathy_clause(candidate_clause)` is True, and `exact_repeat`
compares the FULL response string — so a leading clause that (a) does not
literally contain one of `_EMPATHY_MARKERS`' fixed substrings and (b) is
followed by a DIFFERENT trailing question each turn was invisible to every
existing guard. Live repro: "잠 못 드는 상황이 계속되면 마음이 지칠 수
있어요" shipped byte-identically as the leading clause on 4 consecutive
turns (indices 7/11/15/19 of `experiments/EXP-032_f1_reverify/final/
session3_denial.jsonl`) — "지칠" does not match `_EMPATHY_MARKERS`'
"지치셨"/"지치시".

Fix: (1) prompt-level state-visibility strengthened (`_build_slot_context`
now explicitly flags the immediately-prior turn's own leading clause + one
diversification-principle sentence) as the PRIMARY defense; (2) a new
`_leading_prefix_repeat_violation` hard guard, independent of `_is_empathy_
clause`, as the last-resort safety net — fires ONLY once the candidate
would be the 3rd byte-identical leading-clause occurrence in a row.

No live LLM calls — deterministic stub adapter, same pattern as
`test_dialogue_self_referential_relief.py`/`test_bug082_...py`.
"""

from __future__ import annotations

import asyncio
import json

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.prompts.loader import PromptLoader
from src.schemas.dialogue import DialogueInput

_REPEATED_PREFIX = "잠 못 드는 상황이 계속되면 마음이 지칠 수 있어요."


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


class _SamePrefixAdapter(LLMAdapter):
    """Always ships `_REPEATED_PREFIX` as the leading clause. The trailing
    question is keyed off `turn_index` (set by the test BEFORE each
    external `run()` call, held fixed across that turn's internal
    retries) so the FULL response never repeats byte-identically ACROSS
    turns (isolating this guard from `exact_repeat`), while staying
    deterministic across a turn's own retry attempts (needed to
    exhaust the retry budget and exercise the degrade branch). Each
    question is on-topic per `_SLOT_TOPIC_KEYWORDS` (never catch-all per
    `_is_catchall_question`), so `target_mismatch`/`catchall_violation`
    never preempts this guard."""

    _QUESTIONS = (
        "기존에 진단받은 신체질환이 있으신가요?",
        "가족분들 중에 비슷한 어려움을 겪으셨던 분이 계신가요?",
        "최근 음주나 수면제 사용은 없으셨나요?",
    )

    def __init__(self) -> None:
        self.turn_index = 0

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        question = self._QUESTIONS[self.turn_index % len(self._QUESTIONS)]
        return ChatResponse(
            content=json.dumps(
                {"assistant_response": f"{_REPEATED_PREFIX} {question}"},
                ensure_ascii=False,
            ),
            model="stub-model",
        )


def _turn_input(conversation_history: list[dict[str, str]]) -> DialogueInput:
    return DialogueInput(
        session_id="test-session-leading-prefix-repeat",
        user_message="없어요.",
        conversation_history=conversation_history,
        filled_slots={"chief_complaint": "불면"},
        safety_result={"risk_level": "low"},
        session_state={},
        slot_updates_this_turn=None,
    )


def test_leading_prefix_repeat_violation_unit() -> None:
    """Unit: fires only on the 3rd consecutive byte-identical occurrence,
    independent of `_is_empathy_clause` (this exact clause is NOT
    recognized as empathy per `_EMPATHY_MARKERS`)."""
    assert DialogueAgent._is_empathy_clause(_REPEATED_PREFIX.rstrip(".")) is False  # noqa: SLF001

    two_prior = [_REPEATED_PREFIX, "다른 표현이에요"]
    assert DialogueAgent._leading_prefix_repeat_violation(  # noqa: SLF001
        _REPEATED_PREFIX, two_prior
    ) is False  # last prior differs -> not 2 consecutive

    three_prior = [_REPEATED_PREFIX, _REPEATED_PREFIX]
    assert DialogueAgent._leading_prefix_repeat_violation(  # noqa: SLF001
        _REPEATED_PREFIX, three_prior
    ) is True  # candidate would be the 3rd in a row


def test_run_degrades_on_third_consecutive_verbatim_prefix() -> None:
    """End-to-end guard loop across 3 sequential turns: turns 1-2 ship the
    repeated prefix unmodified (guard has not fired yet — matches the
    "last resort, not first offense" design), turn 3 (the 3rd consecutive
    occurrence) must be caught and degraded — the prefix must not survive
    unmodified into a 3rd turn."""
    adapter = _SamePrefixAdapter()
    agent = DialogueAgent(
        model_router=_StubRouter(adapter),
        prompt_loader=PromptLoader("prompts"),
    )
    history: list[dict[str, str]] = []
    responses: list[str] = []
    for turn in range(3):
        adapter.turn_index = turn
        inp = _turn_input(list(history))
        output = asyncio.run(agent.run(inp))
        responses.append(output.assistant_response)
        history.append({"role": "assistant", "content": output.assistant_response})
        history.append({"role": "user", "content": "없어요."})

    assert responses[0].startswith(_REPEATED_PREFIX)
    assert responses[1].startswith(_REPEATED_PREFIX)
    # 3rd consecutive occurrence — the last-resort guard must catch it.
    assert not responses[2].startswith(_REPEATED_PREFIX), (
        "leading_prefix_repeat guard did not fire on the 3rd consecutive "
        f"verbatim occurrence: {responses[2]!r}"
    )
    assert "?" in responses[2]  # question must survive the degrade


def test_build_slot_context_flags_the_immediately_prior_lead_in() -> None:
    """Prompt-level primary defense: `_build_slot_context` must surface
    the immediately-prior turn's own leading clause distinctly (not just
    buried in the up-to-5-item X-list) plus a one-sentence diversification
    principle."""
    agent = DialogueAgent(
        model_router=_StubRouter(_SamePrefixAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    conversation_history = [
        {"role": "assistant", "content": f"{_REPEATED_PREFIX} 질문 1?"},
        {"role": "user", "content": "없어요."},
    ]
    context = agent._build_slot_context(  # noqa: SLF001
        filled_slots={"chief_complaint": "불면"},
        session_state={},
        conversation_history=conversation_history,
    )
    assert "직전 턴 도입부" in context
    assert _REPEATED_PREFIX in context
    assert "매 턴 도입부" in context
