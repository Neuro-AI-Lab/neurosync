"""STT orchestration — file validation, storage, transcribe, 48h purge.

Platform owns consent / storage / retention; the AI server is a pure
transcription function (PRD §0.3, FR-033~037).

Storage: object storage (S3 SSE-KMS) is Phase 2. The demo writes encrypted-at-
rest-by-the-OS local files under `settings.audio_storage_dir`; `file_url` holds
the path. Swapping in S3 is confined to `store_audio` / `delete_audio_file`.
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from contracts.stt import STTRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.encryption import encrypt_str
from src.models.audio import AudioRecording, STTTranscription
from src.services.ai_client import AIClient, AIClientError

logger = logging.getLogger(__name__)

# Magic-number prefixes for the accepted encodings (FR-033).
_OGG_MAGIC = b"OggS"  # Opus is carried in an Ogg container
_RIFF_MAGIC = b"RIFF"
_WAVE_TAG = b"WAVE"


class STTError(Exception):
    """Maps to a specific HTTP status in the router via `.code` / `.http_status`."""

    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _transcription_aad(session_id: uuid.UUID | None, transcription_id: uuid.UUID) -> bytes:
    return f"stt_transcriptions.text:{session_id}:{transcription_id}".encode()


def validate_audio(data: bytes, encoding: str, *, settings: Settings) -> None:
    if not data:
        raise STTError("INVALID_AUDIO", "오디오가 비어 있어요.", 400)
    if len(data) > settings.audio_max_bytes:
        raise STTError("AUDIO_TOO_LARGE", "오디오가 너무 커요 (최대 2MB).", 413)
    if encoding == "opus":
        if not data.startswith(_OGG_MAGIC):
            raise STTError("INVALID_AUDIO", "Opus(Ogg) 형식이 아니에요.", 400)
    elif encoding == "pcm16":
        if not (data.startswith(_RIFF_MAGIC) and data[8:12] == _WAVE_TAG):
            raise STTError("INVALID_AUDIO", "WAV(PCM16) 형식이 아니에요.", 400)
    else:
        raise STTError("INVALID_AUDIO", f"지원하지 않는 인코딩이에요: {encoding}", 400)


def store_audio(data: bytes, *, recording_id: uuid.UUID, encoding: str, settings: Settings) -> str:
    """Persist bytes to local storage, return the file_url (path). S3 later."""
    ext = "ogg" if encoding == "opus" else "wav"
    os.makedirs(settings.audio_storage_dir, exist_ok=True)
    path = os.path.join(settings.audio_storage_dir, f"{recording_id}.{ext}")
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def delete_audio_file(file_url: str) -> None:
    try:
        if file_url and os.path.exists(file_url):
            os.remove(file_url)
    except OSError:
        logger.warning("audio.purge.file_remove_failed", extra={"file": file_url})


async def transcribe(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID,
    session_id: uuid.UUID,
    audio: bytes,
    encoding: str,
    sample_rate_hz: int,
    lang: str,
    prev_context: str,
    consent_snapshot_id: uuid.UUID,
    ai_client: AIClient,
    settings: Settings,
) -> tuple[STTTranscription, AudioRecording, str]:
    """Validate → store audio → call AI → persist transcription.

    Raises STTError (INVALID_AUDIO / AUDIO_TOO_LARGE / STT_LOW_CONFIDENCE /
    STT_UNAVAILABLE). FR-035: the transcription is NOT added as a message — the
    client edits and sends it explicitly via the WS chat.
    """
    validate_audio(audio, encoding, settings=settings)

    recording_id = uuid.uuid4()
    file_url = store_audio(
        audio, recording_id=recording_id, encoding=encoding, settings=settings
    )
    recording = AudioRecording(
        id=recording_id,
        session_id=session_id,
        patient_id=patient_id,
        file_url=file_url,
        encoding=encoding,
        sample_rate_hz=sample_rate_hz,
        duration_ms=0,  # filled from STT response below
        bytes=len(audio),
        consent_snapshot_id=consent_snapshot_id,
        delete_after=datetime.now(UTC)
        + timedelta(hours=settings.audio_retention_hours),
    )
    db.add(recording)
    await db.flush()

    try:
        result = await ai_client.stt_transcribe(
            STTRequest(
                audio_base64=base64.b64encode(audio).decode("ascii"),
                encoding=encoding,
                sample_rate_hz=sample_rate_hz,
                lang=lang,
                prev_context=prev_context[:500],
            )
        )
    except AIClientError as exc:
        logger.warning("stt.unavailable", extra={"error": str(exc)})
        raise STTError(
            "STT_UNAVAILABLE", "음성 인식을 사용할 수 없어요. 키보드로 입력해 주세요.", 503
        ) from exc

    recording.duration_ms = result.duration_ms

    # FR-037 — below the confidence floor, reject so the client falls back to text.
    if result.confidence < settings.stt_min_confidence:
        raise STTError(
            "STT_LOW_CONFIDENCE",
            "잘 들리지 않았어요. 다시 말씀하시거나 키보드로 입력해 주세요.",
            422,
        )

    transcription_id = uuid.uuid4()
    transcription = STTTranscription(
        id=transcription_id,
        audio_recording_id=recording.id,
        session_id=session_id,
        text_encrypted=encrypt_str(
            result.text,
            aad=_transcription_aad(session_id, transcription_id),
            settings=settings,
        ),
        confidence=Decimal(str(round(result.confidence, 3))),
        vendor=result.vendor.value,
        lang=lang,
        latency_ms=result.latency_ms,
        fallback_chain=[step.model_dump(mode="json") for step in result.fallback_chain]
        or None,
    )
    db.add(transcription)
    await db.flush()
    return transcription, recording, result.text


async def purge_expired_audio(
    db: AsyncSession, *, now: datetime | None = None, limit: int = 500
) -> int:
    """FR-036 — delete original audio files past their 48h window.

    Marks `deleted_at` and removes the file. Transcriptions are retained (they
    are patient speech, merged into the record). Returns the count purged.
    Intended to run on a schedule (Celery Beat); exposed as a function so a cron
    or the demo can trigger it directly.
    """
    cutoff = now or datetime.now(UTC)
    rows = await db.execute(
        select(AudioRecording)
        .where(
            AudioRecording.delete_after <= cutoff,
            AudioRecording.deleted_at.is_(None),
        )
        .limit(limit)
    )
    purged = 0
    for rec in rows.scalars().all():
        delete_audio_file(rec.file_url)
        rec.deleted_at = cutoff
        purged += 1
    if purged:
        await db.commit()
    return purged
