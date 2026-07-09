"""Smoke test — Kakao Local REST API (address geocoding).

- 실제 API 호출로 주소 → 좌표 변환 검증
- HIRA에서 반환한 병원 주소 몇 개를 재-geocoding하여 일치 여부 대조
- Backend 전용 키 사용 (client에 노출 금지)

Run:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_kakao_local
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

# 3개 검증 케이스: 알려진 주소 + HIRA에서 받은 병원 주소 재검증
TEST_ADDRESSES = [
    "서울특별시청",
    "서울특별시 종로구 세종대로 172",
    "경기도 성남시 분당구 판교역로 235",
]


async def test_direct_geocoding(adapter) -> list[dict]:
    """Case 1: 알려진 주소 3개 geocoding."""
    print("\n[Case 1] Direct geocoding — known addresses")
    results = []
    for addr in TEST_ADDRESSES:
        try:
            body = await adapter.search_address(addr, size=1)
            docs = body.get("documents") or []
            doc = docs[0] if docs else {}
            entry = {
                "query": addr,
                "found": bool(docs),
                "address_name": doc.get("address_name"),
                "x_lng": doc.get("x"),
                "y_lat": doc.get("y"),
                "total_count": body.get("meta", {}).get("total_count", 0),
            }
            results.append(entry)
            print(f"  ✓ {addr}")
            print(f"    → {doc.get('address_name')}")
            print(f"    → lat={doc.get('y')}, lng={doc.get('x')}")
        except Exception as exc:
            print(f"  ✗ {addr}: {type(exc).__name__}: {exc}")
            results.append({"query": addr, "error": str(exc)})
    return results


async def test_hira_cross_verification(nearby_agent, kakao_adapter) -> list[dict]:
    """Case 2: HIRA 병원 3곳 주소를 Kakao로 재geocoding → 좌표 대조."""
    print("\n[Case 2] HIRA → Kakao cross-verification (좌표 대조)")

    # 서울시청 근처 병원 3개 가져오기
    inp = NearbySearchInput(
        session_id="smoke-kakao",
        entity_type="hospital",
        lat=37.5665,
        lng=126.9780,
        radius_km=1.0,
        num_of_rows=3,
    )
    resp = await nearby_agent.search(inp)

    results = []
    for place in resp.places[:3]:
        if not place.address:
            print(f"  - {place.name}: no address, skipping")
            continue
        kakao_result = await kakao_adapter.geocode(place.address)
        if kakao_result is None:
            print(f"  ✗ {place.name}: Kakao geocoding returned nothing")
            results.append(
                {
                    "place": place.name,
                    "hira_lat": place.lat,
                    "hira_lng": place.lng,
                    "kakao": None,
                }
            )
            continue
        k_lat, k_lng = kakao_result
        # 두 좌표 간 거리 (rough — 100m 정도면 정상)
        import math
        R = 6371.0088
        dlat = math.radians(k_lat - place.lat)
        dlng = math.radians(k_lng - place.lng)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(place.lat)) * math.cos(math.radians(k_lat))
            * math.sin(dlng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist_km = R * c
        print(f"  ✓ {place.name}")
        print(f"    HIRA:  ({place.lat:.6f}, {place.lng:.6f})")
        print(f"    Kakao: ({k_lat:.6f}, {k_lng:.6f})")
        print(f"    Δ:     {dist_km * 1000:.1f}m  ({'일치' if dist_km < 0.3 else '불일치'})")
        results.append({
            "place": place.name,
            "address": place.address,
            "hira_lat": place.lat, "hira_lng": place.lng,
            "kakao_lat": k_lat, "kakao_lng": k_lng,
            "delta_m": round(dist_km * 1000, 1),
        })
    return results


async def main() -> int:
    kakao = get_kakao_local_adapter()
    if kakao is None:
        print("[ERR] Kakao adapter not registered (KAKAO_REST_API_KEY missing)", file=sys.stderr)
        return 1

    print("=== Kakao Local REST API Smoke Test ===")
    print(f"Base URL: {kakao._base_url}")
    print(f"API key:  ***{kakao._api_key[-4:]}")

    # Case 1: known addresses
    try:
        case1 = await test_direct_geocoding(kakao)
    except Exception as exc:
        print(f"[Case 1] FAILED: {exc}")
        case1 = [{"error": str(exc)}]

    # Case 2: cross-verify HIRA
    nearby = get_nearby_agent()
    try:
        case2 = await test_hira_cross_verification(nearby, kakao)
    except Exception as exc:
        print(f"[Case 2] FAILED: {exc}")
        case2 = [{"error": str(exc)}]

    # Save
    out_dir = REPO_ROOT / "docs" / "ai" / "simulation_results" / "nearby_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "kakao_local_smoke.json"
    out.write_text(
        json.dumps({"direct": case1, "cross_verification": case2}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n=== saved to {out} ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
