"""`src.rag_trigger` — RAG trigger Policy A/B pure logic + choke-point filter.

PLAN-2026-W28-Q W4. Deterministic, no live LLM/DB anywhere in this file —
Policy B is exercised via a fake judge object, per this dispatch's own
constraint ("No live LLM call in this dispatch — deterministic tests use
mocked judge outputs").
"""

from __future__ import annotations

import pytest

from src.rag_trigger import (
    SLOT_INSUFFICIENCY_THRESHOLD_N,
    STAGE1_QUERY_SLOTS,
    TriggerDecision,
    apply_risk_lexicon_filter,
    combined_slot_length,
    compose_fallback_queries,
    compose_slot_queries,
    decide_policy_a,
    decide_policy_b,
    is_slot_insufficient,
    no_rag_decision,
    probe_adjacent_turns,
)
from src.schemas.domain_inference import UtteranceTurn


class TestComposeSlotQueries:
    def test_mirrors_stage1_query_slots_exactly(self) -> None:
        assert STAGE1_QUERY_SLOTS == ("chief_complaint", "history_of_present_illness")
        assert "risk_assessment" not in STAGE1_QUERY_SLOTS

    def test_composes_both_when_present(self) -> None:
        slots = {"chief_complaint": "불안감", "history_of_present_illness": "2주 전부터"}
        assert compose_slot_queries(slots) == ["불안감", "2주 전부터"]

    def test_falsy_slots_excluded(self) -> None:
        slots = {"chief_complaint": "", "history_of_present_illness": "2주 전부터"}
        assert compose_slot_queries(slots) == ["2주 전부터"]

    def test_risk_assessment_never_composed(self) -> None:
        slots = {"chief_complaint": "불안감", "risk_assessment": "자살사고 있음"}
        assert compose_slot_queries(slots) == ["불안감"]


class TestSlotInsufficiencyThresholdBoundary:
    """N-boundary: 74/75/76 chars — N=75 is ADOPTED (Appendix A), the
    trigger condition is `< N` (strictly less), so exactly 75 is
    SUFFICIENT, 74 is insufficient, 76 is sufficient."""

    def test_threshold_constant_is_75(self) -> None:
        assert SLOT_INSUFFICIENCY_THRESHOLD_N == 75

    def test_74_chars_is_insufficient(self) -> None:
        cc = "가" * 74
        assert combined_slot_length({"chief_complaint": cc}) == 74
        assert is_slot_insufficient({"chief_complaint": cc}) is True

    def test_75_chars_is_sufficient(self) -> None:
        cc = "가" * 75
        assert combined_slot_length({"chief_complaint": cc}) == 75
        assert is_slot_insufficient({"chief_complaint": cc}) is False

    def test_76_chars_is_sufficient(self) -> None:
        cc = "가" * 76
        assert is_slot_insufficient({"chief_complaint": cc}) is False

    def test_combined_across_both_slots_at_boundary(self) -> None:
        slots = {"chief_complaint": "가" * 40, "history_of_present_illness": "나" * 35}
        assert combined_slot_length(slots) == 75
        assert is_slot_insufficient(slots) is False
        slots["history_of_present_illness"] = "나" * 34
        assert combined_slot_length(slots) == 74
        assert is_slot_insufficient(slots) is True

    def test_custom_threshold_override(self) -> None:
        assert is_slot_insufficient({"chief_complaint": "가" * 10}, threshold=5) is False
        assert is_slot_insufficient({"chief_complaint": "가" * 4}, threshold=5) is True


class TestBothFalsyTrigger:
    def test_both_absent_is_insufficient(self) -> None:
        assert is_slot_insufficient({}) is True

    def test_both_empty_string_is_insufficient(self) -> None:
        slots = {"chief_complaint": "", "history_of_present_illness": ""}
        assert is_slot_insufficient(slots) is True

    def test_one_present_one_absent_uses_length_not_falsy_branch(self) -> None:
        """Only one slot falsy is NOT the both-falsy case — governed by the
        length check instead."""
        slots = {"chief_complaint": "가" * 80}
        assert is_slot_insufficient(slots) is False  # length alone is sufficient


class TestProbeAdjacentTurnExclusion:
    def test_extracts_turn_numbers_from_probe_events(self) -> None:
        events = [
            {"type": "trigger", "turn": 0},
            {"type": "deescalation", "turn": 2},
        ]
        assert probe_adjacent_turns(events) == {0, 2}

    def test_no_events_yields_empty_set(self) -> None:
        assert probe_adjacent_turns([]) == set()

    def test_fallback_excludes_probe_adjacent_turns(self) -> None:
        turns = [
            UtteranceTurn(turn=0, patient_message="처음 발화"),
            UtteranceTurn(turn=1, patient_message="probe 답변"),
            UtteranceTurn(turn=2, patient_message="clean 발화"),
        ]
        probe_events = [{"type": "trigger", "turn": 1}]
        composed = compose_fallback_queries(turns, probe_events)
        assert "probe 답변" not in composed
        assert "처음 발화" in composed
        assert "clean 발화" in composed

    def test_all_probe_adjacent_yields_no_fallback_candidates(self) -> None:
        turns = [UtteranceTurn(turn=0, patient_message="only turn")]
        probe_events = [{"type": "trigger", "turn": 0}]
        assert compose_fallback_queries(turns, probe_events) == []

    def test_max_queries_cap(self) -> None:
        turns = [UtteranceTurn(turn=i, patient_message=f"발화{i}") for i in range(5)]
        composed = compose_fallback_queries(turns, [], max_queries=2)
        assert len(composed) == 2


class TestApplyRiskLexiconFilter:
    """The single choke point (REV-022 Issues 9/10)."""

    def test_clean_queries_pass_through_unchanged(self) -> None:
        clean, dropped = apply_risk_lexicon_filter(["불안감과 수면 문제", "2주 전부터 악화"])
        assert clean == ["불안감과 수면 문제", "2주 전부터 악화"]
        assert dropped == []

    def test_risk_worded_query_dropped_not_sanitized(self) -> None:
        clean, dropped = apply_risk_lexicon_filter(["살고 싶지 않아요"])
        assert clean == []
        assert dropped == ["살고 싶지 않아요"]

    def test_mixed_list_only_risky_ones_dropped(self) -> None:
        clean, dropped = apply_risk_lexicon_filter(
            ["불안감과 수면 문제", "죽고 싶다는 생각이 듦", "2주 전부터 악화"]
        )
        assert clean == ["불안감과 수면 문제", "2주 전부터 악화"]
        assert dropped == ["죽고 싶다는 생각이 듦"]

    def test_empty_string_query_is_not_dropped_but_stays_clean(self) -> None:
        clean, dropped = apply_risk_lexicon_filter([""])
        assert clean == [""]
        assert dropped == []

    def test_empty_list_input(self) -> None:
        assert apply_risk_lexicon_filter([]) == ([], [])


class TestNoRagDecision:
    def test_records_honest_decision_no_llm_call(self) -> None:
        decision = no_rag_decision("A")
        assert decision.policy == "A"
        assert decision.retrieve is False
        assert decision.queries == []
        assert decision.trigger_reason == "no_rag_flag"

    def test_policy_b_variant(self) -> None:
        decision = no_rag_decision("B")
        assert decision.policy == "B"
        assert decision.judge_output is None


class TestDecidePolicyA:
    def test_sufficient_slots_no_fallback_engaged(self) -> None:
        slots = {
            "chief_complaint": (
                "불안감과 수면 문제가 지속되고 있으며 집중이 잘 되지 않고 일상생활 전반에 "
                "어려움을 느낌"
            ),
            "history_of_present_illness": (
                "2주 전부터 점진적으로 악화되어 일상생활에 지장이 있고 식욕도 저하됨"
            ),
        }
        assert combined_slot_length(slots) >= SLOT_INSUFFICIENCY_THRESHOLD_N
        decision = decide_policy_a(slots, turns=[], probe_events=[])
        assert decision.policy == "A"
        assert decision.fallback_used is False
        assert decision.retrieve is True
        assert decision.queries == list(slots.values())
        assert decision.dropped_queries == []

    def test_insufficient_short_slots_engages_fallback(self) -> None:
        slots = {"chief_complaint": "불안"}  # far below N=75, falsy HPI too
        turns = [
            UtteranceTurn(turn=0, patient_message="불안"),
            UtteranceTurn(turn=1, patient_message="잠도 잘 못 자요"),
        ]
        decision = decide_policy_a(slots, turns, probe_events=[])
        assert decision.fallback_used is True
        assert decision.retrieve is True
        assert "잠도 잘 못 자요" in decision.queries

    def test_both_falsy_and_no_usable_fallback_does_not_retrieve(self) -> None:
        decision = decide_policy_a({}, turns=[], probe_events=[])
        assert decision.retrieve is False
        assert decision.queries == []
        assert "no_usable_queries" in decision.trigger_reason

    # ── Single-choke-point filter application (both branches) ───────────

    def test_choke_point_filters_primary_queries_even_when_sufficient(self) -> None:
        """REV-022 finding 3d: cc/HPI queries were NEVER filtered before
        this wave, even on the default/sufficient path. This is the fix —
        the filter now runs unconditionally."""
        slots = {
            "chief_complaint": (
                "살고 싶지 않다는 생각이 계속 들고 무기력하며 답답함을 느끼고 잠도 잘 못 이룸"
            ),
            "history_of_present_illness": (
                "2주 전부터 점진적으로 악화되어 일상생활에 지장이 크게 있음"
            ),
        }
        assert combined_slot_length(slots) >= SLOT_INSUFFICIENCY_THRESHOLD_N
        decision = decide_policy_a(slots, turns=[], probe_events=[])
        assert slots["chief_complaint"] not in decision.queries
        assert slots["chief_complaint"] in decision.dropped_queries
        assert slots["history_of_present_illness"] in decision.queries

    def test_choke_point_filters_fallback_queries_too(self) -> None:
        slots = {"chief_complaint": "불안"}
        turns = [
            UtteranceTurn(turn=0, patient_message="불안"),
            UtteranceTurn(turn=1, patient_message="자살 생각이 자꾸 들어요"),
        ]
        decision = decide_policy_a(slots, turns, probe_events=[])
        assert "자살 생각이 자꾸 들어요" not in decision.queries
        assert "자살 생각이 자꾸 들어요" in decision.dropped_queries

    # ── VP-003 run2 shape (data's W4 flag, Appendix A item 4) ────────────

    def test_vp003_run2_shape_terse_complete_risky_cc_routes_to_fallback_and_filters(
        self,
    ) -> None:
        """Reproduces the empirically-flagged shape (synthetic equivalent,
        real artifact under `_archive/`, not read here): a COMPLETE
        (non-falsy) but terse cc+HPI pair under N=75 chars, with a
        risk-lexicon-flagged chief_complaint. Turn 0 (which restates the
        chief complaint) is ALSO the Safety-Probe trigger turn — so probe-
        turn exclusion alone would NOT catch the risk content (it arrives
        via the PRIMARY slot-text path, `final_slots["chief_complaint"]`,
        not via the fallback-turns path at all). Only the single-choke-
        point risk-lexicon filter closes this — the assertion this test
        exists to make.
        """
        risky_cc = "요즘 계속 살고 싶지 않다는 생각이 들고 무기력하고 답답함"
        hpi = "2주 전부터 악화되고 불면도 동반됨"
        slots = {"chief_complaint": risky_cc, "history_of_present_illness": hpi}
        assert combined_slot_length(slots) < SLOT_INSUFFICIENCY_THRESHOLD_N, (
            "fixture must reproduce the 'terse-but-complete, under N=75' shape"
        )

        turns = [
            UtteranceTurn(turn=0, patient_message=risky_cc),
            UtteranceTurn(turn=1, patient_message="네, 최근 잠도 잘 못 자요"),
        ]
        # Turn 0 IS the probe trigger turn — excluded from the fallback-turns
        # candidate pool (verified below), yet the SAME risky text still
        # reaches Stage 1's query composition via the primary slot path.
        probe_events = [{"type": "trigger", "turn": 0}]

        decision = decide_policy_a(slots, turns, probe_events)

        assert decision.fallback_used is True, "insufficiency must route into the fallback path"
        # Probe-turn exclusion worked: turn 0's text never became a
        # fallback candidate (it only appears via the primary slot path).
        fallback_only = compose_fallback_queries(turns, probe_events)
        assert risky_cc not in fallback_only

        # The single choke point is what actually stripped it:
        assert risky_cc not in decision.queries
        assert risky_cc in decision.dropped_queries
        # A clean query still reaches Stage 1 (retrieval is not abandoned
        # outright just because one source was risk-flagged).
        assert decision.retrieve is True
        assert hpi in decision.queries


class _FakeJudge:
    def __init__(self, retrieve: bool, query: str | None, prompts_degraded: bool = False):
        self._retrieve = retrieve
        self._query = query
        self._prompts_degraded = prompts_degraded
        self.received_input = None

    async def run(self, inp):
        self.received_input = inp
        from src.schemas.rag_trigger_judge import RagTriggerJudgeOutput

        return RagTriggerJudgeOutput(
            model_used="fake", prompt_version="v1", latency_ms=1.0,
            reason_summary="fake judge",
            retrieve=self._retrieve, query=self._query,
            prompts_degraded=self._prompts_degraded,
        )


class TestDecidePolicyB:
    @pytest.mark.asyncio
    async def test_judge_retrieve_true_with_clean_query(self) -> None:
        judge = _FakeJudge(retrieve=True, query="불안감과 수면 문제")
        decision = await decide_policy_b(
            judge, session_id="t", final_slots={"chief_complaint": "불안"}, turns=[]
        )
        assert decision.policy == "B"
        assert decision.retrieve is True
        assert decision.queries == ["불안감과 수면 문제"]
        assert decision.judge_output["retrieve"] is True
        assert decision.judge_output["query"] == "불안감과 수면 문제"

    @pytest.mark.asyncio
    async def test_judge_retrieve_false(self) -> None:
        judge = _FakeJudge(retrieve=False, query=None)
        decision = await decide_policy_b(
            judge, session_id="t", final_slots={}, turns=[]
        )
        assert decision.retrieve is False
        assert decision.queries == []
        assert decision.judge_output["retrieve"] is False

    @pytest.mark.asyncio
    async def test_risk_assessment_stripped_before_judge_ever_sees_it(self) -> None:
        """REV-022 Issue 10's original mitigation, still enforced: the judge
        never receives `risk_assessment`, regardless of what it decides."""
        judge = _FakeJudge(retrieve=True, query="불안감")
        final_slots = {
            "chief_complaint": "불안감",
            "risk_assessment": "자살사고 있음, 구체적 계획 보고",
        }
        await decide_policy_b(judge, session_id="t", final_slots=final_slots, turns=[])
        assert "risk_assessment" not in judge.received_input.final_slots

    @pytest.mark.asyncio
    async def test_choke_point_filters_judge_composed_query(self) -> None:
        """The SAME single choke point applies to Policy B's judge-composed
        query as Policy A's queries (REV-022 Issues 9/10)."""
        judge = _FakeJudge(retrieve=True, query="죽고 싶다는 생각이 계속 듦")
        decision = await decide_policy_b(
            judge, session_id="t", final_slots={}, turns=[]
        )
        # judge SAID retrieve=True, but its only query was risk-flagged —
        # the EFFECTIVE decision must not retrieve with it.
        assert decision.queries == []
        assert "죽고 싶다는 생각이 계속 듦" in decision.dropped_queries
        assert decision.retrieve is False
        assert decision.trigger_reason == "judge_retrieve_but_query_risk_filtered"
        # But the judge's OWN raw decision is preserved for audit (Gate 0.5
        # / SC-3b's stability check reads this field, not the effective one).
        assert decision.judge_output["retrieve"] is True

    @pytest.mark.asyncio
    async def test_judge_io_persisted_in_judge_output(self) -> None:
        """REV-024 Issue 3 (blocking-scoped, Gate 0 criterion 5): the agent
        computes a genuine per-call ``latency_ms`` (`rag_trigger_judge.py`);
        this asserts it survives into the persisted artifact dict, not just
        onto the transient `RagTriggerJudgeOutput` object — the prior
        fixture omitted the key and so encoded the drop instead of catching
        it."""
        judge = _FakeJudge(retrieve=True, query="수면 문제", prompts_degraded=True)
        decision = await decide_policy_b(
            judge, session_id="t", final_slots={}, turns=[]
        )
        assert decision.judge_output == {
            "retrieve": True,
            "query": "수면 문제",
            "reason_summary": "fake judge",
            "model_used": "fake",
            "prompt_version": "v1",
            "prompts_degraded": True,
            "latency_ms": 1.0,
        }

    @pytest.mark.asyncio
    async def test_null_query_with_retrieve_true_is_not_treated_as_a_query(self) -> None:
        judge = _FakeJudge(retrieve=True, query=None)
        decision = await decide_policy_b(
            judge, session_id="t", final_slots={}, turns=[]
        )
        assert decision.queries == []
        assert decision.retrieve is False


class TestTriggerDecisionAsDict:
    def test_as_dict_shape(self) -> None:
        decision = TriggerDecision(
            policy="A", retrieve=True, queries=["q1"], dropped_queries=["q2"],
            trigger_reason="sufficient_no_fallback_retrieve", fallback_used=False,
        )
        assert decision.as_dict() == {
            "policy": "A", "retrieve": True, "queries": ["q1"], "dropped_queries": ["q2"],
            "trigger_reason": "sufficient_no_fallback_retrieve", "fallback_used": False,
            "judge_output": None,
        }
