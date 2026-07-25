"""POST /ai/chat/respond — Dialogue endpoint with orchestrator-managed safety gate."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.agents.dialogue import DialogueAgent
from src.agents.orchestrator import CRISIS_MESSAGE_TEXTS, OrchestratorAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.common import SOFT_SAFETY_NOTE
from src.schemas.dialogue import DialogueInput, DialogueOutput
from src.schemas.orchestrator import (
    OrchestratorInput,
    SessionStage,
    SessionState,
)

# BUG-051 (CVR-039 finding 1): distinctive substring of SOFT_SAFETY_NOTE
# used for same-turn dedup — never appended if the model's OWN generated
# response already contains this (either it echoed the injected text from
# a prior turn, per CVR-039's own observed root cause, or it produced
# equivalent content on its own).
_SOFT_SAFETY_NOTE_DEDUP_KEY = "자살예방상담전화"

# BUG-051 (CVR-039 recommendation): overlay texts that are ALWAYS injected
# verbatim (never model-generated) and therefore must never be shown to
# DialogueAgent as prior conversation content — seeing them in history is
# exactly the mechanism CVR-039 traced the model's own mutated-echo
# generation to (finding 1, "혼자 감당하지 않으셔도 됩니다"-class fixed
# crisis templates carry the identical risk to SOFT_SAFETY_NOTE).
_INJECTED_OVERLAY_TEXTS: tuple[str, ...] = (SOFT_SAFETY_NOTE, *CRISIS_MESSAGE_TEXTS)


def _strip_injected_overlays_for_llm(
    conversation_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """BUG-051 (CVR-039 finding 1/history decontamination): return a COPY
    of `conversation_history` with every injected-overlay text (the
    verbatim `SOFT_SAFETY_NOTE`/crisis-message strings, never model-
    generated) removed from assistant turns — the exact text a later
    turn's DialogueAgent call must never see, so it cannot imitate a
    system overlay as if it were conversational content it once said
    itself. The overlay is a simple, exact substring (appended via plain
    string concatenation, `.rstrip() + NOTE`/shipped verbatim as the whole
    crisis turn) — removal is a plain string operation, no heuristics.
    Only the COPY passed to DialogueAgent is cleaned; the caller's own
    `conversation_history`/the backend-stored history and the wire
    response are never touched here — the patient genuinely saw the note,
    that history stays intact."""
    cleaned: list[dict[str, str]] = []
    for turn in conversation_history:
        content = turn.get("content", "")
        if turn.get("role") == "assistant" and content:
            for overlay in _INJECTED_OVERLAY_TEXTS:
                content = content.replace(overlay, "")
            cleaned.append({**turn, "content": content})
        else:
            cleaned.append(turn)
    return cleaned

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/chat", tags=["chat"])

_DIALOGUE_AGENT_NAME = "dialogue"
# PLAN-2026-W28 C1: labels DialogueOutput.prompt_version on the two bypass
# paths below (crisis / handoff-ready) where the real DialogueAgent LLM call
# is skipped (model_used="orchestrator") — kept in sync with the dialogue
# prompt pin in agents/dialogue.py (prompt_redesign_v3.md §2.2). Pin only,
# no orchestration logic changed.
_PROMPT_VERSION = "v2"


def _get_orchestrator(
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> OrchestratorAgent:
    return OrchestratorAgent(model_router=model_router, prompt_loader=prompt_loader)


@router.post("/respond", response_model=DialogueOutput)
async def respond(
    body: DialogueInput,
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
    orchestrator: OrchestratorAgent = Depends(_get_orchestrator),
) -> DialogueOutput:
    """Process a user chat message through the orchestrator pipeline.

    Flow: OrchestratorAgent (safety gate + state) → Dialogue LLM (if not crisis) → response.
    """
    start = time.perf_counter()

    if not body.request_id:
        body.request_id = str(uuid.uuid4())

    logger.info(
        "Chat respond request_id=%s session_id=%s",
        body.request_id,
        body.session_id,
    )

    # ── Step 1: Orchestrator turn (safety gate + state management) ───
    # Restore session state from previous turn if available
    session_state = None
    if body.session_state:
        try:
            session_state = SessionState.model_validate(body.session_state)
        except Exception as exc:
            logger.warning("Invalid session_state, starting fresh: %s", exc)

    orch_input = OrchestratorInput(
        session_id=body.session_id,
        patient_id=body.extra.get("patient_id", ""),
        raw_input=body.user_message,
        # Coverage-seeding fix: the SAME backend-accumulated slot map
        # already threaded into DialogueInput below — process_turn unions
        # it into state.slot_data before this turn's handoff-ready check.
        filled_slots=body.filled_slots,
        session_state=session_state,
    )

    try:
        orch_result = await orchestrator.process_turn(orch_input)
    except Exception as exc:
        logger.error("Orchestrator failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Pipeline orchestration failed"
        ) from exc

    # ── Step 2: Handle crisis — bypass dialogue LLM ─────────────────
    if orch_result.crisis_triggered:
        logger.warning(
            "Crisis detected (CTRS=%s) — bypassing dialogue",
            orch_result.safety_status.ctrs_level,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        return DialogueOutput(
            model_used="orchestrator",
            prompt_version=_PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary=f"Crisis protocol: CTRS {orch_result.safety_status.ctrs_level}",
            assistant_response=orch_result.assistant_response,
            slot_updates={},
            risk_level=orch_result.safety_status.risk_level,
            requires_human_review=True,
            all_slots=dict(body.filled_slots),
            session_state=orch_result.session_state.model_dump(),
            # CVR-051 fix: this IS the crisis-bypass turn — previously
            # unrepresentable on DialogueOutput at all (see schema
            # docstring). Every other return site in this route leaves
            # the field at its default False.
            crisis_triggered=True,
            # BUG-060/CVR-051 follow-up: real category signal for apps/api
            # to map to the correct RiskCategory (not a hardcoded placeholder).
            risk_categories=orch_result.safety_status.categories,
        )

    # ── Step 3: Handle handoff ready — no more dialogue needed ──────
    # REV-001 Issue 1 (critic): `orch_result.handoff_ready` now reflects
    # whether `handoff_report` was actually produced (orchestrator.py fix,
    # same REV-001 entry) — this branch can no longer be entered with a
    # None report. `handoff_report` is threaded onto the wire via
    # DialogueOutput's new field, closing the structural wire-contract gap
    # REV-001 identified (the field did not exist at all before this fix).
    if orch_result.handoff_ready:
        latency_ms = (time.perf_counter() - start) * 1000
        return DialogueOutput(
            model_used="orchestrator",
            prompt_version=_PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary="Handoff ready — slot coverage threshold reached",
            # 사용자 지시(2026-07-25, 마무리 멘트 재설계 1단계): 슬롯 수집
            # 완료 시점 환자 발화에서 "충분한 정보가 수집" 직설 표현과
            # "보고서" 언급을 제거 — 보고서는 임상용이며 이 시점 이전 구간에
            # 환자에게 노출되면 안 된다. 2단계(설문 전환) 멘트는 모바일
            # intake 흐름(chat.tsx::goSurvey, domain/infer 성공 후)에서
            # 별도로 표시된다.
            # BUG-086/090 (2026-07-25): this used to re-declare the ack
            # text as a bare literal — now reads `orch_result.
            # assistant_response`, which `OrchestratorAgent` itself
            # populates with the SAME text (`_HANDOFF_ACK_MESSAGE`, the
            # single source of truth) on this path, avoiding the
            # duplicate hardcoded copy.
            assistant_response=orch_result.assistant_response,
            slot_updates={},
            risk_level=orch_result.safety_status.risk_level,
            requires_human_review=False,
            all_slots=dict(body.filled_slots),
            session_state=orch_result.session_state.model_dump(),
            handoff_ready=True,
            handoff_report=orch_result.handoff_report,
        )

    # ── Step 3.5: post-handoff short-circuit (Cluster G / ADR-043) ──────
    # `orch_result.current_stage == completed` here (as opposed to the
    # `handoff_ready` branch above) means `state.handoff_delivered` was
    # already True BEFORE this turn started — the orchestrator's own
    # once-fire guard fired and returned its short-circuit message
    # WITHOUT re-running slot extraction or the handoff-generation+
    # verification pipeline. Ship that message directly; never invoke
    # DialogueAgent for this turn. A post-handoff crisis disclosure never
    # reaches this branch — it is intercepted by the crisis check above
    # (Step 2), which runs before the orchestrator's own handoff_delivered
    # guard (safety-gate-before-coverage invariant, ADR-043).
    if orch_result.current_stage == SessionStage.completed:
        latency_ms = (time.perf_counter() - start) * 1000
        # ADR-044 (CVR-043 pin-fix): this branch is also reached on the
        # FIRST turn the backstop-vs-risk-grounding gate fires this
        # session (not only on subsequent already-terminal turns) —
        # `orch_result.assistant_response` is the escalation message in
        # that case (`_INCOMPLETE_INTAKE_MESSAGE`), set by orchestrator.py
        # itself; `requires_human_review` is forced True here to match the
        # escalation's clinical intent (a routine post-handoff turn stays
        # False, unchanged).
        reason_summary = (
            "Risk screening incomplete at session end — clinician "
            "escalation required (ADR-044)"
            if orch_result.clinical_escalation_required
            else "Post-handoff — session already completed (ADR-043)"
        )
        return DialogueOutput(
            model_used="orchestrator",
            prompt_version=_PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary=reason_summary,
            assistant_response=orch_result.assistant_response,
            slot_updates={},
            risk_level=orch_result.safety_status.risk_level,
            requires_human_review=(
                True if orch_result.clinical_escalation_required else False
            ),
            all_slots=dict(body.filled_slots),
            session_state=orch_result.session_state.model_dump(),
            handoff_ready=False,
            clinical_escalation_required=orch_result.clinical_escalation_required,
        )

    # ── Step 4: DialogueAgent (proper agent with slot tracking + repetition prevention) ──
    state = orch_result.session_state
    dialogue_agent = DialogueAgent(model_router=model_router, prompt_loader=prompt_loader)

    # Cluster A/C (EXP-030): thread the orchestrator-computed probe/SI-
    # screen instruction and deferred-slot set into DialogueAgent's
    # `session_state` dict — the SAME unconstrained dict `f1.py` has
    # always used for this (`probe_instruction`/`deferred_slots` keys);
    # DialogueAgent itself needs no orchestrator-specific import, it
    # already reads these keys generically.
    dialogue_session_state: dict = state.model_dump() if hasattr(state, "model_dump") else state
    if isinstance(dialogue_session_state, dict):
        if orch_result.probe_instruction:
            dialogue_session_state = {
                **dialogue_session_state, "probe_instruction": orch_result.probe_instruction,
            }
        if state.deferred_slots:
            dialogue_session_state = {
                **dialogue_session_state, "deferred_slots": list(state.deferred_slots),
            }

    try:
        dialogue_input = DialogueInput(
            session_id=body.session_id,
            request_id=body.request_id,
            user_message=body.user_message,
            # BUG-051 (CVR-039 finding 1): decontaminated COPY — the
            # verbatim injected-overlay texts (SOFT_SAFETY_NOTE/crisis
            # messages) are never shown to DialogueAgent, so it cannot
            # imitate them as if they were its own prior conversational
            # content. `body.conversation_history` itself (backend-stored,
            # wire-visible) is untouched — the patient genuinely saw them.
            conversation_history=_strip_injected_overlays_for_llm(
                body.conversation_history
            ),
            filled_slots=body.filled_slots,
            session_state=dialogue_session_state,
            # PHR context wire-through: `body` IS a DialogueInput (this route's
            # own request model), so `patient_history_context` — POSTed once by
            # the backend after `/ai/phr/context` at session start — must be
            # forwarded to every subsequent turn's real DialogueAgent call, not
            # just carried on the unused request object. Previously dropped
            # here (fixed 2026-07-20): the field existed on `body` but this
            # reconstruction never read it, so it never reached DialogueAgent.
            patient_history_context=body.patient_history_context,
            # slot_updates_this_turn intentionally NOT forwarded: it is
            # per-turn data f1.py's own pipeline computes locally (Step 1b's
            # risk_assessment composition / Step 2's ClinicalSlotAgent
            # extraction) BEFORE calling DialogueAgent in the same process —
            # this route never runs slot extraction itself, so it has no
            # same-turn slot deltas to thread. `body.filled_slots` (session-
            # accumulated) is threaded above; DialogueInput's own docstring
            # documents this exact caller as the one that "still gets the
            # filled_slots-only check" (BUG-037 output-isolation guard,
            # lower-priority path).
        )
        dialogue_output = await dialogue_agent.run(dialogue_input)
    except Exception as exc:
        logger.error("DialogueAgent failed: %s", exc)
        raise HTTPException(status_code=500, detail="Dialogue generation failed") from exc

    # ── Step 5: Update orchestrator state ──
    OrchestratorAgent.update_slots(state, dialogue_output.slot_updates)
    OrchestratorAgent.add_assistant_turn(state, dialogue_output.assistant_response)

    # BUG-046 (EXP-028): DialogueAgent.run() intentionally hardcodes
    # risk_level=none / requires_human_review=False on its own output
    # ("위험도 판단은 SafetyAgent의 역할", src/agents/dialogue.py) — it is this
    # route's job, as the caller holding the real `state.safety_status`
    # (already computed by the orchestrator's safety gate this turn), to
    # thread the actual values onto the wire. Steps 2/3 above (crisis-bypass
    # / handoff-ready) already do this; this non-bypass path — the common
    # case, and the exact path BUG-046's CTRS-3 passive-SI repro hit — did
    # not, so every CTRS 3-5 turn shipped risk_level="none" and
    # requires_human_review=False regardless of the real safety judgment.
    dialogue_output.risk_level = state.safety_status.risk_level
    dialogue_output.requires_human_review = state.safety_status.requires_human_review

    # BUG-047: soft-safety in-turn hotline reminder — CTRS 3 + SI-adjacent
    # category this turn (`orch_result.pending_soft_safety`, computed by
    # `OrchestratorAgent._execute_pipeline` via the SAME trigger predicate
    # `src.f1`'s own probe mechanism uses, ALREADY gated on the BUG-051
    # once-per-session latch — see `OrchestratorAgent._soft_safety_latch_
    # allows`). Ported here (never inside orchestrator.py) because
    # `assistant_response` does not exist yet at `process_turn` return
    # time on this path — only this route, after the real DialogueAgent
    # call, holds the text to append to.
    #
    # BUG-051 (CVR-039 finding 1) same-turn dedup: never append if the
    # model's own generated response already contains the note's content
    # (either an imitated echo of a prior turn's injected text, or content
    # it produced independently) — appending on top of that is exactly
    # the "두 번 연속" duplication CVR-039 observed live.
    # (The once-per-session latch itself is already set by `OrchestratorAgent.
    # _execute_pipeline` at the trigger-decision point — this route only
    # decides whether to append THIS turn's text, never touches the latch.)
    already_present = _SOFT_SAFETY_NOTE_DEDUP_KEY in dialogue_output.assistant_response
    if orch_result.pending_soft_safety and not already_present:
        dialogue_output.assistant_response = (
            dialogue_output.assistant_response.rstrip() + SOFT_SAFETY_NOTE
        )
    elif orch_result.pending_soft_safety and already_present:
        logger.info(
            "Soft-safety note suppressed (already present in model output) "
            "session_id=%s turn=%d",
            state.session_id, state.turn_count,
        )

    dialogue_output.session_state = state.model_dump() if hasattr(state, "model_dump") else state

    latency_ms = (time.perf_counter() - start) * 1000
    dialogue_output.latency_ms = latency_ms

    return dialogue_output
