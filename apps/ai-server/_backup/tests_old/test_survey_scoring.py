"""T1-F3-VER-001/002: Rule-based survey scoring unit tests.

Tests every severity boundary for PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C.
"""

import pytest

from src.scoring.survey_scorer import ScoreResult, score_survey


# ── PHQ-9 (T1-F3-VER-001) ───────────────────────────────────────────


class TestPHQ9:
    """PHQ-9: 9 items, each 0-3, total 0-27."""

    @pytest.mark.parametrize(
        "total, severity",
        [
            (0, "minimal"),
            (4, "minimal"),
            (5, "mild"),
            (9, "mild"),
            (10, "moderate"),
            (14, "moderate"),
            (15, "moderately_severe"),
            (19, "moderately_severe"),
            (20, "severe"),
            (27, "severe"),
        ],
    )
    def test_severity_boundaries(self, total: int, severity: str):
        # Build responses that sum to `total`
        responses = _build_responses(total, n_items=9, max_per_item=3)
        result = score_survey("PHQ-9", responses)
        assert result.severity == severity
        assert result.total_score == total
        assert result.max_score == 27
        assert result.scale_name == "PHQ-9"

    def test_q9_positive_triggers_safety(self):
        """Item 9 (suicidal ideation) >= 1 → critical_item_positive."""
        responses = [0, 0, 0, 0, 0, 0, 0, 0, 1]  # total=1, but Q9=1
        result = score_survey("PHQ-9", responses)
        assert result.critical_item_positive is True
        assert result.recommended_action == "safety_referral"
        assert any(c["flag"] == "suicidal_ideation" for c in result.critical_items)

    def test_q9_zero_no_flag(self):
        responses = [1, 1, 1, 1, 1, 0, 0, 0, 0]  # total=5, Q9=0
        result = score_survey("PHQ-9", responses)
        assert result.critical_item_positive is False

    def test_wrong_item_count(self):
        with pytest.raises(ValueError, match="9 responses"):
            score_survey("PHQ-9", [0, 1, 2])

    def test_out_of_range(self):
        with pytest.raises(ValueError, match="out of range"):
            score_survey("PHQ-9", [0, 0, 0, 0, 0, 0, 0, 0, 4])


# ── GAD-7 (T1-F3-VER-002) ───────────────────────────────────────────


class TestGAD7:
    """GAD-7: 7 items, each 0-3, total 0-21."""

    @pytest.mark.parametrize(
        "total, severity",
        [
            (0, "minimal"),
            (4, "minimal"),
            (5, "mild"),
            (9, "mild"),
            (10, "moderate"),
            (14, "moderate"),
            (15, "severe"),
            (21, "severe"),
        ],
    )
    def test_severity_boundaries(self, total: int, severity: str):
        responses = _build_responses(total, n_items=7, max_per_item=3)
        result = score_survey("GAD-7", responses)
        assert result.severity == severity
        assert result.total_score == total
        assert result.max_score == 21

    def test_no_critical_items(self):
        result = score_survey("GAD-7", [3, 3, 3, 3, 3, 3, 3])
        assert result.critical_item_positive is False

    def test_wrong_item_count(self):
        with pytest.raises(ValueError, match="7 responses"):
            score_survey("GAD-7", [0, 1])


# ── PHQ-4 ────────────────────────────────────────────────────────────


class TestPHQ4:
    @pytest.mark.parametrize(
        "total, severity",
        [(0, "normal"), (2, "normal"), (3, "mild"), (5, "mild"),
         (6, "moderate"), (8, "moderate"), (9, "severe"), (12, "severe")],
    )
    def test_severity_boundaries(self, total: int, severity: str):
        responses = _build_responses(total, n_items=4, max_per_item=3)
        result = score_survey("PHQ-4", responses)
        assert result.severity == severity

    def test_subscales(self):
        result = score_survey("PHQ-4", [2, 3, 1, 0])
        assert result.subscale_scores["anxiety"] == 5   # Q1+Q2
        assert result.subscale_scores["depression"] == 1  # Q3+Q4


# ── WHO-5 ────────────────────────────────────────────────────────────


class TestWHO5:
    def test_low_wellbeing(self):
        result = score_survey("WHO-5", [2, 2, 3, 3, 3])  # raw=13
        assert result.severity == "low_wellbeing"
        assert result.subscale_scores["percentage"] == 52

    def test_adequate_wellbeing(self):
        result = score_survey("WHO-5", [3, 3, 3, 3, 3])  # raw=15
        assert result.severity == "adequate_wellbeing"
        assert result.subscale_scores["percentage"] == 60

    def test_max_score(self):
        result = score_survey("WHO-5", [5, 5, 5, 5, 5])  # raw=25
        assert result.total_score == 25
        assert result.subscale_scores["percentage"] == 100


# ── AUDIT-C ──────────────────────────────────────────────────────────


class TestAUDITC:
    def test_male_threshold(self):
        result = score_survey("AUDIT-C", [1, 1, 1], patient_sex="male")
        assert result.severity == "low_risk"  # total=3 < threshold=4
        result2 = score_survey("AUDIT-C", [2, 1, 1], patient_sex="male")
        assert result2.severity == "hazardous_drinking"  # total=4 >= 4

    def test_female_threshold(self):
        result = score_survey("AUDIT-C", [1, 1, 0], patient_sex="female")
        assert result.severity == "low_risk"  # total=2 < threshold=3
        result2 = score_survey("AUDIT-C", [1, 1, 1], patient_sex="female")
        assert result2.severity == "hazardous_drinking"  # total=3 >= 3


# ── Invalid scale ────────────────────────────────────────────────────


class TestInvalidScale:
    def test_unsupported_scale(self):
        with pytest.raises(ValueError, match="Unsupported scale"):
            score_survey("INVALID", [1, 2, 3])


# ── Helper ───────────────────────────────────────────────────────────


def _build_responses(total: int, n_items: int, max_per_item: int) -> list[int]:
    """Build a list of `n_items` responses summing to `total`, each <= max_per_item."""
    responses = [0] * n_items
    remaining = total
    for i in range(n_items):
        give = min(remaining, max_per_item)
        responses[i] = give
        remaining -= give
        if remaining == 0:
            break
    assert sum(responses) == total, f"Could not build responses summing to {total}"
    return responses
