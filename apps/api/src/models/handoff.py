"""HandoffReport — structured pre-consult report, one per session (FR-010/018).

PRD §5.2. Generation is async (BackgroundTasks now, Celery later — see
src/services/handoff.py): the row is created `generating`, then flipped to
`ready` with `content`, or `failed` with `failure_reason`. `content` mirrors
the `contracts.handoff.HandoffResponse` shape produced by apps/ai-server.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class HandoffReport(Base):
    __tablename__ = "handoff_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('generating','ready','failed')",
            name="ck_handoff_reports_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="generating"
    )
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
