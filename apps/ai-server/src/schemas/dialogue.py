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
    patient_history_context: str = Field(
        default="",
        description=(
            "환자 PHR(개인건강기록) 요약. 세션 시작 전 로드되어 있으면 dialogue "
            "system prompt 첫 부분에 삽입되어 LLM이 병력·복약을 인지한 상태로 "
            "대화한다. 비어있으면 무시."
        ),
    )
    slot_updates_this_turn: dict[str, str] | None = Field(
        default=None,
        description=(
            "Slot values written THIS turn only, before this dialogue call "
            "(e.g. f1.py Step 1b's risk_assessment composition, or Step 2's "
            "ClinicalSlotAgent extraction). Used by the BUG-037 output-"
            "isolation guard (`_archive/plans/fix_design_exhaustion_bug037.md` §2) "
            "to prioritize detection of same-turn clinical-note leaks. "
            "Distinct from `filled_slots` (the full session-accumulated "
            "slot state, also checked by the same guard at lower priority). "
            "Optional — callers that do not thread it (e.g. routes/chat.py) "
            "still get the `filled_slots`-only check."
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
    # REV-001 Issue 1 (critic, `discussion.md`): this schema previously had
    # NO field at all that could carry `OrchestratorTurnResult.handoff_report`
    # onto the wire — not a null-check gap, a structural absence. Every
    # handoff-ready turn through `routes/chat.py` shipped a Korean "report
    # will be written" message with zero report content reachable by the
    # client. Typed the same shape as `OrchestratorTurnResult.handoff_report`
    # (`dict[str, Any] | None`, `schemas/orchestrator.py`) — a passthrough,
    # never re-derived here. `None` on every non-handoff-ready turn and on
    # every pre-fix caller that never sets it (additive, non-breaking).
    handoff_report: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Passthrough of OrchestratorTurnResult.handoff_report when "
            "handoff_ready=True. Always None when handoff_ready=False."
        ),
    )
    # ADR-044 (CVR-043 pin-fix): passthrough of `OrchestratorTurnResult.
    # clinical_escalation_required` — True when this session's turn cap
    # was reached with `risk_assessment` still ungrounded (the backstop-
    # vs-risk-grounding gate), so `handoff_ready` was deliberately
    # suppressed instead of shipping a routine "ready for pickup" signal.
    # Clinician-facing only — never rendered to the patient (see
    # `OrchestratorAgent._INCOMPLETE_INTAKE_MESSAGE`'s own docstring for
    # why the patient-facing text stays calm/non-alarming).
    clinical_escalation_required: bool = Field(
        default=False,
        description=(
            "True when the session ended via the ADR-044 backstop-vs-"
            "risk-grounding gate (risk_assessment never grounded before "
            "the hard turn ceiling) — handoff_ready is always False and "
            "handoff_report is always None whenever this is True."
        ),
    )
    # CVR-051 fix: mirrors `OrchestratorTurnResult.crisis_triggered`
    # (`schemas/orchestrator.py`) onto the wire — this route's own
    # crisis-bypass branch (`routes/chat.py` Step 2) sets this True;
    # every other branch/path leaves the safe default False. Previously
    # absent from this schema entirely, so a crisis detected by THIS
    # (conversation-history-aware, distinct from apps/api's pre-gate)
    # SafetyClassifierAgent invocation was unrepresentable on the wire —
    # only `risk_level`/`requires_human_review` (BUG-046) carried, and
    # neither alone told the caller "this is the crisis-bypass turn".
    # BUG-060/CVR-051 follow-up: passthrough of `SafetyStatus.categories`
    # (`schemas/orchestrator.py`) — lets `routes/chat.py`'s crisis-bypass
    # branch (Step 2) surface WHICH kind of risk fired this turn, instead
    # of only carrying `risk_level`. Empty on every non-crisis turn and on
    # a crisis turn where neither the rule engine nor the LLM attached a
    # category (safe-default case, see `SafetyStatus.categories` docstring).
    risk_categories: list[str] = Field(default_factory=list)
    crisis_triggered: bool = Field(
        default=False,
        description=(
            "True when this turn's orchestrator run hit the crisis "
            "bypass (`OrchestratorTurnResult.crisis_triggered`) — "
            "`assistant_response` is the fixed crisis-protocol message, "
            "not a DialogueAgent LLM generation."
        ),
    )
    # BUG-030 iter-2 / BUG-035 guard telemetry (`docs/ai/fix_design_bug030_
    # iter2.md` §6, ADR-029). Additive, safe defaults — the two non-guard
    # construction sites (`routes/chat.py:95,111`) never set these.
    retry_count: int = Field(
        default=0,
        description="Regeneration attempts this turn (BUG-030 iter-2 / BUG-035 guard)",
    )
    retry_reasons: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered violation reasons that triggered each attempt: "
            "output_isolation_this_turn | output_isolation_prior_turn | "
            "output_isolation_patient_echo | presence_missing | exact_repeat | "
            "near_dup_back_to_back | near_dup_session_cap"
        ),
    )
    fall_through: bool = Field(
        default=False,
        description=(
            "True if the retry budget was exhausted while a violation "
            "still held AND no safe-degrade path exists for that "
            "violation type — response shipped anyway. As of Fix 2/Fix 3 "
            "(ADR-030, `_archive/plans/fix_design_exhaustion_bug037.md` §3) this "
            "is unreachable for every currently-enumerated violation: "
            "output_isolation_* ships `output_isolation_fallback` instead, "
            "and presence_missing/exact_repeat/near_dup_* ship "
            "`exhaustion_degrade` instead. Kept as a defensive catch-all "
            "for any future violation type not yet covered by either path. "
            "Mutually exclusive with `output_isolation_fallback` and "
            "`exhaustion_degrade` by construction — only one branch of the "
            "exhaustion decision runs per turn."
        ),
    )
    retry_latency_ms: float = Field(
        default=0.0,
        description="Wall-clock time spent in regeneration LLM calls only (subset of latency_ms)",
    )
    crisis_adjacent: bool = Field(
        default=False,
        description="True if this turn qualified for the BUG-035 empathy-presence check",
    )
    output_isolation_fallback: bool = Field(
        default=False,
        description=(
            "BUG-037: True if the output-isolation retry budget was "
            "exhausted while a violation still held — unlike fall_through, "
            "the violating text was NOT shipped; assistant_response was "
            "replaced with a minimal neutral continuation instead "
            "(`_archive/plans/fix_design_exhaustion_bug037.md` §2)."
        ),
    )
    near_dup_detail: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "BUG-036 telemetry: one entry per attempt where the near-dup "
            "sub-check itself detected a match (independent of whether it "
            "was the acted-upon violation that attempt — a higher-priority "
            "check may have outranked it). Each entry: "
            "{reason: back_to_back|session_cap, family: <matched clause "
            "text>, count: <prior same-family occurrences>} "
            "(`_archive/plans/fix_design_exhaustion_bug037.md` §2)."
        ),
    )
    # Fix 2 — Option C (`_archive/plans/fix_design_exhaustion_bug037.md` §3,
    # ADR-030 Decisions 1/2): the elevated-review flag for the retry-
    # budget-exhaustion safe-degrade path (CVR-013 condition 1).
    exhaustion_degrade: str | None = Field(
        default=None,
        description=(
            "The violation reason (presence_missing | exact_repeat | "
            "near_dup_back_to_back | near_dup_session_cap) if the retry "
            "budget was exhausted while an empathy-degradable violation "
            "still held and the leading empathy clause was deterministically "
            "substituted/prepended with a pool phrase, instead of shipping "
            "the detected-violating text (`fall_through`) or the "
            "output-isolation neutral fallback "
            "(`output_isolation_fallback`). None on every other turn. "
            "Mutually exclusive with both `fall_through` and "
            "`output_isolation_fallback` by construction — only one "
            "branch of the exhaustion decision runs per turn."
        ),
    )
    exhaustion_degrade_phrase: str | None = Field(
        default=None,
        description=(
            "Which `_EMPATHY_DEGRADE_POOL` phrase was substituted/"
            "prepended, when `exhaustion_degrade` is set (elevated-review "
            "detail, CVR-013 condition 1). None when `exhaustion_degrade` "
            "is None."
        ),
    )
