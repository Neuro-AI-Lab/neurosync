"""Targeted test for `_major_course_bullets` (D2 / backlog #6, `plan.md` §3
cluster D2, `discussion.md` STATE-2026-07-21f). CVR-026 Finding 3's
docstring claims the MIDDLE change point is picked to avoid missing a
clinically material timepoint, but the old implementation picked
`history[len(history) // 2]` by POSITION -- so a nadir session that is not
at the midpoint index was silently dropped. This test constructs a history
whose true nadir (lowest-CTRS-adjacent / worst-scored session) sits at an
index the positional pick would NOT have selected, and asserts the fixed
selection now surfaces it."""

from __future__ import annotations

from src.schemas.handoff_report import (
    RiskSafetySection,
    SlotOverviewRow,
    SlotOverviewSection,
    StalenessPointer,
)
from src.services.f5_report import (
    _major_course_bullets,
    _qualitative_nadir_index,
    _scale_nadir_index,
)


def _staleness() -> StalenessPointer:
    return StalenessPointer(applicable=False, note="테스트 고정값 — staleness 비적용")


def _a3(min_ctrs_session_index: int | None) -> RiskSafetySection:
    return RiskSafetySection(
        current_session_index=6,
        current_simulated_date="2026-01-06",
        risk_assessment_present=True,
        current_session_has_f3=False,
        staleness_pointer=_staleness(),
        min_ctrs_session_index=min_ctrs_session_index,
        min_ctrs_simulated_date="2026-01-04" if min_ctrs_session_index else None,
        min_ctrs_value=1 if min_ctrs_session_index else None,
    )


def _row(key: str, label: str, change_history: list[str]) -> SlotOverviewRow:
    return SlotOverviewRow(
        key=key,
        label=label,
        collected=True,
        latest_value=change_history[-1],
        source_session_index=6,
        source_simulated_date="2026-01-06",
        change_history=change_history,
        change_history_full=change_history,
    )


def test_qualitative_nadir_not_at_midpoint_index() -> None:
    """5-entry history (S1/S2/S4/S5/S6); midpoint INDEX is 2 (-> S4), but
    the arc's true nadir session is S5 (min_ctrs_session_index=5). The fixed
    selection must surface S5, not the positionally-picked S4."""
    history = [
        "S1: '평온함'",
        "S2: '경미한 불안'",
        "S4: '수면 저하'",
        "S5: '자살사고 표현'",
        "S6: '호전'",
    ]
    # Old buggy behavior would have picked history[5 // 2] == history[2] == S4.
    old_positional_pick = history[len(history) // 2]
    assert old_positional_pick == "S4: '수면 저하'"

    nadir_idx = _qualitative_nadir_index(history, min_ctrs_session_index=5)
    assert history[nadir_idx] == "S5: '자살사고 표현'"
    assert nadir_idx != len(history) // 2


def test_qualitative_nadir_falls_back_to_midpoint_without_ctrs_reference() -> None:
    """No CTRS nadir known anywhere in the arc -> graceful fallback to the
    old positional midpoint, never a crash."""
    history = ["S1: 'a'", "S2: 'b'", "S3: 'c'"]
    assert _qualitative_nadir_index(history, min_ctrs_session_index=None) == 1


def test_scale_nadir_prefers_worse_ctrs_value_over_position() -> None:
    """Scored-dimension (CTRS, lower=worse) branch: the worst (lowest) CTRS
    entry is NOT at the midpoint index."""
    history = [
        "S1: 'CTRS 4/5'",
        "S2: 'CTRS 3/5'",
        "S3: 'CTRS 3/5'",
        "S4: 'CTRS 1/5'",
        "S5: 'CTRS 4/5'",
    ]
    assert history[len(history) // 2] == "S3: 'CTRS 3/5'"
    nadir_idx = _scale_nadir_index(history)
    assert nadir_idx == 3
    assert history[nadir_idx] == "S4: 'CTRS 1/5'"


def test_scale_nadir_prefers_worse_phq9_ratio_over_position() -> None:
    """PHQ-9 (higher-is-worse) scored dimension: the worst (highest ratio)
    entry is NOT at the midpoint index."""
    history = [
        "S1: 'PHQ-9 5/27'",
        "S2: 'PHQ-9 8/27'",
        "S3: 'PHQ-9 10/27'",
        "S4: 'PHQ-9 22/27'",
        "S5: 'PHQ-9 9/27'",
    ]
    assert history[len(history) // 2] == "S3: 'PHQ-9 10/27'"
    nadir_idx = _scale_nadir_index(history)
    assert nadir_idx == 3
    assert history[nadir_idx] == "S4: 'PHQ-9 22/27'"


def test_scale_nadir_returns_none_for_ordinary_qualitative_text() -> None:
    """The common case (no embedded scale score anywhere) must not
    misfire -- callers fall through to the qualitative selection."""
    history = ["S1: '평온함'", "S2: '경미한 불안'", "S3: '호전'"]
    assert _scale_nadir_index(history) is None


def test_major_course_bullets_surfaces_nadir_session_not_midpoint() -> None:
    """End-to-end: `_major_course_bullets` on a `risk_assessment` row whose
    true nadir (S5, matching `a3.min_ctrs_session_index`) is not at the
    positional midpoint -- the rendered bullet must show S5, not S4."""
    history = [
        "S1: '평온함'",
        "S2: '경미한 불안'",
        "S4: '수면 저하'",
        "S5: '자살사고 표현'",
        "S6: '호전'",
    ]
    so = SlotOverviewSection(rows=[_row("risk_assessment", "위험평가", history)])
    a3 = _a3(min_ctrs_session_index=5)

    bullets = _major_course_bullets(so, a3)

    assert len(bullets) == 1
    assert "S5: '자살사고 표현'" in bullets[0]
    assert "S4: '수면 저하'" not in bullets[0]
    assert bullets[0].startswith("위험평가: S1: '평온함' → S5")
    assert bullets[0].endswith("→ S6: '호전'")


def test_major_course_bullets_handles_missing_and_short_rows_gracefully() -> None:
    """Rows absent from the priority list, or with <2 change points, are
    skipped without crashing; `limit` semantics unchanged."""
    so = SlotOverviewSection(
        rows=[
            _row("chief_complaint", "주호소", ["S1: 'a'", "S2: 'b'"]),
        ]
    )
    a3 = _a3(min_ctrs_session_index=None)

    bullets = _major_course_bullets(so, a3, limit=5)

    assert bullets == ["주호소: S1: 'a' → S2: 'b'"]
