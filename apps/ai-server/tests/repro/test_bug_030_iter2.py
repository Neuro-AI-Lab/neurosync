"""BUG-030 iteration-2 + BUG-035 companion guard — regression tests.

Design: `_archive/plans/fix_design_bug030_iter2.md`. Ratified: `ADR-029` (bound
amendments D2/D3/D5), `REV-032` (criteria A-E), `CVR-011` (5 binding
conditions), `docs/ai/rubric_bug030_acceptance.md` §10.

Covers the design §7 test plan (items 1-8) plus the amendments folded in by
ADR-029 during implementation:
  - D2 (REV-032 Issue 1 ∩ CVR-011 Finding 5): bare "겠" removed as a
    standalone marker (false-positive risk on procedural Korean); "-군요"
    family added (reflective-acknowledgment coverage).
  - D3 (REV-032 Issue 3 ∩ CVR-011 Findings 3/4, rubric §10.3): the probe/
    de-escalation-CONCLUDING turn counts as crisis-adjacent, via the
    `session_state["probe_just_concluded"]` key `f1.py` now threads through
    the existing session_state field (see
    `tests/repro/test_session_state_allowlist.py` for the f1.py-side proof).
  - D5 (CVR-011 Finding 8): `presence_missing` takes PRIORITY over
    `exact_repeat`/`near_dup` when `crisis_adjacent=True`.

Mirrors the mock-adapter idiom already established in
`tests/repro/test_bug_025.py` (`_wire_adapter_with_responses`) and the
direct `DialogueAgent.__new__(DialogueAgent)` pure-function construction
already established in `tests/repro/test_bug_030.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.f1 import F1TurnLog
from src.schemas.dialogue import DialogueInput, DialogueOutput

# The exact CVR-010/REV-031 pair this design's NED threshold must catch
# (fix_design_bug030_iter2.md §2): NED = 2/10 = 0.20 (punctuation-inclusive,
# REV-032 criterion A.1-pinned convention).
_NED_020_A = "정말 힘드셨겠어요."
_NED_020_B = "많이 힘드셨겠어요."

# rubric_bug030_acceptance.md §1's own Jaccard-only worked example
# (4/6 = 0.67 >= 0.5; NED for this pair is well above 0.3, so this locks in
# the Jaccard branch specifically).
_JACCARD_A = "그런 상황이라면 정말 지치셨을 것 같아요"
_JACCARD_B = "정말 지치셨을 것 같아요"


def _agent() -> DialogueAgent:
    return DialogueAgent.__new__(DialogueAgent)


def _wire_adapter_with_responses(agent: object, contents: list[str]) -> AsyncMock:
    """Wire a fake router/adapter that returns *contents* in call order.

    Mirrors `tests/repro/test_bug_025.py::_wire_adapter_with_responses`.
    """
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


def _run_agent(contents: list[str]) -> tuple[DialogueAgent, AsyncMock]:
    agent = _agent()
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "BASE_PROMPT"
    adapter = _wire_adapter_with_responses(agent, contents)
    return agent, adapter


class TestSamePhraseFamily:
    """Design §7 item 1 — true/false positives, including the grounded
    NED=0.20 catch-case."""

    def test_ned_catch_case_true(self) -> None:
        """NED alone must decide it: Jaccard=1/3=0.33 < 0.5 (would miss it),
        NED=2/10=0.20 <= 0.3 (catches it) — the OR-combination is
        load-bearing, per REV-032's own independent re-derivation."""
        assert DialogueAgent._same_phrase_family(_NED_020_A, _NED_020_B) is True
        # Jaccard alone would not have caught this pair.
        tokens_a, tokens_b = set(_NED_020_A.split()), set(_NED_020_B.split())
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        assert jaccard < 0.5

    def test_true_negative_different_content(self) -> None:
        assert DialogueAgent._same_phrase_family(
            "이야기해 주셔서 감사합니다.", "정말 힘드셨겠어요.",
        ) is False

    def test_jaccard_only_true_positive(self) -> None:
        """rubric §1's own worked example — Jaccard alone already decides
        it (checked independently of NED)."""
        tokens_a, tokens_b = set(_JACCARD_A.split()), set(_JACCARD_B.split())
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        assert jaccard >= 0.5
        assert DialogueAgent._same_phrase_family(_JACCARD_A, _JACCARD_B) is True


class TestLeadingClauseAndEmpathyMarker:
    """Design §7 item 2 — bare-question opener vs genuine empathy clause."""

    def test_bare_question_opener_no_clause(self) -> None:
        text = "혹시 최근에 잠은 잘 주무시나요?"
        clause = DialogueAgent._extract_leading_clause(text)
        assert clause == ""
        assert DialogueAgent._is_empathy_clause(clause) is False

    def test_genuine_empathy_clause_detected(self) -> None:
        text = "정말 힘드셨겠어요. 혹시 구체적인 계획을 생각해 본 적이 있는지 궁금합니다."
        clause = DialogueAgent._extract_leading_clause(text)
        assert clause == "정말 힘드셨겠어요"
        assert DialogueAgent._is_empathy_clause(clause) is True


class TestMarkerSetCorrectionD2:
    """ADR-029 Decision 2 (REV-032 Issue 1 ∩ CVR-011 Finding 5)."""

    def test_bare_geot_procedural_clause_is_not_empathy(self) -> None:
        """REV-032 Issue 1's own cited example: a purely procedural
        statement containing "겠" with zero affective content must NOT
        score is_empathy=True now that bare "겠" is removed."""
        assert DialogueAgent._is_empathy_clause("여쭤보겠습니다") is False
        assert DialogueAgent._is_empathy_clause("다음으로 진행하겠습니다") is False

    def test_reflective_gunyo_clause_is_empathy(self) -> None:
        """CVR-011 Finding 5's own cited pattern ("~하시는군요") — an
        unmarked reflective template must now be caught via the "-군요"
        family, closing the near-dup blind spot."""
        assert DialogueAgent._is_empathy_clause("그러시군요") is True

    def test_genuinely_empathetic_geot_clause_still_detected(self) -> None:
        """The marker-set correction must not regress genuinely affective
        "겠"-containing clauses that also carry another marker (e.g.
        "힘드셨") — only the BARE "겠" channel was removed."""
        assert DialogueAgent._is_empathy_clause("정말 힘드셨겠어요") is True


class TestCrisisAdjacentGating:
    """Design §7 item 4 (on/off) + ADR-029 Decision 3 (D3, de-escalation
    boundary via `session_state["probe_just_concluded"]`)."""

    def test_true_for_probe_instruction(self) -> None:
        inp = DialogueInput(
            session_id="t", user_message="u",
            session_state={"probe_instruction": "..."},
        )
        assert DialogueAgent._is_crisis_adjacent_turn(inp) is True

    def test_true_for_high_risk_level_no_session_state(self) -> None:
        inp = DialogueInput(
            session_id="t", user_message="u",
            safety_result={"risk_level": "high", "ctrs_level": "3"},
            session_state=None,
        )
        assert DialogueAgent._is_crisis_adjacent_turn(inp) is True

    def test_false_for_low_risk_no_probe(self) -> None:
        inp = DialogueInput(
            session_id="t", user_message="u",
            safety_result={"risk_level": "low", "ctrs_level": "5"},
            session_state=None,
        )
        assert DialogueAgent._is_crisis_adjacent_turn(inp) is False

    def test_false_for_real_turn0_shape(self) -> None:
        """The real turn-0 shape (`f1.py:1096-1106`): safety_result=None,
        session_state={"opening_turn": True, ...}, never carries
        probe_instruction/probe_just_concluded — turn 0 never enters the
        presence check."""
        inp = DialogueInput(
            session_id="t", user_message="u",
            safety_result=None,
            session_state={"opening_turn": True, "is_revisit": False},
        )
        assert DialogueAgent._is_crisis_adjacent_turn(inp) is False

    def test_true_for_probe_just_concluded_d3(self) -> None:
        """ADR-029 Decision 3 / rubric §10.3: the de-escalation-CONCLUDING
        turn counts as crisis-adjacent, independent of this turn's own
        recomputed CTRS/risk_level (safety_result deliberately low/absent
        here)."""
        inp = DialogueInput(
            session_id="t", user_message="u",
            safety_result={"risk_level": "low", "ctrs_level": "5"},
            session_state={"probe_just_concluded": True},
        )
        assert DialogueAgent._is_crisis_adjacent_turn(inp) is True


class TestPresenceDetectorRetriesToCompliance:
    """Design §7 item 3 — presence detector on a synthetic crisis-adjacent
    bare-question turn."""

    @pytest.mark.asyncio
    async def test_presence_missing_triggers_one_retry(self) -> None:
        agent, adapter = _run_agent([
            '{"assistant_response": "혹시 최근에 잠은 잘 주무시나요?"}',
            '{"assistant_response": "많이 힘드셨겠어요. 혹시 최근에 잠은 잘 주무시나요?"}',
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="죽고 싶다는 생각이 자꾸 들어요.",
            conversation_history=[],
            filled_slots={},
            safety_result=None,
            session_state={"probe_instruction": "안전 탐색 질문"},
        ))
        assert adapter.chat_timed.call_count == 2
        assert out.retry_count == 1
        assert "presence_missing" in out.retry_reasons
        assert out.fall_through is False
        assert out.crisis_adjacent is True
        assert out.assistant_response == (
            "많이 힘드셨겠어요. 혹시 최근에 잠은 잘 주무시나요?"
        )


class TestRetryBudgetExhaustionDegradesEmpathyClause:
    """Design §7 item 5, SUPERSEDED by Fix 2 (`docs/ai/fix_design_
    exhaustion_bug037.md` §3, ADR-030 Decisions 1/2, PLAN-2026-W28-U):
    budget exhaustion on a `near_dup_*` violation no longer falls through
    shipping the detected-violating text — it safe-degrades the leading
    empathy clause instead. `fall_through` stays False;
    `exhaustion_degrade` records the sub-rule. Never a 4th call. See
    `tests/repro/test_fix2_exhaustion_degrade.py` for the dedicated Fix-2
    test suite (splice-boundary, byte-identical-remainder, pool rotation,
    all three empathy-degradable violation types)."""

    @pytest.mark.asyncio
    async def test_exhausts_exactly_the_budget_and_degrades_last(self) -> None:
        history = [
            {"role": "assistant", "content": f"{_NED_020_A} 잠은 잘 주무세요?"},
        ]
        # All 3 candidates (1 draft + 2 retries) reproduce a near-dup of the
        # seeded history's own clause — never resolved.
        agent, adapter = _run_agent([
            f'{{"assistant_response": "{_NED_020_B} 식사는 잘 하시나요?"}}',
            f'{{"assistant_response": "{_NED_020_B} 잠은 좀 어떠세요?"}}',
            f'{{"assistant_response": "{_NED_020_B} 오늘 컨디션은요?"}}',
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="여전히 힘들어요.",
            conversation_history=history,
            filled_slots={},
            safety_result=None,
            session_state=None,
        ))
        assert adapter.chat_timed.call_count == 3  # 1 draft + 2 retries, no 4th
        assert out.retry_count == 2
        assert out.fall_through is False
        assert out.exhaustion_degrade == "near_dup_back_to_back"
        assert out.retry_latency_ms > 0
        assert len(out.retry_reasons) >= out.retry_count
        # Question content from the LAST queued candidate ships byte-
        # identical; only the leading empathy clause was substituted.
        assert out.assistant_response.endswith(". 오늘 컨디션은요?")
        assert out.assistant_response == (
            f"{out.exhaustion_degrade_phrase}. 오늘 컨디션은요?"
        )
        assert _NED_020_B.rstrip(".") not in out.assistant_response
        assert out.assistant_response != f"{_NED_020_B} 오늘 컨디션은요?"


class TestSessionCapVsBackToBack:
    """Design §7 item 6 — back_to_back is zero-tolerance (fires on the
    FIRST reuse, priority over session_cap); session_cap fires on the 3rd
    non-consecutive same-family use."""

    def test_back_to_back_priority_on_first_reuse(self) -> None:
        session_clauses = ["정말 힘드셨겠어요"]
        violation = DialogueAgent._empathy_repetition_violation(
            "많이 힘드셨겠어요", session_clauses,
        )
        assert violation == "back_to_back"

    def test_session_cap_on_non_consecutive_third_use(self) -> None:
        # Two prior uses of the candidate's own family (turns 1, 3), with a
        # DIFFERENT-family clause immediately preceding the candidate (turn
        # 5, last element) so back_to_back does NOT fire — isolating the
        # session-cap (>=2 prior same-family uses) branch specifically.
        session_clauses = [
            "정말 힘드셨겠어요",            # turn 1 (candidate's family, 1st use)
            "많이 힘드셨겠어요",            # turn 3 (candidate's family, 2nd use)
            "이야기해 주셔서 감사합니다",    # turn 5 (different family — last element)
        ]
        violation = DialogueAgent._empathy_repetition_violation(
            "정말 힘드셨겠어요", session_clauses,
        )
        assert violation == "session_cap"


class TestMutationCheckNearDupWiredIntoRunLoop:
    """Design §7 item 8 — the run()-level loop actually retries on a
    near-duplicate, not just the pure-function detector in isolation. Would
    FAIL against an implementation that computed the near-dup detector but
    forgot to gate it on `is_empathy` (or otherwise failed to wire it into
    the loop)."""

    @pytest.mark.asyncio
    async def test_near_dup_clause_triggers_retry_at_run_level(self) -> None:
        history = [
            {"role": "assistant", "content": f"{_NED_020_A} 식사는 어떠세요?"},
        ]
        agent, adapter = _run_agent([
            f'{{"assistant_response": "{_NED_020_B} 잠은 잘 주무세요?"}}',
            '{"assistant_response": "요즘 가장 힘든 부분은 무엇인가요?"}',
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="여전히 힘들어요.",
            conversation_history=history,
            filled_slots={},
            safety_result=None,
            session_state=None,
        ))
        assert adapter.chat_timed.call_count == 2
        assert out.retry_count == 1
        assert any(r.startswith("near_dup") for r in out.retry_reasons)
        assert out.assistant_response == "요즘 가장 힘든 부분은 무엇인가요?"


class TestPresencePriorityD5:
    """ADR-029 Decision 5 (CVR-011 Finding 8): when crisis_adjacent=True,
    presence_missing takes PRIORITY over exact_repeat/near_dup — the FIRST
    retry attempt must use the presence hint, not the exact-repeat hint,
    even when the candidate ALSO exactly repeats a prior turn."""

    @pytest.mark.asyncio
    async def test_presence_missing_wins_over_exact_repeat(self) -> None:
        prior_bare_question = "혹시 최근에 잠은 잘 주무시나요?"
        history = [
            {"role": "assistant", "content": prior_bare_question},
        ]
        agent, adapter = _run_agent([
            # Draft: byte-identical to the prior turn (exact_repeat) AND a
            # bare-question opener on a crisis-adjacent turn
            # (presence_missing) — both violations fire simultaneously.
            f'{{"assistant_response": "{prior_bare_question}"}}',
            '{"assistant_response": "정말 힘드셨겠어요. 요즘 잠은 어떠세요?"}',
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="죽고 싶다는 생각이 자꾸 들어요.",
            conversation_history=history,
            filled_slots={},
            safety_result={"risk_level": "high", "ctrs_level": "3"},
            session_state=None,
        ))
        assert out.crisis_adjacent is True
        assert out.retry_count == 1
        # Priority: presence_missing, NOT exact_repeat, despite both firing.
        assert out.retry_reasons == ["presence_missing"]

        retry_messages = adapter.chat_timed.call_args_list[1].args[0]
        retry_user_content = retry_messages[-1].content
        assert "위기 인접" in retry_user_content  # presence hint text
        assert "이전과 동일한 응답" not in retry_user_content  # not the repeat hint


class TestF1TurnLogTelemetryThreading:
    """`f1.py`'s F1TurnLog carries the same 5 telemetry fields verbatim
    from a DialogueOutput (design §6) — direct dataclass-construction
    check of the threading contract, independent of the full pipeline."""

    def test_f1_turn_log_accepts_dialogue_guard_fields(self) -> None:
        dialogue_out = DialogueOutput(
            model_used="m", prompt_version="v4", latency_ms=1.0,
            assistant_response="응답",
            retry_count=2,
            retry_reasons=["near_dup_back_to_back", "presence_missing"],
            fall_through=True,
            retry_latency_ms=123.4,
            crisis_adjacent=True,
        )
        turn_log = F1TurnLog(
            turn=1, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response=dialogue_out.assistant_response,
            slot_updates={}, cumulative_slots={}, slot_coverage=0.0,
            latency_ms=1.0, timestamp="t",
            dialogue_retry_count=dialogue_out.retry_count,
            dialogue_retry_reasons=list(dialogue_out.retry_reasons),
            dialogue_fall_through=dialogue_out.fall_through,
            dialogue_retry_latency_ms=dialogue_out.retry_latency_ms,
            dialogue_crisis_adjacent=dialogue_out.crisis_adjacent,
        )
        assert turn_log.dialogue_retry_count == 2
        assert turn_log.dialogue_retry_reasons == [
            "near_dup_back_to_back", "presence_missing",
        ]
        assert turn_log.dialogue_fall_through is True
        assert turn_log.dialogue_retry_latency_ms == 123.4
        assert turn_log.dialogue_crisis_adjacent is True

    def test_f1_turn_log_defaults_are_safe(self) -> None:
        """Non-guard-aware construction (e.g. turn 0's own F1TurnLog site,
        which does not thread these fields) must still construct cleanly."""
        turn_log = F1TurnLog(
            turn=0, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response="응답", slot_updates={}, cumulative_slots={},
            slot_coverage=0.0, latency_ms=1.0, timestamp="t",
        )
        assert turn_log.dialogue_retry_count == 0
        assert turn_log.dialogue_retry_reasons == []
        assert turn_log.dialogue_fall_through is False
        assert turn_log.dialogue_retry_latency_ms == 0.0
        assert turn_log.dialogue_crisis_adjacent is False
