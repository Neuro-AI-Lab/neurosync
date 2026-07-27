"""근처 정신건강의학과 검색 — 플랫폼(apps/api) 직접 조회 (ADR-041).

ADR-041: `/ai/nearby/*` ai-server 라우트는 삭제되고, 병원/약국 검색은 앱/플랫폼
측 사용자-개시 기능으로 이전되었다. 이 모듈은 그 결정에 맞춰 apps/api가 **Kakao
Local 키워드 검색**을 직접 호출해 근처 '정신건강의학과' 좌표를 얻는다 (ai-server
미경유).

Kakao Local keyword.json:
  GET https://dapi.kakao.com/v2/local/search/keyword.json
  ?query=정신건강의학과&x=<lng>&y=<lat>&radius=<m>&sort=distance
  Authorization: KakaoAK <REST_KEY>

우아한 저하: 키 없음/네트워크 실패 시 빈 리스트를 반환한다 (지도는 내 위치만
표시). 위기 상황에 로그인 없이도 지도가 떠야 하므로 절대 예외를 위로 던지지 않는다.
"""

from __future__ import annotations

import logging

import httpx

from src.core.config import Settings

logger = logging.getLogger(__name__)

# 정신과 사전문진 제품 제약 — 병원 검색은 항상 정신건강의학과로 고정.
_PSYCH_KEYWORD = "정신건강의학과"
# Kakao Local radius 상한은 20,000m.
_MAX_RADIUS_M = 20_000


async def find_psychiatry_hospitals(
    *, lat: float, lng: float, radius_km: float, settings: Settings
) -> list[dict]:
    """근처 정신건강의학과 목록. 지도 마커용 dict 리스트를 반환한다.

    각 항목: name, lat, lng, address, phone, distance_km, type_name.
    실패/키 없음이면 빈 리스트 (호출부가 빈 지도로 저하)."""
    key = settings.kakao_rest_api_key
    if not key:
        logger.warning("hospital_finder skipped — KAKAO_REST_API_KEY not set")
        return []

    radius_m = max(1, min(int(radius_km * 1000), _MAX_RADIUS_M))
    url = f"{settings.kakao_local_base_url.rstrip('/')}/v2/local/search/keyword.json"
    params = {
        "query": _PSYCH_KEYWORD,
        "x": f"{lng:.6f}",  # Kakao: x=경도(lng), y=위도(lat)
        "y": f"{lat:.6f}",
        "radius": radius_m,
        "sort": "distance",
        "size": 15,  # Kakao 페이지 상한
    }
    headers = {"Authorization": f"KakaoAK {key}"}

    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_nearby_timeout_seconds
        ) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("hospital_finder Kakao Local failed: %s", exc)
        return []

    places: list[dict] = []
    for d in docs:
        try:
            plng = float(d["x"])
            plat = float(d["y"])
        except (KeyError, TypeError, ValueError):
            continue
        dist_m = d.get("distance")
        places.append(
            {
                "name": d.get("place_name") or "정신건강의학과",
                "lat": plat,
                "lng": plng,
                "address": d.get("road_address_name") or d.get("address_name") or "",
                "phone": d.get("phone") or "",
                "distance_km": (int(dist_m) / 1000) if dist_m else None,
                "type_name": "정신건강의학과",
            }
        )
    logger.info("hospital_finder: %d psychiatry places near (%.4f,%.4f)", len(places), lat, lng)
    return places
