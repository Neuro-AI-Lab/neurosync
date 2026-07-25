"""POST /ai/handoff/generate — request / response schema.

Single source of truth between apps/api (consumer, plumbing) and
apps/ai-server (producer, LLM generation). PRD §0.3 contract — change requires
both PRDs updated simultaneously. SLA: p95 < 30s (PRD §4.1).

BUG-066 fix (EXP-031 fix_wave_design.md): `HandoffRequest`/`HandoffResponse`
below are now field-identical to ai-server's real wire schema
(`apps/ai-server/src/schemas/handoff.py::HandoffInput`/`HandoffOutput`) on
BOTH directions — the pre-fix version shared zero field names with either
side, so every request field was silently dropped (ai-server's `HandoffInput`
had no `extra="forbid"`) and the response never validated (apps/api's
pre-fix `HandoffResponse` required non-optional `chief_complaint`/
`present_illness` ai-server never returns).

Separation of concerns (unchanged): the AI server produces the *narrative*
(`report_markdown`/`report_json`) + evidence packets. The platform composes
the deterministic facts (questionnaire scores, risk signals, patient
demographics) at GET /report time — they are NOT part of this contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SlotData(BaseModel):
    """Collected clinical slot data — field-identical to ai-server's
    `schemas.handoff.SlotData` (BUG-066 fix). Mirrors `ALL_SLOT_KEYS` in
    ai-server's `clinical_slot.py`; the flat canonical-12 keys
    `ClinicalSlotAgent` actually emits (see BUG-050) are the 4 fields
    prefixed with a comment below plus the pre-existing ones."""

    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    onset: str | None = None
    duration: str | None = None
    triggers: str | None = None
    sleep: str | None = None
    appetite: str | None = None
    mood: str | None = None
    anxiety: str | None = None
    concentration: str | None = None
    energy: str | None = None
    functional_impairment: str | None = None
    medication: str | None = None
    past_psychiatric_history: str | None = None
    risk_factors: str | None = None
    psychosocial_context: str | None = None
    substance_use: str | None = None
    # BUG-050's canonical-12 keys ClinicalSlotAgent actually produces.
    medical_history: str | None = None
    personal_social_history: str | None = None
    family_history: str | None = None
    substance_use_history: str | None = None

    model_config = ConfigDict(extra="forbid")


class ScaleScore(BaseModel):
    """Standardized questionnaire score — mirrors ai-server's `ScaleScore`."""

    scale_name: str = Field(..., description="e.g. PHQ-9, GAD-7")
    total_score: int
    severity: str = Field(default="", description="e.g. mild, moderate, severe")

    model_config = ConfigDict(extra="forbid")


class HandoffRequest(BaseModel):
    """Wire request — field-identical to ai-server's `HandoffInput`
    (BUG-066 fix). `session_id` is a `str` here (not `UUID`) to match
    `AgentInput.session_id: str` exactly; `services/handoff.py::_build_request`
    is responsible for `str(session_id)` at the call site."""

    session_id: str
    slots: SlotData = Field(default_factory=SlotData)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    scale_scores: list[ScaleScore] = Field(default_factory=list)
    risk_events: list[dict[str, str]] = Field(
        default_factory=list,
        description="Safety events during the session",
    )
    ocr_documents: list[dict[str, str]] = Field(default_factory=list)
    prior_handoff: str | None = Field(
        default=None,
        description="Previous handoff report markdown (for longitudinal delta)",
    )
    is_first_visit: bool = Field(default=True)
    # BUG-069 follow-up (F5 metadata enrichment, 2026-07-25) — mirrors
    # ai-server's `schemas.handoff.HandoffInput` additive fields exactly
    # (field-identical contract, same rationale as BUG-066's fix). `None`
    # means "not provided" and ai-server keeps its existing "기록 없음"/
    # "미수집" grounded fallback in that case.
    patient_gender: str | None = Field(
        default=None,
        description="Patient gender, e.g. 'M'/'F' — None if unavailable",
    )
    session_started_at: str | None = Field(
        default=None,
        description="Session start timestamp, ISO 8601 — None if unavailable",
    )
    session_ended_at: str | None = Field(
        default=None,
        description="Session submission timestamp, ISO 8601 — None if the "
        "session was never submitted",
    )

    model_config = ConfigDict(extra="forbid")


class EvidencePacket(BaseModel):
    """Mirrors ai-server's `schemas.common.EvidencePacket`."""

    evidence_id: str
    source_type: str
    source_ref: str
    content_summary: str

    model_config = ConfigDict(extra="forbid")


class HandoffResponse(BaseModel):
    """Wire response — mirrors ai-server's real `HandoffOutput` fields
    (BUG-066 fix). Deliberately NOT `extra="forbid"`: ai-server's actual
    JSON also carries the shared `AgentOutput` base fields (`model_used`,
    `prompt_version`, `latency_ms`, `reason_summary`, `prompts_degraded`),
    none of which this contract declares — forbidding them would make this
    contract brittle to any future additive `AgentOutput` field (same
    rationale as `contracts.safety.SafetyResponse`, this fix wave)."""

    report_markdown: str = Field(
        ..., description="Full handoff report in Markdown format"
    )
    report_json: dict | None = Field(
        default=None,
        description="Structured JSON parsed from the 12-section report — "
        "UNVERIFIED whether ai-server's `handoff_generator.py` ever "
        "populates this (no `report_json=` assignment found there as of "
        "this fix); treat as `None` by default (`report_markdown` is the "
        "primary rendering surface, see `apps/web/components/"
        "HandoffReportView.tsx`).",
    )
    report_pdf_base64: str | None = None
    trend_plot_base64: str | None = None
    evidence_packets: list[EvidencePacket] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="none")
    requires_human_review: bool = Field(default=False)

    model_config = ConfigDict(extra="ignore")
