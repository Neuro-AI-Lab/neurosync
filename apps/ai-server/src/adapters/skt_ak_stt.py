"""SKT A.X STT Batch adapter — REST-only implementation.

Streaming (WebSocket) support is not included in this initial adapter — batch
covers the F1 push-to-talk use case (short 5~15s utterances) with acceptable
latency (< 1s for typical VP-scale audio).

Flow (docs/ai/api/SKT_A_X_API.md §6):
    1. GET  /v1/stt/upload-token?fileSize=N   → upload_token
    2. PUT  /v1/stt/upload/{upload_token}     → file_key
    3. POST /v1/stt/transcript                → utterances[], words[], ...

Auth: header ``X-API-Key: $SKT_A_X_API_KEY``.
No native confidence field — spec §6.7 explicitly warns against fabricating one.

Not an LLM adapter — extends VendorAdapter directly (same pattern as
SolarDocumentParseAdapter).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.adapters.base import VendorAdapter
from src.config import Settings

logger = logging.getLogger(__name__)

_UPLOAD_TIMEOUT_S = 60.0
_TRANSCRIPT_TIMEOUT_S = 180.0
_MAX_RETRIES = 2
_BACKOFF_BASE_S = 2.0
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class SktAkSttAdapter(VendorAdapter):
    """Adapter for SKT A.X STT Batch API.

    - Endpoint base: ``https://awf-gw.adot.ai``
    - Header auth: ``X-API-Key``
    - Model: ``A.X_STT_note_batch``
    - File limits (spec §6.6): 100MB / 30분 per file
    - No confidence score in response — caller must not synthesize one.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.skt_a_x_rest_base_url.rstrip("/")
        self._api_key = settings.skt_a_x_api_key
        self._batch_model = settings.skt_a_x_stt_batch_model or "A.X_STT_note_batch"

    @property
    def adapter_name(self) -> str:
        return "skt-ak-stt"

    async def healthcheck(self) -> bool:
        """Cheap ping — issue a HEAD to upload-token with size=1 to verify auth+base URL."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self._base_url}/v1/stt/upload-token",
                    params={"fileSize": 1},
                    headers={"X-API-Key": self._api_key},
                )
                # 200 OK means auth+URL are OK. 4xx from server also proves reachability.
                return r.status_code < 500
        except Exception:
            logger.warning("skt-ak-stt healthcheck failed", exc_info=True)
            return False

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(payload)
        for key in ("api_key", "X-API-Key", "x-api-key", "authorization", "Authorization"):
            if key in redacted:
                redacted[key] = "***REDACTED***"
        if "audio" in redacted:
            length = (
                len(redacted["audio"])
                if isinstance(redacted["audio"], (bytes, bytearray))
                else "?"
            )
            redacted["audio"] = f"<binary {length} bytes>"
        return redacted

    async def transcribe(
        self,
        audio: bytes,
        *,
        message_id: str,
        keywords: list[str] | None = None,
        agreement_of_data_collection: bool = False,
        speech_model: str | None = None,
        timeout_s: float = _TRANSCRIPT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Full batch pipeline. Returns raw transcript response body.

        Raises:
            httpx.HTTPStatusError: on non-transient failure.
            RuntimeError: after retries exhausted.
        """
        model = speech_model or self._batch_model
        if not self._api_key:
            raise RuntimeError("skt-ak-stt: SKT_A_X_API_KEY not configured")

        headers_auth = {"X-API-Key": self._api_key}

        # Step 1: upload token (with retry on transient failures)
        upload_token = await self._issue_upload_token(len(audio), headers_auth)

        # Step 2: upload the file
        file_key = await self._upload_file(audio, upload_token, headers_auth)

        # Step 3: transcript
        payload = {
            "message_id": message_id,
            "speech_model": model,
            "audio_file_key": file_key,
            "keywords": list(keywords or []),
            "agreement_of_data_collection": agreement_of_data_collection,
        }
        logger.debug(
            "skt-ak-stt transcript request: %s",
            self.redact_for_log({**headers_auth, **payload, "audio": audio}),
        )
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    r = await client.post(
                        f"{self._base_url}/v1/stt/transcript",
                        headers={**headers_auth, "Content-Type": "application/json"},
                        json=payload,
                    )
                if r.status_code == 200:
                    return r.json()
                if r.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "skt-ak-stt transcript %d, retry in %.1fs (attempt %d/%d)",
                        r.status_code, wait, attempt + 1, _MAX_RETRIES + 1,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error("skt-ak-stt transcript HTTP %d: %s", r.status_code, r.text[:500])
                r.raise_for_status()
            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    await asyncio.sleep(wait)
                    continue
        raise RuntimeError(
            f"skt-ak-stt: transcript failed after {_MAX_RETRIES + 1} attempts"
        ) from last_exc

    # ── Internal helpers ────────────────────────────────────────────

    async def _issue_upload_token(self, file_size: int, auth: dict[str, str]) -> str:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT_S) as client:
                    r = await client.get(
                        f"{self._base_url}/v1/stt/upload-token",
                        params={"fileSize": file_size},
                        headers=auth,
                    )
                if r.status_code == 200:
                    token = r.json().get("upload_token")
                    if not token:
                        raise RuntimeError("skt-ak-stt: upload_token missing in response")
                    return token
                if r.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue
                logger.error(
                    "skt-ak-stt upload-token HTTP %d: %s", r.status_code, r.text[:300]
                )
                r.raise_for_status()
            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue
        raise RuntimeError("skt-ak-stt: upload-token failed") from last_exc

    async def _upload_file(
        self, audio: bytes, upload_token: str, auth: dict[str, str]
    ) -> str:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT_S) as client:
                    r = await client.put(
                        f"{self._base_url}/v1/stt/upload/{upload_token}",
                        headers={**auth, "Content-Type": "application/octet-stream"},
                        content=audio,
                    )
                if r.status_code == 200:
                    file_key = r.json().get("file_key")
                    if not file_key:
                        raise RuntimeError("skt-ak-stt: file_key missing in response")
                    return file_key
                if r.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue
                logger.error(
                    "skt-ak-stt upload HTTP %d: %s", r.status_code, r.text[:300]
                )
                r.raise_for_status()
            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue
        raise RuntimeError("skt-ak-stt: file upload failed") from last_exc
