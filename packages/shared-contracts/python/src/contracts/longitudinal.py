"""POST /ai/temporal/analyze + POST /ai/handoff/report — request/response schema.

Single source of truth between apps/api (consumer) and apps/ai-server
(producer) for the STATELESS F4/F5 compute endpoints
(`docs/ai/deployment_integration_plan.md` R1/R2). ai-server never persists
session state (R2, stateless compute principle) — the caller (backend) sends
the FULL session series on every call; ai-server's routes convert this
payload into `src.f4`/`src.f5`'s own harness-input dataclasses in-process and
call the pure, zero-LLM engines directly. No engine logic lives here.

`LongitudinalSessionEntry` mirrors one F1/F2/F3 session-ledger entry (+ that
session's own `conversation.json` top-level fields) — the SAME field set
`src/continuous_test.py::_build_session_record`/`_build_f5_f3_administration`
already read from disk for the file-backed harness path, flattened into one
caller-supplied JSON shape so a stateless HTTP caller never needs to hand
ai-server a file path.

`f3` (when present) carries the ledger's own `"f3"` sub-object fields PLUS
`critical_item_positive` — the ledger sub-object itself omits that field (it
lives only in the separately-persisted `survey.json`'s `score_result`,
`src.f3` module docstring); a stateless caller that already scored the
survey via `POST /ai/survey/score` has that value in hand and supplies it
directly here (no second file read to backfill it, unlike the harness path).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LongitudinalSessionEntry(BaseModel):
    """One session's worth of F1/F2/F3 data, ledger-entry-shaped."""

    session_index: int
    simulated_date: str
    scenario_pack_id: str | None = None
    arc_mode: str | None = None
    final_slots: dict[str, str] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    session_ctrs: int | None = None
    crisis_triggered: bool = False
    crisis_turn: int | None = None
    # BUG-055 fail-loud (Option B, ADR-046 #1): explicit, typed carriers for
    # this session's risk-assessment/escalation signal — the SAME value
    # ai-server's orchestrator writes to `SessionState.slot_data
    # ["risk_assessment"]` (`schemas/orchestrator.py`), reachable to the
    # caller via `ChatResponse.session_state.slot_data.risk_assessment`
    # once contract1 (session_state round-trip) is in place. Deliberately
    # NOT folded into the untyped `final_slots` dict — a generic
    # `dict[str, str]` slot silently absorbs a missing/blank value with no
    # schema-level signal, which is exactly BUG-055's fail-silent mechanism
    # (this endpoint had NO field at all for it before this fix). `/ai/slots
    # /extract` still never accepts `risk_assessment` from the extractor
    # (`routes/slots.py::_apply_grounding_filter`, BUG-049 — that filter is
    # unaffected and correct-by-design: only a dedicated safety protocol may
    # populate this value, never the slot extractor).
    risk_assessment: str | None = Field(
        default=None,
        description="This session's risk-assessment text, sourced from "
        "session_state.slot_data.risk_assessment — REQUIRED (fail-loud, "
        "see `routes/handoff.py::report`) whenever crisis_triggered or "
        "clinical_escalation_required is True for this session.",
    )
    clinical_escalation_required: bool = Field(
        default=False,
        description="ADR-044 backstop passthrough for this session — "
        "sourced from ChatResponse.session_state's own "
        "clinical_escalation_required (contract1).",
    )
    probe_events: list[dict[str, Any]] = Field(default_factory=list)
    risk_floor: int | None = None
    turn_sentiment_polarities: list[float] = Field(default_factory=list)
    turn_risk_signal_count: int = 0
    session_sentiment_summary: dict[str, Any] | None = None
    domain_candidates: list[dict[str, Any]] = Field(default_factory=list)
    ai_predicted_disease: dict[str, Any] | None = None
    f3: dict[str, Any] | None = None

    # ── Header/latest-session-only fields (F5 `SessionSnapshot`; F4 ignores
    # these — required only on the LAST entry by `session_index`, optional
    # on every earlier one). ──
    session_id: str | None = None
    persona_id: str | None = None
    persona_name: str | None = None
    model: str | None = None

    model_config = ConfigDict(extra="forbid")


class TemporalAnalyzeRequest(BaseModel):
    """`POST /ai/temporal/analyze` request — `sessions` must be caller-sorted
    by non-decreasing `session_index` (mirrors `LongitudinalSeriesInput`'s own
    requirement, `src/f4.py`)."""

    vp_id: str
    sessions: list[LongitudinalSessionEntry]

    model_config = ConfigDict(extra="forbid")


class DomainInferenceInput(BaseModel):
    """The LATEST session's F2 artifact content — mirrors
    `src.f5.DomainInferenceSnapshot`'s own 3 fields."""

    ai_predicted_disease: dict[str, Any] | None = None
    department_candidates: list[dict[str, Any]] = Field(default_factory=list)
    validation_errors_present: bool = False

    model_config = ConfigDict(extra="forbid")


class HandoffReportRequest(BaseModel):
    """`POST /ai/handoff/report` request — the SAME session series
    `TemporalAnalyzeRequest` carries (F4 is recomputed internally, never
    accepted pre-computed, so the two endpoints can never silently diverge
    on the same input) plus the latest session's F2 domain-inference detail.

    `include_charts`: generates the 4 F4 PNG charts in-memory (via
    `src.services.trend_plotter`, the SAME chart-building functions
    `src.services.f4_report` already calls — no chart-generation logic
    duplicated) and returns them as base64 PNGs; also feeds them into the
    embedded-PDF chart pages when `include_pdf=True`. Off by default — chart
    generation is the most expensive part of this call.
    `include_pdf`: build and return `pdf_base64` (base64-encoded, ~10MB
    response size guard — `pdf_omitted_reason` explains an omission).
    """

    vp_id: str
    sessions: list[LongitudinalSessionEntry]
    domain_inference: DomainInferenceInput = Field(default_factory=DomainInferenceInput)
    narrative_enabled: bool = False
    narrative_text: str | None = None
    include_charts: bool = False
    include_pdf: bool = True

    model_config = ConfigDict(extra="forbid")


class HandoffReportResponse(BaseModel):
    """`POST /ai/handoff/report` response — `report_markdown`/`fhir_bundle`
    are `src.f5.assemble_handoff_report` + `src.services.f5_report`'s own
    `build_markdown_report`/`build_fhir_bundle` output, unmodified.
    `pdf_base64` is `build_pdf_report`'s bytes, base64-encoded; `None` (with
    `pdf_omitted_reason` set) when `include_pdf=False` or the encoded size
    would exceed the ~10MB response guard."""

    vp_id: str
    report_markdown: str
    fhir_bundle: dict[str, Any]
    pdf_base64: str | None = None
    pdf_omitted_reason: str | None = None
    chart_pngs_base64: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


ChartKey = Literal[
    "scales_ctrs_sentiment", "ctrs_zoom", "disease_similarity", "domain_confidence"
]
