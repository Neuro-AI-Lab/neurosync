"""Kakao Local REST API 어댑터.

주소 문자열 → 좌표 변환 (geocoding). HIRA 좌표가 없거나 검증 필요한 경우 fallback.

Endpoint: GET https://dapi.kakao.com/v2/local/search/address.json
Auth:     Authorization: KakaoAK {KAKAO_REST_API_KEY}

Reference: docs/ai/api/hira_kakao_map_api_usage_guide.md §7
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.adapters.base import VendorAdapter
from src.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 15.0
_MAX_RETRIES = 2
_BACKOFF_BASE_S = 1.0
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class KakaoLocalAdapter(VendorAdapter):
    """Kakao Local REST API — address geocoding.

    Non-LLM adapter. Backend only — REST key must NOT reach client.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.kakao_local_rest_base_url.rstrip("/")
        self._api_key = settings.kakao_rest_api_key

    @property
    def adapter_name(self) -> str:
        return "kakao-local"

    async def healthcheck(self) -> bool:
        """Cheap ping — probe with a well-known address."""
        try:
            result = await self.search_address("서울특별시청")
            return bool(result.get("documents"))
        except Exception:
            logger.warning("kakao-local healthcheck failed", exc_info=True)
            return False

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(payload)
        for key in ("Authorization", "authorization"):
            if key in redacted:
                redacted[key] = "***REDACTED***"
        return redacted

    async def search_address(
        self,
        query: str,
        *,
        analyze_type: str | None = None,
        page: int = 1,
        size: int = 10,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Geocode a Korean address.

        Args:
            query: 주소 문자열 (도로명 또는 지번)
            analyze_type: 'similar' (기본, 유사 매칭) | 'exact'
            page: 1-based
            size: 최대 30

        Returns:
            Raw Kakao response body:
            {
              "documents": [{
                "address_name": "...", "x": "127.05983", "y": "37.61955",
                "address": {...}, "road_address": {...}
              }],
              "meta": {"total_count", "pageable_count", "is_end"}
            }
        """
        if not self._api_key:
            raise RuntimeError("kakao-local: KAKAO_REST_API_KEY not configured")

        url = f"{self._base_url}/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {self._api_key}"}
        params: dict[str, Any] = {"query": query, "page": page, "size": size}
        if analyze_type in {"similar", "exact"}:
            params["analyze_type"] = analyze_type

        logger.debug(
            "kakao-local request: %s",
            self.redact_for_log({"url": url, **params, **headers}),
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    r = await client.get(url, headers=headers, params=params)

                if r.status_code == 200:
                    return r.json()

                if r.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "kakao-local transient %d, retry in %.1fs (attempt %d/%d)",
                        r.status_code, wait, attempt + 1, _MAX_RETRIES + 1,
                    )
                    await asyncio.sleep(wait)
                    continue

                logger.error(
                    "kakao-local HTTP %d: %s", r.status_code, r.text[:300]
                )
                r.raise_for_status()

            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue

        raise RuntimeError(
            f"kakao-local: search_address failed after {_MAX_RETRIES + 1} attempts"
        ) from last_exc

    async def search_keyword(
        self,
        query: str,
        *,
        lng: float | None = None,
        lat: float | None = None,
        radius_m: int | None = None,
        category_group_code: str | None = None,
        page: int = 1,
        size: int = 15,
        sort: str = "distance",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Kakao Local keyword search.

        Endpoint: GET /v2/local/search/keyword.json
        - `category_group_code=HP8`이면 병원 카테고리만.
        - 응답 document의 `category_name`은 "의료,건강 > 병원 > 정신건강의학과"
          형태로 세분되어 있어, 정신과 전문 여부 판별에 사용 가능.
        - `radius_m` 범위 max 20000m.
        """
        if not self._api_key:
            raise RuntimeError("kakao-local: KAKAO_REST_API_KEY not configured")

        url = f"{self._base_url}/v2/local/search/keyword.json"
        headers = {"Authorization": f"KakaoAK {self._api_key}"}
        params: dict[str, Any] = {"query": query, "page": page, "size": size, "sort": sort}
        if lng is not None and lat is not None:
            params["x"] = f"{lng:.6f}"
            params["y"] = f"{lat:.6f}"
            if radius_m is not None:
                params["radius"] = int(radius_m)
        if category_group_code:
            params["category_group_code"] = category_group_code

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    r = await client.get(url, headers=headers, params=params)

                if r.status_code == 200:
                    return r.json()
                if r.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue
                logger.error("kakao-local keyword HTTP %d: %s", r.status_code, r.text[:300])
                r.raise_for_status()
            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue

        raise RuntimeError(
            f"kakao-local: search_keyword failed after {_MAX_RETRIES + 1} attempts"
        ) from last_exc

    async def geocode(self, address: str) -> tuple[float, float] | None:
        """Convenience: return (lat, lng) or None on no result / failure.

        Spec §0 규칙: HIRA 좌표가 있으면 항상 우선. Kakao 결과는 fallback.
        """
        try:
            body = await self.search_address(address, size=1)
        except Exception as exc:
            logger.warning("kakao-local geocode failed for %r: %s", address, exc)
            return None

        docs = body.get("documents") or []
        if not docs:
            return None
        doc = docs[0]
        try:
            lng = float(doc["x"])
            lat = float(doc["y"])
        except (KeyError, TypeError, ValueError):
            return None
        return lat, lng
