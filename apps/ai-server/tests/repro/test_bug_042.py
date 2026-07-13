"""BUG-042 regression test — `src/f4.py::_SEVERITY_BAND_RANK`'s per-scale
ordinal severity-band ranking had NO test in the full suite that would
fail if two adjacent bands' ranks were swapped.

Filed: `error.md` BUG-042 (qa mutation check, `PLAN-2026-W29-D` step 6,
`ADR-036` item 1). `_SEVERITY_BAND_RANK` (`src/f4.py:119-125`) is
consumed by `_scale_trend_verdict` to compute the `ordinal band delta`
evidence string and the same-scale >=2-band-jump `NOTABLE` flag (design
doc §7.4/REV-044 Criterion 2 territory) — this is user-facing report text,
not merely an internal intermediate.

Mutation check performed 2026-07-13 (qa, gate on commit `75472ee`):
swapping PHQ-9's `"moderate": 2` and `"moderately_severe": 3` to
`"moderate": 3, "moderately_severe": 2` survived the FULL 1665-test suite
(`uv run pytest -q tests/` — 1665 passed even with the mutation live).
`TestScaleAggregationBasisNotNaivePairwiseThreshold
.test_band_transition_notable_flag_on_two_band_jump` (`tests/test_f4.py`)
exists but only exercises a mild<->severe jump (ranks 1 and 4 in both the
correct and swapped tables — the swap only touches the interior
moderate/moderately_severe pair, so that test cannot distinguish them).

This test closes that gap: (1) a direct ordinal-ordering check on the
table itself, and (2) a `_scale_trend_verdict` fixture whose evidence
string is only correct if `moderate < moderately_severe` in rank.
"""

from __future__ import annotations

from src.f4 import _SEVERITY_BAND_RANK, _scale_trend_verdict
from src.schemas.longitudinal import ScaleSeriesPoint


def test_phq9_band_ranks_are_strictly_ordinal_bug_042() -> None:
    """PHQ-9's 5 bands must rank strictly increasing in the documented
    clinical order: minimal < mild < moderate < moderately_severe < severe.
    A rank swap (BUG-042's mutant) breaks this strict ordering."""
    ranks = _SEVERITY_BAND_RANK["PHQ-9"]
    ordered_bands = ["minimal", "mild", "moderate", "moderately_severe", "severe"]
    ordered_values = [ranks[b] for b in ordered_bands]
    assert ordered_values == sorted(ordered_values), (
        f"PHQ-9 severity-band ranks must be strictly increasing in clinical order, "
        f"got {dict(zip(ordered_bands, ordered_values, strict=True))} -- BUG-042 regression "
        "if 'moderate' and 'moderately_severe' (or any adjacent pair) are swapped."
    )


def test_moderate_to_moderately_severe_transition_is_positive_delta_bug_042() -> None:
    """A same-scale total-score increase that crosses moderate ->
    moderately_severe must report a POSITIVE ordinal band delta (+1) in
    the shipped evidence string -- a rank swap flips this to -1, silently
    mislabeling a worsening transition as an improving one in the report
    text."""
    points = [
        ScaleSeriesPoint(
            session_index=1, simulated_date="2026-01-01", scale_name="PHQ-9",
            administered=True, total_score=13, severity="moderate",
        ),
        ScaleSeriesPoint(
            session_index=2, simulated_date="2026-01-08", scale_name="PHQ-9",
            administered=True, total_score=17, severity="moderately_severe",
        ),
    ]
    tv = _scale_trend_verdict("PHQ-9", points)
    assert any("ordinal band delta +1" in e for e in tv.evidence), (
        "moderate -> moderately_severe must report 'ordinal band delta +1' -- "
        f"BUG-042 regression if evidence shows a negative delta instead. Evidence: {tv.evidence}"
    )
