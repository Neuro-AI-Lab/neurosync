"""Smoke test — HIRA 병원/약국 API + NearbyFacilitiesAgent.

실 API 호출로 전체 파이프라인 검증:
1. HIRA 어댑터가 실제 응답을 받아오는지
2. envelope 파싱 (header/items/meta)이 정확한지
3. 좌표 XPos/YPos → lng/lat 정규화
4. 거리 계산 & 반경 필터
5. Kakao Marker payload 생성

Run:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_nearby_hira
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / "apps" / "ai-server" / ".env")

from src.dependencies import get_nearby_agent
from src.schemas.nearby import NearbySearchInput

# 테스트 기준 좌표: 서울시청 근처
TEST_LAT = 37.5665
TEST_LNG = 126.9780
TEST_RADIUS_KM = 1.0


async def test_hospitals(agent) -> dict:
    print(f"\n[hospitals] lat={TEST_LAT} lng={TEST_LNG} radius={TEST_RADIUS_KM}km")
    inp = NearbySearchInput(
        session_id="smoke-nearby",
        entity_type="hospital",
        lat=TEST_LAT,
        lng=TEST_LNG,
        radius_km=TEST_RADIUS_KM,
        num_of_rows=20,
    )
    resp = await agent.search(inp)
    meta = resp.sources.get("hospital")
    print(f"  latency: {resp.latency_ms:.0f}ms")
    print(f"  result_code: {meta.result_code if meta else '?'}")
    print(f"  returned/normalized/total: "
          f"{meta.returned_count if meta else 0}"
          f"/{meta.normalized_count if meta else 0}"
          f"/{meta.total_count if meta else 0}")
    print(f"  places (radius filter applied): {len(resp.places)}")
    print(f"  markers (with coords): {len(resp.map.markers)}")
    print()
    print("  top 5 places:")
    for p in resp.places[:5]:
        print(f"    - {p.name} ({p.type_name or '-'}) "
              f"@ ({p.lat},{p.lng}) → {p.distance_km}km")
    return resp.model_dump()


async def test_pharmacies(agent) -> dict:
    print(f"\n[pharmacies] lat={TEST_LAT} lng={TEST_LNG} radius={TEST_RADIUS_KM}km")
    inp = NearbySearchInput(
        session_id="smoke-nearby",
        entity_type="pharmacy",
        lat=TEST_LAT,
        lng=TEST_LNG,
        radius_km=TEST_RADIUS_KM,
        num_of_rows=20,
    )
    resp = await agent.search(inp)
    meta = resp.sources.get("pharmacy")
    print(f"  latency: {resp.latency_ms:.0f}ms")
    print(f"  result_code: {meta.result_code if meta else '?'}")
    print(f"  returned/normalized/total: "
          f"{meta.returned_count if meta else 0}"
          f"/{meta.normalized_count if meta else 0}"
          f"/{meta.total_count if meta else 0}")
    print(f"  places: {len(resp.places)}")
    print(f"  markers: {len(resp.map.markers)}")
    print()
    print("  top 5 places:")
    for p in resp.places[:5]:
        print(f"    - {p.name} @ ({p.lat},{p.lng}) → {p.distance_km}km")
    return resp.model_dump()


async def main() -> int:
    agent = get_nearby_agent()
    print(f"=== HIRA Nearby Facilities Smoke Test ===")
    print(f"Agent: {agent.agent_name}")
    print(f"Hospital: {agent._hospital.base_url}")
    print(f"Pharmacy: {agent._pharmacy.base_url}")

    try:
        hosp = await test_hospitals(agent)
    except Exception as exc:
        print(f"[hospitals] FAILED: {type(exc).__name__}: {exc}")
        hosp = {"error": str(exc)}

    try:
        pharm = await test_pharmacies(agent)
    except Exception as exc:
        print(f"[pharmacies] FAILED: {type(exc).__name__}: {exc}")
        pharm = {"error": str(exc)}

    # Save raw results for inspection
    out_dir = REPO_ROOT / "docs" / "ai" / "simulation_results" / "nearby_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hospitals_smoke.json").write_text(
        json.dumps(hosp, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "pharmacies_smoke.json").write_text(
        json.dumps(pharm, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n=== saved to {out_dir} ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
