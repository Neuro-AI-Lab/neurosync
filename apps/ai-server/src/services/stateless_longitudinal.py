"""Stateless-request -> `src.f4`/`src.f5` harness-input conversion.

`docs/ai/deployment_integration_plan.md` R1/R2. Thin, additive glue between
the shared-contracts request schema (`contracts.longitudinal`) and
`src.f4`/`src.f5`'s own pure, zero-LLM engine dataclasses — mirrors exactly
what `src/continuous_test.py`'s file-backed assembly functions
(`_build_session_record`/`_build_f5_session_snapshot`/
`_build_f5_f3_administration`/`_build_f5_domain_inference_snapshot`) already
build from ledger/artifact files, just from an in-memory HTTP request
payload instead (R2, stateless compute principle — ai-server never reads or
writes session state itself). Every value below is passed through verbatim;
this module makes zero clinical judgments and calls zero LLMs.
"""

from __future__ import annotations

from contracts.longitudinal import DomainInferenceInput, LongitudinalSessionEntry

from src import f4, f5
from src.schemas.ai_predicted_disease import AIPredictedDiseaseOutput
from src.schemas.longitudinal import LongitudinalAnalysisOutput
from src.services import f4_report
from src.services.trend_plotter import (
    NamedSeriesPoint,
    generate_domain_trend_plot,
    generate_similarity_trend_plot,
    generate_trend_plot,
)


def sorted_sessions(sessions: list[LongitudinalSessionEntry]) -> list[LongitudinalSessionEntry]:
    """Caller-sorted-by-non-decreasing-`session_index` — `src.f4`/`src.f5`
    both require this and raise loudly rather than re-sort; sorting here
    once, before either engine call, keeps the two routes' inputs
    consistent (never a caller-supplied ordering bug surfacing as two
    DIFFERENT engine-side errors depending which route ran first)."""
    return sorted(sessions, key=lambda e: e.session_index)


def build_series_input(
    vp_id: str, sessions: list[LongitudinalSessionEntry]
) -> f4.LongitudinalSeriesInput:
    """One `f4.SessionRecord` per request entry, verbatim field-for-field —
    the SAME shape `continuous_test._build_session_record` builds from a
    ledger entry + its `conversation.json`/`domain_inference.json`, just
    sourced from the request body instead of disk."""
    records = tuple(
        f4.SessionRecord(
            session_index=e.session_index,
            simulated_date=e.simulated_date,
            scenario_pack_id=e.scenario_pack_id,
            arc_mode=e.arc_mode,
            final_slots=e.final_slots,
            missing_slots=e.missing_slots,
            session_ctrs=e.session_ctrs,
            crisis_triggered=e.crisis_triggered,
            crisis_turn=e.crisis_turn,
            probe_events=e.probe_events,
            risk_floor=e.risk_floor,
            turn_sentiment_polarities=e.turn_sentiment_polarities,
            turn_risk_signal_count=e.turn_risk_signal_count,
            session_sentiment_summary=e.session_sentiment_summary,
            domain_candidates=e.domain_candidates,
            ai_predicted_disease=e.ai_predicted_disease,
            f3=e.f3,
        )
        for e in sessions
    )
    return f4.LongitudinalSeriesInput(vp_id=vp_id, sessions=records)


def build_f3_administration(entry: LongitudinalSessionEntry) -> f5.F3Administration | None:
    """One `f5.F3Administration` from `entry.f3` — mirrors
    `continuous_test._build_f5_f3_administration`'s field reprojection
    verbatim, EXCEPT `critical_item_positive`: the harness backfills that
    from a separately-persisted `survey.json` it reads off disk; this
    stateless route has no file to read, so the caller (already holding the
    `POST /ai/survey/score` result) supplies it directly as an extra key on
    the same `f3` dict (`contracts.longitudinal.LongitudinalSessionEntry.f3`
    docstring). Returns `None` (never raises) for an entry with no/
    unrecognized `f3` sub-object — an honest "no F3 this session", same
    discipline as the harness."""
    f3 = entry.f3
    if not f3:
        return None
    outcome = f3.get("outcome")
    if outcome not in ("administered", "no_questionnaire_indicated", "item_bank_unpopulated"):
        return None
    return f5.F3Administration(
        session_index=entry.session_index,
        simulated_date=entry.simulated_date,
        outcome=outcome,
        scale_name=f3.get("scale_name"),
        item_bank_version=f3.get("item_bank_version"),
        item_bank_provenance=f3.get("item_bank_provenance"),
        responses=tuple(f3.get("responses") or ()),
        total_score=f3.get("total_score"),
        max_score=f3.get("max_score"),
        severity=f3.get("severity"),
        critical_item_positive=f3.get("critical_item_positive"),
        safety_referral=bool(f3.get("safety_referral", False)),
        administration_mode=f3.get("administration_mode", "natural"),
        threshold_caveat=f3.get("threshold_caveat"),
    )


def build_session_snapshot(entry: LongitudinalSessionEntry) -> f5.SessionSnapshot:
    """The header (LATEST) session's `f5.SessionSnapshot` — `entry` must be
    the series' own last (highest `session_index`) entry, same "latest
    session" rule `continuous_test._build_f5_session_snapshot` applies to
    the header `conversation.json`."""
    return f5.SessionSnapshot(
        session_id=entry.session_id or "",
        persona_id=entry.persona_id or "",
        persona_name=entry.persona_name or "",
        session_index=entry.session_index,
        simulated_date=entry.simulated_date,
        model=entry.model or "",
        final_slots=entry.final_slots,
        session_ctrs=entry.session_ctrs,
        crisis_triggered=entry.crisis_triggered,
        crisis_turn=entry.crisis_turn,
        risk_floor=entry.risk_floor,
        probe_event_count=len(entry.probe_events or []),
    )


def build_domain_inference_snapshot(di: DomainInferenceInput) -> f5.DomainInferenceSnapshot:
    """Mirrors `continuous_test._build_f5_domain_inference_snapshot`'s
    validate-then-extract discipline — an unparseable/absent
    `ai_predicted_disease` dict degrades to `None` (`ValidationError`
    propagates as a 422 at the route layer, never silently swallowed into a
    fabricated empty section)."""
    apd = (
        AIPredictedDiseaseOutput.model_validate(di.ai_predicted_disease)
        if di.ai_predicted_disease
        else None
    )
    depts = tuple(
        f5.DepartmentCandidateInput(
            department=d.get("department", ""),
            reason=d.get("reason", ""),
            domain_ref=d.get("domain_ref"),
        )
        for d in di.department_candidates
    )
    return f5.DomainInferenceSnapshot(
        ai_predicted_disease=apd,
        department_candidates=depts,
        validation_errors_present=di.validation_errors_present,
    )


def build_all_sessions(
    sessions: list[LongitudinalSessionEntry],
) -> tuple[f5.SessionSlotSnapshot, ...]:
    """Task-1 all-session slot maximization input — one `SessionSlotSnapshot`
    per request entry (mirrors `continuous_test._run_f5_report`'s own
    `all_sessions` construction from every ledger entry, not just the
    header)."""
    return tuple(
        f5.SessionSlotSnapshot(
            session_index=e.session_index,
            simulated_date=e.simulated_date,
            final_slots=e.final_slots,
        )
        for e in sessions
    )


# ── In-memory chart generation (R1, `include_charts=True` only) ──────────
#
# Reuses `src.services.f4_report._build_trend_data_points` (the SAME
# TrendDataPoint-assembly helper the file-backed harness's own chart step
# calls, `f4_report.save_f4_result` -> `_generate_and_save_charts`) and
# `src.services.trend_plotter`'s chart-rendering functions directly — no
# chart-building logic is duplicated or changed here, only invoked without
# the file-write step (`_generate_and_save_charts` always writes PNGs to
# disk; this stateless route never does).

_CHART_FILENAMES = {
    "scales_ctrs_sentiment": "scales_ctrs_sentiment.png",
    "ctrs_zoom": "ctrs_zoom.png",
    "disease_similarity": "disease_similarity.png",
    "domain_confidence": "domain_confidence.png",
}


def generate_charts_in_memory(
    output: LongitudinalAnalysisOutput,
) -> tuple[f5.ChartFilenames, dict[str, bytes]]:
    """Returns `(ChartFilenames, {chart_key: png_bytes})` — `ChartFilenames`
    carries the SAME 4 keys as `_CHART_FILENAMES` (used only as stable,
    caller-facing labels in the response's `report_markdown`/PDF; no file
    with that name is ever written to disk by this stateless route). A
    chart whose underlying data is empty is honestly omitted (both dicts),
    never fabricated — same "absent, never invented" discipline
    `_resolve_f5_chart_filenames` applies to the file-backed path."""
    data_points = f4_report._build_trend_data_points(output)
    filenames_kwargs: dict[str, str] = {}
    png_bytes: dict[str, bytes] = {}

    result = generate_trend_plot(
        data_points, patient_name=output.vp_id, title=f"F4 종단 추이 — {output.vp_id}"
    )
    if result is not None:
        filenames_kwargs["scales_ctrs_sentiment"] = _CHART_FILENAMES["scales_ctrs_sentiment"]
        png_bytes["scales_ctrs_sentiment"] = result.png_bytes

    ctrs_only = [dp for dp in data_points if dp.ctrs is not None]
    if ctrs_only:
        ctrs_result = generate_trend_plot(
            ctrs_only, patient_name=output.vp_id, title=f"F4 위기단계(CTRS) 확대 — {output.vp_id}"
        )
        if ctrs_result is not None:
            filenames_kwargs["ctrs_zoom"] = _CHART_FILENAMES["ctrs_zoom"]
            png_bytes["ctrs_zoom"] = ctrs_result.png_bytes

    disease_points = [
        NamedSeriesPoint(date=pt.simulated_date, name=pt.disease, value=pt.similarity_score)
        for pt in output.disease_candidate_series
    ]
    similarity_result = generate_similarity_trend_plot(disease_points, patient_name=output.vp_id)
    if similarity_result is not None:
        filenames_kwargs["disease_similarity"] = _CHART_FILENAMES["disease_similarity"]
        png_bytes["disease_similarity"] = similarity_result.png_bytes

    domain_points = [
        NamedSeriesPoint(date=pt.simulated_date, name=pt.domain, value=pt.confidence)
        for pt in output.domain_candidate_series
    ]
    domain_result = generate_domain_trend_plot(domain_points, patient_name=output.vp_id)
    if domain_result is not None:
        filenames_kwargs["domain_confidence"] = _CHART_FILENAMES["domain_confidence"]
        png_bytes["domain_confidence"] = domain_result.png_bytes

    return f5.ChartFilenames(**filenames_kwargs), png_bytes
