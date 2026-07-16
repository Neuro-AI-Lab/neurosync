"""정신과 약물 분류 — HIRA 약효분류번호(meftDivNo) 기반.

이전 버전은 성분명 화이트리스트를 하드코딩했으나(근거 없음), 이제
건강보험심사평가원 「의약품성분약효정보조회서비스」의 약효분류번호를 유일한
판정 기준으로 삼는다. 이 모듈은 순수 매핑 로직만 담고, 조회(API/캐시)는
`hira_efficacy_cache` + `adapters.hira_drug_efficacy` 가 담당한다.

## 정신과 약효분류 (KFDA 약효분류번호)
- 117 정신신경용제 — 항우울제(SSRI/SNRI/TCA)·항불안제(benzodiazepine)·항정신병약
  까지 포괄. (국내 분류상 alprazolam 등 항불안제도 117.)
- 112 최면진정제 — zolpidem 등 수면진정제.

세분류(SSRI vs SNRI vs benzo)는 약효분류번호만으로는 구분되지 않는다(모두 117).
더 세밀한 분류가 필요하면 ATC 코드(N05/N06) 소스가 별도로 필요 —
docs/ai/psychotropic_classification.md §한계 참조.

113 항전간제(라모트리진·발프로에이트 등)는 기분안정제로도 쓰이나 순수 뇌전증과
구분 불가하여 기본 정신과 판정에서 제외한다(오탐 방지).
"""

from __future__ import annotations

from typing import Literal

PsychotropicClass = Literal[
    "PSYCHONEUROTIC",     # 117 정신신경용제
    "SEDATIVE_HYPNOTIC",  # 112 최면진정제
    "NON_PSYCHIATRIC",    # 약효분류가 정신과군이 아님
    "UNKNOWN",            # 약효분류 미조회 — 판정 보류 (정신과로 단정하지 않음)
]

# 약효분류번호 → 정신과 약물군
_EFFICACY_TO_CLASS: dict[int, PsychotropicClass] = {
    117: "PSYCHONEUROTIC",
    112: "SEDATIVE_HYPNOTIC",
}

# 정신과 이력으로 간주하는 약효분류번호 집합
PSYCHIATRIC_EFFICACY_CODES = frozenset(_EFFICACY_TO_CLASS)

# 표시용 한글 라벨 (system prompt/handoff 노출)
PSYCHOTROPIC_LABEL: dict[PsychotropicClass, str] = {
    "PSYCHONEUROTIC": "정신신경용제",
    "SEDATIVE_HYPNOTIC": "최면진정제",
    "NON_PSYCHIATRIC": "비정신과약",
    "UNKNOWN": "약효미확인",
}


def classify_efficacy(meft_div_no: int | None) -> PsychotropicClass:
    """약효분류번호(meftDivNo) → 정신과 약물군.

    - None (미조회): `UNKNOWN` — 정신과로 단정하지 않음.
    - 112/117: 해당 정신과군.
    - 그 외: `NON_PSYCHIATRIC`.
    """
    if meft_div_no is None:
        return "UNKNOWN"
    return _EFFICACY_TO_CLASS.get(meft_div_no, "NON_PSYCHIATRIC")


def is_psychiatric(cls: PsychotropicClass) -> bool:
    """정신과 약물군 여부. `UNKNOWN`/`NON_PSYCHIATRIC`는 False (보수적)."""
    return cls in ("PSYCHONEUROTIC", "SEDATIVE_HYPNOTIC")


def label(cls: PsychotropicClass) -> str:
    """표시용 한글 라벨."""
    return PSYCHOTROPIC_LABEL.get(cls, cls)
