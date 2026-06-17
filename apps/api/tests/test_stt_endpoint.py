"""STT transcribe endpoint + voice consent + 48h purge (FR-033~037).

DB-backed (auto-skips without Postgres). The AI STT call is mocked via respx.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

respx = pytest.importorskip("respx")
from httpx import Response  # noqa: E402

from src.models.audio import AudioRecording  # noqa: E402
from src.models.consent import ConsentSnapshot  # noqa: E402
from src.services.stt import purge_expired_audio  # noqa: E402

TRANSCRIBE_URL = "/api/v1/stt/transcribe"
OGG = b"OggS" + b"\x00" * 64


def _register(client, *, voice: bool) -> dict[str, Any]:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"v-{uuid.uuid4().hex[:8]}@example.com",
            "password": "Hunter2-Strong!Password",
            "name": "음성",
            "birthYear": datetime.now(tz=UTC).year - 30,
            "gender": "female",
            "phone": "010-1111-2222",
            "region": "서울",
            "emergencyContact": "010-3333-4444",
            "consents": {
                "tos": True,
                "privacy": True,
                "sensitive": True,
                "riskNotification": True,
                "voice": voice,
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


def _session(client, access: str) -> str:
    return client.post(
        "/api/v1/sessions", headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]


def _stt_response(text: str = "잠을 잘 못 잤어요", confidence: float = 0.92) -> dict[str, Any]:
    return {
        "text": text,
        "confidence": confidence,
        "vendor": "whisper-openai",
        "duration_ms": 5400,
        "latency_ms": 780,
        "fallback_chain": [{"vendor": "skt-adot", "status": "skipped", "latency_ms": 0}],
    }


def _upload(client, access: str, sid: str):
    return client.post(
        TRANSCRIBE_URL,
        headers={"Authorization": f"Bearer {access}"},
        data={"sessionId": sid, "encoding": "opus", "sampleRateHz": "16000"},
        files={"audio": ("clip.ogg", OGG, "audio/ogg")},
    )


# ────────── consent gate (FR-034) ──────────


@pytest.mark.asyncio
async def test_transcribe_requires_voice_consent(client):
    auth = _register(client, voice=False)
    access = auth["accessToken"]
    sid = _session(client, access)
    res = _upload(client, access, sid)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "VOICE_CONSENT_REQUIRED"


# ────────── happy path (FR-033/035) ──────────


@pytest.mark.asyncio
@respx.mock
async def test_transcribe_returns_text_without_auto_send(client, test_settings, db_session):
    respx.post(f"{test_settings.ai_server_url}/ai/stt/transcribe").mock(
        return_value=Response(200, json=_stt_response("최근 한 달 잠을 못 잤어요"))
    )
    auth = _register(client, voice=True)
    access = auth["accessToken"]
    sid = _session(client, access)

    res = _upload(client, access, sid)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["text"] == "최근 한 달 잠을 못 잤어요"
    assert data["confidence"] == pytest.approx(0.92)
    assert data["vendor"] == "whisper-openai"
    assert data["transcriptionId"] and data["audioRecordingId"]

    # FR-035 — transcription must NOT have been added as a chat message.
    from sqlalchemy import func, select

    from src.models.session import Message

    count = await db_session.execute(
        select(func.count(Message.id)).where(Message.session_id == uuid.UUID(sid))
    )
    assert int(count.scalar() or 0) == 0


# ────────── low confidence fallback (FR-037) ──────────


@pytest.mark.asyncio
@respx.mock
async def test_low_confidence_returns_422_but_keeps_audio(client, test_settings, db_session):
    respx.post(f"{test_settings.ai_server_url}/ai/stt/transcribe").mock(
        return_value=Response(200, json=_stt_response("음...", confidence=0.41))
    )
    auth = _register(client, voice=True)
    access = auth["accessToken"]
    sid = _session(client, access)

    res = _upload(client, access, sid)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "STT_LOW_CONFIDENCE"

    # Audio recording is retained for the 48h retry window.
    from sqlalchemy import func, select

    cnt = await db_session.execute(
        select(func.count(AudioRecording.id)).where(
            AudioRecording.session_id == uuid.UUID(sid)
        )
    )
    assert int(cnt.scalar() or 0) == 1


# ────────── voice consent toggle (FR-034) ──────────


@pytest.mark.asyncio
@respx.mock
async def test_voice_consent_toggle_enables_transcription(client, test_settings):
    respx.post(f"{test_settings.ai_server_url}/ai/stt/transcribe").mock(
        return_value=Response(200, json=_stt_response())
    )
    auth = _register(client, voice=False)
    access = auth["accessToken"]
    sid = _session(client, access)

    # Initially blocked.
    assert _upload(client, access, sid).status_code == 403

    toggle = client.post(
        "/api/v1/consent/voice",
        headers={"Authorization": f"Bearer {access}"},
        json={"voice": True},
    )
    assert toggle.status_code == 200
    assert toggle.json()["data"]["voice"] is True

    # Now allowed.
    assert _upload(client, access, sid).status_code == 200


# ────────── 48h purge (FR-036) ──────────


@pytest.mark.asyncio
async def test_purge_deletes_expired_audio(client, db_session, test_settings):
    auth = _register(client, voice=True)
    patient_id = uuid.UUID(auth["userId"])
    consent = await db_session.execute(
        ConsentSnapshot.__table__.select().where(
            ConsentSnapshot.user_id == patient_id
        )
    )
    consent_id = consent.first()[0]

    expired = AudioRecording(
        patient_id=patient_id,
        file_url="/tmp/does-not-exist.ogg",
        encoding="opus",
        sample_rate_hz=16000,
        duration_ms=5000,
        bytes=1234,
        consent_snapshot_id=consent_id,
        delete_after=datetime.now(UTC) - timedelta(hours=1),
    )
    fresh = AudioRecording(
        patient_id=patient_id,
        file_url="/tmp/also-missing.ogg",
        encoding="opus",
        sample_rate_hz=16000,
        duration_ms=5000,
        bytes=1234,
        consent_snapshot_id=consent_id,
        delete_after=datetime.now(UTC) + timedelta(hours=10),
    )
    db_session.add_all([expired, fresh])
    await db_session.commit()

    purged = await purge_expired_audio(db_session, now=datetime.now(UTC))
    assert purged == 1

    await db_session.refresh(expired)
    await db_session.refresh(fresh)
    assert expired.deleted_at is not None
    assert fresh.deleted_at is None
