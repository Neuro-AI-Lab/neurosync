"""POST /ai/chat/respond — request / response schema.

Single source of truth between apps/api (consumer, WS gateway) and
apps/ai-server (producer, LLM dialogue). PRD §0.3 contract — change requires
both PRDs updated simultaneously. SLA: 첫 토큰 < 800ms (PRD §4.1).

ADR-046 decision #2 (`discussion.md`, PRD §5.1 Option A): this contract's
request/response field NAMES are aligned 1:1 to ai-server's own
`schemas.dialogue.DialogueInput`/`DialogueOutput` (the actual wire shape
`routes/chat.py` reads/returns) — the platform-bespoke `messages`/`reply`/
`progress`-only shape this contract previously had was structurally
incompatible (`extra=forbid` on both sides -> permanent 422, BUG analysis
`analysis_app_merge_20260721.md` finding 1). Renamed/added fields below are
a straight mirror of `DialogueInput`/`DialogueOutput`; ai-server needs zero
code changes for this fix (Option A's stated advantage).

`session_state` is the ADR-046 round-trip channel: the platform must send
back on turn N+1 exactly what it received in `ChatResponse.session_state` on
turn N (opaque `dict[str, Any]`, ai-server-owned shape) so the ADR-044
backstop fields (`asked_slot_counts`/`risk_screening_incomplete`/
`clinical_escalation_required`/`handoff_delivered`, nested under
`session_state.*`, `schemas/orchestrator.py::SessionState`) survive the
platform hop instead of being silently dropped every turn.

Separation of concerns:
- AI server generates the assistant reply AND decides which of the structured
  intake items have been collected so far (`progress.collected_items`), when
  it chooses to populate it. The 13-item taxonomy is an AI-domain decision;
  the platform only displays the ratio and persists it on the session.
  `progress` is additive/optional here (not part of `DialogueOutput`) — a
  turn that omits it leaves the session's last-known ratio unchanged
  (`services/chat.py`), never resets to 0.
- Streaming (`ai:token`) is deferred until the AI server exposes SSE; this
  contract is the non-streaming full-reply shape consumed for `ai:complete`.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str = Field(description="'user' | 'ai' | 'system'")
    content: str

    model_config = ConfigDict(extra="forbid")


class ChatProgress(BaseModel):
    """Intake completeness — drives the patient-facing progress bar (FR-004).

    `ratio` is AI-computed (collected / total) and is the value the platform
    trusts for display + the §5.5 flow gate (≥0.7 → questionnaire step).
    """

    collected_items: list[str] = Field(
        default_factory=list,
        description="Keys of the structured items gathered so far (e.g. "
        "'chief_complaint', 'onset'). Cumulative across the conversation.",
    )
    total_items: int = Field(default=13, ge=1)
    ratio: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class GroundingCase(BaseModel):
    """RAG: 유사 심리상담 사례 (남의 사례, grounding)."""

    disease_class: str = Field(description="DEPRESSION | ANXIETY | ADDICTION")
    situation: str
    score: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class GroundingPast(BaseModel):
    """RAG: 환자 본인의 과거 세션 요약 (개인화). 플랫폼이 patient_id로 필터·복호화."""

    disease_class: str | None = None
    situation: str
    score: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class GroundingKnowledge(BaseModel):
    """RAG: 정신과 지식 QA."""

    question: str
    answer: str
    score: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class GroundingFollowup(BaseModel):
    """RAG: disease_symptom 그래프 기반 후보 질병 + 미확인 증상(추가질문 후보)."""

    candidate_disease: str
    follow_up_symptoms: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class Grounding(BaseModel):
    """플랫폼(apps/api)이 pgvector RAG로 만들어 AI에 주입하는 컨텍스트.

    docs/ai §3.2: Platform이 context를 먹이고 AI는 순수 LLM 함수. AI는 DB 미접근.
    AI 서버는 이 grounding을 프롬프트(정신과 EMR 주입)로 활용한다.
    """

    similar_cases: list[GroundingCase] = Field(default_factory=list)
    my_past: list[GroundingPast] = Field(default_factory=list)
    knowledge: list[GroundingKnowledge] = Field(default_factory=list)
    mentioned_symptoms: list[str] = Field(default_factory=list)
    follow_up: GroundingFollowup | None = None

    model_config = ConfigDict(extra="forbid")


class ChatRequest(BaseModel):
    """Mirrors `schemas.dialogue.DialogueInput`'s own field set (ADR-046 #2)."""

    session_id: UUID
    request_id: str | None = Field(default=None, description="Trace/request ID")
    user_message: str = Field(..., min_length=1, description="Current user message")
    conversation_history: list[ChatMessage] = Field(
        default_factory=list,
        description="Previous turns, oldest-first (decrypted by platform); "
        "excludes the current `user_message`.",
    )
    filled_slots: dict[str, str] = Field(
        default_factory=dict,
        description="Session-accumulated clinical slots (platform's "
        "`sessions.clinical_slots`) — the SAME map threaded to "
        "`/ai/slots/extract`.",
    )
    session_state: dict[str, Any] | None = Field(
        default=None,
        description="ADR-046 round-trip channel: verbatim pass-through of "
        "the PRIOR turn's `ChatResponse.session_state` (opaque, "
        "ai-server-owned). `None` on the session's first turn.",
    )
    patient_history_context: str = Field(
        default="",
        description="환자 PHR 요약 (세션 시작 시 1회 로드, 있으면 매 턴 전달).",
    )

    model_config = ConfigDict(extra="forbid")


class ChatResponse(BaseModel):
    """Mirrors `schemas.dialogue.DialogueOutput`'s own field set (ADR-046 #2).

    `extra="ignore"` — `DialogueOutput` carries additional BUG-030/036/037
    retry-telemetry fields (`retry_count`, `near_dup_detail`, ...) the
    platform does not consume; tolerating them here (rather than
    `extra="forbid"`) is what keeps this contract from re-breaking every
    time ai-server adds a new telemetry field to that schema.
    """

    assistant_response: str = Field(min_length=1)
    model_used: str = Field(default="", description="e.g. 'claude-opus-4-8', 'solar-pro-3'")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Server-measured wall-clock")
    risk_level: Literal["none", "low", "medium", "high", "critical"] = "none"
    requires_human_review: bool = False
    all_slots: dict[str, str] = Field(
        default_factory=dict, description="Merged slot state after this turn"
    )
    session_state: dict[str, Any] | None = Field(
        default=None,
        description="ADR-046 round-trip channel — echo back verbatim on "
        "the NEXT `ChatRequest.session_state`. Carries the ADR-044 backstop "
        "fields (`asked_slot_counts`/`risk_screening_incomplete`/"
        "`clinical_escalation_required`/`handoff_delivered`) nested inside, "
        "ai-server-owned shape (`schemas/orchestrator.py::SessionState`).",
    )
    handoff_ready: bool = Field(
        default=False, description="True when slot coverage threshold reached"
    )
    handoff_report: dict[str, Any] | None = Field(
        default=None, description="Passthrough report payload when handoff_ready=True"
    )
    clinical_escalation_required: bool = Field(
        default=False,
        description="ADR-044 backstop: risk_assessment never grounded before "
        "the session's hard turn ceiling — clinician escalation required.",
    )
    crisis_triggered: bool = Field(
        default=False,
        description="CVR-051 fix: mirrors `DialogueOutput.crisis_triggered` "
        "(itself a mirror of `OrchestratorTurnResult.crisis_triggered`, "
        "ADR-046 #2 field-name alignment). True only when ai-server's own "
        "conversation-history-aware SafetyClassifierAgent invocation "
        "inside the orchestrator (`agents/orchestrator.py::_run_safety_"
        "gate`/`_execute_pipeline`) fired the crisis bypass on THIS turn — "
        "distinct from `risk_level`/`requires_human_review` (which are set "
        "on every turn, bypass or not). The platform (`services/chat.py::"
        "respond()`) uses this flag, not `risk_level` alone, to decide "
        "whether to run the SAME `handle_safety_result` escalation "
        "(RiskEvent + `risk:detected`) the pre-gate safety path already "
        "runs — previously this signal was silently dropped end-to-end "
        "(CVR-051).",
    )
    risk_categories: list[str] = Field(
        default_factory=list,
        description="BUG-060/CVR-051 follow-up: mirrors `DialogueOutput."
        "risk_categories` — the merged rule+LLM category tags "
        "(`schemas.safety.SafetyOutput.categories`, e.g. "
        "'suicidal_ideation'/'self_harm'/'harm_to_others'/'distress') for "
        "THIS turn's safety classification. Populated (non-empty) only "
        "when `crisis_triggered=True` for this turn; the platform "
        "(`services/chat.py::_handle_orchestrator_crisis`) maps this to "
        "the correct `contracts.safety.RiskCategory` instead of "
        "hardcoding `OTHER_HARM` for every orchestrator-crisis RiskEvent. "
        "Empty is a valid safe-default (see ai-server schema docstring), "
        "not an error.",
    )
    progress: ChatProgress | None = Field(
        default=None,
        description="Intake completeness for the progress bar (FR-004) — "
        "additive/optional (NOT part of DialogueOutput). BUG-075: ai-server "
        "has never actually populated this field on any real call (its "
        "`DialogueOutput` schema has no `progress` field to source it "
        "from), so it is always `None` in practice. `services/chat.py::"
        "respond` no longer derives progress from this field at all — it "
        "computes `progress_ratio`/`collected_items` directly from "
        "`ChatResponse.session_state` (ai-server's own `SessionState."
        "slot_coverage`/`filled_slots`, always present) instead. This field "
        "is kept on the contract for backward compatibility only (an "
        "ai-server that DID start populating it would not break parsing) — "
        "do not add new consumers of it without re-checking `services/"
        "chat.py`'s own BUG-075 fix note first.",
    )

    model_config = ConfigDict(extra="ignore")
