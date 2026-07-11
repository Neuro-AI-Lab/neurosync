"""Schemas for the Dialogue agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput
from src.schemas.common import RiskLevel


class DialogueInput(AgentInput):
    """Input to the dialogue agent.

    ``session_state`` is intentionally an unconstrained ``dict[str, Any]``
    at the schema level, not narrowed to a single caller's key space: it is
    genuinely polymorphic across this codebase's two independent live
    producers — ``src.f1.F1Pipeline`` (5-key set, see
    ``tests/repro/test_session_state_allowlist.py``) and
    ``src.routes.chat``'s ``OrchestratorAgent`` flow (``SessionState.
    model_dump()``, a disjoint ~14-key set, `src/routes/chat.py:130-136`).
    A schema-level allowlist keyed to one caller's shape would reject the
    other caller's legitimate, currently-shipped payload — confirmed by
    `tests/test_chat_orchestrator_integration.py::
    test_dialogue_input_has_session_state_field` exercising exactly that
    shape. REV-024 ruling 3's mechanical allowlist is therefore enforced at
    the CALLER level (`src.f1`'s own construction sites, standing-tested),
    not here — see that test module's docstring for the full rationale.
    """

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
