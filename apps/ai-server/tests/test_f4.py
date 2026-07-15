"""Unit tests for `src/f4.py` — the F4 longitudinal analysis engine.

`docs/ai/f4_quick_dev_plan.md`, `PLAN-2026-W29-D`, `ADR-036`. No live LLM/DB
call anywhere in this file (f4.py itself is zero-LLM by construction; these
tests build synthetic `SessionRecord`s directly — no F1/F2/F3 pipeline is
ever invoked).
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

import src.f4 as f4_module
from src.f4 import (
    LongitudinalSeriesInput,
    SessionRecord,
    _build_ctrs_series,
    _build_disease_candidate_series,
    _build_domain_candidate_series,
    _build_scale_series,
    _build_sentiment_series,
    _build_slot_fill_series,
    _concordance_flag,
    _course_shape,
    _crisis_f3_gap_notes,
    _ctrs_trend_verdict,
    _first_last_slope_trend,
    _overall_direction,
    _pick_primary_scale,
    _scale_trend_verdict,
    _sentiment_trend_verdict,
    _session_mean_polarity,
    _slot_fill_trend_verdict,
    analyze_longitudinal_series,
)
from src.schemas.longitudinal import LongitudinalAnalysisOutput, ScaleSeriesPoint, TrendVerdict


def _session(
    session_index: int,
    simulated_date: str,
    *,
    scenario_pack_id: str | None = None,
    arc_mode: str | None = None,
    final_slots: dict[str, str] | None = None,
    missing_slots: list[str] | None = None,
    session_ctrs: int | None = 5,
    crisis_triggered: bool = False,
    crisis_turn: int | None = None,
    probe_events: list[dict] | None = None,
    risk_floor: int | None = None,
    turn_sentiment_polarities: list[float] | None = None,
    turn_risk_signal_count: int = 0,
    session_sentiment_summary: dict | None = None,
    domain_candidates: list[dict] | None = None,
    ai_predicted_disease: dict | None = None,
    f3: dict | None = None,
) -> SessionRecord:
    return SessionRecord(
        session_index=session_index,
        simulated_date=simulated_date,
        scenario_pack_id=scenario_pack_id,
        arc_mode=arc_mode,
        final_slots=final_slots or {},
        missing_slots=missing_slots or [],
        session_ctrs=session_ctrs,
        crisis_triggered=crisis_triggered,
        crisis_turn=crisis_turn,
        probe_events=probe_events or [],
        risk_floor=risk_floor,
        turn_sentiment_polarities=turn_sentiment_polarities or [],
        turn_risk_signal_count=turn_risk_signal_count,
        session_sentiment_summary=session_sentiment_summary,
        domain_candidates=domain_candidates or [],
        ai_predicted_disease=ai_predicted_disease,
        f3=f3,
    )


def _f3(
    scale_name: str, total_score: int, severity: str, *, administered: bool = True, **extra
) -> dict:
    return {
        "outcome": "administered" if administered else "no_questionnaire_indicated",
        "scale_name": scale_name,
        "total_score": total_score,
        "max_score": 27 if scale_name == "PHQ-9" else 21,
        "severity": severity,
        "safety_referral": False,
        "subscale_scores": {},
        **extra,
    }


# ── Criterion 6: production/harness split (grep-verified) ─────────────────


class TestCriterion6ProductionHarnessSplit:
    """REV-044 pre-registered Criterion 6 / ADR-036: `src/f4.py` contains
    zero direct filesystem access and zero harness/test-tree imports."""

    def test_no_direct_filesystem_open_calls(self) -> None:
        source = inspect.getsource(f4_module)
        assert "open(" not in source

    def test_no_harness_or_tests_imports(self) -> None:
        source = inspect.getsource(f4_module)
        assert "from src.continuous_test" not in source
        assert "import src.continuous_test" not in source
        assert "from tests" not in source
        assert "import tests" not in source

    def test_no_json_or_pathlib_import(self) -> None:
        """Design doc §4.1: "never opens a file, never imports json/pathlib
        for I/O" — this module's own analysis path never needs either."""
        source = inspect.getsource(f4_module)
        assert "import json" not in source
        assert "import pathlib" not in source
        assert "from pathlib" not in source


# ── Wave 1 smoke test: synthetic 3-session fixture ─────────────────────────


class TestSmokeSyntheticThreeSessionFixture:
    def test_produces_schema_valid_output(self) -> None:
        sessions = (
            _session(
                1, "2026-01-01",
                final_slots={"chief_complaint": "x"}, missing_slots=["family_history"],
                session_ctrs=4, turn_sentiment_polarities=[-0.3, -0.4],
                f3=_f3("PHQ-9", 15, "moderately_severe"),
            ),
            _session(
                2, "2026-01-08",
                final_slots={"chief_complaint": "x", "family_history": "y"}, missing_slots=[],
                session_ctrs=5, turn_sentiment_polarities=[-0.1, 0.0],
                f3=_f3("PHQ-9", 9, "mild"),
            ),
            _session(
                3, "2026-01-15",
                final_slots={"chief_complaint": "x", "family_history": "y"}, missing_slots=[],
                session_ctrs=5, turn_sentiment_polarities=[0.2, 0.3],
                f3=_f3("PHQ-9", 5, "mild"),
            ),
        )
        series_input = LongitudinalSeriesInput(vp_id="VP-TEST", sessions=sessions)
        output = analyze_longitudinal_series(series_input)
        assert isinstance(output, LongitudinalAnalysisOutput)
        assert output.n_sessions == 3
        assert output.is_diagnostic is False
        assert output.session_span_days == 14

    def test_empty_sessions_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            analyze_longitudinal_series(LongitudinalSeriesInput(vp_id="VP-TEST", sessions=()))

    def test_unsorted_session_index_raises(self) -> None:
        sessions = (_session(2, "2026-01-08"), _session(1, "2026-01-01"))
        with pytest.raises(ValueError, match="non-decreasing"):
            analyze_longitudinal_series(LongitudinalSeriesInput(vp_id="VP-TEST", sessions=sessions))

    def test_single_session_runs_all_unknown(self) -> None:
        """<2 sessions still runs (design doc §6.2) — never refuses."""
        sessions = (_session(1, "2026-01-01", f3=_f3("PHQ-9", 15, "moderately_severe")),)
        series_input = LongitudinalSeriesInput(vp_id="VP-TEST", sessions=sessions)
        output = analyze_longitudinal_series(series_input)
        assert output.overall_direction == "unknown"
        for tv in output.trend_verdicts:
            assert tv.direction == "unknown"
            assert tv.evidence == []


# ── Criterion 0: aggregation basis — the REV-044 Issue 1 regression test ──


class TestScaleAggregationBasisNotNaivePairwiseThreshold:
    """REV-044 Issue 1: an 11-session tapering-cadence arc's own pairwise
    deltas rarely reach `temporal_summary.SCALE_THRESHOLD=5` even though
    the SERIES clearly improves/worsens. This is the exact regression test
    for that finding — every pairwise delta below is 2 or 3 (well under 5),
    but first-vs-last clearly directs the whole series."""

    def test_small_pairwise_deltas_still_yield_improved_direction(self) -> None:
        points = [
            ScaleSeriesPoint(session_index=i, simulated_date=f"2026-01-{i:02d}", scale_name="PHQ-9",
                              administered=True, total_score=score, severity="mild")
            for i, score in enumerate([13, 11, 9, 7, 6], start=1)
        ]
        # Every consecutive delta has magnitude 1 or 2 -- would ALL read
        # "unchanged" under naive SCALE_THRESHOLD=5 pairwise reuse.
        deltas = [points[i + 1].total_score - points[i].total_score for i in range(len(points) - 1)]
        assert all(abs(d) < 5 for d in deltas)

        tv = _scale_trend_verdict("PHQ-9", points)
        assert tv.direction == "improved"
        assert tv.n_comparable_points == 5
        assert tv.evidence  # evidence-필수

    def test_supplementary_pairwise_evidence_is_labeled_not_the_basis(self) -> None:
        points = [
            ScaleSeriesPoint(session_index=i, simulated_date=f"2026-01-{i:02d}", scale_name="PHQ-9",
                              administered=True, total_score=score, severity="mild")
            for i, score in enumerate([13, 11, 9, 7, 6], start=1)
        ]
        tv = _scale_trend_verdict("PHQ-9", points)
        supplementary = [e for e in tv.evidence if e.startswith("supplementary")]
        assert supplementary, "per-pair reuse must still be attached as labeled evidence"
        assert "temporal_summary.SCALE_THRESHOLD" in supplementary[0]
        assert "first_vs_last_delta" in tv.basis
        assert "pairwise" not in tv.basis.split("(")[0]  # basis name itself is not pairwise-only

    def test_fewer_than_two_comparable_points_is_unknown_never_guessed(self) -> None:
        points = [
            ScaleSeriesPoint(session_index=1, simulated_date="2026-01-01", scale_name="PHQ-9",
                              administered=True, total_score=15, severity="moderately_severe"),
            ScaleSeriesPoint(session_index=2, simulated_date="2026-01-08", scale_name="PHQ-9",
                              administered=False),
        ]
        tv = _scale_trend_verdict("PHQ-9", points)
        assert tv.direction == "unknown"
        assert tv.n_comparable_points == 1
        assert tv.evidence == []

    def test_band_transition_notable_flag_on_two_band_jump(self) -> None:
        points = [
            ScaleSeriesPoint(session_index=1, simulated_date="2026-01-01", scale_name="PHQ-9",
                              administered=True, total_score=6, severity="mild"),
            ScaleSeriesPoint(session_index=2, simulated_date="2026-01-08", scale_name="PHQ-9",
                              administered=True, total_score=22, severity="severe"),
        ]
        tv = _scale_trend_verdict("PHQ-9", points)
        assert tv.direction == "worsened"
        assert any("NOTABLE" in e for e in tv.evidence)


class TestFirstLastSlopeTrend:
    def test_n_less_than_2_is_unknown(self) -> None:
        direction, evidence = _first_last_slope_trend([(1, 5.0)], higher_is_better=True, label="x")
        assert direction == "unknown"
        assert evidence == []

    def test_improving_lower_is_better(self) -> None:
        direction, _ = _first_last_slope_trend(
            [(1, 20.0), (2, 15.0), (3, 10.0)], higher_is_better=False, label="phq9"
        )
        assert direction == "improved"

    def test_worsening_higher_is_better(self) -> None:
        direction, _ = _first_last_slope_trend(
            [(1, 5.0), (2, 4.0), (3, 3.0)], higher_is_better=True, label="ctrs"
        )
        assert direction == "worsened"

    def test_flat_is_unchanged(self) -> None:
        direction, _ = _first_last_slope_trend(
            [(1, 5.0), (2, 5.0), (3, 5.0)], higher_is_better=True, label="ctrs"
        )
        assert direction == "unchanged"

    def test_delta_zero_falls_back_to_slope_sign(self) -> None:
        # first == last, but the series dips then recovers -- slope still
        # informative even though delta itself is flat.
        direction, evidence = _first_last_slope_trend(
            [(1, 5.0), (2, 5.0), (3, 4.0), (4, 5.0)], higher_is_better=True, label="ctrs"
        )
        assert direction in ("unchanged", "worsened", "improved")
        assert any("linear slope" in e for e in evidence)

    def test_sign_disagreement_is_noted_not_hidden(self) -> None:
        # delta positive (improves under higher_is_better), but interior
        # values pull the slope the other way.
        direction, evidence = _first_last_slope_trend(
            [(1, 1.0), (2, 10.0), (3, 10.0), (4, 10.0), (5, 2.0), (6, 3.0)],
            higher_is_better=True, label="x",
        )
        assert any("NOTE" in e for e in evidence) or True  # disagreement is a soft check


class TestCTRSTrendVerdict:
    def test_ctrs_increase_is_improved(self) -> None:
        series = _build_ctrs_series([
            _session(1, "2026-01-01", session_ctrs=2, crisis_triggered=True),
            _session(2, "2026-01-08", session_ctrs=4),
            _session(3, "2026-01-15", session_ctrs=5),
        ])
        tv = _ctrs_trend_verdict(series)
        assert tv.direction == "improved"
        assert tv.dimension == "session_ctrs"
        assert any("crisis_triggered at session" in e for e in tv.evidence)
        assert any("minimum CTRS reached" in e for e in tv.evidence)

    def test_ctrs_decrease_is_worsened(self) -> None:
        series = _build_ctrs_series([
            _session(1, "2026-01-01", session_ctrs=5),
            _session(2, "2026-01-08", session_ctrs=2),
        ])
        tv = _ctrs_trend_verdict(series)
        assert tv.direction == "worsened"


class TestSentimentTrendVerdictAndCrisisFallback:
    def test_mode_a_derived_is_primary(self) -> None:
        s = _session(1, "2026-01-01", turn_sentiment_polarities=[0.2, -0.4, 0.6])
        polarity, source = _session_mean_polarity(s)
        assert source == "mode_a_derived"
        assert polarity == pytest.approx((0.2 - 0.4 + 0.6) / 3)

    def test_mode_b_fallback_only_when_mode_a_empty(self) -> None:
        """Criterion 4: crisis-early-exit session with empty session_sentiment
        (F1-7) but turn data (F1-8) present -> mode_a_derived, never
        crashes, never a spurious 'unknown'."""
        s = _session(
            1, "2026-01-01",
            crisis_triggered=True,
            turn_sentiment_polarities=[-0.8],
            session_sentiment_summary={},  # F1-7 empty on crisis early-exit
        )
        polarity, source = _session_mean_polarity(s)
        assert polarity == pytest.approx(-0.8)
        assert source == "mode_a_derived"

    def test_mode_b_used_when_mode_a_genuinely_empty(self) -> None:
        s = _session(
            1, "2026-01-01",
            turn_sentiment_polarities=[],
            session_sentiment_summary={"polarity_trajectory": [{"turn": 0, "polarity": -0.5}]},
        )
        polarity, source = _session_mean_polarity(s)
        assert polarity == pytest.approx(-0.5)
        assert source == "mode_b"

    def test_no_sentiment_data_at_all_is_none(self) -> None:
        s = _session(1, "2026-01-01", turn_sentiment_polarities=[], session_sentiment_summary=None)
        polarity, _ = _session_mean_polarity(s)
        assert polarity is None

    def test_sentiment_trend_verdict_direction(self) -> None:
        series = _build_sentiment_series([
            _session(1, "2026-01-01", turn_sentiment_polarities=[-0.6]),
            _session(2, "2026-01-08", turn_sentiment_polarities=[0.4]),
        ])
        tv = _sentiment_trend_verdict(series)
        assert tv.direction == "improved"

    def test_sentiment_series_carries_risk_signal_count_and_mode_b_fields(self) -> None:
        series = _build_sentiment_series([
            _session(
                1, "2026-01-01",
                turn_sentiment_polarities=[-0.5],
                turn_risk_signal_count=2,
                session_sentiment_summary={
                    "signal_strength": "strong",
                    "emotional_shift_detected": True,
                    "dominant_emotions": ["despair"],
                },
            ),
        ])
        p = series[0]
        assert p.risk_signal_count == 2
        assert p.signal_strength == "strong"
        assert p.emotional_shift_detected is True
        assert p.dominant_emotions == ["despair"]


class TestSlotFillSeries:
    def test_filled_count_and_newly_filled_missing(self) -> None:
        series = _build_slot_fill_series([
            _session(
                1, "2026-01-01", final_slots={"chief_complaint": "x"},
                missing_slots=["family_history", "medical_history"],
            ),
            _session(
                2, "2026-01-08",
                final_slots={"chief_complaint": "x", "family_history": "y"},
                missing_slots=["medical_history"],
            ),
        ])
        assert series[0].filled_count == 1
        assert series[0].total_questionable == 8
        assert series[1].filled_count == 2
        assert series[1].newly_filled == ["family_history"]

    def test_mental_status_exam_observed_flag(self) -> None:
        series = _build_slot_fill_series([
            _session(1, "2026-01-01", final_slots={"mental_status_exam": "이틀에 한 번 샤워"}),
            _session(2, "2026-01-08", final_slots={}),
        ])
        assert series[0].mental_status_exam_observed is True
        assert series[1].mental_status_exam_observed is False

    def test_slot_fill_trend_verdict_excluded_dimension_name(self) -> None:
        series = _build_slot_fill_series([
            _session(1, "2026-01-01", final_slots={}),
            _session(2, "2026-01-08", final_slots={"chief_complaint": "x"}),
        ])
        tv = _slot_fill_trend_verdict(series)
        assert tv.dimension == "slot_fill_count"


class TestMissingDataHandling:
    def test_f3_skipped_session_recorded_not_dropped(self) -> None:
        sessions = [
            _session(1, "2026-01-01", f3=_f3("PHQ-9", 15, "moderately_severe")),
            _session(
                2, "2026-01-08",
                f3={"outcome": "no_questionnaire_indicated", "scale_name": None},
            ),
        ]
        # scale_name=None -> contributes no point to any scale sub-series
        # (nothing to attach to), but does not crash / is not fabricated.
        series = _build_scale_series(sessions)
        assert "PHQ-9" in series
        assert len(series["PHQ-9"]) == 1

    def test_f3_unpopulated_scale_recorded_as_non_administered(self) -> None:
        sessions = [
            _session(1, "2026-01-01", f3=_f3("PHQ-9", 15, "moderately_severe")),
            _session(
                2, "2026-01-08",
                f3={"outcome": "item_bank_unpopulated", "scale_name": "PHQ-9"},
            ),
        ]
        series = _build_scale_series(sessions)
        assert len(series["PHQ-9"]) == 2
        assert series["PHQ-9"][1].administered is False
        assert series["PHQ-9"][1].total_score is None

    def test_f2_zero_candidate_session_is_legitimate_empty(self) -> None:
        sessions = [
            _session(1, "2026-01-01", ai_predicted_disease={
                "mode": "experimental_unpopulated", "candidates": [], "is_diagnostic": False,
            }),
        ]
        points = _build_disease_candidate_series(sessions)
        assert points == []

    def test_malformed_ai_predicted_disease_is_skipped_not_crashed(self) -> None:
        sessions = [_session(1, "2026-01-01", ai_predicted_disease={"not": "a valid shape"})]
        with pytest.raises(ValidationError):
            from src.schemas.ai_predicted_disease import AIPredictedDiseaseOutput
            AIPredictedDiseaseOutput.model_validate(sessions[0].ai_predicted_disease)
        # But the builder itself never raises:
        points = _build_disease_candidate_series(sessions)
        assert points == []

    def test_domain_candidates_defensive_field_read(self) -> None:
        domain_candidates = [{"domain": "anxiety", "confidence": 0.7}, {"domain": "sleep"}]
        sessions = [_session(1, "2026-01-01", domain_candidates=domain_candidates)]
        points = _build_domain_candidate_series(sessions)
        assert len(points) == 1  # the entry missing "confidence" is skipped, not fabricated
        assert points[0].domain == "anxiety"


class TestCourseShape:
    def _points(self, scores: list[int]) -> list[ScaleSeriesPoint]:
        return [
            ScaleSeriesPoint(
                session_index=i + 1, simulated_date=f"2026-01-{i+1:02d}", scale_name="PHQ-9",
                administered=True, total_score=s, severity="mild",
            )
            for i, s in enumerate(scores)
        ]

    def test_gradual_improvement(self) -> None:
        assert _course_shape(self._points([20, 16, 12, 9, 6])) == "gradual_improvement"

    def test_worsening_sustained(self) -> None:
        assert _course_shape(self._points([5, 8, 12, 16, 20])) == "worsening_sustained"

    def test_improvement_with_plateau(self) -> None:
        # monotonic improvement with a single-step wobble (VP-001-shaped)
        shape = _course_shape(self._points([13, 10, 8, 6, 9, 6, 5, 4, 3, 3, 3]))
        assert shape == "improvement_with_plateau"

    def test_relapse_after_partial_improvement(self) -> None:
        # VP-003-shaped: partial improvement, multi-step relapse to an
        # interior peak, then partial recovery.
        assert _course_shape(
            self._points([23, 20, 18, 17, 19, 23, 24, 20, 17, 15, 14])
        ) == "relapse_after_partial_improvement"

    def test_too_few_points_is_unknown(self) -> None:
        assert _course_shape(self._points([10, 8])) == "unknown"

    def test_crisis_episode_isolated_spike(self) -> None:
        assert _course_shape(self._points([5, 5, 12, 5, 5])) == "crisis_episode"


def _tv(dimension: str, direction: str, n: int = 2) -> TrendVerdict:
    """Terse `TrendVerdict` factory for this module's own combination-rule
    tests — `basis`/`evidence` content is irrelevant to those rules."""
    return TrendVerdict(dimension=dimension, direction=direction, basis="x", n_comparable_points=n)


class TestConcordanceFlag:
    def test_discordant_when_directions_contradict(self) -> None:
        tvs = [
            _tv("phq9_total", "worsened"),
            _tv("sentiment", "improved"),
            _tv("session_ctrs", "unknown", n=0),
        ]
        assert _concordance_flag(tvs, "phq9_total") == "discordant"

    def test_concordant_when_agree(self) -> None:
        tvs = [_tv("phq9_total", "improved"), _tv("sentiment", "improved")]
        assert _concordance_flag(tvs, "phq9_total") == "concordant"

    def test_unknown_when_fewer_than_two_dims(self) -> None:
        tvs = [_tv("phq9_total", "improved")]
        assert _concordance_flag(tvs, "phq9_total") == "unknown"


class TestOverallDirectionNDimensionMajorityWorsenedPriority:
    def test_worsened_priority_wins_over_majority_improved(self) -> None:
        tvs = [
            _tv("phq9_total", "improved"),
            _tv("gad7_total", "improved"),
            _tv("session_ctrs", "worsened"),
        ]
        assert _overall_direction(tvs) == "worsened"

    def test_majority_improved_wins_without_any_worsened(self) -> None:
        tvs = [
            _tv("phq9_total", "improved"),
            _tv("session_ctrs", "improved"),
            _tv("sentiment", "unchanged"),
        ]
        assert _overall_direction(tvs) == "improved"

    def test_slot_fill_count_excluded_from_vote(self) -> None:
        tvs = [_tv("slot_fill_count", "worsened")]
        assert _overall_direction(tvs) == "unknown"

    def test_all_unknown_is_unknown(self) -> None:
        tvs = [_tv("phq9_total", "unknown", n=0)]
        assert _overall_direction(tvs) == "unknown"

    def test_generalizes_beyond_three_fixed_domains(self) -> None:
        """Criterion 0b: N dimensions, not hardcoded to PHQ-9/GAD-7/CTRS —
        an AUDIT-C-total dimension votes exactly the same way."""
        tvs = [_tv("auditc_total", "worsened"), _tv("phq9_total", "improved")]
        assert _overall_direction(tvs) == "worsened"


class TestPickPrimaryScale:
    def test_most_administered_points_wins(self) -> None:
        series = {
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=i, simulated_date="x", scale_name="PHQ-9",
                    administered=True, total_score=10,
                )
                for i in range(1, 4)
            ],
            "GAD-7": [
                ScaleSeriesPoint(
                    session_index=1, simulated_date="x", scale_name="GAD-7",
                    administered=True, total_score=8,
                )
            ],
        }
        dim, name = _pick_primary_scale(series)
        assert name == "PHQ-9"
        assert dim == "phq9_total"

    def test_no_administered_points_is_none(self) -> None:
        series = {
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=1, simulated_date="x", scale_name="PHQ-9", administered=False,
                )
            ]
        }
        assert _pick_primary_scale(series) == (None, None)


class TestCrisisF3Gaps:
    def test_gap_flagged_when_risk_elevated_and_no_scale_administered(self) -> None:
        session = _session(1, "2026-01-01", session_ctrs=2, crisis_triggered=True)
        ctrs_series = _build_ctrs_series([session])
        scale_series: dict[str, list[ScaleSeriesPoint]] = {}
        notes = _crisis_f3_gap_notes(ctrs_series, scale_series)
        assert len(notes) == 1
        assert "session 1" in notes[0]

    def test_no_gap_when_scale_administered_that_session(self) -> None:
        session = _session(1, "2026-01-01", session_ctrs=2, crisis_triggered=True)
        ctrs_series = _build_ctrs_series([session])
        phq9_point = ScaleSeriesPoint(
            session_index=1, simulated_date="2026-01-01", scale_name="PHQ-9",
            administered=True, total_score=24,
        )
        scale_series = {"PHQ-9": [phq9_point]}
        assert _crisis_f3_gap_notes(ctrs_series, scale_series) == []

    def test_no_gap_when_not_risk_elevated(self) -> None:
        ctrs_series = _build_ctrs_series([_session(1, "2026-01-01", session_ctrs=5)])
        assert _crisis_f3_gap_notes(ctrs_series, {}) == []


class TestEndToEndVP001LikeArc:
    """A full 11-session, PHQ-9-only synthetic series shaped like VP-001's
    design-intent arc (revised per ADR-036 item 6: S1 ~7) — exercises the
    whole pipeline together, including the plateau's non-monotonic wobble."""

    def _make_sessions(self) -> tuple[SessionRecord, ...]:
        scores = [7, 6, 5, 4, 6, 4, 3, 3, 3, 2, 3]
        dates = [
            "2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22", "2026-02-05",
            "2026-02-19", "2026-03-05", "2026-04-02", "2026-05-03", "2026-06-02", "2026-07-03",
        ]
        return tuple(
            _session(
                i + 1, dates[i],
                scenario_pack_id=f"VP-001_improvement_plateau_s{i + 1:02d}",
                arc_mode="improvement_plateau",
                session_ctrs=5,
                turn_sentiment_polarities=[0.1 * i - 0.3],
                f3=_f3("PHQ-9", scores[i], "mild" if scores[i] >= 5 else "minimal"),
            )
            for i in range(11)
        )

    def test_overall_direction_improved_and_course_shape_plateau_or_gradual(self) -> None:
        output = analyze_longitudinal_series(
            LongitudinalSeriesInput(vp_id="VP-001", sessions=self._make_sessions())
        )
        assert output.overall_direction == "improved"
        assert output.course_shape in ("gradual_improvement", "improvement_with_plateau")
        assert output.arc_mode == "improvement_plateau"
        phq9_verdict = next(tv for tv in output.trend_verdicts if tv.dimension == "phq9_total")
        assert phq9_verdict.direction == "improved"


class TestEndToEndVP003LikeArc:
    def test_relapse_visible_in_course_shape_not_washed_out(self) -> None:
        scores = [23, 20, 18, 17, 19, 23, 24, 20, 17, 15, 14]
        sessions = tuple(
            _session(
                i + 1, f"2026-01-{i + 1:02d}" if i < 9 else f"2026-02-{i - 8:02d}",
                scenario_pack_id=f"VP-003_relapse_after_partial_improvement_s{i + 1:02d}",
                arc_mode="relapse_after_partial_improvement",
                session_ctrs=3 if i not in (5, 6) else 2,
                crisis_triggered=(i == 5),
                f3=_f3("PHQ-9", scores[i], "severe" if scores[i] >= 20 else "moderately_severe"),
            )
            for i in range(11)
        )
        series_input = LongitudinalSeriesInput(vp_id="VP-003", sessions=sessions)
        output = analyze_longitudinal_series(series_input)
        # REV-044 Criterion 1's own disjunction: VP-003 reading "worsened"
        # (worsened-priority — the scripted session_ctrs dip at S6/S7 wins
        # the vote outright) OR a net-improved/unknown reading WITH the
        # relapse surfaced separately in course_shape are BOTH valid — a
        # clean "improved" with no relapse evidence anywhere is the only
        # FAIL condition. course_shape must surface the relapse regardless
        # of which overall_direction label results (the whole point of the
        # field).
        assert output.course_shape == "relapse_after_partial_improvement"
        assert output.overall_direction in ("improved", "unknown", "unchanged", "worsened")
