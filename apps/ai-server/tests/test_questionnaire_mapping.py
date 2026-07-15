"""Disease<->questionnaire static mapping — smoke tests + the structural
offline check, PLAN-2026-W28-Q W5 (plan §3 "Disease questionnaire linkage"
row, answer #5a).

Structural offline check (plan §3's own wording: "Structural offline check
(every shipped disease resolves into SUPPORTED_SCALES, deterministic)
before the field ships"): every disease `rag.ontology.DISEASES` currently
ships must resolve, through `CLASSIFICATION_TO_SCALE`, into either a
`SUPPORTED_SCALES` member or the explicit none-category — never an
unmapped classification silently defaulting through the module's
defensive fallback. Deterministic, run-free (no DB/LLM call) — importable
and assertable in default CI.

Zero prompt-file changes; this file makes no reference to any prompt/
certification artifact.
"""

from __future__ import annotations

from src.rag.ontology import DISEASES
from src.rag.questionnaire_mapping import (
    CLASSIFICATION_TO_CAVEAT,
    CLASSIFICATION_TO_SCALE,
    resolve_questionnaire_caveat_for_classification,
    resolve_questionnaire_caveat_for_disease_name_ko,
    resolve_questionnaire_caveat_for_disease_slug,
    resolve_questionnaire_for_classification,
    resolve_questionnaire_for_disease_name_ko,
    resolve_questionnaire_for_disease_slug,
)
from src.scoring.survey_scorer import SUPPORTED_SCALES

# CVR-001 weak-point register item 7's named no-coverage territory — every
# classification bucketing one of these disease slugs must map to None
# (never a forced best-effort fit).
_NO_FORCED_MISMATCH_SLUGS = {
    "obsessive-compulsive-disorder": "ocd",
    "post-traumatic-stress-disorder": "trauma",
    "schizophrenia": "psychotic",
    "attention-deficit-hyperactivity-disorder": "neurodevelopmental",
}


class TestStructuralOfflineCheck:
    """Plan §3's "every shipped disease resolves" check — the deliverable
    item 3 structural check. Must run in default CI (no marker/skip)."""

    def test_every_disease_classification_is_an_explicit_mapping_key(self) -> None:
        """No `DISEASES` classification is missing from
        `CLASSIFICATION_TO_SCALE` — a missing key would silently resolve to
        `None` via the defensive fallback, masking a genuine coverage gap
        rather than recording a documented, reviewed no-questionnaire
        decision. This is a STRICTER check than "resolves to None or a
        valid scale": it requires explicit membership."""
        shipped_classifications = {entry[3] for entry in DISEASES.values()}
        missing = shipped_classifications - set(CLASSIFICATION_TO_SCALE)
        assert missing == set(), (
            f"classification(s) with no explicit CLASSIFICATION_TO_SCALE "
            f"entry: {missing} — every DISEASES classification must be a "
            "reviewed key (scale or explicit None), never fall through the "
            "module's defensive unmapped-classification fallback"
        )

    def test_every_shipped_disease_resolves_into_supported_scales_or_none(self) -> None:
        """Every disease slug currently in `DISEASES` resolves, via its
        classification, into a `SUPPORTED_SCALES` member or `None` — no
        unmapped classification, no scale outside the set."""
        for slug, entry in DISEASES.items():
            classification = entry[3]
            resolved = resolve_questionnaire_for_disease_slug(slug)
            assert resolved is None or resolved in SUPPORTED_SCALES, (
                f"{slug!r} (classification={classification!r}) resolved to "
                f"{resolved!r}, not None or a member of SUPPORTED_SCALES "
                f"{sorted(SUPPORTED_SCALES)}"
            )

    def test_no_scale_outside_supported_scales_appears_anywhere_in_the_table(self) -> None:
        for classification, scale in CLASSIFICATION_TO_SCALE.items():
            assert scale is None or scale in SUPPORTED_SCALES, (
                f"CLASSIFICATION_TO_SCALE[{classification!r}] = {scale!r} "
                f"is outside SUPPORTED_SCALES {sorted(SUPPORTED_SCALES)}"
            )

    def test_no_forced_mismatch_named_classifications_map_to_none(self) -> None:
        """CVR-001 weak-point register item 7's named no-coverage
        territory (OCD/PTSD/psychosis/ADHD) must resolve to None, not a
        forced best-effort scale — the binding rule this module's docstring
        and per-row rationale comments implement."""
        for slug, expected_classification in _NO_FORCED_MISMATCH_SLUGS.items():
            assert slug in DISEASES, f"fixture drift: {slug!r} no longer in DISEASES"
            actual_classification = DISEASES[slug][3]
            assert actual_classification == expected_classification, (
                f"fixture drift: {slug!r} classification changed from "
                f"{expected_classification!r} to {actual_classification!r}"
            )
            assert resolve_questionnaire_for_disease_slug(slug) is None, (
                f"{slug!r} (no-forced-mismatch territory) must resolve to "
                "None, never a forced scale"
            )

    def test_substance_classification_maps_to_audit_c(self) -> None:
        """Deliverable item 1: the `substance` classification -> AUDIT-C row
        must exist now, so the W6 AUD ontology entry (`alcohol-use-disorder`,
        also classified `substance`) slots in with zero code change."""
        assert CLASSIFICATION_TO_SCALE["substance"] == "AUDIT-C"
        assert "AUDIT-C" in SUPPORTED_SCALES
        # Both current substance-classified diseases resolve to AUDIT-C today.
        for slug, entry in DISEASES.items():
            if entry[3] == "substance":
                assert resolve_questionnaire_for_disease_slug(slug) == "AUDIT-C"

    def test_w6_forward_compat_hypothetical_aud_entry_needs_zero_code_change(self) -> None:
        """Classification-level check, independent of whether the row
        exists yet: proves the classification-keyed design resolves
        'substance' correctly regardless of DISEASES' current membership."""
        assert resolve_questionnaire_for_classification("substance") == "AUDIT-C"

    def test_w6_aud_entry_now_shipped_resolves_to_audit_c_with_zero_code_change(self) -> None:
        """W6 (PLAN-2026-W28-Q, plan §9): `ontology.py`'s DISEASES gained
        the real `alcohol-use-disorder` DRAFT entry (developer, this
        mission) — this module and its tests required NO edit for it to
        resolve; the classification-keyed design (not slug-keyed) is what
        makes that true. DISEASES now ships 27 diseases (26 Ada + 1
        team-authored draft)."""
        assert len(DISEASES) == 27
        assert "alcohol-use-disorder" in DISEASES
        assert DISEASES["alcohol-use-disorder"][3] == "substance"
        assert resolve_questionnaire_for_disease_slug("alcohol-use-disorder") == "AUDIT-C"
        assert resolve_questionnaire_caveat_for_disease_slug("alcohol-use-disorder") == (
            CLASSIFICATION_TO_CAVEAT["substance"]
        )
        # Structural check now covers all 3 substance-classified diseases.
        substance_slugs = {slug for slug, e in DISEASES.items() if e[3] == "substance"}
        assert len(substance_slugs) == 3
        for slug in substance_slugs:
            assert resolve_questionnaire_for_disease_slug(slug) == "AUDIT-C"


class TestClassificationLookup:
    def test_mood_maps_to_phq9(self) -> None:
        assert resolve_questionnaire_for_classification("mood") == "PHQ-9"

    def test_anxiety_maps_to_gad7(self) -> None:
        assert resolve_questionnaire_for_classification("anxiety") == "GAD-7"

    def test_unrecognized_classification_returns_none_not_raise(self) -> None:
        assert resolve_questionnaire_for_classification("not-a-real-classification") is None


class TestDiseaseNameKoLookup:
    def test_real_ontology_name_resolves(self) -> None:
        # "우울 삽화(우울증)" == DISEASES["depressive-episode"][1] (mood -> PHQ-9)
        assert resolve_questionnaire_for_disease_name_ko("우울 삽화(우울증)") == "PHQ-9"

    def test_real_ontology_name_no_coverage_resolves_to_none(self) -> None:
        # "조현병" == DISEASES["schizophrenia"][1] (psychotic -> None)
        assert resolve_questionnaire_for_disease_name_ko("조현병") is None

    def test_unrecognized_name_returns_none_not_raise(self) -> None:
        """Synthetic test markers / DB-drift names (e.g.
        tests/test_hpi_isolation.py's leak marker, or
        tests/test_f2_pipeline.py's non-ontology '불안장애' stub) resolve to
        None gracefully rather than raising."""
        assert resolve_questionnaire_for_disease_name_ko("ZZZ_NOT_A_REAL_DISEASE") is None


class TestDiseaseSlugLookup:
    def test_known_slug_resolves(self) -> None:
        assert resolve_questionnaire_for_disease_slug("generalized-anxiety-disorder") == "GAD-7"

    def test_unknown_slug_returns_none_not_raise(self) -> None:
        assert resolve_questionnaire_for_disease_slug("not-a-real-slug") is None


class TestClassificationToCaveat:
    """CVR-003 Findings 1/3 (W5 addendum, `discussion.md` "CVR-003 folded"
    disposition, 2026-07-11) — the per-row caveat column."""

    def test_key_set_matches_classification_to_scale_exactly(self) -> None:
        """The module-level fail-fast assertion already enforces this at
        import time (this test would never even collect if it failed) —
        this test documents and locks in the invariant explicitly."""
        assert set(CLASSIFICATION_TO_CAVEAT) == set(CLASSIFICATION_TO_SCALE)

    def test_mood_caveat_discloses_mania_blind_spot(self) -> None:
        caveat = CLASSIFICATION_TO_CAVEAT["mood"]
        assert caveat is not None
        assert "manic" in caveat or "mania" in caveat.lower()
        assert "PHQ-9" in caveat

    def test_substance_caveat_discloses_consumption_vs_dependence_scope(self) -> None:
        caveat = CLASSIFICATION_TO_CAVEAT["substance"]
        assert caveat is not None
        assert "AUDIT-C" in caveat
        assert "dependence" in caveat.lower()

    def test_classifications_with_no_disclosed_caveat_are_explicit_none(self) -> None:
        for classification in ("anxiety", "ocd", "trauma", "psychotic", "personality",
                                "neurodevelopmental", "somatic", "neurocognitive"):
            assert CLASSIFICATION_TO_CAVEAT[classification] is None

    def test_resolve_caveat_for_classification_mood(self) -> None:
        assert resolve_questionnaire_caveat_for_classification("mood") == (
            CLASSIFICATION_TO_CAVEAT["mood"]
        )

    def test_resolve_caveat_for_classification_no_caveat_returns_none(self) -> None:
        assert resolve_questionnaire_caveat_for_classification("anxiety") is None

    def test_resolve_caveat_for_unrecognized_classification_returns_none_not_raise(self) -> None:
        assert resolve_questionnaire_caveat_for_classification("not-a-real-classification") is None

    def test_resolve_caveat_for_disease_name_ko_real_mood_disease(self) -> None:
        # "우울 삽화(우울증)" == DISEASES["depressive-episode"][1] (mood)
        caveat = resolve_questionnaire_caveat_for_disease_name_ko("우울 삽화(우울증)")
        assert caveat == CLASSIFICATION_TO_CAVEAT["mood"]

    def test_resolve_caveat_for_disease_name_ko_no_coverage_resolves_to_none(self) -> None:
        # "조현병" == DISEASES["schizophrenia"][1] (psychotic -> None scale, None caveat)
        assert resolve_questionnaire_caveat_for_disease_name_ko("조현병") is None

    def test_resolve_caveat_for_disease_name_ko_unrecognized_name_returns_none(self) -> None:
        assert resolve_questionnaire_caveat_for_disease_name_ko("ZZZ_NOT_A_REAL_DISEASE") is None

    def test_resolve_caveat_for_disease_slug_known_mood_slug(self) -> None:
        caveat = resolve_questionnaire_caveat_for_disease_slug("depressive-episode")
        assert caveat == CLASSIFICATION_TO_CAVEAT["mood"]

    def test_resolve_caveat_for_disease_slug_unknown_slug_returns_none(self) -> None:
        assert resolve_questionnaire_caveat_for_disease_slug("not-a-real-slug") is None

    def test_every_shipped_disease_caveat_resolves_without_raising(self) -> None:
        """Structural offline check, mirroring
        TestStructuralOfflineCheck's scale-side check: no shipped disease
        slug crashes the caveat resolver."""
        for slug in DISEASES:
            caveat = resolve_questionnaire_caveat_for_disease_slug(slug)
            assert caveat is None or isinstance(caveat, str)
