"""Phase 1b intake plumbing — questionnaires, submit/report, risk ack.

DB-backed (auto-skipped without Postgres, like test_clinician.py). The async
Handoff generation is monkeypatched to a no-op so these tests stay deterministic
and offline — the AI generation itself is covered separately (apps/ai-server).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

import src.api.v1.sessions as sessions_module
from src.core.security import create_token
from src.models.session import RiskEvent, Session
from src.models.user import User


def _register_patient(client, email: str | None = None) -> dict:
    email = email or f"pt-{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Hunter2-Strong!Password",
            "name": "환자",
            "birthYear": datetime.now(tz=UTC).year - 30,
            "gender": "male",
            "phone": "010-1111-2222",
            "region": "서울",
            "emergencyContact": "010-3333-4444",
            "consents": {
                "tos": True,
                "privacy": True,
                "sensitive": True,
                "riskNotification": True,
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


def _create_session(client, access: str) -> str:
    res = client.post(
        "/api/v1/sessions", headers={"Authorization": f"Bearer {access}"}
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["sessionId"]


@pytest.fixture(autouse=True)
def _no_bg_generation(monkeypatch):
    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(sessions_module, "generate_report_task", _noop)


# ────────── questionnaires (FR-006/007) ──────────


@pytest.mark.asyncio
async def test_phq9_submit_scores_and_classifies(client):
    auth = _register_patient(client)
    access = auth["accessToken"]
    sid = _create_session(client, access)

    res = client.post(
        f"/api/v1/sessions/{sid}/questionnaires",
        headers={"Authorization": f"Bearer {access}"},
        json={"type": "PHQ9", "answers": [2, 2, 2, 2, 2, 2, 2, 2, 1]},
    )
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["totalScore"] == 17
    assert data["severity"] == "moderately_severe"
    assert data["type"] == "PHQ9"


@pytest.mark.asyncio
async def test_questionnaire_wrong_count_rejected(client):
    auth = _register_patient(client)
    access = auth["accessToken"]
    sid = _create_session(client, access)

    res = client.post(
        f"/api/v1/sessions/{sid}/questionnaires",
        headers={"Authorization": f"Bearer {access}"},
        json={"type": "PHQ9", "answers": [1, 2, 3]},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ANSWER_COUNT_MISMATCH"


@pytest.mark.asyncio
async def test_questionnaire_other_patient_session_404(client):
    owner = _register_patient(client)
    sid = _create_session(client, owner["accessToken"])

    intruder = _register_patient(client)
    res = client.post(
        f"/api/v1/sessions/{sid}/questionnaires",
        headers={"Authorization": f"Bearer {intruder['accessToken']}"},
        json={"type": "GAD7", "answers": [0, 0, 0, 0, 0, 0, 0]},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "SESSION_NOT_FOUND"


# ────────── submit + report (FR-010/018/017) ──────────


@pytest.mark.asyncio
async def test_submit_freezes_session_and_creates_report(client, db_session, test_settings):
    auth = _register_patient(client)
    access = auth["accessToken"]
    sid = _create_session(client, access)

    client.post(
        f"/api/v1/sessions/{sid}/questionnaires",
        headers={"Authorization": f"Bearer {access}"},
        json={"type": "GAD7", "answers": [1, 1, 1, 1, 1, 1, 1]},
    )

    res = client.post(
        f"/api/v1/sessions/{sid}/submit",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert res.status_code == 202, res.text
    data = res.json()["data"]
    assert data["status"] == "report_generating"
    assert data["estimatedSeconds"] == 30
    assert data["reportId"]

    # Session is frozen — further questionnaire writes are rejected (FR-010).
    again = client.post(
        f"/api/v1/sessions/{sid}/questionnaires",
        headers={"Authorization": f"Bearer {access}"},
        json={"type": "PHQ9", "answers": [0] * 9},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "SESSION_NOT_EDITABLE"


@pytest.mark.asyncio
async def test_get_report_composes_questionnaires(client, db_session, test_settings):
    auth = _register_patient(client)
    access = auth["accessToken"]
    sid = _create_session(client, access)
    client.post(
        f"/api/v1/sessions/{sid}/questionnaires",
        headers={"Authorization": f"Bearer {access}"},
        json={"type": "PHQ9", "answers": [3, 3, 3, 3, 3, 3, 3, 3, 3]},
    )
    client.post(
        f"/api/v1/sessions/{sid}/submit",
        headers={"Authorization": f"Bearer {access}"},
    )

    clinician = User(
        email=f"doc-{uuid.uuid4().hex[:8]}@hospital.example",
        password_hash="x",
        role="clinician",
    )
    db_session.add(clinician)
    await db_session.flush()
    token = create_token(
        clinician.id, "access", role="clinician", settings=test_settings
    )

    res = client.get(
        f"/api/v1/sessions/{sid}/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "generating"  # bg generation was stubbed out
    phq = next(q for q in data["questionnaires"] if q["type"] == "PHQ9")
    assert phq["totalScore"] == 27
    assert phq["severity"] == "severe"
    assert data["narrative"] is None


@pytest.mark.asyncio
async def test_report_requires_clinician(client):
    auth = _register_patient(client)
    access = auth["accessToken"]
    sid = _create_session(client, access)
    client.post(
        f"/api/v1/sessions/{sid}/submit",
        headers={"Authorization": f"Bearer {access}"},
    )
    # Patient cannot read the clinician report surface.
    res = client.get(
        f"/api/v1/sessions/{sid}/report",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert res.status_code == 403


# ────────── risk event ack (FR-011/022) ──────────


@pytest.mark.asyncio
async def test_patient_acknowledges_own_risk_event(client, db_session, test_settings):
    auth = _register_patient(client)
    access = auth["accessToken"]
    patient_id = uuid.UUID(auth["userId"])
    sid = uuid.UUID(_create_session(client, access))

    risk = RiskEvent(
        patient_id=patient_id,
        session_id=sid,
        level="critical",
        category="suicide",
        status="detected",
        legal_basis="consent:risk_notification",
    )
    db_session.add(risk)
    await db_session.commit()

    res = client.patch(
        f"/api/v1/risk_events/{risk.id}",
        headers={"Authorization": f"Bearer {access}"},
        json={"aloneStatus": "alone"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "acknowledged"
    assert data["aloneStatus"] == "alone"
    assert data["acknowledgedAt"]


@pytest.mark.asyncio
async def test_cannot_acknowledge_other_patients_risk_event(
    client, db_session, test_settings
):
    owner = _register_patient(client)
    owner_id = uuid.UUID(owner["userId"])
    sess = Session(patient_id=owner_id, status="in_progress")
    db_session.add(sess)
    await db_session.flush()
    risk = RiskEvent(
        patient_id=owner_id,
        session_id=sess.id,
        level="high",
        category="self_harm",
        status="detected",
    )
    db_session.add(risk)
    await db_session.commit()

    intruder = _register_patient(client)
    res = client.patch(
        f"/api/v1/risk_events/{risk.id}",
        headers={"Authorization": f"Bearer {intruder['accessToken']}"},
        json={"aloneStatus": "with_someone"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RISK_EVENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_alone_status_rejected(client, db_session, test_settings):
    auth = _register_patient(client)
    access = auth["accessToken"]
    patient_id = uuid.UUID(auth["userId"])
    sid = uuid.UUID(_create_session(client, access))
    risk = RiskEvent(
        patient_id=patient_id, session_id=sid, level="high", status="detected"
    )
    db_session.add(risk)
    await db_session.commit()

    res = client.patch(
        f"/api/v1/risk_events/{risk.id}",
        headers={"Authorization": f"Bearer {access}"},
        json={"aloneStatus": "maybe"},
    )
    assert res.status_code == 422
