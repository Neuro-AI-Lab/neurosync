"""POST /ai/handoff/generate — request / response schema.

Single source of truth between apps/api (consumer, plumbing) and
apps/ai-server (producer, LLM generation). PRD §0.3 contract — change requires
both PRDs updated simultaneously. SLA: p95 < 30s (PRD §4.1).

Separation of concerns:
- AI server produces the *narrative* fields + citation links (`evidence`).
- Platform composes the deterministic facts (questionnaire scores, risk
  signals, patient demographics) at GET /report time — they are NOT part of
  this contract.

FR-018 안전장치: every narrative field that makes a clinical claim must be
backed by an entry in `evidence` pointing at a real source message id (원문
근거 인용 강제). The AI server is responsible for that guarantee; the platform
surfaces it verbatim.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HandoffMessage(BaseModel):
    """A decrypted conversation turn passed to the generator."""

    message_id: UUID
    role: str = Field(description="'user' | 'ai' | 'system'")
    content: str

    model_config = ConfigDict(extra="forbid")


class HandoffQuestionnaire(BaseModel):
    type: str = Field(description="'PHQ9' | 'GAD7'")
    total_score: int
    severity: str

    model_config = ConfigDict(extra="forbid")


class HandoffRiskSignal(BaseModel):
    level: str
    category: str | None = None
    source_message_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class HandoffRequest(BaseModel):
    session_id: UUID
    messages: list[HandoffMessage] = Field(default_factory=list)
    questionnaires: list[HandoffQuestionnaire] = Field(default_factory=list)
    doc_texts: list[str] = Field(default_factory=list)
    risk_signals: list[HandoffRiskSignal] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class Citation(BaseModel):
    """FR-018 원문 근거: ties a narrative field to a source message + quote."""

    field: str
    source_message_id: UUID
    quote: str

    model_config = ConfigDict(extra="forbid")


class SleepAppetiteActivity(BaseModel):
    sleep: str | None = None
    appetite: str | None = None
    activity: str | None = None

    model_config = ConfigDict(extra="forbid")


class HandoffResponse(BaseModel):
    """Structured narrative the clinician reads (PRD §5.1 GET /report)."""

    chief_complaint: str
    present_illness: str
    symptoms: list[str] = Field(default_factory=list)
    onset: str | None = None
    recent_changes: str | None = None
    triggers: list[str] = Field(default_factory=list)
    sleep_appetite_activity: SleepAppetiteActivity = Field(
        default_factory=SleepAppetiteActivity
    )
    psych_history: str | None = None
    medications: str | None = None
    documents_summary: list[str] = Field(default_factory=list)
    clinician_attention: list[str] = Field(default_factory=list)
    evidence: list[Citation] = Field(default_factory=list)
    latency_ms: int = Field(ge=0, description="Server-measured wall-clock")

    model_config = ConfigDict(extra="forbid")
