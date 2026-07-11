"""BUG-025 (PLAN-2026-W28-Q W2, EXP-014 SM-06 regression) — regression tests
for the diagnosed cause + fix.

Diagnosis (result.md EXP-014, discussion.md PLAN-2026-W28-Q status): SM-06
stopped at turn 7 (of 12) because the AI asked a byte-identical
`substance_use_history` question at turns 5/6/7, tripping the pipeline's
pre-existing "stop after 2 consecutive repeats" guard (`f1.py:1655-1665`,
unmodified this wave — never loosened here) before the mandatory SI screen.
Bisection (worktree `247922e`, dialogue v2, EXP-014) reproduced a clean
12-turn pass; the round-robin/target-selection code in `dialogue.py`
(`compute_target_slot`/`_build_slot_context`) is provably byte-identical
between v2 and v3 (diff `247922e..d3e524d`) and, cross-checked against the
failing run's own artifact (`experiments/EXP-014/runs/sm_regression/SM-06/`),
correctly computed a FRESH target (`past_psychiatric_history` at turn 6,
`medical_history` at turn 7) each time — the LLM ignored that instruction
and repeated its previous turn's question verbatim regardless. The DialogueAgent
already ships a self-correction retry for exactly this case
(`is_repeated` -> "retrying with stronger hint", `run.log` shows it firing
at both turn 6 and turn 7) but the hint's "미수집 슬롯" list was computed
from `_ESSENTIAL_SLOTS` only — a set that both omits every non-essential
questionable slot (past_psychiatric_history, medical_history,
personal_social_history, family_history, substance_use_history: exactly
where the round-robin target usually lands) and can include non-questionable
essential slots (mental_status_exam, clinical_assessment) that must never be
asked about directly. The retry's own hint therefore never told the model
the one thing it needed to hear. This file locks that fix in place: the
retry hint must always match the SAME canonical `missing_questionable_slots`
list the slot-context directive itself used to pick the turn's target.

The v3 prompt content fix (`docs/ai/prompts/dialogue/v3.system.md`,
sha256 `d8870e5dda81dffde9099a2e606e9656b7aeb8f897dbdd41f25705efbdc84325`,
supersedes pin `2440f29b63315d3613b8726b982d612479d97b7be8e4a796c0a5f80e947e1e0b`)
is covered structurally in `test_prompt_v3.py::TestDialogueV3File` (all
pre-existing assertions still pass unmodified) — this file adds the one new
assertion specific to the diagnosis: the turn-0/revisit-only rule content is
no longer unconditionally duplicated as a full imperative block on every
non-opening, non-revisit turn.

The full proof that the fix actually clears SM-06 is the live SM-01..08b
re-run (ADR-025) — out of this agent's charter; these are mock-LLM-level
tests of the diagnosed mechanism only.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.schemas.dialogue import DialogueInput

_PROMPTS_DIR = Path(__file__).resolve().parents[4] / "docs" / "ai" / "prompts"
_DIALOGUE_V3 = (_PROMPTS_DIR / "dialogue" / "v3.system.md").read_text(encoding="utf-8")

# The literal turn-6 substance_use_history question from EXP-014's failing
# SM-06 transcript (`experiments/EXP-014/runs/sm_regression/SM-06/artifacts/
# SM-06_20260711_121554_report.md`) — long enough (>=80 chars) to hit the
# `is_repeated` length-gated branch, exactly as it did live.
_SM06_SUBSTANCE_QUESTION = (
    "그런 상황이라면 정말 지치셨을 것 같아요. 혹시 최근에 술이나 수면제, "
    "진정제, 카페인 같은 것을 자주 사용하시거나, 복용하시는 약이 있으신가요?"
)
assert len(_SM06_SUBSTANCE_QUESTION) >= 80


def _wire_adapter_with_responses(agent: object, contents: list[str]) -> AsyncMock:
    """Wire a fake router/adapter that returns *contents* in call order."""
    router = MagicMock()
    agent._router = router  # type: ignore[attr-defined]

    def _resp(content: str) -> MagicMock:
        resp = MagicMock()
        resp.content = content
        resp.model = "test-model"
        resp.latency_ms = 1.0
        return resp

    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(side_effect=[_resp(c) for c in contents])
    router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    router.get_adapter.return_value = adapter
    router.record_success = MagicMock()
    return adapter


class TestRepeatRetryHintMatchesRoundRobinTarget:
    """BUG-025 fix: the is_repeated retry hint must use the SAME canonical
    missing-slot list `_build_slot_context`'s round-robin target uses — not
    the narrower/wrong `_ESSENTIAL_SLOTS` filter."""

    @pytest.mark.asyncio
    async def test_hint_names_the_non_essential_target_slot(self) -> None:
        """Reproduces the exact EXP-014 SM-06 turn-6 filled_slots state
        (chief_complaint + history_of_present_illness + substance_use_history
        filled; risk_assessment/past_psychiatric_history/medical_history/
        personal_social_history/family_history still missing). The round-
        robin's actual computed target at that state was
        `past_psychiatric_history` (verified against the run's own
        `targeted_slot` field) — a NON-essential slot the old
        `_ESSENTIAL_SLOTS`-only hint could never have named.
        """
        agent = DialogueAgent.__new__(DialogueAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "BASE_PROMPT"
        adapter = _wire_adapter_with_responses(
            agent,
            [
                f'{{"assistant_response": "{_SM06_SUBSTANCE_QUESTION}"}}',
                '{"assistant_response": "다른 질문입니다."}',
            ],
        )

        filled_slots = {
            "chief_complaint": "이직하면서 스트레스가 커져서 잠들기가 어려움",
            "history_of_present_illness": "두 달 전부터 새벽 2~3시까지 잠들기 어려움",
            "substance_use_history": "술 거의 안 마시고 커피 하루 한 잔",
        }
        conversation_history = [
            {"role": "assistant", "content": "안녕하세요, 오늘은 어떤 고민이 있으신가요?"},
            {"role": "user", "content": "잠들기가 어려워요."},
            {"role": "assistant", "content": _SM06_SUBSTANCE_QUESTION},
            {"role": "user", "content": "술은 거의 안 마시고 커피는 하루 한 잔 마셔요."},
        ]

        out = await agent.run(DialogueInput(
            session_id="t-bug-025",
            user_message="술은 거의 안 마시고 커피는 하루 한 잔 마셔요.",
            conversation_history=conversation_history,
            filled_slots=filled_slots,
            safety_result=None,
            session_state=None,
        ))

        # The retry must have fired (is_repeated caught the duplicate).
        assert adapter.chat_timed.call_count == 2

        retry_messages = adapter.chat_timed.call_args_list[1].args[0]
        retry_user_content = retry_messages[-1].content

        expected_missing = DialogueAgent.missing_questionable_slots(filled_slots)
        assert "past_psychiatric_history" in expected_missing  # sanity on the fixture
        for slot in expected_missing:
            assert slot in retry_user_content, (
                f"retry hint missing canonical target {slot!r}: {retry_user_content!r}"
            )
        # The final output is whatever the (mocked) retry returned — this
        # test only locks in the HINT content, not live-model compliance.
        assert out.assistant_response == "다른 질문입니다."

    @pytest.mark.asyncio
    async def test_hint_never_names_non_questionable_slots(self) -> None:
        """Old bug's other half: `_ESSENTIAL_SLOTS` includes
        `mental_status_exam`/`clinical_assessment`, both `_NO_QUESTION_SLOTS`
        the agent must never be told to ask about directly. With nothing
        filled, the fixed hint must still exclude them."""
        agent = DialogueAgent.__new__(DialogueAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "BASE_PROMPT"
        adapter = _wire_adapter_with_responses(
            agent,
            [
                f'{{"assistant_response": "{_SM06_SUBSTANCE_QUESTION}"}}',
                '{"assistant_response": "다른 질문입니다."}',
            ],
        )

        conversation_history = [
            {"role": "assistant", "content": _SM06_SUBSTANCE_QUESTION},
        ]

        await agent.run(DialogueInput(
            session_id="t-bug-025-empty",
            user_message="환자 발화",
            conversation_history=conversation_history,
            filled_slots={},
            safety_result=None,
            session_state=None,
        ))

        retry_messages = adapter.chat_timed.call_args_list[1].args[0]
        retry_user_content = retry_messages[-1].content
        assert "mental_status_exam" not in retry_user_content
        assert "clinical_assessment" not in retry_user_content


class TestV3PromptNoLongerAlwaysInjectsTurnZeroRules:
    """BUG-025 diagnosis: the v3 prompt's turn-0/revisit-only content used
    to be TWO full imperative rule sections (9 bullet items total) present
    unconditionally in the static file loaded on every single dialogue call
    this session makes — including turns where it is fully irrelevant. The
    equivalent full guidance is already delivered dynamically and
    conditionally by `_build_opening_context()`/`_build_slot_context()`
    (`test_dialogue_v3_opening.py`). This asserts the static file no longer
    duplicates that full block unconditionally."""

    def test_old_always_on_numbered_turn0_rules_removed(self) -> None:
        # The old section spelled out 4 numbered turn-0 rules verbatim.
        assert "1. 아직 슬롯 문진·진단·위험 평가" not in _DIALOGUE_V3
        assert "4. 인사말은 매번 자연스럽게 다르게 생성한다" not in _DIALOGUE_V3

    def test_condensed_section_states_conditional_scope(self) -> None:
        assert "적용된다" in _DIALOGUE_V3
        assert "무관" in _DIALOGUE_V3

    def test_required_phrases_still_present_for_existing_static_tests(self) -> None:
        """Guards `test_prompt_v3.py::TestDialogueV3File` invariants —
        redundant here on purpose, this file must never regress independent
        of that one."""
        assert "세션 시작 인사" in _DIALOGUE_V3
        assert "슬롯 문진" in _DIALOGUE_V3
        assert "연속성" in _DIALOGUE_V3
