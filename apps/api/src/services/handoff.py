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

from contracts.handoff import HandoffRequest, ScaleScore, SlotData
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.encryption import decrypt_str
from src.db import SessionLocal
from src.models.audit_log import AuditLog
from src.models.handoff import HandoffReport
from src.models.patient_profile import PatientProfile
from src.models.questionnaire import QuestionnaireResult
from src.models.session import Message, RiskEvent, Session
from src.models.user import User
from src.schemas.handoff import (
    HandoffReportOut,
    QuestionnaireScore,
    ReportPatient,
    ReportRiskSignal,
)
from src.services.ai_client import AIClient, AIClientError, get_ai_client
from src.services.clinician import _can_access_patient  # ISS-022: shared org-access rule

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


async def _build_slots(db: AsyncSession, session_id: uuid.UUID) -> SlotData:
    """BUG-066 fix — resolves the fix_wave_design.md UNVERIFIED open item:
    apps/api DOES persist per-session slot data, in `Session.clinical_slots`
    (JSONB, populated in the background by `services/chat.py::
    _extract_slots_bg` — a flat dict keyed by ClinicalSlotAgent's
    canonical-12 slot names, per BUG-050). `_build_request` never read this
    column before this fix — every handoff request silently shipped
    `slots=SlotData()` (all-`None` defaults), which is why BUG-066's live
    probe found a vacuous 12-section report despite real filled slots
    existing in the DB. Unknown/stale dict keys (defensive — `clinical_slots`
    is caller-controlled JSONB, not schema-enforced) are filtered against
    `SlotData.model_fields` rather than passed through, so a stray key can
    never trip `SlotData`'s own `extra="forbid"`."""
    row = await db.execute(select(Session.clinical_slots).where(Session.id == session_id))
    raw = row.scalar_one_or_none() or {}
    filtered = {k: v for k, v in raw.items() if k in SlotData.model_fields}
    return SlotData(**filtered)


async def _build_patient_metadata(
    db: AsyncSession, session_id: uuid.UUID
) -> tuple[str | None, str | None, str | None]:
    """BUG-069 follow-up (F5 metadata enrichment, 2026-07-25): resolves the
    real `patient_gender`/`session_started_at`/`session_ended_at` values
    `HandoffRequest` gained additively — previously nothing threaded these
    into the handoff pipeline at all (v4.3's "기록 없음"/"미수집" fallback
    was the only rendering, by design, given that absence). Returns `(None,
    None, None)` per-field wherever the underlying row/column is missing —
    never guesses; `handoff_generator.py::_build_user_content` keeps its
    existing grounded fallback text for any `None` here."""
    sess_row = await db.execute(
        select(Session.created_at, Session.submitted_at, Session.patient_id).where(
            Session.id == session_id
        )
    )
    sess = sess_row.first()
    if sess is None:
        return None, None, None
    created_at, submitted_at, patient_id = sess

    gender_row = await db.execute(
        select(PatientProfile.gender).where(PatientProfile.user_id == patient_id)
    )
    gender = gender_row.scalar_one_or_none()

    return (
        gender,
        created_at.isoformat() if created_at is not None else None,
        submitted_at.isoformat() if submitted_at is not None else None,
    )


async def _build_request(
    db: AsyncSession, session_id: uuid.UUID
) -> HandoffRequest:
    """BUG-066 fix: assembles the REAL `HandoffInput`-shaped request
    (`conversation_history`/`scale_scores`/`risk_events`/`slots`) instead of
    the pre-fix invented `HandoffMessage`/`HandoffQuestionnaire`/
    `HandoffRiskSignal` shape ai-server's `extra`-permissive (pre-fix)
    `HandoffInput` silently dropped in full."""
    msg_rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    conversation_history: list[dict[str, str]] = []
    for m in msg_rows.scalars().all():
        try:
            content = decrypt_str(
                m.content_encrypted, aad=_message_aad(session_id, m.id)
            )
        except Exception:
            content = ""
        conversation_history.append({"role": m.role, "content": content})

    q_rows = await db.execute(
        select(QuestionnaireResult).where(
            QuestionnaireResult.session_id == session_id
        )
    )
    scale_scores = [
        ScaleScore(scale_name=q.type, total_score=q.total_score, severity=q.severity)
        for q in q_rows.scalars().all()
    ]

    r_rows = await db.execute(
        select(RiskEvent).where(RiskEvent.session_id == session_id)
    )
    risk_events: list[dict[str, str]] = [
        {
            "level": r.level,
            "category": r.category or "",
            "source_message_id": str(r.trigger_message_id) if r.trigger_message_id else "",
        }
        for r in r_rows.scalars().all()
    ]

    slots = await _build_slots(db, session_id)
    patient_gender, session_started_at, session_ended_at = await _build_patient_metadata(
        db, session_id
    )

    return HandoffRequest(
        session_id=str(session_id),
        slots=slots,
        conversation_history=conversation_history,
        scale_scores=scale_scores,
        risk_events=risk_events,
        patient_gender=patient_gender,
        session_started_at=session_started_at,
        session_ended_at=session_ended_at,
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
    db: AsyncSession,
    *,
    actor: User,
    session_id: uuid.UUID,
    require_delivered: bool = True,
) -> HandoffReportOut | None:
    """Compose the GET /report payload. Returns None if no report row exists,
    or if the session's patient is outside the actor's organization (ISS-022).

    v3 §6-B — 수동 전달: 기본적으로 **전달된 리포트만** 노출한다. 환자가
    [전달하기]를 누르기 전(delivered_at IS NULL)에는 의료진이 볼 수 없다. 리포트
    본문은 여전히 clinician 전용이며, 이 게이트는 '언제 보이는가'만 통제한다."""
    row = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = row.scalar_one_or_none()
    if report is None:
        return None
    if require_delivered and report.delivered_at is None:
        # 아직 환자가 전달하지 않음 — 존재 자체를 노출하지 않는다(None → 404).
        return None

    sess_row = await db.execute(select(Session).where(Session.id == session_id))
    sess = sess_row.scalar_one_or_none()
    if sess is None:
        return None

    # ISS-022: org-scope — the session's patient must belong to the actor's org.
    hosp_row = await db.execute(
        select(PatientProfile.target_hospital_id).where(
            PatientProfile.user_id == sess.patient_id
        )
    )
    if not _can_access_patient(actor, hosp_row.scalar_one_or_none()):
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
