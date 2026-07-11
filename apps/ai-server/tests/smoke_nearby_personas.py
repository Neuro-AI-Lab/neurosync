"""Smoke test — 4명 페르소나별 위치 기반 HIRA 근처 병원·약국 검색.

Flow (spec §11 활용 시나리오 그대로):
1. 페르소나 주소 → Kakao Local REST로 좌표 획득
2. 그 좌표로 HIRA 병원 + 약국 검색 (radius=2km, num_of_rows=10)
3. 결과 표 + JSON 저장

Run:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_nearby_personas
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / "apps" / "ai-server" / ".env")

from src.dependencies import get_kakao_local_adapter, get_nearby_agent  # noqa: E402
from src.schemas.nearby import NearbySearchInput  # noqa: E402

# 페르소나별 임의 위치 (OCR 진단서 · persona MD 기준)
PERSONAS = [
    {
        "vp_id": "VP-001",
        "name": "김서연",
        "profile": "28F · 초진 경증 · 불안+불면",
        "address": "서울특별시 마포구 월드컵북로 400",  # 마포구청 근처
        "fallback_lat": 37.5663,
        "fallback_lng": 126.9018,
    },
    {
        "vp_id": "VP-002",
        "name": "이준호",
        "profile": "35M · 재진 경증 · 치료 중",
        "address": "경기도 성남시 분당구 판교역로 235",  # 판교역 근처
        "fallback_lat": 37.3947,
        "fallback_lng": 127.1112,
    },
    {
        "vp_id": "VP-003",
        "name": "박민수",
        "profile": "42M · 초진 중증 · 자살 사고",
        "address": "서울특별시 관악구 관악로 145",  # 관악구청 근처
        "fallback_lat": 37.4784,
        "fallback_lng": 126.9516,
    },
    {
        "vp_id": "VP-004",
        "name": "최하은",
        "profile": "29F · 재진 중증 · 공황+자살",
        "address": "서울특별시 강서구 화곡로 302",  # 강서구청 근처
        "fallback_lat": 37.5510,
        "fallback_lng": 126.8495,
    },
]

RADIUS_KM = 2.0
NUM_OF_ROWS = 10


async def geocode_or_fallback(kakao, persona: dict) -> tuple[float, float, str]:
    """Try Kakao geocoding; fall back to hardcoded coords if fails."""
    if kakao is None:
        return persona["fallback_lat"], persona["fallback_lng"], "fallback"
    result = await kakao.geocode(persona["address"])
    if result is None:
        return persona["fallback_lat"], persona["fallback_lng"], "fallback"
    lat, lng = result
    return lat, lng, "kakao_geocoded"


async def search_for_persona(nearby, persona: dict, lat: float, lng: float) -> dict:
    """Search both hospitals and pharmacies for one persona."""
    session_id = f"nearby-{persona['vp_id']}"

    # Hospitals
    hosp_inp = NearbySearchInput(
        session_id=session_id,
        entity_type="hospital",
        lat=lat,
        lng=lng,
        radius_km=RADIUS_KM,
        num_of_rows=NUM_OF_ROWS,
    )
    hosp_resp = await nearby.search(hosp_inp)

    # Pharmacies
    pharm_inp = NearbySearchInput(
        session_id=session_id,
        entity_type="pharmacy",
        lat=lat,
        lng=lng,
        radius_km=RADIUS_KM,
        num_of_rows=NUM_OF_ROWS,
    )
    pharm_resp = await nearby.search(pharm_inp)

    return {
        "hospitals": hosp_resp.model_dump(),
        "pharmacies": pharm_resp.model_dump(),
    }


async def main() -> int:
    kakao = get_kakao_local_adapter()
    nearby = get_nearby_agent()

    print("=" * 78)
    print("4 페르소나별 위치 기반 HIRA 근처 병원·약국 검색")
    print(f"Radius: {RADIUS_KM}km  |  Num per query: {NUM_OF_ROWS}")
    print("=" * 78)

    all_results = []
    for p in PERSONAS:
        print(f"\n[{p['vp_id']}] {p['name']} ({p['profile']})")
        print(f"  주소: {p['address']}")

        lat, lng, coord_source = await geocode_or_fallback(kakao, p)
        print(f"  좌표: ({lat:.6f}, {lng:.6f}) — {coord_source}")

        try:
            result = await search_for_persona(nearby, p, lat, lng)
        except Exception as exc:
            print(f"  ✗ Error: {type(exc).__name__}: {exc}")
            all_results.append({
                "vp_id": p["vp_id"],
                "name": p["name"],
                "address": p["address"],
                "lat": lat, "lng": lng,
                "coord_source": coord_source,
                "error": str(exc),
            })
            continue

        h_places = result["hospitals"]["places"]
        p_places = result["pharmacies"]["places"]
        h_meta = result["hospitals"]["sources"].get("hospital", {})
        p_meta = result["pharmacies"]["sources"].get("pharmacy", {})

        print(f"  🏥 병원: {len(h_places)}/{h_meta.get('total_count', '?')} "
              f"(latency {result['hospitals'].get('latency_ms', 0):.0f}ms)")
        for hp in h_places[:5]:
            print(f"     - {hp['name']} ({hp.get('type_name') or '-'}) "
                  f"@ {hp.get('distance_km', 0):.2f}km")

        print(f"  💊 약국: {len(p_places)}/{p_meta.get('total_count', '?')} "
              f"(latency {result['pharmacies'].get('latency_ms', 0):.0f}ms)")
        for ph in p_places[:5]:
            print(f"     - {ph['name']} @ {ph.get('distance_km', 0):.2f}km")

        all_results.append({
            "vp_id": p["vp_id"],
            "name": p["name"],
            "profile": p["profile"],
            "address": p["address"],
            "lat": lat, "lng": lng,
            "coord_source": coord_source,
            "hospital_count": len(h_places),
            "pharmacy_count": len(p_places),
            "hospital_total": h_meta.get("total_count", 0),
            "pharmacy_total": p_meta.get("total_count", 0),
            "top_hospitals": [
                {"name": p["name"], "type": p.get("type_name"), "distance_km": p.get("distance_km")}
                for p in h_places[:5]
            ],
            "top_pharmacies": [
                {"name": p["name"], "distance_km": p.get("distance_km")}
                for p in p_places[:5]
            ],
            "raw": result,
        })

    # Save
    out_dir = REPO_ROOT / "docs" / "ai" / "simulation_results" / "nearby_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "personas_nearby.json"
    out.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n=== saved to {out} ===")

    # Summary table
    print("\n" + "=" * 78)
    print("Summary")
    print("=" * 78)
    print(f"{'VP':<8}{'Name':<10}{'Coord source':<16}{'Hosp (2km)':<14}{'Pharm (2km)':<14}")
    print("-" * 78)
    for r in all_results:
        if "error" in r:
            print(f"{r['vp_id']:<8}{r['name']:<10}FAIL")
            continue
        print(
            f"{r['vp_id']:<8}"
            f"{r['name']:<10}"
            f"{r['coord_source']:<16}"
            f"{r['hospital_count']:>3}/{r['hospital_total']:<10}"
            f"{r['pharmacy_count']:>3}/{r['pharmacy_total']:<10}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
