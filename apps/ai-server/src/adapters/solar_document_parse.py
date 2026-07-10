"""Upstage Solar Document Parse adapter — layout-aware OCR via multipart upload.

Not an LLM adapter (no chat interface). Extends VendorAdapter directly.
Endpoint: POST /v1/document-digitization with model=document-parse.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.adapters.base import VendorAdapter
from src.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 120.0
_MAX_RETRIES = 2
_BACKOFF_BASE_S = 2.0
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class SolarDocumentParseAdapter(VendorAdapter):
    """Adapter for Upstage Document Parse.

    - Endpoint: ``POST {base_url}/document-digitization`` with ``model=document-parse``.
    - Multipart upload: ``document`` file + form fields.
    - Sync mode only (async endpoint exists but not used here — page limit 100 sync).
    - Supported formats: PDF, JPEG, PNG, BMP, TIFF, HEIC, DOCX, PPTX, XLSX, HWP, HWPX.
    - Max file size: 50MB.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.upstage_base_url.rstrip("/")
        self._api_key = settings.upstage_api_key
        self._model = "document-parse"

    @property
    def adapter_name(self) -> str:
        return "solar-document-parse"

    async def healthcheck(self) -> bool:
        """Ping Upstage models endpoint to verify API key + connectivity."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            logger.warning("solar-document-parse healthcheck failed", exc_info=True)
            return False

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(payload)
        for key in ("api_key", "authorization", "Authorization"):
            if key in redacted:
                redacted[key] = "***REDACTED***"
        # Never log document bytes
        if "document" in redacted:
            doc = redacted["document"]
            size = len(doc) if isinstance(doc, (bytes, bytearray)) else "?"
            redacted["document"] = f"<binary {size} bytes>"
        return redacted

    async def parse(
        self,
        document: bytes,
        filename: str,
        *,
        content_type: str = "application/pdf",
        output_formats: list[str] | None = None,
        coordinates: bool = True,
        chart_recognition: bool = True,
        ocr_mode: str = "auto",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Parse a document and return the raw Upstage response.

        Args:
            document: Raw bytes of the file.
            filename: Original filename (used in the multipart part).
            content_type: MIME type (defaults to PDF).
            output_formats: Which formats to request (default: markdown, text, html).
            coordinates: Whether to include bounding boxes per element.
            chart_recognition: Whether to run chart OCR.
            ocr_mode: 'auto' | 'force' (force runs OCR even on text-based PDFs).
            timeout_s: HTTP timeout.

        Returns:
            Raw JSON body from Upstage (dict). Includes ``elements``, ``content``,
            ``usage``, ``model`` fields.

        Raises:
            httpx.HTTPStatusError: on non-transient failure (4xx except 429).
            RuntimeError: after retries exhausted for transient failures.
        """
        if output_formats is None:
            output_formats = ["markdown", "text", "html"]

        url = f"{self._base_url}/document-digitization"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        import asyncio
        import json as _json

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    files = {"document": (filename, document, content_type)}
                    data = {
                        "model": self._model,
                        "ocr": ocr_mode,
                        "output_formats": _json.dumps(output_formats),
                        "coordinates": "true" if coordinates else "false",
                        "chart_recognition": "true" if chart_recognition else "false",
                    }
                    logger.debug(
                        "solar-document-parse request: %s",
                        self.redact_for_log({"url": url, "data": data, "document": document}),
                    )
                    resp = await client.post(url, headers=headers, files=files, data=data)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "solar-document-parse transient %d (attempt %d/%d), retry in %.1fs",
                        resp.status_code, attempt + 1, _MAX_RETRIES + 1, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                # Permanent failure — raise with details
                logger.error(
                    "solar-document-parse HTTP %d: %s", resp.status_code, resp.text[:500]
                )
                resp.raise_for_status()

            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "solar-document-parse connection error (attempt %d/%d), retry in %.1fs: %s",
                        attempt + 1, _MAX_RETRIES + 1, wait, exc,
                    )
                    await asyncio.sleep(wait)
                    continue

        raise RuntimeError(
            f"solar-document-parse failed after {_MAX_RETRIES + 1} attempts"
        ) from last_exc
