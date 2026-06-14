"""POST /ai/chat/respond — request / response schema.

Single source of truth between apps/api (consumer, WS gateway) and
apps/ai-server (producer, LLM dialogue). PRD §0.3 contract — change requires
both PRDs updated simultaneously. SLA: 첫 토큰 < 800ms (PRD §4.1).

Separation of concerns:
- AI server generates the assistant reply AND decides which of the structured
  intake items have been collected so far (`progress.collected_items`). The
  13-item taxonomy is an AI-domain decision; the platform only displays the
  ratio and persists it on the session.
- Streaming (`ai:token`) is deferred until the AI server exposes SSE; this
  contract is the non-streaming full-reply shape consumed for `ai:complete`.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str = Field(description="'user' | 'ai' | 'system'")
    content: str

    model_config = ConfigDict(extra="forbid")


class ChatProgress(BaseModel):
    """Intake completeness — drives the patient-facing progress bar (FR-004).

    `ratio` is AI-computed (collected / total) and is the value the platform
    trusts for display + the §5.5 flow gate (≥0.7 → questionnaire step).
    """

    collected_items: list[str] = Field(
        default_factory=list,
        description="Keys of the structured items gathered so far (e.g. "
        "'chief_complaint', 'onset'). Cumulative across the conversation.",
    )
    total_items: int = Field(default=13, ge=1)
    ratio: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ChatRequest(BaseModel):
    session_id: UUID
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Conversation so far, oldest-first (decrypted by platform).",
    )

    model_config = ConfigDict(extra="forbid")


class ChatResponse(BaseModel):
    reply: str = Field(min_length=1)
    model_used: str = Field(description="e.g. 'claude-opus-4-8', 'solar-pro-3'")
    progress: ChatProgress
    latency_ms: int = Field(ge=0, description="Server-measured wall-clock")

    model_config = ConfigDict(extra="forbid")
