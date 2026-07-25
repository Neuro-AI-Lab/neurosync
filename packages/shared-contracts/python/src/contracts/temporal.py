"""POST /ai/temporal/summarize — 요청/응답 계약 (F4 종단 상태 추론).

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.

ai-server가 직전 방문과 이번 방문의 척도(PHQ-9/GAD-7)·CTRS·정서를 비교해
방향(호전/악화/불변)과 시각화용 `plot_data`를 준다. 플랫폼은 이를 모바일 리포트의
**점수 추이 차트**에 바인딩한다 (핸드오프 문서 수정 7).

케이싱: ai-server는 snake_case를 주고(필드명으로 파싱), 모바일에는 camelCase로
내보낸다(serialization_alias + model_dump(by_alias=True)). ai-server 응답은
domain_trends 등 필드가 더 많으므로 extra="ignore".

⚠️ v3 원칙 1(NFR v3-2): 추이는 **환자 본인 응답 기반 표준 척도 점수**만 시각화한다.
AI 추정 질환명·도메인은 이 응답에도 넣지 않고 화면에도 남기지 않는다.
CTRS는 **숫자가 낮을수록 위험**(1=최고위험)이므로 클라이언트가 반대로 표기한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Direction = Literal["improved", "worsened", "unchanged", "unknown"]


class TemporalSummarizeRequest(BaseModel):
    """ai-server `TemporalSummaryInput`(AgentInput 상속)에 맞춘 요청.

    current/prior_scales 는 도구명→점수 맵 (예: {"PHQ-9": 15, "GAD-7": 10}).
    첫 방문이면 prior_* 는 비우고 is_first_visit=True 로 둔다.
    """

    session_id: str
    request_id: str | None = None
    patient_id: str = ""
    is_first_visit: bool = True
    current_scales: dict[str, int] = Field(default_factory=dict)
    prior_scales: dict[str, int] = Field(default_factory=dict)
    current_ctrs: int | None = None
    prior_ctrs: int | None = None
    current_date: str = ""
    prior_date: str = ""

    # ai-server AgentInput 은 extra 필드를 허용한다.
    model_config = ConfigDict(extra="allow")


class TemporalPlotPoint(BaseModel):
    date: str = ""
    phq9: int | None = None
    gad7: int | None = None
    ctrs_level: int | None = Field(default=None, serialization_alias="ctrsLevel")
    sentiment_polarity: float | None = Field(
        default=None, serialization_alias="sentimentPolarity"
    )
    events: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class TemporalSummarizeResponse(BaseModel):
    overall_direction: Direction = Field(
        default="unknown", serialization_alias="overallDirection"
    )
    plot_data: list[TemporalPlotPoint] = Field(
        default_factory=list, serialization_alias="plotData"
    )
    is_first_visit: bool = Field(default=True, serialization_alias="isFirstVisit")

    model_config = ConfigDict(extra="ignore")
