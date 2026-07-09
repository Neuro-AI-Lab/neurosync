"""HIRA 병원정보서비스 어댑터.

Endpoint: POST https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList
Reference: docs/ai/api/hira_kakao_map_api_usage_guide.md §2
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.adapters.hira_base import HiraApiError, HiraBaseAdapter
from src.config import Settings

logger = logging.getLogger(__name__)


class HiraHospitalAdapter(HiraBaseAdapter):
    """HIRA 병원정보서비스 (Hospital Basis List)."""

    operation = "getHospBasisList"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.base_url = settings.hira_hospital_service_url.rstrip("/")

    @property
    def adapter_name(self) -> str:
        return "hira-hospital"

    async def search(
        self,
        *,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius_m: Optional[int] = None,
        name: Optional[str] = None,
        sido_code: Optional[str] = None,
        sggu_code: Optional[str] = None,
        subject_code: Optional[str] = None,
        hospital_type_code: Optional[str] = None,
        page_no: int = 1,
        num_of_rows: int = 20,
    ) -> tuple[dict, list[dict], dict]:
        """Search hospitals. Returns (header, items, body_meta).

        Args:
            lat, lng, radius_m: 위치 기반 검색 (radius는 미터 단위)
            name: 병원명 검색어 (yadmNm)
            sido_code, sggu_code: 시도/시군구 코드
            subject_code: 진료과목 코드 (dgsbjtCd)
            hospital_type_code: 의료기관 종별 코드 (clCd)
            page_no, num_of_rows: 페이지네이션

        Raises:
            HiraApiError: HIRA header.resultCode != '00'
        """
        params: dict[str, Any] = {
            "pageNo": page_no,
            "numOfRows": num_of_rows,
        }
        if lat is not None and lng is not None:
            # HIRA: xPos = 경도 (longitude), yPos = 위도 (latitude)
            params["xPos"] = f"{lng:.6f}"
            params["yPos"] = f"{lat:.6f}"
            if radius_m is not None:
                params["radius"] = int(radius_m)
        if name:
            params["yadmNm"] = name
        if sido_code:
            params["sidoCd"] = sido_code
        if sggu_code:
            params["sgguCd"] = sggu_code
        if subject_code:
            params["dgsbjtCd"] = subject_code
        if hospital_type_code:
            params["clCd"] = hospital_type_code

        body = await self._fetch_page(params)
        header, items, body_meta = self.parse_envelope(body)
        # Non-success codes → raise (caller can catch and produce empty response)
        self.check_success(header)

        logger.info(
            "hira-hospital fetched %d/%d (page %d, total %d)",
            len(items),
            body_meta["numOfRows"],
            body_meta["pageNo"],
            body_meta["totalCount"],
        )
        return header, items, body_meta

    async def search_all(
        self,
        *,
        max_pages: int = 10,
        num_of_rows: int = 1000,
        **kwargs: Any,
    ) -> tuple[dict, list[dict], dict, bool]:
        """Aggregate multi-page results. Returns (last_header, items, meta, truncated).

        Stops when:
        - page < max_pages AND items exhausted (totalCount reached)
        - OR page reaches max_pages (truncated=True)
        """
        all_items: list[dict] = []
        last_header: dict = {}
        last_meta: dict = {
            "numOfRows": num_of_rows,
            "pageNo": 1,
            "totalCount": 0,
        }
        truncated = False
        pages_fetched = 0

        for page in range(1, max_pages + 1):
            try:
                header, items, meta = await self.search(
                    page_no=page,
                    num_of_rows=num_of_rows,
                    **kwargs,
                )
            except HiraApiError as exc:
                # First-page error → propagate; later-page error → truncate
                if pages_fetched == 0:
                    raise
                logger.warning(
                    "hira-hospital search_all: page %d failed (%s), truncating",
                    page, exc,
                )
                truncated = True
                break

            all_items.extend(items)
            last_header = header
            last_meta = meta
            pages_fetched = page

            if len(all_items) >= meta["totalCount"] or not items:
                break
            if page >= max_pages:
                truncated = True

        return last_header, all_items, last_meta, truncated
