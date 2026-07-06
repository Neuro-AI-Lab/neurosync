"""GET /api/v1/clinician/* — read-only dashboard endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.core.encryption import encrypt_str
from src.core.security import hash_password
from src.models.audit_log import AuditLog
from src.models.consent import ConsentSnapshot
from src.models.handoff import HandoffReport
from src.models.patient_profile import PatientProfile
from src.models.session import Message, RiskEvent, Session
from src.models.user import Organization, User

PATIENTS_URL = "/api/v1/clinician/patients"


def _profile_aad(user_id, column):
    return f"patient_profiles.{column}:{user_id}".encode()


def _message_aad(session_id, message_id):
    return f"messages.content:{session_id}:{message_id}".encode()


async def _create_org(db_session, name: str = "Hospital") -> Organization:
    org = Organization(name=name, type="hospital")
    db_session.add(org)
    await db_session.flush()
    return org


async def _create_clinician(db_session, test_settings, *, organization_id=None) -> User:
    user = User(
        email=f"doc-{uuid.uuid4().hex[:8]}@hospital.example",
        password_hash=hash_password("Doctor!Password-2026", test_settings),
        role="clinician",
        organization_id=organization_id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _create_patient_with_session(
    db_session,
    test_settings,
    *,
    name: str = "홍길동",
    with_risk: bool = False,
    target_hospital_id=None,
) -> tuple[User, Session, RiskEvent | None]:
    user = User(
        email=f"pt-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Hunter2-Strong!Password", test_settings),
        role="patient",
    )
    db_session.add(user)
    await db_session.flush()

    profile = PatientProfile(
        user_id=user.id,
        name_encrypted=encrypt_str(
            name, aad=_profile_aad(user.id, "name"), settings=test_settings
        ),
        birth_year=datetime.now(tz=UTC).year - 30,
        gender="female",
        target_hospital_id=target_hospital_id,
        phone_encrypted=encrypt_str(
            "01011112222",
            aad=_profile_aad(user.id, "phone"),
            settings=test_settings,
        ),
        region="서울",
        emergency_contact_encrypted=encrypt_str(
            "01033334444",
            aad=_profile_aad(user.id, "emergency_contact"),
            settings=test_settings,
        ),
    )
    db_session.add(profile)
    db_session.add(
        ConsentSnapshot(
            user_id=user.id,
            tos=True,
            privacy=True,
            sensitive=True,
            risk_notification=True,
            tos_version="t1",
            privacy_version="p1",
        )
    )

    sess = Session(patient_id=user.id, status="in_progress")
    db_session.add(sess)
    await db_session.flush()

    msg = Message(
        session_id=sess.id,
        role="user",
        content_encrypted=encrypt_str(
            "테스트 메시지",
            aad=_message_aad(sess.id, uuid.uuid4()),  # AAD doesn't need to match for read
            settings=test_settings,
        ),
        input_modality="text",
    )
    db_session.add(msg)
    await db_session.flush()
    # Re-encrypt now that the real message_id is known.
    msg.content_encrypted = encrypt_str(
        "테스트 메시지",
        aad=_message_aad(sess.id, msg.id),
        settings=test_settings,
    )

    risk: RiskEvent | None = None
    if with_risk:
        risk = RiskEvent(
            patient_id=user.id,
            session_id=sess.id,
            level="critical",
            category="suicide",
            trigger_message_id=msg.id,
            ai_evidence={"matched_keywords": ["test"], "classifier": "test"},
            status="detected",
            legal_basis="consent:risk_notification",
        )
        db_session.add(risk)

    await db_session.commit()
    return user, sess, risk


# ────────── access control ──────────


@pytest.mark.asyncio
async def test_patient_role_blocked(client):
    # Register a patient and try to hit clinician endpoint.
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "blocked@example.com",
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
    assert reg.status_code == 201
    access = reg.json()["data"]["accessToken"]

    res = client.get(PATIENTS_URL, headers={"Authorization": f"Bearer {access}"})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ROLE_MISMATCH"


@pytest.mark.asyncio
async def test_no_token_returns_401(client):
    res = client.get(PATIENTS_URL)
    assert res.status_code == 401


# ────────── happy path ──────────


@pytest.mark.asyncio
async def test_list_patients_returns_decrypted_name_and_risk_badge(
    client, db_session, test_settings
):
    org = await _create_org(db_session)
    clinician = await _create_clinician(
        db_session, test_settings, organization_id=org.id
    )
    await _create_patient_with_session(
        db_session, test_settings, name="홍길동", with_risk=True, target_hospital_id=org.id
    )

    from src.core.security import create_token

    token = create_token(clinician.id, "access", role="clinician", settings=test_settings)

    res = client.get(PATIENTS_URL, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    patients = body["data"]
    assert len(patients) >= 1
    target = next(p for p in patients if p["name"] == "홍길동")
    assert target["latestRisk"]["level"] == "critical"
    assert target["riskEventCount"] == 1


@pytest.mark.asyncio
async def test_get_patient_detail_decrypts_pii(client, db_session, test_settings):
    org = await _create_org(db_session)
    clinician = await _create_clinician(
        db_session, test_settings, organization_id=org.id
    )
    patient, _, _ = await _create_patient_with_session(
        db_session, test_settings, name="김선영", target_hospital_id=org.id
    )
    from src.core.security import create_token

    token = create_token(clinician.id, "access", role="clinician", settings=test_settings)
    res = client.get(
        f"/api/v1/clinician/patients/{patient.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["name"] == "김선영"
    assert data["phone"] == "01011112222"
    assert data["emergencyContact"] == "01033334444"
    assert data["consent"]["riskNotification"] is True
    assert len(data["sessions"]) >= 1


@pytest.mark.asyncio
async def test_get_session_detail_includes_messages_and_risks(
    client, db_session, test_settings
):
    org = await _create_org(db_session)
    clinician = await _create_clinician(
        db_session, test_settings, organization_id=org.id
    )
    _, sess, _ = await _create_patient_with_session(
        db_session, test_settings, with_risk=True, target_hospital_id=org.id
    )
    from src.core.security import create_token

    token = create_token(clinician.id, "access", role="clinician", settings=test_settings)
    res = client.get(
        f"/api/v1/clinician/sessions/{sess.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["messages"][0]["content"] == "테스트 메시지"
    assert data["riskEvents"][0]["level"] == "critical"


@pytest.mark.asyncio
async def test_missing_patient_returns_404(client, db_session, test_settings):
    clinician = await _create_clinician(db_session, test_settings)
    from src.core.security import create_token

    token = create_token(clinician.id, "access", role="clinician", settings=test_settings)
    res = client.get(
        f"/api/v1/clinician/patients/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PATIENT_NOT_FOUND"


# ────────── audit ──────────


@pytest.mark.asyncio
async def test_clinician_read_writes_audit_log(client, db_session, test_settings):
    clinician = await _create_clinician(db_session, test_settings)
    from sqlalchemy import select

    from src.core.security import create_token

    token = create_token(clinician.id, "access", role="clinician", settings=test_settings)
    res = client.get(PATIENTS_URL, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

    rows = await db_session.execute(
        select(AuditLog).where(AuditLog.actor_id == clinician.id)
    )
    actions = [r.action for r in rows.scalars().all()]
    assert "clinician.patients.list" in actions


# ────────── org-scoped authorization (ISS-022) ──────────


async def _token(clinician, test_settings) -> str:
    from src.core.security import create_token

    return create_token(clinician.id, "access", role="clinician", settings=test_settings)


@pytest.mark.asyncio
async def test_clinician_cannot_list_other_org_patient(client, db_session, test_settings):
    org_a = await _create_org(db_session, "Hospital A")
    org_b = await _create_org(db_session, "Hospital B")
    clinician_a = await _create_clinician(db_session, test_settings, organization_id=org_a.id)
    await _create_patient_with_session(
        db_session, test_settings, name="다른병원환자", target_hospital_id=org_b.id
    )

    token = await _token(clinician_a, test_settings)
    res = client.get(PATIENTS_URL, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    names = [p["name"] for p in res.json()["data"]]
    assert "다른병원환자" not in names, "clinician saw another org's patient (PHI leak)"


@pytest.mark.asyncio
async def test_clinician_cannot_read_other_org_patient_detail(client, db_session, test_settings):
    org_a = await _create_org(db_session, "Hospital A")
    org_b = await _create_org(db_session, "Hospital B")
    clinician_a = await _create_clinician(db_session, test_settings, organization_id=org_a.id)
    patient_b, _, _ = await _create_patient_with_session(
        db_session, test_settings, target_hospital_id=org_b.id
    )

    token = await _token(clinician_a, test_settings)
    res = client.get(
        f"/api/v1/clinician/patients/{patient_b.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404, "clinician read another org's patient detail (PHI leak)"


@pytest.mark.asyncio
async def test_clinician_cannot_read_other_org_session(client, db_session, test_settings):
    org_a = await _create_org(db_session, "Hospital A")
    org_b = await _create_org(db_session, "Hospital B")
    clinician_a = await _create_clinician(db_session, test_settings, organization_id=org_a.id)
    _, sess_b, _ = await _create_patient_with_session(
        db_session, test_settings, with_risk=True, target_hospital_id=org_b.id
    )

    token = await _token(clinician_a, test_settings)
    res = client.get(
        f"/api/v1/clinician/sessions/{sess_b.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404, "clinician read another org's session (PHI leak)"


@pytest.mark.asyncio
async def test_clinician_cannot_read_other_org_report(client, db_session, test_settings):
    org_a = await _create_org(db_session, "Hospital A")
    org_b = await _create_org(db_session, "Hospital B")
    clinician_a = await _create_clinician(db_session, test_settings, organization_id=org_a.id)
    _, sess_b, _ = await _create_patient_with_session(
        db_session, test_settings, target_hospital_id=org_b.id
    )
    db_session.add(HandoffReport(session_id=sess_b.id, status="generating"))
    await db_session.commit()

    token = await _token(clinician_a, test_settings)
    res = client.get(
        f"/api/v1/sessions/{sess_b.id}/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404, "clinician read another org's handoff report (PHI leak)"
