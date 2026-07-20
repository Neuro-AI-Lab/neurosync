"""score_with_ai — ai-server 위임 채점 + 로컬 폴백 (PR#74 M4).

핵심: ai-server가 성공하면 그 값을, 어떤 실패(AIClientError — C1 수정 후 파싱/검증
실패도 포함)에서도 로컬 컷오프로 폴백한다. 문진 제출은 AI 가용성에 묶이면 안 된다.
"""

from __future__ import annotations

import uuid

import pytest
from contracts.survey import SurveyScoreResponse

from src.services.ai_client import AIClientError
from src.services.questionnaire import score_with_ai

SESSION = uuid.uuid4()


class _FakeClient:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def survey_score(self, payload) -> SurveyScoreResponse:
        if self._error is not None:
            raise self._error
        return self._result


@pytest.mark.asyncio
async def test_uses_ai_server_result_when_available() -> None:
    client = _FakeClient(
        result=SurveyScoreResponse(
            scale_name="PHQ-9",
            total_score=27,
            max_score=27,
            severity="severe",
            critical_item_positive=True,
        )
    )
    total, severity, critical = await score_with_ai(
        "PHQ9", [3] * 9, ai_client=client, session_id=SESSION
    )
    assert (total, severity, critical) == (27, "severe", True)


@pytest.mark.asyncio
async def test_falls_back_to_local_on_ai_failure() -> None:
    """AIClientError(전송/파싱/검증 실패 통칭) 시 로컬 컷오프로 채점."""
    client = _FakeClient(error=AIClientError("survey/score failed: malformed 200"))
    total, severity, critical = await score_with_ai(
        "PHQ9", [3] * 9, ai_client=client, session_id=SESSION
    )
    # 로컬 채점: 27점 severe, 9번(마지막) 양성.
    assert total == 27
    assert severity == "severe"
    assert critical is True


@pytest.mark.asyncio
async def test_local_fallback_item9_negative() -> None:
    client = _FakeClient(error=AIClientError("boom"))
    _, _, critical = await score_with_ai(
        "PHQ9", [1, 1, 0, 0, 0, 0, 0, 0, 0], ai_client=client, session_id=SESSION
    )
    assert critical is False


@pytest.mark.asyncio
async def test_auditc_local_fallback_scores() -> None:
    """AUDIT-C도 폴백 경로에서 채점된다 (이전엔 저장조차 불가했던 척도)."""
    client = _FakeClient(error=AIClientError("boom"))
    total, severity, critical = await score_with_ai(
        "AUDITC", [4, 4, 4], ai_client=client, session_id=SESSION
    )
    assert total == 12
    assert severity == "severe"
    assert critical is False
