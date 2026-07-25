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

from contracts.safety import (
    RiskCategory,
    RiskLevel,
    SafetyAssessment,
    SafetyEvidence,
    SafetyResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog
from src.models.consent import ConsentSnapshot
from src.models.session import RiskEvent

logger = logging.getLogger(__name__)


# BUG-062 fix — single source of truth for ai-server's safety-classifier
# category vocabulary -> platform `RiskCategory`, shared by BOTH:
# (1) `to_safety_assessment` below (pre-gate `/ai/safety/classify` wire
#     response translation, formerly `ai_client.py`'s inline
#     `_SAFETY_CATEGORY_MAP`/`_SAFETY_CATEGORY_PRIORITY`), and
# (2) `services/chat.py::_map_crisis_category` (the CVR-051
#     orchestrator-crisis-gate translation) — that function now imports
#     `CRISIS_CATEGORY_PRIORITY` from here instead of keeping its own copy,
#     per the fix wave's "single source, not two parallel maps" directive.
#
# Priority order (most clinically specific/urgent first) matters because a
# turn can carry multiple co-occurring category tags; first match wins for
# the single-value `RiskCategory` field (the full tag list is preserved
# separately as clinician-facing evidence — see `chat.py::
# _crisis_evidence_keywords`, unaffected by this relocation).
CRISIS_CATEGORY_PRIORITY: tuple[tuple[str, RiskCategory], ...] = (
    ("suicidal_ideation", RiskCategory.SUICIDE),
    ("suicide", RiskCategory.SUICIDE),
    ("self_harm", RiskCategory.SELF_HARM),
    ("self_harm_overdose", RiskCategory.SELF_HARM),
    ("harm_to_others", RiskCategory.OTHER_HARM),
    ("distress", RiskCategory.ACUTE_DISTRESS),
    ("despair", RiskCategory.ACUTE_DISTRESS),
)


def map_crisis_category(
    categories: list[str], *, default: RiskCategory = RiskCategory.NONE
) -> RiskCategory:
    """Map ai-server's merged category tags to the platform `RiskCategory`,
    using `CRISIS_CATEGORY_PRIORITY`'s priority order. `default` lets each
    caller pick its own safe fallback for an empty/unmatched tag list (the
    pre-gate safety-classify path defaults to `NONE`; the CVR-051
    orchestrator-crisis path in `chat.py` defaults to `SELF_HARM` — see
    that call site for why)."""
    for tag, category in CRISIS_CATEGORY_PRIORITY:
        if tag in categories:
            return category
    return default


_WIRE_RISK_LEVEL_MAP: dict[str, RiskLevel] = {
    "none": RiskLevel.LOW,
    "low": RiskLevel.LOW,
    "medium": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH,
    "critical": RiskLevel.CRITICAL,
}


def to_safety_assessment(wire: SafetyResponse) -> SafetyAssessment:
    """BUG-062 fix — translate ai-server's real `/ai/safety/classify` wire
    response (`contracts.safety.SafetyResponse`, field-identical to
    `SafetyOutput`) into the platform's internal `SafetyAssessment`
    (`RiskLevel`/`RiskCategory` enums `handle_safety_result`/
    `handle_unavailable_classifier` consume). Replaces the manual mapping
    previously hand-built inline in `ai_client.py::AIClient.safety_classify`
    (the interim BUG-062 mitigation) — now the ONLY place this translation
    happens, per the fix wave's single-source-of-truth directive."""
    level = _WIRE_RISK_LEVEL_MAP.get(wire.risk_level, RiskLevel.LOW)
    category = map_crisis_category(wire.categories, default=RiskCategory.NONE)
    return SafetyAssessment(
        level=level,
        category=category,
        evidence=SafetyEvidence(
            matched_keywords=list(wire.flagged_phrases),
            classifier=f"ai-server:ctrs{wire.ctrs_level}",
            confidence=float(wire.confidence),
        ),
        latency_ms=0,
    )


# v3 FR-044 — 2024-01부터 자살예방상담전화(1393)·정신건강상담전화(1577-0199)는
# 자살예방 통합번호 109로 통합됐다. 모바일(MOCK_HOTLINES)과 동일하게 맞춘다.
HOTLINES = [
    {"name": "자살예방 통합번호", "number": "109"},
    {"name": "응급의료", "number": "119"},
    {"name": "경찰", "number": "112"},
]

RouteTarget = Literal["/emergency", "/self_hotline"]


class RiskDetectedPayload(TypedDict):
    level: str
    category: str
    riskEventId: str  # FR-011/022 — client PATCHes /risk_events/:id with aloneStatus
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


def _build_unavailable_response() -> SafetyAssessment:
    """M-1: conservative MEDIUM when classifier unavailable."""
    return SafetyAssessment(
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
    risk_event_id: uuid.UUID,
    trigger_message_id: uuid.UUID,
    consent_opted_in: bool,
    reason: str,
) -> RiskDetectedPayload:
    route: RouteTarget = "/emergency" if consent_opted_in else "/self_hotline"
    return RiskDetectedPayload(
        level=level.value,
        category=category.value,
        riskEventId=str(risk_event_id),
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
    safety: SafetyAssessment,
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
        # BUG-076 fix (CVR-055/056 "옵션 A"): MEDIUM + a suicide/self-harm
        # -family category still persists a RiskEvent (status=
        # "pending_reclassify", the same status already used for the
        # classifier-unavailable path — CHECK constraint already allows it,
        # migration 0012) so a passive-SI/CTRS-3-shaped disclosure leaves a
        # clinician-reviewable trace instead of only a log line no one reads
        # (CVR-055 finding: "log severity only... under-triage double
        # failure" — slot contamination + zero structured signal). Client-
        # facing routing/notification policy is UNCHANGED — no `routeTo`,
        # no hotlines payload, no consent/notification dispatch; this is a
        # storage-only addition, not a new alert tier. Plain MEDIUM without
        # an SI-family category (e.g. generic "despair"/"distress" tags)
        # keeps the pre-existing log-only behavior — narrowing the new
        # persistence to the categories BUG-076's live repro was actually
        # about, not every MEDIUM hit.
        if safety.category in (RiskCategory.SUICIDE, RiskCategory.SELF_HARM):
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
                status="pending_reclassify",
                notified_to=None,
                legal_basis=None,
                consent_snapshot_id=consent["id"] if consent else None,
            )
            db.add(risk_event)
            await db.flush()
            db.add(
                AuditLog(
                    actor_id=patient_id,
                    actor_role="patient",
                    action="safety.medium_si_logged",
                    resource_type="risk_event",
                    resource_id=risk_event.id,
                    audit_metadata={
                        "level": safety.level.value,
                        "category": safety.category.value,
                        "classifier": safety.evidence.classifier,
                    },
                )
            )
        # No client routing regardless — the chat continues unchanged.
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
    # CVR-051 self-check finding (RM-1): `risk_event.id` is a Python-side
    # `default=uuid.uuid4` — SQLAlchemy only evaluates it during flush, and
    # `SessionLocal`/every caller's AsyncSession here runs `autoflush=False`
    # (`src/db.py`). Reading `.id` below without this flush returns `None`
    # — both the `AuditLog.resource_id` FK and the `riskEventId` field
    # `_payload_for` puts on the wire (FR-011/022's PATCH target) would
    # silently ship the literal string `"None"`. Flushing (not committing —
    # the caller still owns the transaction boundary) makes the DB assign
    # the real id before either read.
    await db.flush()

    db.add(
        AuditLog(
            actor_id=patient_id,
            actor_role="patient",
            action="safety.detected",
            resource_type="risk_event",
            resource_id=risk_event.id,
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
        risk_event_id=risk_event.id,
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

    CVR-053 fix: category is `RiskCategory.NONE`, not `OTHER_HARM` (타해).
    A classifier-infrastructure outage is not a harm-to-others detection —
    labeling it `OTHER_HARM` overstates the (unknown) clinical content of
    the flagged message, the same category-fidelity defect class CVR-051
    fixed elsewhere in this file (see `map_crisis_category`/
    `to_safety_assessment` above, now this path's single source too).
    """
    consent_opted_in = bool(consent and consent["risk_notification"])
    consent_id = consent["id"] if consent else None

    risk_event = RiskEvent(
        patient_id=patient_id,
        session_id=session_id,
        level=RiskLevel.MEDIUM.value,
        category=RiskCategory.NONE.value,
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
    # CVR-051 self-check finding (RM-1) — same flush-before-read fix as
    # `handle_safety_result` above; see that call site's comment.
    await db.flush()
    db.add(
        AuditLog(
            actor_id=patient_id,
            actor_role="patient",
            action="safety.unavailable",
            resource_type="risk_event",
            resource_id=risk_event.id,
            audit_metadata={"reason": "ai_server_down"},
        )
    )

    return _payload_for(
        level=RiskLevel.MEDIUM,
        category=RiskCategory.NONE,
        risk_event_id=risk_event.id,
        trigger_message_id=trigger_message_id,
        consent_opted_in=consent_opted_in,
        reason="classifier_unavailable",
    )
