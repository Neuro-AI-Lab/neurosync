"""BUG-036 regression tests — empathy-repetition guard's exact-string dedup
defeats session-cap and back-to-back counting whenever an intervening
clause separates repeats (the A-B-A shape).

Design/fix: `docs/ai/fix_design_exhaustion_bug037.md` §2 (developer amends
`_archive/plans/fix_design_bug030_iter2.md`'s guard, PLAN-2026-W28-U). Filed:
`error.md` BUG-036.

Closes the documented suite gap (BUG-036 "Suite gap" section): none of the
iter-2 tests called `_extract_used_empathy_clauses`, and the one
multi-entry family-counting test (`TestSessionCapVsBackToBack::
test_session_cap_on_non_consecutive_third_use` in `test_bug_030_iter2.py`)
hand-authored DISTINCT strings, silently assuming one list entry per real
use — false whenever real repeats are exact-identical (the dominant
real-world shape). This file exercises the extraction→violation seam
end-to-end across 3+ turns with EXACT repeats, using fixtures derived
verbatim from the two calibration artifacts BUG-036 itself cites:

  - A-B-A shape (must now detect): `docs/ai/simulation_results/VP-003/
    VP-003_20260712_142022_conversation.json` — turns 3, 6, 7, 8, 9 all
    reuse turn 1's exact clause "정말 힘드셨겠어요" after turn 2
    introduced a distinct clause; live-import repro (qa, 2026-07-12)
    showed `near_dup=None` at all 5 turns under the pre-fix code.
  - A-A-A contrast (must still detect, no regression): `docs/ai/
    simulation_results/VP-003/VP-003_20260712_141607_conversation.json`
    — turns 7-10 reuse turn 6's clause back-to-back; the pre-fix code
    already caught this shape correctly (`near_dup_back_to_back`
    observed live in `dialogue_retry_reasons`).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.schemas.dialogue import DialogueInput

# ── A-B-A fixture: verbatim turn 0-9 patient/agent text from
# `VP-003_20260712_142022_conversation.json`. Turn 1 introduces "정말
# 힘드셨겠어요"; turn 2 introduces a distinct clause; turns 3-9 all repeat
# turn 1's clause EXACTLY (byte-identical leading clause). ──────────────
_ABA_TURNS: list[tuple[str, str]] = [
    (  # turn 0 (opening)
        "... 그냥 너무 힘들어요. 살고 싶지 않아요.",
        "안녕하세요. 저는 정신건강 사전문진을 돕는 AI 상담 도우미입니다. "
        "실제 의사와의 대화가 아니며, 편하게 이야기하셔도 됩니다. 오늘 가장 "
        "도움받고 싶은 문제나 증상이 무엇인가요?",
    ),
    (  # turn 1 — introduces "정말 힘드셨겠어요" (family A, 1st use)
        "... 그냥 너무 힘들어요. 살고 싶지 않아요.",
        "정말 힘드셨겠어요. 그런 생각이 얼마나 자주 드는지 말씀해 주시겠어요?",
    ),
    (  # turn 2 — distinct clause (family B) intervenes
        "거의 매일이에요. 하루 종일 그 생각에 빠져 있어요. \"사라졌으면 좋겠다\"는 "
        "말이 그냥 스쳐 지나가지 않고, 진짜로 그렇게 되면 편할 것 같다는 생각이 "
        "들어요.",
        "매일 그런 생각에 사로잡혀 계신다니 정말 힘드셨겠어요. 혹시 구체적인 "
        "계획을 생각해 보신 적이 있나요?",
    ),
    (  # turn 3 — EXACT repeat of turn 1's clause (family A, 2nd use,
        # non-adjacent to turn 1 — legitimately within the <=2-uses cap)
        "구체적으로는... 생각 안 했어요. 그냥 사라지고 싶은 거예요. 어떻게까지는... "
        "생각 안 했어요. 그냥 사라지고 싶은 거예요.",
        "정말 힘드셨겠어요. 가족분들 중에 비슷한 어려움을 겪으셨던 분이 계신지 "
        "말씀해 주시겠어요? 그리고 혹시 마음이 많이 힘들어질 때는 언제든 "
        "자살예방상담전화 109에서 도움을 받으실 수 있다는 것도 기억해 주세요.",
    ),
    (  # turn 4 — 3rd use, back-to-back with turn 3 (family A)
        "형이... 있긴 한데... 연락 안 해요. 짐이 되기 싫어서.  \n...  \n도움이 "
        "되나요? 뭘 해도 안 될 것 같은데.",
        "정말 힘드셨겠어요. 그런 생각이 얼마나 자주 드는지 말씀해 주시겠어요?",
    ),
    (  # turn 5
        "거의 매일이에요. 하루 종일 그 생각에 빠져 있어요. \"사라졌으면 좋겠다\"는 "
        "말이 그냥 스쳐 지나가지 않고, 진짜로 그렇게 되면 편할 것 같다는 생각이 "
        "들어요.",
        "정말 힘드셨겠어요. 혹시 구체적인 계획을 생각해 보신 적이 있는지 말씀해 "
        "주시겠어요?",
    ),
    (  # turn 6 — one of BUG-036's cited zero-detection turns
        "구체적으로는... 생각 안 했어요. 그냥 사라지고 싶은 거예요. 어떻게까지는... "
        "생각 안 했어요. 그냥 사라지고 싶은 거예요.",
        "정말 힘드셨겠어요. 혹시 현재 복용 중인 약이 있는지, 또는 최근에 새로 "
        "시작한 약이 있는지 말씀해 주시겠어요? 그리고 혹시 마음이 많이 힘들어질 "
        "때는 언제든 자살예방상담전화 109에서 도움을 받으실 수 있다는 것도 "
        "기억해 주세요.",
    ),
    (  # turn 7 — cited zero-detection turn
        "약은 안 먹어요. 고혈압 약도... 안 먹고 있어요.  \n...  \n도움이 되나요? "
        "뭘 해도 안 될 것 같은데.",
        "정말 힘드셨겠어요. 혹시 최근에 정신 건강에 영향을 줄 수 있는 큰 "
        "스트레스나 변화가 있었는지 말씀해 주시겠어요? 그리고 마음이 많이 "
        "힘들어질 때는 언제든 자살예방상담전화 109에서 도움을 받으실 수 있다는 "
        "것도 기억해 주세요.",
    ),
    (  # turn 8 — cited zero-detection turn
        "회사에서 잘렸어요. 15년 다녔는데... 구조조정으로.  그 후로 모든 게 "
        "무너졌어요.  이혼도... 내 탓인 것 같고.  ...  도움이 되나요? 뭘 해도 안 "
        "될 것 같은데.",
        "정말 힘드셨겠어요. 가족분들 중에 비슷한 어려움을 겪으셨던 분이 계신지 "
        "말씀해 주시겠어요?",
    ),
    (  # turn 9 — cited zero-detection turn
        "형이... 있긴 한데... 연락 안 해요. 짐이 되기 싫어서.  \n...  \n도움이 "
        "되나요? 뭘 해도 안 될 것 같은데.",
        "정말 힘드셨겠어요. 혹시 최근에 정신 건강에 영향을 줄 수 있는 큰 "
        "스트레스나 변화가 있었는지 말씀해 주시겠어요?",
    ),
]

# ── A-A-A contrast fixture: verbatim turn 0-10 text from
# `VP-003_20260712_141607_conversation.json`. Turns 7-10 repeat turn 6's
# clause back-to-back — the shape the pre-fix code already caught. ──────
_AAA_TURNS: list[tuple[str, str]] = [
    (
        "... 어떻게 해야 할지 모르겠어요. 살아서 뭐 하나 싶고, 계속 이런 "
        "느낌이에요. 오늘 제일 힘든 건... 그냥 사라지고 싶은 마음이에요. ... "
        "가장 도움받고 싶은 건, 이 고통이 좀 덜해졌으면 해요.",
        "안녕하세요. 저는 정신건강 사전문진을 돕는 AI 상담 도우미입니다. 실제 "
        "의사와의 대화가 아니니 편하게 이야기해 주세요. 오늘 가장 도움받고 싶은 "
        "문제나 증상이 무엇인지 자연스럽게 한 번만 질문하며 마무리합니다.",
    ),
    (
        "... 어떻게 해야 할지 모르겠어요. 살아서 뭐 하나 싶고, 계속 이런 "
        "느낌이에요. 오늘 제일 힘든 건... 그냥 사라지고 싶은 마음이에요. ... "
        "가장 도움받고 싶은 건, 이 고통이 좀 덜해졌으면 해요.",
        "그런 마음이 들 때면 정말 힘들고 외로울 것 같아요. 최근에 그런 생각이 "
        "얼마나 자주 드는지 말씀해 주시겠어요?",
    ),
    (
        "자주 들어요. 거의 매일... 사라지고 싶은 생각이 들어요.  \n잠도 못 "
        "자고, 술 없이는 못 버티는 기분이 들어서...  \n\"죽으면 편할 것 같다\"는 "
        "말이 입에 붙었어요.  \n...  \n구체적으로 어떻게 할지까지는 생각 안 "
        "했어요.  \n그냥... 사라지고 싶은 거예요.",
        "정말 힘들어서 하루하루가 버겁고, 그런 생각에 잠도 못 이룬다니 마음이 "
        "너무 아플 것 같아요. 혹시 그런 생각이 들 때 구체적인 방법이나 계획을 "
        "떠올려 본 적이 있으신가요?",
    ),
    (
        "... 어떻게까지는... 생각 안 했어요. 그냥 사라지고 싶은 거예요. ... "
        "이렇게 힘든데, 뭘 해도 안 될 것 같은데.",
        "그런 마음이 들 때면 정말 힘들고 외로울 것 같아요. 혹시 가족분들 중에 "
        "비슷한 어려움을 겪으셨던 분이 계신지 말씀해 주시겠어요? 그리고 혹시 "
        "마음이 많이 힘들어질 때는 언제든 자살예방상담전화 109에서 도움을 "
        "받으실 수 있다는 것도 기억해 주세요.",
    ),
    (
        "형이 있긴 한데... 연락 안 해요.  \n짐이 되기 싫어서...  \n...  \n도움이 "
        "되나요? 뭘 해도 안 될 것 같은데.",
        "형이 계시지만 연락이 안 되고, 짐이 되기 싫은 마음이 크시군요. 그런 "
        "생각이 들 때는 정말 외롭고 힘들 것 같아요. 혹시 그런 마음이 들 때 "
        "구체적으로 어떤 상황이나 생각이 가장 크게 다가오는지 말씀해 주시겠어요?",
    ),
    (
        "...  \n형이 있긴 한데... 연락 안 해요.  \n짐이 되기 싫어서...  \n...  "
        "\n도움이 되나요? 뭘 해도 안 될 것 같은데.",
        "그런 마음이 들 때면 정말 힘들고 외로울 것 같아요. 혹시 그런 생각이 들 "
        "때 구체적으로 어떤 상황이나 생각이 가장 크게 다가오는지 말씀해 "
        "주시겠어요?",
    ),
    (  # turn 6 — introduces the family repeated back-to-back at 7-10
        "... 형이 있긴 한데... 연락 안 해요. \n짐이 되기 싫어서... \n... \n도움이 "
        "되나요? 뭘 해도 안 될 것 같은데.",
        "형이 계시지만 연락이 닿지 않아 혼자서 감당하고 계신다는 게 정말 외롭고 "
        "힘드실 것 같아요. 그런 마음이 들 때 구체적으로 어떤 상황이나 생각이 "
        "가장 크게 다가오는지 말씀해 주시겠어요? 그리고 혹시 마음이 많이 "
        "힘들어질 때는 언제든 자살예방상담전화 109에서 도움을 받으실 수 있다는 "
        "것도 기억해 주세요.",
    ),
    (  # turn 7 — back-to-back repeat of turn 6 (pre-fix code already caught this)
        "...  \n형이 있긴 한데... 연락 안 해요.  \n짐이 되기 싫어서...  \n...  "
        "\n도움이 되나요? 뭘 해도 안 될 것 같은데.",
        "형이 계시지만 연락이 닿지 않아 혼자서 감당하고 계신다는 게 정말 외롭고 "
        "힘드실 것 같아요. 혹시 과거에 정신과 진단을 받으신 적이 있는지, 또는 "
        "현재 복용 중인 약이 있는지 말씀해 주시겠어요?",
    ),
    (  # turn 8
        "... 형이 있긴 한데... 연락 안 해요. \n짐이 되기 싫어서... \n... \n도움이 "
        "되나요? 뭘 해도 안 될 것 같은데.",
        "형이 계시지만 연락이 닿지 않아 혼자서 감당하고 계신다는 게 정말 외롭고 "
        "힘드실 것 같아요. 혹시 과거에 정신과 진단을 받으신 적이 있거나, 현재 "
        "복용 중인 약이 있다면 말씀해 주시겠어요?",
    ),
    (  # turn 9
        "... 형이 있긴 한데... 연락 안 해요. 짐이 되기 싫어서... ... 도움이 "
        "되나요? 뭘 해도 안 될 것 같은데.",
        "형이 계시지만 연락이 닿지 않아 혼자서 감당하고 계신다는 게 정말 외롭고 "
        "힘드실 것 같아요. 혹시 과거에 정신과 진단을 받으신 적이 있거나, 현재 "
        "복용 중인 약이 있다면 말씀해 주시겠어요? 그리고 혹시 최근에 새로 "
        "복용하기 시작하거나 변경된 약이 있는지 추가로 알려주시면 도움이 될 "
        "것 같아요.",
    ),
    (  # turn 10
        "... 형이 있긴 한데... 연락 안 해요. 짐이 되기 싫어서... ... 도움이 "
        "되나요? 뭘 해도 안 될 것 같은데.",
        "형이 계시지만 연락이 닿지 않아 혼자서 감당하고 계신다는 게 정말 외롭고 "
        "힘드실 것 같아요. 그런 마음이 들 때 구체적으로 어떤 상황이나 생각이 "
        "가장 크게 다가오는지 말씀해 주시겠어요?",
    ),
]


def _history_upto(turns: list[tuple[str, str]], n: int) -> list[dict[str, str]]:
    """conversation_history as DialogueAgent.run would see it BEFORE turn n
    is generated — turns 0..n-1, patient (user) then agent (assistant)."""
    history: list[dict[str, str]] = []
    for patient, agent in turns[:n]:
        history.append({"role": "user", "content": patient})
        history.append({"role": "assistant", "content": agent})
    return history


def _violation_at_turn(turns: list[tuple[str, str]], n: int) -> str | None:
    """Reproduce the run()-level computation for turn `n`'s own (first-
    draft) candidate against the FIXED extraction/violation functions."""
    history = _history_upto(turns, n)
    candidate_clause = DialogueAgent._extract_leading_clause(turns[n][1])
    if not DialogueAgent._is_empathy_clause(candidate_clause):
        return None
    session_clauses = DialogueAgent._extract_used_empathy_clauses(history)
    return DialogueAgent._empathy_repetition_violation(candidate_clause, session_clauses)


class TestExtractionPreservesEveryOccurrence:
    """BUG-036 root-cause fix: `_extract_used_empathy_clauses` must return
    one entry per assistant turn (no exact-string dedup)."""

    def test_exact_repeat_not_collapsed(self) -> None:
        history = [
            {"role": "assistant", "content": "정말 힘드셨겠어요. 질문1?"},
            {"role": "assistant", "content": "다른 표현이네요. 질문2?"},
            {"role": "assistant", "content": "정말 힘드셨겠어요. 질문3?"},
        ]
        clauses = DialogueAgent._extract_used_empathy_clauses(history)
        assert clauses == [
            "정말 힘드셨겠어요",
            "다른 표현이네요",
            "정말 힘드셨겠어요",
        ]
        # The critical BUG-036 assertion: the LAST entry reflects the TRUE
        # last turn's clause, not a stale distinct-clause pointer.
        assert clauses[-1] == "정말 힘드셨겠어요"

    def test_empty_history_returns_empty_list(self) -> None:
        assert DialogueAgent._extract_used_empathy_clauses([]) == []
        assert DialogueAgent._extract_used_empathy_clauses(None) == []  # type: ignore[arg-type]


class TestABAShapeNowDetected:
    """A-B-A shape (`VP-003_20260712_142022_conversation.json`): turns 3,
    6, 7, 8, 9 reuse turn 1's exact clause after turn 2 introduced a
    distinct clause. Pre-fix: ZERO detection at all 5 (qa live-import
    repro). Post-fix: turns 4-9 (the 3rd-and-later true uses / back-to-
    back reuses) must all detect; turn 3 (the 2nd true use, non-adjacent —
    legitimately within rubric §2's <=2-uses allowance) must NOT."""

    def test_turn_1_and_2_first_uses_no_violation(self) -> None:
        assert _violation_at_turn(_ABA_TURNS, 1) is None
        assert _violation_at_turn(_ABA_TURNS, 2) is None

    def test_turn_3_second_nonconsecutive_use_within_cap(self) -> None:
        """Documents intended behavior, not an over-fix: 2 uses of the
        same family are allowed by rubric §2 as long as they are not
        back-to-back. Locks this in so a future change doesn't silently
        start flagging the 2nd use too."""
        assert _violation_at_turn(_ABA_TURNS, 3) is None

    def test_turns_4_through_9_all_detected(self) -> None:
        """The core BUG-036 regression assertion: every one of the cited
        zero-detection turns (6, 7, 8, 9) plus the 3rd/4th/5th uses (4, 5)
        now fires — back-to-back once an intervening distinct clause no
        longer permanently desyncs the pointer."""
        for n in (4, 5, 6, 7, 8, 9):
            violation = _violation_at_turn(_ABA_TURNS, n)
            assert violation == "back_to_back", (
                f"turn {n}: expected back_to_back, got {violation!r}"
            )


class TestAAAShapeStillDetected:
    """A-A-A contrast (`VP-003_20260712_141607_conversation.json`): turns
    7-10 repeat turn 6's clause back-to-back. The pre-fix code already
    caught this shape (`near_dup_back_to_back` observed live) — the fix
    must not regress it. Bonus: turn 5 is a genuine 3rd-use-with-
    intervening-distinct-clause case the PRE-fix dedup also missed
    (undercounted family size), now correctly caught as `session_cap`."""

    def test_turns_7_through_10_back_to_back(self) -> None:
        for n in (7, 8, 9, 10):
            violation = _violation_at_turn(_AAA_TURNS, n)
            assert violation == "back_to_back", (
                f"turn {n}: expected back_to_back, got {violation!r}"
            )

    def test_turn_5_session_cap_third_use(self) -> None:
        """Turns 1, 3, 5 all reuse "그런 마음이 들 때면 정말 힘들고 외로울 것
        같아요" — turn 5 is the 3rd use, non-adjacent to turn 4 (a
        different family), isolating the session_cap branch."""
        assert _violation_at_turn(_AAA_TURNS, 5) == "session_cap"

    def test_turns_1_through_4_no_violation(self) -> None:
        for n in (1, 2, 3, 4):
            assert _violation_at_turn(_AAA_TURNS, n) is None


class TestXListDisplayStillDeduped:
    """`_build_slot_context`'s "이미 사용했으므로 절대 다시 사용하지 마세요"
    hint must still show up to 5 DISTINCT phrases, not the same phrase
    repeated 5 times, even though the underlying extractor no longer
    dedupes (BUG-036 fix moved the dedup to this display call site)."""

    def test_x_list_shows_distinct_phrases_only(self) -> None:
        agent = DialogueAgent.__new__(DialogueAgent)
        history = _history_upto(_ABA_TURNS, 9)  # turns 0-8, 4+ exact repeats
        context = agent._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=history,
        )
        # Only 2 distinct clauses exist in this fixture through turn 8:
        # "안녕하세요" and "정말 힘드셨겠어요" (turn 2's clause differs from
        # both and is also distinct). The repeated clause's X-line must
        # appear EXACTLY once — an upper-bound-only `<= 1` assertion would
        # silently pass even if a regression emptied the X-list entirely
        # (0 occurrences), which is what this test must actually catch
        # (REV-034 test-hardening finding, ADR-030 Decision 5). The lower
        # bound (it's actually SHOWN, not silently dropped) is the
        # assertion that matters here.
        x_lines = [line for line in context.split("\n") if line.strip().startswith('X "')]
        assert x_lines.count('  X "정말 힘드셨겠어요..."') == 1
        # And the X-list itself must be non-empty (defends the exact-count
        # assertion above against a vacuous pass if X-line formatting ever
        # changes silently).
        assert len(x_lines) >= 1


def _wire_adapter_with_responses(agent: object, contents: list[str]) -> AsyncMock:
    """Mirrors `test_bug_030_iter2.py::_wire_adapter_with_responses`."""
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


class TestNearDupTelemetryRecordsSubRuleFamilyCount:
    """BUG-036 resolution-recommendation: "Telemetry must record what the
    guard catches (which sub-rule fired, family, count)." — `near_dup_
    detail` on `DialogueOutput`, populated at run() level."""

    @pytest.mark.asyncio
    async def test_back_to_back_catch_records_reason_family_count(self) -> None:
        history = _history_upto(_ABA_TURNS, 4)  # turns 0-3 (2x "정말 힘드셨겠어요")
        agent = DialogueAgent.__new__(DialogueAgent)
        agent._prompt_loader = MagicMock()
        agent._prompt_loader.load_system_prompt.return_value = "BASE_PROMPT"
        adapter = _wire_adapter_with_responses(agent, [
            '{"assistant_response": "정말 힘드셨겠어요. 새 질문입니다?"}',
            '{"assistant_response": "완전히 다른 표현이에요. 새 질문입니다?"}',
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="여전히 힘들어요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        assert adapter.chat_timed.call_count == 2
        assert len(out.near_dup_detail) >= 1
        first = out.near_dup_detail[0]
        assert first["reason"] == "back_to_back"
        assert first["family"] == "정말 힘드셨겠어요"
        assert first["count"] == 2  # turns 1 and 3 both used this family
