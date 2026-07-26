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

import asyncio
import logging
import math
import time
from datetime import UTC, datetime
from typing import Any

from src.adapters.hira_base import HiraApiError
from src.adapters.hira_hospital import HiraHospitalAdapter
from src.adapters.hira_madm_dtl import HiraMadmDtlAdapter
from src.adapters.hira_pharmacy import HiraPharmacyAdapter
from src.adapters.kakao_local import KakaoLocalAdapter
from src.agents.base import BaseAgent
from src.schemas.nearby import (
    ALLOWED_CL_CODES,
    DEFAULT_NOTICE_HOSPITAL,
    DEFAULT_NOTICE_PHARMACY,
    EXCLUDED_CL_CODES,
    EXCLUDED_TYPE_NAMES,
    PROVIDER_GROUP,
    PSYCHIATRIC_SUBJECT_CODE,
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


_UNIV_HOSPITAL_PATTERNS = ("대학교병원", "대학병원", "의과대학")


def _is_supported_provider(place: Place) -> bool:
    """제품 정책상 정신과 전문 진료 연결 대상인 기관인가.

    clCd 우선, 누락 시 clCdNm으로 방어. 요양병원·한방·치과·보건소 등 제외.
    """
    if place.type_code and place.type_code in EXCLUDED_CL_CODES:
        return False
    if place.type_name and place.type_name in EXCLUDED_TYPE_NAMES:
        return False
    if place.type_code and place.type_code not in ALLOWED_CL_CODES:
        return False
    if place.type_code is None and place.type_name is None:
        # 종별 정보 자체가 없는 이상 케이스 — 방어적으로 스킵.
        return False
    return True


def _classify_group(place: Place) -> str | None:
    """clCd → provider group 매핑."""
    if place.type_code and place.type_code in PROVIDER_GROUP:
        return PROVIDER_GROUP[place.type_code]
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
        kakao_adapter: KakaoLocalAdapter | None = None,
        madm_dtl_adapter: HiraMadmDtlAdapter | None = None,
    ) -> None:
        self._hospital = hospital_adapter
        self._pharmacy = pharmacy_adapter
        # Kakao Local (optional). 있으면 hospital 결과에 대해 정신건강의학과
        # 카테고리 매칭으로 specialist_verified를 채운다. 없으면 fallback 유지.
        self._kakao = kakao_adapter
        # HIRA MadmDtl (optional). Kakao 매칭 실패한 place에 대해 진료과별
        # 전문의 수를 확인해 실제 검증. 승인 미완/실패 시 fallback 유지.
        self._madm_dtl = madm_dtl_adapter
        # ykiho별 dgsbjt→count 응답 캐시 (프로세스 수명 · 단순 dict)
        self._madm_dtl_cache: dict[str, dict[str, int] | None] = {}

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

    _PSYCH_CATEGORY_KEYWORD = "정신건강의학과"

    async def _fetch_psych_verified_set(
        self,
        *,
        lat: float | None,
        lng: float | None,
        radius_km: float | None,
    ) -> set[tuple[float, float]]:
        """Kakao Local `keyword=정신건강의학과`로 반경 내 verified 좌표 세트 구축.

        Returns:
            {(lat_rounded, lng_rounded), ...} — 6자리 반올림 좌표. HIRA place와
            근접 매칭(≤ ~100m)으로 verified 판정에 사용.
        """
        if self._kakao is None or lat is None or lng is None:
            return set()
        radius_m = int((radius_km or 5.0) * 1000)
        radius_m = min(radius_m, 20000)  # Kakao 상한 20km
        try:
            # 최대 45개까지 (page 1-3, size 15). 5km 반경엔 대체로 충분.
            docs: list[dict[str, Any]] = []
            for page in (1, 2, 3):
                body = await self._kakao.search_keyword(
                    query=self._PSYCH_CATEGORY_KEYWORD,
                    lat=lat,
                    lng=lng,
                    radius_m=radius_m,
                    category_group_code="HP8",
                    page=page,
                    size=15,
                    sort="distance",
                )
                docs.extend(body.get("documents") or [])
                if (body.get("meta") or {}).get("is_end"):
                    break
        except Exception as exc:
            logger.warning("kakao psych verify fetch failed: %s", exc)
            return set()

        coords: set[tuple[float, float]] = set()
        for d in docs:
            cat = d.get("category_name") or ""
            if self._PSYCH_CATEGORY_KEYWORD not in cat:
                continue
            try:
                lng2 = float(d["x"])
                lat2 = float(d["y"])
            except (KeyError, TypeError, ValueError):
                continue
            # ~11m 격자(6자리). 매칭 시 이 격자 내 근접 좌표를 verified.
            coords.add((round(lat2, 4), round(lng2, 4)))
        return coords

    @staticmethod
    def _is_near(lat: float, lng: float, verified_set: set[tuple[float, float]]) -> bool:
        """place 좌표가 Kakao verified 격자(~11m at 위도 37°) 근처인지.

        4자리 반올림 격자 기준 3×3 이웃 검사 (~33m 반경). 병원 등록 좌표는
        HIRA↔Kakao 간 소폭 오차(대개 <50m)가 있어 넉넉히 커버.
        """
        base_lat = round(lat, 4)
        base_lng = round(lng, 4)
        for dl in (-1, 0, 1):
            for dg in (-1, 0, 1):
                cell = (round(base_lat + dl * 0.0001, 4), round(base_lng + dg * 0.0001, 4))
                if cell in verified_set:
                    return True
        return False

    async def search(self, inp: NearbySearchInput) -> NearbyResponse:
        """Single-page search."""
        started = time.perf_counter()
        radius_m = int(inp.radius_km * 1000) if inp.radius_km else None

        try:
            if inp.entity_type == "hospital":
                # 정신과 사전문진 제품 제약: 병원 검색은 항상 정신건강의학과로 고정.
                # 호출자가 다른 subject_code를 전달해도 03으로 덮어쓴다.
                if inp.subject_code and inp.subject_code != PSYCHIATRIC_SUBJECT_CODE:
                    logger.info(
                        "nearby.hospital subject_code=%s overridden to %s "
                        "(psychiatric-only product constraint)",
                        inp.subject_code, PSYCHIATRIC_SUBJECT_CODE,
                    )
                header, items, meta = await self._hospital.search(
                    lat=inp.lat,
                    lng=inp.lng,
                    radius_m=radius_m,
                    name=inp.name,
                    sido_code=inp.sido_code,
                    sggu_code=inp.sggu_code,
                    subject_code=PSYCHIATRIC_SUBJECT_CODE,
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
            return self._empty_response(
                inp.entity_type,
                inp,
                reason=f"HIRA {exc.result_code}: {exc.result_msg}",
            )

        # Kakao 카테고리 매칭용 verified 세트 (병원만)
        verified_coords: set[tuple[float, float]] = set()
        if inp.entity_type == "hospital":
            verified_coords = await self._fetch_psych_verified_set(
                lat=inp.lat, lng=inp.lng, radius_km=inp.radius_km,
            )

        resp = self._build_response(
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
            verified_coords=verified_coords,
        )
        # 2차 검증: HIRA MadmDtl 2.8로 실제 전문의 수 확인 (병원만)
        if inp.entity_type == "hospital":
            await self._enrich_via_madm_dtl(resp.places)
            self._resort_places(resp.places)
            self._sync_map_and_meta(resp)
        return resp

    async def report(self, inp: NearbyReportInput) -> NearbyResponse:
        """Multi-page aggregate. Use for larger radius / dashboard views."""
        started = time.perf_counter()
        radius_m = int(inp.radius_km * 1000) if inp.radius_km else None

        try:
            if inp.entity_type == "hospital":
                # 정신과 사전문진 제품 제약: report도 정신건강의학과 고정.
                header, items, meta, truncated = await self._hospital.search_all(
                    max_pages=inp.max_pages,
                    num_of_rows=inp.num_of_rows,
                    lat=inp.lat,
                    lng=inp.lng,
                    radius_m=radius_m,
                    subject_code=PSYCHIATRIC_SUBJECT_CODE,
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
            return self._empty_response(
                inp.entity_type,
                inp,
                reason=f"HIRA {exc.result_code}: {exc.result_msg}",
            )

        verified_coords: set[tuple[float, float]] = set()
        if inp.entity_type == "hospital":
            verified_coords = await self._fetch_psych_verified_set(
                lat=inp.lat, lng=inp.lng, radius_km=inp.radius_km,
            )

        resp = self._build_response(
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
            verified_coords=verified_coords,
            pages_fetched=(inp.max_pages if truncated else meta.get("pageNo", 1) or 1),
        )
        if inp.entity_type == "hospital":
            await self._enrich_via_madm_dtl(resp.places)
            self._resort_places(resp.places)
            self._sync_map_and_meta(resp)
        return resp

    # ── MadmDtl 2차 검증 ─────────────────────────────────────────────

    async def _enrich_via_madm_dtl(self, places: list[Place]) -> list[Place]:
        """HIRA MadmDtl 2.8 API로 진료과별 전문의 수를 조회해 verified 태깅.

        - 어댑터 미구성 or 승인 미완이면 no-op.
        - Kakao로 이미 verified인 place도 실 전문의 수를 채우기 위해 조회.
        - 동시 요청 수 제한(=5) · 응답은 인스턴스 캐시.
        - **명시적 확정 배제**: MadmDtl 응답 성공 & 정신과 전문의 수 == 0인
          병원은 응답에서 제거 (스펙 §4 최종 포함 조건). MadmDtl 실패는
          Kakao 판정 유지(fallback).

        Returns:
            정리된 places 리스트 (제외된 것 삭제). 호출자가 이를 원본에 반영.
        """
        if self._madm_dtl is None:
            return places
        targets = [p for p in places if p.entity_type == "hospital" and p.source_id]
        if not targets:
            return places

        sem = asyncio.Semaphore(5)
        # place.id → drop 여부 (True면 응답에서 제외)
        drop_ids: set[str] = set()

        async def _one(place: Place) -> None:
            ykiho = place.source_id
            if ykiho in self._madm_dtl_cache:
                counts = self._madm_dtl_cache[ykiho]
            else:
                async with sem:
                    counts = await self._madm_dtl.get_dgsbjt_specialist_counts(ykiho)
                self._madm_dtl_cache[ykiho] = counts
            if counts is None:
                return  # 미승인/실패 — Kakao 판정 유지
            # MadmDtl 조회 성공: 실제 전문의 수가 최종 진실. Kakao 카테고리
            # 오분류(예: '김의원'을 정신과로 분류하는 등)를 덮어쓴다.
            psych = counts.get(PSYCHIATRIC_SUBJECT_CODE, 0)
            place.psychiatry_specialist_count = psych
            place.specialist_verified = psych >= 1
            if psych == 0:
                # 스펙 §4 최종 포함 조건: 정신과 전문의 0명은 명시적 배제.
                # (HIRA는 등록 이력 기준으로 dgsbjtCd=03 필터에 포함하지만,
                # MadmDtl은 현행 인력 기준이라 정확도가 더 높음)
                drop_ids.add(place.id)

        await asyncio.gather(*[_one(p) for p in targets])

        if not drop_ids:
            return places
        excluded = [p for p in places if p.id in drop_ids]
        if excluded:
            logger.info(
                "nearby: %d hospital(s) excluded (psychiatry_specialist_count==0): %s",
                len(excluded),
                ", ".join(p.name for p in excluded[:5]),
            )
        # 원본 리스트 in-place 갱신
        places[:] = [p for p in places if p.id not in drop_ids]
        return places

    @staticmethod
    def _sync_map_and_meta(resp: NearbyResponse) -> None:
        """places 변경 후 markers · sources.normalized_count 재동기화."""
        # marker 재구축 (drop된 place 제외)
        new_markers: list[Marker] = []
        for p in resp.places:
            m = _build_marker(p)
            if m is not None:
                new_markers.append(m)
        resp.map = MapPayload(markers=new_markers)
        # sources.normalized_count 동기화 (있는 경우)
        for key, meta in resp.sources.items():
            if key == "hospital":
                meta.normalized_count = len(resp.places)

    @staticmethod
    def _resort_places(places: list[Place]) -> None:
        """스펙 §7 정렬 키 재적용 (in-place)."""
        places.sort(
            key=lambda p: (
                not p.specialist_verified,
                p.distance_km is None,
                p.distance_km or 0.0,
                -(p.psychiatry_specialist_count or 0),
                p.name,
            )
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
        verified_coords: set[tuple[float, float]] | None = None,
    ) -> NearbyResponse:
        verified_coords = verified_coords or set()
        # 1. Normalize each item
        places: list[Place] = []
        excluded_unsupported = 0
        excluded_nursing = 0
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
            # 3. Hospital 전용 필터: 제품 정책상 지원 종별만 유지
            if entity_type == "hospital":
                if not _is_supported_provider(place):
                    if place.type_code == "28" or place.type_name == "요양병원":
                        excluded_nursing += 1
                    else:
                        excluded_unsupported += 1
                    continue
                # HIRA getHospBasisList 응답에는 dgsbjtCd/dgsbjtCdNm 없음.
                # 필터 사실에 근거해 정신건강의학과 태그 부여.
                if place.subject_code is None:
                    place.subject_code = PSYCHIATRIC_SUBJECT_CODE
                    place.subject_name = "정신건강의학과"
                # 그룹 분류
                place.group = _classify_group(place)  # type: ignore[assignment]
                # 대학병원 후보 여부 (확정 아님)
                if any(p in place.name for p in _UNIV_HOSPITAL_PATTERNS):
                    place.is_university_hospital_candidate = True
                # Kakao Local `category=정신건강의학과`로 verified 판정.
                # HIRA↔Kakao 좌표 오차(≤~30m)를 이웃 격자 검사로 흡수.
                if (
                    place.lat is not None
                    and place.lng is not None
                    and verified_coords
                    and self._is_near(place.lat, place.lng, verified_coords)
                ):
                    place.specialist_verified = True
                else:
                    place.specialist_verified = False
            places.append(place)

        # 3. Sort by distance (nulls last)
        # 정렬 (스펙 §7):
        #   1) specialist_verified 우선
        #   2) 거리
        #   3) 전문의 수 (없으면 0)
        #   4) 이름
        # pharmacy는 verified 개념 없으므로 이 정렬키가 자연스럽게 (False,dist,0,name)이 됨.
        places.sort(
            key=lambda p: (
                not p.specialist_verified,
                p.distance_km is None,
                p.distance_km or 0.0,
                -(p.psychiatry_specialist_count or 0),
                p.name,
            )
        )

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
            generated_at=datetime.now(UTC).isoformat(),
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
            generated_at=datetime.now(UTC).isoformat(),
            source="HIRA",
            query=inp.model_dump(),
            sources={entity_type: source_meta},
            places=[],
            map=MapPayload(markers=[]),
            notice=(
                DEFAULT_NOTICE_HOSPITAL if entity_type == "hospital" else DEFAULT_NOTICE_PHARMACY
            ),
            reason_summary=reason,
        )
