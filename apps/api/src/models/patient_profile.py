"""PatientProfile — encrypted PII columns per PRD §5.2."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class PatientProfile(Base):
    """PRD §5.2 patient_profiles.

    name/phone/emergency_contact are AES-256 encrypted blobs (BYTEA).

    BUG-065 fix: `is_minor` was a Postgres `GENERATED ALWAYS AS STORED`
    column using the non-immutable `CURRENT_DATE` — PG16 rejects this
    (fresh-DB `alembic upgrade head` could never complete), see
    `alembic/versions/0001_initial_auth_schema.py`'s docstring for the full
    rationale. Now a plain column: the app sets it explicitly at INSERT time
    (`api/v1/auth.py::register`, reusing `_is_minor()` — the SAME helper
    already used independently for the FR-027 guardian-consent gate, now the
    single source of truth instead of an app function plus a DB-computed
    shadow of it).
    """

    __tablename__ = "patient_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_minor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gender: Mapped[str | None] = mapped_column(Text)
    phone_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    region: Mapped[str | None] = mapped_column(Text)
    # v3 수정 1 — 사회인구학적 항목 확장 (모두 선택, 코드 저장 · 마이그레이션 0011).
    # 비-PII 범주형이라 gender/region처럼 평문 Text. 소득·종교는 민감(prefer_not 허용).
    marital_status: Mapped[str | None] = mapped_column(Text)
    household_type: Mapped[str | None] = mapped_column(Text)
    education_level: Mapped[str | None] = mapped_column(Text)
    occupation: Mapped[str | None] = mapped_column(Text)
    employment_status: Mapped[str | None] = mapped_column(Text)
    income_level: Mapped[str | None] = mapped_column(Text)
    religion: Mapped[str | None] = mapped_column(Text)
    emergency_contact_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    target_hospital_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    pseudonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pseudonymous_id: Mapped[str | None] = mapped_column(Text, unique=True)

    user = relationship("User", back_populates="profile")
