"""Safety service — bridges AI server output to risk_events + WS event payload.

Per PRD §5.5 Flow C and §4.5.2 "위기 보호 통보 정책":
- WS gateway calls this on every user:message.
- HIGH or CRITICAL + risk_notification=True → persist RiskEvent with
  `legal_basis="consent:risk_notification"`, emit `routeTo="/emergency"` +
  hotlines, queue downstream notification (Phase 2 = real SMS).
- HIGH or CRITICAL + risk_notification=False → persist RiskEvent with
  `legal_basis="self_hotline_only"`, emit `routeTo="/self_hotline"` +
  hotlines only (no emergency contact / clinician routing).
- MEDIUM → log only, no client routing.
- LOW → noop.

PRD §8.1 conservativity: when the AI classifier is unavailable, we treat
the result as MEDIUM-level "pending_reclassify" and still return a
self-hotline payload — silence is unacceptable in a life-safety domain.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal, TypedDict

from contracts.safety import RiskCategory, RiskLevel, SafetyEvidence, SafetyResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog
from src.models.consent import ConsentSnapshot
from src.models.session import RiskEvent

logger = logging.getLogger(__name__)


HOTLINES = [
    {"name": "자살예방상담전화", "number": "1393"},
    {"name": "응급의료", "number": "119"},
    {"name": "정신건강상담전화", "number": "1577-0199"},
]

RouteTarget = Literal["/emergency", "/self_hotline"]


class RiskDetectedPayload(TypedDict):
    level: str
    category: str
    triggerMessageId: str
    routeTo: RouteTarget
    hotlines: list[dict[str, str]]
    reason: str  # short human label — UI uses for analytics & telemetry


class ConsentSnapshotRef(TypedDict):
    id: uuid.UUID
    risk_notification: bool


async def latest_consent_snapshot(
    db: AsyncSession, patient_id: uuid.UUID
) -> ConsentSnapshotRef | None:
    """PRD §5.2 consent_snapshots — newest row is the authoritative state."""
    row = await db.execute(
        select(
            ConsentSnapshot.id, ConsentSnapshot.risk_notification
        )
        .where(ConsentSnapshot.user_id == patient_id)
        .order_by(ConsentSnapshot.collected_at.desc())
        .limit(1)
    )
    record = row.first()
    if record is None:
        return None
    return {"id": record[0], "risk_notification": bool(record[1])}


def _is_blocking(level: RiskLevel) -> bool:
    return level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def _build_unavailable_response() -> SafetyResponse:
    """M-1: conservative MEDIUM when classifier unavailable."""
    return SafetyResponse(
        level=RiskLevel.MEDIUM,
        category=RiskCategory.OTHER_HARM,  # closest placeholder; reclassify in Phase 2
        evidence=SafetyEvidence(
            matched_keywords=[],
            classifier="unavailable",
            confidence=0.0,
        ),
        latency_ms=0,
    )


def _payload_for(
    *,
    level: RiskLevel,
    category: RiskCategory,
    trigger_message_id: uuid.UUID,
    consent_opted_in: bool,
    reason: str,
) -> RiskDetectedPayload:
    route: RouteTarget = "/emergency" if consent_opted_in else "/self_hotline"
    return RiskDetectedPayload(
        level=level.value,
        category=category.value,
        triggerMessageId=str(trigger_message_id),
        routeTo=route,
        hotlines=HOTLINES,
        reason=reason,
    )


async def handle_safety_result(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID,
    session_id: uuid.UUID,
    trigger_message_id: uuid.UUID,
    context_message_ids: list[uuid.UUID],
    safety: SafetyResponse,
    consent: ConsentSnapshotRef | None,
) -> RiskDetectedPayload | None:
    """Persist a RiskEvent if needed and return the client-facing payload.

    Returns None when the safety result is LOW (silent ok) or MEDIUM (logged only).
    """
    if safety.level == RiskLevel.LOW:
        return None

    if safety.level == RiskLevel.MEDIUM:
        logger.info(
            "safety.medium",
            extra={
                "patient_id": str(patient_id),
                "session_id": str(session_id),
                "category": safety.category.value,
                "classifier": safety.evidence.classifier,
            },
        )
        # No client routing — the chat continues. RiskEvent skipped for MEDIUM
        # to keep the table focused on actionable events.
        return None

    # HIGH / CRITICAL path.
    consent_opted_in = bool(consent and consent["risk_notification"])
    consent_id = consent["id"] if consent else None

    legal_basis = (
        "consent:risk_notification" if consent_opted_in else "self_hotline_only"
    )
    notified_to: list[dict] | None = (
        []  # Phase 2 = actual SMS/clinician dispatch fills this with entries
        if consent_opted_in
        else None
    )

    risk_event = RiskEvent(
        patient_id=patient_id,
        session_id=session_id,
        level=safety.level.value,
        category=safety.category.value,
        trigger_message_id=trigger_message_id,
        context_message_ids=context_message_ids or None,
        ai_evidence={
            "matched_keywords": safety.evidence.matched_keywords,
            "classifier": safety.evidence.classifier,
            "confidence": safety.evidence.confidence,
            "latency_ms": safety.latency_ms,
        },
        status="detected",
        notified_to=notified_to,
        legal_basis=legal_basis,
        consent_snapshot_id=consent_id,
    )
    db.add(risk_event)

    db.add(
        AuditLog(
            actor_id=patient_id,
            actor_role="patient",
            action="safety.detected",
            resource_type="risk_event",
            audit_metadata={
                "level": safety.level.value,
                "category": safety.category.value,
                "classifier": safety.evidence.classifier,
                "consent_opted_in": consent_opted_in,
            },
        )
    )

    return _payload_for(
        level=safety.level,
        category=safety.category,
        trigger_message_id=trigger_message_id,
        consent_opted_in=consent_opted_in,
        reason="risk_detected",
    )


async def handle_unavailable_classifier(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID,
    session_id: uuid.UUID,
    trigger_message_id: uuid.UUID,
    context_message_ids: list[uuid.UUID],
    consent: ConsentSnapshotRef | None,
) -> RiskDetectedPayload:
    """M-1: AI classifier down → conservative MEDIUM with reclassify queued.

    A `pending_reclassify` RiskEvent is persisted so the Phase 2 replay job
    can re-evaluate without losing the message. The client always gets a
    self-hotline payload (consent-aware) — silence is unacceptable.
    """
    consent_opted_in = bool(consent and consent["risk_notification"])
    consent_id = consent["id"] if consent else None

    risk_event = RiskEvent(
        patient_id=patient_id,
        session_id=session_id,
        level=RiskLevel.MEDIUM.value,
        category=RiskCategory.OTHER_HARM.value,
        trigger_message_id=trigger_message_id,
        context_message_ids=context_message_ids or None,
        ai_evidence={
            "matched_keywords": [],
            "classifier": "unavailable",
            "confidence": 0.0,
            "latency_ms": 0,
        },
        status="pending_reclassify",
        notified_to=None,
        legal_basis=(
            "consent:risk_notification" if consent_opted_in else "self_hotline_only"
        ),
        consent_snapshot_id=consent_id,
    )
    db.add(risk_event)
    db.add(
        AuditLog(
            actor_id=patient_id,
            actor_role="patient",
            action="safety.unavailable",
            resource_type="risk_event",
            audit_metadata={"reason": "ai_server_down"},
        )
    )

    return _payload_for(
        level=RiskLevel.MEDIUM,
        category=RiskCategory.OTHER_HARM,
        trigger_message_id=trigger_message_id,
        consent_opted_in=consent_opted_in,
        reason="classifier_unavailable",
    )
