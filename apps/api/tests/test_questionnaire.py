"""Unit tests for PHQ-9 / GAD-7 scoring (no DB). FR-006/007."""

from __future__ import annotations

import pytest

from src.services.questionnaire import (
    QuestionnaireError,
    score_questionnaire,
    severity_for,
    validate_answers,
)

# ────────── PHQ-9 severity bands ──────────


@pytest.mark.parametrize(
    ("score", "expected"),
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
def test_phq9_severity_bands(score: int, expected: str) -> None:
    assert severity_for("PHQ9", score) == expected


# ────────── GAD-7 severity bands ──────────


@pytest.mark.parametrize(
    ("score", "expected"),
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
def test_gad7_severity_bands(score: int, expected: str) -> None:
    assert severity_for("GAD7", score) == expected


# ────────── score_questionnaire totals ──────────


def test_phq9_full_score() -> None:
    total, severity = score_questionnaire("PHQ9", [3, 3, 3, 3, 3, 3, 3, 3, 3])
    assert total == 27
    assert severity == "severe"


def test_gad7_zero_score() -> None:
    total, severity = score_questionnaire("GAD7", [0, 0, 0, 0, 0, 0, 0])
    assert total == 0
    assert severity == "minimal"


def test_phq9_mixed_score() -> None:
    total, severity = score_questionnaire("PHQ9", [0, 1, 2, 1, 3, 0, 1, 2, 1])
    assert total == 11
    assert severity == "moderate"


# ────────── validation ──────────


def test_wrong_item_count_rejected() -> None:
    with pytest.raises(QuestionnaireError) as exc:
        validate_answers("PHQ9", [0, 1, 2])
    assert exc.value.code == "ANSWER_COUNT_MISMATCH"


def test_gad7_with_phq9_count_rejected() -> None:
    with pytest.raises(QuestionnaireError) as exc:
        validate_answers("GAD7", [0] * 9)
    assert exc.value.code == "ANSWER_COUNT_MISMATCH"


def test_out_of_range_answer_rejected() -> None:
    with pytest.raises(QuestionnaireError) as exc:
        validate_answers("PHQ9", [0, 1, 2, 1, 4, 0, 1, 2, 1])
    assert exc.value.code == "ANSWER_OUT_OF_RANGE"


def test_negative_answer_rejected() -> None:
    with pytest.raises(QuestionnaireError) as exc:
        validate_answers("GAD7", [0, -1, 2, 1, 3, 0, 1])
    assert exc.value.code == "ANSWER_OUT_OF_RANGE"


def test_unknown_type_rejected() -> None:
    with pytest.raises(QuestionnaireError) as exc:
        validate_answers("BDI", [0, 1, 2])
    assert exc.value.code == "INVALID_QUESTIONNAIRE_TYPE"
