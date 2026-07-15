"""HIRA 약효분류 로컬 캐시.

`hira_efficacy_cache.json` (HIRA API 응답 스냅샷)을 읽어 일반명코드(gnlNmCd)로
약효분류 정보를 O(1) 조회한다. 이 캐시는 임의 하드코딩이 아니라 API 응답을 그대로
캐싱한 것으로, `build_efficacy_cache.py` 로 재생성 가능하다.

런타임 흐름 (PatientHistoryAgent):
1. 캐시 hit → 즉시 사용 (네트워크·지연 없음, 오프라인/테스트 동작)
2. 캐시 miss & 어댑터 존재 → HIRA API 조회
3. 둘 다 실패 → UNKNOWN (정신과로 단정하지 않음)
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from src.adapters.hira_drug_efficacy import EfficacyInfo

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).with_name("hira_efficacy_cache.json")


@lru_cache(maxsize=1)
def _load() -> dict[str, EfficacyInfo]:
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("hira_efficacy_cache 로드 실패 (%s) — 빈 캐시로 동작", exc)
        return {}
    out: dict[str, EfficacyInfo] = {}
    for code, v in (raw.get("codes") or {}).items():
        meft = v.get("meftDivNo")
        out[code] = EfficacyInfo(
            gnl_nm_cd=code,
            meft_div_no=int(meft) if meft is not None else None,
            div_nm=str(v.get("divNm") or ""),
            gnl_nm=str(v.get("gnlNm") or ""),
        )
    return out


def lookup(gnl_nm_cd: str | None) -> EfficacyInfo | None:
    """캐시에서 일반명코드 조회. miss 시 None."""
    if not gnl_nm_cd:
        return None
    return _load().get(gnl_nm_cd.strip())
