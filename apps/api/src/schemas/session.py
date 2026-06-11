"""Session / Message / RiskEvent — request & response shapes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionOut(BaseModel):
    session_id: UUID = Field(alias="sessionId")
    status: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# ────────── WebSocket frames ──────────


class WSAuthConnect(BaseModel):
    """C→S initial frame."""

    type: str = Field(default="auth:connect", pattern="^auth:connect$")
    payload: WSAuthConnectPayload

    model_config = ConfigDict(extra="forbid")


class WSAuthConnectPayload(BaseModel):
    access_token: str = Field(alias="accessToken", min_length=10)
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class WSUserMessage(BaseModel):
    """C→S after auth:connected."""

    type: str = Field(default="user:message", pattern="^user:message$")
    payload: WSUserMessagePayload

    model_config = ConfigDict(extra="forbid")


class WSUserMessagePayload(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    input_modality: str = Field(default="text", alias="inputModality")
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=64)
    stt_transcription_id: UUID | None = Field(default=None, alias="sttTranscriptionId")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# Forward-ref resolution at import end
WSAuthConnect.model_rebuild()
WSUserMessage.model_rebuild()
