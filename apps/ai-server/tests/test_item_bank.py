"""`src.scoring.item_bank` — v1 byte-fidelity tests + retained v0 provenance
tests.

`PLAN-2026-W29-A` step 3, `docs/ai/item_bank_v1_sources.md` (brainstorm's
sourcing note), `CVR-016` (content-fidelity gate), `ADR-033` (dispositions).
No LLM/DB — pure structural + string-fidelity checks against the sourcing
note's own appendix quotes (CVR-016 condition 1: appendix is canonical, not
the note's prose-table renderings).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.scoring.item_bank import (
    AUDIT_C_THRESHOLD_CAVEAT,
    CONSTRUCT_LABELS_V0_PROVENANCE,
    GAD7_BAND_CAVEAT,
    ITEM_BANK,
    ITEM_BANK_V0,
    UNPOPULATED_V0_PROVENANCE,
    ItemBankEntry,
    ScaleItem,
    get_item_bank,
    get_item_bank_v0,
    validate_item_bank_completeness,
)
from src.scoring.survey_scorer import SUPPORTED_SCALES

# ── Ground truth: the sourcing note's own appendix (§A1/§A2/§A5), dewrapped
#    the same way CVR-016 condition 1 requires — no separate transcription,
#    this reads the actual note so a future note edit that silently drifts
#    from item_bank.py is caught here, not just eyeballed once at authoring
#    time.

_SOURCES_NOTE_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "ai" / "item_bank_v1_sources.md"
)

# AUDIT-C v2's own canonical byte-fidelity source (CVR-018 binding condition
# 8) — a SEPARATE file from item_bank_v1_sources.md, which only documents
# v1's (now-superseded) SBIRT Oregon AUDIT-C text.
_AUDIT_C_RESEARCH_NOTE_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "ai" / "audit_c_korean_research.md"
)


def _dewrap_appendix_block(text: str, start_marker: str, end_marker: str) -> str:
    """Join a `> `-prefixed markdown blockquote's wrapped lines with single
    spaces (a hard line-wrap in the note's own source is not a real newline
    in the quoted document) — mirrors how the note's own prose sections
    already render the same content.
    """
    s = text.index(start_marker)
    e = text.index(end_marker, s)
    block = text[s:e]
    quote_start = block.index("\n>")
    quote_end = block.index("\n\n", quote_start)
    quote = block[quote_start:quote_end]
    lines = [
        line[2:] if line.startswith("> ") else line[1:]
        for line in quote.splitlines()
        if line.strip()
    ]
    return " ".join(line.strip() for line in lines)


@pytest.fixture(scope="module")
def sources_note_text() -> str:
    if not _SOURCES_NOTE_PATH.exists():
        pytest.skip(f"sourcing note not found at {_SOURCES_NOTE_PATH}")
    return _SOURCES_NOTE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def appendix_a1(sources_note_text: str) -> str:
    return _dewrap_appendix_block(sources_note_text, "### §A1", "### §A2 —")


@pytest.fixture(scope="module")
def appendix_a2(sources_note_text: str) -> str:
    return _dewrap_appendix_block(sources_note_text, "### §A2 — Pfizer", "### §A2b")


@pytest.fixture(scope="module")
def appendix_a5(sources_note_text: str) -> str:
    return _dewrap_appendix_block(sources_note_text, "### §A5 —", "### §A6 —")


@pytest.fixture(scope="module")
def audit_c_research_note_text() -> str:
    if not _AUDIT_C_RESEARCH_NOTE_PATH.exists():
        pytest.skip(f"AUDIT-C research note not found at {_AUDIT_C_RESEARCH_NOTE_PATH}")
    return _AUDIT_C_RESEARCH_NOTE_PATH.read_text(encoding="utf-8")


class TestRegistryCompleteness:
    def test_key_set_matches_supported_scales(self) -> None:
        assert set(ITEM_BANK.keys()) == SUPPORTED_SCALES

    def test_v0_key_set_matches_supported_scales(self) -> None:
        assert set(ITEM_BANK_V0.keys()) == SUPPORTED_SCALES

    def test_validate_item_bank_completeness_passes_on_real_bank(self) -> None:
        validate_item_bank_completeness()  # must not raise (defaults to ITEM_BANK)
        validate_item_bank_completeness(ITEM_BANK_V0)  # must not raise

    def test_validate_item_bank_completeness_raises_on_missing_key(self) -> None:
        broken = {k: v for k, v in ITEM_BANK.items() if k != "GAD-7"}
        with pytest.raises(AssertionError, match="missing"):
            validate_item_bank_completeness(broken)

    def test_validate_item_bank_completeness_raises_on_extra_key(self) -> None:
        broken = dict(ITEM_BANK)
        broken["NOT-A-REAL-SCALE"] = ITEM_BANK["PHQ-9"]  # type: ignore[index]
        with pytest.raises(AssertionError, match="extra"):
            validate_item_bank_completeness(broken)  # type: ignore[arg-type]


# ── v1 byte-fidelity: PHQ-9, GAD-7, AUDIT-C item text/anchors must match the
#    note's appendix EXACTLY (CVR-016 condition 1) ──────────────────────────


class TestPHQ9V1ByteFidelity:
    def test_populated_nine_items_v1(self) -> None:
        entry = get_item_bank("PHQ-9")
        assert entry.populated is True
        assert entry.version == "v1"
        assert len(entry.items) == 9

    def test_every_item_text_byte_matches_appendix_a1(self, appendix_a1: str) -> None:
        entry = get_item_bank("PHQ-9")
        for item in entry.items:
            assert item.text_ko in appendix_a1, f"PHQ-9 item {item.index} not byte-exact vs §A1"

    def test_item_8_full_behavioral_stem_present(self, appendix_a1: str) -> None:
        """CVR-015 Finding 1 / CVR-016 Finding 2's subject item — the whole
        reason this v1 dispatch exists."""
        entry = get_item_bank("PHQ-9")
        item8 = entry.items[7]
        assert item8.index == 8
        assert "안절부절" in item8.text_ko
        assert "느리게 움직이거나" in item8.text_ko
        assert item8.text_ko in appendix_a1

    def test_item_9_is_the_suicidal_ideation_item(self) -> None:
        entry = get_item_bank("PHQ-9")
        assert "자살" in entry.items[8].text_ko or "해칠" in entry.items[8].text_ko
        assert entry.items[8].index == 9

    def test_response_anchors_populated_and_byte_match_appendix(self, appendix_a1: str) -> None:
        entry = get_item_bank("PHQ-9")
        for item in entry.items:
            assert item.response_anchors is not None
            assert set(item.response_anchors.keys()) == {0, 1, 2, 3}
            for label in item.response_anchors.values():
                assert label in appendix_a1

    def test_instruction_ko_byte_matches_appendix(self, appendix_a1: str) -> None:
        entry = get_item_bank("PHQ-9")
        assert entry.instruction_ko is not None
        assert entry.instruction_ko in appendix_a1

    def test_response_range_unchanged_0_3(self) -> None:
        entry = get_item_bank("PHQ-9")
        for item in entry.items:
            assert (item.response_min, item.response_max) == (0, 3)

    def test_provenance_cites_the_sourcing_note(self) -> None:
        entry = get_item_bank("PHQ-9")
        assert "item_bank_v1_sources.md" in entry.provenance
        assert "Pfizer" in entry.provenance


class TestGAD7V1ByteFidelity:
    def test_populated_seven_items_v1(self) -> None:
        entry = get_item_bank("GAD-7")
        assert entry.populated is True
        assert entry.version == "v1"
        assert len(entry.items) == 7

    def test_every_item_text_byte_matches_appendix_a2(self, appendix_a2: str) -> None:
        entry = get_item_bank("GAD-7")
        for item in entry.items:
            assert item.text_ko in appendix_a2, f"GAD-7 item {item.index} not byte-exact vs §A2"

    def test_response_anchors_populated_and_byte_match_appendix(self, appendix_a2: str) -> None:
        entry = get_item_bank("GAD-7")
        for item in entry.items:
            assert item.response_anchors is not None
            assert set(item.response_anchors.keys()) == {0, 1, 2, 3}
            for label in item.response_anchors.values():
                assert label in appendix_a2

    def test_option_2_anchor_differs_from_phq9_option_2(self) -> None:
        """§2.3: GAD-7's Pfizer option-2 wording ("2 주 중 절반 이상") differs
        from PHQ-9's Pfizer option-2 wording ("7 일 이상") — reported as-is
        per the note, never harmonized."""
        gad7_anchor2 = get_item_bank("GAD-7").items[0].response_anchors[2]
        phq9_anchor2 = get_item_bank("PHQ-9").items[0].response_anchors[2]
        assert gad7_anchor2 != phq9_anchor2
        assert "절반" in gad7_anchor2
        assert "7" in phq9_anchor2

    def test_instruction_ko_byte_matches_appendix(self, appendix_a2: str) -> None:
        entry = get_item_bank("GAD-7")
        assert entry.instruction_ko is not None
        assert entry.instruction_ko in appendix_a2


class TestPHQ4V1Composition:
    def test_populated_four_items_v1(self) -> None:
        entry = get_item_bank("PHQ-4")
        assert entry.populated is True
        assert entry.version == "v1"
        assert len(entry.items) == 4

    def test_items_1_2_are_gad7_items_1_2(self) -> None:
        phq4 = get_item_bank("PHQ-4").items
        gad7 = get_item_bank("GAD-7").items
        assert phq4[0].text_ko == gad7[0].text_ko
        assert phq4[1].text_ko == gad7[1].text_ko

    def test_items_3_4_are_phq9_items_1_2(self) -> None:
        phq4 = get_item_bank("PHQ-4").items
        phq9 = get_item_bank("PHQ-9").items
        assert phq4[2].text_ko == phq9[0].text_ko
        assert phq4[3].text_ko == phq9[1].text_ko

    def test_anchor_option_2_wording_inherited_unharmonized(self) -> None:
        """§3.3: items 1-2 keep GAD-7's "2주 중 절반 이상"; items 3-4 keep
        PHQ-9's "7 일 이상" — inherited verbatim per the composition rule,
        not harmonized into one shared wording."""
        phq4 = get_item_bank("PHQ-4").items
        assert phq4[0].response_anchors[2] == get_item_bank("GAD-7").items[0].response_anchors[2]
        assert phq4[2].response_anchors[2] == get_item_bank("PHQ-9").items[0].response_anchors[2]


class TestAuditCV2ByteFidelity:
    """AUDIT-C v2 (CVR-018 Q2 adopted / ADR-034 decision 2) — the [별지
    제15호의3서식] soju-track text. Canonical byte-fidelity source is
    `docs/ai/audit_c_korean_research.md` §3.2 (CVR-018 binding condition
    8), NOT `item_bank_v1_sources.md` (that file only documents v1's
    now-superseded SBIRT Oregon text)."""

    def test_populated_three_items_v2(self) -> None:
        entry = get_item_bank("AUDIT-C")
        assert entry.populated is True
        assert entry.version == "v2"
        assert len(entry.items) == 3

    def test_every_item_text_byte_matches_research_note(
        self, audit_c_research_note_text: str
    ) -> None:
        entry = get_item_bank("AUDIT-C")
        for item in entry.items:
            assert item.text_ko in audit_c_research_note_text, (
                f"AUDIT-C item {item.index} not byte-exact vs audit_c_korean_research.md"
            )

    def test_item_anchors_byte_match_research_note(
        self, audit_c_research_note_text: str
    ) -> None:
        entry = get_item_bank("AUDIT-C")
        for item in entry.items:
            assert item.response_anchors is not None
            assert set(item.response_anchors.keys()) == {0, 1, 2, 3, 4}
            for label in item.response_anchors.values():
                assert label in audit_c_research_note_text

    def test_item2_secondary_track_anchors_byte_match_research_note(
        self, audit_c_research_note_text: str
    ) -> None:
        """CVR-018 Q2(c): item 2's '기타 술' secondary track + its explicit
        beer/makgeolli/draft-beer conversion note."""
        item2 = get_item_bank("AUDIT-C").items[1]
        assert item2.secondary_track_label == "기타 술 트랙"
        assert item2.secondary_response_anchors is not None
        assert set(item2.secondary_response_anchors.keys()) == {0, 1, 2, 3, 4}
        for label in item2.secondary_response_anchors.values():
            assert label in audit_c_research_note_text
        assert item2.secondary_track_conversion_note_ko is not None
        assert item2.secondary_track_conversion_note_ko in audit_c_research_note_text

    def test_item2_primary_track_label_byte_matches_research_note(
        self, audit_c_research_note_text: str
    ) -> None:
        """BUG-039 fix: item 2's primary (소주) track needs its own sourced
        label so `build_item_prompt` can render both tracks distinguishably
        — verbatim from `docs/ai/audit_c_korean_research.md` §3.2's own
        bolded "소주 트랙" table-row label, never invented in the harness."""
        item2 = get_item_bank("AUDIT-C").items[1]
        assert item2.primary_track_label == "소주 트랙"
        assert item2.primary_track_label in audit_c_research_note_text

    def test_only_item2_has_primary_track_label(self) -> None:
        entry = get_item_bank("AUDIT-C")
        assert entry.items[0].primary_track_label is None
        assert entry.items[1].primary_track_label is not None
        assert entry.items[2].primary_track_label is None

    def test_item1_ships_mirror1_complete_five_anchor_set(self) -> None:
        """CVR-018 Q2(a) / binding condition 3: item 1 ships mirror 1's
        complete five-anchor set, including the zero/never anchor mirror 2
        appears to be missing."""
        item1 = get_item_bank("AUDIT-C").items[0]
        assert item1.response_anchors[0] == "전혀 안 마신다(0점)"
        assert len(item1.response_anchors) == 5

    def test_only_item2_is_dual_tracked(self) -> None:
        entry = get_item_bank("AUDIT-C")
        assert entry.items[0].secondary_response_anchors is None
        assert entry.items[1].secondary_response_anchors is not None
        assert entry.items[2].secondary_response_anchors is None

    def test_item_anchors_are_item_specific_not_shared(self) -> None:
        entry = get_item_bank("AUDIT-C")
        assert entry.items[0].response_anchors != entry.items[1].response_anchors
        assert entry.items[1].response_anchors != entry.items[2].response_anchors

    def test_response_range_0_4(self) -> None:
        entry = get_item_bank("AUDIT-C")
        for item in entry.items:
            assert (item.response_min, item.response_max) == (0, 4)

    def test_instruction_ko_is_none_no_fabricated_framing(self) -> None:
        """No standalone instruction/framing sentence for the [별지
        제15호의3서식] form is quoted verbatim in the research note's §3 —
        fabrication-0 means this stays None, never invented (unlike v1's
        SBIRT-sourced instruction_ko, which WAS quoted verbatim)."""
        assert get_item_bank("AUDIT-C").instruction_ko is None

    def test_provenance_discloses_translation_identity_unconfirmed(self) -> None:
        """CVR-018 Finding 6: translation-identity to the Korean-population
        cutoff-validation studies underlying the adopted threshold (Lee JH
        2018 KNHANES, Kwon 2013) is unconfirmed — must be disclosed in the
        provenance, not silently dropped."""
        entry = get_item_bank("AUDIT-C")
        assert "unconfirmed" in entry.provenance.lower()
        assert "Lee JH" in entry.provenance
        assert "Kwon" in entry.provenance

    def test_provenance_discloses_mirror2_discrepancy_and_pick_rationale(self) -> None:
        """CVR-018 binding condition 3: provenance must disclose the
        mirror-2 four-anchor discrepancy AND the mirror-1 pick rationale,
        not just silently ship mirror 1's set."""
        entry = get_item_bank("AUDIT-C")
        assert "mirror 1" in entry.provenance
        assert "mirror 2" in entry.provenance
        assert "0-anchor" in entry.provenance or "0점" in entry.provenance

    def test_provenance_notes_v1_superseded(self) -> None:
        entry = get_item_bank("AUDIT-C")
        assert "supersede" in entry.provenance.lower()
        assert "item_bank_v1_sources.md" in entry.provenance

    def test_v2_item_text_differs_from_no_longer_shipped_v1_text(self) -> None:
        """Sanity: v2's item text is genuinely different from the
        no-longer-shipped v1 SBIRT-Oregon text (the specific v1 item-1
        string is no longer what ships) — otherwise 'AUDIT-C is v2' would
        be a version-stamp-only change."""
        item1 = get_item_bank("AUDIT-C").items[0]
        assert item1.text_ko != "알코올 음료를 얼마나 자주 마십니까?"


class TestAuditCV2NoFabrication:
    """Fabrication-0 for AUDIT-C v2 specifically — every Korean string on
    every item/anchor (including the item-2 secondary track) must exist
    verbatim in `docs/ai/audit_c_korean_research.md` (AUDIT-C's OWN
    canonical source, separate from item_bank_v1_sources.md)."""

    def test_every_item_text_exists_in_research_note(
        self, audit_c_research_note_text: str
    ) -> None:
        entry = get_item_bank("AUDIT-C")
        for item in entry.items:
            assert item.text_ko in audit_c_research_note_text

    def test_every_item_anchor_exists_in_research_note(
        self, audit_c_research_note_text: str
    ) -> None:
        entry = get_item_bank("AUDIT-C")
        for item in entry.items:
            for label in (item.response_anchors or {}).values():
                assert label in audit_c_research_note_text
            for label in (item.secondary_response_anchors or {}).values():
                assert label in audit_c_research_note_text


class TestAuditCThresholdCaveat:
    """CVR-018 Q4 / ADR-034 decision 1-2: machine-readable caveat, rewritten
    per Q4's five content requirements. Threshold VALUES themselves live in
    `survey_scorer.py::_score_audit_c` (male/unknown>=6, female>=5), not
    this module — checked separately in `test_survey_scoring.py`."""

    def test_caveat_constant_is_nonempty_and_english(self) -> None:
        assert AUDIT_C_THRESHOLD_CAVEAT
        assert "male" in AUDIT_C_THRESHOLD_CAVEAT.lower()

    def test_point_i_adopted_threshold_and_basis(self) -> None:
        """(i) adopted threshold + basis: male>=6/female>=5, KNHANES/Lee JH
        2018, corroborated by Kwon 2013."""
        assert "6" in AUDIT_C_THRESHOLD_CAVEAT
        assert "5" in AUDIT_C_THRESHOLD_CAVEAT
        assert "Lee JH" in AUDIT_C_THRESHOLD_CAVEAT
        assert "KNHANES" in AUDIT_C_THRESHOLD_CAVEAT
        assert "Kwon" in AUDIT_C_THRESHOLD_CAVEAT

    def test_point_ii_non_adopted_alternatives_with_explicit_reasons(self) -> None:
        """(ii) Seong 2009 and Lee BW 2000 considered and NOT adopted, with
        the explicit reason (not merely 'a different number')."""
        assert "Seong" in AUDIT_C_THRESHOLD_CAVEAT
        assert "Lee BW" in AUDIT_C_THRESHOLD_CAVEAT
        assert "NOT adopted" in AUDIT_C_THRESHOLD_CAVEAT
        assert "female arm" in AUDIT_C_THRESHOLD_CAVEAT
        assert "case-control" in AUDIT_C_THRESHOLD_CAVEAT

    def test_point_iii_international_cutoff_as_metadata(self) -> None:
        """(iii) international cutoff (Bush et al. 1998, male/unknown>=4,
        female>=3) retained as non-action-driving reference metadata,
        cited by name."""
        assert "Bush" in AUDIT_C_THRESHOLD_CAVEAT
        assert "1998" in AUDIT_C_THRESHOLD_CAVEAT
        assert "non-action-driving" in AUDIT_C_THRESHOLD_CAVEAT
        assert "clinician_review" in AUDIT_C_THRESHOLD_CAVEAT

    def test_point_iv_residual_translation_identity_caveat(self) -> None:
        """(iv) no study reproduces its own item-text appendix; byte-
        identity to whichever item text ships is unconfirmed either way."""
        assert "unconfirmed" in AUDIT_C_THRESHOLD_CAVEAT.lower()
        assert "item-text appendix" in AUDIT_C_THRESHOLD_CAVEAT

    def test_point_v_criterion_circularity_disclosure(self) -> None:
        """(v) same-instrument criterion-circularity limitation, disclosed
        not smoothed over."""
        assert "circularity" in AUDIT_C_THRESHOLD_CAVEAT.lower()


class TestGad7BandCaveat:
    """CVR-016 binding condition 1 / CVR-017 binding condition 1 / REV-039
    correction D: GAD-7 gets the same structural caveat-field treatment as
    AUDIT-C — band values themselves untouched (survey_scorer.py's own
    byte-frozen territory, not this module's)."""

    def test_caveat_constant_is_nonempty_and_english(self) -> None:
        assert GAD7_BAND_CAVEAT
        assert "Spitzer" in GAD7_BAND_CAVEAT
        assert "2006" in GAD7_BAND_CAVEAT

    def test_caveat_discloses_the_retraction(self) -> None:
        assert "retract" in GAD7_BAND_CAVEAT.lower()
        assert "item_bank_v1_sources.md" in GAD7_BAND_CAVEAT
        assert "2.4" in GAD7_BAND_CAVEAT

    def test_caveat_does_not_claim_a_band_value_change(self) -> None:
        assert "unchanged" in GAD7_BAND_CAVEAT.lower()

    def test_caveat_is_distinct_from_audit_c_caveat(self) -> None:
        assert GAD7_BAND_CAVEAT != AUDIT_C_THRESHOLD_CAVEAT


class TestWHO5StillUnpopulatedInV1:
    def test_who5_is_unpopulated_and_flagged(self) -> None:
        entry = get_item_bank("WHO-5")
        assert entry.populated is False
        assert entry.items == ()
        assert entry.version == "v1"

    def test_who5_provenance_documents_the_sourcing_gap_not_a_placeholder(self) -> None:
        entry = get_item_bank("WHO-5")
        assert "unpopulated-v1" in entry.provenance
        assert "sourcing gap" in entry.provenance

    def test_who5_instruction_is_none_no_fabricated_timeframe(self) -> None:
        assert get_item_bank("WHO-5").instruction_ko is None


class TestNoFabrication:
    """Fabrication-0: every Korean string on every v1 item/anchor/
    instruction must exist verbatim in the sourcing note (not just the
    appendix subset checked above item-by-item — a whole-note substring
    check across all 4 v1 scales). AUDIT-C is v2 as of this mission and is
    checked separately, against its own canonical source
    (`TestAuditCV2NoFabrication` above, `docs/ai/audit_c_korean_research.md`
    — NOT `item_bank_v1_sources.md`, which only documents v1's now-
    superseded AUDIT-C text)."""

    @pytest.mark.parametrize("scale_name", ["PHQ-9", "GAD-7", "PHQ-4"])
    def test_every_populated_item_text_exists_in_sources_note(
        self, scale_name: str, sources_note_text: str
    ) -> None:
        entry = get_item_bank(scale_name)
        for item in entry.items:
            assert item.text_ko in sources_note_text, (
                f"{scale_name} item {item.index} text not found anywhere in "
                "item_bank_v1_sources.md"
            )

    @pytest.mark.parametrize("scale_name", ["PHQ-9", "GAD-7", "PHQ-4"])
    def test_every_populated_item_anchor_exists_in_sources_note(
        self, scale_name: str, sources_note_text: str
    ) -> None:
        entry = get_item_bank(scale_name)
        for item in entry.items:
            for label in (item.response_anchors or {}).values():
                assert label in sources_note_text, (
                    f"{scale_name} item {item.index} anchor {label!r} not found in "
                    "item_bank_v1_sources.md"
                )


class TestGetItemBank:
    def test_unknown_scale_raises_keyerror_loudly(self) -> None:
        with pytest.raises(KeyError, match="No item bank entry"):
            get_item_bank("NOT-A-SCALE")  # type: ignore[arg-type]


# ── v0 provenance — retained, unchanged, for EXP-019 artifact
#    interpretability (item_bank_version="v0" artifacts must stay
#    reconstructable) ─────────────────────────────────────────────────────


class TestV0PopulatedScalesPHQ9AndAuditCRetained:
    def test_phq9_v0_populated_nine_items_range_0_3(self) -> None:
        entry = get_item_bank_v0("PHQ-9")
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

    def test_phq9_v0_item_9_is_the_suicidal_ideation_item(self) -> None:
        entry = get_item_bank_v0("PHQ-9")
        assert "자살" in entry.items[8].text_ko

    def test_audit_c_v0_populated_three_items_range_0_4(self) -> None:
        entry = get_item_bank_v0("AUDIT-C")
        assert entry.populated is True
        assert entry.provenance == CONSTRUCT_LABELS_V0_PROVENANCE
        assert len(entry.items) == 3
        for i, item in enumerate(entry.items, start=1):
            assert item.index == i
            assert item.response_min == 0
            assert item.response_max == 4
            assert item.response_anchors is None
            assert item.text_ko

    def test_phq9_v0_labels_sourced_from_persona_files_not_invented(self) -> None:
        """Cross-check against VP-001's own documented PHQ-9 construct
        labels (docs/ai/personas/VP-001_first_visit_mild.md:81-95) — proves
        this module's v0 text is repo-sourced, not authored fresh here."""
        entry = get_item_bank_v0("PHQ-9")
        labels = [it.text_ko for it in entry.items]
        assert "1. 흥미/즐거움 감소" in labels
        assert "2. 우울감" in labels
        assert "9. 자살/자해 사고" in labels

    def test_audit_c_v0_labels_sourced_from_persona_file_not_invented(self) -> None:
        entry = get_item_bank_v0("AUDIT-C")
        labels = [it.text_ko for it in entry.items]
        assert "1. 음주 빈도" in labels
        assert "2. 1회 음주량" in labels

    def test_v0_and_v1_phq9_item_text_differ(self) -> None:
        """Sanity: v0's abbreviated construct labels and v1's verbatim
        official item text must actually be different strings — otherwise
        "v0 kept for interpretability" would be vacuous."""
        v0_labels = {it.text_ko for it in get_item_bank_v0("PHQ-9").items}
        v1_labels = {it.text_ko for it in get_item_bank("PHQ-9").items}
        assert v0_labels.isdisjoint(v1_labels)


class TestV0UnpopulatedScalesRetained:
    @pytest.mark.parametrize("scale_name", ["GAD-7", "PHQ-4", "WHO-5"])
    def test_v0_unpopulated_scales_have_no_items_and_are_flagged(
        self, scale_name: str
    ) -> None:
        entry = get_item_bank_v0(scale_name)
        assert entry.populated is False
        assert entry.items == ()
        assert entry.provenance == UNPOPULATED_V0_PROVENANCE
        assert entry.version == "v0"


class TestGetItemBankV0:
    def test_unknown_scale_raises_keyerror_loudly(self) -> None:
        with pytest.raises(KeyError, match="No v0 item bank entry"):
            get_item_bank_v0("NOT-A-SCALE")  # type: ignore[arg-type]


class TestMakeEntryPopulatedComputation:
    """`_make_entry`'s `populated` computation, exercised indirectly via a
    hand-built entry (not monkeypatching module state)."""

    def test_wrong_item_count_is_never_populated(self) -> None:
        from src.scoring.item_bank import _make_entry  # noqa: PLC0415 — test-only reach-in

        entry = _make_entry(
            "PHQ-9",
            (ScaleItem(index=1, text_ko="x", response_min=0, response_max=3),),
            CONSTRUCT_LABELS_V0_PROVENANCE,
            "v0",
        )
        assert entry.populated is False

    def test_empty_provenance_is_never_populated(self) -> None:
        from src.scoring.item_bank import _EXPECTED_ITEM_COUNTS, _make_entry  # noqa: PLC0415

        items = tuple(
            ScaleItem(index=i, text_ko=f"item {i}", response_min=0, response_max=4)
            for i in range(1, _EXPECTED_ITEM_COUNTS["AUDIT-C"] + 1)
        )
        entry = _make_entry("AUDIT-C", items, "", "v1")
        assert entry.populated is False

    def test_blank_item_text_is_never_populated(self) -> None:
        from src.scoring.item_bank import _EXPECTED_ITEM_COUNTS, _make_entry  # noqa: PLC0415

        items = tuple(
            ScaleItem(
                index=i, text_ko="" if i == 1 else f"item {i}", response_min=0, response_max=4
            )
            for i in range(1, _EXPECTED_ITEM_COUNTS["AUDIT-C"] + 1)
        )
        entry = _make_entry("AUDIT-C", items, CONSTRUCT_LABELS_V0_PROVENANCE, "v0")
        assert entry.populated is False


def test_item_bank_entry_and_scale_item_are_frozen() -> None:
    entry = get_item_bank("PHQ-9")
    with pytest.raises(Exception):  # noqa: B017, PT011 — dataclasses.FrozenInstanceError
        entry.populated = False  # type: ignore[misc]
    with pytest.raises(Exception):  # noqa: B017, PT011
        entry.items[0].index = 99  # type: ignore[misc]


def test_item_bank_entry_type_is_the_expected_dataclass() -> None:
    assert isinstance(get_item_bank("PHQ-9"), ItemBankEntry)
