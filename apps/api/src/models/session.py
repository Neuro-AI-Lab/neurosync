"""Session / Message / RiskEvent — PRD §5.2.

Phase 1a Day 8+ scope. Embedding column (pgvector, FR-RAG) is deferred to
Phase 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress','submitted','report_ready','closed')",
            name="ck_sessions_status",
        ),
        Index("idx_sessions_patient", "patient_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # FR-004 — AI-reported intake completeness for the progress bar.
    progress_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    collected_items: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user','ai','system')", name="ck_messages_role"
        ),
        CheckConstraint(
            "input_modality IN ('text','voice')", name="ck_messages_modality"
        ),
        Index("idx_messages_session", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    input_modality: Mapped[str] = mapped_column(
        String(10), nullable=False, default="text"
    )
    stt_transcription_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session = relationship("Session", back_populates="messages")


class RiskEvent(Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        CheckConstraint(
            "level IN ('low','medium','high','critical')", name="ck_risk_events_level"
        ),
        CheckConstraint(
            "status IN ('detected','acknowledged','resolved','dismissed')",
            name="ck_risk_events_status",
        ),
        CheckConstraint(
            "alone_status IS NULL OR alone_status IN ('alone','with_someone')",
            name="ck_risk_events_alone_status",
        ),
        Index("idx_risk_events_patient", "patient_id", "detected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sessions.id")
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str | None] = mapped_column(String(32))
    trigger_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id")
    )
    context_message_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True))
    )
    ai_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="detected")
    notified_to: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    consent_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("consent_snapshots.id")
    )
    # FR-011/022 — patient response on the emergency screen.
    alone_status: Mapped[str | None] = mapped_column(String(16))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
