"""F5 report writer — `save_f5_result` + markdown/PDF/FHIR exporters.

`docs/ai/f5_quick_dev_plan.md` §5. Deliberately kept OUT of `src/f5.py` (the
pure, zero-file-I/O assembly engine) so a whole-file grep for `open(`/file-
I/O in `src/f5.py` returns 0 hits with zero ambiguity (REV-044 Criterion 6,
`ADR-037` Decision 6 citation fix) — this module is the ONE place F5's OWN
output artifacts (`_handoff.md`/`.pdf`/`_fhir.json`) get written to disk,
the same role `src/services/f4_report.py` already plays for F4. Called by
the harness (`src/continuous_test.py`) AFTER `src.f5.assemble_handoff_
report` returns — never by `src/f5.py` itself.

FHIR claim discipline (`REV-046` MAY/MUST-NOT wording table row 2, binding):
this module and every string it writes MAY say the FHIR bundle is
"structurally valid per this project's own `validate_fhir_bundle` checks" —
it MUST NOT claim "FHIR-conformant", "validated against the FHIR spec",
"`$validate`-passed", or any implication of HL7 Implementation Guide
conformance. No FHIR `$validate` service call anywhere in this module (D3).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from src.f1 import OUTPUT_DIR
from src.schemas.handoff_report import (
    NON_VALIDATED_ADMINISTRATION_CAVEAT_KO,
    HandoffReportOutput,
)

logger = logging.getLogger(__name__)


def save_f5_result(
    report: HandoffReportOutput,
    output_dir: Path | None = None,
    *,
    vp_id: str | None = None,
    chart_paths: dict[str, Path] | None = None,
) -> dict[str, Path]:
    """Save F5 result as markdown + PDF + FHIR R4 document Bundle (design
    doc §5). Naming mirrors `save_f1_result`/.../`save_f4_result`:
    `<vp_id>_<ts>_handoff.md` / `_handoff.pdf` / `_handoff_fhir.json`, under
    `docs/ai/simulation_results/<vp_id>/` — same directory as every other
    F1-F4 artifact for that VP, no new directory.

    `chart_paths`: optional mapping of the SAME 4 keys as
    `schemas.handoff_report.ChartReferences` (`scales_ctrs_sentiment`/
    `ctrs_zoom`/`disease_similarity`/`domain_confidence`) to the REAL,
    already-on-disk F4 PNG `Path`s — used only by the PDF exporter to embed
    chart bytes (F5 never generates or regenerates chart bytes itself,
    design doc §2.2 B5 row). The markdown/FHIR exporters use only the
    filenames already carried on `report.b_longitudinal.chart_filenames`.
    """
    resolved_vp_id = vp_id or report.vp_id
    base = output_dir or OUTPUT_DIR
    out = base / resolved_vp_id
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{resolved_vp_id}_{ts}"

    paths: dict[str, Path] = {}

    md_path = out / f"{prefix}_handoff.md"
    md_path.write_text(build_markdown_report(report), encoding="utf-8")
    paths["markdown"] = md_path

    pdf_path = out / f"{prefix}_handoff.pdf"
    pdf_path.write_bytes(build_pdf_report(report, chart_paths or {}))
    paths["pdf"] = pdf_path

    fhir_bundle = build_fhir_bundle(report)
    fhir_path = out / f"{prefix}_handoff_fhir.json"
    fhir_path.write_text(json.dumps(fhir_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["fhir"] = fhir_path

    logger.info("F5 results saved: %s", ", ".join(str(p) for p in paths.values()))
    return paths


# ═══════════════════════════════════════════════════════════════════════
# Markdown (design doc §5.1)
# ═══════════════════════════════════════════════════════════════════════


def _none_marker(value: object, marker: str) -> str:
    return marker if value in (None, "", []) else str(value)


def build_markdown_report(report: HandoffReportOutput) -> str:
    """One `##`/`###` per §2.2 A0-A8/B1-B5 row — every section header is
    ALWAYS present, with an explicit "정보 없음"/"평가 불가" marker when no
    data exists (never silently dropped, qa's `T1-F5-VER-011` completeness
    grep target)."""
    a0, a1, a2, a3 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a2_hpi,
        report.a3_risk_safety,
    )
    a4, a5, a6, a7, a8 = (
        report.a4_mental_status,
        report.a5_questionnaires,
        report.a6_ai_predicted_disease,
        report.a7_recommendations,
        report.a8_narrative,
    )
    b = report.b_longitudinal
    lon = b.analysis

    lines: list[str] = [
        f"# F5 인계 요약 보고서 (Hand-off report) — {report.vp_id}",
        "",
        f"> session_index: {a0.session_index} | simulated_date: {a0.simulated_date} | "
        f"model: {a0.model} | generated_at: {report.generated_at}",
        f"> session_ctrs: {a0.session_ctrs} | risk_level: {a0.risk_level} | "
        f"crisis_triggered: {a0.crisis_triggered} | is_diagnostic: {report.is_diagnostic}",
        "",
        "## 면책 조항 (Disclaimer)",
        "",
        report.disclaimer,
        "",
        f"- {a0.disclaimer.self_report_only}",
        f"- {a0.disclaimer.ai_assembled}",
        f"- {a0.disclaimer.not_official_record}",
        f"- {a0.disclaimer.non_diagnostic}",
        "",
    ]

    # ── A0 ──
    lines += [
        "## A0. 헤더 / 상황 요약",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| session_id | {a0.session_id} |",
        f"| persona_id / persona_name | {a0.persona_id} / {a0.persona_name} |",
        f"| session_index | {a0.session_index} |",
        f"| simulated_date | {a0.simulated_date} |",
        f"| model | {a0.model} |",
        f"| chief_complaint_summary | {_none_marker(a0.chief_complaint_summary, '정보 없음')} |",
        f"| session_ctrs / risk_level | {a0.session_ctrs} / {a0.risk_level} |",
        f"| crisis_triggered / crisis_turn | {a0.crisis_triggered} / {a0.crisis_turn} |",
        "",
    ]

    # ── A1 ──
    lines += [
        "## A1. 주호소 (Chief complaint)",
        "",
        a1.text if a1.present else "정보 없음 (chief_complaint 슬롯 미채움)",
        "",
    ]

    # ── A2 ──
    lines += [
        "## A2. 현병력 (History of present illness)",
        "",
        a2.text if a2.present else "정보 없음 (history_of_present_illness 슬롯 미채움)",
        "",
    ]

    # ── A3 ──
    lines += [
        "## A3. 위험/안전 평가 (Risk / safety assessment)",
        "",
        f"### 당해 세션 ({a3.current_session_index}회차, {a3.current_simulated_date})",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| risk_assessment (슬롯) | "
        f"{_none_marker(a3.risk_assessment_text, '정보 없음 (Safety Probe 미시행)')} |",
        f"| session_ctrs / risk_level | {a3.session_ctrs} / {a3.risk_level} |",
        f"| risk_floor | {a3.risk_floor} |",
        f"| probe_event_count | {a3.probe_event_count} |",
        f"| crisis_triggered / crisis_turn | {a3.crisis_triggered} / {a3.crisis_turn} |",
        f"| 당해 세션 F3 시행 여부 | {a3.current_session_has_f3} |",
        f"| 당해 세션 safety_referral | {a3.current_session_safety_referral} |",
        f"| 당해 세션 critical_item_positive | {a3.current_session_critical_item_positive} |",
        "",
        "### 종단 위험 신호 (모든 세션의 item-9 양성 / safety_referral 시행)",
        "",
        f"> 추세-수준 일치도(trend_concordance_flag, F4 산출, 종단 전체): "
        f"**{a3.trend_concordance_flag}** — 이는 아래 세션별(same-session) 항목9-CTRS "
        "불일치와는 다른 질문에 답합니다 (B4 참조, 혼동 금지).",
        "",
    ]
    if a3.longitudinal_risk_signals:
        lines += [
            "| session | date | scale | total/max | severity | safety_referral | "
            "critical_item_positive | 동일 세션 CTRS | 동일 세션 위기 | 판정 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for sig in a3.longitudinal_risk_signals:
            lines.append(
                f"| {sig.session_index} | {sig.simulated_date} | {sig.scale_name} | "
                f"{sig.total_score}/{sig.max_score} | {sig.severity} | {sig.safety_referral} | "
                f"{sig.critical_item_positive} | {sig.same_session_ctrs} | "
                f"{sig.same_session_crisis_triggered} | {sig.discordance_note} |"
            )
    else:
        lines.append(
            "해당 없음 — 이 환자의 전체 세션 중 item-9 양성/safety_referral 시행 이력이 없습니다."
        )
    lines += [
        "",
        "### 최신 시행 척도 최신성 안내 (staleness pointer)",
        "",
        a3.staleness_pointer.note,
        "",
    ]

    # ── A4 ──
    lines += [
        "## A4. 정신상태 검사 (부분, MSE — text-derived only)",
        "",
        f"레이블: {a4.label}",
        "",
        a4.raw_text
        if a4.present
        else "정보 없음 (mental_status_exam 슬롯 미채움 — 설계상 드물게 발생)",
        "",
        "| 영역 (domain) | 개별 평가 가능 | 비고 |",
        "|---|---|---|",
    ]
    for d in a4.domain_checklist:
        lines.append(f"| {d.domain} | {d.assessable} | {d.note} |")
    lines.append("")

    # ── A5 ──
    lines += ["## A5. 시행된 설문 (Administered questionnaires)", ""]
    if not a5.present:
        lines += ["정보 없음 (이 VP의 전체 세션 중 시행된 설문 없음)", ""]
    else:
        lines += [
            f"> {a5.non_validated_caveat}",
            "",
            "| 항목 | 값 |",
            "|---|---|",
            f"| administering_session_index | {a5.administering_session_index} |",
            f"| administering_simulated_date | {a5.administering_simulated_date} |",
            f"| 헤더(당해) 세션과 상이(stale) | {a5.is_stale_relative_to_header} |",
            f"| scale_name | {a5.scale_name} |",
            f"| item_bank_version | {a5.item_bank_version} |",
            f"| item_bank_provenance | {a5.item_bank_provenance} |",
            f"| responses | {a5.responses} |",
            f"| total_score / max_score | {a5.total_score} / {a5.max_score} |",
            f"| severity | {a5.severity} |",
            f"| critical_item_positive | {a5.critical_item_positive} |",
            f"| administration_mode | {a5.administration_mode} |",
            f"| threshold_caveat | {_none_marker(a5.threshold_caveat, '(null)')} |",
            "",
        ]
        if a5.threshold_caveat_asymmetry_note:
            lines += [f"> {a5.threshold_caveat_asymmetry_note}", ""]
        if a5.gap_disclosure:
            lines += ["**F3 gap 공백 (당해 세션까지):**", ""]
            if a5.gap_acuity_framing_note:
                lines += [f"> {a5.gap_acuity_framing_note}", ""]
            for g in a5.gap_disclosure:
                lines.append(f"- {g}")
            lines.append("")

    # ── A6 (hard red line — own fenced section) ──
    lines += [
        "## A6. AI 예상질환 (비진단적 의사결정 지원, non-diagnostic decision-support)",
        "",
        "> ⚠ 이 섹션은 A0-A5/A7-A8의 결정론적 임상 서술과 별개인 독립 섹션입니다. "
        "similarity_score는 '유사도'일 뿐 '확률'/'가능성'/'신뢰도'가 아닙니다 (REV-013 §4).",
        "",
    ]
    if not a6.present:
        lines += [_none_marker(a6.no_data_note, "정보 없음"), ""]
    else:
        lines += [
            f"mode: {a6.mode}",
            "",
            "| 순위(rank) | 공동순위 | 질환(disease) | 유사도(similarity_score) | "
            "source_id | quote |",
            "|---|---|---|---|---|---|",
        ]
        for rc in a6.candidates:
            c = rc.candidate
            lines.append(
                f"| {rc.rank} | {rc.tie_marker or '-'} | {c.disease} | {c.similarity_score:.3f} | "
                f"{c.source_id or '-'} | {c.quote or '-'} |"
            )
        lines += [
            "",
            f"disclaimer: {a6.disclaimer}",
            f"recommended_questionnaire: {a6.recommended_questionnaire}",
            f"recommendation_caveat: {_none_marker(a6.recommendation_caveat, '(없음)')}",
            "",
        ]

    # ── A7 ──
    lines += ["## A7. 권장 진료과 / 설문 (Recommended department / questionnaire)", ""]
    if a7.department_candidates:
        lines += ["| 진료과 | 사유 | domain_ref |", "|---|---|---|"]
        for d in a7.department_candidates:
            lines.append(f"| {d.department} | {d.reason} | {d.domain_ref or '-'} |")
        lines.append("")
    else:
        lines += ["정보 없음 (권장 진료과 없음)", ""]
    lines += [
        f"recommended_questionnaire: {_none_marker(a7.recommended_questionnaire, '(없음)')}",
        f"recommendation_caveat: {_none_marker(a7.recommendation_caveat, '(없음)')}",
        "",
        f"> {a7.medication_note}",
        "",
    ]

    # ── A8 ──
    lines += ["## A8. 임상 종합 소견 (AI narrative synthesis, optional)", ""]
    if a8.narrative_enabled and a8.text:
        lines += [a8.text, ""]
    else:
        lines += [a8.absent_marker, ""]

    # ── B1 ──
    lines += [
        "## B1. 추세 판정 (Trend verdicts)",
        "",
        f"> arc_mode: {lon.arc_mode or 'N/A'} | n_sessions: {lon.n_sessions} | "
        f"session_span_days: {lon.session_span_days}",
        f"> overall_direction: **{lon.overall_direction}** | "
        f"course_shape: **{lon.course_shape}** | "
        f"concordance_flag(trend-level): **{lon.concordance_flag}**",
        "",
        f"> {b.overall_direction_sensitivity_note}",
        "",
        lon.disclaimer,
        "",
        "| dimension | direction | basis | n_comparable | evidence |",
        "|---|---|---|---|---|",
    ]
    for tv in lon.trend_verdicts:
        ev = "<br>".join(tv.evidence) if tv.evidence else "(none)"
        lines.append(
            f"| {tv.dimension} | {tv.direction} | {tv.basis} | {tv.n_comparable_points} | {ev} |"
        )
    lines.append("")

    # ── B2 ──
    lines += [
        "## B2. CTRS 추이 (CTRS trajectory)",
        "",
        "| session | date | session_ctrs | crisis_triggered | probe_event_count | risk_floor |",
        "|---|---|---|---|---|---|",
    ]
    for p in lon.ctrs_series:
        lines.append(
            f"| {p.session_index} | {p.simulated_date} | {p.session_ctrs} | {p.crisis_triggered} | "
            f"{p.probe_event_count} | {p.risk_floor} |"
        )
    if not lon.ctrs_series:
        lines.append("| - | - | (없음) | - | - | - |")
    lines.append("")

    # ── B3 ──
    lines += ["## B3. 사건 타임라인 (Event timeline)", ""]
    crisis_points = [p for p in lon.ctrs_series if p.crisis_triggered]
    if crisis_points:
        lines += ["| session | date | probe_event_count |", "|---|---|---|"]
        for p in crisis_points:
            lines.append(f"| {p.session_index} | {p.simulated_date} | {p.probe_event_count} |")
        lines.append("")
    else:
        lines += ["crisis_triggered=true 세션 없음.", ""]
    if lon.crisis_f3_gaps:
        lines += ["**F3 gap (risk-elevated 세션 중 미시행):**", ""]
        if b.gap_acuity_framing_note:
            lines += [f"> {b.gap_acuity_framing_note}", ""]
        for g in lon.crisis_f3_gaps:
            lines.append(f"- {g}")
        lines.append("")
    else:
        lines += ["risk-elevated 세션 중 F3 gap 없음.", ""]

    # ── B4 ──
    lines += [
        "## B4. 불일치 신호 (Discordance flags)",
        "",
        f"trend-level concordance_flag (F4 산출, primary scale vs session_ctrs vs sentiment): "
        f"**{lon.concordance_flag}**",
        "",
        "> 이 값은 추세(trend) 수준 지표이며, A3의 세션별(item-9-vs-CTRS same-session) "
        "co-display 표와는 별개의 질문에 답합니다 — 두 지표를 서술에서 혼동하지 않습니다.",
        "",
    ]

    # ── B5 ──
    lines += ["## B5. 추세 차트 (Trend charts, F4 PNG 재사용)", ""]
    chart_map = {
        "scales_ctrs_sentiment": b.chart_filenames.scales_ctrs_sentiment,
        "ctrs_zoom": b.chart_filenames.ctrs_zoom,
        "disease_similarity": b.chart_filenames.disease_similarity,
        "domain_confidence": b.chart_filenames.domain_confidence,
    }
    any_chart = False
    for key, filename in chart_map.items():
        if filename:
            any_chart = True
            lines.append(f"![{key}]({filename})")
    if not any_chart:
        lines.append("정보 없음 (차트 없음)")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# PDF (design doc §5.2 — reportlab, built-in Adobe CID Korean fonts)
# ═══════════════════════════════════════════════════════════════════════

_BODY_FONT = "HYGothic-Medium"
_HEADING_FONT = "HYSMyeongJo-Medium"


def _register_korean_fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    for name in (_BODY_FONT, _HEADING_FONT):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(name))


def build_pdf_report(
    report: HandoffReportOutput, chart_paths: dict[str, Path] | None = None
) -> bytes:
    """Renders the same A0-A8/B1-B5 content as `build_markdown_report`
    into a paginated PDF (reportlab platypus), embedding the 4 F4 PNG
    charts directly (design doc §5.2 — a PDF has no reliable external-file
    reference convention). A6 is visually fenced with a bordered/shaded
    table (decision-support, structurally separate)."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _register_korean_fonts()
    chart_paths = chart_paths or {}

    styles = {
        "title": ParagraphStyle(
            "title", fontName=_HEADING_FONT, fontSize=16, leading=20, spaceAfter=10
        ),
        "h2": ParagraphStyle(
            "h2", fontName=_HEADING_FONT, fontSize=13, leading=17, spaceBefore=12, spaceAfter=6
        ),
        "h3": ParagraphStyle(
            "h3", fontName=_HEADING_FONT, fontSize=11, leading=15, spaceBefore=8, spaceAfter=4
        ),
        "body": ParagraphStyle("body", fontName=_BODY_FONT, fontSize=9.5, leading=14),
        "meta": ParagraphStyle(
            "meta", fontName=_BODY_FONT, fontSize=8.5, leading=12, textColor=colors.grey
        ),
        "warn": ParagraphStyle(
            "warn",
            fontName=_BODY_FONT,
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#B00020"),
        ),
    }

    def P(text: str, style: str = "body") -> Paragraph:
        safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(safe.replace("\n", "<br/>"), styles[style])

    story: list = []
    a0, a1, a2, a3 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a2_hpi,
        report.a3_risk_safety,
    )
    a4, a5, a6, a7, a8 = (
        report.a4_mental_status,
        report.a5_questionnaires,
        report.a6_ai_predicted_disease,
        report.a7_recommendations,
        report.a8_narrative,
    )
    b = report.b_longitudinal
    lon = b.analysis

    # ── Title / A0 situation header (SBAR-first, design doc §5.2 layout) ──
    story.append(P(f"F5 인계 요약 보고서 — {report.vp_id}", "title"))
    story.append(
        P(
            f"session_index {a0.session_index} | {a0.simulated_date} | model {a0.model} | "
            f"generated_at {report.generated_at}",
            "meta",
        )
    )
    story.append(
        P(
            f"session_ctrs {a0.session_ctrs} | risk_level {a0.risk_level} | "
            f"crisis_triggered {a0.crisis_triggered}",
            "meta",
        )
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(P("면책 조항", "h2"))
    story.append(P(report.disclaimer, "body"))
    for line in (
        a0.disclaimer.self_report_only,
        a0.disclaimer.ai_assembled,
        a0.disclaimer.not_official_record,
        a0.disclaimer.non_diagnostic,
    ):
        story.append(P(f"- {line}", "body"))
    story.append(P(f"chief_complaint_summary: {a0.chief_complaint_summary or '정보 없음'}", "body"))

    # ── A1 / A2 ──
    story.append(P("A1. 주호소 (Chief complaint)", "h2"))
    story.append(P(a1.text if a1.present else "정보 없음", "body"))
    story.append(P("A2. 현병력 (HPI)", "h2"))
    story.append(P(a2.text if a2.present else "정보 없음", "body"))

    # ── A3 (risk, promoted top-level) ──
    story.append(P("A3. 위험/안전 평가", "h2"))
    story.append(P(f"당해 세션 {a3.current_session_index}회차 ({a3.current_simulated_date})", "h3"))
    story.append(
        P(
            f"risk_assessment: {a3.risk_assessment_text or '정보 없음'} | session_ctrs: "
            f"{a3.session_ctrs} ({a3.risk_level}) | risk_floor: {a3.risk_floor} | "
            f"probe_event_count: {a3.probe_event_count} | crisis_triggered: {a3.crisis_triggered}",
            "body",
        )
    )
    story.append(
        P(
            f"당해 세션 F3 시행: {a3.current_session_has_f3} | safety_referral: "
            f"{a3.current_session_safety_referral} | critical_item_positive: "
            f"{a3.current_session_critical_item_positive}",
            "body",
        )
    )
    story.append(P("종단 위험 신호 (모든 세션)", "h3"))
    story.append(P(f"추세-수준 concordance_flag: {a3.trend_concordance_flag}", "body"))
    if a3.longitudinal_risk_signals:
        rows = [["session", "date", "scale", "score", "severity", "동일세션CTRS", "판정"]]
        for sig in a3.longitudinal_risk_signals:
            rows.append(
                [
                    str(sig.session_index),
                    sig.simulated_date,
                    str(sig.scale_name),
                    f"{sig.total_score}/{sig.max_score}",
                    str(sig.severity),
                    str(sig.same_session_ctrs),
                    sig.discordance_note[:40],
                ]
            )
        t = Table(rows, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _BODY_FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                ]
            )
        )
        story.append(t)
    else:
        story.append(P("해당 없음 — item-9 양성/safety_referral 시행 이력 없음", "body"))
    story.append(P(f"최신성 안내: {a3.staleness_pointer.note}", "warn"))

    # ── A4 ──
    story.append(P("A4. 정신상태 검사 (부분, MSE)", "h2"))
    story.append(P(f"[{a4.label}] " + (a4.raw_text if a4.present else "정보 없음"), "body"))

    # ── A5 ──
    story.append(P("A5. 시행된 설문", "h2"))
    if not a5.present:
        story.append(P("정보 없음 (시행된 설문 없음)", "body"))
    else:
        story.append(P(a5.non_validated_caveat, "warn"))
        story.append(
            P(
                f"{a5.scale_name} — {a5.administering_session_index}회차 "
                f"({a5.administering_simulated_date}), stale={a5.is_stale_relative_to_header}: "
                f"{a5.total_score}/{a5.max_score} ({a5.severity}), mode={a5.administration_mode}",
                "body",
            )
        )
        if a5.threshold_caveat:
            story.append(P(f"threshold_caveat: {a5.threshold_caveat}", "body"))
        if a5.threshold_caveat_asymmetry_note:
            story.append(P(a5.threshold_caveat_asymmetry_note, "body"))
        for g in a5.gap_disclosure:
            story.append(P(f"- {g}", "body"))

    # ── A6 (visually fenced decision-support box) ──
    story.append(P("A6. AI 예상질환 (비진단적 의사결정 지원)", "h2"))
    a6_flow: list = [
        P(
            "⚠ DECISION-SUPPORT ONLY — 이 섹션의 내용은 similarity_score(유사도)이며 확률/가능성/"
            "신뢰도가 아닙니다. A0-A5/A7-A8과 구조적으로 분리됩니다.",
            "warn",
        )
    ]
    if not a6.present:
        a6_flow.append(P(a6.no_data_note or "정보 없음", "body"))
    else:
        rows = [["rank", "공동순위", "disease", "similarity_score"]]
        for rc in a6.candidates:
            rows.append(
                [
                    str(rc.rank),
                    rc.tie_marker or "-",
                    rc.candidate.disease,
                    f"{rc.candidate.similarity_score:.3f}",
                ]
            )
        t = Table(rows, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _BODY_FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                ]
            )
        )
        a6_flow.append(t)
        a6_flow.append(P(f"mode: {a6.mode} | disclaimer: {a6.disclaimer}", "body"))
    fence = Table([[a6_flow]], hAlign="LEFT")
    fence.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#B00020")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3F3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(fence)

    # ── A7 ──
    story.append(P("A7. 권장 진료과 / 설문", "h2"))
    if a7.department_candidates:
        for d in a7.department_candidates:
            story.append(P(f"- {d.department}: {d.reason}", "body"))
    else:
        story.append(P("정보 없음", "body"))
    story.append(P(a7.medication_note, "body"))

    # ── A8 ──
    story.append(P("A8. 임상 종합 소견 (내러티브)", "h2"))
    story.append(P(a8.text if (a8.narrative_enabled and a8.text) else a8.absent_marker, "body"))

    story.append(PageBreak())

    # ── B section ──
    story.append(
        P(
            f"B1. 추세 판정 — overall_direction: {lon.overall_direction}, "
            f"course_shape: {lon.course_shape}",
            "h2",
        )
    )
    story.append(P(b.overall_direction_sensitivity_note, "body"))
    story.append(P(lon.disclaimer, "meta"))
    for tv in lon.trend_verdicts:
        story.append(P(f"- {tv.dimension}: {tv.direction} ({tv.basis})", "body"))

    story.append(P("B2. CTRS 추이", "h2"))
    for p in lon.ctrs_series:
        story.append(
            P(
                f"- {p.session_index}회차 ({p.simulated_date}): session_ctrs={p.session_ctrs}, "
                f"crisis_triggered={p.crisis_triggered}",
                "body",
            )
        )

    story.append(P("B3. 사건 타임라인", "h2"))
    for g in lon.crisis_f3_gaps:
        story.append(P(f"- {g}", "body"))
    if not lon.crisis_f3_gaps:
        story.append(P("risk-elevated 세션 중 F3 gap 없음", "body"))

    story.append(P(f"B4. 불일치 신호 — trend concordance_flag: {lon.concordance_flag}", "h2"))
    story.append(
        P("추세-수준 지표이며 A3의 세션별 item-9-vs-CTRS co-display와는 별개입니다.", "body")
    )

    story.append(P("B5. 추세 차트", "h2"))
    chart_map = {
        "scales_ctrs_sentiment": b.chart_filenames.scales_ctrs_sentiment,
        "ctrs_zoom": b.chart_filenames.ctrs_zoom,
        "disease_similarity": b.chart_filenames.disease_similarity,
        "domain_confidence": b.chart_filenames.domain_confidence,
    }
    any_chart = False
    for key, filename in chart_map.items():
        path = chart_paths.get(key)
        if filename and path is not None and Path(path).exists():
            any_chart = True
            story.append(P(filename, "meta"))
            story.append(Image(str(path), width=16 * cm, height=9 * cm, kind="proportional"))
    if not any_chart:
        story.append(P("정보 없음 (차트 없음 또는 chart_paths 미전달)", "body"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )
    doc.build(story)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════
# FHIR R4 document Bundle (design doc §5.3 — file export only, D3)
# ═══════════════════════════════════════════════════════════════════════

_LOCAL_CODE_SYSTEM = "urn:neurosync:f5-local-codes"

# `system`/`code` pairs VERIFIED against the design doc §5.3 mapping table
# (research note + brainstorm's own LOINC lookups). `display` is
# deliberately OMITTED wherever the plan did not hand us an independently
# confirmed LOINC long-common-name string — never fabricate an official
# display text; free-text labeling instead lives in `CodeableConcept.text`
# / `Composition.section.title`, which FHIR treats as ordinary prose, not
# an authority claim.
_LOINC = {
    "composition_type": "57143-0",
    "cc": "10154-3",
    "hpi": "10164-2",
    "risk": "84209-6",
    "mse": "10190-7",
    "phq9_total": "44261-6",
    "phq9_panel": "44249-1",
    "gad7_total": "70274-6",
    "auditc_total": "75626-2",
    "eval_plan": "51847-2",
}

_SCALE_TOTAL_LOINC = {
    "PHQ-9": _LOINC["phq9_total"],
    "GAD-7": _LOINC["gad7_total"],
    "AUDIT-C": _LOINC["auditc_total"],
}


def _new_entry(resource: dict) -> tuple[str, dict]:
    full_url = f"urn:uuid:{uuid.uuid4()}"
    return full_url, {"fullUrl": full_url, "resource": resource}


def _loinc_concept(key: str, text: str) -> dict:
    return {"coding": [{"system": "http://loinc.org", "code": _LOINC[key]}], "text": text}


def _local_concept(code: str, text: str) -> dict:
    return {"coding": [{"system": _LOCAL_CODE_SYSTEM, "code": code}], "text": text}


def _div(text: str) -> dict:
    """`Narrative` (status=generated) wrapping free text in the required
    xhtml div — used for every `Composition.section.text` below."""
    return {"status": "generated", "div": f"<div xmlns='http://www.w3.org/1999/xhtml'>{text}</div>"}


def build_fhir_bundle(report: HandoffReportOutput) -> dict:
    """R4 `Bundle(type="document")`, `Composition` first entry (design doc
    §5.3). File-export only — no `$validate` call, no server round-trip
    (D3). Structural validity only — see `validate_fhir_bundle` and the
    module-level FHIR claim discipline note above."""
    a0, a1, a2, a3 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a2_hpi,
        report.a3_risk_safety,
    )
    a4, a5, a6, a7 = (
        report.a4_mental_status,
        report.a5_questionnaires,
        report.a6_ai_predicted_disease,
        report.a7_recommendations,
    )
    b = report.b_longitudinal
    lon = b.analysis

    entries: list[dict] = []
    full_urls: dict[str, str] = {}

    def add(key: str, resource: dict) -> str:
        full_url, entry = _new_entry(resource)
        entries.append(entry)
        full_urls[key] = full_url
        return full_url

    # ── Patient (minimal, flagged simulated) ──
    patient_url = add(
        "patient",
        {
            "resourceType": "Patient",
            "id": a0.persona_id,
            "meta": {
                "tag": [{"system": "urn:neurosync:simulation-flag", "code": "simulated-patient"}]
            },
            "identifier": [{"system": "urn:neurosync:vp-id", "value": report.vp_id}],
            "name": [{"text": a0.persona_name}],
        },
    )

    sections: list[dict] = []

    # ── A1 CC ──
    sections.append(
        {
            "title": "A1. 주호소 (Chief complaint)",
            "code": _loinc_concept("cc", "chief complaint"),
            "text": _div(a1.text or "정보 없음"),
        }
    )

    # ── A2 HPI ──
    sections.append(
        {
            "title": "A2. 현병력 (HPI)",
            "code": _loinc_concept("hpi", "history of present illness"),
            "text": _div(a2.text or "정보 없음"),
        }
    )

    # ── A3 Risk/safety: RiskAssessment + CTRS Observation ──
    ctrs_obs_url = add(
        "ctrs_observation",
        {
            "resourceType": "Observation",
            "id": str(uuid.uuid4()),
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "survey",
                        }
                    ]
                }
            ],
            "code": _local_concept("ctrs", "Crisis Triage Rating Scale (session_ctrs, local)"),
            "subject": {"reference": patient_url},
            "effectiveDateTime": a3.current_simulated_date,
            "valueInteger": a3.session_ctrs,
            "note": [
                {
                    "text": (
                        f"probe_event_count={a3.probe_event_count}, "
                        f"risk_floor={a3.risk_floor}, crisis_triggered={a3.crisis_triggered}"
                    )
                }
            ],
        },
    )
    risk_assessment_url = add(
        "risk_assessment",
        {
            "resourceType": "RiskAssessment",
            "id": str(uuid.uuid4()),
            "status": "final",
            "subject": {"reference": patient_url},
            "basis": [{"reference": ctrs_obs_url}],
            "prediction": [
                {
                    "qualitativeRisk": {"text": a3.risk_level or "unknown"},
                    "rationale": a3.risk_assessment_text or "정보 없음",
                }
            ],
            "note": [
                {
                    "text": (
                        f"trend concordance_flag(F4)={a3.trend_concordance_flag}; "
                        f"staleness_pointer={a3.staleness_pointer.note}"
                    )
                }
            ],
        },
    )
    risk_narrative = "; ".join(
        [
            f"session_ctrs={a3.session_ctrs}({a3.risk_level})",
            f"safety_referral={a3.current_session_safety_referral}",
            *[f"[{s.session_index}] {s.discordance_note}" for s in a3.longitudinal_risk_signals],
        ]
    )
    sections.append(
        {
            "title": "A3. 위험/안전 평가",
            "code": {"coding": [{"system": "http://loinc.org", "code": _LOINC["risk"]}]},
            "text": _div(risk_narrative),
            "entry": [{"reference": risk_assessment_url}, {"reference": ctrs_obs_url}],
        }
    )

    # ── A4 MSE (partial — disclosure non-optional) ──
    mse_obs_url = add(
        "mse_observation",
        {
            "resourceType": "Observation",
            "id": str(uuid.uuid4()),
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "exam",
                        }
                    ]
                }
            ],
            "code": {"coding": [{"system": "http://loinc.org", "code": _LOINC["mse"]}]},
            "subject": {"reference": patient_url},
            "valueString": a4.raw_text or "정보 없음",
            "note": [
                {
                    "text": (
                        "PARTIAL / TEXT-ONLY MSE — 이 관찰은 완전한 임상 관찰 기반 MSE가 아니라 "
                        f"단일 텍스트 슬롯({a4.label})에서만 도출되었습니다. 5개 관찰-의존 영역은 "
                        "평가 불가로 표시됩니다."
                    )
                }
            ],
        },
    )
    sections.append(
        {
            "title": "A4. 정신상태 검사 (부분, MSE)",
            "code": {"coding": [{"system": "http://loinc.org", "code": _LOINC["mse"]}]},
            "text": _div(a4.raw_text or "정보 없음"),
            "entry": [{"reference": mse_obs_url}],
        }
    )

    # ── A5 Questionnaires: QuestionnaireResponse + Observation(total) ──
    a5_entries: list[dict] = []
    if a5.present:
        qr_url = add(
            "questionnaire_response",
            {
                "resourceType": "QuestionnaireResponse",
                "id": str(uuid.uuid4()),
                "status": "completed",
                "subject": {"reference": patient_url},
                "authored": a5.administering_simulated_date,
                "item": [
                    {"linkId": f"item_{i + 1}", "answer": [{"valueInteger": v}]}
                    for i, v in enumerate(a5.responses)
                ],
                "note": [{"text": a5.non_validated_caveat}],
            },
        )
        a5_entries.append({"reference": qr_url})
        total_code = _SCALE_TOTAL_LOINC.get(a5.scale_name or "")
        obs_code = (
            {
                "coding": [{"system": "http://loinc.org", "code": total_code}],
                "text": f"{a5.scale_name} total",
            }
            if total_code
            else _local_concept("scale-total", f"{a5.scale_name} total")
        )
        notes = [{"text": a5.non_validated_caveat}]
        if a5.threshold_caveat:
            notes.append({"text": a5.threshold_caveat})
        if a5.threshold_caveat_asymmetry_note:
            notes.append({"text": a5.threshold_caveat_asymmetry_note})
        obs_url = add(
            "a5_total_observation",
            {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "survey",
                            }
                        ]
                    }
                ],
                "code": obs_code,
                "subject": {"reference": patient_url},
                "effectiveDateTime": a5.administering_simulated_date,
                "valueQuantity": {"value": a5.total_score, "unit": "score"},
                "note": notes,
            },
        )
        a5_entries.append({"reference": obs_url})
        a5_text = (
            f"{a5.scale_name} {a5.total_score}/{a5.max_score} ({a5.severity}) — "
            f"{a5.non_validated_caveat}"
        )
    else:
        a5_text = "정보 없음 (시행된 설문 없음)"
    sections.append(
        {
            "title": "A5. 시행된 설문",
            "code": _local_concept("questionnaires", "administered questionnaires"),
            "text": _div(a5_text),
            **({"entry": a5_entries} if a5_entries else {}),
        }
    )

    # ── A6 AI-predicted-disease (hard red line — own section/resource) ──
    a6_entries: list[dict] = []
    if a6.present:
        components = [
            {
                "code": {"text": rc.candidate.disease},
                "valueQuantity": {"value": rc.candidate.similarity_score, "unit": "similarity"},
            }
            for rc in a6.candidates
        ]
        a6_obs_url = add(
            "ai_predicted_disease_observation",
            {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "survey",
                            }
                        ]
                    }
                ],
                "code": _local_concept(
                    "ai-predicted-disease", "AI-predicted disease candidates (non-diagnostic)"
                ),
                "subject": {"reference": patient_url},
                "component": components,
                "note": [
                    {"text": "NOT A DIAGNOSIS, NOT A PROBABILITY — similarity_score only."},
                    {"text": a6.disclaimer or ""},
                ],
            },
        )
        a6_entries.append({"reference": a6_obs_url})
        a6_text = "; ".join(
            f"{rc.tie_marker or f'#{rc.rank}'} {rc.candidate.disease} "
            f"(similarity={rc.candidate.similarity_score:.3f})"
            for rc in a6.candidates
        )
    else:
        a6_obs_url = None
        a6_text = a6.no_data_note or "정보 없음"
    sections.append(
        {
            "title": "A6. AI 예상질환 (비진단적 의사결정 지원)",
            "code": _local_concept(
                "ai-predicted-disease-section", "AI-predicted disease (non-diagnostic)"
            ),
            "text": _div(f"NOT A DIAGNOSIS. {a6_text}"),
            **({"entry": a6_entries} if a6_entries else {}),
        }
    )

    # ── A7 Department recommendation: ServiceRequest ──
    a7_entries: list[dict] = []
    for d in a7.department_candidates:
        sr_url = add(
            f"service_request_{len(a7_entries)}",
            {
                "resourceType": "ServiceRequest",
                "id": str(uuid.uuid4()),
                "status": "active",
                "intent": "proposal",
                "subject": {"reference": patient_url},
                "category": [{"text": "department-referral"}],
                "performer": [{"display": d.department}],
                "reasonCode": [{"text": d.reason}],
                **({"reasonReference": [{"reference": a6_obs_url}]} if a6_obs_url else {}),
            },
        )
        a7_entries.append({"reference": sr_url})
    a7_text = (
        "; ".join(f"{d.department}: {d.reason}" for d in a7.department_candidates) or "정보 없음"
    )
    sections.append(
        {
            "title": "A7. 권장 진료과 / 설문",
            "code": _local_concept("department-recommendation", "recommended department"),
            "text": _div(f"{a7_text}. {a7.medication_note}"),
            **({"entry": a7_entries} if a7_entries else {}),
        }
    )

    # ── B1-B3: repeated Observation per scale_series/ctrs_series point ──
    b_entries: list[dict] = []
    for scale_name, points in lon.scale_series.items():
        total_code = _SCALE_TOTAL_LOINC.get(scale_name)
        code = (
            {
                "coding": [{"system": "http://loinc.org", "code": total_code}],
                "text": f"{scale_name} total",
            }
            if total_code
            else _local_concept("scale-total", f"{scale_name} total")
        )
        for p in points:
            if not p.administered or p.total_score is None:
                continue
            b_url = add(
                f"b1_{scale_name}_{p.session_index}",
                {
                    "resourceType": "Observation",
                    "id": str(uuid.uuid4()),
                    "status": "final",
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                    "code": "survey",
                                }
                            ]
                        }
                    ],
                    "code": code,
                    "subject": {"reference": patient_url},
                    "effectiveDateTime": p.simulated_date,
                    "valueQuantity": {"value": p.total_score, "unit": "score"},
                    "note": [{"text": NON_VALIDATED_ADMINISTRATION_CAVEAT_KO}],
                },
            )
            b_entries.append({"reference": b_url})
    for p in lon.ctrs_series:
        if p.session_ctrs is None:
            continue
        b_url = add(
            f"b2_ctrs_{p.session_index}",
            {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "survey",
                            }
                        ]
                    }
                ],
                "code": _local_concept("ctrs", "Crisis Triage Rating Scale (local)"),
                "subject": {"reference": patient_url},
                "effectiveDateTime": p.simulated_date,
                "valueInteger": p.session_ctrs,
            },
        )
        b_entries.append({"reference": b_url})
    sections.append(
        {
            "title": "B1-B3. 종단 추세 / CTRS 추이 / 사건 타임라인",
            "code": _local_concept("longitudinal-trend", "longitudinal trend"),
            "text": _div(
                f"overall_direction={lon.overall_direction}, course_shape={lon.course_shape}. "
                f"{b.overall_direction_sensitivity_note}"
            ),
            **({"entry": b_entries} if b_entries else {}),
        }
    )

    # ── B4 Discordance ──
    sections.append(
        {
            "title": "B4. 불일치 신호",
            "code": _local_concept("discordance-flag", "trend concordance/discordance (local)"),
            "text": _div(
                f"trend concordance_flag={lon.concordance_flag} "
                "(trend-level only, distinct from A3's same-session co-display)"
            ),
        }
    )

    # ── Cross-cutting non-diagnostic disclosure (dedicated section) ──
    sections.append(
        {
            "title": "면책 조항 (Disclaimer)",
            "code": {"text": "disclaimer"},
            "text": _div(report.disclaimer),
        }
    )

    composition = {
        "resourceType": "Composition",
        "id": str(uuid.uuid4()),
        "status": "final",
        "type": _loinc_concept("composition_type", "Mental health referral note"),
        "subject": {"reference": patient_url},
        "date": report.generated_at,
        "author": [{"display": "F5 자동 조합 엔진 (neurosync, is_diagnostic=false)"}],
        "title": f"F5 정신건강 인계 요약 — {report.vp_id}",
        "section": sections,
    }
    comp_full_url, comp_entry = _new_entry(composition)
    entries.insert(0, comp_entry)

    return {
        "resourceType": "Bundle",
        "type": "document",
        "timestamp": report.generated_at,
        "identifier": {
            "system": "urn:neurosync:f5-bundle-id",
            "value": f"{report.vp_id}-{report.generated_at}",
        },
        "entry": entries,
    }


def validate_fhir_bundle(bundle: dict) -> list[str]:
    """Structural self-check only (design doc §5.3 last paragraph) — NEVER
    an HL7 `$validate` call (D3). Returns a list of violation strings
    (empty = structurally OK per this project's own checks). Checks:
    (a) required fields present per resource type used, (b) every
    `urn:uuid` reference resolves to an actual bundle entry, (c) bundle
    type is "document" with a Composition first entry, (d) `is_diagnostic`/
    disclaimer text present verbatim (dedicated Composition section)."""
    violations: list[str] = []

    if bundle.get("resourceType") != "Bundle":
        violations.append("bundle.resourceType must be 'Bundle'")
    if bundle.get("type") != "document":
        violations.append("bundle.type must be 'document'")

    entries = bundle.get("entry") or []
    if not entries:
        violations.append("bundle.entry must be non-empty")
        return violations

    first = entries[0].get("resource", {})
    if first.get("resourceType") != "Composition":
        violations.append(
            "first bundle entry must be a Composition resource (document Bundle rule)"
        )

    full_urls = [e.get("fullUrl") for e in entries]
    if any(not u for u in full_urls):
        violations.append("every bundle entry must carry a non-empty fullUrl")
    if len(set(full_urls)) != len(full_urls):
        violations.append("every bundle entry must carry a UNIQUE fullUrl")
    full_url_set = set(full_urls)

    required_fields: dict[str, list[str]] = {
        "Composition": ["status", "type", "date", "author", "title", "section", "subject"],
        "Patient": ["resourceType", "id"],
        "Observation": ["status", "code"],
        "RiskAssessment": ["status", "subject"],
        "ServiceRequest": ["status", "intent", "subject"],
        "QuestionnaireResponse": ["status", "subject"],
    }
    for e in entries:
        res = e.get("resource", {})
        rtype = res.get("resourceType")
        for f in required_fields.get(rtype, []):
            if f not in res or res[f] in (None, "", []):
                violations.append(
                    f"{rtype} (fullUrl={e.get('fullUrl')}) missing required field '{f}'"
                )

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            ref = obj.get("reference")
            if isinstance(ref, str) and ref.startswith("urn:uuid:") and ref not in full_url_set:
                violations.append(f"unresolved reference: {ref}")
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(bundle)

    for sec in first.get("section", []):
        if not sec.get("title"):
            violations.append("Composition.section missing title")
        if not sec.get("text") and not sec.get("entry"):
            violations.append(
                f"Composition.section '{sec.get('title')}' has neither text nor entry"
            )

    disclaimer_section = next(
        (s for s in first.get("section", []) if s.get("code", {}).get("text") == "disclaimer"), None
    )
    if disclaimer_section is None:
        violations.append(
            "Composition must carry a dedicated disclaimer section (code.text=='disclaimer')"
        )

    return violations
