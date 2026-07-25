"""Smoke test for DB-F1 fix: load_simulations scale-name alignment with the
0010 (head) questionnaire_results.type CHECK — non-hyphenated 4-scale, no
WHO-5. Offline only; no DB/network access.
"""

from __future__ import annotations

from src.rag.tooling import load_simulations as ls

# The 0010 head CHECK: type IN ('PHQ9','GAD7','AUDITC','PHQ4').
HEAD_CHECK_SCALES = {"PHQ9", "GAD7", "AUDITC", "PHQ4"}


def test_questionnaire_type_map_targets_are_all_within_head_check() -> None:
    """Every mapped DB value must be an allowed 0010 CHECK value."""
    assert set(ls.QUESTIONNAIRE_TYPE_MAP.values()) == HEAD_CHECK_SCALES


def test_questionnaire_type_map_keys_are_hyphenated_source_scales() -> None:
    """Map keys are the hyphenated source scale_name values from *_survey.json."""
    assert set(ls.QUESTIONNAIRE_TYPE_MAP.keys()) == {
        "PHQ-9",
        "GAD-7",
        "AUDIT-C",
        "PHQ-4",
    }


def test_who5_has_no_questionnaire_results_mapping() -> None:
    """WHO-5 is F4-longitudinal-only (no slot in 0010's CHECK) — must stay unmapped."""
    assert "WHO-5" not in ls.QUESTIONNAIRE_TYPE_MAP
    assert "WHO-5" in ls.ALLOWED_SCALES  # still a recognized source scale for F4


def test_allowed_scales_still_covers_every_type_map_key() -> None:
    """The source-format filter (ALLOWED_SCALES) must not drop a mappable scale."""
    assert set(ls.QUESTIONNAIRE_TYPE_MAP.keys()) <= ls.ALLOWED_SCALES
