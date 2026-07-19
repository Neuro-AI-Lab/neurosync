"""Schemas for the Policy-B RAG-trigger judge agent (F2, PLAN-2026-W28-Q W4).

``_archive/plans/validation_plan_f1f2_continuous.md`` §3 Policy-B row + §6 allowlist
table's "Policy-B judge (new)" row: licensed input is session transcript +
slot state ONLY — persona paths and ``retrieve_grounding()`` are explicitly
NOT licensed (mirrored, mechanically, by the BUG-022 guard test extension in
``tests/repro/test_bug_022.py`` — ``RagTriggerJudgeInput`` simply has no
field for either, so the guard's exact-match allowlist assertion catches any
future drift). ``risk_assessment`` is additionally hard-excluded as a query
source (REV-022 Issue 10's original mitigation) — enforced by
``src.rag_trigger.decide_policy_b`` stripping the key from ``final_slots``
BEFORE this schema is ever constructed, never merely instructed away in the
prompt, per this project's established code-enforce-not-prompt-only
precedent (ADR-014/REV-010/012/014).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput
from src.schemas.domain_inference import UtteranceTurn


class RagTriggerJudgeInput(AgentInput):
    """Input to ``RagTriggerJudgeAgent`` — session transcript + slot state
    ONLY (plan §6 allowlist, Policy-B judge row).

    ``final_slots`` must never carry a ``risk_assessment`` key — callers
    (``src.rag_trigger.decide_policy_b``) strip it before constructing this
    input; this schema does not re-validate that at the field level (the
    guard is ``tests/repro/test_bug_022.py``'s forbidden-field allowlist
    check plus ``decide_policy_b``'s own strip, not a runtime assertion
    here).
    """

    turns: list[UtteranceTurn] = Field(
        default_factory=list, description="Session transcript (patient utterances)"
    )
    final_slots: dict[str, str] = Field(
        default_factory=dict,
        description="Current F1 slot state (risk_assessment excluded by the caller)",
    )


class RagTriggerJudgeLLMResponse(BaseModel):
    """Exact JSON schema the judge LLM must produce (code-parsed, model-facing contract)."""

    retrieve: bool
    query: str | None = Field(default=None)


class RagTriggerJudgeOutput(AgentOutput):
    """Output from ``RagTriggerJudgeAgent`` — code-parsed only, never free text."""

    retrieve: bool = Field(default=False)
    query: str | None = Field(
        default=None,
        description="LLM-composed retrieval query text; None when retrieve=False",
    )
