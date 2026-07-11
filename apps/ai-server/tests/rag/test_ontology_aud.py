"""W6 AUD ontology DRAFT — `alcohol-use-disorder` entry + per-entry source
widening (PLAN-2026-W28-Q W6, plan §9 table, `CVR-002` Finding 6).

Deterministic, run-free (no DB/LLM call) — importable and assertable in
default CI. This suite does NOT certify clinical content (the Korean name
is an explicit DRAFT pending clinical-validator sign-off, see the code
comment at `src.rag.ontology.DISEASES["alcohol-use-disorder"]`) and does
NOT run `load_ontology.py` — the DB load is deferred pending CV sign-off.
"""

from __future__ import annotations

from src.rag.ontology import (
    BUCKETS,
    DISEASE_SOURCE,
    DISEASE_SYMPTOMS,
    DISEASES,
    disease_source,
)

AUD_SLUG = "alcohol-use-disorder"


class TestDiseasesCountAndShape:
    """26 -> 27 (Ada 26 + 1 team-authored draft)."""

    def test_diseases_count_is_27(self) -> None:
        assert len(DISEASES) == 27

    def test_aud_slug_present(self) -> None:
        assert AUD_SLUG in DISEASES

    def test_aud_entry_is_still_a_5_tuple(self) -> None:
        """Backward-compat: DISEASES values stay a 5-tuple shape so
        `questionnaire_mapping.py`'s positional unpacking
        (`for slug, (name, name_ko, kcd, cls, desc) in DISEASES.items()`)
        is untouched by this addition — zero code change there."""
        entry = DISEASES[AUD_SLUG]
        assert len(entry) == 5

    def test_aud_entry_fields_match_plan_9_table(self) -> None:
        name_en, name_ko, kcd, classification, description = DISEASES[AUD_SLUG]
        assert name_en == "Alcohol Use Disorder"
        assert name_ko == "알코올 사용장애(의존)"
        assert kcd == "F10.2"
        assert classification == "substance"
        assert isinstance(description, str) and description

    def test_aud_name_ko_does_not_collide_with_any_existing_disease(self) -> None:
        """`questionnaire_mapping.py`'s `_NAME_KO_TO_CLASSIFICATION` reverse
        lookup asserts name_ko uniqueness at import time — this test makes
        that invariant explicit for the new entry specifically."""
        name_ko_values = [entry[1] for entry in DISEASES.values()]
        assert name_ko_values.count("알코올 사용장애(의존)") == 1


class TestDiseaseSource:
    """PLAN-2026-W28-Q W6, plan §9 "Provenance defect found" — per-entry
    source, backward-compatible widening (companion dict, not a tuple
    shape change)."""

    def test_aud_slug_is_team_sourced(self) -> None:
        assert DISEASE_SOURCE[AUD_SLUG] == "team"
        assert disease_source(AUD_SLUG) == "team"

    def test_original_26_default_to_ada(self) -> None:
        for slug in DISEASES:
            if slug == AUD_SLUG:
                continue
            assert disease_source(slug) == "ada", (
                f"{slug!r} must default to 'ada' provenance (unchanged from "
                "before the W6 widening)"
            )

    def test_unregistered_slug_defaults_to_ada(self) -> None:
        assert disease_source("not-a-real-slug") == "ada"

    def test_disease_source_keys_are_a_subset_of_diseases(self) -> None:
        """DISEASE_SOURCE only needs to list non-'ada' exceptions."""
        assert set(DISEASE_SOURCE) <= set(DISEASES)


class TestAudDiseaseSymptoms:
    """CVR-002 Finding 6: prefer craving/perceived_loss_of_control over
    acute intoxication/withdrawal flags. Both flags already exist in the
    vocabulary (reused, not invented)."""

    def test_aud_symptoms_key_present(self) -> None:
        assert AUD_SLUG in DISEASE_SYMPTOMS

    def test_aud_uses_craving_and_perceived_loss_of_control(self) -> None:
        flags = DISEASE_SYMPTOMS[AUD_SLUG]
        assert "craving" in flags
        assert "perceived_loss_of_control" in flags

    def test_aud_reused_flags_already_exist_in_the_symptom_vocabulary(self) -> None:
        """Both flags predate this entry (they're reused, per option (a) —
        "reuse the closest existing flags", not newly invented)."""
        assert BUCKETS.get("craving") == "symptom"
        assert BUCKETS.get("perceived_loss_of_control") == "symptom"

    def test_aud_does_not_reuse_acute_intoxication_or_withdrawal_specific_flags(self) -> None:
        """Deliberately excludes flags that belong to the ACUTE
        intoxication/withdrawal presentations (already owned by
        alcohol-intoxication/alcohol-withdrawal), keeping the chronic-AUD
        entry distinct from those two."""
        flags = set(DISEASE_SYMPTOMS[AUD_SLUG])
        assert "withdrawal" not in flags
        assert "tolerance" not in flags
        assert flags == {"craving", "perceived_loss_of_control"}


class TestNoOntologyRegressionOnExistingSubstanceEntries:
    """Sanity: adding the AUD draft must not disturb the two pre-existing
    substance-classified diseases."""

    def test_alcohol_intoxication_and_withdrawal_unchanged_classification(self) -> None:
        assert DISEASES["alcohol-intoxication"][3] == "substance"
        assert DISEASES["alcohol-withdrawal"][3] == "substance"

    def test_three_substance_diseases_now_shipped(self) -> None:
        substance_slugs = {slug for slug, e in DISEASES.items() if e[3] == "substance"}
        assert substance_slugs == {
            "alcohol-intoxication",
            "alcohol-withdrawal",
            "alcohol-use-disorder",
        }
