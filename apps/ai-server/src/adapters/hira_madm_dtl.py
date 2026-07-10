"""HIRA MadmDtlInfoService2.8 — 의료기관별 상세정보서비스 어댑터.

병원(ykiho) 단위로 진료과목별 전문의 수 등 상세 정보를 조회한다.
Nearby 검색에서 정신건강의학과 전문의 존재 여부 (specialist_verified) 검증에 사용.

Endpoint: GET {HIRA_MADM_DTL_SERVICE_URL}/getDgsbjtInfo2.8
Auth:     query param `serviceKey` (HIRA_SERVICE_KEY 공유)

미승인 상태(403)이면 어댑터는 조용히 실패 반환. 호출자(NearbyFacilitiesAgent)가
fallback을 유지하도록 예외를 흡수한다.

Response envelope (관례상 HIRA 공통):
{
  "response": {
    "header": {"resultCode": "00", ...},
    "body": {
      "items": {"item": [{"dgsbjtCd": "03", "dgsbjtCdNm": "정신건강의학과",
                          "dgsbjtPrSdrCnt": 2, ...}, ...]},
      ...
    }
  }
}

전문의 수 필드는 버전별로 이름이 다를 수 있어 여러 후보를 확인한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.adapters.base import VendorAdapter
from src.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 10.0
_MAX_RETRIES = 2
_BACKOFF_BASE_S = 1.0
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}  # 403은 재시도 대상 아님

# 진료과목별 전문의 수 후보 필드 (HIRA 응답 필드명이 스펙 판본마다 상이)
_SPECIALIST_COUNT_FIELDS = (
    "dgsbjtPrSdrCnt",  # 진료과목별 전문의 수 (가장 유력)
    "specialistCount",
    "prSdrCnt",
    "cdiagDrCnt",  # 참고: 유사 필드
)


class HiraMadmDtlAdapter(VendorAdapter):
    """HIRA MadmDtl (의료기관별 상세정보) client — 진료과별 전문의 수 조회."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.hira_madm_dtl_service_url.rstrip("/")
        self._service_key = settings.hira_service_key

    @property
    def adapter_name(self) -> str:
        return "hira-madm-dtl"

    async def healthcheck(self) -> bool:
        # 아무 ykiho에 대해 호출 가능한지만 확인. 승인 미완이면 False.
        try:
            probe_ykiho = (
                "JDQ4MTg4MSM1MSMkMSMkMCMkODkkMzgxMzUxIzExIyQyIyQ3IyQwMCQ0NjEwMDIjNTEjJDEjJDYjJDgz"
            )
            counts = await self.get_dgsbjt_specialist_counts(probe_ykiho)
            return counts is not None
        except Exception:
            return False

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(payload)
        if "serviceKey" in redacted:
            redacted["serviceKey"] = "***REDACTED***"
        return redacted

    async def get_dgsbjt_specialist_counts(
        self,
        ykiho: str,
        *,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> dict[str, int] | None:
        """`ykiho` 병원의 {dgsbjtCd → 전문의 수} 매핑을 반환.

        Returns:
            성공 시 `{"03": 2, "01": 5, ...}` 형태.
            401/403 (미승인) 또는 재시도 초과 실패 시 `None`.
            응답 정상이지만 items 비어있으면 `{}`.
        """
        if not self._service_key:
            logger.warning("hira-madm-dtl: HIRA_SERVICE_KEY 미설정, skip")
            return None

        url = f"{self._base_url}/getDgsbjtInfo2.8"
        params: dict[str, Any] = {
            "serviceKey": self._service_key,
            "ykiho": ykiho,
            "_type": "json",
            "numOfRows": 50,
            "pageNo": 1,
        }

        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    r = await client.get(url, params=params)

                if r.status_code == 200:
                    return self._parse_counts(r.text)
                if r.status_code in (401, 403):
                    logger.info(
                        "hira-madm-dtl unauthorized (%d) — API 승인 미완 · fallback",
                        r.status_code,
                    )
                    return None
                if r.status_code in _TRANSIENT_STATUS_CODES and attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue
                logger.warning(
                    "hira-madm-dtl HTTP %d for ykiho=%s: %s",
                    r.status_code, ykiho[:12], r.text[:200],
                )
                return None
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE_S * (2**attempt))
                    continue
                logger.warning("hira-madm-dtl request failed: %s", exc)
                return None
        return None

    @staticmethod
    def _parse_counts(body_text: str) -> dict[str, int]:
        """응답 JSON body 파싱 → {dgsbjtCd: count}."""
        import json as _json

        try:
            body = _json.loads(body_text)
        except _json.JSONDecodeError:
            logger.warning("hira-madm-dtl invalid JSON: %s", body_text[:200])
            return {}

        resp = body.get("response") or {}
        header = resp.get("header") or {}
        result_code = str(header.get("resultCode", ""))
        if result_code and result_code != "00":
            logger.info(
                "hira-madm-dtl non-success resultCode=%s msg=%s",
                result_code, header.get("resultMsg"),
            )
            return {}

        items_wrap = (resp.get("body") or {}).get("items") or {}
        raw_items = items_wrap.get("item")
        if raw_items is None:
            return {}
        # 단일 item이 dict로 오는 경우도 있음
        items = raw_items if isinstance(raw_items, list) else [raw_items]

        counts: dict[str, int] = {}
        for it in items:
            code = str(it.get("dgsbjtCd") or "").strip()
            if not code:
                continue
            cnt = None
            for f in _SPECIALIST_COUNT_FIELDS:
                v = it.get(f)
                if v is None or v == "":
                    continue
                try:
                    cnt = int(v)
                    break
                except (TypeError, ValueError):
                    continue
            if cnt is not None:
                counts[code] = cnt
        return counts
