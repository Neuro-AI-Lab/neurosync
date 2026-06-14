"""Handoff report orchestration (FR-010/018).

Async generation flow:
1. POST /submit creates a `generating` handoff_reports row (in the request txn).
2. A background task (`generate_report_task`) opens its own DB session, gathers
   the session's messages / questionnaires / risk events, calls
   apps/ai-server `/ai/handoff/generate`, and flips the row to `ready`/`failed`.
3. GET /report composes the response: deterministic facts (questionnaires, risk
   signals, patient demographics) are assembled here regardless of generation
   state, so the clinician sees *something* even while the narrative is pending.

NOTE: BackgroundTasks (in-process) is the Demo executor. The seam is
`generate_report_task(session_id)` — swapping it for a Celery task later is a
one-line change at the call site (PRD/PLAN 1b.3).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from contracts.handoff import (
    HandoffMessage,
    HandoffQuestionnaire,
    HandoffRequest,
    HandoffRiskSignal,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.encryption import decrypt_str
from src.db import SessionLocal
from src.models.audit_log import AuditLog
from src.models.handoff import HandoffReport
from src.models.patient_profile import PatientProfile
from src.models.questionnaire import QuestionnaireResult
from src.models.session import Message, RiskEvent, Session
from src.schemas.handoff import (
    HandoffReportOut,
    QuestionnaireScore,
    ReportPatient,
    ReportRiskSignal,
)
from src.services.ai_client import AIClient, AIClientError, get_ai_client

logger = logging.getLogger(__name__)


def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


def _profile_aad(user_id: uuid.UUID, column: str) -> bytes:
    return f"patient_profiles.{column}:{user_id}".encode()


async def create_pending_report(
    db: AsyncSession, *, session_id: uuid.UUID
) -> HandoffReport:
    """Create (or reset) the report row for a session, status=generating.

    Re-submission regenerates: an existing row is flipped back to generating.
    """
    existing = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = existing.scalar_one_or_none()
    if report is None:
        report = HandoffReport(session_id=session_id, status="generating")
        db.add(report)
    else:
        report.status = "generating"
        report.content = None
        report.failure_reason = None
        report.generated_at = None
    await db.flush()
    return report


async def _build_request(
    db: AsyncSession, session_id: uuid.UUID
) -> HandoffRequest:
    msg_rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    messages: list[HandoffMessage] = []
    for m in msg_rows.scalars().all():
        try:
            content = decrypt_str(
                m.content_encrypted, aad=_message_aad(session_id, m.id)
            )
        except Exception:
            content = ""
        messages.append(
            HandoffMessage(message_id=m.id, role=m.role, content=content)
        )

    q_rows = await db.execute(
        select(QuestionnaireResult).where(
            QuestionnaireResult.session_id == session_id
        )
    )
    questionnaires = [
        HandoffQuestionnaire(
            type=q.type, total_score=q.total_score, severity=q.severity
        )
        for q in q_rows.scalars().all()
    ]

    r_rows = await db.execute(
        select(RiskEvent).where(RiskEvent.session_id == session_id)
    )
    risk_signals = [
        HandoffRiskSignal(
            level=r.level,
            category=r.category,
            source_message_id=r.trigger_message_id,
        )
        for r in r_rows.scalars().all()
    ]

    return HandoffRequest(
        session_id=session_id,
        messages=messages,
        questionnaires=questionnaires,
        risk_signals=risk_signals,
    )


async def generate_report_task(
    session_id: uuid.UUID, *, ai_client: AIClient | None = None
) -> None:
    """Background entrypoint. Opens its own session; never raises to the caller."""
    client = ai_client or get_ai_client()
    async with SessionLocal() as db:
        try:
            request = await _build_request(db, session_id)
            response = await client.handoff_generate(request)
        except AIClientError as exc:
            logger.warning(
                "handoff.generate.failed",
                extra={"session_id": str(session_id), "error": str(exc)},
            )
            await _mark_failed(db, session_id, reason="ai_server_unavailable")
            return
        except Exception:  # noqa: BLE001 — defensive: a bg task must not crash silently
            logger.exception("handoff.generate.unexpected", extra={"session_id": str(session_id)})
            await _mark_failed(db, session_id, reason="internal_error")
            return

        await _mark_ready(db, session_id, content=response.model_dump(mode="json"))


async def _mark_ready(
    db: AsyncSession, session_id: uuid.UUID, *, content: dict
) -> None:
    row = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = row.scalar_one_or_none()
    if report is None:
        return
    report.status = "ready"
    report.content = content
    report.failure_reason = None
    report.generated_at = datetime.now(UTC)

    sess_row = await db.execute(select(Session).where(Session.id == session_id))
    sess = sess_row.scalar_one_or_none()
    if sess is not None:
        sess.status = "report_ready"

    db.add(
        AuditLog(
            actor_id=None,
            actor_role="system",
            action="handoff.report.ready",
            resource_type="handoff_report",
            resource_id=report.id,
            audit_metadata={"session_id": str(session_id)},
        )
    )
    await db.commit()


async def _mark_failed(
    db: AsyncSession, session_id: uuid.UUID, *, reason: str
) -> None:
    row = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = row.scalar_one_or_none()
    if report is None:
        return
    report.status = "failed"
    report.failure_reason = reason
    db.add(
        AuditLog(
            actor_id=None,
            actor_role="system",
            action="handoff.report.failed",
            resource_type="handoff_report",
            resource_id=report.id,
            audit_metadata={"session_id": str(session_id), "reason": reason},
        )
    )
    await db.commit()


async def build_report_response(
    db: AsyncSession, session_id: uuid.UUID
) -> HandoffReportOut | None:
    """Compose the GET /report payload. Returns None if no report row exists."""
    row = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = row.scalar_one_or_none()
    if report is None:
        return None

    sess_row = await db.execute(select(Session).where(Session.id == session_id))
    sess = sess_row.scalar_one_or_none()
    if sess is None:
        return None

    # Deterministic facts — always composed server-side (not AI output).
    q_rows = await db.execute(
        select(QuestionnaireResult).where(
            QuestionnaireResult.session_id == session_id
        )
    )
    questionnaires = [
        QuestionnaireScore(
            type=q.type, total_score=q.total_score, severity=q.severity
        )
        for q in q_rows.scalars().all()
    ]

    r_rows = await db.execute(
        select(RiskEvent)
        .where(RiskEvent.session_id == session_id)
        .order_by(RiskEvent.detected_at.desc())
    )
    risk_signals = [
        ReportRiskSignal(
            level=r.level,
            category=r.category,
            trigger_message_id=r.trigger_message_id,
        )
        for r in r_rows.scalars().all()
    ]

    patient = await _report_patient(db, sess.patient_id)

    return HandoffReportOut(
        report_id=report.id,
        session_id=session_id,
        status=report.status,
        generated_at=report.generated_at,
        failure_reason=report.failure_reason,
        patient=patient,
        questionnaires=questionnaires,
        risk_signals=risk_signals,
        narrative=report.content,
    )


async def _report_patient(
    db: AsyncSession, patient_id: uuid.UUID
) -> ReportPatient | None:
    row = await db.execute(
        select(PatientProfile).where(PatientProfile.user_id == patient_id)
    )
    profile = row.scalar_one_or_none()
    if profile is None:
        return None
    try:
        name = decrypt_str(
            profile.name_encrypted, aad=_profile_aad(patient_id, "name")
        )
    except Exception:
        name = "(이름 복호화 실패)"
    return ReportPatient(
        id=patient_id,
        name=name,
        birth_year=profile.birth_year,
        gender=profile.gender,
    )
