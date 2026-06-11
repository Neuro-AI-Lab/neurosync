"""POST /api/v1/auth/register integration tests — PRD §5.1."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

ADULT_BIRTH_YEAR = datetime.now().year - 30  # 30yo
MINOR_BIRTH_YEAR = datetime.now().year - 10  # 10yo

REGISTER_URL = "/api/v1/auth/register"


def _base_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "email": "patient@example.com",
        "password": "Hunter2-Strong!Password",
        "name": "홍길동",
        "birthYear": ADULT_BIRTH_YEAR,
        "gender": "male",
        "phone": "010-1234-5678",
        "region": "서울 강남구",
        "emergencyContact": "010-9876-5432",
        "consents": {
            "tos": True,
            "privacy": True,
            "sensitive": True,
            "riskNotification": True,
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_register_success_returns_tokens(client):
    response = client.post(REGISTER_URL, json=_base_payload())
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["accessToken"]
    assert data["refreshToken"]
    assert data["expiresIn"] > 0
    assert data["userId"]


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client):
    response = client.post(
        REGISTER_URL,
        json=_base_payload(password="short", email="weak@example.com"),
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "WEAK_PASSWORD"


@pytest.mark.asyncio
async def test_register_rejects_missing_required_consent(client):
    payload = _base_payload(email="missing-consent@example.com")
    payload["consents"]["sensitive"] = False
    response = client.post(REGISTER_URL, json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "CONSENT_REQUIRED"
    fields = [d["field"] for d in body["error"]["details"]]
    assert "sensitive" in fields


@pytest.mark.asyncio
async def test_register_allows_risk_notification_optout(client):
    payload = _base_payload(email="optout@example.com")
    payload["consents"]["riskNotification"] = False
    response = client.post(REGISTER_URL, json=payload)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_register_blocks_minor_without_guardian(client):
    response = client.post(
        REGISTER_URL,
        json=_base_payload(email="minor@example.com", birthYear=MINOR_BIRTH_YEAR),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "GUARDIAN_CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = _base_payload(email="dup@example.com")
    r1 = client.post(REGISTER_URL, json=payload)
    assert r1.status_code == 201
    r2 = client.post(REGISTER_URL, json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "EMAIL_EXISTS"


@pytest.mark.asyncio
async def test_register_rejects_emergency_contact_same_as_phone(client):
    payload = _base_payload(
        email="same-contact@example.com",
        emergencyContact="010-1234-5678",  # same as phone
    )
    response = client.post(REGISTER_URL, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"
