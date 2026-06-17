"""STT transcribe + voice-consent HTTP shapes (PRD §5.1, FR-033/034/037)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class STTTranscribeOut(BaseModel):
    transcription_id: UUID = Field(alias="transcriptionId")
    text: str
    confidence: float
    vendor: str
    duration_ms: int = Field(alias="durationMs")
    latency_ms: int = Field(alias="latencyMs")
    audio_recording_id: UUID = Field(alias="audioRecordingId")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class VoiceConsentIn(BaseModel):
    voice: bool

    model_config = ConfigDict(extra="forbid")


class VoiceConsentOut(BaseModel):
    voice: bool
    consent_snapshot_id: UUID = Field(alias="consentSnapshotId")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
