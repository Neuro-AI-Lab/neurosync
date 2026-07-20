"""POST /ai/domain/infer — request / response schema (F2).

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.

⚠️ 이 엔드포인트는 **Stage 2 전용**이다. Stage 1(RAG 검색)은 호출자 책임이며,
검색 없이 호출하려면 `retrieval_mode="llm_only"`로 두고 `turns`(환자 발화)만
근거 소스로 제공한다. 플랫폼은 현재 llm_only 모드로 호출한다 —
fabrication-0 보장이 필요한 평가 경로는 ai-server의 f2.py 하니스를 쓴다.

v3 원칙 1(NFR v3-2): 이 응답의 `domain` 문자열은 **라우팅 키로만** 쓰고
화면·클라이언트 상태·로그에 병명으로 남기지 않는다. 플랫폼 프록시가 도구 ID만
잘라서 모바일에 내려주는 이유다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DomainName = Literal[
    "anxiety", "depression", "alcohol", "substance", "trauma", "sleep", "psychosis", "other"
]
RetrievalMode = Literal["rag", "llm_only"]
EvidenceSourceType = Literal["rag_chunk", "utterance", "ocr_document"]


class UtteranceTurn(BaseModel):
    turn: int
    patient_message: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class DomainEvidence(BaseModel):
    source_type: EvidenceSourceType
    source_id: str
    quote: str

    model_config = ConfigDict(extra="ignore")


class DomainCandidate(BaseModel):
    domain: DomainName
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[DomainEvidence] = Field(default_factory=list)
    recommended_surveys: list[str] | None = None

    model_config = ConfigDict(extra="ignore")


class DomainInferRequest(BaseModel):
    """AgentInput 상속 필드(session_id/request_id) + F2 입력."""

    session_id: str
    request_id: str | None = None

    final_slots: dict[str, str] = Field(default_factory=dict, description="F1 임상 슬롯")
    session_ctrs: int = Field(default=3, ge=1, le=5)
    crisis_triggered: bool = False
    crisis_turn: int | None = None
    is_first_visit: bool = True

    turns: list[UtteranceTurn] = Field(default_factory=list)
    retrieval_mode: RetrievalMode = "llm_only"

    model_config = ConfigDict(extra="allow")


class DomainInferResponse(BaseModel):
    domain_candidates: list[DomainCandidate] = Field(default_factory=list)
    summary: str = ""

    model_config = ConfigDict(extra="ignore")
