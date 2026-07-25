"""Schemas for the Safety Classifier agent."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import AgentInput, AgentOutput
from src.schemas.common import CTRSLevel, RiskLevel


class SafetyInput(AgentInput):
    """Input to the safety classifier.

    BUG-066 fix: `extra="forbid"` scoped to this subclass (not the shared
    `AgentInput` base — see that class's docstring) so any future
    apps/api<->ai-server field-name drift on this specific contract 422s
    immediately instead of silently dropping fields (BUG-062's root cause).
    """

    user_message: str = Field(..., description="Raw user message text")
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Recent conversation turns [{role, content}, ...]",
    )

    model_config = ConfigDict(extra="forbid")


class SafetyClassification(BaseModel):
    """LLM-produced safety classification (JSON output schema)."""

    risk_level: RiskLevel = Field(default=RiskLevel.none)
    categories: list[str] = Field(
        default_factory=list,
        description="Detected risk categories (e.g. 'suicidal_ideation', 'self_harm')",
    )
    flagged_phrases: list[str] = Field(
        default_factory=list,
        description="Specific phrases that triggered the classification",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence 0-1",
    )
    reason_summary: str = Field(
        default="",
        description="One-line explanation (never raw CoT)",
    )


class SafetyOutput(AgentOutput):
    """Output from the safety classifier agent."""

    risk_level: RiskLevel = Field(default=RiskLevel.none)
    categories: list[str] = Field(default_factory=list)
    flagged_phrases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rule_triggered: bool = Field(
        default=False,
        description="Whether the rule-based classifier fired",
    )
    llm_risk_level: RiskLevel | None = Field(
        default=None,
        description="Risk level from LLM alone (before merge)",
    )
    rule_risk_level: RiskLevel | None = Field(
        default=None,
        description="Risk level from rule engine alone (before merge)",
    )
    ctrs_level: int = Field(
        default=CTRSLevel.STABLE,
        ge=1,
        le=5,
        description="CTRS level: 1=emergency, 5=stable",
    )
    requires_human_review: bool = Field(default=False)
    crisis_protocol_activated: bool = Field(
        default=False,
        description="True if CTRS 1-2 — immediate crisis intervention needed",
    )
