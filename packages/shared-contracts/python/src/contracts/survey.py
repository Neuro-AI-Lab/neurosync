"""POST /ai/survey/score — request / response schema.

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.

결정론적 채점(LLM 없음)이라 SLA는 사실상 네트워크 왕복. 임상 규칙(AUDIT-C 한국
절사점, PHQ-9 9번 critical item 판정)을 ai-server 단일 소스로 두기 위해 플랫폼이
이 계약을 통해 채점을 위임한다 (v3 FR-040).

플랫폼 코드는 하이픈이 없고(`PHQ9`) 채점기 스케일명은 하이픈이 있다(`PHQ-9`).
변환은 apps/api의 `services.questionnaire.AI_SCALE_NAME`이 담당한다.

ADR-046 #2 (contract3 fix): `responses`는 flat `list[int]`가 아니라 ai-server
`schemas.survey.SurveyScoreInput.responses: list[SurveyItemResponse]`(1-based
`index` + `value` 쌍)과 동일한 shape이다 — 이전 flat-int shape는 ai-server
스키마와 구조적으로 불일치해 상시 422를 유발했다
(`analysis_app_merge_20260721.md` 발견 3). `apps/api`측 변환은
`services.questionnaire.score_with_ai`가 담당한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ScaleName = Literal["PHQ-9", "GAD-7", "PHQ-4", "WHO-5", "AUDIT-C"]


class SurveyItemResponse(BaseModel):
    """One administered item's response — mirrors ai-server's own
    `schemas.survey.SurveyItemResponse` (index/value pair) 1:1."""

    index: int = Field(..., description="1-based item index")
    value: int = Field(..., description="Selected response value for this item")

    model_config = ConfigDict(extra="forbid")


class SurveyScoreRequest(BaseModel):
    session_id: str = Field(default="", description="추적용 — 채점에는 쓰이지 않음")
    scale_name: ScaleName
    responses: list[SurveyItemResponse] = Field(min_length=1, max_length=20)
    patient_sex: str = Field(
        default="unknown", description="male/female/unknown — AUDIT-C 절사점에 사용"
    )

    model_config = ConfigDict(extra="forbid")


class SurveyScoreResponse(BaseModel):
    scale_name: str
    total_score: int
    max_score: int
    severity: str
    # v3 FR-043 — PHQ-9 9번 양성이면 클라이언트가 인라인 확인 카드를 띄운다.
    critical_item_positive: bool = False
    critical_items: list[dict] = Field(default_factory=list)
    subscale_scores: dict[str, int] = Field(default_factory=dict)
    interpretation: str = ""
    recommended_action: str = ""

    # ai-server가 필드를 추가해도 플랫폼이 깨지지 않도록 허용(안전한 방향).
    model_config = ConfigDict(extra="ignore")
