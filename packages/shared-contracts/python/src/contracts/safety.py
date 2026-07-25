"""POST /ai/safety/classify — request / response schema.

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.
SLA: p95 < 1,000 ms (PRD §4.1).

BUG-062 fix (EXP-031 fix_wave_design.md, Option B): `SafetyRequest`/
`SafetyResponse` below are now field-identical to ai-server's real wire
schema (`apps/ai-server/src/schemas/safety.py::SafetyInput`/`SafetyOutput`) —
this is what makes `AIClient.safety_classify` a plain generic `_post` call
instead of a hand-built adapter. `SafetyAssessment` (below, formerly named
`SafetyResponse` pre-fix) is the PLATFORM's own internal vocabulary
(`RiskLevel`/`RiskCategory` enums) that `services/safety.py`'s domain layer
translates the wire `SafetyResponse` into — the translation (including the
category-priority reduction previously hand-built inline in `ai_client.py`)
now lives in `services/safety.py::to_safety_assessment`, a single source
shared with the CVR-051 orchestrator-crisis category vocabulary
(`services/chat.py`'s `_CRISIS_CATEGORY_PRIORITY`, itself now imported from
`services/safety.py` — see that module for the single-source mapping).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(StrEnum):
    """Platform-internal risk vocabulary (never sent to/from ai-server
    directly) — `services/safety.py::to_safety_assessment` maps the wire
    `SafetyResponse.risk_level` (which additionally has `"none"`) into this
    enum, collapsing `"none"` to `LOW` (no separate "no risk" tier
    platform-side; see that function for the mapping)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(StrEnum):
    """PRD §5.1 risk:detected event categories (platform-internal)."""

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
    """Wire request — field-identical to ai-server's `SafetyInput`
    (BUG-062 fix). `session_id` is required by ai-server's shared
    `AgentInput` base; apps/api's pre-gate caller has no natural per-message
    session concept for this call, so it sends the platform session id."""

    session_id: str
    user_message: str = Field(min_length=1, max_length=4000)
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Recent conversation turns [{role, content}, ...], "
        "oldest-first. Bounded so the request stays small.",
        max_length=10,
    )

    model_config = ConfigDict(extra="forbid")


class SafetyResponse(BaseModel):
    """Wire response — mirrors ai-server's real `SafetyOutput` fields
    (BUG-062 fix). Deliberately NOT `extra="forbid"`: ai-server's actual
    JSON also carries the shared `AgentOutput` base fields (`model_used`,
    `prompt_version`, `latency_ms`, `reason_summary`, `prompts_degraded`),
    none of which this platform-facing subset needs — forbidding them would
    make this contract brittle to any future additive `AgentOutput` field."""

    risk_level: str = Field(
        description="ai-server's RiskLevel wire value — includes 'none', "
        "'low', 'medium', 'high', 'critical' (superset of this platform's "
        "own `RiskLevel` enum, translated by `services/safety.py`)."
    )
    categories: list[str] = Field(default_factory=list)
    flagged_phrases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ctrs_level: int = Field(default=5, ge=1, le=5)
    requires_human_review: bool = Field(default=False)
    crisis_protocol_activated: bool = Field(default=False)

    model_config = ConfigDict(extra="ignore")


class SafetyAssessment(BaseModel):
    """Platform-internal safety result (formerly the pre-fix `SafetyResponse`
    shape) — what `services/safety.py`/`services/chat.py`'s escalation logic
    actually consumes. Built by `services/safety.py::to_safety_assessment`
    from a wire `SafetyResponse`, or constructed directly for the
    classifier-unavailable fallback / the orchestrator-crisis path."""

    level: RiskLevel
    category: RiskCategory
    evidence: SafetyEvidence
    latency_ms: int = Field(ge=0, description="Server-measured wall-clock")

    model_config = ConfigDict(extra="forbid")
