"""Schemas for the Handoff Generator agent."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import AgentInput, AgentOutput
from src.schemas.common import EvidencePacket, RiskLevel


class SlotData(BaseModel):
    """Collected clinical slot data from the dialogue session.

    Fields map to ALL_SLOT_KEYS in clinical_slot.py.

    BUG-050 finding (2026-07-21): the docstring above claimed this already
    mapped to `ALL_SLOT_KEYS`, but it never did — `medical_history`,
    `personal_social_history`, `family_history`, and `substance_use_
    history` (4 of the 7 `PATIENT_FILLABLE_SLOTS`) had NO field here at
    all; the pre-existing fields below (`onset`/`duration`/`triggers`/
    `sleep`/`appetite`/`mood`/`anxiety`/`concentration`/`energy`/
    `functional_impairment`/`medication`/`risk_factors`/
    `psychosocial_context`/`substance_use`) are a stale, pre-refactor
    vocabulary `ClinicalSlotAgent` never actually produces (it emits the
    flat canonical-12 keys only) — so those 14 fields have always been
    silently `None` in every real session, and `_build_handoff_input`
    silently dropped 4 of the patient's 7 real, filled slots before they
    ever reached the report generator. The 4 fields below close that gap
    additively; the stale fields are left in place (harmless, always-None,
    out of this fix's scope to remove) rather than risk breaking an
    unknown caller.
    """

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
    # BUG-050 additive fix — the actual canonical-12 keys ClinicalSlotAgent
    # produces for these 4 slots (never mapped before this fix).
    medical_history: str | None = None
    personal_social_history: str | None = None
    family_history: str | None = None
    substance_use_history: str | None = None


class ScaleScore(BaseModel):
    """Standardized questionnaire score."""

    scale_name: str = Field(..., description="e.g. PHQ-9, GAD-7")
    total_score: int
    severity: str = Field(default="", description="e.g. mild, moderate, severe")


class HandoffInput(AgentInput):
    """Input to the handoff generator.

    BUG-066 fix: `extra="forbid"` scoped to this subclass (not the shared
    `AgentInput` base) so a request-side field-name mismatch (BUG-066's
    actual root cause — apps/api's pre-fix `HandoffRequest` shared zero
    field names with this schema) 422s immediately instead of silently
    generating a report from empty defaults.
    """

    slots: SlotData = Field(default_factory=SlotData)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    scale_scores: list[ScaleScore] = Field(default_factory=list)
    risk_events: list[dict[str, str]] = Field(
        default_factory=list,
        description="Safety events during the session",
    )
    ocr_documents: list[dict[str, str]] = Field(
        default_factory=list,
        description="OCR-parsed document blocks",
    )
    prior_handoff: str | None = Field(
        default=None,
        description="Previous handoff report markdown (for longitudinal delta)",
    )
    is_first_visit: bool = Field(default=True)
    # BUG-069 follow-up (F5 metadata enrichment, 2026-07-25): optional,
    # additive real-value fields for sections 1/2's demographic/timing
    # requests — previously structurally absent (v4.3/v4.5's "기록 없음"/
    # "미수집" grounded fallback exists precisely because no field ever
    # carried a real value). `None` means "not provided by apps/api"
    # (pre-existing sessions, or a caller that hasn't upgraded) and
    # `_build_user_content` keeps rendering the v4.3 fallback text in that
    # case — the "기록 없음"/"미수집" grounding discipline is NOT removed,
    # only bypassed when a real value is actually present.
    patient_gender: str | None = Field(
        default=None,
        description="Patient gender, e.g. 'M'/'F' (PatientProfile.gender, "
        "plaintext, not encrypted) — None if unavailable",
    )
    session_started_at: str | None = Field(
        default=None,
        description="Session start timestamp, ISO 8601 (Session.created_at) "
        "— None if unavailable",
    )
    session_ended_at: str | None = Field(
        default=None,
        description="Session submission timestamp, ISO 8601 "
        "(Session.submitted_at) — None if the session was never submitted",
    )

    model_config = ConfigDict(extra="forbid")


class HandoffOutput(AgentOutput):
    """Output from the handoff generator agent."""

    report_markdown: str = Field(
        ...,
        description="Full handoff report in Markdown format",
    )
    report_json: dict | None = Field(
        default=None,
        description="Structured JSON parsed from the 12-section report",
    )
    report_pdf_base64: str | None = Field(
        default=None,
        description="Base64-encoded PDF of the report (None if unavailable)",
    )
    trend_plot_base64: str | None = Field(
        default=None,
        description="Base64-encoded PNG of longitudinal trend line chart",
    )
    evidence_packets: list[EvidencePacket] = Field(default_factory=list)
    missing_slots: list[str] = Field(
        default_factory=list,
        description="Slot names that were not collected",
    )
    risk_level: RiskLevel = Field(default=RiskLevel.none)
    requires_human_review: bool = Field(default=False)
