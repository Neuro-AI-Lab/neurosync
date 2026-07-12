"""`src.scoring.item_bank` — v0 item bank structural + no-fabrication tests.

`docs/ai/f3_quick_dev_plan.md` §2. No LLM/DB — pure structural checks.
"""

from __future__ import annotations

import pytest

from src.scoring.item_bank import (
    CONSTRUCT_LABELS_V0_PROVENANCE,
    ITEM_BANK,
    UNPOPULATED_V0_PROVENANCE,
    ItemBankEntry,
    ScaleItem,
    get_item_bank,
    validate_item_bank_completeness,
)
from src.scoring.survey_scorer import SUPPORTED_SCALES


class TestRegistryCompleteness:
    def test_key_set_matches_supported_scales(self) -> None:
        assert set(ITEM_BANK.keys()) == SUPPORTED_SCALES

    def test_validate_item_bank_completeness_passes_on_real_bank(self) -> None:
        validate_item_bank_completeness()  # must not raise

    def test_validate_item_bank_completeness_raises_on_missing_key(self) -> None:
        broken = {k: v for k, v in ITEM_BANK.items() if k != "GAD-7"}
        with pytest.raises(AssertionError, match="missing"):
            validate_item_bank_completeness(broken)

    def test_validate_item_bank_completeness_raises_on_extra_key(self) -> None:
        broken = dict(ITEM_BANK)
        broken["NOT-A-REAL-SCALE"] = ITEM_BANK["PHQ-9"]  # type: ignore[index]
        with pytest.raises(AssertionError, match="extra"):
            validate_item_bank_completeness(broken)  # type: ignore[arg-type]


class TestPopulatedScalesPHQ9AndAuditC:
    def test_phq9_populated_nine_items_range_0_3(self) -> None:
        entry = get_item_bank("PHQ-9")
        assert entry.populated is True
        assert entry.version == "v0"
        assert entry.provenance == CONSTRUCT_LABELS_V0_PROVENANCE
        assert len(entry.items) == 9
        for i, item in enumerate(entry.items, start=1):
            assert item.index == i
            assert item.response_min == 0
            assert item.response_max == 3
            assert item.response_anchors is None
            assert item.text_ko  # non-empty, never fabricated blank

    def test_phq9_item_9_is_the_suicidal_ideation_item(self) -> None:
        entry = get_item_bank("PHQ-9")
        assert "자살" in entry.items[8].text_ko

    def test_audit_c_populated_three_items_range_0_4(self) -> None:
        entry = get_item_bank("AUDIT-C")
        assert entry.populated is True
        assert entry.provenance == CONSTRUCT_LABELS_V0_PROVENANCE
        assert len(entry.items) == 3
        for i, item in enumerate(entry.items, start=1):
            assert item.index == i
            assert item.response_min == 0
            assert item.response_max == 4
            assert item.response_anchors is None
            assert item.text_ko

    def test_phq9_labels_sourced_from_persona_files_not_invented(self) -> None:
        """Cross-check against VP-001's own documented PHQ-9 construct
        labels (docs/ai/personas/VP-001_first_visit_mild.md:81-95) — proves
        this module's text is repo-sourced, not authored fresh here."""
        entry = get_item_bank("PHQ-9")
        labels = [it.text_ko for it in entry.items]
        assert "1. 흥미/즐거움 감소" in labels
        assert "2. 우울감" in labels
        assert "9. 자살/자해 사고" in labels

    def test_audit_c_labels_sourced_from_persona_file_not_invented(self) -> None:
        entry = get_item_bank("AUDIT-C")
        labels = [it.text_ko for it in entry.items]
        assert "1. 음주 빈도" in labels
        assert "2. 1회 음주량" in labels


class TestUnpopulatedScales:
    @pytest.mark.parametrize("scale_name", ["GAD-7", "PHQ-4", "WHO-5"])
    def test_unpopulated_scales_have_no_items_and_are_flagged(self, scale_name: str) -> None:
        entry = get_item_bank(scale_name)
        assert entry.populated is False
        assert entry.items == ()
        assert entry.provenance == UNPOPULATED_V0_PROVENANCE
        assert entry.version == "v0"


class TestGetItemBank:
    def test_unknown_scale_raises_keyerror_loudly(self) -> None:
        with pytest.raises(KeyError, match="No item bank entry"):
            get_item_bank("NOT-A-SCALE")  # type: ignore[arg-type]


class TestMakeEntryPopulatedComputation:
    """`_make_entry`'s `populated` computation, exercised indirectly via a
    hand-built entry (not monkeypatching module state)."""

    def test_wrong_item_count_is_never_populated(self) -> None:
        from src.scoring.item_bank import _make_entry  # noqa: PLC0415 — test-only reach-in

        entry = _make_entry(
            "PHQ-9",
            (ScaleItem(index=1, text_ko="x", response_min=0, response_max=3),),
            CONSTRUCT_LABELS_V0_PROVENANCE,
        )
        assert entry.populated is False

    def test_empty_provenance_is_never_populated(self) -> None:
        from src.scoring.item_bank import _EXPECTED_ITEM_COUNTS, _make_entry  # noqa: PLC0415

        items = tuple(
            ScaleItem(index=i, text_ko=f"item {i}", response_min=0, response_max=4)
            for i in range(1, _EXPECTED_ITEM_COUNTS["AUDIT-C"] + 1)
        )
        entry = _make_entry("AUDIT-C", items, "")
        assert entry.populated is False

    def test_blank_item_text_is_never_populated(self) -> None:
        from src.scoring.item_bank import _EXPECTED_ITEM_COUNTS, _make_entry  # noqa: PLC0415

        items = tuple(
            ScaleItem(
                index=i, text_ko="" if i == 1 else f"item {i}", response_min=0, response_max=4
            )
            for i in range(1, _EXPECTED_ITEM_COUNTS["AUDIT-C"] + 1)
        )
        entry = _make_entry("AUDIT-C", items, CONSTRUCT_LABELS_V0_PROVENANCE)
        assert entry.populated is False


def test_item_bank_entry_and_scale_item_are_frozen() -> None:
    entry = get_item_bank("PHQ-9")
    with pytest.raises(Exception):  # noqa: B017, PT011 — dataclasses.FrozenInstanceError
        entry.populated = False  # type: ignore[misc]
    with pytest.raises(Exception):  # noqa: B017, PT011
        entry.items[0].index = 99  # type: ignore[misc]


def test_item_bank_entry_type_is_the_expected_dataclass() -> None:
    assert isinstance(get_item_bank("PHQ-9"), ItemBankEntry)
