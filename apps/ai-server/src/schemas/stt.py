"""Schemas for the STT (Speech-to-Text) agent.

Contract per docs/ai/agents/06_stt.md + docs/ai/api/SKT_A_X_API.md §6.

Note: SKT A.X STT does NOT expose per-response confidence
(spec §6.7 explicitly warns against fabricating one). `confidence` is optional
and set only when the vendor provides it. Downstream code must treat
`confidence is None` as "unknown quality — rely on other signals (empty text,
user re-utterance, etc.)".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import AgentInput, AgentOutput

STTMode = Literal["batch", "streaming"]


class STTSegment(BaseModel):
    """Utterance-level segment as returned by vendor."""

    text: str = Field(..., description="Segment transcript")
    start_ms: int = Field(default=0, ge=0)
    end_ms: int = Field(default=0, ge=0)
    speaker: int | None = Field(
        default=None, description="Speaker index if diarization was applied"
    )

    model_config = ConfigDict(extra="ignore")


class STTInput(AgentInput):
    """Input for STTAgent (metadata only — audio bytes passed alongside)."""

    patient_id: str = Field(..., description="Pseudonymous patient identifier")
    filename: str = Field(default="audio.mp3")
    mode: STTMode = Field(default="batch")
    language: str = Field(default="ko-KR")
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Word boosting for domain terms. Neuro-Sync default includes "
            "'우울감', '불면', '불안', '자살', '자해'."
        ),
    )
    agreement_of_data_collection: bool = Field(
        default=False,
        description="SKT A.X 데이터 수집 동의 필드. 앱의 음성 동의와 별도 관리 (FR-036).",
    )
    message_id_override: str | None = Field(
        default=None,
        description="Override for SKT message_id. Defaults to session_id-based UUID.",
    )


class STTOutput(AgentOutput):
    """Output from STTAgent.

    FR-035: `user_confirmed=False` on initial return. Caller (UI) must obtain
    explicit user confirmation before feeding transcript into LLM pipeline.
    """

    session_id: str
    patient_id: str
    text: str = Field(default="", description="Full concatenated transcript")
    segments: list[STTSegment] = Field(default_factory=list)
    confidence: float | None = Field(
        default=None,
        description=(
            "Vendor-provided confidence. None when vendor does not expose one "
            "(SKT A.X STT case — spec §6.7)."
        ),
    )
    mode: STTMode = Field(default="batch")
    vendor: str = Field(default="skt-ak-stt")
    audio_duration_ms: int = Field(default=0, ge=0)
    audio_retention_expires_at: str | None = Field(
        default=None,
        description="ISO8601 — spec FR-036: audio must be deleted within 48h.",
    )
    user_confirmed: bool = Field(
        default=False,
        description=(
            "FR-035: STT transcript must NOT be forwarded to LLM until the user "
            "reviews & confirms. Callers set this True after user tap in UI."
        ),
    )
    timestamp: str = Field(default="")
