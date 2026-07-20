"""표준 척도 채점 + 저장 (FR-006/007, v3 FR-040).

지원 도구 4종 — PHQ-9 / GAD-7 / AUDIT-C / PHQ-4 (v3 FR-040 문항 주입형 문진).

채점 경로:
1. 우선 ai-server `/ai/survey/score`(결정론적 채점기 5종)를 호출한다. AUDIT-C의
   한국 절사점·PHQ-9 9번 critical item 판정 같은 임상 규칙을 그쪽 단일 소스로
   두어, 플랫폼이 규칙을 두 벌 갖지 않게 한다.
2. ai-server 장애 시 아래 로컬 표준 컷오프로 폴백한다. 문진 제출이 AI 서버
   가용성에 묶이면 안 되기 때문(PRD §4.2).

로컬 폴백 컷오프:
- PHQ-9 (9문항, 0-27): 0-4 minimal / 5-9 mild / 10-14 moderate /
  15-19 moderately_severe / 20-27 severe (Kroenke 2001)
- GAD-7 (7문항, 0-21): 0-4 minimal / 5-9 mild / 10-14 moderate / 15-21 severe
- PHQ-4 (4문항, 0-12): 0-2 minimal / 3-5 mild / 6-8 moderate / 9-12 severe
- AUDIT-C (3문항, 0-12): 한국 절사점 근사 — 정본은 ai-server 채점기
"""

from __future__ import annotations

import logging
import uuid

from contracts.survey import SurveyScoreRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.questionnaire import QuestionnaireResult
from src.services.ai_client import AIClient, AIClientError

logger = logging.getLogger(__name__)

# 문항 수 / 문항별 최대값. AUDIT-C만 0-4 척도라 별도.
ITEM_COUNT: dict[str, int] = {"PHQ9": 9, "GAD7": 7, "AUDITC": 3, "PHQ4": 4}
MAX_ANSWER: dict[str, int] = {"PHQ9": 3, "GAD7": 3, "AUDITC": 4, "PHQ4": 3}

# 플랫폼 코드(하이픈 없음) ↔ ai-server 채점기 스케일명(하이픈 있음)
AI_SCALE_NAME: dict[str, str] = {
    "PHQ9": "PHQ-9",
    "GAD7": "GAD-7",
    "AUDITC": "AUDIT-C",
    "PHQ4": "PHQ-4",
}

SUPPORTED_TYPES: tuple[str, ...] = tuple(ITEM_COUNT)


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
    ceiling = MAX_ANSWER[qtype]
    for a in answers:
        # `bool` is an `int` subclass — reject it so a JSON `true` can't score as 1.
        if isinstance(a, bool) or not isinstance(a, int) or a < 0 or a > ceiling:
            raise QuestionnaireError(
                "ANSWER_OUT_OF_RANGE",
                f"각 응답은 0~{ceiling} 사이여야 해요.",
            )


def severity_for(qtype: str, score: int) -> str:
    """로컬 폴백 채점 — ai-server 불가 시에만 쓰인다."""
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
    if qtype == "GAD7":
        if score <= 4:
            return "minimal"
        if score <= 9:
            return "mild"
        if score <= 14:
            return "moderate"
        return "severe"
    if qtype == "PHQ4":
        if score <= 2:
            return "minimal"
        if score <= 5:
            return "mild"
        if score <= 8:
            return "moderate"
        return "severe"
    # AUDITC — 한국 절사점 근사 (정본은 ai-server 채점기)
    if score <= 3:
        return "minimal"
    if score <= 7:
        return "mild"
    if score <= 9:
        return "moderate"
    return "severe"


def score_questionnaire(qtype: str, answers: list[int]) -> tuple[int, str]:
    """검증 + 합산 + 로컬 분류. Returns (total_score, severity)."""
    validate_answers(qtype, answers)
    total = sum(answers)
    return total, severity_for(qtype, total)


def critical_item_positive(qtype: str, answers: list[int]) -> bool:
    """PHQ-9 9번(자해·죽음) 양성 여부 — v3 FR-043 확인 카드 트리거.

    ai-server 응답이 있으면 그 값을 쓰고, 폴백 시 이 함수가 쓰인다.
    """
    if qtype == "PHQ9" and len(answers) == 9:
        return answers[8] > 0
    return False


async def score_with_ai(
    qtype: str,
    answers: list[int],
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    patient_sex: str = "unknown",
) -> tuple[int, str, bool]:
    """ai-server 채점기 호출, 실패 시 로컬 폴백.

    Returns (total_score, severity, critical_item_positive).
    """
    validate_answers(qtype, answers)
    try:
        result = await ai_client.survey_score(
            SurveyScoreRequest(
                session_id=str(session_id),
                scale_name=AI_SCALE_NAME[qtype],
                responses=answers,
                patient_sex=patient_sex,
            )
        )
        return result.total_score, result.severity, result.critical_item_positive
    except AIClientError as exc:
        logger.warning(
            "survey scoring fell back to local cutoffs (session=%s type=%s): %s",
            session_id,
            qtype,
            exc,
        )
        total, severity = score_questionnaire(qtype, answers)
        return total, severity, critical_item_positive(qtype, answers)


async def upsert_result(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    qtype: str,
    answers: list[int],
    ai_client: AIClient | None = None,
    patient_sex: str = "unknown",
) -> tuple[QuestionnaireResult, bool]:
    """채점 후 저장. 같은 (session, type) 재제출은 덮어쓴다.

    Returns (row, critical_item_positive).
    """
    if ai_client is not None:
        total, severity, critical = await score_with_ai(
            qtype,
            answers,
            ai_client=ai_client,
            session_id=session_id,
            patient_sex=patient_sex,
        )
    else:
        total, severity = score_questionnaire(qtype, answers)
        critical = critical_item_positive(qtype, answers)

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
    return result, critical
