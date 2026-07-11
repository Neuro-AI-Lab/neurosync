"""Schemas for the Dialogue agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput
from src.schemas.common import RiskLevel


class DialogueInput(AgentInput):
    """Input to the dialogue agent."""

    user_message: str = Field(..., description="Current user message")
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Previous turns [{role, content}, ...]",
    )
    filled_slots: dict[str, str] = Field(
        default_factory=dict,
        description="Already-collected slot values",
    )
    safety_result: dict[str, str] | None = Field(
        default=None,
        description="Latest safety classification if available",
    )
    session_state: dict[str, Any] | None = Field(
        default=None,
        description="Orchestrator session state from previous turn (pass-through)",
    )
    patient_history_context: str = Field(
        default="",
        description=(
            "환자 PHR(개인건강기록) 요약. 세션 시작 전 로드되어 있으면 dialogue "
            "system prompt 첫 부분에 삽입되어 LLM이 병력·복약을 인지한 상태로 "
            "대화한다. 비어있으면 무시."
        ),
    )


class DialogueLLMResponse(BaseModel):
    """Expected JSON structure from the Dialogue LLM call.

    Dialogue Agent는 응답 생성만 담당한다.
    slot_updates, risk_level 등은 다른 Agent의 역할이므로 여기서 요구하지 않는다.
    LLM이 extra 필드를 보내더라도 무시한다 (model_config).
    """
    model_config = {"extra": "ignore"}

    assistant_response: str = Field(..., description="Patient-facing response text")
    reason_summary: str = Field(default="")


class DialogueOutput(AgentOutput):
    """Output from the dialogue agent."""

    assistant_response: str = Field(..., description="Patient-facing response")
    slot_updates: dict[str, str] = Field(default_factory=dict)
    risk_level: RiskLevel = Field(default=RiskLevel.none)
    requires_human_review: bool = Field(default=False)
    all_slots: dict[str, str] = Field(
        default_factory=dict,
        description="Merged slot state after this turn",
    )
    session_state: dict[str, Any] | None = Field(
        default=None,
        description="Updated orchestrator session state for next turn",
    )
    handoff_ready: bool = Field(
        default=False,
        description="True when slot coverage threshold reached — trigger handoff",
    )
