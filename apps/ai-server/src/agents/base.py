"""Abstract base agent with shared input/output schemas."""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    """Base input shared by every agent."""

    session_id: str = Field(..., description="Session identifier")
    request_id: str | None = Field(default=None, description="Trace/request ID")
    extra: dict[str, Any] = Field(default_factory=dict, description="Agent-specific payload")


class AgentOutput(BaseModel):
    """Base output that every agent must return."""

    model_used: str = Field(default="", description="Model identifier actually used")
    prompt_version: str = Field(default="", description="Prompt template version")
    latency_ms: float = Field(default=0.0, description="End-to-end agent latency in ms")
    reason_summary: str = Field(
        default="",
        description="One-line policy reason for this output (never raw CoT)",
    )
    prompts_degraded: bool = Field(
        default=False,
        description=(
            "BUG-021: True when this agent's system prompt failed to load "
            "from PROMPTS_BASE_DIR and a hardcoded generic fallback prompt "
            "was used instead — makes a degraded run machine-visible in its "
            "artifacts instead of only a WARNING log line."
        ),
    )


class BaseAgent(abc.ABC):
    """Every domain agent inherits from this and implements run()."""

    @property
    @abc.abstractmethod
    def agent_name(self) -> str:
        """Registry key for this agent, e.g. 'safety_classifier'."""

    @abc.abstractmethod
    async def run(self, inp: AgentInput, **kwargs: Any) -> AgentOutput:
        """Execute the agent logic and return a typed output."""
