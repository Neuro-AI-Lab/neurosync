"""PHQ-9 / GAD-7 scoring + persistence (FR-006/007).

Pure scoring functions (no DB) keep severity thresholds unit-testable. PRD §5.1:
severity is clinician-reference only. Standard cutoffs:
- PHQ-9 (9 items, 0-27): 0-4 minimal / 5-9 mild / 10-14 moderate /
  15-19 moderately_severe / 20-27 severe.
- GAD-7 (7 items, 0-21): 0-4 minimal / 5-9 mild / 10-14 moderate / 15-21 severe.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.questionnaire import QuestionnaireResult

# Item count per instrument; each answer is a 0-3 Likert integer.
ITEM_COUNT: dict[str, int] = {"PHQ9": 9, "GAD7": 7}
MAX_ANSWER = 3


class QuestionnaireError(ValueError):
    """Raised on a malformed questionnaire submission (caller maps to 422)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_answers(qtype: str, answers: list[int]) -> None:
    expected = ITEM_COUNT.get(qtype)
    if expected is None:
        raise QuestionnaireError(
            "INVALID_QUESTIONNAIRE_TYPE", f"알 수 없는 문진 유형이에요: {qtype}"
        )
    if len(answers) != expected:
        raise QuestionnaireError(
            "ANSWER_COUNT_MISMATCH",
            f"{qtype}는 {expected}문항이어야 해요 (받은 값: {len(answers)}개).",
        )
    for a in answers:
        # `bool` is an `int` subclass — reject it so a JSON `true` can't score as 1.
        if isinstance(a, bool) or not isinstance(a, int) or a < 0 or a > MAX_ANSWER:
            raise QuestionnaireError(
                "ANSWER_OUT_OF_RANGE",
                f"각 응답은 0~{MAX_ANSWER} 사이여야 해요.",
            )


def severity_for(qtype: str, score: int) -> str:
    if qtype == "PHQ9":
        if score <= 4:
            return "minimal"
        if score <= 9:
            return "mild"
        if score <= 14:
            return "moderate"
        if score <= 19:
            return "moderately_severe"
        return "severe"
    # GAD7
    if score <= 4:
        return "minimal"
    if score <= 9:
        return "mild"
    if score <= 14:
        return "moderate"
    return "severe"


def score_questionnaire(qtype: str, answers: list[int]) -> tuple[int, str]:
    """Validate, sum, and classify. Returns (total_score, severity)."""
    validate_answers(qtype, answers)
    total = sum(answers)
    return total, severity_for(qtype, total)


async def upsert_result(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    qtype: str,
    answers: list[int],
) -> QuestionnaireResult:
    """Score and persist. Re-submission of the same (session, type) overwrites."""
    total, severity = score_questionnaire(qtype, answers)

    existing_row = await db.execute(
        select(QuestionnaireResult).where(
            QuestionnaireResult.session_id == session_id,
            QuestionnaireResult.type == qtype,
        )
    )
    result = existing_row.scalar_one_or_none()
    if result is None:
        result = QuestionnaireResult(
            session_id=session_id,
            type=qtype,
            answers=answers,
            total_score=total,
            severity=severity,
        )
        db.add(result)
    else:
        result.answers = answers
        result.total_score = total
        result.severity = severity
    await db.flush()
    return result
