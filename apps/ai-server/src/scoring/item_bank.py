"""Item bank v1 — sourced Korean instrument content for F3 administration.

`PLAN-2026-W29-A` step 3, `docs/ai/item_bank_v1_sources.md` (brainstorm's
sourcing note, `CVR-016` content-fidelity gate, `ADR-033` dispositions).

v1 replaces v0's abbreviated construct labels with verbatim official item
text, response anchors, and instruction/timeframe wording for PHQ-9, GAD-7,
PHQ-4, and AUDIT-C. WHO-5 stays unpopulated (0/5 items sourced after an
exhaustive documented retry — `item_bank_v1_sources.md` §4.6 — fabrication-0
means an unreachable instrument ships empty, never invented).

Fidelity discipline (CVR-016 condition 1, binding): every `text_ko` and
`response_anchors` string below is transcribed from
`item_bank_v1_sources.md`'s **appendix** (§A1 Pfizer PHQ-9, §A2 Pfizer
GAD-7, §A5 SBIRT Oregon AUDIT-C) — the LITERAL quoted extraction — never
from the note's prose-table renderings (§1.3/§2.3/§5.3), which the note's
own CVR-016 review flagged as a possible whitespace-variant risk. Every
Korean string in this module traces to that note; nothing here is
paraphrased, back-translated, or reconstructed from memory.

Translation-version picks (`ADR-033` decision 1): PHQ-9 primary = Pfizer/
phqscreeners.com Korean translation (the instance Seo & Park 2015's Korean
validation study actually administered) — the government 별지14호 form is
documented in the note as an alternate only and is NOT shipped here.
GAD-7/AUDIT-C both use their respective note-primary sources (Pfizer,
SBIRT Oregon).

PHQ-4 (`ADR-033`, note §3): no standalone Korean PHQ-4 document exists;
Kim et al. 2021 documents that the Korean PHQ-4 IS the first two items of
the Korean GAD-7 + the first two items of the Korean PHQ-9 — every PHQ-4
word below is therefore copy-identical to an already-sourced GAD-7/PHQ-9
row (traced individually via `ScaleItem.source`), not independently
translated.

AUDIT-C is **v2** as of `PLAN-2026-W29-B` / `CVR-018` / `ADR-034` (decisions
1-2, binding conditions 1-4) — the earlier v1 SBIRT Oregon Korean AUDIT text
(`CVR-016` conditions 2-3 / `ADR-033` decisions 2-3) is SUPERSEDED, not
shipped in this item bank; it remains documented as an alternate in
`item_bank_v1_sources.md` §5. v2 ships the sourced-verbatim [별지
제15호의3서식] 음주 생활습관 평가 도구 (Korea's official 보건복지부고시
health-screening alcohol-lifestyle assessment form), items 1-3 — every
`text_ko`/`response_anchors` string below is transcribed from
`docs/ai/audit_c_korean_research.md` §3.2's own table row (copied, never
retyped); THAT file, not `item_bank_v1_sources.md`, is the canonical
byte-fidelity source for AUDIT-C specifically (`CVR-018` binding condition
8). `AUDIT_C_V2_PROVENANCE` carries the two-mirror cross-verification, the
mirror-1 item-1 five-anchor pick + mirror-2 discrepancy disclosure
(`CVR-018` Q2(a)), and the standing translation-identity caveat (`CVR-018`
Finding 6). `AUDIT_C_THRESHOLD_CAVEAT` is a separate, English-language,
machine-readable caveat for the Korean-primary male>=6/female>=5 threshold
(Lee JH et al. 2018 KNHANES, `CVR-018` Q1 / `ADR-034` decision 1) — English,
not a Korean instrument string, so it is outside this module's Korean-
fabrication-0 scope by construction. The threshold VALUES themselves live in
`survey_scorer.py::_score_audit_c`, not this module; the international
cutoff (Bush et al. 1998, male/unknown>=4, female>=3) is retained as
non-action-driving metadata on the F3 artifact by `src/f3.py`, also outside
this module.

GAD-7 (`CVR-016` binding condition 1 / `CVR-017` binding condition 1 /
`REV-039` correction D): `GAD7_BAND_CAVEAT` is the same-pattern,
English-language, machine-readable caveat for GAD-7's severity bands
(0-4/5-9/10-14/15-21, unchanged, byte-frozen) — the appendix-completion
pass retracted the Korean-language clinician scoring-table citation that
previously supported these bands (`item_bank_v1_sources.md` §2.4); the
bands now rest on international-convention-only sourcing (Spitzer et al.
2006), not independently confirmed against any Korean-language source.
Structurally identical treatment to `AUDIT_C_THRESHOLD_CAVEAT` — a
disclosure-symmetry fix, not a value change.

v0 content (`ITEM_BANK_V0`, `_PHQ9_ITEMS_V0`/`_AUDIT_C_ITEMS_V0`,
`CONSTRUCT_LABELS_V0_PROVENANCE`/`UNPOPULATED_V0_PROVENANCE`) is retained
UNCHANGED and stays independently addressable via `get_item_bank_v0` — EXP-
019's artifacts (item_bank_version="v0") must stay interpretable against
the content that actually produced them. `ITEM_BANK` (this module's primary
export, consumed by `src/f3.py`) is v1 as of this mission.
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
    """One administrable item.

    `response_anchors`: `{response_value: anchor_text_ko}` — populated for
    every v1 item (`None` only for a hand-built test fixture or a future
    unpopulated scale with no anchor wording to report).

    `source`: free-text citation into `item_bank_v1_sources.md` (section +
    appendix ref) this exact item's text/anchors trace to. Entry-level
    `ItemBankEntry.provenance` already covers the common case (one scale,
    one source); `source` matters most for PHQ-4, whose 4 items trace to
    TWO different parent-instrument appendix blocks.

    `primary_track_label`/`secondary_track_label`/`secondary_response_anchors`/
    `secondary_track_conversion_note_ko`: AUDIT-C v2 item 2 only (`CVR-018`
    Q2(c) / `ADR-034` decision 2, `BUG-039` fix). The sourced [별지
    제15호의3서식] form bifurcates item 2 into a native 소주-bottle track
    (`response_anchors`, the primary/administered-by-default track,
    labeled "소주 트랙" verbatim in `docs/ai/audit_c_korean_research.md`
    §3.2's own table row) and a glasses-based "기타 술" track with its own
    explicit beer/makgeolli/draft-beer unit-conversion table — adopted
    specifically because it structurally eliminates the Western/soju
    unit-conversion confound `CVR-017` Finding 4 live-confirmed under v1's
    Western-unit-only item 2. `primary_track_label` is populated ONLY when
    `secondary_response_anchors` is also populated (i.e. only for a
    dual-tracked item) — a single-tracked item's `response_anchors` needs
    no distinguishing label. `None` for every item that is not dual-tracked
    (every item except AUDIT-C v2 item 2).
    """

    index: int  # 1-based
    text_ko: str  # construct label (v0) or verbatim item text (v1/v2)
    response_min: int
    response_max: int
    response_anchors: dict[int, str] | None = None
    source: str = ""
    primary_track_label: str | None = None
    secondary_track_label: str | None = None
    secondary_response_anchors: dict[int, str] | None = None
    secondary_track_conversion_note_ko: str | None = None


@dataclass(frozen=True)
class ItemBankEntry:
    scale_name: ScaleName
    version: str
    provenance: str
    items: tuple[ScaleItem, ...]  # empty tuple = unpopulated
    populated: bool
    instruction_ko: str | None = None  # timeframe/instruction wording, entry-level (not per-item)


def _make_entry(
    scale_name: ScaleName,
    items: tuple[ScaleItem, ...],
    provenance: str,
    version: str,
    instruction_ko: str | None = None,
) -> ItemBankEntry:
    expected = _EXPECTED_ITEM_COUNTS[scale_name]
    populated = (
        len(items) == expected
        and bool(provenance)
        and all(bool(it.text_ko) for it in items)
    )
    return ItemBankEntry(
        scale_name=scale_name,
        version=version,
        provenance=provenance,
        items=items,
        populated=populated,
        instruction_ko=instruction_ko,
    )


# ── v0 content — UNCHANGED, retained for EXP-019 artifact interpretability ─


def _phq9_item_v0(index: int, text_ko: str) -> ScaleItem:
    return ScaleItem(index=index, text_ko=text_ko, response_min=0, response_max=3)


def _audit_c_item_v0(index: int, text_ko: str) -> ScaleItem:
    return ScaleItem(index=index, text_ko=text_ko, response_min=0, response_max=4)


# PHQ-9 construct labels — sourced verbatim from VP-001/VP-003/VP-012's own
# "### PHQ-9 예상 항목별 점수" tables (identical label set across all three
# persona files; item 8's fuller "정신운동 지연/초조" wording, from
# VP-001/VP-012, is used over VP-003's abbreviated "정신운동 지연").
_PHQ9_ITEMS_V0: tuple[ScaleItem, ...] = (
    _phq9_item_v0(1, "1. 흥미/즐거움 감소"),
    _phq9_item_v0(2, "2. 우울감"),
    _phq9_item_v0(3, "3. 수면 문제"),
    _phq9_item_v0(4, "4. 피로"),
    _phq9_item_v0(5, "5. 식욕 변화"),
    _phq9_item_v0(6, "6. 자책감"),
    _phq9_item_v0(7, "7. 집중력"),
    _phq9_item_v0(8, "8. 정신운동 지연/초조"),
    _phq9_item_v0(9, "9. 자살/자해 사고"),
)

# AUDIT-C construct labels — sourced verbatim from VP-012's own
# "### AUDIT-C 예상 항목별 점수" table (the only persona with an AUDIT-C table).
_AUDIT_C_ITEMS_V0: tuple[ScaleItem, ...] = (
    _audit_c_item_v0(1, "1. 음주 빈도"),
    _audit_c_item_v0(2, "2. 1회 음주량"),
    _audit_c_item_v0(3, "3. 폭음 빈도 (6잔 이상/1회)"),
)

ITEM_BANK_V0: dict[ScaleName, ItemBankEntry] = {
    "PHQ-9": _make_entry("PHQ-9", _PHQ9_ITEMS_V0, CONSTRUCT_LABELS_V0_PROVENANCE, "v0"),
    "AUDIT-C": _make_entry("AUDIT-C", _AUDIT_C_ITEMS_V0, CONSTRUCT_LABELS_V0_PROVENANCE, "v0"),
    "GAD-7": _make_entry("GAD-7", (), UNPOPULATED_V0_PROVENANCE, "v0"),
    "PHQ-4": _make_entry("PHQ-4", (), UNPOPULATED_V0_PROVENANCE, "v0"),
    "WHO-5": _make_entry("WHO-5", (), UNPOPULATED_V0_PROVENANCE, "v0"),
}


# ── v1 content — sourced per item_bank_v1_sources.md, appendix-verbatim ───


def _phq9_item_v1(
    index: int, text_ko: str, anchors: dict[int, str], source: str
) -> ScaleItem:
    return ScaleItem(
        index=index, text_ko=text_ko, response_min=0, response_max=3,
        response_anchors=anchors, source=source,
    )


def _gad7_item_v1(
    index: int, text_ko: str, anchors: dict[int, str], source: str
) -> ScaleItem:
    return ScaleItem(
        index=index, text_ko=text_ko, response_min=0, response_max=3,
        response_anchors=anchors, source=source,
    )


def _phq4_item_v1(
    index: int, text_ko: str, anchors: dict[int, str], source: str
) -> ScaleItem:
    return ScaleItem(
        index=index, text_ko=text_ko, response_min=0, response_max=3,
        response_anchors=anchors, source=source,
    )


def _audit_c_item_v2(
    index: int,
    text_ko: str,
    anchors: dict[int, str],
    source: str,
    *,
    primary_track_label: str | None = None,
    secondary_track_label: str | None = None,
    secondary_response_anchors: dict[int, str] | None = None,
    secondary_track_conversion_note_ko: str | None = None,
) -> ScaleItem:
    return ScaleItem(
        index=index, text_ko=text_ko, response_min=0, response_max=4,
        response_anchors=anchors, source=source,
        primary_track_label=primary_track_label,
        secondary_track_label=secondary_track_label,
        secondary_response_anchors=secondary_response_anchors,
        secondary_track_conversion_note_ko=secondary_track_conversion_note_ko,
    )


# Pfizer PHQ-9 anchor set (item_bank_v1_sources.md §1.3/§A1, appendix-verbatim).
_PFIZER_PHQ9_ANCHORS_V1: dict[int, str] = {
    0: "전혀 방해 받지 않았다",
    1: "며칠 동안 방해 받았다",
    2: "7 일 이상 방해 받았다",
    3: "거의 매일 방해 받았다",
}

# Pfizer GAD-7 anchor set (item_bank_v1_sources.md §2.3/§A2, appendix-
# verbatim) — option 2 wording ("2 주 중 절반 이상") differs from PHQ-9's own
# Pfizer anchor set's option 2 ("7 일 이상") even though both are official
# Pfizer translations of the same "more than half the days" construct;
# reported as-is per the note, not harmonized.
_PFIZER_GAD7_ANCHORS_V1: dict[int, str] = {
    0: "전혀 방해 받지 않았다",
    1: "며칠 동안 방해 받았다",
    2: "2 주 중 절반 이상 방해 받았다",
    3: "거의 매일 방해 받았다",
}

_PHQ9_INSTRUCTION_KO_V1 = (
    '지난 2 주일 동안 당신은 다음의 문제들로 인해서 얼마나 자주 방해를 받았습니까? '
    '("✔"로 답을 나타내시오)'
)

PHQ9_V1_PROVENANCE = (
    "v1, verbatim Pfizer/phqscreeners.com Korean PHQ-9 PDF, retrieved 2026-07-13 "
    "(item_bank_v1_sources.md §1.2/§1.3, appendix §A1); translation chosen per "
    "ADR-033 decision 1 (Seo & Park 2015's Korean validation study administered "
    "this same translation)"
)

# item_bank_v1_sources.md §1.2 (table) / §A1 (appendix, appendix-verbatim —
# CVR-016 condition 1 canonical source).
_PHQ9_ITEMS_V1: tuple[ScaleItem, ...] = (
    _phq9_item_v1(
        1, "일 또는 여가 활동을 하는 데 흥미나 즐거움을 느끼지 못함",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    _phq9_item_v1(
        2, "기분이 가라앉거나, 우울하거나, 희망이 없음",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    _phq9_item_v1(
        3, "잠이 들거나 계속 잠을 자는 것이 어려움, 또는 잠을 너무 많이 잠",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    _phq9_item_v1(
        4, "피곤하다고 느끼거나 기운이 거의 없음",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    _phq9_item_v1(
        5, "입맛이 없거나 과식을 함",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    _phq9_item_v1(
        6, "자신을 부정적으로 봄 - 혹은 자신이 실패자라고 느끼거나 자신 또는 가족을 실망시킴",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    _phq9_item_v1(
        7, "신문을 읽거나 텔레비전 보는 것과 같은 일에 집중하는 것이 어려움",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    # Item 8 — CVR-015 Finding 1 / CVR-016 Finding 2's subject: the full
    # behavioral (retardation-OR-agitation) stem, not v0's bare 2-3-word
    # label. Byte-checked against a re-fetch in item_bank_v1_sources.md's
    # appendix-completion pass (§6 changelog, §A1) — 0 mismatches found.
    _phq9_item_v1(
        8,
        "다른 사람들이 주목할 정도로 너무 느리게 움직이거나 말을 함. 또는 반대로 평상시보다 "
        "많이 움직여서, 너무 안절부절 못하거나 들떠 있음",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
    # Item 9 — the suicidal/self-harm ideation item; deterministic safety-
    # pathway wiring keys on this item at the F3 consumer seam
    # (`src.continuous_test._route_phq9_safety_pathway`), never inside this
    # module or `src/f3.py`.
    _phq9_item_v1(
        9, "자신이 죽는 것이 더 낫다고 생각하거나 어떤 식으로든 자신을 해칠 것이라고 생각함",
        _PFIZER_PHQ9_ANCHORS_V1, PHQ9_V1_PROVENANCE,
    ),
)

_GAD7_INSTRUCTION_KO_V1 = (
    '지난 2 주 동안 당신은 다음의 문제들로 인해서 얼마나 자주 방해를 받았습니까? '
    '("✔"로 답을 나타내시오)'
)

GAD7_V1_PROVENANCE = (
    "v1, verbatim Pfizer/phqscreeners.com Korean GAD-7 PDF, retrieved 2026-07-13 "
    "(item_bank_v1_sources.md §2.2/§2.3, appendix §A2); severity bands remain "
    "international-convention-sourced only (Spitzer et al. 2006), NOT independently "
    "confirmed against a Korean-language source (§2.4) — reporting only, values unchanged"
)

# item_bank_v1_sources.md §2.2 (table) / §A2 (appendix, appendix-verbatim).
_GAD7_ITEMS_V1: tuple[ScaleItem, ...] = (
    _gad7_item_v1(
        1, "초조하거나 불안하거나 조마조마하게 느낀다", _PFIZER_GAD7_ANCHORS_V1, GAD7_V1_PROVENANCE
    ),
    _gad7_item_v1(
        2, "걱정하는 것을 멈추거나 조절할 수가 없다", _PFIZER_GAD7_ANCHORS_V1, GAD7_V1_PROVENANCE
    ),
    _gad7_item_v1(
        3, "여러 가지 것들에 대해 걱정을 너무 많이 한다",
        _PFIZER_GAD7_ANCHORS_V1, GAD7_V1_PROVENANCE,
    ),
    _gad7_item_v1(4, "편하게 있기가 어렵다", _PFIZER_GAD7_ANCHORS_V1, GAD7_V1_PROVENANCE),
    _gad7_item_v1(
        5, "너무 안절부절못해서 가만히 있기가 힘들다", _PFIZER_GAD7_ANCHORS_V1, GAD7_V1_PROVENANCE
    ),
    _gad7_item_v1(
        6, "쉽게 짜증이 나거나 쉽게 성을 내게 된다", _PFIZER_GAD7_ANCHORS_V1, GAD7_V1_PROVENANCE
    ),
    _gad7_item_v1(
        7, "마치 끔찍한 일이 생길 것처럼 두렵게 느껴진다",
        _PFIZER_GAD7_ANCHORS_V1, GAD7_V1_PROVENANCE,
    ),
)

# PHQ-4 has no standalone Korean source; composed per Kim, Shin, Lee, Han
# (2021) — items 1-2 ARE GAD-7 items 1-2 (anxiety subscale), items 3-4 ARE
# PHQ-9 items 1-2 (depression subscale) (item_bank_v1_sources.md §3.2/§A4).
# No independently-sourced composite instruction sentence exists for PHQ-4
# itself — reusing the PHQ-9 parent's own Pfizer instruction verbatim
# (items 3-4 literally ARE PHQ-9 items 1-2; items 1-2's GAD-7 parent uses an
# equivalent "지난 2주" framing per §2.3/§3.3) rather than inventing a new
# composite sentence.
_PHQ4_INSTRUCTION_KO_V1 = _PHQ9_INSTRUCTION_KO_V1

PHQ4_V1_PROVENANCE = (
    "v1, composed per Kim, Shin, Lee, Han (2021) from Pfizer Korean GAD-7 items 1-2 "
    "(anxiety subscale) + Pfizer Korean PHQ-9 items 1-2 (depression subscale) — "
    "item_bank_v1_sources.md §3.2, appendix §A2 (GAD-7)/§A1 (PHQ-9)/§A4 (composition "
    "citation, summary-basis only)"
)

_PHQ4_GAD7_SOURCE_V1 = f"{PHQ4_V1_PROVENANCE} — this item = GAD-7 item text, appendix §A2"
_PHQ4_PHQ9_SOURCE_V1 = f"{PHQ4_V1_PROVENANCE} — this item = PHQ-9 item text, appendix §A1"

_PHQ4_ITEMS_V1: tuple[ScaleItem, ...] = (
    _phq4_item_v1(
        1, "초조하거나 불안하거나 조마조마하게 느낀다",
        _PFIZER_GAD7_ANCHORS_V1, _PHQ4_GAD7_SOURCE_V1,
    ),
    _phq4_item_v1(
        2, "걱정하는 것을 멈추거나 조절할 수가 없다",
        _PFIZER_GAD7_ANCHORS_V1, _PHQ4_GAD7_SOURCE_V1,
    ),
    _phq4_item_v1(
        3, "일 또는 여가 활동을 하는 데 흥미나 즐거움을 느끼지 못함",
        _PFIZER_PHQ9_ANCHORS_V1, _PHQ4_PHQ9_SOURCE_V1,
    ),
    _phq4_item_v1(
        4, "기분이 가라앉거나, 우울하거나, 희망이 없음",
        _PFIZER_PHQ9_ANCHORS_V1, _PHQ4_PHQ9_SOURCE_V1,
    ),
)

# AUDIT-C v2 (CVR-018 Q2 adopted / ADR-034 decision 2, binding conditions
# 3-4): [별지 제15호의3서식] 음주 생활습관 평가 도구 (Korea's official
# 보건복지부고시 "건강검진 실시기준" health-screening alcohol-lifestyle
# assessment form), items 1-3 (the AUDIT-C-equivalent subset) — SUPERSEDES
# v1's SBIRT Oregon Korean AUDIT text (v1 remains documented as an
# alternate in item_bank_v1_sources.md §5, not shipped here). Every
# text_ko/response_anchors string below is copied verbatim from
# docs/ai/audit_c_korean_research.md §3.2's own table row — CVR-018 binding
# condition 8 / the qa byte-fidelity gate checks directly against THAT
# file, not this module's own copy.

# Item 1 — mirror 1 (elandclinic.com)'s complete five-anchor set, ruled for
# per CVR-018 Q2(a) (mirror 2 shows only four anchors, apparently missing
# "전혀 안 마신다(0점)" — a plausible OCR/page-render dropout, not a
# confirmed genuine form variant; disclosed in AUDIT_C_V2_PROVENANCE below).
_AUDIT_C_ITEM1_ANCHORS_V2: dict[int, str] = {
    0: "전혀 안 마신다(0점)",
    1: "한 달에 1번 이하(1점)",
    2: "한 달에 2~4번(2점)",
    3: "일주일에 2~3번(3점)",
    4: "일주일에 4번 이상(4점)",
}

# Item 2 primary track — 소주(soju)-bottle-based response anchors, both
# mirrors byte-identical.
_AUDIT_C_ITEM2_SOJU_ANCHORS_V2: dict[int, str] = {
    0: "반병 이하(0점)",
    1: "1병 이하(1점)",
    2: "1.5병정도(2점)",
    3: "2병정도(3점)",
    4: "2.5병 이상(4점)",
}

# Item 2 secondary track — glasses-based "기타 술" (other drinks) response
# anchors + the form's own explicit unit-conversion note, both mirrors
# byte-identical.
_AUDIT_C_ITEM2_OTHER_ANCHORS_V2: dict[int, str] = {
    0: "1~2잔(0점)",
    1: "3~4잔(1점)",
    2: "5~6잔(2점)",
    3: "7~9잔(3점)",
    4: "10잔 이상(4점)",
}
_AUDIT_C_ITEM2_OTHER_CONVERSION_NOTE_V2 = (
    "양주·와인은 각각의 술잔; 막걸리는 한 사발=1잔; 맥주는 캔맥주 1캔 또는 작은 병맥주 "
    "1병=1잔, 생맥주 500cc=1.3잔"
)

_AUDIT_C_ITEM3_ANCHORS_V2: dict[int, str] = {
    0: "전혀 없다(0점)",
    1: "한 달에 한 번 미만(1점)",
    2: "한 달에 한 번 정도(2점)",
    3: "일주일에 한 번 정도(3점)",
    4: "거의 매일(4점)",
}

AUDIT_C_V2_PROVENANCE = (
    "v2, verbatim [별지 제15호의3서식] 음주 생활습관 평가 도구 (Korea's official "
    "보건복지부고시 '건강검진 실시기준' health-screening alcohol-lifestyle assessment "
    "form), items 1-3 (the AUDIT-C-equivalent subset). Cross-verified via two "
    "independent mirrors, both retrieved 2026-07-13: elandclinic.com "
    "'음주생활습관평가도구(검진자용).pdf' (mirror 1) and epower.hanilmed.net "
    "'2021_생활습관포함서식.pdf' (mirror 2) -- docs/ai/audit_c_korean_research.md "
    "§3.1/§3.2. Item 1 ships mirror 1's complete five-anchor set (incl. '전혀 안 "
    "마신다(0점)'); mirror 2 shows only four anchors for item 1, apparently missing "
    "the 0-anchor -- CVR-018 Q2(a) rules for mirror 1's complete set (universal AUDIT "
    "item-1 zero/never-anchor shape; plausible OCR/page-render dropout in mirror 2, "
    "not a confirmed genuine form variant). Items 2-3 are byte-identical across both "
    "mirrors, no discrepancy to disclose. Item 2 is bifurcated into a native "
    "소주-bottle track (response_anchors) and a glasses-based '기타 술' track with its "
    "own explicit beer/makgeolli/draft-beer unit-conversion table "
    "(secondary_response_anchors / secondary_track_conversion_note_ko) -- adopted "
    "specifically because it structurally eliminates the Western/soju unit-conversion "
    "confound CVR-017 Finding 4 live-confirmed under v1's Western-unit-only item 2 "
    "(CVR-018 Q2(c)). CVR-018 Finding 6 translation-identity caveat, unresolved either "
    "way: byte-identity of this item wording to the Korean-population cutoff-validation "
    "studies underlying the adopted threshold (Lee JH et al. 2018 KNHANES, Kwon et al. "
    "2013) is UNCONFIRMED -- none of those studies reproduce their own item-text "
    "appendix (docs/ai/audit_c_korean_research.md §3.4). Supersedes v1's SBIRT Oregon "
    "Korean AUDIT text (ADR-034 decision 2) -- the v1 text remains documented as an "
    "alternate in item_bank_v1_sources.md §5, not shipped in this item bank as of v2."
)

_AUDIT_C_ITEMS_V2: tuple[ScaleItem, ...] = (
    _audit_c_item_v2(
        1, "술을 마시는 횟수는 어느 정도입니까?",
        _AUDIT_C_ITEM1_ANCHORS_V2, AUDIT_C_V2_PROVENANCE,
    ),
    _audit_c_item_v2(
        2,
        "술을 마시는 날은 보통 어느 정도 마십니까? (아래의 두 곳 중 주로 드시는 술을 "
        "선택하여 한 곳에 표시해 주시면 됩니다.)",
        _AUDIT_C_ITEM2_SOJU_ANCHORS_V2, AUDIT_C_V2_PROVENANCE,
        primary_track_label="소주 트랙",
        secondary_track_label="기타 술 트랙",
        secondary_response_anchors=_AUDIT_C_ITEM2_OTHER_ANCHORS_V2,
        secondary_track_conversion_note_ko=_AUDIT_C_ITEM2_OTHER_CONVERSION_NOTE_V2,
    ),
    _audit_c_item_v2(
        3,
        "한 번의 술좌석에서 소주 1병을 초과하거나 맥주 5캔(생맥주 2,000cc) 이상*을 마시는 "
        "횟수는 어느 정도입니까? (*알코올 60g에 해당하는 음주량을 의미한다. / 양주, 와인, "
        "막걸리는 각각의 술잔으로 5잔 이상)",
        _AUDIT_C_ITEM3_ANCHORS_V2, AUDIT_C_V2_PROVENANCE,
    ),
)

# Machine-readable AUDIT-C threshold caveat (CVR-018 Q4 / ADR-034 decision
# 1, binding condition 2) -- English, not a Korean instrument string
# (outside this module's Korean-fabrication-0 scope by construction).
# Attached to the F3 artifact by `src/f3.py` for AUDIT-C administered
# outcomes; the threshold ITSELF lives in survey_scorer.py::_score_audit_c.
# Rewritten per CVR-018 Q4's five content requirements: (i) adopted
# threshold + basis, (ii) non-adopted alternatives + explicit reasons,
# (iii) international-cutoff-as-metadata note, (iv) residual
# translation-identity caveat, (v) criterion-circularity disclosure.
AUDIT_C_THRESHOLD_CAVEAT = (
    "AUDIT-C severity threshold is Korean-primary: male/unknown >= 6, female >= 5 "
    "(Lee JH et al. 2018, KNHANES waves 4-6, N=46,450 nationally representative Korean "
    "adults, sex-split cutoff; male value independently corroborated by Kwon et al. "
    "2013's DSM-IV-TR-anchored at-risk-drinking male cutoff, also 6). Adopted per "
    "CVR-018 Q1 / ADR-034 decision 1 -- chosen as the more sensitive (lower, more "
    "inclusive) end of the Korean evidence range to bound under-triage risk on a "
    "substance-use screen. "
    "Two higher Korean cutoffs were considered and NOT adopted: Seong et al. 2009 "
    "(N=302 Korean men, cutoff >=8) has no female arm and cannot alone found a "
    "dual-sex threshold; Lee BW et al. 2000 (N=86, cutoff >=8) is an explicit "
    "case-control design with unreported sex composition, a weaker population match "
    "than a nationally representative sample. "
    "The international cutoff (Bush et al. 1998, male/unknown >= 4, female >= 3) is "
    "retained on the F3 artifact as non-action-driving structured reference metadata "
    "only -- it never independently triggers severity or clinician_review. "
    "Residual caveat: no study in the evidentiary base (Korean or international) "
    "reproduces its own item-text appendix, so byte-identity between these adopted "
    "cutoff numbers and whichever AUDIT-C item text is administered (v1 SBIRT Oregon "
    "or v2 soju-track) is unconfirmed either way. "
    "The adopted cutoff study (KNHANES) and most of the underlying Korean literature "
    "validate AUDIT-C against a whole-AUDIT total score derived from the same 10-item "
    "instrument (AUDIT-C is items 1-3 of it) -- a same-instrument criterion-circularity "
    "limitation, disclosed here rather than smoothed over. "
    "See docs/ai/audit_c_korean_research.md section 1 (study #9 Lee JH 2018, study #4 "
    "Kwon 2013) and CVR-018 Q1/Q4."
)

# Machine-readable GAD-7 band-sourcing caveat (CVR-016 binding condition 1 /
# CVR-017 binding condition 1 / REV-039 correction D) -- English, not a
# Korean instrument string, outside this module's Korean-fabrication-0 scope
# by construction, same structural discipline as AUDIT_C_THRESHOLD_CAVEAT
# above. Attached to the F3 artifact by src/f3.py for GAD-7 administered
# outcomes; the bands THEMSELVES (survey_scorer.py 0-4/5-9/10-14/15-21) are
# byte-unchanged -- this is a disclosure-symmetry fix, not a value change.
GAD7_BAND_CAVEAT = (
    "GAD-7 severity bands (0-4 minimal / 5-9 mild / 10-14 moderate / 15-21 severe) "
    "rest on international-convention-only sourcing: Spitzer RL, Kroenke K, Williams "
    "JB, Löwe B. \"A brief measure for assessing generalized anxiety disorder: the "
    "GAD-7.\" Arch Intern Med. 2006;166(10):1092-1097 -- the GAD-7's own primary "
    "validation paper, citation-basis only (not fetched or read in full this "
    "mission). A previously-cited Korean-language clinician scoring-table source for "
    "these bands was RETRACTED during v1 sourcing after a re-fetch of the same URL "
    "returned no such table -- see item_bank_v1_sources.md section 2.4. "
    "No Korean-population source currently confirms these particular band cutoffs; "
    "band values are unchanged this mission (ADR-033 decision 2) -- this is a "
    "disclosure-symmetry fix, not a value change."
)

# WHO-5: 0/5 items sourced after an exhaustive, documented two-session retry
# (item_bank_v1_sources.md §4.6) — psykiatri-regionh.dk 5/5 timeouts; Kim
# et al. 2010 / Moon et al. 2014 both abstract-only (KCI/DBpia/ScienceDirect
# gated, no OA PDF per direct OpenAlex/Semantic Scholar queries); NCMH
# standard-guide PDF blocked via 3 independent routes (JS-triggered
# handlers). Fabrication-0: ships empty, never invented.
WHO5_V1_PROVENANCE = (
    "unpopulated-v1, sourcing gap documented (item_bank_v1_sources.md §4.6): "
    "psykiatri-regionh.dk 5/5 timeouts across 2 sessions; Kim et al. 2010 / Moon et al. "
    "2014 both abstract-only-accessible (no OA PDF); NCMH standard-guide PDF blocked "
    "via 3 independent routes. No item text fabricated."
)

ITEM_BANK: dict[ScaleName, ItemBankEntry] = {
    "PHQ-9": _make_entry(
        "PHQ-9", _PHQ9_ITEMS_V1, PHQ9_V1_PROVENANCE, "v1", _PHQ9_INSTRUCTION_KO_V1
    ),
    "GAD-7": _make_entry(
        "GAD-7", _GAD7_ITEMS_V1, GAD7_V1_PROVENANCE, "v1", _GAD7_INSTRUCTION_KO_V1
    ),
    "PHQ-4": _make_entry(
        "PHQ-4", _PHQ4_ITEMS_V1, PHQ4_V1_PROVENANCE, "v1", _PHQ4_INSTRUCTION_KO_V1
    ),
    "WHO-5": _make_entry("WHO-5", (), WHO5_V1_PROVENANCE, "v1", None),
    # instruction_ko=None: unlike v1's SBIRT Oregon source, no standalone
    # instruction/framing sentence for the [별지 제15호의3서식] form is
    # quoted verbatim anywhere in docs/ai/audit_c_korean_research.md's §3 —
    # fabrication-0 means this ships absent, never invented (same
    # discipline as WHO-5's empty item list above).
    "AUDIT-C": _make_entry("AUDIT-C", _AUDIT_C_ITEMS_V2, AUDIT_C_V2_PROVENANCE, "v2", None),
}


def validate_item_bank_completeness(
    bank: Mapping[ScaleName, ItemBankEntry] | None = None,
) -> None:
    """Fail-fast registry-completeness check (mirrors
    `questionnaire_mapping.py`'s own import-time assertion pattern):
    `bank`'s key set must equal `SUPPORTED_SCALES` exactly. A missing KEY is
    a bug; an unpopulated entry (present, `populated=False`) is not.

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


# Fail fast at import time, same discipline as questionnaire_mapping.py —
# checked against BOTH the live v1/v2 bank and the retained v0 bank.
validate_item_bank_completeness(ITEM_BANK)
validate_item_bank_completeness(ITEM_BANK_V0)

# AUDIT-C is v2 as of CVR-018/ADR-034; every other scale in ITEM_BANK stays
# v1 this mission (PHQ-9/GAD-7/PHQ-4/WHO-5 byte-untouched).
_EXPECTED_ITEM_BANK_VERSION: dict[ScaleName, str] = {
    "PHQ-9": "v1", "GAD-7": "v1", "PHQ-4": "v1", "WHO-5": "v1", "AUDIT-C": "v2",
}

for _scale_name, _entry in ITEM_BANK.items():
    _expected_version = _EXPECTED_ITEM_BANK_VERSION[_scale_name]
    assert _entry.version == _expected_version, (
        f"ITEM_BANK[{_scale_name!r}] version must be {_expected_version!r}"
    )
    if _entry.populated:
        assert len(_entry.items) == _EXPECTED_ITEM_COUNTS[_scale_name], (
            f"ITEM_BANK[{_scale_name!r}] marked populated with the wrong item count"
        )
        assert _entry.provenance, f"ITEM_BANK[{_scale_name!r}] populated but provenance is empty"
        assert all(it.text_ko for it in _entry.items), (
            f"ITEM_BANK[{_scale_name!r}] populated but has a blank item text"
        )
    else:
        assert _entry.items == (), f"ITEM_BANK[{_scale_name!r}] unpopulated but items is non-empty"
        assert _entry.provenance, (
            f"ITEM_BANK[{_scale_name!r}] unpopulated but provenance is empty — a gap must "
            "still self-describe why"
        )

for _scale_name, _entry in ITEM_BANK_V0.items():
    assert _entry.version == "v0", f"ITEM_BANK_V0[{_scale_name!r}] version must be 'v0'"
    if _entry.populated:
        assert len(_entry.items) == _EXPECTED_ITEM_COUNTS[_scale_name], (
            f"ITEM_BANK_V0[{_scale_name!r}] marked populated with the wrong item count"
        )
        assert _entry.provenance == CONSTRUCT_LABELS_V0_PROVENANCE, (
            f"ITEM_BANK_V0[{_scale_name!r}] populated but provenance is not the v0 "
            "construct-label string"
        )
    else:
        assert _entry.items == (), (
            f"ITEM_BANK_V0[{_scale_name!r}] unpopulated but items is non-empty"
        )
        assert _entry.provenance == UNPOPULATED_V0_PROVENANCE, (
            f"ITEM_BANK_V0[{_scale_name!r}] unpopulated but provenance is not 'unpopulated-v0'"
        )


def get_item_bank(scale_name: ScaleName) -> ItemBankEntry:
    """Look up the v1 item bank entry for `scale_name`. Raises `KeyError`
    (loud, never a silent `None`) for a scale not in `SUPPORTED_SCALES` —
    should never happen once `validate_item_bank_completeness()` is green.
    """
    entry = ITEM_BANK.get(scale_name)
    if entry is None:
        raise KeyError(
            f"No item bank entry registered for scale {scale_name!r} — "
            f"SUPPORTED_SCALES={sorted(SUPPORTED_SCALES)}"
        )
    return entry


def get_item_bank_v0(scale_name: ScaleName) -> ItemBankEntry:
    """v0 lookup — kept for EXP-019 artifact interpretability (that battery
    ran against v0 content; its item text must stay reconstructable even
    though `ITEM_BANK`/`get_item_bank` are v1 as of this mission).
    """
    entry = ITEM_BANK_V0.get(scale_name)
    if entry is None:
        raise KeyError(
            f"No v0 item bank entry registered for scale {scale_name!r} — "
            f"SUPPORTED_SCALES={sorted(SUPPORTED_SCALES)}"
        )
    return entry
