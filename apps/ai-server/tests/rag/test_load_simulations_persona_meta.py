"""`PERSONA_META` completeness — PLAN-2026-W28-Q W6 (plan §9's "PERSONA_META
and f1.py:1815 help text need new-ID entries at implementation time").

Deterministic, run-free (no DB/embedding-network call, no `main()`
invocation) — imports the module and reads its module-level dicts / helper
functions only. Does NOT load anything into the DB.
"""

from __future__ import annotations

from src.rag.tooling.load_simulations import PERSONA_DIR, PERSONA_META, _persona_demographics

ALL_SEVEN_PERSONAS = ("VP-001", "VP-002", "VP-003", "VP-004", "VP-010", "VP-011", "VP-012")
NEW_PERSONAS = ("VP-010", "VP-011", "VP-012")


class TestPersonaMetaCompleteness:
    def test_all_seven_personas_have_a_persona_meta_entry(self) -> None:
        for persona_id in ALL_SEVEN_PERSONAS:
            assert persona_id in PERSONA_META, f"{persona_id} missing from PERSONA_META"

    def test_persona_meta_entries_carry_the_same_shape_as_the_original_four(self) -> None:
        expected_keys = {"class", "suicidal"}
        for persona_id in ALL_SEVEN_PERSONAS:
            entry = PERSONA_META[persona_id]
            assert set(entry) == expected_keys, (
                f"{persona_id} PERSONA_META shape drift: {set(entry)} != {expected_keys}"
            )
            assert isinstance(entry["class"], str) and entry["class"]
            assert isinstance(entry["suicidal"], bool)

    def test_new_personas_are_crisis_forward_excluded_suicidal_false(self) -> None:
        """VP-010/011/012 are all crisis-forward Excluded by binding design
        (plan §9 table) — SI/self-harm none/negative in every ground-truth
        section of all three persona files."""
        for persona_id in NEW_PERSONAS:
            assert PERSONA_META[persona_id]["suicidal"] is False

    def test_vp012_class_is_addiction(self) -> None:
        """VP-012's stated presenting concern is alcohol (§2) — the
        clinical focus, per its own §2 comorbidity note."""
        assert PERSONA_META["VP-012"]["class"] == "ADDICTION"

    def test_vp010_and_vp011_class_is_depression(self) -> None:
        assert PERSONA_META["VP-010"]["class"] == "DEPRESSION"
        assert PERSONA_META["VP-011"]["class"] == "DEPRESSION"

    def test_persona_meta_class_values_are_from_the_rag_3_way_taxonomy(self) -> None:
        allowed = {"ANXIETY", "DEPRESSION", "ADDICTION"}
        for persona_id in ALL_SEVEN_PERSONAS:
            assert PERSONA_META[persona_id]["class"] in allowed


class TestPersonaFilesResolvableByGlob:
    """`_persona_demographics`'s `PERSONA_DIR.glob(f"{persona_id}_*.md")`
    pattern already generalizes to any VP-0* id (no code widening needed —
    verified here, not assumed) — this test proves the three new files
    actually resolve and their demographics are parseable."""

    def test_all_seven_persona_ids_resolve_to_exactly_one_md_file(self) -> None:
        for persona_id in ALL_SEVEN_PERSONAS:
            matches = sorted(PERSONA_DIR.glob(f"{persona_id}_*.md"))
            assert len(matches) == 1, (
                f"{persona_id}: expected exactly 1 match, got {matches}"
            )

    def test_new_persona_demographics_parse_without_raising(self) -> None:
        expected_name_prefix = {
            "VP-010": "강태민",
            "VP-011": "한소영",
            "VP-012": "정우식",
        }
        for persona_id, expected_name in expected_name_prefix.items():
            demo = _persona_demographics(persona_id)
            assert demo["name"] == expected_name
            assert isinstance(demo["birth_year"], int)
            assert demo["gender"] in ("남성", "여성")
