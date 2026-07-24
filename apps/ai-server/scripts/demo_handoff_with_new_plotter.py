"""Produce a real F5 handoff report (PDF + MD) whose embedded longitudinal
chart is rendered by the refactored ``trend_plotter.py``.

Pipeline: rich LongitudinalAnalysisOutput → f4_report._generate_and_save_charts
(new small-multiples engine) → assemble_handoff_report → f5_report.build_pdf_report
embedding the F4 PNG. Writes to /tmp/handoff_demo/.
"""

from __future__ import annotations

from pathlib import Path

from src.f5 import (
    ChartFilenames,
    DepartmentCandidateInput,
    DomainInferenceSnapshot,
    F3Administration,
    HandoffReportInput,
    SessionSnapshot,
    assemble_handoff_report,
)
from src.schemas.ai_predicted_disease import (
    AIPredictedDiseaseCandidate,
    AIPredictedDiseaseOutput,
)
from src.schemas.longitudinal import (
    CTRSSeriesPoint,
    DiseaseCandidateSeriesPoint,
    DomainCandidateSeriesPoint,
    LongitudinalAnalysisOutput,
    ScaleSeriesPoint,
    SentimentSeriesPoint,
    SlotFillPoint,
)
from src.services.f4_report import _generate_and_save_charts
from src.services.f5_report import build_markdown_report, build_pdf_report

OUT = Path("/tmp/handoff_demo")
OUT.mkdir(parents=True, exist_ok=True)
VP = "VP-DEMO"

# 6-session arc: crisis → medication → sustained improvement, with a
# missing PHQ/GAD session (S2) and a late 2-point AUDIT-C series.
DATES = ["2026-01-05", "2026-01-26", "2026-02-16", "2026-03-09", "2026-03-30", "2026-04-20"]
PHQ = [22, None, 17, 12, 8, 6]
GAD = [15, None, 11, 8, 6, 5]
AUDIT = [None, None, None, None, 11, 8]
CTRS = [2, 3, 4, 4, 5, 5]
SENT = [-0.7, -0.5, -0.2, 0.0, 0.3, 0.35]
SLOT = [4, 6, 8, 8, 8, 8]


def _scale(name, scores):
    return [
        ScaleSeriesPoint(
            session_index=i + 1, simulated_date=d, scale_name=name,
            administered=s is not None, total_score=s,
            max_score={"PHQ-9": 27, "GAD-7": 21, "AUDIT-C": 12}[name],
        )
        for i, (d, s) in enumerate(zip(DATES, scores, strict=True))
    ]


longitudinal = LongitudinalAnalysisOutput(
    vp_id=VP,
    n_sessions=6,
    session_span_days=105,
    slot_fill_series=[
        SlotFillPoint(session_index=i + 1, simulated_date=d, filled_count=c, total_questionable=8)
        for i, (d, c) in enumerate(zip(DATES, SLOT, strict=True))
    ],
    scale_series={"PHQ-9": _scale("PHQ-9", PHQ), "GAD-7": _scale("GAD-7", GAD),
                  "AUDIT-C": _scale("AUDIT-C", AUDIT)},
    ctrs_series=[
        CTRSSeriesPoint(session_index=i + 1, simulated_date=d, session_ctrs=c,
                        crisis_triggered=(c <= 2))
        for i, (d, c) in enumerate(zip(DATES, CTRS, strict=True))
    ],
    sentiment_series=[
        SentimentSeriesPoint(session_index=i + 1, simulated_date=d, mean_polarity=p)
        for i, (d, p) in enumerate(zip(DATES, SENT, strict=True))
    ],
    disease_candidate_series=[
        DiseaseCandidateSeriesPoint(session_index=i + 1, simulated_date=d,
                                    disease="주요우울장애", similarity_score=v, rank=1)
        for i, (d, v) in enumerate(zip(DATES, [0.42, 0.5, 0.55, 0.6, 0.63, 0.65], strict=True))
    ],
    domain_candidate_series=[
        DomainCandidateSeriesPoint(session_index=i + 1, simulated_date=d,
                                   domain="정신건강의학과", confidence=v)
        for i, (d, v) in enumerate(zip(DATES, [0.55, 0.6, 0.7, 0.75, 0.8, 0.82], strict=True))
    ],
    overall_direction="improved",
    course_shape="gradual_improvement",
    concordance_flag="concordant",
)

# 1) Generate F4 charts with the NEW trend_plotter engine.
chart_paths = _generate_and_save_charts(longitudinal, OUT, VP)
print("charts:", {k: p.name for k, p in chart_paths.items()})

# map f4_report keys → f5 ChartReferences keys
key_map = {
    "chart_scales_ctrs_sentiment": "scales_ctrs_sentiment",
    "chart_ctrs_zoom": "ctrs_zoom",
    "chart_disease_similarity": "disease_similarity",
    "chart_domain_confidence": "domain_confidence",
}
f5_chart_paths = {key_map[k]: p for k, p in chart_paths.items() if k in key_map}

# 2) Assemble the handoff report input.
session = SessionSnapshot(
    session_id=f"f1_{VP}", persona_id=VP, persona_name="김데모", session_index=6,
    simulated_date=DATES[-1], model="solar-pro3-260323",
    final_slots={"chief_complaint": "우울감과 수면 문제가 호전 중",
                 "history_of_present_illness": "3개월간 약물치료 후 점진 개선",
                 "risk_assessment": "현재 자살/자해 사고 부인"},
    session_ctrs=5, crisis_triggered=False, crisis_turn=None, risk_floor=4, probe_event_count=0,
)
report = assemble_handoff_report(HandoffReportInput(
    vp_id=VP,
    session=session,
    current_session_f3=F3Administration(
        session_index=6, simulated_date=DATES[-1], outcome="administered",
        scale_name="PHQ-9", item_bank_version="v1",
        item_bank_provenance="v1, verbatim Pfizer PHQ-9",
        responses=(1, 1, 0, 1, 1, 0, 1, 0, 1),
        total_score=6, max_score=27, severity="mild", critical_item_positive=False,
        safety_referral=False),
    all_f3_administrations=(),
    domain_inference=DomainInferenceSnapshot(
        ai_predicted_disease=AIPredictedDiseaseOutput(
            candidates=[AIPredictedDiseaseCandidate(
                disease="주요우울장애", similarity_score=0.65,
                source_id="case_card:2001", quote="q")],
            mode="rag_live", recommended_questionnaire="PHQ-9"),
        department_candidates=(DepartmentCandidateInput(
            department="정신건강의학과", reason="우울·수면·음주 복합", domain_ref="mood"),)),
    longitudinal=longitudinal,
    chart_filenames=ChartFilenames(
        scales_ctrs_sentiment=chart_paths["chart_scales_ctrs_sentiment"].name,
        ctrs_zoom=chart_paths.get("chart_ctrs_zoom", Path("")).name or None,
        disease_similarity=chart_paths.get("chart_disease_similarity", Path("")).name or None,
        domain_confidence=chart_paths.get("chart_domain_confidence", Path("")).name or None,
    ),
))

# 3) Build the actual handoff artifacts.
md = build_markdown_report(report)
(OUT / f"{VP}_handoff.md").write_text(md, encoding="utf-8")
pdf = build_pdf_report(report, f5_chart_paths)
(OUT / f"{VP}_handoff.pdf").write_bytes(pdf)
print(f"handoff MD chars={len(md)}  PDF bytes={len(pdf)}  →  {OUT}")
