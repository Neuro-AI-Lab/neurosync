"""POST /api/v1/auth/login + /api/v1/auth/refresh integration tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.security import hash_password
from src.models.user import User

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
REGISTER_URL = "/api/v1/auth/register"

ADULT_BIRTH_YEAR = datetime.now().year - 30


def _base_register_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "Hunter2-Strong!Password",
        "name": "테스트",
        "birthYear": ADULT_BIRTH_YEAR,
        "gender": "female",
        "phone": "010-2222-3333",
        "region": "서울",
        "emergencyContact": "010-4444-5555",
        "consents": {
            "tos": True,
            "privacy": True,
            "sensitive": True,
            "riskNotification": True,
        },
    }


@pytest.mark.asyncio
async def test_login_success_after_register(client):
    email = "login-ok@example.com"
    assert client.post(REGISTER_URL, json=_base_register_payload(email)).status_code == 201

    res = client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": "Hunter2-Strong!Password",
            "role": "patient",
        },
    )
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["data"]["accessToken"]
    assert body["data"]["refreshToken"]


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    email = "wrong-pw@example.com"
    assert client.post(REGISTER_URL, json=_base_register_payload(email)).status_code == 201

    res = client.post(
        LOGIN_URL,
        json={"email": email, "password": "Wrong-Password-2026!", "role": "patient"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_invalid_credentials(client):
    res = client.post(
        LOGIN_URL,
        json={
            "email": "ghost@example.com",
            "password": "Hunter2-Strong!Password",
            "role": "patient",
        },
    )
    # Same code as wrong password — avoid leaking email existence
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_role_mismatch_blocks(client, db_session, test_settings):
    """A clinician account trying to log in via patient role is blocked."""
    clinician = User(
        email="doc@hospital.example",
        password_hash=hash_password("Hunter2-Strong!Password", test_settings),
        role="clinician",
    )
    db_session.add(clinician)
    await db_session.commit()

    res = client.post(
        LOGIN_URL,
        json={
            "email": "doc@hospital.example",
            "password": "Hunter2-Strong!Password",
            "role": "patient",
        },
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ROLE_MISMATCH"


@pytest.mark.asyncio
async def test_refresh_issues_new_access_token(client):
    email = "refresh@example.com"
    reg = client.post(REGISTER_URL, json=_base_register_payload(email))
    refresh = reg.json()["data"]["refreshToken"]

    res = client.post(REFRESH_URL, json={"refreshToken": refresh})
    assert res.status_code == 200, res.json()
    assert res.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_refresh_rejects_access_token_used_as_refresh(client):
    email = "wrong-type@example.com"
    reg = client.post(REGISTER_URL, json=_base_register_payload(email))
    access = reg.json()["data"]["accessToken"]

    res = client.post(REFRESH_URL, json={"refreshToken": access})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "TOKEN_TYPE_MISMATCH"
