"""POST /ai/slots/extract — request / response schema (F1 임상 슬롯 추출).

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.

대화 중 백그라운드로 주호소·현병력·수면·과거력 등 임상 슬롯을 뽑아 세션에
누적한다. 이 슬롯이 F2 도메인 추정(`final_slots`)의 입력이 되고, F5 핸드오프
리포트의 구조화 근거가 된다.

저장 위치 주의: 추출 결과는 플랫폼 `sessions.clinical_slots`에 보관한다.
`rag.session_insights.slots`는 VP 시뮬레이션(코퍼스) 테이블이므로 실환자 슬롯을
그쪽에 쓰면 RAG 코퍼스가 오염된다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SlotsExtractRequest(BaseModel):
    session_id: str
    request_id: str | None = None
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list, description="[{role, content}] — 오래된 것부터"
    )
    current_slots: dict[str, Any] = Field(
        default_factory=dict, description="지금까지 누적된 슬롯 (증분 추출용)"
    )
    dialogue_target_slot: str | None = Field(
        default=None,
        description="BUG-072/073: 직전에 dialogue steering이 실제로 질문한 슬롯 "
        "(ai-server `SessionState.dialogue_target_slot`, single source of "
        "truth). platform이 라운드트립받은 `session_state`에서 그대로 읽어 "
        "채운다 — 이 값이 있으면 ai-server가 마지막 환자 발화를 이 슬롯에 대한 "
        "ask-evidence로 태깅해, 짧은 부인 답변('없어')도 grounding될 수 있다.",
    )

    model_config = ConfigDict(extra="allow")


class SlotsExtractResponse(BaseModel):
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    filled_slots: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    essential_filled: list[str] = Field(default_factory=list)
    essential_missing: list[str] = Field(default_factory=list)
    slot_coverage: float = 0.0
    slot_status: dict[str, str] = Field(
        default_factory=dict,
        description="BUG-072: 이번 호출에서 accept된 슬롯 키의 3-상태 grounding "
        "판정('filled'|'denied') — ai-server `src.grounding."
        "verdict_to_slot_status`. 이번 호출에서 제안되지 않았거나 필터에서 "
        "drop된 키는 없음 — 누적 뷰가 필요하면 호출자가 이전 턴 값과 병합한다.",
    )

    model_config = ConfigDict(extra="ignore")
