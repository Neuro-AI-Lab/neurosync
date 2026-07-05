"""Schemas for the Handoff Generator agent."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput
from src.schemas.common import EvidencePacket, RiskLevel


class SlotData(BaseModel):
    """Collected clinical slot data from the dialogue session.

    Fields map to ALL_SLOT_KEYS in clinical_slot.py.
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


class ScaleScore(BaseModel):
    """Standardized questionnaire score."""

    scale_name: str = Field(..., description="e.g. PHQ-9, GAD-7")
    total_score: int
    severity: str = Field(default="", description="e.g. mild, moderate, severe")


class HandoffInput(AgentInput):
    """Input to the handoff generator."""

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
