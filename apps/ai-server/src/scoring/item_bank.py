"""Item bank v0 — questionnaire item construct labels for F3 administration.

`docs/ai/f3_quick_dev_plan.md` §2. Confirmed gap (plan §2.1): verbatim
instrument item text and response anchors (PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C
stems + the standard 0-3 "전혀 아니다 / 며칠 동안 / ..." wording) are absent
repo-wide. This module ships ONLY what actually exists in this repo:
abbreviated Korean construct labels sourced verbatim from persona files
(`docs/ai/personas/VP-001_first_visit_mild.md:81-95`,
`VP-003_first_visit_severe.md:104-118`, `VP-012_first_visit_alcohol.md:101-122`)
— PHQ-9 (9/9 items) and AUDIT-C (3/3 items) only. GAD-7/PHQ-4/WHO-5 ship
`items=()`, `populated=False`, `provenance="unpopulated-v0"` — no fabricated
item text, ever (REV-036 positive finding "no-fabrication boundary verified
airtight for v0").

`response_anchors=None` for every v0 item — no anchor wording exists to
populate it with (plan §2.2); the simulator (`tests/simulation/
survey_answer_llm.py`) is designed around a bare `[min, max]` integer ask
precisely because anchor phrases aren't available.

`response_min`/`response_max` come from `src.scoring.survey_scorer`'s own
already-validated per-item ranges (0-3 for PHQ-9, 0-4 for AUDIT-C) — scoring-
engine range metadata already in the repo, not new clinical text.

Ratified scope (ADR-032 (1)): v0 (construct-labels-only, PHQ-9/AUDIT-C)
proceeds without pausing; GAD-7/PHQ-4/WHO-5 stay `SKIPPED-item-bank-
unpopulated` pending a user decision on a v1 item bank (plan §2.3). Item
bank v1 (validated instrument text) is out of scope for this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.scoring.survey_scorer import SUPPORTED_SCALES, ScaleName

CONSTRUCT_LABELS_V0_PROVENANCE = "construct-labels-v0, persona-file-sourced, non-validated"
UNPOPULATED_V0_PROVENANCE = "unpopulated-v0"

# Matches `survey_scorer.py`'s own per-scale `len(responses) != N` checks —
# not invented here, just mirrored so `populated` can be computed structurally.
_EXPECTED_ITEM_COUNTS: dict[ScaleName, int] = {
    "PHQ-9": 9,
    "GAD-7": 7,
    "PHQ-4": 4,
    "WHO-5": 5,
    "AUDIT-C": 3,
}


@dataclass(frozen=True)
class ScaleItem:
    """One administrable item. `response_anchors` is `None` in v0 (no anchor
    wording exists repo-wide, plan §2.2) — never populated with invented text.
    """

    index: int  # 1-based
    text_ko: str  # construct label (v0) or verbatim item text (future v1)
    response_min: int
    response_max: int
    response_anchors: dict[int, str] | None = None


@dataclass(frozen=True)
class ItemBankEntry:
    scale_name: ScaleName
    version: str
    provenance: str
    items: tuple[ScaleItem, ...]  # empty tuple = unpopulated
    populated: bool


def _phq9_item(index: int, text_ko: str) -> ScaleItem:
    return ScaleItem(index=index, text_ko=text_ko, response_min=0, response_max=3)


def _audit_c_item(index: int, text_ko: str) -> ScaleItem:
    return ScaleItem(index=index, text_ko=text_ko, response_min=0, response_max=4)


# PHQ-9 construct labels — sourced verbatim from VP-001/VP-003/VP-012's own
# "### PHQ-9 예상 항목별 점수" tables (identical label set across all three
# persona files; item 8's fuller "정신운동 지연/초조" wording, from
# VP-001/VP-012, is used over VP-003's abbreviated "정신운동 지연").
_PHQ9_ITEMS_V0: tuple[ScaleItem, ...] = (
    _phq9_item(1, "1. 흥미/즐거움 감소"),
    _phq9_item(2, "2. 우울감"),
    _phq9_item(3, "3. 수면 문제"),
    _phq9_item(4, "4. 피로"),
    _phq9_item(5, "5. 식욕 변화"),
    _phq9_item(6, "6. 자책감"),
    _phq9_item(7, "7. 집중력"),
    _phq9_item(8, "8. 정신운동 지연/초조"),
    _phq9_item(9, "9. 자살/자해 사고"),
)

# AUDIT-C construct labels — sourced verbatim from VP-012's own
# "### AUDIT-C 예상 항목별 점수" table (the only persona with an AUDIT-C table).
_AUDIT_C_ITEMS_V0: tuple[ScaleItem, ...] = (
    _audit_c_item(1, "1. 음주 빈도"),
    _audit_c_item(2, "2. 1회 음주량"),
    _audit_c_item(3, "3. 폭음 빈도 (6잔 이상/1회)"),
)


def _make_entry(
    scale_name: ScaleName, items: tuple[ScaleItem, ...], provenance: str
) -> ItemBankEntry:
    expected = _EXPECTED_ITEM_COUNTS[scale_name]
    populated = (
        len(items) == expected
        and bool(provenance)
        and all(bool(it.text_ko) for it in items)
    )
    return ItemBankEntry(
        scale_name=scale_name, version="v0", provenance=provenance, items=items, populated=populated
    )


ITEM_BANK: dict[ScaleName, ItemBankEntry] = {
    "PHQ-9": _make_entry("PHQ-9", _PHQ9_ITEMS_V0, CONSTRUCT_LABELS_V0_PROVENANCE),
    "AUDIT-C": _make_entry("AUDIT-C", _AUDIT_C_ITEMS_V0, CONSTRUCT_LABELS_V0_PROVENANCE),
    "GAD-7": _make_entry("GAD-7", (), UNPOPULATED_V0_PROVENANCE),
    "PHQ-4": _make_entry("PHQ-4", (), UNPOPULATED_V0_PROVENANCE),
    "WHO-5": _make_entry("WHO-5", (), UNPOPULATED_V0_PROVENANCE),
}


def validate_item_bank_completeness(
    bank: Mapping[ScaleName, ItemBankEntry] | None = None,
) -> None:
    """Fail-fast registry-completeness check (mirrors
    `questionnaire_mapping.py`'s own import-time assertion pattern):
    `bank`'s key set must equal `SUPPORTED_SCALES` exactly. A missing KEY is
    a bug; an unpopulated v0 entry (present, `populated=False`) is not.

    Accepts an optional `bank` override (default: the module's own
    `ITEM_BANK`) so this check is directly unit-testable against a
    deliberately-broken registry without monkeypatching module state.
    """
    target = bank if bank is not None else ITEM_BANK
    missing = SUPPORTED_SCALES - target.keys()
    extra = target.keys() - SUPPORTED_SCALES
    if missing or extra:
        raise AssertionError(
            f"item bank key set does not match SUPPORTED_SCALES — missing={sorted(missing)} "
            f"extra={sorted(extra)}"
        )


# Fail fast at import time, same discipline as questionnaire_mapping.py.
validate_item_bank_completeness()

for _scale_name, _entry in ITEM_BANK.items():
    if _entry.populated:
        assert len(_entry.items) == _EXPECTED_ITEM_COUNTS[_scale_name], (
            f"ITEM_BANK[{_scale_name!r}] marked populated with the wrong item count"
        )
        assert _entry.provenance == CONSTRUCT_LABELS_V0_PROVENANCE, (
            f"ITEM_BANK[{_scale_name!r}] populated but provenance is not the v0 construct-label "
            "string"
        )
    else:
        assert _entry.items == (), f"ITEM_BANK[{_scale_name!r}] unpopulated but items is non-empty"
        assert _entry.provenance == UNPOPULATED_V0_PROVENANCE, (
            f"ITEM_BANK[{_scale_name!r}] unpopulated but provenance is not 'unpopulated-v0'"
        )


def get_item_bank(scale_name: ScaleName) -> ItemBankEntry:
    """Look up the item bank entry for `scale_name`. Raises `KeyError` (loud,
    never a silent `None`) for a scale not in `SUPPORTED_SCALES` — should
    never happen once `validate_item_bank_completeness()` is green.
    """
    entry = ITEM_BANK.get(scale_name)
    if entry is None:
        raise KeyError(
            f"No item bank entry registered for scale {scale_name!r} — "
            f"SUPPORTED_SCALES={sorted(SUPPORTED_SCALES)}"
        )
    return entry
