"""Handoff report HTTP response shapes (PRD §5.1 GET /report).

The clinician-facing payload merges deterministic facts (questionnaires, risk
signals, patient demographics — composed by the platform) with the AI-generated
`narrative` (stored verbatim from `contracts.handoff.HandoffResponse`). The
narrative is null until generation completes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QuestionnaireScore(BaseModel):
    type: str
    total_score: int = Field(alias="totalScore")
    severity: str

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ReportRiskSignal(BaseModel):
    level: str
    category: str | None
    trigger_message_id: UUID | None = Field(default=None, alias="triggerMessageId")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ReportPatient(BaseModel):
    id: UUID
    name: str
    birth_year: int = Field(alias="birthYear")
    gender: str | None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class HandoffReportOut(BaseModel):
    report_id: UUID = Field(alias="reportId")
    session_id: UUID = Field(alias="sessionId")
    status: str  # generating | ready | failed
    generated_at: datetime | None = Field(default=None, alias="generatedAt")
    failure_reason: str | None = Field(default=None, alias="failureReason")
    patient: ReportPatient | None
    questionnaires: list[QuestionnaireScore]
    risk_signals: list[ReportRiskSignal] = Field(alias="riskSignals")
    # Raw AI narrative (contracts.handoff.HandoffResponse) — null until ready.
    narrative: dict[str, Any] | None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SubmitAccepted(BaseModel):
    session_id: UUID = Field(alias="sessionId")
    status: str
    report_id: UUID = Field(alias="reportId")
    estimated_seconds: int = Field(alias="estimatedSeconds")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
