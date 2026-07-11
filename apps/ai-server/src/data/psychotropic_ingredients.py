"""정신과 약물 성분 카탈로그.

PHR MedicationDispense의 성분명(영문 lowercase)을 정신과 약물군으로 분류한다.
분류 결과는 `PhrSummary.psychotropic_medications` 필터와 `has_psychiatric_history`
판정에 사용된다.

## 관리 원칙
- 성분명 소문자/공백 정규화 후 조회 (`classify()`)
- 카탈로그 확장은 임상팀 리뷰가 필요한 값 변경 — 근거는
  `docs/ai/references/psychotropic_ingredients.md`에 첨부 예정 (v1은 하드코딩).
- ATC 코드(N05/N06) 매핑은 국내 PHR에 ATC 필드가 없어 도입 미정.
"""

from __future__ import annotations

from typing import Literal

PsychotropicClass = Literal[
    "SSRI",              # 선택적 세로토닌 재흡수 억제제
    "SNRI",              # 세로토닌·노르에피네프린 재흡수 억제제
    "TCA",               # 삼환계 항우울제
    "BENZO",             # 벤조디아제핀 (항불안·수면)
    "ZDRUG",             # Z-drug 계열 수면제
    "ANTIPSYCHOTIC",     # 항정신병약
    "MOOD_STABILIZER",   # 기분안정제
    "OTHER_NEURO",       # 기타 중추신경계 약물 (미르타자핀·트라조돈 등)
    "NON_PSYCHIATRIC",   # 정신과 약이 아님
]

# 국제 통용 성분명 (INN) 기준. 소문자 · 공백 없이 관리.
_CATALOG: dict[str, PsychotropicClass] = {
    # SSRI
    "escitalopram": "SSRI",
    "sertraline": "SSRI",
    "fluoxetine": "SSRI",
    "paroxetine": "SSRI",
    "citalopram": "SSRI",
    "fluvoxamine": "SSRI",
    # SNRI
    "venlafaxine": "SNRI",
    "duloxetine": "SNRI",
    "desvenlafaxine": "SNRI",
    "milnacipran": "SNRI",
    # 삼환계
    "amitriptyline": "TCA",
    "nortriptyline": "TCA",
    "imipramine": "TCA",
    "clomipramine": "TCA",
    # 벤조디아제핀
    "alprazolam": "BENZO",
    "lorazepam": "BENZO",
    "diazepam": "BENZO",
    "clonazepam": "BENZO",
    "bromazepam": "BENZO",
    "etizolam": "BENZO",
    # Z-drug
    "zolpidem": "ZDRUG",
    "zopiclone": "ZDRUG",
    "eszopiclone": "ZDRUG",
    "zaleplon": "ZDRUG",
    # 항정신병약 (비정형 위주)
    "quetiapine": "ANTIPSYCHOTIC",
    "olanzapine": "ANTIPSYCHOTIC",
    "risperidone": "ANTIPSYCHOTIC",
    "aripiprazole": "ANTIPSYCHOTIC",
    "paliperidone": "ANTIPSYCHOTIC",
    "clozapine": "ANTIPSYCHOTIC",
    # 기분안정제
    "lithium": "MOOD_STABILIZER",
    "lamotrigine": "MOOD_STABILIZER",
    "valproate": "MOOD_STABILIZER",
    "valproic acid": "MOOD_STABILIZER",
    "carbamazepine": "MOOD_STABILIZER",
    # 기타 중추신경계
    "mirtazapine": "OTHER_NEURO",
    "trazodone": "OTHER_NEURO",
    "buspirone": "OTHER_NEURO",
    "bupropion": "OTHER_NEURO",
    "tianeptine": "OTHER_NEURO",
    "vortioxetine": "OTHER_NEURO",
}


def _normalize(name: str | None) -> str:
    if not name:
        return ""
    return name.strip().lower().replace(" ", "").replace("-", "")


# 정규화된 키로 재구성 (조회 성능)
_INDEX: dict[str, PsychotropicClass] = {_normalize(k): v for k, v in _CATALOG.items()}


def classify(ingredient_name: str | None) -> PsychotropicClass:
    """성분명 → 정신과 약물군. 매칭 실패 시 `NON_PSYCHIATRIC`."""
    key = _normalize(ingredient_name)
    if not key:
        return "NON_PSYCHIATRIC"
    if key in _INDEX:
        return _INDEX[key]
    # 부분 일치 (예: 'escitalopramoxalate' → 'escitalopram')
    for known, cls in _INDEX.items():
        if known in key:
            return cls
    return "NON_PSYCHIATRIC"


def is_psychotropic(ingredient_name: str | None) -> bool:
    """Convenience — classify != NON_PSYCHIATRIC."""
    return classify(ingredient_name) != "NON_PSYCHIATRIC"
