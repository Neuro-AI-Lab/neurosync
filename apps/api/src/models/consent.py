"""ConsentSnapshot — append-only per PRD §5.2 (FR-001 / FR-026 / FR-027)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class ConsentSnapshot(Base):
    __tablename__ = "consent_snapshots"
    __table_args__ = (
        Index("idx_consent_user", "user_id", "collected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tos: Mapped[bool] = mapped_column(Boolean, nullable=False)
    privacy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_notification: Mapped[bool] = mapped_column(Boolean, nullable=False)  # FR-026
    guardian_consent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # FR-027
    tos_version: Mapped[str] = mapped_column(String(32), nullable=False)
    privacy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    collected_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
