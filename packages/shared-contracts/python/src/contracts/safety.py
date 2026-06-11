"""POST /ai/safety/classify — request / response schema.

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.
SLA: p95 < 1,000 ms (PRD §4.1).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(StrEnum):
    """PRD §5.1 risk:detected event categories."""

    SELF_HARM = "self_harm"
    SUICIDE = "suicide"
    ACUTE_DISTRESS = "acute_distress"
    OTHER_HARM = "other_harm"  # 타해
    NONE = "none"


class SafetyEvidence(BaseModel):
    """Why the classifier returned this level. Surfaced in audit + clinician UI."""

    matched_keywords: list[str] = Field(default_factory=list)
    classifier: str = Field(description="e.g. 'keyword-v1', 'llm-anthropic-claude-3'")
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class SafetyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    prev_context: list[str] = Field(
        default_factory=list,
        description="Most recent N messages (oldest-first). Used as context for "
        "classifier disambiguation. Bounded so the request stays small.",
        max_length=10,
    )

    model_config = ConfigDict(extra="forbid")


class SafetyResponse(BaseModel):
    level: RiskLevel
    category: RiskCategory
    evidence: SafetyEvidence
    latency_ms: int = Field(ge=0, description="Server-measured wall-clock")

    model_config = ConfigDict(extra="forbid")
