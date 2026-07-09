"""HIRA 약국정보서비스 어댑터.

Endpoint: GET https://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList

⚠️ 주의: 공식 operation 이름이 `getParmacyBasisList` (Pharmacy 아님, Parmacy 오타).
URL path를 임의로 고치지 않는다.

Reference: docs/ai/api/hira_kakao_map_api_usage_guide.md §3
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.adapters.hira_base import HiraApiError, HiraBaseAdapter
from src.config import Settings

logger = logging.getLogger(__name__)


class HiraPharmacyAdapter(HiraBaseAdapter):
    """HIRA 약국정보서비스 (Pharmacy Basis List)."""

    operation = "getParmacyBasisList"  # 원문 오타 유지 (spec §3.7)

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.base_url = settings.hira_pharmacy_service_url.rstrip("/")

    @property
    def adapter_name(self) -> str:
        return "hira-pharmacy"

    async def search(
        self,
        *,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius_m: Optional[int] = None,
        name: Optional[str] = None,
        sido_code: Optional[str] = None,
        sggu_code: Optional[str] = None,
        emdong_name: Optional[str] = None,
        page_no: int = 1,
        num_of_rows: int = 20,
    ) -> tuple[dict, list[dict], dict]:
        """Search pharmacies. Returns (header, items, body_meta)."""
        params: dict[str, Any] = {
            "pageNo": page_no,
            "numOfRows": num_of_rows,
        }
        if lat is not None and lng is not None:
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
        if emdong_name:
            params["emdongNm"] = emdong_name

        body = await self._fetch_page(params)
        header, items, body_meta = self.parse_envelope(body)
        self.check_success(header)

        logger.info(
            "hira-pharmacy fetched %d/%d (page %d, total %d)",
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
        """Aggregate multi-page results. Returns (last_header, items, meta, truncated)."""
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
                if pages_fetched == 0:
                    raise
                logger.warning(
                    "hira-pharmacy search_all: page %d failed (%s), truncating",
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
