"""Nearby Facilities agent — HIRA 병원/약국 원본 응답을 앱 계약으로 정규화.

Contract: docs/ai/api/hira_kakao_map_api_usage_guide.md §4.

Responsibilities:
1. HIRA 어댑터 호출 (병원/약국 각각)
2. HIRA raw items → typed Place / Marker
3. XPos/YPos → lng/lat 변환 (⚠️ HIRA XPos = 경도, YPos = 위도)
4. 거리 계산 (Haversine, 기준점 있을 때만)
5. 반경 필터 (radius_km)
6. 가까운 순 정렬
7. Kakao Map marker payload 생성 (Place와 동일 id 체계)

Safety (spec §10):
- `emergency_available`, `open_now` 등 nullable 필드는 절대 True로 채우지 않음.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from src.adapters.hira_base import HiraApiError
from src.adapters.hira_hospital import HiraHospitalAdapter
from src.adapters.hira_pharmacy import HiraPharmacyAdapter
from src.agents.base import BaseAgent
from src.schemas.nearby import (
    DEFAULT_NOTICE_HOSPITAL,
    DEFAULT_NOTICE_PHARMACY,
    MapPayload,
    Marker,
    NearbyReportInput,
    NearbyResponse,
    NearbySearchInput,
    Place,
    SourceMeta,
)

logger = logging.getLogger(__name__)

_EARTH_RADIUS_KM = 6371.0088


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km (WGS84 sphere approx)."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_hira_item(
    item: dict[str, Any],
    entity_type: str,
    *,
    user_lat: float | None,
    user_lng: float | None,
) -> Place | None:
    """HIRA 원본 item → typed Place. 좌표 없으면 lat/lng는 None."""
    ykiho = str(item.get("ykiho") or "").strip()
    if not ykiho:
        # ykiho 없는 이상 케이스 — 스킵 (id를 만들 수 없음)
        return None

    xpos = _safe_float(item.get("XPos"))  # 경도
    ypos = _safe_float(item.get("YPos"))  # 위도
    # Sanity: KR 좌표는 위도 33~39, 경도 124~132 대략. 벗어나면 무시.
    if xpos is not None and not (120.0 <= xpos <= 135.0):
        xpos = None
    if ypos is not None and not (30.0 <= ypos <= 45.0):
        ypos = None

    distance_km: float | None = None
    if user_lat is not None and user_lng is not None and ypos is not None and xpos is not None:
        distance_km = round(_haversine_km(user_lat, user_lng, ypos, xpos), 3)

    place = Place(
        id=f"{entity_type}:{ykiho}",
        entity_type=entity_type,  # type: ignore[arg-type]
        source_id=ykiho,
        name=str(item.get("yadmNm") or "").strip(),
        title=str(item.get("yadmNm") or "").strip(),
        address=str(item.get("addr") or "").strip(),
        phone=str(item.get("telno") or "").strip(),
        sido_code=str(item.get("sidoCd") or "").strip() or None,
        sido_name=str(item.get("sidoCdNm") or "").strip() or None,
        sggu_code=str(item.get("sgguCd") or "").strip() or None,
        sggu_name=str(item.get("sgguCdNm") or "").strip() or None,
        lat=ypos,
        lng=xpos,
        latitude=ypos,
        longitude=xpos,
        coordinate_source="hira" if (xpos is not None and ypos is not None) else None,
        distance_km=distance_km,
    )

    # Hospital-only fields
    if entity_type == "hospital":
        place.type_code = str(item.get("clCd") or "").strip() or None
        place.type_name = str(item.get("clCdNm") or "").strip() or None
        place.subject_code = str(item.get("dgsbjtCd") or "").strip() or None
        place.subject_name = str(item.get("dgsbjtCdNm") or "").strip() or None

    return place


def _build_marker(place: Place) -> Marker | None:
    """Place → Marker. 좌표 없으면 None (marker 제외)."""
    if place.lat is None or place.lng is None:
        return None
    return Marker(
        id=place.id,
        entity_type=place.entity_type,
        title=place.title or place.name,
        address=place.address,
        phone=place.phone,
        lat=place.lat,
        lng=place.lng,
        distance_km=place.distance_km,
        coordinate_source=place.coordinate_source or "hira",
    )


class NearbyFacilitiesAgent(BaseAgent):
    """사용자 위치 기반 병원·약국 검색 및 지도 marker 생성."""

    def __init__(
        self,
        *,
        hospital_adapter: HiraHospitalAdapter,
        pharmacy_adapter: HiraPharmacyAdapter,
    ) -> None:
        self._hospital = hospital_adapter
        self._pharmacy = pharmacy_adapter

    @property
    def agent_name(self) -> str:
        return "nearby_facilities"

    async def run(self, inp: Any, **kwargs: Any) -> NearbyResponse:
        """Dispatch on input type."""
        if isinstance(inp, NearbySearchInput):
            return await self.search(inp)
        if isinstance(inp, NearbyReportInput):
            return await self.report(inp)
        raise TypeError(
            f"Expected NearbySearchInput or NearbyReportInput, got {type(inp).__name__}"
        )

    async def search(self, inp: NearbySearchInput) -> NearbyResponse:
        """Single-page search."""
        started = time.perf_counter()
        radius_m = int(inp.radius_km * 1000) if inp.radius_km else None

        try:
            if inp.entity_type == "hospital":
                header, items, meta = await self._hospital.search(
                    lat=inp.lat,
                    lng=inp.lng,
                    radius_m=radius_m,
                    name=inp.name,
                    sido_code=inp.sido_code,
                    sggu_code=inp.sggu_code,
                    subject_code=inp.subject_code,
                    hospital_type_code=inp.hospital_type_code,
                    page_no=inp.page_no,
                    num_of_rows=inp.num_of_rows,
                )
            else:  # pharmacy
                header, items, meta = await self._pharmacy.search(
                    lat=inp.lat,
                    lng=inp.lng,
                    radius_m=radius_m,
                    name=inp.name,
                    sido_code=inp.sido_code,
                    sggu_code=inp.sggu_code,
                    page_no=inp.page_no,
                    num_of_rows=inp.num_of_rows,
                )
        except HiraApiError as exc:
            logger.error("HIRA %s search failed: %s", inp.entity_type, exc)
            return self._empty_response(inp.entity_type, inp, reason=f"HIRA {exc.result_code}: {exc.result_msg}")

        return self._build_response(
            entity_type=inp.entity_type,
            header=header,
            items=items,
            meta=meta,
            user_lat=inp.lat,
            user_lng=inp.lng,
            radius_km=inp.radius_km,
            query=inp.model_dump(),
            latency_ms=(time.perf_counter() - started) * 1000,
            truncated=False,
            pages_fetched=1,
        )

    async def report(self, inp: NearbyReportInput) -> NearbyResponse:
        """Multi-page aggregate. Use for larger radius / dashboard views."""
        started = time.perf_counter()
        radius_m = int(inp.radius_km * 1000) if inp.radius_km else None

        try:
            if inp.entity_type == "hospital":
                header, items, meta, truncated = await self._hospital.search_all(
                    max_pages=inp.max_pages,
                    num_of_rows=inp.num_of_rows,
                    lat=inp.lat,
                    lng=inp.lng,
                    radius_m=radius_m,
                )
            else:
                header, items, meta, truncated = await self._pharmacy.search_all(
                    max_pages=inp.max_pages,
                    num_of_rows=inp.num_of_rows,
                    lat=inp.lat,
                    lng=inp.lng,
                    radius_m=radius_m,
                )
        except HiraApiError as exc:
            logger.error("HIRA %s report failed: %s", inp.entity_type, exc)
            return self._empty_response(inp.entity_type, inp, reason=f"HIRA {exc.result_code}: {exc.result_msg}")

        return self._build_response(
            entity_type=inp.entity_type,
            header=header,
            items=items,
            meta=meta,
            user_lat=inp.lat,
            user_lng=inp.lng,
            radius_km=inp.radius_km,
            query=inp.model_dump(),
            latency_ms=(time.perf_counter() - started) * 1000,
            truncated=truncated,
            pages_fetched=(inp.max_pages if truncated else meta.get("pageNo", 1) or 1),
        )

    # ── Response construction ───────────────────────────────────────

    def _build_response(
        self,
        *,
        entity_type: str,
        header: dict,
        items: list[dict],
        meta: dict,
        user_lat: float | None,
        user_lng: float | None,
        radius_km: float | None,
        query: dict,
        latency_ms: float,
        truncated: bool,
        pages_fetched: int,
    ) -> NearbyResponse:
        # 1. Normalize each item
        places: list[Place] = []
        for raw in items:
            place = _normalize_hira_item(
                raw, entity_type=entity_type, user_lat=user_lat, user_lng=user_lng,
            )
            if place is None:
                continue
            # 2. Radius filter (only if user location + radius given)
            if (
                radius_km is not None
                and place.distance_km is not None
                and place.distance_km > radius_km
            ):
                continue
            places.append(place)

        # 3. Sort by distance (nulls last)
        places.sort(key=lambda p: (p.distance_km is None, p.distance_km or 0.0))

        # 4. Markers (only those with coordinates)
        markers: list[Marker] = []
        for p in places:
            m = _build_marker(p)
            if m is not None:
                markers.append(m)

        # 5. Source metadata
        source_meta = SourceMeta(
            result_code=str(header.get("resultCode", "")),
            result_msg=str(header.get("resultMsg", "")),
            format="json",
            page_no=int(meta.get("pageNo") or 1),
            num_of_rows=int(meta.get("numOfRows") or 0),
            total_count=int(meta.get("totalCount") or 0),
            returned_count=len(items),
            normalized_count=len(places),
            pages_fetched=pages_fetched,
            truncated=truncated,
        )

        notice = (
            DEFAULT_NOTICE_HOSPITAL if entity_type == "hospital" else DEFAULT_NOTICE_PHARMACY
        )

        return NearbyResponse(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source="HIRA",
            query=query,
            sources={entity_type: source_meta},
            places=places,
            map=MapPayload(markers=markers),
            notice=notice,
            latency_ms=latency_ms,
            reason_summary=(
                f"HIRA {entity_type} fetched {len(items)} items, "
                f"{len(places)} normalized, {len(markers)} markers"
            ),
        )

    @staticmethod
    def _empty_response(
        entity_type: str,
        inp: NearbySearchInput | NearbyReportInput,
        *,
        reason: str,
    ) -> NearbyResponse:
        source_meta = SourceMeta(
            result_code="",
            result_msg=reason,
            format="json",
            returned_count=0,
            normalized_count=0,
            pages_fetched=0,
            truncated=False,
        )
        return NearbyResponse(
            generated_at=datetime.now(timezone.utc).isoformat(),
            source="HIRA",
            query=inp.model_dump(),
            sources={entity_type: source_meta},
            places=[],
            map=MapPayload(markers=[]),
            notice=DEFAULT_NOTICE_HOSPITAL if entity_type == "hospital" else DEFAULT_NOTICE_PHARMACY,
            reason_summary=reason,
        )
