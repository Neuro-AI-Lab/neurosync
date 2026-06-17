"""AudioRecording / STTTranscription — PRD §5.2 (FR-033/036).

Audio bytes themselves live in object storage (file_url); the DB holds metadata
+ the 48h purge window. Transcription text is AES-256-GCM encrypted like
message content (it is patient speech, treated identically — PRD §4.3.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class AudioRecording(Base):
    __tablename__ = "audio_recordings"
    __table_args__ = (
        CheckConstraint(
            "encoding IN ('opus','pcm16')", name="ck_audio_recordings_encoding"
        ),
        Index(
            "idx_audio_delete_after",
            "delete_after",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    encoding: Mapped[str] = mapped_column(String(16), nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    consent_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("consent_snapshots.id"), nullable=False
    )
    delete_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class STTTranscription(Base):
    __tablename__ = "stt_transcriptions"
    __table_args__ = (Index("idx_stt_session", "session_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    audio_recording_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("audio_recordings.id", ondelete="SET NULL")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    text_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    vendor: Mapped[str] = mapped_column(String(24), nullable=False)
    lang: Mapped[str] = mapped_column(String(16), nullable=False, default="ko-KR")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    fallback_chain: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    edited_by_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
