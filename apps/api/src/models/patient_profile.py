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
    is_minor is app-managed (set at registration from birth_year per FR-027);
    a Postgres STORED generated column cannot use CURRENT_DATE (non-immutable).
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
    emergency_contact_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    target_hospital_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    pseudonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pseudonymous_id: Mapped[str | None] = mapped_column(Text, unique=True)

    user = relationship("User", back_populates="profile")
