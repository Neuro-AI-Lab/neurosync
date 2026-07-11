"""페르소나별 정신건강의학과 검색 (dgsbjtCd=03).

Neuro-Sync 임상 시나리오: F1 대화 종료 후 Handoff Report에 근처 정신과 3곳
자동 첨부할 때 이 필터가 핵심.

Run:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_psychiatric_personas
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / "apps" / "ai-server" / ".env")

from src.dependencies import get_nearby_agent  # noqa: E402
from src.schemas.nearby import NearbySearchInput  # noqa: E402

PERSONAS = [
    ("VP-001", "김서연 (28F 초진 경증 · 마포구)", 37.5807, 126.8898),
    ("VP-002", "이준호 (35M 재진 경증 · 판교)", 37.4020, 127.1087),
    ("VP-003", "박민수 (42M 초진 중증 · 관악구)", 37.4782, 126.9515),
    ("VP-004", "최하은 (29F 재진 중증 · 강서구)", 37.5510, 126.8495),
]

RADIUS_KM = 3.0
NUM_OF_ROWS = 10


async def main() -> int:
    agent = get_nearby_agent()

    print("=" * 78)
    print("페르소나별 정신건강의학과 (dgsbjtCd=03) 검색")
    print(f"Radius: {RADIUS_KM}km  |  Top {NUM_OF_ROWS}")
    print("=" * 78)

    all_results = {}
    for vp_id, name, lat, lng in PERSONAS:
        print(f"\n[{vp_id}] {name} @ ({lat}, {lng})")
        inp = NearbySearchInput(
            session_id=f"psych-{vp_id}",
            entity_type="hospital",
            lat=lat,
            lng=lng,
            radius_km=RADIUS_KM,
            subject_code="03",
            num_of_rows=NUM_OF_ROWS,
        )
        resp = await agent.search(inp)
        meta = resp.sources.get("hospital")
        total = meta.total_count if meta else 0
        print(
            f"  🧠 정신과: {len(resp.places)}/{total}개 "
            f"(반경 {RADIUS_KM}km 내 필터 후 {len(resp.places)}개)"
        )
        for pl in resp.places[:5]:
            typ = f" ({pl.type_name})" if pl.type_name else ""
            print(f"    - {pl.distance_km:.2f}km  {pl.name}{typ}")
            if pl.phone:
                print(f"       📞 {pl.phone}")

        all_results[vp_id] = {
            "name": name,
            "lat": lat, "lng": lng,
            "total_in_area": total,
            "returned": len(resp.places),
            "top5": [
                {
                    "name": pl.name,
                    "type": pl.type_name,
                    "distance_km": pl.distance_km,
                    "address": pl.address,
                    "phone": pl.phone,
                }
                for pl in resp.places[:5]
            ],
        }

    # Save
    out_dir = REPO_ROOT / "docs" / "ai" / "simulation_results" / "nearby_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "psychiatric_personas.json"
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== saved to {out} ===")

    # Summary
    print("\n" + "=" * 78)
    print(f"{'VP':<8}{'이름':<30}{'반경 내':<12}{'가장 가까운 곳'}")
    print("-" * 78)
    for vp_id, name, _lat, _lng in PERSONAS:
        r = all_results[vp_id]
        closest = r["top5"][0] if r["top5"] else None
        cl = f"{closest['distance_km']:.2f}km {closest['name']}" if closest else "-"
        print(f"{vp_id:<8}{name[:28]:<30}{r['returned']:>3}/{r['total_in_area']:<8}{cl}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
