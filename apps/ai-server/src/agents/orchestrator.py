"""Orchestrator agent — rule-based state machine for the Task 1 pipeline.

Manages the full pre-consultation flow:
  input_received → safety_gate → context_retrieval → dialogue_loop
  → slot_extraction → handoff_generation → evidence_verification → handoff_delivery

CTRS 1-2 at any point → crisis_flow (immediate).
All routing decisions are rule-based — no LLM call in this agent.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src import safety_probe
from src.agents.base import BaseAgent
from src.agents.clinical_slot import (
    ALL_SLOT_KEYS,
    ESSENTIAL_SLOT_KEYS,
    PATIENT_FILLABLE_SLOTS,
    ClinicalSlotAgent,
)
from src.agents.dialogue import DialogueAgent
from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
)
from src.agents.handoff_generator import HandoffGeneratorAgent
from src.agents.safety_classifier import SafetyClassifierAgent
from src.grounding import (
    QUESTIONABLE_SLOT_KEYS,
    RISK_SLOT_KEY,
    evaluate_slot_grounding,
    infer_literal_target_slot,
    is_meta_utterance,
    reply_has_negation,
    reply_is_dont_know,
    verdict_to_slot_status,
)
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.clinical_slot import ClinicalSlotInput
from src.schemas.common import CTRSLevel, RiskLevel, should_trigger_soft_safety
from src.schemas.handoff import HandoffInput, ScaleScore, SlotData
from src.schemas.orchestrator import (
    OrchestratorInput,
    OrchestratorTurnResult,
    SafetyStatus,
    SessionStage,
    SessionState,
    StageRecord,
)
from src.schemas.safety import SafetyInput
from src.scoring.survey_scorer import ScoreResult, score_survey

logger = logging.getLogger(__name__)

# Slot coverage threshold to exit dialogue loop
_SLOT_COVERAGE_THRESHOLD = 0.7

# BUG-051 (CVR-039): once-per-session latch re-arm window for the
# BUG-047 soft-safety note — a NEW escalation at least this many turns
# after the last note was sent is still allowed to re-fire (never a
# permanent one-shot-forever silence); anything sooner is suppressed as
# a repeat of the same still-ongoing episode. Simple, documented rule —
# not derived from any external threshold.
_SOFT_SAFETY_REARM_TURNS = 5

# Maximum dialogue turns before forcing slot extraction
_MAX_DIALOGUE_TURNS = 20

# ADR-044 (CVR-043 pin-fix, cluster item 6): number of turns immediately
# BEFORE `_MAX_DIALOGUE_TURNS` during which the mandatory SI screen is
# forced onto dialogue steering even if other question-able slots remain
# unfilled — closes the CVR-043 finding-1 gap where the SI screen's
# normal "only once every OTHER question-able slot is filled" priority
# let the hard backstop preempt it, potentially for the whole session.
# This does not fully resolve finding 1's broader universal-screening
# critique (asking SI only near the end of a session, rather than early,
# is still not ideal) — that is a larger design question this pin-fix
# wave does not reopen — but it guarantees the screen is at least
# ATTEMPTED before the backstop can silently terminate the session
# without it ever having been asked.
_SI_SCREEN_RESERVE_TURNS = 4

# Crisis CTRS levels
_CRISIS_CTRS = {CTRSLevel.EMERGENCY, CTRSLevel.HIGH_RISK}

# Maximum handoff regeneration attempts
_MAX_HANDOFF_REGEN = 2

# Cluster A (asked-slot generalized fix, EXP-030): after this many
# consecutive turns a slot was targeted by dialogue steering and remained
# unfilled at the start of the next turn, the slot is deferred — dialogue
# steering stops re-selecting it for the remainder of the session. N=2
# per the approved design (`experiments/EXP-030/plan.md` cluster A row).
_ASK_DEFER_THRESHOLD = 2

# BUG-072: max length (chars) of a patient reply that is still eligible
# for the direct bare-denial compose path in `_update_asked_slot_tracking`
# — deliberately short (a plain "없어요."/"아니요, 없어요." class reply),
# so a longer answer mixing a negation morpheme with real substantive
# content is never short-circuited away from the real extractor path.
_BARE_DENIAL_MAX_CHARS = 12

# risk_assessment is never deferred by the Cluster A counter above — it is
# governed exclusively by the Cluster C probe/termination gate (safety-
# critical; giving up on it would defeat the termination gate entirely).
_NON_DEFERRABLE_SLOTS: frozenset[str] = frozenset({RISK_SLOT_KEY})

# Cluster G (post-handoff once-fire guard, ADR-043): the message shipped
# on every turn AFTER the session's handoff report has already been
# delivered — replaces re-running the full slot-extraction +
# handoff-generation + evidence-verification pipeline on every subsequent
# turn purely because `slot_coverage` stays above threshold forever.
_POST_HANDOFF_MESSAGE = (
    "사전문진이 이미 완료되어 상담원에게 인계되었습니다. 추가로 나누고 싶은 "
    "이야기가 있다면 말씀해 주세요 — 상담원이 확인 후 연락드리겠습니다."
)

# ADR-044 (CVR-043 pin-fix): patient-facing message when the session
# terminated via the backstop-vs-risk-grounding gate (`risk_screening_
# incomplete`) rather than a real handoff. Deliberately calm/non-alarming
# for the patient (never surfaces "safety screening incomplete" wording
# to the patient themselves) — the clinician-facing urgency signal is
# carried separately on the wire (`clinical_escalation_required`,
# `SessionState.risk_screening_incomplete`), never in this text. Patient
# is NOT stranded: the session still ends with a clear, benign next step.
_INCOMPLETE_INTAKE_MESSAGE = (
    "사전문진 내용을 상담원에게 전달드렸습니다. 안전과 관련해 조금 더 확인이 "
    "필요한 부분이 있어, 상담원이 곧 연락드려 이어서 확인하겠습니다. 지금 더 "
    "나누고 싶은 이야기가 있다면 편하게 말씀해 주세요."
)

# BUG-086/BUG-090 (2026-07-25): single source of truth for the "stage-1"
# closing ack — shipped the instant slot-coverage/risk-grounded
# termination criteria are met (BUG-090: immediately, never gated behind
# the expensive slot-extraction + handoff-generation + evidence-
# verification chain), and reused verbatim as the non-empty fallback
# whenever that deferred chain later completes WITHOUT a verified report
# and WITHOUT the risk-screening-incomplete escalation (BUG-086: an
# orchestrator turn result's `assistant_response` must never be the empty
# string — apps/api's `ChatResponse.assistant_response` contract
# (`min_length=1`, `packages/shared-contracts/python/src/contracts/
# chat.py`) rejects "" outright and silently drops the entire turn, with
# no once-fire latch engaging afterward — see BUG-086's error.md entry
# for the live-reproduced permanent stall this caused). Previously
# duplicated as a bare string literal in `routes/chat.py`'s Step 3
# branch; that call site now reads `OrchestratorTurnResult.
# assistant_response` instead of re-declaring the text.
_HANDOFF_ACK_MESSAGE = (
    "네 알겠습니다. 답변 주신 내용을 토대로 증상 확인 중입니다."
)

# Crisis response messages per CTRS level
_CRISIS_MESSAGES: dict[CTRSLevel, str] = {
    CTRSLevel.EMERGENCY: (
        "지금 많이 위급한 상황이시군요. 즉시 119 또는 112에 연락해 주세요. "
        "자살예방상담전화 109도 24시간 운영되고 있습니다. "
        "당신의 안전이 가장 중요합니다."
    ),
    CTRSLevel.HIGH_RISK: (
        "지금 많이 힘드시군요. 당신의 이야기를 듣고 있습니다. "
        "혼자 감당하지 않으셔도 됩니다. "
        "자살예방 통합상담전화 109로 연락해 주세요. 24시간 상담할 수 있어요."
    ),
}

# BUG-051 (CVR-039 recommendation — mirror the same history-decontamination
# discipline for crisis messages, same echo risk as SOFT_SAFETY_NOTE): the
# fixed CTRS 1-2 crisis-bypass template strings, public so `routes/chat.py`
# can strip them from a LATER turn's conversation_history before it reaches
# DialogueAgent — never re-authored/duplicated, single source of truth.
CRISIS_MESSAGE_TEXTS: frozenset[str] = frozenset(_CRISIS_MESSAGES.values())

# Essential slot list for coverage tracking
_ESSENTIAL_SLOTS = ESSENTIAL_SLOT_KEYS


class OrchestratorAgent(BaseAgent):
    """Rule-based state machine orchestrating the clinical pipeline."""

    def __init__(
        self,
        model_router: ModelRouter,
        prompt_loader: PromptLoader,
    ) -> None:
        self._model_router = model_router
        self._prompt_loader = prompt_loader
        # Sub-agents are created lazily
        self._safety_agent: SafetyClassifierAgent | None = None
        self._slot_agent: ClinicalSlotAgent | None = None
        self._handoff_agent: HandoffGeneratorAgent | None = None
        self._verifier_agent: EvidenceVerifierAgent | None = None

    @property
    def agent_name(self) -> str:
        return "orchestrator"

    def _get_safety_agent(self) -> SafetyClassifierAgent:
        if self._safety_agent is None:
            self._safety_agent = SafetyClassifierAgent(
                model_router=self._model_router,
                prompt_loader=self._prompt_loader,
            )
        return self._safety_agent

    def _get_slot_agent(self) -> ClinicalSlotAgent:
        if self._slot_agent is None:
            self._slot_agent = ClinicalSlotAgent(
                model_router=self._model_router,
                prompt_loader=self._prompt_loader,
            )
        return self._slot_agent

    def _get_handoff_agent(self) -> HandoffGeneratorAgent:
        if self._handoff_agent is None:
            self._handoff_agent = HandoffGeneratorAgent(
                model_router=self._model_router,
                prompt_loader=self._prompt_loader,
            )
        return self._handoff_agent

    def _get_verifier_agent(self) -> EvidenceVerifierAgent:
        if self._verifier_agent is None:
            self._verifier_agent = EvidenceVerifierAgent()
        return self._verifier_agent

    # ── Public API ──────────────────────────────────────────────────

    async def run(self, inp: Any, **kwargs: Any) -> OrchestratorTurnResult:
        """Execute one orchestrator turn.

        Accepts OrchestratorInput directly (not AgentInput) because the
        orchestrator is the top-level coordinator, not a leaf agent.
        """
        if not isinstance(inp, OrchestratorInput):
            raise TypeError(f"Expected OrchestratorInput, got {type(inp).__name__}")
        return await self.process_turn(inp)

    async def process_turn(self, inp: OrchestratorInput) -> OrchestratorTurnResult:
        """Process a single patient turn through the state machine.

        For the dialogue phase, each call handles one turn (safety → dialogue).
        When slot coverage reaches threshold or max turns, transitions to
        slot_extraction → handoff pipeline automatically.
        """
        # Initialize or restore session state
        state = inp.session_state or SessionState(
            session_id=inp.session_id,
            patient_id=inp.patient_id,
        )

        try:
            result = await self._execute_pipeline(inp, state)
        except Exception as exc:
            logger.error("Orchestrator pipeline error: %s", exc, exc_info=True)
            state.current_stage = SessionStage.error
            state.error_log.append(f"{datetime.now().isoformat()}: {exc}")
            result = OrchestratorTurnResult(
                session_id=state.session_id,
                current_stage=SessionStage.error,
                session_state=state,
                stage_history=state.stage_history,
                error=str(exc),
            )

        return result

    # ── Pipeline execution ──────────────────────────────────────────

    async def _execute_pipeline(
        self, inp: OrchestratorInput, state: SessionState
    ) -> OrchestratorTurnResult:
        """Run stages sequentially until we need to wait for next user input.

        Single coordinated change (EXP-030 Phase 2, clusters A/#1 + C/#3 +
        G/#9 — see `experiments/EXP-030/plan.md` cross-cluster note): all
        three touch this one method, so they are sequenced as ONE guard
        flow rather than three independent early-returns:
          1. safety gate (unchanged — mandatory every turn, always first)
          2. crisis check (unchanged — returns before anything below)
          3. Cluster G: post-handoff terminal guard (checked immediately
             AFTER the safety/crisis checks above, never before — this
             preserves the safety-gate-before-coverage invariant: a
             post-handoff crisis utterance already exited via the crisis
             branch, so this guard only ever sees non-crisis turns)
          4. Cluster A: resolve last turn's asked-slot outcome
          5. Cluster C: advance the safety-probe state machine with this
             turn's answer/trigger check (so `risk_grounded` reflects
             reality before the termination gate below)
          6. `_should_extract_slots` — now gated on `risk_grounded` too
             (Cluster C termination gate), on top of the existing
             coverage/turn-count checks
          7. Cluster A: resolve this turn's dialogue-steering target (for
             next turn's asked-slot check) / Cluster C: resolve this
             turn's probe instruction (mutually exclusive — probe/SI-
             screen suspends round-robin exactly as `f1.py` does)
        """

        # Stage 1: Input received
        state.current_stage = SessionStage.input_received
        self._record_stage(state, SessionStage.input_received, "orchestrator", "pass")

        # Stage 2: Safety gate (mandatory, every turn)
        safety_result = await self._run_safety_gate(inp, state)

        if state.current_stage == SessionStage.crisis_flow:
            return self._build_crisis_result(state, safety_result)

        # Cluster G (ADR-043): post-handoff terminal guard. Only reached
        # once `state.handoff_delivered` is True (set at the end of
        # `_run_post_dialogue_pipeline` below) — never re-runs slot
        # extraction or the handoff-generation+verification pipeline on a
        # subsequent turn. Placed AFTER the crisis check above (never
        # before), so a post-handoff crisis disclosure already returned
        # via `_build_crisis_result` and is unaffected by this guard.
        if state.handoff_delivered:
            state.turn_count += 1
            if inp.raw_input:
                state.conversation_history.append({
                    "role": "user",
                    "content": inp.raw_input,
                })
            return self._build_post_handoff_result(state)

        # BUG-090: lazy-resume guard. Only reached once `state.
        # pending_handoff_pipeline` is True (set below, the instant
        # termination criteria were first met on a PRIOR turn — see
        # that field's own schema docstring for why this "resume on the
        # next request" shape, rather than an in-process background
        # task, is the only deferral mechanism available without adding a
        # session store to ai-server). THIS turn is where the deferred
        # slot-extraction + handoff-generation + evidence-verification
        # chain actually runs — mirrors Cluster G's own turn-count/
        # conversation-history bookkeeping (placed AFTER the crisis check
        # and Cluster G's own guard above, so a post-handoff crisis
        # disclosure or an already-fully-delivered session are both
        # unaffected by this branch; the two guards are mutually
        # exclusive by construction — `_run_post_dialogue_pipeline` below
        # always sets `handoff_delivered = True` before returning, so a
        # session is never `pending_handoff_pipeline` and
        # `handoff_delivered` at once).
        if state.pending_handoff_pipeline:
            state.pending_handoff_pipeline = False
            state.turn_count += 1
            if inp.raw_input:
                state.conversation_history.append({
                    "role": "user",
                    "content": inp.raw_input,
                })
            result = await self._run_post_dialogue_pipeline(state)
            state.handoff_delivered = True  # BUG-086: latch unconditionally
            return result

        # Stage 3: Context retrieval (first turn only, or when needed)
        if state.turn_count == 0:
            await self._run_context_retrieval(state)

        # Stage 4: Dialogue loop — return response and wait for next input
        state.current_stage = SessionStage.dialogue_loop
        state.turn_count += 1

        # Add user message to conversation history
        if inp.raw_input:
            state.conversation_history.append({
                "role": "user",
                "content": inp.raw_input,
            })

        # Coverage seeding (orchestrator design decision, approved): the
        # stateless backend owns slot accumulation (`POST /ai/slots/extract`
        # → `filled_slots` on each chat request) — union it into
        # `state.slot_data` BEFORE this turn's coverage/handoff-ready check,
        # so backend-accumulated slots drive `handoff_ready` organically
        # instead of only the turn-count ceiling below.
        self._seed_slot_data_from_caller(state, inp.filled_slots)

        # Cluster A (asked-slot generalized fix): resolve LAST turn's
        # outcome (was `state.pending_target_slot` answered by the message
        # just appended above?) BEFORE computing this turn's coverage/
        # target — mirrors f1.py's own per-turn targeted_slot bookkeeping.
        self._update_asked_slot_tracking(state)

        # Cluster C (ADR-042): advance the ported Safety Probe state
        # machine with THIS turn's incoming answer/trigger check, so
        # `state.risk_grounded` reflects reality before the termination
        # gate (`_should_extract_slots`) is evaluated below.
        if self._advance_safety_probe(inp, state, safety_result):
            # Belt-and-braces lexical escalation (plan/means disclosure) —
            # treat exactly like a crisis-flow safety-gate hit.
            state.current_stage = SessionStage.crisis_flow
            return self._build_crisis_result(state, safety_result)

        # Check if we should exit dialogue and move to slot extraction
        # (Cluster C termination gate lives inside this call now — coverage
        # crossing the threshold is necessary but no longer sufficient on
        # its own until risk_assessment is grounded).
        if self._should_extract_slots(state):
            # BUG-090 (user-directed UX redesign, 2026-07-25): termination
            # criteria (coverage threshold + risk-grounded, or the max-
            # turns backstop) are met THIS turn — ship the stage-1 ack
            # IMMEDIATELY instead of blocking this turn's response behind
            # the expensive slot-extraction + handoff-generation +
            # evidence-verification chain (`_run_post_dialogue_pipeline`,
            # live-measured 49-58s). That chain is deferred to the NEXT
            # `process_turn` call for this session (picked up by the
            # `pending_handoff_pipeline` guard above — see that field's
            # schema docstring for why "resume on next request" is the
            # only sound deferral shape here, ai-server having no cross-
            # request session store). `state.risk_screening_incomplete`
            # is already known synchronously (no LLM call required) —
            # the escalation ack ships on THIS turn too, never delayed,
            # so the clinician-facing urgency signal (`clinical_
            # escalation_required`) reaches the caller no later than
            # before this change (in fact strictly earlier — previously
            # it also waited behind the same 49-58s chain).
            state.pending_handoff_pipeline = True
            escalation = state.risk_screening_incomplete
            self._record_stage(
                state, SessionStage.slot_extraction, "orchestrator",
                "pass" if not escalation else "skip",
                "termination criteria met — handoff pipeline deferred to "
                "next turn (BUG-090)"
                + (", risk_screening_incomplete (ADR-044)" if escalation else ""),
            )
            return OrchestratorTurnResult(
                session_id=state.session_id,
                current_stage=SessionStage.completed,
                assistant_response=(
                    _INCOMPLETE_INTAKE_MESSAGE if escalation else _HANDOFF_ACK_MESSAGE
                ),
                safety_status=state.safety_status,
                slot_coverage=state.slot_coverage,
                handoff_ready=False,
                clinical_escalation_required=escalation,
                session_state=state,
                stage_history=state.stage_history,
            )

        # Still in dialogue — return turn result for caller to generate response
        self._record_stage(state, SessionStage.dialogue_loop, "03_dialogue", "continue")
        self._update_slot_coverage(state)

        # BUG-047: same trigger predicate `src.f1` uses for its own
        # soft-safety probe — computed from THIS turn's raw safety result
        # (`safety_result.categories` has no counterpart on `SafetyStatus`,
        # so read it here, not re-derived from state). `safety_result` is
        # guaranteed non-None on this path (a safety-gate failure sets
        # `current_stage=crisis_flow`, which returns earlier above) — the
        # `bool(safety_result and ...)` guard is defensive only.
        pending_soft_safety = bool(
            safety_result
            and should_trigger_soft_safety(safety_result.ctrs_level, safety_result.categories)
            and self._soft_safety_latch_allows(state)
        )
        # BUG-051 (CVR-039): latch is set HERE (the trigger-decision point),
        # optimistically — not deferred to `routes/chat.py` — so the
        # once-per-session guarantee holds for ANY caller of `process_turn`,
        # not only this specific route. `routes/chat.py`'s own same-turn
        # dedup (finding 1, model self-echo) is a SEPARATE, additional
        # layer that decides whether to actually append text this turn;
        # it never needs to touch the latch itself.
        if pending_soft_safety:
            state.soft_safety_note_sent = True
            state.soft_safety_note_last_turn = state.turn_count

        # Cluster A/C: resolve this turn's dialogue-steering directive
        # BEFORE returning — either the probe/mandatory-SI-screen
        # instruction (Cluster C, suspends round-robin exactly like
        # `f1.py`) or, absent that, the round-robin target slot (Cluster
        # A, recorded so NEXT turn's `_update_asked_slot_tracking` above
        # can check whether it was answered). `routes/chat.py` threads
        # `probe_instruction` into DialogueAgent's `session_state` dict —
        # DialogueAgent already reads that key (previously only ever
        # populated by `src.f1`'s harness), so it needs no new code here.
        probe_instruction = self._resolve_dialogue_probe_instruction(state)
        if probe_instruction is None:
            target = DialogueAgent.compute_target_slot(
                state.slot_data, state.conversation_history,
                deferred_slots=set(state.deferred_slots),
            )
            state.pending_target_slot = target
            # Mirrors f1.py exactly: the PLAIN round-robin can independently
            # land on risk_assessment (it is essential and question-able,
            # not exclusive to the forced-SI-screen branch above) whenever
            # `_other_missing_risk_slots` is non-empty but risk_assessment
            # itself is still unfilled. Whichever branch produced this
            # target, if it is risk_assessment the NEXT turn's answer must
            # still be consumed as the screening answer — never tracked by
            # the Cluster A asked-slot counter (`_NON_DEFERRABLE_SLOTS`).
            if target == RISK_SLOT_KEY:
                state.risk_question_pending = True
                state.pending_target_slot = None
            # BUG-073 (single source of truth, additive): unlike
            # `pending_target_slot` — Cluster A's OWN bookkeeping field,
            # deliberately reset to None for risk_assessment since Cluster
            # A never counts/defers it — `dialogue_target_slot` always
            # records the REAL target, whatever it is, so a caller can
            # answer "what is dialogue asking about this turn" without
            # knowing which of the two mechanisms picked it.
            state.dialogue_target_slot = target
        else:
            state.pending_target_slot = None  # risk_assessment is never deferred/tracked
            # The probe/mandatory-SI-screen path always targets
            # risk_assessment (that IS what `probe_instruction`/
            # `SI_SCREEN_INSTRUCTION` asks about) — record it here too.
            state.dialogue_target_slot = RISK_SLOT_KEY

        return OrchestratorTurnResult(
            session_id=state.session_id,
            current_stage=SessionStage.dialogue_loop,
            safety_status=state.safety_status,
            slot_coverage=state.slot_coverage,
            pending_soft_safety=pending_soft_safety,
            probe_instruction=probe_instruction,
            session_state=state,
            stage_history=state.stage_history,
        )

    # ── Safety gate ─────────────────────────────────────────────────

    async def _run_safety_gate(
        self, inp: OrchestratorInput, state: SessionState
    ) -> Any:
        """Run SafetyClassifier on the current input. Returns SafetyOutput."""
        state.current_stage = SessionStage.safety_gate

        safety_agent = self._get_safety_agent()
        safety_input = SafetyInput(
            session_id=state.session_id,
            user_message=inp.raw_input,
            conversation_history=state.conversation_history,
        )

        try:
            result = await safety_agent.run(safety_input)
        except Exception as exc:
            # Safety failure → assume CTRS 2 (safe-side default)
            logger.error("Safety gate failed: %s — assuming CTRS 2", exc)
            state.safety_status = SafetyStatus(
                ctrs_level=CTRSLevel.HIGH_RISK,
                risk_level=RiskLevel.high,
                crisis_triggered=True,
                # Safe-side default: CTRS 2 is within the CTRS<=3 review band
                # (safety_classifier.py's own `ctrs <= CTRSLevel.ACUTE` rule)
                # — a safety-gate failure must never silently ship
                # requires_human_review=False.
                requires_human_review=True,
                last_checked_at=datetime.now(),
            )
            state.current_stage = SessionStage.crisis_flow
            state.error_log.append(f"Safety gate timeout/failure: {exc}")
            self._record_stage(state, SessionStage.safety_gate, "02_safety_classifier", "fail")
            return None

        # Update safety status
        state.safety_status = SafetyStatus(
            ctrs_level=result.ctrs_level,
            risk_level=result.risk_level,
            crisis_triggered=result.crisis_protocol_activated,
            # BUG-046: threaded from SafetyOutput.requires_human_review
            # (safety_classifier.py's `ctrs <= CTRSLevel.ACUTE` computation)
            # — previously never read here at all.
            requires_human_review=result.requires_human_review,
            last_checked_at=datetime.now(),
            # BUG-060/CVR-051 follow-up: real category signal, not re-derived.
            categories=list(result.categories),
        )

        # Check for crisis
        if result.ctrs_level in _CRISIS_CTRS:
            state.current_stage = SessionStage.crisis_flow
            self._record_stage(
                state, SessionStage.safety_gate, "02_safety_classifier",
                "crisis", f"CTRS {int(result.ctrs_level)}"
            )
        else:
            self._record_stage(
                state, SessionStage.safety_gate, "02_safety_classifier",
                "pass", f"CTRS {int(result.ctrs_level)}"
            )

        return result

    # ── Context retrieval ───────────────────────────────────────────

    async def _run_context_retrieval(self, state: SessionState) -> None:
        """Retrieve prior context (temporal data, prior handoffs).

        Cross-session trend context is out of scope for this state
        machine — that analysis is owned entirely by a separate,
        stateless module (see the F4 stage of `continuous_test.py`),
        never called from here (HPI-isolation, see
        `tests/test_f4_hpi_isolation.py`).
        """
        state.current_stage = SessionStage.context_retrieval

        # For first-visit patients, this is a no-op anyway.
        if state.is_first_visit:
            self._record_stage(
                state, SessionStage.context_retrieval, "context_retrieval",
                "skip", "first visit — no prior context"
            )
        else:
            self._record_stage(
                state, SessionStage.context_retrieval, "context_retrieval",
                "skip", "cross-session trend context out of scope for this module"
            )

    # ── Slot coverage check ─────────────────────────────────────────

    def _should_extract_slots(self, state: SessionState) -> bool:
        """Decide whether to exit dialogue and proceed to slot extraction.

        Cluster C termination gate (ADR-042): coverage crossing
        `_SLOT_COVERAGE_THRESHOLD` is necessary but no longer SUFFICIENT
        on its own — the session may not terminate on slot-completion
        until `risk_assessment` has actually been grounded by the safety
        probe/mandatory SI screen (`state.risk_grounded`), mirroring
        `f1.py`'s own `risk_grounded` termination condition
        (`not other_missing and risk_grounded`). The `_MAX_DIALOGUE_TURNS`
        backstop below is an intentional exception — an absolute ceiling
        that still fires regardless of risk-grounding status, so a
        session can never loop forever.

        ADR-044 (CVR-043 pin-fix, item 6): a session that hits this
        backstop ungrounded no longer ships an ordinary "확인 필요"
        handoff silently — it sets `state.risk_screening_incomplete`,
        which `OrchestratorAgent._run_post_dialogue_pipeline` reads to
        force `handoff_ready=False` + `clinical_escalation_required=True`
        instead of a routine ready-for-pickup signal (ADR-042's absolute
        claim: no `handoff_ready` before `risk_grounded`, enforced even at
        the one place a bare coverage/turn check used to bypass it).
        """
        self._update_slot_coverage(state)

        if state.turn_count >= _MAX_DIALOGUE_TURNS:
            if not state.risk_grounded:
                state.risk_screening_incomplete = True
                logger.warning(
                    "ADR-044: max turns %d reached with risk_assessment "
                    "still NOT grounded — terminating session (not looping "
                    "forever) but suppressing handoff_ready and flagging "
                    "clinical_escalation_required instead of a silent "
                    "ready-for-handoff signal (session_id=%s)",
                    _MAX_DIALOGUE_TURNS, state.session_id,
                )
            else:
                logger.info(
                    "Max turns %d reached — forcing slot extraction (hard "
                    "backstop; risk_assessment already grounded, so this "
                    "does not trigger the ADR-044 escalation gate)",
                    _MAX_DIALOGUE_TURNS,
                )
            return True

        if state.slot_coverage >= _SLOT_COVERAGE_THRESHOLD:
            if not state.risk_grounded:
                logger.info(
                    "Slot coverage %.2f >= %.2f but risk_assessment is not "
                    "yet grounded — termination gate (ADR-042) holds the "
                    "session in dialogue_loop until the safety probe/SI "
                    "screen grounds it",
                    state.slot_coverage, _SLOT_COVERAGE_THRESHOLD,
                )
                return False
            logger.info(
                "Slot coverage %.2f >= %.2f and risk_assessment grounded — "
                "moving to extraction",
                state.slot_coverage, _SLOT_COVERAGE_THRESHOLD,
            )
            return True

        return False

    # ── Cluster A: asked-slot tracking (generalized fix) ─────────────

    @staticmethod
    def _last_user_message(state: SessionState) -> str:
        """The most recently appended patient utterance, or "" if the
        history is empty or its last turn is not a user turn."""
        history = state.conversation_history
        if history and history[-1].get("role") == "user":
            return history[-1].get("content", "") or ""
        return ""

    @staticmethod
    def _last_assistant_message(state: SessionState) -> str:
        """BUG-077: the rendered assistant turn immediately preceding the
        just-appended patient reply — i.e. `conversation_history[-2]` when
        `conversation_history[-1]` is the user turn `_execute_pipeline`
        just appended this turn. Returns "" when unavailable (e.g. the
        caller never threaded the assistant turn back via
        `add_assistant_turn` before this call — a gap in the caller's own
        history bookkeeping, not something this method can recover)."""
        history = state.conversation_history
        if (
            len(history) >= 2
            and history[-1].get("role") == "user"
            and history[-2].get("role") == "assistant"
        ):
            return history[-2].get("content", "") or ""
        return ""

    @staticmethod
    def _update_asked_slot_tracking(state: SessionState) -> None:
        """Resolve LAST turn's outcome before this turn's coverage/target
        are computed: was `state.pending_target_slot` (recorded at the
        end of the previous turn) filled by the reply that was just
        appended to `conversation_history`? If not — and it is not a
        `_NON_DEFERRABLE_SLOTS` member (risk_assessment, governed by
        Cluster C instead) — increment its miss counter and, at
        `_ASK_DEFER_THRESHOLD` misses, move it into `deferred_slots` so
        `DialogueAgent`'s round-robin steering stops re-selecting it for
        the rest of the session. Still surfaced in the handoff's
        missing-slots section — never silently dropped from the record.

        BUG-072 (direct-compose fix): before falling through to the miss
        counter, check whether the just-appended reply is itself an
        unambiguous bare denial (`reply_has_negation`) to the slot that
        was directly asked about. If so, ground it HERE — composing
        "없음(환자 부인: '<발화 인용>')" straight from the patient's own
        words, exactly the same no-template-fabrication discipline
        `safety_probe.compose_screen_risk_assessment` already uses for
        risk_assessment — rather than waiting on the async extractor
        LLM call (which may not even propose a value for a 2-character
        reply) or `has_lexical_evidence` (which structurally cannot pass
        for a single negation-only token, see `src.grounding._is_generic`).
        This closes the live repro (BUG-072, session `d2d9ba21`): a slot
        answered with a clean "없어" now grounds on the FIRST answer, so
        the miss counter — and the re-ask it would otherwise take 2 misses
        to suppress — never engages at all for this case.

        BUG-077 (attribution-accuracy fix on the above): before trusting
        `target` (the internally-recorded steering bookkeeping) as the
        slot to ground, this now checks what the PRIOR assistant turn's
        rendered text literally, recognizably asked about
        (`infer_literal_target_slot`, topic-keyword match — the live repro
        showed `target`/the literal rendered question can diverge). Three
        outcomes:
          - literal text unavailable (caller never threaded the assistant
            turn back) → trust `target` unchanged, same as pre-BUG-077.
          - literal slot == `target` → ground `target`, unchanged from
            pre-BUG-077 (the common, correctly-targeted case).
          - literal slot != `target` (a DIFFERENT specific slot, or None
            for an ambiguous/generic catch-all question) → `target` was
            NOT literally asked this turn, so it is never marked "denied"
            off this reply (closes the over-attribution symptom); when the
            literal slot is a real, different slot, THAT slot is grounded
            instead (closes the silent-non-capture symptom — e.g.
            `personal_social_history` asked in the rendered text but
            never grounded because `target` was `history_of_present_
            illness`). Either way, `target` itself falls through to its
            own ordinary miss-counter handling below, since it was not
            literally answered this turn.
        """
        target = state.pending_target_slot
        state.pending_target_slot = None
        if not target or target in _NON_DEFERRABLE_SLOTS:
            return

        if OrchestratorAgent._slot_is_filled(state.slot_data, target):
            state.asked_slot_counts.pop(target, None)
            # Never downgrade an already-"denied" status back to "filled"
            # just because the slot (still) has a value — "denied" IS a
            # filled state, just a more specific one a caller may want to
            # distinguish (BUG-072's whole point).
            if state.slot_status.get(target) != "denied":
                state.slot_status[target] = "filled"
            return

        last_reply = OrchestratorAgent._last_user_message(state)
        # BUG-072 scope guard: only a short, essentially-content-free reply
        # (the negation/don't-know signal itself IS the whole signal — "없
        # 어", "아니요", "안 해요", "잘 모르겠습니다") is composed directly.
        # A longer reply that happens to contain a negation/don't-know
        # morpheme alongside substantive content (e.g. "그건 없는데 요즘 잠을
        # 잘 못 자요") must still go through the real extractor/grounding
        # path so that substantive content is not discarded into a
        # boilerplate denial.
        #
        # Coordinator directive (2026-07-25, "수집-불가 응답의 즉시-이동
        # 규칙"): a "don't-know"/unanswerable reply ("잘 모르겠습니다") is
        # checked FIRST and separately from an active denial — both
        # `reply_is_dont_know` and `reply_has_negation` would match "모르"-
        # rooted text, but they are clinically distinct and must ground to
        # DIFFERENT `slot_status` values ("unknown" vs "denied") so the
        # record never mislabels "the patient doesn't know" as "the patient
        # denies". Either way, grounding here removes the slot from
        # `missing_questionable_slots` entirely (see `_slot_is_filled`,
        # value-presence only, independent of status) — this is a stronger,
        # IMMEDIATE resolution than the `_ASK_DEFER_THRESHOLD`-gated miss
        # counter below, so a don't-know/denial reply never has to survive
        # 2 unanswered asks before the round-robin moves on; it moves on
        # this very turn.
        reply_stripped = last_reply.strip() if last_reply else ""
        is_short_reply = bool(reply_stripped) and len(reply_stripped) <= _BARE_DENIAL_MAX_CHARS
        is_dont_know = is_short_reply and reply_is_dont_know(last_reply)
        is_bare_denial = is_short_reply and not is_dont_know and reply_has_negation(last_reply)

        if is_dont_know or is_bare_denial:
            status = "unknown" if is_dont_know else "denied"
            kind_label = "an unknown/don't-know answer" if is_dont_know else "a bare denial"

            def _compose_value(reply: str, _dont_know: bool = is_dont_know) -> str:
                return (
                    f"미상(환자 응답: '{safety_probe.clip(reply)}')" if _dont_know
                    else f"없음(환자 부인: '{safety_probe.clip(reply)}')"
                )

            last_ai_text = OrchestratorAgent._last_assistant_message(state)
            if last_ai_text:
                literal_slot = infer_literal_target_slot(last_ai_text)
                if literal_slot == RISK_SLOT_KEY:
                    # risk_assessment is governed exclusively by the
                    # safety-probe machine (_NON_DEFERRABLE_SLOTS) — never
                    # grounded from this path.
                    literal_slot = None
            else:
                # No rendered text on record to check against — trust
                # `target` unconditionally (pre-BUG-077 behavior).
                literal_slot = target

            if literal_slot == target:
                state.slot_data[target] = _compose_value(last_reply)
                state.slot_status[target] = status
                state.asked_slot_counts.pop(target, None)
                logger.info(
                    "Slot '%s' grounded as %s from the patient's own reply "
                    "(BUG-072/BUG-084 direct-compose) — no re-ask needed",
                    target, kind_label,
                )
                return

            if literal_slot is not None and not OrchestratorAgent._slot_is_filled(
                state.slot_data, literal_slot
            ):
                state.slot_data[literal_slot] = _compose_value(last_reply)
                state.slot_status[literal_slot] = status
                state.asked_slot_counts.pop(literal_slot, None)
                logger.info(
                    "BUG-077: %s literally answered '%s' (per the prior "
                    "turn's rendered question), not the internally-tracked "
                    "target '%s' — grounded to the literal slot; '%s' was "
                    "not literally asked this turn, so its own ask counter "
                    "still advances below",
                    kind_label, literal_slot, target, target,
                )
            elif literal_slot is None:
                logger.info(
                    "BUG-077: %s reply not grounded to target '%s' — the "
                    "prior turn's rendered question was ambiguous/generic "
                    "(no specific slot literally asked), so this reply is "
                    "not attributed to any slot; '%s' falls through to its "
                    "own ask counter below",
                    kind_label, target, target,
                )
            # target itself was NOT literally asked this turn — fall
            # through to its own miss-counter handling below (no early
            # return).

        count = state.asked_slot_counts.get(target, 0) + 1
        state.asked_slot_counts[target] = count
        if count >= _ASK_DEFER_THRESHOLD and target not in state.deferred_slots:
            state.deferred_slots.append(target)
            state.slot_status[target] = "missing"
            logger.info(
                "Slot '%s' asked %d times without an answer — deferring "
                "for the rest of the session (asked-slot generalized fix)",
                target, count,
            )

    # ── Cluster C: risk_assessment Safety Probe (ADR-042) ────────────

    @staticmethod
    def _other_missing_risk_slots(state: SessionState) -> list[str]:
        """The question-able slots OTHER than risk_assessment still
        missing — mirrors f1.py's own `other_missing` local exactly
        (`QUESTIONABLE_SLOT_KEYS` minus `RISK_SLOT_KEY`)."""
        return [
            s for s in QUESTIONABLE_SLOT_KEYS
            if s != RISK_SLOT_KEY and not OrchestratorAgent._slot_is_filled(state.slot_data, s)
        ]

    def _advance_safety_probe(
        self, inp: OrchestratorInput, state: SessionState, safety_result: Any
    ) -> bool:
        """Port of f1.py's graduated Safety Probe state machine
        (`src/safety_probe.py`), operating on `SessionState`'s `probe_*`
        primitive fields (the stateless-wire equivalent of f1.py's
        in-process `_ProbeState`) — no new server-side session store is
        introduced. Runs once per turn, BEFORE `_should_extract_slots`, so
        `state.risk_grounded` reflects THIS turn's incoming answer/trigger
        before the termination gate is evaluated.

        Returns True if this turn's answer triggered the belt-and-braces
        LEXICAL escalation (plan/means disclosure) — the caller must then
        treat this turn exactly like a crisis-flow safety-gate hit (the
        per-turn CTRS classification is the PRIMARY escalation path and is
        already handled earlier in `_execute_pipeline`; this is the same
        second, independent signal f1.py's own probe uses).

        BUG-078 (topic-relevance gate on the mandatory SI screen answer):
        the `risk_question_pending` branch below previously accepted
        `patient_message` verbatim as the SI screen's answer whenever it
        contained ANY negation morpheme (`reply_has_negation`), with no
        check that the reply actually answers the SI question. A patient
        meta-complaint about repetitive questioning ("없다니까 왜 자꾸
        물어봐요.") contains "없" and was fabricated into a permanent
        `risk_assessment` SI-denial citation, with `risk_grounded=True`
        then blocking the patient's real, later SI denial from ever being
        captured (`_resolve_dialogue_probe_instruction` short-circuits on
        `risk_grounded`). This now checks `is_meta_utterance` first — a
        meta-complaint neither grounds nor sets `risk_grounded`, leaving
        risk_assessment "still unanswered" so the existing SI-screen/
        round-robin machinery re-asks it later (immediately if the hard
        backstop is near or no other slot is missing, otherwise on its
        normal round-robin turn) instead of silently marking it answered.
        Safety-conservative default: when uncertain, leave risk_assessment
        ungrounded rather than fabricate a citation.
        """
        patient_message = inp.raw_input or ""
        probe_just_concluded = False

        if state.probe_active and state.probe_awaiting_answer:
            answered_stage = safety_probe.PROBE_STAGES[
                min(state.probe_stage_idx, len(safety_probe.PROBE_STAGES) - 1)
            ][0]
            # BUG-083 (BUG-079 parity, 2026-07-25): before scoring this
            # reply against `answered_stage`, verify the immediately-prior
            # rendered assistant text actually literally asked THAT
            # stage's topic. `_last_assistant_message` returns "" when the
            # caller never threaded conversation history back — trusted
            # unchanged in that case (same test/caller-bookkeeping fallback
            # BUG-079's own literal-target check uses). A topic mismatch
            # (dialogue rendered a DIFFERENT stage's question, or drifted
            # off-topic entirely) means this reply never actually answered
            # `answered_stage` — leave `probe_awaiting_answer=True` so the
            # SAME stage is re-rendered next turn instead of scoring an
            # off-topic reply against it (never advance/escalate/
            # de-escalate on a stage that was never actually asked).
            last_ai_text = OrchestratorAgent._last_assistant_message(state)
            if last_ai_text and safety_probe.infer_literal_probe_stage(
                last_ai_text
            ) != answered_stage:
                return False

            state.probe_awaiting_answer = False
            state.probe_answers.append(patient_message)
            outcome = safety_probe.classify_probe_answer(state.probe_stage_idx, patient_message)

            if outcome == "escalate":
                state.probe_active = False
                state.safety_status.crisis_triggered = True
                self._record_stage(
                    state, SessionStage.safety_gate, "safety_probe",
                    "crisis", "plan/means disclosure (lexical check)"
                )
                return True

            if outcome == "deescalate":
                if answered_stage == "protective":
                    state.probe_protective_answer = patient_message
                self._ground_risk_from_probe(state, patient_message)
                probe_just_concluded = True
            else:
                state.probe_stage_idx += 1
                if state.probe_stage_idx >= len(safety_probe.PROBE_STAGES):
                    # Stages exhausted without denial or disclosure —
                    # compose from the full exchange and exit probe.
                    self._ground_risk_from_probe(state, patient_message)
                    probe_just_concluded = True

        elif state.risk_question_pending:
            # Answer to the mandatory SI screening question (outside
            # probe mode).
            state.risk_question_pending = False
            if safety_result and safety_probe.probe_should_trigger(
                safety_result.ctrs_level, safety_result.categories
            ):
                # The screening answer itself revealed CTRS-3 SI — the
                # generic trigger check below enters probe mode instead
                # of grounding from the screen directly.
                pass
            elif is_meta_utterance(patient_message):
                # BUG-078: a meta-complaint about repetitive questioning
                # ("없다니까 왜 자꾸 물어봐요.") is NOT an answer to the SI
                # screen — do not ground, do not set risk_grounded.
                # BUG-079 (CVR-056 follow-up): unlike the original BUG-078
                # fix, this NOW arms `risk_screen_retry_needed` — relying
                # solely on "risk_grounded stays False so round-robin will
                # eventually come back to it" (the original fix's reasoning,
                # see the comment this replaces) proved insufficient live:
                # `_resolve_dialogue_probe_instruction`'s forced-retry
                # condition only fires near the backstop or once every OTHER
                # question-able slot is filled, and the PLAIN round-robin
                # path can independently consume many turns before its
                # modulo cycle lands on `risk_assessment` again — in two of
                # three live sessions (CVR-056), it never did before the
                # session ended, and a genuine SI denial that arrived
                # off-topic in the meantime was silently never grounded.
                # This flag does NOT itself set `risk_question_pending`
                # (that remains `_resolve_dialogue_probe_instruction`'s sole
                # responsibility, consumed there — see that method) — so
                # pending is still only ever true on a turn where the SI
                # screen instruction is actually the one rendered.
                state.risk_screen_retry_needed = True
            elif (
                OrchestratorAgent._last_assistant_message(state)
                and infer_literal_target_slot(
                    OrchestratorAgent._last_assistant_message(state)
                ) != RISK_SLOT_KEY
            ):
                # BUG-079 (CVR-056 follow-up, BUG-077 item B parity, but
                # DELIBERATELY stricter than that precedent on the MATCH
                # side): the turn `risk_question_pending` was armed for did
                # not literally, recognizably render the SI screen question
                # — live repro `db6da0e2`: `dialogue_target_slot` internally
                # recorded `risk_assessment` but the rendered text asked
                # about something else entirely ("잠을 잘 못 주무시고 짜증이
                # 많이 나셨겠어요"), which `infer_literal_target_slot` reads
                # as `None` (no slot's keywords match — an ambiguous/generic
                # reflection, not a confirmed SI question). Unlike BUG-077
                # item B (bare-denial attribution on an ORDINARY slot, where
                # a `None` literal match is accepted to avoid starving
                # legitimate but topically-unmatched grounding), this branch
                # requires an EXACT `risk_assessment` literal match WHEN THE
                # PRIOR ASSISTANT TEXT IS AVAILABLE — both a different
                # literal slot AND an ambiguous/`None` match are rejected.
                # Rationale: this is the single highest-stakes slot in the
                # pipeline — a false grounding here (`risk_grounded=True` on
                # a reply that never actually answered an SI question) is a
                # "오기록" (false record) that would falsely satisfy the
                # termination gate and let the session end without ever
                # genuinely screening for suicidal ideation. Retrying the SI
                # screen an extra time in the (rare, backstop-bounded) case
                # a genuine SI paraphrase used no listed keyword is the
                # strictly safer failure mode ("미기록>오기록", CVR-056 §4).
                # The `and OrchestratorAgent._last_assistant_message(state)`
                # guard mirrors BUG-077 item B's own "literal text
                # unavailable → trust the caller's tracking unchanged"
                # fallback exactly — when the caller never threaded the
                # assistant turn back (empty history, the shape every
                # pre-existing BUG-078 unit test constructs), this is a test/
                # caller-bookkeeping gap, not evidence of a real mismatch,
                # so it falls through to grounding unchanged (no regression).
                state.risk_screen_retry_needed = True
            else:
                risk_value = safety_probe.compose_screen_risk_assessment(patient_message)
                state.slot_data[RISK_SLOT_KEY] = risk_value
                state.risk_grounded = True
                state.risk_screen_retry_needed = False

        # Probe trigger check (CTRS 3 + SI/self-harm this turn) — never
        # re-trigger on the turn that just concluded a probe (mirrors
        # f1.py's own cooldown, its "QA finding 8").
        if (
            safety_result
            and not state.probe_active
            and not probe_just_concluded
            and safety_probe.probe_should_trigger(
                safety_result.ctrs_level, safety_result.categories
            )
        ):
            state.probe_active = True
            state.probe_awaiting_answer = False
            state.probe_stage_idx = 0
            state.probe_trigger_utterance = patient_message
            state.probe_answers = []
            state.probe_protective_answer = ""
            state.risk_grounded = False  # new risk episode — re-ground

        return False

    @staticmethod
    def _ground_risk_from_probe(state: SessionState, final_answer: str) -> None:
        risk_value = safety_probe.compose_probe_risk_assessment(
            state.probe_trigger_utterance, final_answer, state.probe_protective_answer,
        )
        state.slot_data[RISK_SLOT_KEY] = risk_value
        state.risk_grounded = True
        state.probe_active = False

    def _resolve_dialogue_probe_instruction(self, state: SessionState) -> str | None:
        """Decide what — if anything — should override DialogueAgent's
        normal round-robin slot targeting THIS turn. Mirrors f1.py's own
        branch order exactly: probe active > mandatory SI screen > normal
        round-robin (unchanged, handled by the caller) — with two
        additions: ADR-044's within-`_SI_SCREEN_RESERVE_TURNS`-of-backstop
        force, and BUG-079's `risk_screen_retry_needed` force (see below).
        This is the ONLY place `state.risk_question_pending` is ever set
        True — so BUG-079's retry flag, consumed here, guarantees a re-arm
        is always tied to a turn where the SI screen instruction is
        actually the one returned to be rendered, never an inline/stale
        force-arm elsewhere."""
        if state.probe_active:
            state.probe_awaiting_answer = True
            return safety_probe.build_probe_instruction(state.probe_stage_idx)

        if state.risk_grounded:
            state.risk_screen_retry_needed = False  # defensive — moot once grounded
            return None

        # BUG-079 (CVR-056 follow-up): a failed prior SI-screen attempt
        # (meta-utterance or literal-target mismatch, see
        # `_advance_safety_probe`) forces the SI screen to be THIS turn's
        # render target immediately — closing the gap where the plain
        # round-robin's turn-count-modulo cycle might not land back on
        # `risk_assessment` again before the session ends (CVR-056's live
        # finding: 2 of 3 sessions never recovered). Consumed (reset False)
        # here, the single point that can set `risk_question_pending`.
        retry_needed = state.risk_screen_retry_needed
        near_backstop = state.turn_count >= _MAX_DIALOGUE_TURNS - _SI_SCREEN_RESERVE_TURNS
        if near_backstop or retry_needed or not self._other_missing_risk_slots(state):
            state.risk_screen_retry_needed = False
            # Either all other question-able slots are collected (session
            # may NOT end until risk is grounded), or the hard backstop is
            # near enough that the SI screen must be attempted NOW rather
            # than risk losing its turn to the backstop entirely (ADR-044).
            state.risk_question_pending = True
            return safety_probe.SI_SCREEN_INSTRUCTION

        return None

    # ── Cluster G: post-handoff once-fire guard (ADR-043) ────────────

    def _build_post_handoff_result(self, state: SessionState) -> OrchestratorTurnResult:
        """Post-handoff short-circuit — only reached when `state.
        handoff_delivered` is already True. The safety gate for THIS turn
        has already run in `_execute_pipeline` (this branch is checked
        AFTER the crisis-flow return), so a new crisis disclosure on an
        already-completed session is unaffected: it returns via
        `_build_crisis_result` before this method is ever called. Never
        re-runs slot extraction or the handoff pipeline.

        ADR-044 (CVR-043 pin-fix): `state.handoff_delivered` is now also
        set True by the backstop-vs-risk-grounding escalation outcome (not
        only a real handoff) — `state.risk_screening_incomplete` picks the
        correct message/flag on every subsequent turn of that session, so
        the patient consistently sees the calm escalation message rather
        than the "already handed off" one it was never actually given.

        BUG-086 fix: `state.handoff_delivered` is now ALSO latched True on
        an unverified terminal outcome (regenerate-exhausted/reject/
        exception, no escalation) — `state.handoff_unverified` picks the
        matching `_HANDOFF_ACK_MESSAGE` text on every subsequent turn,
        distinct from both the real-success `_POST_HANDOFF_MESSAGE` and
        the escalation `_INCOMPLETE_INTAKE_MESSAGE`.

        CVR-058 (blocking) fix: the `unverified` branch used to ship
        `_HANDOFF_ACK_MESSAGE` verbatim on EVERY subsequent turn of the
        session, regardless of what the patient said — live-observed as a
        7-turn identical-string non-responsive loop (qa session
        `5f6583d4`), right at a point where the patient may have just
        disclosed SI. `_HANDOFF_ACK_MESSAGE` is still returned here as
        `assistant_response` (the safe, never-empty fallback — BUG-086's
        own invariant is preserved unconditionally), but
        `needs_closing_dialogue=True` is now also set on this branch so
        `routes/chat.py` can override it with a real, content-aware
        `DialogueAgent` closing-mode call. The escalation and real-
        success branches are unaffected (both already ship a genuine
        terminal message, not a content-blind repeat).
        """
        escalation = state.risk_screening_incomplete
        unverified = state.handoff_unverified
        self._record_stage(
            state, SessionStage.completed, "orchestrator",
            "skip",
            "post-handoff short-circuit ("
            + (
                "risk_screening_incomplete, ADR-044" if escalation
                else "handoff_unverified, BUG-086" if unverified
                else "handoff_delivered, ADR-043"
            ) + ")"
        )
        if escalation:
            assistant_response = _INCOMPLETE_INTAKE_MESSAGE
        elif unverified:
            assistant_response = _HANDOFF_ACK_MESSAGE
        else:
            assistant_response = _POST_HANDOFF_MESSAGE
        return OrchestratorTurnResult(
            session_id=state.session_id,
            current_stage=SessionStage.completed,
            assistant_response=assistant_response,
            safety_status=state.safety_status,
            slot_coverage=state.slot_coverage,
            handoff_ready=False,
            clinical_escalation_required=escalation,
            session_state=state,
            stage_history=state.stage_history,
            # CVR-058 fix: unverified-only — escalation/real-success stay False.
            needs_closing_dialogue=(unverified and not escalation),
        )

    @staticmethod
    def _seed_slot_data_from_caller(state: SessionState, filled_slots: dict[str, str]) -> None:
        """Union the caller-supplied (backend-accumulated) slot map into
        `state.slot_data` — additive only, never overwrites an existing
        internal value (this orchestrator's own `update_slots` call,
        `routes/chat.py` Step 5, may already hold a same-session value for
        a key; the caller's map is a floor, not an override). A blank/
        whitespace-only caller value is never written (same "empty means
        unfilled" rule `_slot_is_filled` applies everywhere else)."""
        if not filled_slots:
            return
        for key, value in filled_slots.items():
            if not value or not value.strip():
                continue
            if key not in state.slot_data:
                state.slot_data[key] = value

    @staticmethod
    def _soft_safety_latch_allows(state: SessionState) -> bool:
        """BUG-051 (CVR-039): once-per-session latch — True on the FIRST
        trigger this session (`soft_safety_note_sent` still False), or
        again once `_SOFT_SAFETY_REARM_TURNS` turns have passed since the
        last send. `state.turn_count` is already incremented for THIS
        turn at the point this is called (Stage 4, above). The latch
        state itself is SET by the caller (`_execute_pipeline`,
        immediately after this returns True) — this method only decides
        whether firing is ALLOWED, never mutates state itself."""
        if not state.soft_safety_note_sent:
            return True
        if state.soft_safety_note_last_turn is None:
            return True
        return (state.turn_count - state.soft_safety_note_last_turn) >= _SOFT_SAFETY_REARM_TURNS

    def _update_slot_coverage(self, state: SessionState) -> None:
        """Recompute slot coverage from current slot_data.

        B5 enabler (EXP-029, orchestrator design decision): `state.
        slot_coverage` — the value the `handoff_ready` gate (`_should_
        extract_slots`) thresholds against — is computed over
        `PATIENT_FILLABLE_SLOTS` only (7 of 12; excludes risk_assessment,
        the 3 system/clinician-authored slots, and mental_status_exam —
        see that constant's own docstring for the full categorization
        evidence). `state.filled_slots` itself stays the FULL 12-slot
        picture unchanged (still used for `missing_essential_slots`
        reporting) — only the coverage FRACTION's denominator changed.
        """
        filled = [k for k in ALL_SLOT_KEYS if self._slot_is_filled(state.slot_data, k)]
        state.filled_slots = filled
        state.missing_essential_slots = [
            k for k in _ESSENTIAL_SLOTS if k not in filled
        ]
        filled_fillable = [k for k in filled if k in PATIENT_FILLABLE_SLOTS]
        state.slot_coverage = (
            len(filled_fillable) / len(PATIENT_FILLABLE_SLOTS)
            if PATIENT_FILLABLE_SLOTS else 0.0
        )

    @staticmethod
    def _slot_is_filled(slot_data: dict[str, Any], key: str) -> bool:
        """Check if a slot key is present and non-empty in slot_data."""
        parts = key.split(".")
        if len(parts) == 1:
            val = slot_data.get(key)
        else:
            # Nested: e.g. "symptoms.sleep"
            parent = slot_data.get(parts[0], {})
            if isinstance(parent, dict):
                val = parent.get(parts[1])
            else:
                val = None

        if val is None:
            return False
        if isinstance(val, str) and not val.strip():
            return False
        if isinstance(val, dict) and val.get("value") in (None, ""):
            return False
        return True

    # ── Post-dialogue pipeline ──────────────────────────────────────

    async def _run_post_dialogue_pipeline(
        self, state: SessionState
    ) -> OrchestratorTurnResult:
        """Run slot_extraction → handoff_generation → evidence_verification → delivery."""

        # ── Slot extraction ─────────────────────────────────────────
        state.current_stage = SessionStage.slot_extraction
        try:
            slot_agent = self._get_slot_agent()
            slot_input = ClinicalSlotInput(
                session_id=state.session_id,
                conversation_history=state.conversation_history,
                current_slots=state.slot_data,
                # BUG-072/073: same ask-evidence hint threaded to the HTTP
                # route (`routes/slots.py`) — this call is IN-PROCESS
                # (`ClinicalSlotAgent.run()` direct), so it must apply the
                # SAME grounding discipline itself, not rely on the route.
                dialogue_target_slot=state.dialogue_target_slot,
            )
            slot_result = await slot_agent.run(slot_input)
            # BUG-072/BUG-049 lineage: this call previously merged
            # `slot_result.extracted_slots` straight into `state.slot_data`
            # with ZERO grounding — the SAME "raw LLM output reaches the
            # clinical record ungrounded" gap BUG-049 fixed for the HTTP
            # route (`routes/slots.py::_apply_grounding_filter`), just at a
            # different call site (this one is in-process, never goes
            # through that route). Ground it here with the SAME
            # `evaluate_slot_grounding` call, tagging the last patient
            # utterance with `state.dialogue_target_slot` exactly like the
            # route does.
            if hasattr(slot_result, "extracted_slots") and slot_result.extracted_slots:
                patient_utterances = [
                    m.get("content", "")
                    for m in state.conversation_history
                    if m.get("role") == "user" and m.get("content")
                ]
                asked_slots = None
                if state.dialogue_target_slot and patient_utterances:
                    asked_slots = {
                        len(patient_utterances) - 1: state.dialogue_target_slot
                    }
                grounded: dict[str, Any] = {}
                for key, value in slot_result.extracted_slots.items():
                    if not isinstance(value, str):
                        continue
                    verdict = evaluate_slot_grounding(
                        key, value, patient_utterances, asked_slots
                    )
                    if verdict.accepted:
                        grounded[key] = value
                        state.slot_status[key] = verdict_to_slot_status(verdict)
                    else:
                        logger.warning(
                            "Post-dialogue slot extraction: dropped slot "
                            "'%s' (value=%r): %s", key, value, verdict.reason,
                        )
                if grounded:
                    self.update_slots(state, grounded)
            self._update_slot_coverage(state)
            self._record_stage(
                state, SessionStage.slot_extraction, "04_clinical_slot",
                "pass", f"coverage={state.slot_coverage:.2f}"
            )
        except Exception as exc:
            logger.warning("Slot extraction failed: %s — proceeding with existing slots", exc)
            self._record_stage(
                state, SessionStage.slot_extraction, "04_clinical_slot",
                "fail", str(exc)
            )

        # ── Handoff generation + verification loop ──────────────────
        state.current_stage = SessionStage.handoff_generation
        handoff_report = None

        try:
            handoff_agent = self._get_handoff_agent()
            handoff_input = self._build_handoff_input(state)

            for attempt in range(1 + _MAX_HANDOFF_REGEN):
                handoff_result = await handoff_agent.run(handoff_input)
                self._record_stage(
                    state, SessionStage.handoff_generation, "08_handoff_generator",
                    "pass", f"attempt {attempt + 1}"
                )

                # Evidence verification
                state.current_stage = SessionStage.evidence_verification
                verifier = self._get_verifier_agent()
                # BUG-050: these 3 context fields were never threaded here
                # at all (all silently defaulted — is_first_visit=True,
                # has_scale_scores=False, ctrs_level=None) — harmless in
                # sessions where the defaults happen to match reality, but
                # a latent gap (e.g. a real revisit session would never
                # have its section-9 requirement checked). Threaded from
                # the real state now, never re-derived independently.
                verifier_input = EvidenceVerifierInput(
                    session_id=state.session_id,
                    report_markdown=handoff_result.report_markdown,
                    evidence_packets=handoff_result.evidence_packets,
                    is_first_visit=state.is_first_visit,
                    has_scale_scores=bool(state.scale_scores),
                    ctrs_level=int(state.safety_status.ctrs_level),
                )
                verification = await verifier.run(verifier_input)

                # BUG-050 observability fix (qa's explicit pain point): the
                # wire previously exposed only the bare stage-history label
                # ("regenerate"/"fail") — never the verbatim VerifierIssue
                # list, forcing code archaeology to diagnose a rejection.
                # Every attempt's issues are now recorded, tagged by
                # attempt number, on `state.verifier_issue_log` (additive
                # SessionState field, survives to the wire via
                # OrchestratorTurnResult.verifier_issue_log below).
                for issue in verification.issues:
                    state.verifier_issue_log.append(
                        f"attempt {attempt + 1}: [{issue.severity}] "
                        f"{issue.issue_type} @ {issue.location}: {issue.description}"
                    )

                if verification.action == VerifierAction.passed:
                    self._record_stage(
                        state, SessionStage.evidence_verification, "09_evidence_verifier",
                        "pass", f"verified on attempt {attempt + 1}"
                    )
                    handoff_report = {
                        "report_markdown": handoff_result.report_markdown,
                        "evidence_packets": [
                            p.model_dump() for p in handoff_result.evidence_packets
                        ],
                        "missing_slots": handoff_result.missing_slots,
                        "risk_level": str(handoff_result.risk_level),
                        # trend_plot은 58db676에서 제거됨(F1 범위 밖). 계약 유지 위해 키만 남김.
                        "trend_plot_base64": None,
                    }
                    break

                if verification.action == VerifierAction.reject:
                    self._record_stage(
                        state, SessionStage.evidence_verification, "09_evidence_verifier",
                        "fail", f"rejected: {len(verification.issues)} issues"
                    )
                    state.error_log.append(
                        f"Handoff rejected: {[i.description for i in verification.issues]}"
                    )
                    break

                # regenerate
                self._record_stage(
                    state, SessionStage.evidence_verification, "09_evidence_verifier",
                    "regenerate", f"attempt {attempt + 1}/{1 + _MAX_HANDOFF_REGEN}"
                )
                state.current_stage = SessionStage.handoff_generation

        except Exception as exc:
            logger.error("Handoff pipeline failed: %s", exc)
            self._record_stage(
                state, SessionStage.handoff_generation, "08_handoff_generator",
                "fail", str(exc)
            )
            state.error_log.append(f"Handoff pipeline error: {exc}")

        # ── Handoff delivery ────────────────────────────────────────
        state.current_stage = SessionStage.handoff_delivery
        self._record_stage(state, SessionStage.handoff_delivery, "orchestrator", "pass")
        state.current_stage = SessionStage.completed

        # REV-001 Issue 1/2 (critic, `discussion.md`): `handoff_ready` used to
        # be hardcoded `True` here regardless of whether `handoff_report`
        # above is actually populated — a pipeline exception (caught at
        # line ~435) or a `VerifierAction.reject` (line ~418) both leave
        # `handoff_report=None`, but the caller (`routes/chat.py`) was told
        # "ready" anyway and shipped a "report will be written" message with
        # no report reachable through the wire contract. `handoff_ready` now
        # reflects reality: only True when a report was actually produced.
        #
        # ADR-044 (CVR-043 pin-fix, item 6): if this session's termination
        # came through the backstop-vs-risk-grounding gate
        # (`state.risk_screening_incomplete`, set in `_should_extract_
        # slots`), `handoff_ready`/`handoff_report` are force-suppressed
        # here EVEN IF a report was otherwise successfully generated and
        # verified — ADR-042's absolute claim is "no handoff_ready before
        # risk_grounded", full stop, not "usually". The patient is not
        # stranded (the session still concludes, via `_INCOMPLETE_INTAKE_
        # MESSAGE` below + the Cluster G-style once-fire guard in
        # `_execute_pipeline`) — what changes is that the RECEIVING
        # CLINICIAN sees an explicit `clinical_escalation_required=True`
        # signal instead of a routine "ready for pickup" one. All the raw
        # slot data collected this session (including any partial risk-
        # adjacent content) still reaches the clinician via `session_state.
        # slot_data` on the wire — only the generated handoff MARKDOWN
        # report and the "ready" status are gated, not the underlying data.
        escalation = state.risk_screening_incomplete
        handoff_ready = handoff_report is not None and not escalation
        # BUG-086 fix (2026-07-25, qa live-reproduced session `2671d9fe`):
        # this branch used to ship a bare empty string whenever the
        # pipeline reached its terminal `completed` outcome WITHOUT a
        # verified report and WITHOUT the escalation flag (verifier
        # rejected, regenerate budget exhausted, or the pipeline raised —
        # `handoff_report is None and not escalation`). apps/api's own
        # `ChatResponse.assistant_response` contract (`min_length=1`)
        # rejects "" outright and silently drops the ENTIRE turn — no
        # `ai:complete` frame, no DB row, and (before the `handoff_
        # delivered` latch fix above) the turn re-ran from scratch on
        # every subsequent message forever. `assistant_response` must
        # never be empty here: reuse `_HANDOFF_ACK_MESSAGE` (the same
        # text already shown on the earlier stage-1 ack turn, per
        # BUG-090) for the unverified case — it is a safe, generic,
        # already-patient-facing string, and this turn is only reachable
        # via the BUG-090 lazy-resume path, whose own stage-1 ack turn
        # the patient has typically already left the chat screen after
        # (see BUG-090's RESULT discussion) — so this text is a
        # defensive non-empty fallback, not the primary UX surface.
        unverified = handoff_report is None and not escalation
        state.handoff_unverified = unverified
        assistant_response = (
            _INCOMPLETE_INTAKE_MESSAGE if escalation else _HANDOFF_ACK_MESSAGE
        )
        return OrchestratorTurnResult(
            session_id=state.session_id,
            current_stage=SessionStage.completed,
            assistant_response=assistant_response,
            safety_status=state.safety_status,
            slot_coverage=state.slot_coverage,
            handoff_ready=handoff_ready,
            clinical_escalation_required=escalation,
            handoff_report=None if escalation else handoff_report,
            verifier_issue_log=state.verifier_issue_log,
            session_state=state,
            stage_history=state.stage_history,
        )

    def _build_handoff_input(self, state: SessionState) -> HandoffInput:
        """Construct HandoffInput from the current session state."""
        slot_data = state.slot_data
        symptoms = (
            slot_data.get("symptoms", {})
            if isinstance(slot_data.get("symptoms"), dict)
            else {}
        )

        # ISS-020: carry collected scale scores + safety/risk events into the
        # handoff so the clinician-facing report never loses PHQ-9/GAD-7 severity
        # or suicide-risk indicators collected during the session.
        scale_scores: list[ScaleScore] = []
        for name, data in state.scale_scores.items():
            if name.startswith("_"):  # skip meta keys (e.g. "_prior" trend data)
                continue
            if isinstance(data, dict) and data.get("total_score") is not None:
                scale_scores.append(
                    ScaleScore(
                        scale_name=name,
                        total_score=int(data["total_score"]),
                        severity=str(data.get("severity", "")),
                    )
                )

        risk_events: list[dict[str, str]] = []
        ss = state.safety_status
        if ss is not None and ss.risk_level != RiskLevel.none:
            risk_events.append(
                {
                    "ctrs_level": str(int(ss.ctrs_level)),
                    "risk_level": ss.risk_level.value,
                    "crisis": str(ss.crisis_triggered),
                }
            )

        return HandoffInput(
            session_id=state.session_id,
            slots=SlotData(
                chief_complaint=slot_data.get("chief_complaint"),
                history_of_present_illness=slot_data.get("history_of_present_illness"),
                onset=slot_data.get("onset"),
                duration=slot_data.get("duration"),
                triggers=slot_data.get("triggers"),
                sleep=symptoms.get("sleep"),
                appetite=symptoms.get("appetite"),
                mood=symptoms.get("mood"),
                anxiety=symptoms.get("anxiety"),
                concentration=symptoms.get("concentration"),
                energy=symptoms.get("energy"),
                functional_impairment=slot_data.get("functional_impairment"),
                medication=slot_data.get("current_medications"),
                past_psychiatric_history=slot_data.get("past_psychiatric_history"),
                risk_factors=slot_data.get("risk_factors"),
                psychosocial_context=slot_data.get("psychosocial_context"),
                substance_use=slot_data.get("substance_use"),
                # BUG-050 fix: these 4 canonical-12 keys ClinicalSlotAgent
                # actually produces were never read into SlotData at all —
                # the generator was missing 4 of the patient's 7 real
                # PATIENT_FILLABLE_SLOTS values, a likely contributor to
                # EvidenceVerifierAgent's 12/12 regenerate rate (the
                # generator improvising ungrounded content to compensate
                # for missing structured context).
                medical_history=slot_data.get("medical_history"),
                personal_social_history=slot_data.get("personal_social_history"),
                family_history=slot_data.get("family_history"),
                substance_use_history=slot_data.get("substance_use_history"),
            ),
            conversation_history=state.conversation_history,
            scale_scores=scale_scores,
            risk_events=risk_events,
            is_first_visit=state.is_first_visit,
        )

    # ── Crisis flow ─────────────────────────────────────────────────

    def _build_crisis_result(
        self, state: SessionState, safety_result: Any
    ) -> OrchestratorTurnResult:
        """Build the crisis protocol response."""
        ctrs = state.safety_status.ctrs_level
        message = _CRISIS_MESSAGES.get(ctrs, _CRISIS_MESSAGES[CTRSLevel.HIGH_RISK])

        self._record_stage(
            state, SessionStage.crisis_flow, "orchestrator",
            "crisis", f"CTRS {ctrs.value} — crisis protocol activated"
        )

        return OrchestratorTurnResult(
            session_id=state.session_id,
            current_stage=SessionStage.crisis_flow,
            assistant_response=message,
            safety_status=state.safety_status,
            slot_coverage=state.slot_coverage,
            crisis_triggered=True,
            requires_human_review=True,
            session_state=state,
            stage_history=state.stage_history,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _record_stage(
        state: SessionState,
        stage: SessionStage,
        agent: str,
        result: str,
        detail: str = "",
    ) -> None:
        """Append a stage transition record to the session history."""
        state.stage_history.append(
            StageRecord(
                stage=stage,
                agent=agent,
                result=result,
                timestamp=datetime.now(),
                detail=detail,
            )
        )

    # ── Convenience: update slots from external call ────────────────

    @staticmethod
    def update_slots(state: SessionState, new_slots: dict[str, Any]) -> None:
        """Merge new slot data into session state (called by route after dialogue)."""
        for key, value in new_slots.items():
            parts = key.split(".")
            if len(parts) == 1:
                state.slot_data[key] = value
            else:
                state.slot_data.setdefault(parts[0], {})[parts[1]] = value

    @staticmethod
    def add_assistant_turn(state: SessionState, response: str) -> None:
        """Record an assistant response in conversation history."""
        state.conversation_history.append({
            "role": "assistant",
            "content": response,
        })

    # ── Survey planner ──────────────────────────────────────────────

    @staticmethod
    def plan_surveys(state: SessionState) -> list[str]:
        """Recommend which clinical scales to administer based on slot data.

        Rules:
        - PHQ-9: always recommended (depression screening standard)
        - GAD-7: if anxiety-related slots are filled or chief_complaint mentions anxiety
        - PHQ-4: if neither PHQ-9 nor GAD-7 scored yet (ultra-brief screener)
        - WHO-5: if mood or energy slots suggest low wellbeing
        - AUDIT-C: if substance_use slot mentions alcohol
        """
        recommended: list[str] = []
        already_scored = set(state.scale_scores.keys())
        slots = state.slot_data

        # PHQ-9 always
        if "PHQ-9" not in already_scored:
            recommended.append("PHQ-9")

        # GAD-7 if anxiety signals present
        symptoms = slots.get("symptoms", {})
        anxiety_signal = (
            isinstance(symptoms, dict) and symptoms.get("anxiety")
        ) or "불안" in str(slots.get("chief_complaint", ""))
        if anxiety_signal and "GAD-7" not in already_scored:
            recommended.append("GAD-7")

        # PHQ-4 as fallback if no PHQ-9 or GAD-7
        if "PHQ-9" not in already_scored and "GAD-7" not in already_scored:
            if "PHQ-4" not in already_scored:
                recommended.append("PHQ-4")

        # WHO-5 if mood/energy concerns
        mood_concern = isinstance(symptoms, dict) and (
            symptoms.get("mood") or symptoms.get("energy")
        )
        if mood_concern and "WHO-5" not in already_scored:
            recommended.append("WHO-5")

        # AUDIT-C if substance use mentions alcohol
        substance = str(slots.get("substance_use", ""))
        if ("알코올" in substance or "술" in substance) and "AUDIT-C" not in already_scored:
            recommended.append("AUDIT-C")

        return recommended

    @staticmethod
    def score_and_check_safety(
        state: SessionState, scale_name: str, responses: list[int],
        patient_sex: str = "unknown",
    ) -> tuple[ScoreResult, bool]:
        """Score a survey and check if it triggers a safety referral.

        Returns:
            (ScoreResult, safety_triggered) — safety_triggered is True if
            the score warrants immediate safety referral (e.g. PHQ-9 Q9 >= 1).
        """
        result = score_survey(scale_name, responses, patient_sex=patient_sex)
        state.scale_scores[scale_name] = {
            "total_score": result.total_score,
            "severity": result.severity,
            "critical_item_positive": result.critical_item_positive,
            "recommended_action": result.recommended_action,
        }

        safety_triggered = result.recommended_action == "safety_referral"
        return result, safety_triggered
