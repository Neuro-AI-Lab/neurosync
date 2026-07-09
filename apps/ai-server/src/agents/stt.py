"""STT (Speech-to-Text) agent — wraps SKT A.X Batch STT.

Contract: docs/ai/agents/06_stt.md.

- Fixed adapter (SKT A.X only, per agent_model_registry.yaml `ocr_agent` pattern).
- Not an LLM agent — extraction happens in the vendor.
- FR-035 (user confirmation): agent returns `user_confirmed=False`; caller
  (route/UI) must set True after human review.
- FR-036 (48h retention): agent surfaces expiry timestamp; actual deletion is
  the Platform's storage layer.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.adapters.skt_ak_stt import SktAkSttAdapter
from src.agents.base import BaseAgent
from src.schemas.stt import STTInput, STTOutput, STTSegment

logger = logging.getLogger(__name__)

_PROMPT_VERSION = "v1"  # spec is non-LLM — kept for AgentOutput schema uniformity
_RETENTION_HOURS = 48


class STTAgent(BaseAgent):
    """Batch STT for push-to-talk sessions."""

    def __init__(self, adapter: SktAkSttAdapter) -> None:
        self._adapter = adapter

    @property
    def agent_name(self) -> str:
        return "stt_agent"

    async def run(self, inp: Any, **kwargs: Any) -> STTOutput:
        raise NotImplementedError("Use STTAgent.transcribe(audio_bytes, meta) directly")

    async def transcribe(self, audio: bytes, meta: STTInput) -> STTOutput:
        """Run batch STT and return typed output.

        On adapter failure, returns an empty transcript with reason_summary set.
        Caller decides fallback (text input mode, re-record prompt, etc.).
        """
        started = time.perf_counter()

        message_id = meta.message_id_override or f"{meta.session_id}-{uuid.uuid4().hex[:8]}"
        try:
            raw = await self._adapter.transcribe(
                audio,
                message_id=message_id,
                keywords=meta.keywords,
                agreement_of_data_collection=meta.agreement_of_data_collection,
            )
        except Exception as exc:
            logger.error("STT adapter failed: %s", exc)
            return _empty_output(
                meta,
                reason=f"adapter_failure: {type(exc).__name__}",
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        # Parse the vendor response
        utterances = raw.get("utterances") or []
        segments: list[STTSegment] = []
        text_parts: list[str] = []
        for u in utterances:
            if not isinstance(u, dict):
                continue
            seg_text = str(u.get("text") or "").strip()
            if not seg_text:
                continue
            text_parts.append(seg_text)
            segments.append(
                STTSegment(
                    text=seg_text,
                    start_ms=int(u.get("start_time") or 0),
                    end_ms=int(u.get("end_time") or 0),
                    speaker=u.get("speaker"),
                )
            )
        full_text = " ".join(text_parts).strip()
        if not full_text and isinstance(raw.get("text"), str):
            full_text = raw["text"].strip()

        # Duration = last segment end_ms (fallback: 0 when no segments)
        duration_ms = segments[-1].end_ms if segments else 0

        # FR-036: mark 48h retention expiry
        expires_at = (
            datetime.now(UTC) + timedelta(hours=_RETENTION_HOURS)
        ).isoformat()

        latency_ms = (time.perf_counter() - started) * 1000

        return STTOutput(
            session_id=meta.session_id,
            patient_id=meta.patient_id,
            text=full_text,
            segments=segments,
            confidence=None,  # SKT A.X does not expose confidence (spec §6.7)
            mode=meta.mode,
            vendor="skt-ak-stt",
            audio_duration_ms=duration_ms,
            audio_retention_expires_at=expires_at,
            user_confirmed=False,  # FR-035: caller must obtain user confirmation
            timestamp=datetime.now().isoformat(),
            model_used=self._adapter._batch_model,  # noqa: SLF001 — direct access ok
            prompt_version=_PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary=(
                f"batch transcribed: {len(segments)} segment(s), {len(full_text)} chars"
                if full_text
                else "empty transcript (silence/noise/adapter error)"
            ),
        )


def _empty_output(meta: STTInput, reason: str, latency_ms: float) -> STTOutput:
    expires_at = (
        datetime.now(UTC) + timedelta(hours=_RETENTION_HOURS)
    ).isoformat()
    return STTOutput(
        session_id=meta.session_id,
        patient_id=meta.patient_id,
        text="",
        segments=[],
        confidence=None,
        mode=meta.mode,
        vendor="skt-ak-stt",
        audio_duration_ms=0,
        audio_retention_expires_at=expires_at,
        user_confirmed=False,
        timestamp=datetime.now().isoformat(),
        prompt_version=_PROMPT_VERSION,
        latency_ms=latency_ms,
        reason_summary=reason,
    )
