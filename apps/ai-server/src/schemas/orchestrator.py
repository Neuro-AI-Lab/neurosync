"""Orchestrator session state and I/O schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.schemas.common import CTRSLevel, RiskLevel


class SessionStage(StrEnum):
    """State machine stages for the orchestrator pipeline."""

    input_received = "input_received"
    safety_gate = "safety_gate"
    context_retrieval = "context_retrieval"
    dialogue_loop = "dialogue_loop"
    slot_extraction = "slot_extraction"
    handoff_generation = "handoff_generation"
    evidence_verification = "evidence_verification"
    handoff_delivery = "handoff_delivery"
    crisis_flow = "crisis_flow"
    completed = "completed"
    error = "error"


class InputType(StrEnum):
    """Input modality types."""

    text = "text"
    stt_transcript = "stt_transcript"
    ocr_document = "ocr_document"


class StageRecord(BaseModel):
    """Single entry in the stage transition history."""

    stage: SessionStage
    agent: str = Field(default="", description="Agent that handled this stage")
    result: str = Field(default="", description="pass | fail | crisis | skip")
    timestamp: datetime = Field(default_factory=datetime.now)
    detail: str = Field(default="", description="Optional detail about outcome")


class SafetyStatus(BaseModel):
    """Current safety classification state."""

    ctrs_level: CTRSLevel = CTRSLevel.STABLE
    risk_level: RiskLevel = RiskLevel.none
    crisis_triggered: bool = False
    # BUG-046 (EXP-028): SafetyOutput.requires_human_review (CTRS<=3, "needs
    # human review" — safety_classifier.py's own `ctrs <= CTRSLevel.ACUTE`
    # computation) had no field to survive onto here at all — a wire-
    # contract absence, not a null-check gap (same shape as REV-001 Issue 1's
    # `handoff_report` finding). Populated by `_run_safety_gate` from
    # `SafetyOutput.requires_human_review` directly, never re-derived.
    requires_human_review: bool = False
    last_checked_at: datetime | None = None
    # BUG-060/CVR-051 follow-up: passthrough of `SafetyOutput.categories`
    # (`agents/safety_classifier.py` rule+LLM merge — e.g. "suicidal_
    # ideation"/"self_harm"/"harm_to_others"/"distress") so the crisis-
    # bypass caller (`routes/chat.py` Step 2) can tell apps/api WHICH kind
    # of risk fired this turn, instead of apps/api hardcoding a single
    # placeholder category for every crisis-bypass RiskEvent. Empty when
    # the safety gate raised (except branch below) or when neither the
    # rule engine nor the LLM populated a category for this turn's risk
    # level — the crisis-bypass CTRS band (`_CRISIS_MESSAGES`) is itself
    # self-harm/suicide-oriented by construction, so an empty list is a
    # safe-default signal, not a data-loss signal.
    categories: list[str] = Field(default_factory=list)


class SessionState(BaseModel):
    """Persistent session state that survives across turns.

    This is the core data structure the Orchestrator mutates as it moves
    through pipeline stages.  It is designed to be serializable so that
    it can be persisted to a DB or cache for crash recovery.
    """

    session_id: str
    patient_id: str = ""
    current_stage: SessionStage = SessionStage.input_received
    safety_status: SafetyStatus = Field(default_factory=SafetyStatus)
    slot_data: dict[str, Any] = Field(default_factory=dict)
    filled_slots: list[str] = Field(default_factory=list)
    missing_essential_slots: list[str] = Field(default_factory=list)
    # B5 enabler (EXP-029, orchestrator design decision, additive semantics
    # change — backend-visible): as of this field, `slot_coverage` is
    # fraction-of-PATIENT-FILLABLE-slots-filled (7 of 12,
    # `src.agents.clinical_slot.PATIENT_FILLABLE_SLOTS` — excludes
    # risk_assessment/encounter_metadata/clinical_assessment/
    # treatment_plan/mental_status_exam), NOT fraction-of-all-12. The 0.7
    # `handoff_ready` threshold and the turn-20 backstop are unchanged;
    # only the denominator changed, so a given real session now reaches
    # 0.7 sooner (organically) than the old all-12 denominator ever
    # allowed on the production route.
    slot_coverage: float = 0.0
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    stage_history: list[StageRecord] = Field(default_factory=list)
    turn_count: int = 0
    is_first_visit: bool = True
    scale_scores: dict[str, Any] = Field(default_factory=dict)
    error_log: list[str] = Field(default_factory=list)
    # BUG-050 observability fix (additive): every `EvidenceVerifierAgent`
    # attempt's verbatim `VerifierIssue` list, tagged by attempt number —
    # "attempt N: [severity] issue_type @ location: description". Was
    # previously invisible on the wire (only the bare "regenerate"/"fail"
    # stage label reached `stage_history`), forcing code archaeology to
    # diagnose why `handoff_ready` never fired (BUG-050's own qa finding).
    verifier_issue_log: list[str] = Field(default_factory=list)
    # BUG-051 (CVR-039 blocking finding, additive): once-per-session latch
    # for the BUG-047 soft-safety note (`src.schemas.common.
    # SOFT_SAFETY_NOTE`) — CVR-039 found it appended twice in one turn and
    # re-appended on every subsequent CTRS-3+SI-adjacent turn within a
    # session. `soft_safety_note_sent`/`soft_safety_note_last_turn` let
    # `OrchestratorAgent._execute_pipeline` gate `pending_soft_safety` on
    # "not sent yet this session, OR >= _SOFT_SAFETY_REARM_TURNS turns
    # since the last send" (re-arm window — a long-gap NEW escalation can
    # still surface the reminder again, never a hard one-shot-forever).
    soft_safety_note_sent: bool = False
    soft_safety_note_last_turn: int | None = None

    # ── Cluster A (asked-slot tracking, additive) ────────────────────
    # Per-slot count of consecutive turns the slot was targeted by
    # dialogue steering and remained unfilled at the START of the NEXT
    # turn. `risk_assessment` is intentionally never tracked here — it is
    # governed exclusively by the Cluster C probe/termination gate below,
    # never deferred (see `OrchestratorAgent._update_asked_slot_tracking`).
    asked_slot_counts: dict[str, int] = Field(default_factory=dict)
    # Slots that hit the ask-count threshold — dialogue steering (round-
    # robin) stops re-selecting these for the rest of the session. Still
    # reported in the handoff's missing-slots section, never silently
    # dropped from the record.
    deferred_slots: list[str] = Field(default_factory=list)
    # The slot dialogue steering targeted THIS turn (recorded so the NEXT
    # turn's `_update_asked_slot_tracking` can check whether it was
    # answered) — None when the turn's context was probe/SI-screen-driven
    # (those are governed by Cluster C, not the asked-slot counter).
    pending_target_slot: str | None = None

    # BUG-073 (single source of truth, additive): the slot dialogue
    # steering is ACTUALLY asking about THIS turn, regardless of WHICH
    # mechanism picked it (plain round-robin OR the probe/mandatory-SI-
    # screen path) — always `RISK_SLOT_KEY` while the probe/screen is
    # active, never reset to `None` the way `pending_target_slot` is for
    # Cluster A's own (risk_assessment-excluded) bookkeeping. This is the
    # one field a caller should read to answer "what is dialogue asking
    # about this turn" — used to (a) tag the ask-evidence hint threaded to
    # `POST /ai/slots/extract` (`ClinicalSlotInput.dialogue_target_slot`,
    # BUG-072) and (b) verify DialogueAgent's own independently-computed
    # render target agrees with what the orchestrator recorded (BUG-073
    # regression guard — both call `DialogueAgent.compute_target_slot`
    # with matching inputs, so they should always agree).
    dialogue_target_slot: str | None = None

    # BUG-072 (additive): 3-state grounding status per slot key —
    # "filled" | "denied" | "missing" (see `src.grounding.
    # verdict_to_slot_status`). Populated by `OrchestratorAgent` whenever
    # it grounds a value itself (the bare-denial direct-compose path in
    # `_update_asked_slot_tracking`, or a merge from a grounded
    # `ClinicalSlotOutput.slot_status`) — additive/best-effort, a key's
    # absence here does not mean "missing" if the key is otherwise present
    # in `slot_data` from an older code path that predates this field.
    slot_status: dict[str, str] = Field(default_factory=dict)

    # ── Cluster C (risk_assessment Safety Probe port, ADR-042) ───────
    # Stateless-wire equivalent of `src.f1`'s in-process `_ProbeState`
    # dataclass (`src/safety_probe.py` holds the ported pure-function
    # logic that operates on these fields).
    probe_active: bool = False
    probe_awaiting_answer: bool = False
    probe_stage_idx: int = 0
    probe_trigger_utterance: str = ""
    probe_answers: list[str] = Field(default_factory=list)
    probe_protective_answer: str = ""
    # True once `risk_assessment` has been grounded THIS session by the
    # probe or the mandatory SI screen (never by caller-seeded/extractor
    # slot data — BUG-049's protection: only a real, run screening
    # counts). The `handoff_ready` termination gate
    # (`OrchestratorAgent._should_extract_slots`) will not fire from slot
    # coverage alone until this is True.
    risk_grounded: bool = False
    # True immediately after dialogue steering asked the mandatory SI
    # screen question (outside probe mode) and is awaiting the patient's
    # answer this turn.
    risk_question_pending: bool = False
    # BUG-079 (CVR-056 follow-up): True when the immediately-preceding SI
    # screen attempt failed to be answered — either a meta-utterance
    # (BUG-078) or a reply that arrived while `risk_question_pending` was
    # True but whose LITERAL prior question text never asked about SI
    # (`infer_literal_target_slot` mismatch, the same over-attribution risk
    # BUG-077 item B closed for the bare-denial path, applied here to
    # Cluster C). Consumed (read + reset False) exactly once, by
    # `OrchestratorAgent._resolve_dialogue_probe_instruction`, which is the
    # ONLY place `risk_question_pending` is ever set True — so setting this
    # flag never itself arms `risk_question_pending`; it only forces that
    # single choke point to re-select the SI screen as THIS turn's render
    # target, guaranteeing `risk_question_pending` is armed exclusively on
    # a turn where the SI screen instruction is actually returned to be
    # rendered (never a stale/inline force-arm on an unrelated turn).
    risk_screen_retry_needed: bool = False

    # ── Cluster G (post-handoff once-fire guard, ADR-043) ────────────
    # True once the pipeline has reached a TERMINAL outcome this session —
    # either a real handoff (`handoff_ready=True`), the ADR-044
    # backstop-escalation terminal state below, OR (BUG-086 fix,
    # 2026-07-25) an ordinary regenerate-budget-exhausted/reject/
    # exception outcome. Checked at the TOP of `_execute_pipeline` (after
    # the mandatory safety gate) so the post-dialogue pipeline (slot
    # extraction + handoff generation + verification) never re-runs on a
    # subsequent turn purely because `current_stage == completed`.
    #
    # BUG-086 (qa, live-reproduced session `2671d9fe`): this field used to
    # stay False on a regenerate/reject/exception outcome ("those
    # legitimately retry next turn" was the original design intent) — but
    # `OrchestratorAgent._run_post_dialogue_pipeline` already
    # unconditionally sets `state.current_stage = SessionStage.completed`
    # regardless of that outcome, so the "retry" this comment used to
    # describe never actually re-entered `dialogue_loop` to gather new
    # information anyway — it just re-ran the ENTIRE ~50s LLM chain from
    # scratch on IDENTICAL data and hit the same non-terminal outcome
    # again, forever, on every subsequent turn (confirmed live: turns 11
    # and 12 both took the identical ~50-58s shape and were both silently
    # dropped by apps/api's `ChatResponse.assistant_response(min_length=1)`
    # contract because the assistant_response was empty on that path —
    # see `handoff_unverified` below for the accompanying message fix).
    # Latching here converts that permanent silent stall into a single
    # terminal outcome the patient sees ONE ack for.
    handoff_delivered: bool = False

    # BUG-086 fix (additive): True once `_run_post_dialogue_pipeline`
    # reached its terminal `completed` outcome WITHOUT producing a
    # verified handoff report AND WITHOUT the `risk_screening_incomplete`
    # escalation (i.e. the evidence verifier rejected the report, the
    # regenerate budget was exhausted, or the pipeline raised an
    # exception — see that method's own final block). Read by
    # `OrchestratorAgent._build_post_handoff_result` on every SUBSEQUENT
    # turn of this session to pick the correct terminal message
    # (`_HANDOFF_ACK_MESSAGE`) instead of the real-success
    # `_POST_HANDOFF_MESSAGE` or the `_INCOMPLETE_INTAKE_MESSAGE`
    # escalation text — distinct terminal state from both of those.
    handoff_unverified: bool = False

    # BUG-090 fix (additive): True for exactly one turn — set the instant
    # `_should_extract_slots` first fires termination criteria (coverage
    # threshold + risk-grounded, or the max-turns backstop), consumed
    # (read + reset False) at the TOP of the very NEXT `process_turn`
    # call for this session. ai-server has no cross-request session store
    # (the caller round-trips `session_state` as an opaque dict on every
    # call — a fresh `SessionState` is deserialized from THAT payload
    # every time, never the in-process object from a prior call), so an
    # in-process `asyncio.create_task` background job spawned on the
    # termination turn could never durably deliver its result into a
    # FUTURE `process_turn` call anyway — "lazy, resumed on the next
    # request" is therefore the only deferral mechanism available without
    # adding a session store to ai-server (out of scope this pass, see
    # BUG-090's RESULT discussion). While this flag is True, the patient
    # has already been shown the stage-1 ack
    # (`_HANDOFF_ACK_MESSAGE`/`_INCOMPLETE_INTAKE_MESSAGE`) and the
    # expensive slot-extraction + handoff-generation + evidence-
    # verification chain has NOT run yet for this session.
    pending_handoff_pipeline: bool = False

    # ── ADR-044 (CVR-043 pin-fix, backstop vs risk-grounding gate) ───
    # True once `_MAX_DIALOGUE_TURNS` was reached this session while
    # `risk_grounded` was still False — i.e. the hard turn ceiling fired
    # before the mandatory SI screen/probe ever grounded risk_assessment.
    # Per ADR-042's absolute claim ("risk_grounded before handoff_ready"),
    # this MUST suppress `handoff_ready` (never silently ship a "ready"
    # signal built on an ungrounded risk_assessment) — enforced in
    # `OrchestratorAgent._run_post_dialogue_pipeline`/`_execute_pipeline`.
    # Sticky for the rest of the session once set (a clinician-facing
    # fact about how this specific session concluded, not something a
    # later turn's grounding — none can occur, since the session is now
    # terminal — could un-set). Surfaced on the wire via
    # `OrchestratorTurnResult.clinical_escalation_required` /
    # `DialogueOutput.clinical_escalation_required`, and distinctly from
    # `SafetyStatus.requires_human_review` (that flag is per-turn safety
    # classification; this flag is "this session's intake ended with an
    # unadministered/unresolved safety screen — clinician must follow up
    # before treating the session as a routine completed intake").
    risk_screening_incomplete: bool = False


# ── Orchestrator I/O ────────────────────────────────────────────────


class OrchestratorInput(BaseModel):
    """Per-turn input to the orchestrator."""

    session_id: str
    patient_id: str = ""
    input_type: InputType = InputType.text
    raw_input: str = ""
    # Coverage-seeding fix (orchestrator design decision, approved): in the
    # stateless deployment the BACKEND owns slot accumulation
    # (`POST /ai/slots/extract` → `filled_slots` on each chat request) —
    # the SAME session-accumulated map already threaded into `DialogueInput.
    # filled_slots` by `routes/chat.py`. `process_turn` unions this into
    # `state.slot_data` each turn (never overwriting an existing internal
    # value) so `handoff_ready` can fire from backend-driven coverage
    # (>= 0.7, `ALL_SLOT_KEYS`/12 canonical) organically, not only via the
    # turn-count ceiling backstop.
    filled_slots: dict[str, str] = Field(default_factory=dict)
    session_state: SessionState | None = None
    # For first turn, session_state may be None → orchestrator creates it.


class OrchestratorTurnResult(BaseModel):
    """Per-turn output from the orchestrator.

    Contains the assistant response (if any), updated session state,
    and flags for the caller.
    """

    session_id: str
    current_stage: SessionStage
    assistant_response: str = ""
    safety_status: SafetyStatus = Field(default_factory=SafetyStatus)
    # Mirrors `SessionState.slot_coverage` — see that field's docstring for
    # the B5 patient-fillable-denominator semantics (additive change).
    slot_coverage: float = 0.0
    crisis_triggered: bool = False
    requires_human_review: bool = False
    # BUG-047: CTRS 3 (ACUTE) + suicidal_ideation/self_harm category this
    # turn — short of the full crisis bypass (`crisis_triggered`, CTRS 1-2
    # only), but still SI-adjacent enough to warrant an in-turn 109
    # reminder. Set by `OrchestratorAgent._execute_pipeline` (same
    # `src.schemas.common.should_trigger_soft_safety` predicate `src.f1`'s
    # own probe mechanism uses) on the non-bypass (dialogue_loop
    # continuation) path only. The caller (`routes/chat.py`, which alone
    # holds the DialogueAgent-generated `assistant_response` text for this
    # path) appends `src.schemas.common.SOFT_SAFETY_NOTE` when this is True
    # — never appended here, since `assistant_response` is still empty at
    # the point this result is built.
    pending_soft_safety: bool = False
    # Cluster C (ADR-042): the probe/mandatory-SI-screen instruction (if
    # any) `routes/chat.py` must thread into DialogueAgent's
    # `session_state` dict this turn — mirrors how `prior_missing_slots`
    # is already threaded, so DialogueAgent needs no orchestrator-specific
    # knowledge (it already reads `session_state["probe_instruction"]`,
    # a mechanism previously only ever populated by `src.f1`'s harness).
    probe_instruction: str | None = None
    handoff_ready: bool = False
    # ADR-044 (CVR-043 pin-fix): mirrors `SessionState.risk_screening_
    # incomplete` — True when this turn concluded the session via the
    # backstop-vs-risk-grounding gate rather than a real handoff.
    # `handoff_ready` is always False and `handoff_report` is always None
    # whenever this is True (the gate blocks both, never a partial leak).
    clinical_escalation_required: bool = False
    handoff_report: dict[str, Any] | None = None
    # Mirrors `SessionState.verifier_issue_log` — see that field's
    # docstring (BUG-050 observability fix).
    verifier_issue_log: list[str] = Field(default_factory=list)
    session_state: SessionState
    stage_history: list[StageRecord] = Field(default_factory=list)
    error: str | None = None
