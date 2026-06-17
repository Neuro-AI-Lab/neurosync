"""POST /sessions + WS /sessions/:id/chat.

Phase 1a Day 8+ — establishes the WebSocket gateway, runs every user message
through the AI Safety classifier, and emits `risk:detected` when warranted.

Authentication / authorization (PRD §5.1 C-7):
- Token MUST arrive in the `auth:connect` initial frame payload — never in
  URL query / Sec-WebSocket-Protocol headers.
- 5-second handshake budget enforced via anyio.fail_after; timeout closes
  with code 1008 explicitly.
- Origin header validated against `settings.cors_ws_origins`.

Idempotency (C-2 hardening):
- Per-connection bounded LRU (`OrderedDict`) caps at `settings.ws_idempotency_cache_size`.
- Replays of the same key get the cached ack back so the client stays in sync.

Conservative classifier fallback (M-1):
- AI server failure → `handle_unavailable_classifier` writes a `pending_reclassify`
  RiskEvent and replies with a self-hotline payload (consent-aware). Silence is
  unacceptable in a life-safety domain.

Per-message AAD (M-3):
- `messages.content` AAD includes the message UUID, not just the session, so
  cross-record swaps fail GCM verification.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import anyio
from contracts.safety import SafetyRequest
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from src.core.config import Settings, get_settings
from src.core.deps import require_role
from src.core.encryption import encrypt_str
from src.core.security import TokenError, decode_token
from src.db import SessionLocal, get_session
from src.models.audit_log import AuditLog
from src.models.handoff import HandoffReport
from src.models.session import Message, Session
from src.models.user import User
from src.schemas.handoff import SubmitAccepted
from src.schemas.questionnaire import QuestionnaireResultOut, QuestionnaireSubmit
from src.schemas.session import (
    SessionOut,
    WSAuthConnect,
    WSUserMessage,
)
from src.services.ai_client import AIClient, AIClientError, get_ai_client
from src.services.chat import respond as chat_turn
from src.services.handoff import (
    build_report_response,
    create_pending_report,
    generate_report_task,
)
from src.services.questionnaire import QuestionnaireError, upsert_result
from src.services.safety import (
    handle_safety_result,
    handle_unavailable_classifier,
    latest_consent_snapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

CONTEXT_PREV_TURNS = 5


# ────────── REST ──────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    sess = Session(patient_id=patient.id, status="in_progress")
    db.add(sess)
    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="session.create",
            resource_type="session",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    await db.refresh(sess)
    return {
        "success": True,
        "data": SessionOut(
            session_id=sess.id, status=sess.status, created_at=sess.created_at
        ).model_dump(by_alias=True, mode="json"),
    }


async def _owned_in_progress_session(
    db: AsyncSession, *, session_id: UUID, patient_id: UUID
) -> Session:
    """Load a session the patient owns, or raise 404/409.

    Patient-facing writes (questionnaires, submit) are only valid while the
    session is still `in_progress` — FR-010 freezes the session after submit.
    """
    row = await db.execute(select(Session).where(Session.id == session_id))
    sess = row.scalar_one_or_none()
    if sess is None or sess.patient_id != patient_id:
        # Don't leak existence of other patients' sessions.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )
    if sess.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SESSION_NOT_EDITABLE",
                "message": "이미 제출된 문진은 수정할 수 없어요.",
            },
        )
    return sess


@router.post("/{session_id}/questionnaires", status_code=status.HTTP_201_CREATED)
async def submit_questionnaire(
    session_id: UUID,
    body: QuestionnaireSubmit,
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    await _owned_in_progress_session(
        db, session_id=session_id, patient_id=patient.id
    )

    try:
        result = await upsert_result(
            db, session_id=session_id, qtype=body.type, answers=body.answers
        )
    except QuestionnaireError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="session.questionnaire.submit",
            resource_type="questionnaire_result",
            resource_id=result.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            audit_metadata={"type": body.type, "session_id": str(session_id)},
        )
    )
    await db.commit()
    await db.refresh(result)
    return {
        "success": True,
        "data": QuestionnaireResultOut(
            id=result.id,
            type=result.type,
            total_score=result.total_score,
            severity=result.severity,
            completed_at=result.completed_at,
        ).model_dump(by_alias=True, mode="json"),
    }


HANDOFF_ESTIMATED_SECONDS = 30

require_clinician = require_role("clinician", "org_admin", "super_admin")


@router.post("/{session_id}/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_session(
    session_id: UUID,
    request: Request,
    background: BackgroundTasks,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """FR-010 — freeze the session and queue Handoff generation (FR-018).

    Generation runs out-of-band (BackgroundTasks now, Celery later); the client
    polls report status. 202 Accepted with the report id.
    """
    sess = await _owned_in_progress_session(
        db, session_id=session_id, patient_id=patient.id
    )
    sess.status = "submitted"
    sess.submitted_at = datetime.now(UTC)

    report = await create_pending_report(db, session_id=session_id)
    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="session.submit",
            resource_type="session",
            resource_id=session_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    # Kick the generation after the response is sent. Failures are captured
    # inside the task and surfaced via report.status = 'failed'.
    background.add_task(generate_report_task, session_id)

    return {
        "success": True,
        "data": SubmitAccepted(
            session_id=session_id,
            status="report_generating",
            report_id=report.id,
            estimated_seconds=HANDOFF_ESTIMATED_SECONDS,
        ).model_dump(by_alias=True, mode="json"),
    }


@router.get("/{session_id}/report/status", response_model=dict)
async def get_report_status(
    session_id: UUID,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """FR-013/018 — patient polls Handoff generation status.

    STATUS ONLY: the report body stays clinician-only (screen-spec §S-12), so
    this never returns report content — just generating / ready / failed.
    """
    srow = await db.execute(select(Session).where(Session.id == session_id))
    sess = srow.scalar_one_or_none()
    if sess is None or sess.patient_id != patient.id:
        # Don't leak existence of other patients' sessions.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )
    rrow = await db.execute(
        select(HandoffReport)
        .where(HandoffReport.session_id == session_id)
        .order_by(HandoffReport.created_at.desc())
        .limit(1)
    )
    report = rrow.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_NOT_FOUND", "message": "리포트를 찾을 수 없어요."},
        )
    return {
        "success": True,
        "data": {"status": report.status, "reportId": str(report.id)},
    }


@router.get("/{session_id}/report", response_model=dict)
async def get_report(
    session_id: UUID,
    request: Request,
    actor: Annotated[User, Depends(require_clinician)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """FR-017/018 — clinician reads the Handoff report. Every read is audited."""
    report = await build_report_response(db, session_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REPORT_NOT_FOUND",
                "message": "리포트를 찾을 수 없어요.",
            },
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            actor_role=actor.role,
            action="clinician.report.read",
            resource_type="handoff_report",
            resource_id=report.report_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    return {
        "success": True,
        "data": report.model_dump(by_alias=True, mode="json"),
    }


# ────────── WebSocket helpers ──────────


async def _send_error_and_close(ws: WebSocket, code: int, reason: str) -> None:
    """Emit auth:error then close. Safe to call before/after accept()."""
    if ws.client_state == WebSocketState.CONNECTED:
        try:
            await ws.send_json({"type": "auth:error", "payload": {"code": reason}})
        except Exception:
            pass
    try:
        await ws.close(code=code)
    except Exception:
        pass


def _origin_allowed(ws: WebSocket, settings: Settings) -> bool:
    if "*" in settings.cors_ws_origins:
        return True  # dev only — validator blocks this in non-dev
    origin = ws.headers.get("origin")
    return origin is not None and origin in settings.cors_ws_origins


def _token_in_url_or_subprotocol(ws: WebSocket) -> bool:
    """PRD C-7: reject if token is smuggled outside the auth:connect frame."""
    if "token" in ws.query_params or "access_token" in ws.query_params:
        return True
    subprotocol = ws.headers.get("sec-websocket-protocol")
    if subprotocol and ("token" in subprotocol.lower() or "bearer" in subprotocol.lower()):
        return True
    return False


async def _await_auth_connect(
    ws: WebSocket, settings: Settings
) -> tuple[UUID, str] | None:
    """Wait for the initial auth:connect frame. Returns (user_id, role) or None.

    Closes the socket with 1008 on any failure (per PRD §5.1 C-7).
    """
    try:
        with anyio.fail_after(settings.ws_auth_handshake_seconds):
            try:
                raw = await ws.receive_json()
            except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
                await _send_error_and_close(ws, 1008, "AUTH_FRAME_INVALID")
                return None
    except TimeoutError:
        await _send_error_and_close(ws, 1008, "AUTH_TIMEOUT")
        return None

    try:
        frame = WSAuthConnect.model_validate(raw)
    except ValidationError:
        await _send_error_and_close(ws, 1008, "AUTH_FRAME_INVALID")
        return None

    try:
        claims = decode_token(
            frame.payload.access_token, expected_type="access", settings=settings
        )
    except TokenError as exc:
        await _send_error_and_close(ws, 1008, exc.code.value)
        return None

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError):
        await _send_error_and_close(ws, 1008, "TOKEN_INVALID")
        return None

    return user_id, str(claims.get("role", "patient"))


async def _persist_user_message(
    db: AsyncSession,
    *,
    session_id: UUID,
    content: str,
    input_modality: str,
    stt_transcription_id: UUID | None,
    settings: Settings,
) -> Message:
    # M-3: pre-generate id so AAD binds the ciphertext to this exact row.
    message_id = uuid.uuid4()
    msg = Message(
        id=message_id,
        session_id=session_id,
        role="user",
        content_encrypted=encrypt_str(
            content,
            aad=f"messages.content:{session_id}:{message_id}".encode(),
            settings=settings,
        ),
        input_modality=input_modality,
        stt_transcription_id=stt_transcription_id,
    )
    db.add(msg)
    await db.flush()
    return msg


async def _recent_message_ids(
    db: AsyncSession, session_id: UUID, limit: int
) -> list[UUID]:
    res = await db.execute(
        select(Message.id)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(res.scalars().all())
    rows.reverse()  # oldest-first for context
    return rows


# ────────── WebSocket route ──────────


@router.websocket("/{session_id}/chat")
async def session_chat(
    ws: WebSocket,
    session_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    ai_client: Annotated[AIClient, Depends(get_ai_client)],
) -> None:
    # M-5: Origin + URL token checks BEFORE accept so attackers don't even
    # get an open channel.
    if not _origin_allowed(ws, settings):
        await ws.close(code=1008)
        return
    if _token_in_url_or_subprotocol(ws):
        await ws.close(code=1008)
        return

    await ws.accept()
    auth = await _await_auth_connect(ws, settings)
    if auth is None:
        return
    user_id, role = auth

    # Authorize session — only the owner can open this WS.
    async with SessionLocal() as db:
        owner_row = await db.execute(
            select(Session.patient_id).where(Session.id == session_id)
        )
        owner = owner_row.scalar_one_or_none()
        if owner is None or owner != user_id:
            await _send_error_and_close(ws, 1008, "SESSION_NOT_AUTHORIZED")
            return

        db.add(
            AuditLog(
                actor_id=user_id,
                actor_role=role,
                action="ws.session.connect",
                resource_type="session",
                resource_id=session_id,
            )
        )
        await db.commit()

    await ws.send_json(
        {
            "type": "auth:connected",
            "payload": {"sessionId": str(session_id)},
        }
    )

    # C-2: bounded LRU. Key → cached response frames for replay. A single
    # user:message can fan out to multiple frames (ack + ai:complete).
    idem_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    try:
        while True:
            try:
                raw = await ws.receive_json()
            except (json.JSONDecodeError, ValueError):
                await ws.send_json(
                    {"type": "error", "payload": {"code": "FRAME_DECODE_FAILED"}}
                )
                continue

            if not isinstance(raw, dict):
                await ws.send_json(
                    {"type": "error", "payload": {"code": "FRAME_NOT_OBJECT"}}
                )
                continue

            frame_type = raw.get("type")
            if frame_type != "user:message":
                await ws.send_json(
                    {
                        "type": "error",
                        "payload": {"code": "FRAME_UNEXPECTED", "got": str(frame_type)},
                    }
                )
                continue

            try:
                frame = WSUserMessage.model_validate(raw)
            except ValidationError as exc:
                await ws.send_json(
                    {
                        "type": "error",
                        "payload": {
                            "code": "FRAME_INVALID",
                            "details": exc.errors(include_url=False),
                        },
                    }
                )
                continue

            cached = idem_cache.get(frame.payload.idempotency_key)
            if cached is not None:
                # Replay the same frames so the client stays consistent.
                idem_cache.move_to_end(frame.payload.idempotency_key)
                for frame_out in cached:
                    await ws.send_json(frame_out)
                continue

            frames = await _handle_message(
                settings=settings,
                ai_client=ai_client,
                user_id=user_id,
                session_id=session_id,
                frame=frame,
            )

            idem_cache[frame.payload.idempotency_key] = frames
            if len(idem_cache) > settings.ws_idempotency_cache_size:
                idem_cache.popitem(last=False)

            for frame_out in frames:
                await ws.send_json(frame_out)

    except WebSocketDisconnect:
        pass
    finally:
        # M-2 follow-up: disconnect audit could go here when we're sure
        # we always reach `finally`. (Best-effort, swallow errors.)
        try:
            async with SessionLocal() as db:
                db.add(
                    AuditLog(
                        actor_id=user_id,
                        actor_role=role,
                        action="ws.session.disconnect",
                        resource_type="session",
                        resource_id=session_id,
                    )
                )
                await db.commit()
        except Exception:
            logger.warning("ws.session.disconnect audit failed", exc_info=True)


async def _handle_message(
    *,
    settings: Settings,
    ai_client: AIClient,
    user_id: UUID,
    session_id: UUID,
    frame: WSUserMessage,
) -> list[dict[str, Any]]:
    started = time.perf_counter()

    async with SessionLocal() as db:
        msg = await _persist_user_message(
            db,
            session_id=session_id,
            content=frame.payload.content,
            input_modality=frame.payload.input_modality,
            stt_transcription_id=frame.payload.stt_transcription_id,
            settings=settings,
        )
        await db.commit()
        trigger_message_id = msg.id

    # Call AI Safety (no DB session held during network IO).
    safety_unavailable = False
    safety = None
    try:
        safety = await ai_client.safety_classify(
            SafetyRequest(message=frame.payload.content)
        )
    except AIClientError as exc:
        logger.warning("safety.unavailable", extra={"error": str(exc)})
        safety_unavailable = True

    async with SessionLocal() as db:
        context_ids = await _recent_message_ids(
            db, session_id, CONTEXT_PREV_TURNS
        )
        consent = await latest_consent_snapshot(db, user_id)

        if safety_unavailable:
            payload = await handle_unavailable_classifier(
                db,
                patient_id=user_id,
                session_id=session_id,
                trigger_message_id=trigger_message_id,
                context_message_ids=context_ids,
                consent=consent,
            )
        else:
            assert safety is not None
            payload = await handle_safety_result(
                db,
                patient_id=user_id,
                session_id=session_id,
                trigger_message_id=trigger_message_id,
                context_message_ids=context_ids,
                safety=safety,
                consent=consent,
            )
        await db.commit()

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # HIGH/CRITICAL — the dialogue is interrupted (PRD §5.1): risk only, no AI reply.
    if payload is not None:
        return [{"type": "risk:detected", "payload": payload}]

    safety_level_str = safety.level.value if safety is not None else "unknown"
    frames: list[dict[str, Any]] = [
        {
            "type": "user:message:received",
            "payload": {
                "messageId": str(trigger_message_id),
                "idempotencyKey": frame.payload.idempotency_key,
                "safetyLevel": safety_level_str,
                "latencyMs": elapsed_ms,
            },
        }
    ]

    # FR-004 — best-effort AI dialogue turn (LOW/MEDIUM only). Failure is
    # swallowed inside chat_turn so the chat keeps flowing.
    async with SessionLocal() as db:
        ai_payload = await chat_turn(
            db, ai_client=ai_client, session_id=session_id, settings=settings
        )
        await db.commit()
    if ai_payload is not None:
        frames.append({"type": "ai:complete", "payload": ai_payload})

    return frames


__all__ = ["router"]
