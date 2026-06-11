"""Unit tests for src.services.safety (no DB / no HTTP).

Covers consent-aware routing (PRD §4.5.2) and the conservative
classifier-unavailable fallback (PRD §8.1).
"""

from __future__ import annotations

import uuid

import pytest
from contracts.safety import (
    RiskCategory,
    RiskLevel,
    SafetyEvidence,
    SafetyResponse,
)

from src.services.safety import (
    HOTLINES,
    ConsentSnapshotRef,
    handle_safety_result,
    handle_unavailable_classifier,
)


def _make_response(level: RiskLevel, category: RiskCategory) -> SafetyResponse:
    return SafetyResponse(
        level=level,
        category=category,
        evidence=SafetyEvidence(
            matched_keywords=["dummy"] if level != RiskLevel.LOW else [],
            classifier="test",
            confidence=0.85 if level != RiskLevel.LOW else 0.0,
        ),
        latency_ms=5,
    )


def _consent(opt_in: bool) -> ConsentSnapshotRef:
    return {"id": uuid.uuid4(), "risk_notification": opt_in}


class _FakeSession:
    """Stand-in AsyncSession that just records `.add()` calls."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)


# ────────── handle_safety_result ──────────


@pytest.mark.asyncio
async def test_low_returns_none_and_writes_nothing():
    db = _FakeSession()
    result = await handle_safety_result(
        db,  # type: ignore[arg-type]
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        safety=_make_response(RiskLevel.LOW, RiskCategory.NONE),
        consent=_consent(True),
    )
    assert result is None
    assert db.added == []


@pytest.mark.asyncio
async def test_medium_logs_but_does_not_route_or_persist():
    db = _FakeSession()
    result = await handle_safety_result(
        db,  # type: ignore[arg-type]
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        safety=_make_response(RiskLevel.MEDIUM, RiskCategory.ACUTE_DISTRESS),
        consent=_consent(True),
    )
    assert result is None
    assert db.added == []


@pytest.mark.asyncio
async def test_critical_opted_in_routes_to_emergency():
    db = _FakeSession()
    pid = uuid.uuid4()
    trig = uuid.uuid4()
    consent = _consent(True)

    result = await handle_safety_result(
        db,  # type: ignore[arg-type]
        patient_id=pid,
        session_id=uuid.uuid4(),
        trigger_message_id=trig,
        context_message_ids=[uuid.uuid4()],
        safety=_make_response(RiskLevel.CRITICAL, RiskCategory.SUICIDE),
        consent=consent,
    )

    assert result is not None
    assert result["level"] == "critical"
    assert result["routeTo"] == "/emergency"
    assert result["triggerMessageId"] == str(trig)
    assert result["hotlines"] == HOTLINES
    # RiskEvent persisted with consent snapshot id + opt-in legal basis
    assert len(db.added) == 2
    risk_event = db.added[0]
    assert risk_event.legal_basis == "consent:risk_notification"
    assert risk_event.consent_snapshot_id == consent["id"]
    assert risk_event.notified_to == []
    audit = db.added[1]
    assert audit.action == "safety.detected"
    assert audit.audit_metadata["consent_opted_in"] is True


@pytest.mark.asyncio
async def test_critical_opted_out_routes_to_self_hotline():
    db = _FakeSession()
    consent = _consent(False)

    result = await handle_safety_result(
        db,  # type: ignore[arg-type]
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        safety=_make_response(RiskLevel.CRITICAL, RiskCategory.SUICIDE),
        consent=consent,
    )

    assert result is not None
    # Per PRD §4.5.2 opt-out — hotlines only, no emergency routing
    assert result["routeTo"] == "/self_hotline"
    assert result["hotlines"] == HOTLINES
    risk_event = db.added[0]
    assert risk_event.legal_basis == "self_hotline_only"
    assert risk_event.notified_to is None
    assert risk_event.consent_snapshot_id == consent["id"]


@pytest.mark.asyncio
async def test_critical_with_no_consent_snapshot_treats_as_opt_out():
    """Defensive: if for some reason no consent_snapshot exists, default to opt-out."""
    db = _FakeSession()
    result = await handle_safety_result(
        db,  # type: ignore[arg-type]
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        safety=_make_response(RiskLevel.CRITICAL, RiskCategory.SUICIDE),
        consent=None,
    )
    assert result is not None
    assert result["routeTo"] == "/self_hotline"
    risk_event = db.added[0]
    assert risk_event.legal_basis == "self_hotline_only"
    assert risk_event.consent_snapshot_id is None


@pytest.mark.asyncio
async def test_high_also_blocks_consent_aware():
    db = _FakeSession()
    result = await handle_safety_result(
        db,  # type: ignore[arg-type]
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        safety=_make_response(RiskLevel.HIGH, RiskCategory.SELF_HARM),
        consent=_consent(True),
    )
    assert result is not None
    assert result["level"] == "high"
    assert result["routeTo"] == "/emergency"


# ────────── handle_unavailable_classifier (M-1) ──────────


@pytest.mark.asyncio
async def test_unavailable_classifier_writes_pending_reclassify():
    db = _FakeSession()
    consent = _consent(True)
    payload = await handle_unavailable_classifier(
        db,  # type: ignore[arg-type]
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        consent=consent,
    )
    # Always returns a payload — silence is unacceptable
    assert payload is not None
    assert payload["routeTo"] == "/emergency"  # opted in
    assert payload["reason"] == "classifier_unavailable"
    risk_event = db.added[0]
    assert risk_event.level == "medium"
    assert risk_event.status == "pending_reclassify"
    assert risk_event.ai_evidence["classifier"] == "unavailable"
    assert risk_event.consent_snapshot_id == consent["id"]


@pytest.mark.asyncio
async def test_unavailable_classifier_respects_opt_out():
    db = _FakeSession()
    payload = await handle_unavailable_classifier(
        db,  # type: ignore[arg-type]
        patient_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        consent=_consent(False),
    )
    assert payload["routeTo"] == "/self_hotline"
    risk_event = db.added[0]
    assert risk_event.legal_basis == "self_hotline_only"
