"""POST /ai/stt/transcribe — request / response schema.

Single source of truth between apps/api (consumer, REST gateway) and
apps/ai-server (producer, STT adapter chain). PRD §0.3 contract — change requires
both PRDs updated simultaneously. SLA: < 2,000ms (PRD §4.1).

The platform sends raw audio bytes (base64) + hints; the AI server runs the
vendor fallback chain (SK A.dot → Whisper) and returns text + confidence +
which vendor won. The platform owns consent, storage, and the 48h purge — the
AI server is a pure transcription function.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class STTVendor(StrEnum):
    SKT_ADOT = "skt-adot"
    WHISPER_OPENAI = "whisper-openai"
    WHISPER_LOCAL = "whisper-local"


class STTFallbackStep(BaseModel):
    vendor: str
    status: str = Field(description="'ok' | 'timeout' | 'error' | 'skipped'")
    latency_ms: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class STTRequest(BaseModel):
    audio_base64: str = Field(min_length=1, description="Opus or 16kHz mono PCM WAV")
    encoding: str = Field(description="'opus' | 'pcm16'")
    sample_rate_hz: int = Field(default=16000, ge=8000, le=48000)
    lang: str = Field(default="ko-KR")
    prev_context: str = Field(
        default="",
        max_length=500,
        description="Previous user utterance — accuracy hint.",
    )

    model_config = ConfigDict(extra="forbid")


class STTResponse(BaseModel):
    text: str = Field(description="Transcript; may be empty on silence/noise.")
    confidence: float = Field(ge=0.0, le=1.0)
    vendor: STTVendor
    duration_ms: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    fallback_chain: list[STTFallbackStep] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
