"""QuestionnaireResult — PHQ-9 / GAD-7 standardized intake (FR-006/007).

PRD §5.2. Answers are non-PII Likert integers, so they're stored in clear
JSONB (no AES envelope). `severity` is clinician-reference only — never shown
to the patient as a diagnosis (PRD §5.1 주의).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class QuestionnaireResult(Base):
    __tablename__ = "questionnaire_results"
    __table_args__ = (
        # v3 FR-040 — 문항 주입형 문진 4종. AUDITC/PHQ4는 top1 라우팅 결과로
        # 선택될 수 있어야 하므로 제약을 확장한다 (마이그레이션 0008).
        CheckConstraint(
            "type IN ('PHQ9','GAD7','AUDITC','PHQ4')",
            name="ck_questionnaire_results_type",
        ),
        UniqueConstraint(
            "session_id", "type", name="uq_questionnaire_results_session_type"
        ),
        Index("idx_questionnaire_results_session", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    answers: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
