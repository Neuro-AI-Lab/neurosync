"""HIRA (건강보험심사평가원) Open API 공통 클라이언트.

- Base URL은 서비스별로 다르지만 요청/응답 envelope은 동일.
- ServiceKey는 Backend에서만 사용 (client 노출 금지).
- 응답은 `_type=json`으로 강제하여 JSON envelope만 파싱.
  (XML fallback은 별도 구현. HIRA는 `_type=xml` 미지정 시에도 JSON 반환 가능.)
- 재시도: 429/5xx 지수 백오프, 최대 3회.

Reference: docs/ai/api/hira_kakao_map_api_usage_guide.md §2, §3
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.adapters.base import VendorAdapter
from src.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 30.0
_MAX_RETRIES = 2
_BACKOFF_BASE_S = 1.0
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class HiraApiError(RuntimeError):
    """Raised when HIRA returns a non-success resultCode after normalization."""

    def __init__(self, result_code: str, result_msg: str) -> None:
        self.result_code = result_code
        self.result_msg = result_msg
        super().__init__(f"HIRA upstream error {result_code}: {result_msg}")


class HiraBaseAdapter(VendorAdapter):
    """Common client for HIRA Open API services.

    Subclasses provide:
    - ``adapter_name`` (property)
    - ``base_url`` (constant)
    - ``operation`` (default operation name, e.g. 'getHospBasisList')
    """

    base_url: str = ""
    operation: str = ""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.hira_service_key

    async def healthcheck(self) -> bool:
        """Cheap ping — issue a size=1 request to verify auth+base URL."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self.base_url}/{self.operation}",
                    params={
                        "ServiceKey": self._api_key,
                        "_type": "json",
                        "pageNo": 1,
                        "numOfRows": 1,
                    },
                )
                # 200 with valid body means auth+URL OK.
                return r.status_code == 200
        except Exception:
            logger.warning("%s healthcheck failed", self.adapter_name, exc_info=True)
            return False

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(payload)
        for key in ("ServiceKey", "serviceKey", "api_key", "authorization", "Authorization"):
            if key in redacted:
                redacted[key] = "***REDACTED***"
        return redacted

    async def _fetch_page(
        self,
        params: dict[str, Any],
        *,
        operation: str | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Fetch a single page. Returns the full HIRA envelope (dict).

        Raises:
            HiraApiError: resultCode != '00' after retries.
            httpx.HTTPStatusError: unrecoverable HTTP failure.
            RuntimeError: after transient retries exhausted.
        """
        if not self._api_key:
            raise RuntimeError(
                f"{self.adapter_name}: HIRA_SERVICE_KEY not configured"
            )

        op = operation or self.operation
        url = f"{self.base_url}/{op}"
        query = {**params, "ServiceKey": self._api_key, "_type": "json"}

        logger.debug(
            "%s request: %s",
            self.adapter_name,
            self.redact_for_log({"url": url, **query}),
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    r = await client.get(url, params=query)

                if r.status_code == 200:
                    return self._safe_json(r)

                if r.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "%s transient %d, retry in %.1fs (attempt %d/%d)",
                        self.adapter_name, r.status_code, wait,
                        attempt + 1, _MAX_RETRIES + 1,
                    )
                    await asyncio.sleep(wait)
                    continue

                logger.error(
                    "%s HTTP %d: %s", self.adapter_name, r.status_code, r.text[:500]
                )
                r.raise_for_status()

            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "%s connection error (attempt %d/%d), retry in %.1fs: %s",
                        self.adapter_name, attempt + 1, _MAX_RETRIES + 1, wait, exc,
                    )
                    await asyncio.sleep(wait)
                    continue

        raise RuntimeError(
            f"{self.adapter_name}: failed after {_MAX_RETRIES + 1} attempts"
        ) from last_exc

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        """Parse response as JSON. HIRA sometimes returns XML on error even
        when _type=json is requested; catch and wrap gracefully."""
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError(f"expected dict, got {type(body).__name__}")
            return body
        except (ValueError, TypeError) as exc:
            # Log first 300 chars for triage
            raise RuntimeError(
                f"HIRA response is not valid JSON (received {len(response.text)} bytes): "
                f"{response.text[:300]}"
            ) from exc

    @staticmethod
    def parse_envelope(body: dict[str, Any]) -> tuple[dict, list[dict], dict]:
        """Extract (header, items, body_meta) from HIRA JSON envelope.

        HIRA envelope:
            {"response": {"header": {...}, "body": {"items": {"item": [...] or {...}},
                                                     "numOfRows", "pageNo", "totalCount"}}}

        `items.item` can be:
        - a list (multiple results)
        - a single dict (one result — HIRA collapses)
        - missing (zero results)

        Returns:
            header: dict (resultCode, resultMsg)
            items: list[dict] (always a list, even for single/zero results)
            body_meta: dict (numOfRows, pageNo, totalCount)
        """
        response = body.get("response", {}) if isinstance(body, dict) else {}
        header = response.get("header", {}) or {}
        body_obj = response.get("body", {}) or {}

        items_wrap = body_obj.get("items") or {}
        if isinstance(items_wrap, dict):
            raw_items = items_wrap.get("item")
        else:
            raw_items = None

        if raw_items is None:
            items: list[dict] = []
        elif isinstance(raw_items, list):
            items = [i for i in raw_items if isinstance(i, dict)]
        elif isinstance(raw_items, dict):
            items = [raw_items]
        else:
            items = []

        body_meta = {
            "numOfRows": int(body_obj.get("numOfRows") or 0),
            "pageNo": int(body_obj.get("pageNo") or 1),
            "totalCount": int(body_obj.get("totalCount") or 0),
        }
        return header, items, body_meta

    @staticmethod
    def check_success(header: dict) -> None:
        """Raise HiraApiError when header.resultCode is not '00'."""
        code = str(header.get("resultCode", "")).strip()
        msg = str(header.get("resultMsg", "")).strip()
        if code and code != "00":
            raise HiraApiError(result_code=code, result_msg=msg or "unknown error")
