"""BUG-041 regression test — `_first_last_slope_trend`'s CONFIRMATORY
slope-sign signal (Criterion 0 basis, `src/f4.py`) was reachable but had
NO test in the full suite that would fail if the slope's sign were
inverted.

Filed: `error.md` BUG-041 (qa mutation check, `PLAN-2026-W29-D` step 6,
`ADR-036` item 1). `docs/ai/f4_quick_dev_plan.md`'s own Criterion 0 names
"first-vs-last delta + slope sign" as the disclosed basis for
`scale_series`/`session_ctrs`/`sentiment` `TrendVerdict`s
(`_first_last_slope_trend`'s own docstring, `src/f4.py:161-181`) — the
slope is the CONFIRMATORY signal used whenever `delta == 0` (a flat
first-vs-last framing a real drift the slope can still see, per rule 2 of
that docstring).

Mutation check performed 2026-07-13 (qa, gate on commit `75472ee`):
negating `slope = float(np.polyfit(xs, ys, 1)[0])` to
`slope = -float(np.polyfit(xs, ys, 1)[0])` survived the FULL 1665-test
suite (`uv run pytest -q tests/` — 1665 passed even with the mutation
live). `TestFirstLastSlopeTrend.test_delta_zero_falls_back_to_slope_sign`
(`tests/test_f4.py`) exists but its own assertion
(`assert direction in ("unchanged", "worsened", "improved")`) accepts all
three outcomes — it does not pin which one is correct.
`test_sign_disagreement_is_noted_not_hidden` is similarly non-
discriminating (`assert any(...) or True` is a tautology, always true
regardless of the checked condition).

This test closes that gap: a `delta == 0`, asymmetric-interior-bump
fixture where the correct slope sign is unambiguously positive (and the
mutated/negated slope would flip the verdict to "worsened").
"""

from __future__ import annotations

from src.f4 import _first_last_slope_trend


def test_delta_zero_slope_sign_pins_correct_direction_bug_041() -> None:
    """first == last (delta == 0), asymmetric interior bump before the
    midpoint pulls the least-squares slope unambiguously POSITIVE
    (verified by hand: xs=[1,2,3,4], ys=[5,5,7,5] -> slope=+0.2). Under
    `higher_is_better=True` this must read "improved" — a slope-sign
    inversion (BUG-041's mutant) flips it to "worsened", which this
    assertion catches.
    """
    points = [(1, 5.0), (2, 5.0), (3, 7.0), (4, 5.0)]
    direction, evidence = _first_last_slope_trend(points, higher_is_better=True, label="x")

    assert direction == "improved", (
        "delta=0 with a positive-slope interior bump must read 'improved' under "
        "higher_is_better=True -- if this reads 'worsened', the slope-sign "
        "computation has regressed (BUG-041)."
    )
    assert any("linear slope across" in e and "+0.2/session" in e for e in evidence), (
        "the confirmatory-slope evidence string must report a POSITIVE slope (+0.2/session) "
        "for this fixture -- BUG-041 regression if it reports negative."
    )


def test_delta_zero_slope_sign_pins_correct_direction_mirrored_bug_041() -> None:
    """Mirror fixture (dip instead of bump) — slope unambiguously NEGATIVE.
    Confirms the sign is genuinely read, not a fixed constant."""
    points = [(1, 5.0), (2, 5.0), (3, 3.0), (4, 5.0)]
    direction, evidence = _first_last_slope_trend(points, higher_is_better=True, label="x")

    assert direction == "worsened", (
        "delta=0 with a negative-slope interior dip must read 'worsened' under "
        "higher_is_better=True -- BUG-041 regression if it reads 'improved'."
    )
    assert any("linear slope across" in e and "-0.2/session" in e for e in evidence)
