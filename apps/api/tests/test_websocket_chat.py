"""WebSocket /api/v1/sessions/:id/chat — handshake + Safety pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pytest

respx = pytest.importorskip("respx")  # CI installs respx via uv sync --dev
from httpx import Response  # noqa: E402

from src.core.security import create_token  # noqa: E402
from src.models.session import Session  # noqa: E402

REGISTER_URL = "/api/v1/auth/register"
SESSIONS_URL = "/api/v1/sessions"


def _register_payload(email: str) -> dict[str, Any]:
    return {
        "email": email,
        "password": "Hunter2-Strong!Password",
        "name": "테스트",
        "birthYear": datetime.now().year - 30,
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
    }


def _ai_safety_response(level: str = "low", category: str = "none") -> dict[str, Any]:
    return {
        "level": level,
        "category": category,
        "evidence": {
            "matched_keywords": ["test-keyword"] if level != "low" else [],
            "classifier": "keyword-v1" if level != "low" else "llm-stub-v0",
            "confidence": 0.9 if level != "low" else 0.0,
        },
        "latency_ms": 3,
    }


def _ai_chat_response(
    reply: str = "조금 더 말씀해 주실 수 있을까요?",
    *,
    collected: list[str] | None = None,
    ratio: float = 0.23,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "model_used": "chat-stub-v0",
        "progress": {
            "collected_items": collected if collected is not None else ["chief_complaint"],
            "total_items": 13,
            "ratio": ratio,
        },
        "latency_ms": 12,
    }


def _new_session_id(db_session, patient_id) -> uuid.UUID:
    sess = Session(patient_id=patient_id, status="in_progress")
    db_session.add(sess)
    return sess


# ────────── REST POST /sessions ──────────


@pytest.mark.asyncio
async def test_create_session_requires_patient(client):
    email = "create-session@example.com"
    reg = client.post(REGISTER_URL, json=_register_payload(email))
    assert reg.status_code == 201, reg.json()
    access = reg.json()["data"]["accessToken"]

    res = client.post(SESSIONS_URL, headers={"Authorization": f"Bearer {access}"})
    assert res.status_code == 201, res.json()
    body = res.json()
    assert body["success"] is True
    assert body["data"]["status"] == "in_progress"
    assert body["data"]["sessionId"]


@pytest.mark.asyncio
async def test_create_session_rejects_missing_token(client):
    res = client.post(SESSIONS_URL)
    assert res.status_code == 401


# ────────── WebSocket handshake ──────────


@pytest.mark.asyncio
async def test_ws_rejects_invalid_auth_frame(client):
    email = "ws-bad-frame@example.com"
    reg = client.post(REGISTER_URL, json=_register_payload(email))
    access = reg.json()["data"]["accessToken"]
    sess_res = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    )
    sid = sess_res.json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "user:message", "payload": {"content": "skip auth"}})
        msg = ws.receive_json()
        assert msg["type"] == "auth:error"
        assert msg["payload"]["code"] == "AUTH_FRAME_INVALID"


@pytest.mark.asyncio
async def test_ws_rejects_token_for_wrong_session(client, db_session):
    """User A logs in but tries to open the WS for User B's session."""
    a = client.post(REGISTER_URL, json=_register_payload("a@example.com"))
    b = client.post(REGISTER_URL, json=_register_payload("b@example.com"))
    a_token = a.json()["data"]["accessToken"]
    b_sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {b.json()['data']['accessToken']}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{b_sid}/chat") as ws:
        ws.send_json(
            {"type": "auth:connect", "payload": {"accessToken": a_token}}
        )
        msg = ws.receive_json()
        assert msg["type"] == "auth:error"
        assert msg["payload"]["code"] == "SESSION_NOT_AUTHORIZED"


# ────────── Safety pipeline ──────────


@pytest.mark.asyncio
@respx.mock
async def test_ws_low_safety_acknowledges_message(client, test_settings):
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        return_value=Response(200, json=_ai_safety_response("low"))
    )

    reg = client.post(REGISTER_URL, json=_register_payload("low-safety@example.com"))
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        assert ws.receive_json()["type"] == "auth:connected"

        ws.send_json(
            {
                "type": "user:message",
                "payload": {
                    "content": "오늘 잠을 잘 잤어요",
                    "idempotencyKey": "idem-low-001",
                },
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "user:message:received"
        assert ack["payload"]["safetyLevel"] == "low"


@pytest.mark.asyncio
@respx.mock
async def test_ws_high_safety_routes_to_emergency_for_opted_in_patient(
    client, test_settings
):
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        return_value=Response(200, json=_ai_safety_response("critical", "suicide"))
    )

    reg = client.post(REGISTER_URL, json=_register_payload("risk@example.com"))
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        assert ws.receive_json()["type"] == "auth:connected"

        ws.send_json(
            {
                "type": "user:message",
                "payload": {
                    "content": "더 이상 살고 싶지 않아요",
                    "idempotencyKey": "idem-critical-001",
                },
            }
        )
        event = ws.receive_json()
        assert event["type"] == "risk:detected"
        assert event["payload"]["level"] == "critical"
        assert event["payload"]["category"] == "suicide"
        assert event["payload"]["routeTo"] == "/emergency"
        numbers = [h["number"] for h in event["payload"]["hotlines"]]
        assert "1393" in numbers
        assert "119" in numbers


@pytest.mark.asyncio
@respx.mock
async def test_ws_high_safety_routes_to_self_hotline_for_opted_out_patient(
    client, test_settings
):
    """PRD §4.5.2 — opt-out 환자에게는 본인용 핫라인만, 응급 라우팅 없음."""
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        return_value=Response(200, json=_ai_safety_response("critical", "suicide"))
    )

    payload = _register_payload("opt-out@example.com")
    payload["consents"]["riskNotification"] = False
    reg = client.post(REGISTER_URL, json=payload)
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        assert ws.receive_json()["type"] == "auth:connected"

        ws.send_json(
            {
                "type": "user:message",
                "payload": {
                    "content": "더 이상 살고 싶지 않아요",
                    "idempotencyKey": "idem-optout-001",
                },
            }
        )
        event = ws.receive_json()
        assert event["type"] == "risk:detected"
        assert event["payload"]["routeTo"] == "/self_hotline"
        # Hotlines still surfaced — opt-out is about clinician/SMS routing,
        # NOT about hiding emergency information from the patient themselves.
        assert event["payload"]["hotlines"]


@pytest.mark.asyncio
@respx.mock
async def test_ws_idempotency_key_deduplicates(client, test_settings):
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        return_value=Response(200, json=_ai_safety_response("low"))
    )

    reg = client.post(REGISTER_URL, json=_register_payload("dedup@example.com"))
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        ws.receive_json()  # auth:connected

        msg = {
            "type": "user:message",
            "payload": {"content": "테스트 메시지", "idempotencyKey": "same-key-001"},
        }
        ws.send_json(msg)
        first = ws.receive_json()
        assert first["type"] == "user:message:received"

        # Send the same key again with different content — dropped silently.
        ws.send_json(
            {
                "type": "user:message",
                "payload": {
                    "content": "다른 내용",
                    "idempotencyKey": "same-key-001",
                },
            }
        )
        # Send a new key to confirm the connection still flows.
        ws.send_json(
            {
                "type": "user:message",
                "payload": {"content": "새 메시지", "idempotencyKey": "diff-key-002"},
            }
        )
        second = ws.receive_json()
        assert second["type"] == "user:message:received"


@pytest.mark.asyncio
@respx.mock
async def test_ws_ai_server_failure_returns_conservative_risk_detected(
    client, test_settings
):
    """M-1: AI 분류기 다운 → SILENCE NOT OK. 보수적 medium risk:detected 응답."""
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        side_effect=Exception("network down")
    )

    reg = client.post(REGISTER_URL, json=_register_payload("ai-down@example.com"))
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        ws.receive_json()

        ws.send_json(
            {
                "type": "user:message",
                "payload": {"content": "테스트", "idempotencyKey": "k1"},
            }
        )
        event = ws.receive_json()
        assert event["type"] == "risk:detected"
        assert event["payload"]["level"] == "medium"
        assert event["payload"]["reason"] == "classifier_unavailable"


# ────────── AI dialogue turn (FR-004) ──────────


@pytest.mark.asyncio
@respx.mock
async def test_ws_low_safety_emits_ai_complete_with_progress(client, test_settings, db_session):
    """LOW safety → ack THEN ai:complete (progress) + session progress persisted."""
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        return_value=Response(200, json=_ai_safety_response("low"))
    )
    respx.post(f"{test_settings.ai_server_url}/ai/chat/respond").mock(
        return_value=Response(
            200, json=_ai_chat_response(reply="언제부터 그러셨나요?", ratio=0.31)
        )
    )

    reg = client.post(REGISTER_URL, json=_register_payload("chat-ok@example.com"))
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        assert ws.receive_json()["type"] == "auth:connected"

        ws.send_json(
            {
                "type": "user:message",
                "payload": {"content": "요즘 너무 힘들어요", "idempotencyKey": "chat-idem-1"},
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "user:message:received"
        assert ack["payload"]["idempotencyKey"] == "chat-idem-1"

        ai = ws.receive_json()
        assert ai["type"] == "ai:complete"
        assert ai["payload"]["content"] == "언제부터 그러셨나요?"
        assert ai["payload"]["progress"]["ratio"] == 0.31
        assert ai["payload"]["progress"]["collectedItems"] == ["chief_complaint"]
        assert ai["payload"]["messageId"]

    # Progress snapshot persisted on the session.
    from sqlalchemy import select

    row = await db_session.execute(select(Session).where(Session.id == uuid.UUID(sid)))
    sess = row.scalar_one()
    assert sess.progress_ratio == 0.31
    assert sess.collected_items == ["chief_complaint"]


@pytest.mark.asyncio
@respx.mock
async def test_ws_chat_failure_is_graceful(client, test_settings):
    """AI chat down → still get the ack, no ai:complete (dialogue is best-effort)."""
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        return_value=Response(200, json=_ai_safety_response("low"))
    )
    respx.post(f"{test_settings.ai_server_url}/ai/chat/respond").mock(
        side_effect=Exception("chat down")
    )

    reg = client.post(REGISTER_URL, json=_register_payload("chat-down@example.com"))
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        ws.receive_json()  # auth:connected

        ws.send_json(
            {
                "type": "user:message",
                "payload": {"content": "안녕하세요", "idempotencyKey": "chat-idem-2"},
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "user:message:received"
        # Next message round-trips fine — connection still healthy.
        ws.send_json(
            {
                "type": "user:message",
                "payload": {"content": "또 메시지", "idempotencyKey": "chat-idem-3"},
            }
        )
        assert ws.receive_json()["type"] == "user:message:received"


@pytest.mark.asyncio
@respx.mock
async def test_ws_critical_safety_skips_ai_reply(client, test_settings):
    """HIGH/CRITICAL interrupts the dialogue — risk:detected only, no ai:complete."""
    respx.post(f"{test_settings.ai_server_url}/ai/safety/classify").mock(
        return_value=Response(200, json=_ai_safety_response("critical", "suicide"))
    )
    chat_route = respx.post(f"{test_settings.ai_server_url}/ai/chat/respond").mock(
        return_value=Response(200, json=_ai_chat_response())
    )

    reg = client.post(REGISTER_URL, json=_register_payload("chat-risk@example.com"))
    access = reg.json()["data"]["accessToken"]
    sid = client.post(
        SESSIONS_URL, headers={"Authorization": f"Bearer {access}"}
    ).json()["data"]["sessionId"]

    with client.websocket_connect(f"/api/v1/sessions/{sid}/chat") as ws:
        ws.send_json({"type": "auth:connect", "payload": {"accessToken": access}})
        ws.receive_json()

        ws.send_json(
            {
                "type": "user:message",
                "payload": {"content": "죽고 싶어요", "idempotencyKey": "chat-idem-4"},
            }
        )
        event = ws.receive_json()
        assert event["type"] == "risk:detected"

    # Dialogue endpoint must NOT be called when the message is a crisis.
    assert not chat_route.called


# Sanity: token util used elsewhere in tests
def test_create_token_smoke(test_settings):
    tok = create_token("user-1", "access", role="patient", settings=test_settings)
    assert tok.count(".") == 2
