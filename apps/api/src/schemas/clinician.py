"""Clinician dashboard response schemas (PRD §5.1, §5.4 /dashboard*).

Read-only Phase 1a slice. PRD §0 ownership: this surface decrypts patient PII
for the clinician seat — every read is recorded in audit_logs by the router
layer (`require_clinician_or_admin` dependency).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RiskBadge(BaseModel):
    level: str
    category: str | None
    detected_at: datetime = Field(alias="detectedAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class PatientListItem(BaseModel):
    user_id: UUID = Field(alias="userId")
    email: EmailStr
    name: str
    birth_year: int = Field(alias="birthYear")
    is_minor: bool = Field(alias="isMinor")
    latest_session_id: UUID | None = Field(default=None, alias="latestSessionId")
    latest_session_status: str | None = Field(default=None, alias="latestSessionStatus")
    latest_session_at: datetime | None = Field(default=None, alias="latestSessionAt")
    latest_risk: RiskBadge | None = Field(default=None, alias="latestRisk")
    risk_event_count: int = Field(default=0, alias="riskEventCount")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SessionSummary(BaseModel):
    id: UUID
    status: str
    created_at: datetime = Field(alias="createdAt")
    submitted_at: datetime | None = Field(default=None, alias="submittedAt")
    risk_event_count: int = Field(default=0, alias="riskEventCount")
    latest_risk: RiskBadge | None = Field(default=None, alias="latestRisk")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ConsentSnapshotOut(BaseModel):
    tos: bool
    privacy: bool
    sensitive: bool
    risk_notification: bool = Field(alias="riskNotification")
    collected_at: datetime = Field(alias="collectedAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class PatientDetail(BaseModel):
    user_id: UUID = Field(alias="userId")
    email: EmailStr
    name: str
    birth_year: int = Field(alias="birthYear")
    is_minor: bool = Field(alias="isMinor")
    gender: str | None
    phone: str | None
    region: str | None
    emergency_contact: str | None = Field(default=None, alias="emergencyContact")
    consent: ConsentSnapshotOut | None
    sessions: list[SessionSummary]

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str  # decrypted server-side; not echoed to non-clinician roles
    input_modality: str = Field(alias="inputModality")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class RiskEventOut(BaseModel):
    id: UUID
    level: str
    category: str | None
    status: str
    legal_basis: str | None = Field(default=None, alias="legalBasis")
    trigger_message_id: UUID | None = Field(default=None, alias="triggerMessageId")
    ai_evidence: dict[str, Any] | None = Field(default=None, alias="aiEvidence")
    detected_at: datetime = Field(alias="detectedAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SessionDetail(BaseModel):
    id: UUID
    patient_id: UUID = Field(alias="patientId")
    status: str
    created_at: datetime = Field(alias="createdAt")
    submitted_at: datetime | None = Field(default=None, alias="submittedAt")
    messages: list[MessageOut]
    risk_events: list[RiskEventOut] = Field(alias="riskEvents")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
