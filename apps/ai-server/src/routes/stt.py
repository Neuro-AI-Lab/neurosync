"""POST /ai/stt/transcribe — Batch STT endpoint.

Multipart upload: `audio` file + form fields. Calls SKT A.X STT Batch via
STTAgent and returns structured `STTOutput`.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.agents.stt import STTAgent
from src.dependencies import get_stt_agent
from src.schemas.stt import STTInput, STTMode, STTOutput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/stt", tags=["stt"])

# SKT A.X limits: 100MB / 30분 (spec §6.6). Enforce 100MB gate.
_MAX_AUDIO_BYTES = 100 * 1024 * 1024
_ALLOWED_AUDIO_CTYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/opus",
    "audio/ogg",
    "audio/flac",
    "audio/m4a",
    "audio/mp4",
    "audio/webm",
    "audio/aac",
    "application/octet-stream",
}


@router.post("/transcribe", response_model=STTOutput)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Patient audio (mp3/wav/opus/etc.)"),
    session_id: str = Form(...),
    patient_id: str = Form(...),
    mode: STTMode = Form("batch"),
    language: str = Form("ko-KR"),
    keywords: str = Form(
        "",
        description="Comma-separated word-boost hints (e.g. '우울감,불면,자살')",
    ),
    agreement_of_data_collection: bool = Form(False),
    request_id: str | None = Form(None),
    agent: STTAgent = Depends(get_stt_agent),
) -> STTOutput:
    """Transcribe patient audio (mp3/wav/opus) to text via SKT A.X STT Batch."""
    if not request_id:
        request_id = str(uuid.uuid4())

    if mode == "streaming":
        raise HTTPException(
            status_code=501,
            detail="Streaming STT not implemented yet — use mode='batch'",
        )

    content_type = audio.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_AUDIO_CTYPES:
        logger.warning(
            "STT request %s: unusual content-type %s (filename=%s), proceeding",
            request_id, content_type, audio.filename,
        )

    body = await audio.read()
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(body) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio exceeds 100MB limit ({len(body):,} bytes)",
        )

    filename = audio.filename or "audio.mp3"
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

    logger.info(
        "STT transcribe request_id=%s session_id=%s patient_id=%s "
        "file=%s (%d bytes) mode=%s keywords=%d",
        request_id, session_id, patient_id, filename, len(body), mode, len(kw_list),
    )

    meta = STTInput(
        session_id=session_id,
        request_id=request_id,
        patient_id=patient_id,
        filename=filename,
        mode=mode,
        language=language,
        keywords=kw_list,
        agreement_of_data_collection=agreement_of_data_collection,
    )

    try:
        result = await agent.transcribe(body, meta)
    except Exception as exc:
        logger.error("STT transcribe failed request_id=%s: %s", request_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="STT upstream failure") from exc

    logger.info(
        "STT transcribe result request_id=%s: text_len=%d segments=%d latency=%.0fms",
        request_id, len(result.text), len(result.segments), result.latency_ms,
    )
    return result
