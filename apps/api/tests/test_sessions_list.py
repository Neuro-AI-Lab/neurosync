"""GET /api/v1/sessions — S09 records (기록 조회).

DB-backed (auto-skips without Postgres, same convention as
`test_intake_flow.py`). Covers: own-sessions-only scoping, `hasReport`
existence flag (independent of a `generating`/`failed` report status),
`progressRatio` round-trip, and newest-first ordering.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest


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


@pytest.mark.asyncio
async def test_list_returns_only_own_sessions_newest_first(client):
    owner = _register_patient(client)
    owner_access = owner["accessToken"]
    sid1 = _create_session(client, owner_access)
    sid2 = _create_session(client, owner_access)

    other = _register_patient(client)
    _create_session(client, other["accessToken"])

    res = client.get(
        "/api/v1/sessions", headers={"Authorization": f"Bearer {owner_access}"}
    )
    assert res.status_code == 200, res.text
    sessions = res.json()["data"]["sessions"]
    ids = [s["sessionId"] for s in sessions]

    assert set(ids) == {sid1, sid2}
    # newest-first: sid2 was created after sid1
    assert ids.index(sid2) < ids.index(sid1)
    for s in sessions:
        assert s["hasReport"] is False
        assert s["progressRatio"] == 0.0
        assert s["status"] == "in_progress"


@pytest.mark.asyncio
async def test_list_empty_for_new_patient(client):
    patient = _register_patient(client)
    res = client.get(
        "/api/v1/sessions", headers={"Authorization": f"Bearer {patient['accessToken']}"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["sessions"] == []


@pytest.mark.asyncio
async def test_list_requires_auth(client):
    res = client.get("/api/v1/sessions")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_reflects_progress_and_report_existence(client, db_session):
    """`progressRatio` mirrors `Session.progress_ratio`, and `hasReport`
    flips true purely on row existence in `handoff_reports` — a
    `generating`/not-yet-`ready` report still counts (the client resolves
    the actual phase separately via `/report/status`)."""
    from sqlalchemy import select

    from src.models.handoff import HandoffReport
    from src.models.session import Session

    patient = _register_patient(client)
    access = patient["accessToken"]
    sid = _create_session(client, access)

    row = await db_session.execute(select(Session).where(Session.id == uuid.UUID(sid)))
    sess = row.scalar_one()
    sess.progress_ratio = 0.42
    db_session.add(HandoffReport(session_id=sess.id, status="generating"))
    await db_session.commit()

    res = client.get("/api/v1/sessions", headers={"Authorization": f"Bearer {access}"})
    assert res.status_code == 200, res.text
    entry = res.json()["data"]["sessions"][0]
    assert entry["sessionId"] == sid
    assert entry["progressRatio"] == pytest.approx(0.42)
    assert entry["hasReport"] is True
