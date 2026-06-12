"""Clinician read service — decrypts PII and assembles dashboard payloads.

Phase 1a Demo simplification: every authenticated clinician sees every patient.
PRD §0.1 organization-scoped RLS lands in Phase 2.
"""

from __future__ import annotations

import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.encryption import decrypt_str
from src.models.consent import ConsentSnapshot
from src.models.patient_profile import PatientProfile
from src.models.session import Message, RiskEvent, Session
from src.models.user import User
from src.schemas.clinician import (
    ConsentSnapshotOut,
    MessageOut,
    PatientDetail,
    PatientListItem,
    RiskBadge,
    RiskEventOut,
    SessionDetail,
    SessionSummary,
)


def _decrypt(blob: bytes | None, *, aad: bytes | None = None) -> str | None:
    if blob is None:
        return None
    try:
        return decrypt_str(blob, aad=aad)
    except Exception:
        # Decryption failure should be logged + surfaced as null — never block
        # the entire patient list from rendering due to one bad row.
        return None


def _profile_aad(user_id: uuid.UUID, column: str) -> bytes:
    return f"patient_profiles.{column}:{user_id}".encode()


def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


async def list_patients(db: AsyncSession, *, limit: int) -> list[PatientListItem]:
    rows = await db.execute(
        select(User, PatientProfile)
        .join(PatientProfile, PatientProfile.user_id == User.id)
        .where(User.role == "patient", User.deleted_at.is_(None))
        .order_by(desc(User.created_at))
        .limit(limit)
    )

    items: list[PatientListItem] = []
    for user, profile in rows.all():
        # Latest session (any status) for the patient.
        latest_session_row = await db.execute(
            select(Session)
            .where(Session.patient_id == user.id)
            .order_by(desc(Session.created_at))
            .limit(1)
        )
        latest_session = latest_session_row.scalar_one_or_none()

        latest_risk: RiskBadge | None = None
        risk_count = 0
        if latest_session is not None:
            risk_count_row = await db.execute(
                select(func.count(RiskEvent.id)).where(
                    RiskEvent.session_id == latest_session.id
                )
            )
            risk_count = int(risk_count_row.scalar() or 0)
            latest_risk_row = await db.execute(
                select(RiskEvent)
                .where(RiskEvent.session_id == latest_session.id)
                .order_by(desc(RiskEvent.detected_at))
                .limit(1)
            )
            r = latest_risk_row.scalar_one_or_none()
            if r is not None:
                latest_risk = RiskBadge(
                    level=r.level, category=r.category, detected_at=r.detected_at
                )

        name = (
            _decrypt(profile.name_encrypted, aad=_profile_aad(user.id, "name"))
            or "(이름 복호화 실패)"
        )

        items.append(
            PatientListItem(
                user_id=user.id,
                email=user.email,
                name=name,
                birth_year=profile.birth_year,
                is_minor=bool(profile.is_minor),
                latest_session_id=latest_session.id if latest_session else None,
                latest_session_status=(
                    latest_session.status if latest_session else None
                ),
                latest_session_at=(
                    latest_session.created_at if latest_session else None
                ),
                latest_risk=latest_risk,
                risk_event_count=risk_count,
            )
        )

    return items


async def get_patient_detail(
    db: AsyncSession, patient_id: uuid.UUID
) -> PatientDetail | None:
    row = await db.execute(
        select(User, PatientProfile)
        .join(PatientProfile, PatientProfile.user_id == User.id)
        .where(User.id == patient_id, User.role == "patient")
    )
    pair = row.first()
    if pair is None:
        return None
    user, profile = pair

    consent_row = await db.execute(
        select(ConsentSnapshot)
        .where(ConsentSnapshot.user_id == user.id)
        .order_by(desc(ConsentSnapshot.collected_at))
        .limit(1)
    )
    latest_consent = consent_row.scalar_one_or_none()
    consent_out: ConsentSnapshotOut | None = None
    if latest_consent is not None:
        consent_out = ConsentSnapshotOut(
            tos=latest_consent.tos,
            privacy=latest_consent.privacy,
            sensitive=latest_consent.sensitive,
            risk_notification=latest_consent.risk_notification,
            collected_at=latest_consent.collected_at,
        )

    sessions_row = await db.execute(
        select(Session)
        .where(Session.patient_id == user.id)
        .order_by(desc(Session.created_at))
    )
    sessions = list(sessions_row.scalars().all())
    summaries: list[SessionSummary] = []
    for sess in sessions:
        count_row = await db.execute(
            select(func.count(RiskEvent.id)).where(RiskEvent.session_id == sess.id)
        )
        count = int(count_row.scalar() or 0)
        latest_risk_row = await db.execute(
            select(RiskEvent)
            .where(RiskEvent.session_id == sess.id)
            .order_by(desc(RiskEvent.detected_at))
            .limit(1)
        )
        r = latest_risk_row.scalar_one_or_none()
        summaries.append(
            SessionSummary(
                id=sess.id,
                status=sess.status,
                created_at=sess.created_at,
                submitted_at=sess.submitted_at,
                risk_event_count=count,
                latest_risk=(
                    RiskBadge(
                        level=r.level, category=r.category, detected_at=r.detected_at
                    )
                    if r is not None
                    else None
                ),
            )
        )

    return PatientDetail(
        user_id=user.id,
        email=user.email,
        name=_decrypt(profile.name_encrypted, aad=_profile_aad(user.id, "name"))
        or "(이름 복호화 실패)",
        birth_year=profile.birth_year,
        is_minor=bool(profile.is_minor),
        gender=profile.gender,
        phone=_decrypt(profile.phone_encrypted, aad=_profile_aad(user.id, "phone")),
        region=profile.region,
        emergency_contact=_decrypt(
            profile.emergency_contact_encrypted,
            aad=_profile_aad(user.id, "emergency_contact"),
        ),
        consent=consent_out,
        sessions=summaries,
    )


async def get_session_detail(
    db: AsyncSession, session_id: uuid.UUID
) -> SessionDetail | None:
    sess_row = await db.execute(select(Session).where(Session.id == session_id))
    sess = sess_row.scalar_one_or_none()
    if sess is None:
        return None

    msg_rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    messages: list[MessageOut] = []
    for m in msg_rows.scalars().all():
        content = _decrypt(
            m.content_encrypted, aad=_message_aad(sess.id, m.id)
        ) or "(메시지 복호화 실패)"
        messages.append(
            MessageOut(
                id=m.id,
                role=m.role,
                content=content,
                input_modality=m.input_modality,
                created_at=m.created_at,
            )
        )

    risk_rows = await db.execute(
        select(RiskEvent)
        .where(RiskEvent.session_id == session_id)
        .order_by(desc(RiskEvent.detected_at))
    )
    risk_events: list[RiskEventOut] = []
    for r in risk_rows.scalars().all():
        risk_events.append(
            RiskEventOut(
                id=r.id,
                level=r.level,
                category=r.category,
                status=r.status,
                legal_basis=r.legal_basis,
                trigger_message_id=r.trigger_message_id,
                ai_evidence=r.ai_evidence,
                detected_at=r.detected_at,
            )
        )

    return SessionDetail(
        id=sess.id,
        patient_id=sess.patient_id,
        status=sess.status,
        created_at=sess.created_at,
        submitted_at=sess.submitted_at,
        messages=messages,
        risk_events=risk_events,
    )
