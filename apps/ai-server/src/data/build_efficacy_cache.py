"""HIRA 약효분류 캐시 재생성 스크립트.

샘플 PHR 파일(또는 --code 로 지정한 코드)의 일반명코드(gnlNmCd)를 수집해
HIRA 의약품성분약효정보조회서비스로 조회하고 `hira_efficacy_cache.json` 을
갱신한다. 네트워크 + 유효한 HIRA_SERVICE_KEY 필요.

사용:
    cd apps/ai-server
    python -m src.data.build_efficacy_cache                    # 샘플에서 코드 수집
    python -m src.data.build_efficacy_cache --code 474802ATB   # 특정 코드 추가

각 엔트리는 API 응답을 그대로 저장한다 (임의 값 없음).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from src.adapters.hira_drug_efficacy import HiraDrugEfficacyAdapter
from src.config import Settings

_CACHE_PATH = Path(__file__).with_name("hira_efficacy_cache.json")
_SAMPLES_DIR = Path(__file__).resolve().parents[4] / "docs/ai/samples/phr"


def _collect_sample_codes() -> set[str]:
    """샘플 PHR medications.json 에서 Substance 일반명코드를 수집."""
    codes: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            if o.get("resourceType") == "Substance":
                for c in ((o.get("code") or {}).get("coding") or []):
                    system = str(c.get("system", ""))
                    code = c.get("code")
                    if "hira.or.kr" in system and code:
                        codes.add(str(code))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in sorted(_SAMPLES_DIR.glob("*_medications.json")):
        walk(json.loads(f.read_text(encoding="utf-8")))
    return codes


async def _build(codes: set[str]) -> dict[str, Any]:
    adapter = HiraDrugEfficacyAdapter(Settings())
    entries: dict[str, Any] = {}
    for code in sorted(codes):
        info = await adapter.get_efficacy(code)
        if info is None:
            print(f"  ! {code}: 미조회 (키/승인/네트워크 확인) — 건너뜀")
            continue
        entries[code] = {
            "meftDivNo": info.meft_div_no,
            "divNm": info.div_nm,
            "gnlNm": info.gnl_nm,
        }
        print(f"  ✓ {code} → {info.meft_div_no} {info.div_nm}")
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description="HIRA 약효분류 캐시 재생성")
    ap.add_argument("--code", action="append", default=[],
                    help="추가 조회할 일반명코드 (여러 번 가능)")
    ap.add_argument("--no-samples", action="store_true",
                    help="샘플 코드 수집 생략 (--code 만 사용)")
    args = ap.parse_args()

    codes: set[str] = set(args.code)
    if not args.no_samples:
        codes |= _collect_sample_codes()
    if not codes:
        print("조회할 코드가 없습니다.")
        return 1

    print(f"HIRA 약효분류 조회 대상 {len(codes)}건...")
    entries = asyncio.run(_build(codes))
    if not entries:
        print("조회 성공 0건 — 캐시를 갱신하지 않습니다.")
        return 1

    payload = {
        "_meta": {
            "source": "HIRA 의약품성분약효정보조회서비스 (getMajorCmpnNmCdList)",
            "endpoint": (
                "https://apis.data.go.kr/B551182/msupCmpnMeftInfoService/"
                "getMajorCmpnNmCdList"
            ),
            "key": "gnlNmCd (일반명코드)",
            "generated": _dt.date.today().isoformat(),
            "note": "API 응답 스냅샷. 각 엔트리는 HIRA API로 검증됨.",
            "regen_command": "python -m src.data.build_efficacy_cache",
        },
        "codes": entries,
    }
    _CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"완료: {len(entries)}건 → {_CACHE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
