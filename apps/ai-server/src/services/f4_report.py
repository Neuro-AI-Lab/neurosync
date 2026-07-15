"""F4 report writer — `save_f4_result` + markdown report + chart orchestration.

`docs/ai/f4_quick_dev_plan.md` §5. Deliberately kept OUT of `src/f4.py` (the
pure, zero-file-I/O analysis engine) so a whole-file grep for `open(`/file-
I/O in `src/f4.py` returns 0 hits with zero ambiguity (REV-044 Criterion 6,
`ADR-036`) — this module is the ONE place F4's OWN output artifacts
(`temporal.json`/`_temporal_report.md`/PNG charts) get written to disk, the
same role `src/services/trend_plotter.py` already plays for chart bytes.
Called by the harness (`src/continuous_test.py`) AFTER
`src.f4.analyze_longitudinal_series` returns — never by `src/f4.py` itself.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.f1 import OUTPUT_DIR
from src.f3 import _SEVERITY_CAVEATS as F3_SEVERITY_CAVEATS
from src.schemas.longitudinal import LongitudinalAnalysisOutput
from src.services.trend_plotter import (
    NamedSeriesPoint,
    TrendDataPoint,
    generate_domain_trend_plot,
    generate_similarity_trend_plot,
    generate_trend_plot,
)

logger = logging.getLogger(__name__)


def save_f4_result(
    output: LongitudinalAnalysisOutput,
    output_dir: Path | None = None,
    *,
    vp_id: str | None = None,
) -> dict[str, Path]:
    """Save F4 result as JSON + markdown report + PNG charts (design doc
    §5.1/§5.2). Naming mirrors `save_f1_result`/`save_f2_result`/
    `save_f3_result`: `<vp_id>_<ts>_temporal.json` / `_temporal_report.md` /
    chart PNGs, under `docs/ai/simulation_results/<vp_id>/` — same directory
    as every other F1-F3 artifact for that VP, no new directory.
    """
    resolved_vp_id = vp_id or output.vp_id
    base = output_dir or OUTPUT_DIR
    out = base / resolved_vp_id
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{resolved_vp_id}_{ts}"

    paths: dict[str, Path] = {}

    json_path = out / f"{prefix}_temporal.json"
    json_path.write_text(
        json.dumps(output.model_dump(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    paths["json"] = json_path

    report_path = out / f"{prefix}_temporal_report.md"
    report_path.write_text(_build_report(output), encoding="utf-8")
    paths["report"] = report_path

    paths.update(_generate_and_save_charts(output, out, prefix))

    logger.info("F4 results saved: %s", ", ".join(str(p) for p in paths.values()))
    return paths


# ── Charts (design doc §5.2) ───────────────────────────────────────────────


def _build_trend_data_points(output: LongitudinalAnalysisOutput) -> list[TrendDataPoint]:
    """One `TrendDataPoint` per distinct simulated_date across the series.
    `phq9`/`gad7` are populated only for sessions actually administering
    that scale (sparse-series handling already proven in
    `trend_plotter._draw_panel`'s `valid_pairs` filter, design doc §5.2
    row 1)."""
    dates = sorted(
        {p.simulated_date for p in output.ctrs_series}
        | {p.simulated_date for p in output.sentiment_series}
        | {p.simulated_date for p in output.slot_fill_series}
    )
    ctrs_by_date = {p.simulated_date: p.session_ctrs for p in output.ctrs_series}
    sentiment_by_date = {p.simulated_date: p.mean_polarity for p in output.sentiment_series}
    slot_fill_by_date = {p.simulated_date: p.filled_count for p in output.slot_fill_series}
    phq9_by_date = {
        p.simulated_date: p.total_score
        for p in output.scale_series.get("PHQ-9", []) if p.administered
    }
    gad7_by_date = {
        p.simulated_date: p.total_score
        for p in output.scale_series.get("GAD-7", []) if p.administered
    }
    return [
        TrendDataPoint(
            date=d,
            phq9=phq9_by_date.get(d),
            gad7=gad7_by_date.get(d),
            ctrs=ctrs_by_date.get(d),
            sentiment=sentiment_by_date.get(d),
            slot_fill_count=slot_fill_by_date.get(d),
        )
        for d in dates
    ]


def _generate_and_save_charts(
    output: LongitudinalAnalysisOutput, out_dir: Path, prefix: str
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    data_points = _build_trend_data_points(output)

    # Chart 1: scale totals + CTRS + sentiment + slot-fill, multi-panel.
    result = generate_trend_plot(
        data_points, patient_name=output.vp_id, title=f"F4 종단 추이 — {output.vp_id}"
    )
    if result is not None:
        p = out_dir / f"{prefix}_temporal_scales_ctrs_sentiment.png"
        p.write_bytes(result.png_bytes)
        paths["chart_scales_ctrs_sentiment"] = p

    # Chart 2: CTRS zoom — same generate_trend_plot call, only CTRS populated
    # (design doc §5.2 row 2 fallback: a dedicated single-panel is the SAME
    # function, a second invocation, zero new code).
    ctrs_only = [
        TrendDataPoint(date=dp.date, ctrs=dp.ctrs) for dp in data_points if dp.ctrs is not None
    ]
    if ctrs_only:
        ctrs_result = generate_trend_plot(
            ctrs_only, patient_name=output.vp_id, title=f"F4 위기단계(CTRS) 확대 — {output.vp_id}"
        )
        if ctrs_result is not None:
            p = out_dir / f"{prefix}_temporal_ctrs_zoom.png"
            p.write_bytes(ctrs_result.png_bytes)
            paths["chart_ctrs_zoom"] = p

    # Chart 3: per-disease similarity trend (VAL-014, on-chart low-confidence cue).
    disease_points = [
        NamedSeriesPoint(date=pt.simulated_date, name=pt.disease, value=pt.similarity_score)
        for pt in output.disease_candidate_series
    ]
    similarity_result = generate_similarity_trend_plot(disease_points, patient_name=output.vp_id)
    if similarity_result is not None:
        p = out_dir / f"{prefix}_temporal_disease_similarity.png"
        p.write_bytes(similarity_result.png_bytes)
        paths["chart_disease_similarity"] = p

    # Chart 4: domain-candidate confidence trend.
    domain_points = [
        NamedSeriesPoint(date=pt.simulated_date, name=pt.domain, value=pt.confidence)
        for pt in output.domain_candidate_series
    ]
    domain_result = generate_domain_trend_plot(domain_points, patient_name=output.vp_id)
    if domain_result is not None:
        p = out_dir / f"{prefix}_temporal_domain_confidence.png"
        p.write_bytes(domain_result.png_bytes)
        paths["chart_domain_confidence"] = p

    return paths


# ── Markdown report (design doc §5.1) ──────────────────────────────────────


def _build_report(output: LongitudinalAnalysisOutput) -> str:
    lines = [
        f"# F4 Longitudinal Analysis Report — {output.vp_id}",
        "",
        f"> arc_mode: {output.arc_mode or 'N/A (natural/unscripted sessions)'} | "
        f"n_sessions: {output.n_sessions} | session_span_days: {output.session_span_days} | "
        f"generated_at: {output.generated_at}",
        f"> overall_direction: **{output.overall_direction}** | "
        f"course_shape: **{output.course_shape}** | "
        f"concordance_flag: **{output.concordance_flag}**",
        f"> is_diagnostic: {output.is_diagnostic}",
        "",
        "## Disclaimer",
        "",
        output.disclaimer,
        "",
    ]

    # ── Risk / crisis section (prominent, CVR-020 binding condition 3) ──
    lines.extend(["## Risk / crisis section", ""])
    if output.crisis_f3_gaps:
        lines.append(
            "**F3 GAP DURING RISK-ELEVATED SESSION(S) — see CVR-020 binding condition 3:**"
        )
        lines.append("")
        for note in output.crisis_f3_gaps:
            lines.append(f"- **{note}**")
        lines.append("")
    else:
        lines.append(
            "No F3 gap coincided with a risk-elevated session this run (no "
            "`crisis_triggered=true`/`session_ctrs<=2` session lacked an administered scale) "
            "— CVR-020 binding condition 3 explicitly checked, not merely omitted."
        )
        lines.append("")
    lines.extend(
        [
            "| Session | Date | session_ctrs | crisis_triggered | probe_event_count | risk_floor |",
            "|---|---|---|---|---|---|",
        ]
    )
    for p in output.ctrs_series:
        lines.append(
            f"| {p.session_index} | {p.simulated_date} | {p.session_ctrs} | "
            f"{p.crisis_triggered} | {p.probe_event_count} | {p.risk_floor} |"
        )
    lines.append("")

    # ── Trend verdicts summary ──
    lines.extend(
        [
            "## Trend verdicts",
            "",
            "| Dimension | Direction | Basis | n_comparable | Evidence |",
            "|---|---|---|---|---|",
        ]
    )
    for tv in output.trend_verdicts:
        evidence_str = "<br>".join(tv.evidence) if tv.evidence else "(none)"
        lines.append(
            f"| {tv.dimension} | {tv.direction} | {tv.basis} | {tv.n_comparable_points} | "
            f"{evidence_str} |"
        )
    lines.append("")

    # ── Slot fill (F1) ──
    lines.extend(
        [
            "## Slot fill (F1)",
            "",
            "| Session | Date | filled/total | newly_filled | newly_missing | MSE observed |",
            "|---|---|---|---|---|---|",
        ]
    )
    for p in output.slot_fill_series:
        lines.append(
            f"| {p.session_index} | {p.simulated_date} | {p.filled_count}/{p.total_questionable} | "
            f"{', '.join(p.newly_filled) or '-'} | {', '.join(p.newly_missing) or '-'} | "
            f"{p.mental_status_exam_observed} |"
        )
    lines.append("")

    # ── Survey scale series (F3), one table per scale ──
    lines.extend(["## Survey scale series (F3)", ""])
    if output.scale_series:
        for scale_name in sorted(output.scale_series):
            points = output.scale_series[scale_name]
            lines.append(f"### {scale_name}")
            lines.append("")
            caveat = F3_SEVERITY_CAVEATS.get(scale_name)
            if caveat:
                lines.append(f"> threshold_caveat (reprojected verbatim from `src.f3`): {caveat}")
                lines.append("")
            lines.append(
                "> Constant-bias check status (CVR-020 Finding 6 / Rec 5, `ISS-F2V-028`): "
                "**NOT separately checked or corrected this run** — the whole-instrument "
                "over-endorsement pattern (CVR-019 #1) may ride the entire band-transition "
                "series below as a constant offset; treat absolute severity-band crossings "
                "with this in mind — the RELATIVE session-to-session delta is less affected "
                "by a roughly-constant bias than the absolute band label is."
            )
            lines.append("")
            lines.extend(
                [
                    "| Session | Date | administered | total_score | max_score | severity | "
                    "critical_item_positive | subscale_scores |",
                    "|---|---|---|---|---|---|---|---|",
                ]
            )
            for p in points:
                lines.append(
                    f"| {p.session_index} | {p.simulated_date} | {p.administered} | "
                    f"{p.total_score} | {p.max_score} | {p.severity} | "
                    f"{p.critical_item_positive} | {p.subscale_scores or '-'} |"
                )
            lines.append("")
    else:
        lines.append("(no scale was ever administered/recommended across this series)")
        lines.append("")

    # ── Sentiment (F1) ──
    lines.extend(
        [
            "## Sentiment (F1)",
            "",
            "| Session | Date | mean_polarity | source | dominant_emotions | "
            "risk_signal_count | signal_strength | emotional_shift_detected |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for p in output.sentiment_series:
        lines.append(
            f"| {p.session_index} | {p.simulated_date} | {p.mean_polarity} | {p.source} | "
            f"{', '.join(p.dominant_emotions) or '-'} | {p.risk_signal_count} | "
            f"{p.signal_strength} | {p.emotional_shift_detected} |"
        )
    lines.append("")

    # ── Domain candidates (F2) ──
    lines.extend([
        "## Domain candidates (F2)", "",
        "| Session | Date | domain | confidence |", "|---|---|---|---|",
    ])
    for p in output.domain_candidate_series:
        lines.append(
            f"| {p.session_index} | {p.simulated_date} | {p.domain} | {p.confidence:.3f} |"
        )
    if not output.domain_candidate_series:
        lines.append("| - | - | (none) | - |")
    lines.append("")

    # ── AI-predicted-disease similarity trend (F2) ──
    lines.extend(
        [
            "## AI-predicted-disease similarity trend (F2)",
            "",
            "> VAL-014 (open, inherited): F2 disease-candidate face-validity is not "
            "established. `similarity_score` is a similarity TREND signal, never a "
            "probability/가능성 (REV-013 §4).",
            "",
            "| Session | Date | disease | similarity_score | rank |",
            "|---|---|---|---|---|",
        ]
    )
    for p in output.disease_candidate_series:
        lines.append(
            f"| {p.session_index} | {p.simulated_date} | {p.disease} | "
            f"{p.similarity_score:.3f} | {p.rank} |"
        )
    if not output.disease_candidate_series:
        lines.append("| - | - | (none) | - | - |")
    lines.append("")

    return "\n".join(lines)
