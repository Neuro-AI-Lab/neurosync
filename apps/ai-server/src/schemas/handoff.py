"""Schemas for the Handoff Generator agent."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from src.agents.base import AgentInput, AgentOutput
from src.schemas.common import EvidencePacket, RiskLevel

RiskLevelLabel = Literal["none", "low", "medium", "high", "critical"]
CtrsLabel = Literal["1", "2", "3", "4", "5"]

_RISK_LABELS: Final[dict[str, RiskLevelLabel]] = {
    "none": "none",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}
_CTRS_LABELS: Final[dict[str, CtrsLabel]] = {
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
}
_VALID_RISK_LABELS: Final = frozenset(_RISK_LABELS)
_VALID_CTRS_LABELS: Final = frozenset(_CTRS_LABELS)


class RiskEvent(BaseModel):
    """A safety event in the local legacy handoff-agent input.

    This model is not the public ``POST /ai/handoff/generate`` request shape;
    that boundary uses the shared ``HandoffRiskSignal`` contract. Local
    severity labels remain strict (ISS-021): an invalid
    ``risk_level``/``ctrs_level`` is rejected instead of being silently
    floored to ``medium`` downstream. Extra legacy keys are preserved. An
    event with no severity keys remains valid and floors to medium downstream
    (issue #21).
    """

    model_config = ConfigDict(extra="allow")

    risk_level: RiskLevelLabel | SkipJsonSchema[None] = Field(
        default_factory=lambda: None,
        exclude_if=lambda value: value is None,
        description="One of: none | low | medium | high | critical (omit the field if unknown)",
    )
    ctrs_level: CtrsLabel | SkipJsonSchema[None] = Field(
        default_factory=lambda: None,
        exclude_if=lambda value: value is None,
        description="Crisis Triage Rating Scale, ASCII digit '1'-'5' (omit the field if unknown)",
    )

    @field_validator("risk_level", mode="before")
    @classmethod
    def _normalize_risk_level(cls, value: object) -> RiskLevelLabel:
        if value is None:
            # Explicit null is a malformed severity claim — reject. A genuinely
            # ABSENT field never reaches this validator (pydantic skips
            # validators for unset fields) and keeps the None default.
            raise ValueError("risk_level must not be null — omit the field instead")
        raw = str(value).strip().lower()
        normalized = _RISK_LABELS.get(raw)
        if normalized is None:
            raise ValueError(
                f"risk_level must be one of {sorted(_VALID_RISK_LABELS)}, got {value!r}"
            )
        return normalized

    @field_validator("ctrs_level", mode="before")
    @classmethod
    def _normalize_ctrs_level(cls, value: object) -> CtrsLabel:
        if value is None:
            raise ValueError("ctrs_level must not be null — omit the field instead")
        raw = str(value).strip()
        # ASCII-strict: rejects unicode digits ("١", "①"), out-of-range, non-digits.
        normalized = _CTRS_LABELS.get(raw)
        if normalized is None:
            raise ValueError(f"ctrs_level must be an ASCII digit '1'-'5', got {value!r}")
        return normalized


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
    """Local legacy input adapted from the public shared request contract."""

    slots: SlotData = Field(default_factory=SlotData)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    scale_scores: list[ScaleScore] = Field(default_factory=list)
    risk_events: list[RiskEvent] = Field(
        default_factory=list,
        max_length=100,
        description="Safety events during the session (severity labels strictly validated)",
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
