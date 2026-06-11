"""Auth schemas — PRD §5.1 /auth/register, /auth/login, /auth/refresh.

Hardening:
- `extra="forbid"` on every model — silently dropping unknown fields (e.g.,
  a forged "role": "super_admin") is a defense-in-depth weakness (M-7).
- Phone normalization runs on the cleaned input so equality guards can't be
  bypassed by punctuation (M-8).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

# E.164 in raw form (international) or KR domestic 010-xxxx-xxxx (after stripping).
_E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")
_KR_PHONE_PATTERN = re.compile(r"^010\d{7,8}$")


def _normalize_phone(value: str) -> str:
    """Strip whitespace/dashes/parens THEN validate. Returns canonical form."""
    cleaned = re.sub(r"[\s\-()]", "", value)
    if not (_E164_PATTERN.match(cleaned) or _KR_PHONE_PATTERN.match(cleaned)):
        raise ValueError("invalid_phone_format")
    return cleaned


class ConsentsIn(BaseModel):
    """PRD FR-001 + FR-026 4-consent split (+ optional voice for FR-034)."""

    tos: bool
    privacy: bool
    sensitive: bool
    risk_notification: bool = Field(alias="riskNotification")
    voice: bool | None = None  # FR-034 optional

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class GuardianConsentIn(BaseModel):
    """FR-027 — under-14 guardian flow. Phase 2 enforces verification; Demo schema-only."""

    guardian_name: str = Field(alias="guardianName")
    guardian_phone: str = Field(alias="guardianPhone")
    verification_method: Literal["phone_kyc", "family_relation_doc"] = Field(
        alias="verificationMethod"
    )
    verification_token: str = Field(alias="verificationToken")
    consents: ConsentsIn

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("guardian_phone")
    @classmethod
    def _check_phone(cls, v: str) -> str:
        return _normalize_phone(v)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)  # policy validation in service layer
    name: str = Field(min_length=1, max_length=30)
    birth_year: int = Field(alias="birthYear", ge=1900, le=2100)
    gender: Literal["male", "female", "other"]
    phone: str
    region: str = Field(min_length=1)
    emergency_contact: str = Field(alias="emergencyContact")
    target_hospital_id: UUID | None = Field(default=None, alias="targetHospitalId")
    consents: ConsentsIn
    guardian_consent: GuardianConsentIn | None = Field(
        default=None, alias="guardianConsent"
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("phone", "emergency_contact")
    @classmethod
    def _phone_format(cls, v: str) -> str:
        return _normalize_phone(v)

    @model_validator(mode="after")
    def _emergency_not_same_as_phone(self) -> RegisterRequest:
        if self.phone == self.emergency_contact:
            raise ValueError("emergency_contact_same_as_phone")
        return self


class TokenPair(BaseModel):
    user_id: UUID = Field(alias="userId")
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    expires_in: int = Field(alias="expiresIn")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: Literal["patient", "clinician", "org_admin"]

    model_config = ConfigDict(extra="forbid")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(alias="refreshToken")
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True, extra="forbid")


# Standard envelope per PRD §5.1.
class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorBody
    meta: dict[str, Any] | None = None


SuccessData = Annotated[Any, "envelope.data"]


class SuccessResponse(BaseModel):
    success: bool = True
    data: Any
