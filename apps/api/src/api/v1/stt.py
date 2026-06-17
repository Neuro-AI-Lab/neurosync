"""POST /api/v1/stt/transcribe — Push-to-Talk audio → text (FR-033/034/037).

FR-035: the transcription is returned only; it is NOT auto-added as a message.
The client edits the text and sends it explicitly over the WS chat.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.deps import require_role
from src.db import get_session
from src.models.audit_log import AuditLog
from src.models.consent import ConsentSnapshot
from src.models.session import Session
from src.models.user import User
from src.schemas.stt import STTTranscribeOut
from src.services.ai_client import AIClient, get_ai_client
from src.services.stt import STTError, transcribe

router = APIRouter(prefix="/stt", tags=["stt"])


@router.post("/transcribe")
async def transcribe_audio(
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    ai_client: Annotated[AIClient, Depends(get_ai_client)],
    audio: Annotated[UploadFile, File()],
    session_id: Annotated[UUID, Form(alias="sessionId")],
    lang: Annotated[str, Form()] = "ko-KR",
    encoding: Annotated[str, Form()] = "opus",
    sample_rate_hz: Annotated[int, Form(alias="sampleRateHz")] = 16000,
    prev_context: Annotated[str, Form(alias="prevContext")] = "",
) -> dict:
    # Session ownership — only the owner may transcribe into their session.
    owner_row = await db.execute(
        select(Session.patient_id).where(Session.id == session_id)
    )
    owner = owner_row.scalar_one_or_none()
    if owner is None or owner != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )

    # FR-034 — voice consent opt-in is required.
    consent_row = await db.execute(
        select(ConsentSnapshot)
        .where(ConsentSnapshot.user_id == patient.id)
        .order_by(desc(ConsentSnapshot.collected_at))
        .limit(1)
    )
    consent = consent_row.scalar_one_or_none()
    if consent is None or not consent.voice:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "VOICE_CONSENT_REQUIRED",
                "message": "음성 입력 동의가 필요해요.",
            },
        )

    data = await audio.read()
    try:
        transcription, recording, text = await transcribe(
            db,
            patient_id=patient.id,
            session_id=session_id,
            audio=data,
            encoding=encoding,
            sample_rate_hz=sample_rate_hz,
            lang=lang,
            prev_context=prev_context,
            consent_snapshot_id=consent.id,
            ai_client=ai_client,
            settings=settings,
        )
    except STTError as exc:
        await db.commit()  # persist the audio_recording row even on low-confidence
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="stt.transcribe",
            resource_type="stt_transcription",
            resource_id=transcription.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            audit_metadata={"vendor": transcription.vendor, "session_id": str(session_id)},
        )
    )
    await db.commit()

    return {
        "success": True,
        "data": STTTranscribeOut(
            transcription_id=transcription.id,
            text=text,
            confidence=float(transcription.confidence),
            vendor=transcription.vendor,
            duration_ms=recording.duration_ms,
            latency_ms=transcription.latency_ms,
            audio_recording_id=recording.id,
        ).model_dump(by_alias=True, mode="json"),
    }
