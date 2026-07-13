"""Tests for `src/services/f4_report.py` — `save_f4_result` + markdown
report + chart orchestration. `docs/ai/f4_quick_dev_plan.md` §5.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.schemas.longitudinal import (
    CTRSSeriesPoint,
    DiseaseCandidateSeriesPoint,
    DomainCandidateSeriesPoint,
    LongitudinalAnalysisOutput,
    ScaleSeriesPoint,
    SentimentSeriesPoint,
    SlotFillPoint,
    TrendVerdict,
)
from src.services.f4_report import _build_report, _build_trend_data_points, save_f4_result


def _sample_output(*, crisis_gaps: list[str] | None = None) -> LongitudinalAnalysisOutput:
    return LongitudinalAnalysisOutput(
        vp_id="VP-001",
        arc_mode="improvement_plateau",
        n_sessions=3,
        session_span_days=14,
        slot_fill_series=[
            SlotFillPoint(
                session_index=1, simulated_date="2026-01-01", filled_count=4, total_questionable=8,
            ),
            SlotFillPoint(
                session_index=2, simulated_date="2026-01-08", filled_count=6, total_questionable=8,
                newly_filled=["family_history"],
            ),
            SlotFillPoint(
                session_index=3, simulated_date="2026-01-15", filled_count=8, total_questionable=8,
                mental_status_exam_observed=True,
            ),
        ],
        scale_series={
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=1, simulated_date="2026-01-01", scale_name="PHQ-9",
                    administered=True, total_score=13, max_score=27, severity="moderate",
                ),
                ScaleSeriesPoint(
                    session_index=2, simulated_date="2026-01-08", scale_name="PHQ-9",
                    administered=True, total_score=8, max_score=27, severity="mild",
                ),
                ScaleSeriesPoint(
                    session_index=3, simulated_date="2026-01-15", scale_name="PHQ-9",
                    administered=True, total_score=5, max_score=27, severity="mild",
                ),
            ]
        },
        ctrs_series=[
            CTRSSeriesPoint(session_index=1, simulated_date="2026-01-01", session_ctrs=4),
            CTRSSeriesPoint(session_index=2, simulated_date="2026-01-08", session_ctrs=5),
            CTRSSeriesPoint(session_index=3, simulated_date="2026-01-15", session_ctrs=5),
        ],
        sentiment_series=[
            SentimentSeriesPoint(session_index=1, simulated_date="2026-01-01", mean_polarity=-0.3),
            SentimentSeriesPoint(session_index=2, simulated_date="2026-01-08", mean_polarity=0.0),
            SentimentSeriesPoint(session_index=3, simulated_date="2026-01-15", mean_polarity=0.4),
        ],
        disease_candidate_series=[
            DiseaseCandidateSeriesPoint(
                session_index=1, simulated_date="2026-01-01",
                disease="우울 삽화(우울증)", similarity_score=0.45, rank=1,
            ),
            DiseaseCandidateSeriesPoint(
                session_index=2, simulated_date="2026-01-08",
                disease="우울 삽화(우울증)", similarity_score=0.50, rank=1,
            ),
        ],
        domain_candidate_series=[
            DomainCandidateSeriesPoint(
                session_index=1, simulated_date="2026-01-01", domain="anxiety", confidence=0.6,
            ),
        ],
        trend_verdicts=[
            TrendVerdict(
                dimension="phq9_total", direction="improved",
                basis="first_vs_last_delta+slope_sign",
                n_comparable_points=3, evidence=["phq9_total: first-vs-last delta ..."],
            ),
        ],
        overall_direction="improved",
        course_shape="gradual_improvement",
        concordance_flag="concordant",
        crisis_f3_gaps=crisis_gaps or [],
        generated_at="2026-01-15T00:00:00",
    )


class TestBuildTrendDataPoints:
    def test_sparse_scale_series_handled(self) -> None:
        output = _sample_output()
        points = _build_trend_data_points(output)
        assert len(points) == 3
        assert points[0].phq9 == 13
        assert points[0].slot_fill_count == 4
        assert points[0].ctrs == 4
        assert points[2].slot_fill_count == 8


class TestBuildReport:
    def test_report_contains_key_sections(self) -> None:
        md = _build_report(_sample_output())
        assert "# F4 Longitudinal Analysis Report" in md
        assert "## Risk / crisis section" in md
        assert "## Trend verdicts" in md
        assert "## Slot fill (F1)" in md
        assert "## Survey scale series (F3)" in md
        assert "## Sentiment (F1)" in md
        assert "## Domain candidates (F2)" in md
        assert "## AI-predicted-disease similarity trend (F2)" in md
        assert "VAL-014" in md
        assert "gradual_improvement" in md

    def test_no_crisis_gap_states_explicit_absence(self) -> None:
        md = _build_report(_sample_output())
        assert "No F3 gap coincided with a risk-elevated session" in md

    def test_crisis_gap_surfaced_prominently(self) -> None:
        gap = "session 6 (2026-02-19): risk-elevated ..."
        md = _build_report(_sample_output(crisis_gaps=[gap]))
        assert "F3 GAP DURING RISK-ELEVATED SESSION" in md
        assert "session 6 (2026-02-19)" in md

    def test_severity_caveat_reprojected_for_audit_c(self) -> None:
        output = _sample_output()
        audit_c_point = ScaleSeriesPoint(
            session_index=1, simulated_date="2026-01-01", scale_name="AUDIT-C",
            administered=True, total_score=7, max_score=12, severity="hazardous_drinking",
        )
        output = output.model_copy(update={
            "scale_series": {**output.scale_series, "AUDIT-C": [audit_c_point]}
        })
        md = _build_report(output)
        assert "threshold_caveat (reprojected verbatim from `src.f3`)" in md
        assert "Constant-bias check status" in md
        assert "ISS-F2V-028" in md


class TestSaveF4Result:
    def test_writes_json_report_and_charts(self, tmp_path: Path) -> None:
        output = _sample_output()
        paths = save_f4_result(output, tmp_path, vp_id="VP-001")
        assert "json" in paths and paths["json"].exists()
        assert "report" in paths and paths["report"].exists()

        saved = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert saved["vp_id"] == "VP-001"
        assert saved["is_diagnostic"] is False

        report_text = paths["report"].read_text(encoding="utf-8")
        assert "F4 Longitudinal Analysis Report" in report_text

        # At least the main multi-panel chart should render given phq9+ctrs+
        # sentiment+slot_fill data is present.
        assert "chart_scales_ctrs_sentiment" in paths
        assert paths["chart_scales_ctrs_sentiment"].exists()

    def test_output_dir_naming_convention_matches_f1_f2_f3(self, tmp_path: Path) -> None:
        output = _sample_output()
        paths = save_f4_result(output, tmp_path, vp_id="VP-001")
        assert paths["json"].parent == tmp_path / "VP-001"
        assert paths["json"].name.endswith("_temporal.json")
        assert paths["report"].name.endswith("_temporal_report.md")
