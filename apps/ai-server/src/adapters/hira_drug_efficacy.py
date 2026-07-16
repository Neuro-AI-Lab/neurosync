"""HIRA 의약품성분약효정보조회서비스 어댑터.

일반명코드(gnlNmCd) → 약효분류번호(meftDivNo)·분류명(divNm) 조회.
PHR MedicationDispense의 성분코드(= HIRA 일반명코드)로 정신과 약물 여부를
authoritative 하게 판정하기 위해 사용한다 (하드코딩 카탈로그 대체).

Endpoint: GET {HIRA_DRUG_EFFICACY_SERVICE_URL}/getMajorCmpnNmCdList
Auth:     query param `ServiceKey` (HIRA_SERVICE_KEY 공유)

Response envelope (HIRA 공통):
{
  "response": {
    "header": {"resultCode": "00", ...},
    "body": {"items": {"item": [{"gnlNmCd": "474802ATB", "meftDivNo": 117,
                                 "divNm": "정신신경용제", "gnlNm": "escitalopram ...",
                                 ...}]}}
  }
}

한 일반명코드는 (성분/함량/제형 단위라) 보통 단일 약효분류로 매핑되므로 첫 item만
사용한다. 미승인(403)·키 미설정·네트워크 실패 시 조용히 `None` 반환 —
호출자(PatientHistoryAgent)가 캐시/보류 fallback을 유지한다.

Reference: docs/ai/psychotropic_classification.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from src.adapters.hira_base import HiraApiError, HiraBaseAdapter
from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EfficacyInfo:
    """의약품성분약효정보 단건 — 분류 판정에 필요한 필드만."""

    gnl_nm_cd: str
    meft_div_no: int | None
    div_nm: str
    gnl_nm: str = ""


class HiraDrugEfficacyAdapter(HiraBaseAdapter):
    """HIRA 의약품성분약효정보조회서비스 (일반명코드 → 약효분류)."""

    operation = "getMajorCmpnNmCdList"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.base_url = settings.hira_drug_efficacy_service_url.rstrip("/")

    @property
    def adapter_name(self) -> str:
        return "hira-drug-efficacy"

    async def get_efficacy(self, gnl_nm_cd: str | None) -> EfficacyInfo | None:
        """일반명코드(gnlNmCd)의 약효분류 정보 조회.

        Returns:
            성공 시 `EfficacyInfo`.
            코드 없음/키 미설정/미승인(401·403)/네트워크 실패/미조회 시 `None`.
        """
        code = (gnl_nm_cd or "").strip()
        if not code:
            return None
        if not self._api_key:
            logger.info("hira-drug-efficacy: HIRA_SERVICE_KEY 미설정, skip")
            return None

        params: dict[str, Any] = {
            "gnlNmCd": code,
            "pageNo": 1,
            "numOfRows": 1,
        }
        try:
            body = await self._fetch_page(params)
        except HiraApiError as exc:
            logger.info(
                "hira-drug-efficacy resultCode=%s for %s — skip",
                exc.result_code, code,
            )
            return None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.info(
                "hira-drug-efficacy HTTP %s for %s — 미승인/오류 · fallback",
                status, code,
            )
            return None
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("hira-drug-efficacy request failed for %s: %s", code, exc)
            return None

        _header, items, _meta = self.parse_envelope(body)
        if not items:
            logger.info("hira-drug-efficacy: %s 미조회 (빈 응답)", code)
            return None
        return self._to_info(items[0], fallback_code=code)

    @staticmethod
    def _to_info(item: dict[str, Any], *, fallback_code: str) -> EfficacyInfo:
        meft_raw = item.get("meftDivNo")
        try:
            meft = int(meft_raw) if meft_raw not in (None, "") else None
        except (TypeError, ValueError):
            meft = None
        return EfficacyInfo(
            gnl_nm_cd=str(item.get("gnlNmCd") or fallback_code),
            meft_div_no=meft,
            div_nm=str(item.get("divNm") or ""),
            gnl_nm=str(item.get("gnlNm") or ""),
        )
