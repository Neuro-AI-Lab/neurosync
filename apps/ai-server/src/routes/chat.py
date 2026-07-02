"""POST /ai/chat/respond — Dialogue endpoint with orchestrator-managed safety gate."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.agents.dialogue import DialogueAgent
from src.agents.orchestrator import OrchestratorAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.dialogue import DialogueInput, DialogueOutput
from src.schemas.orchestrator import (
    OrchestratorInput,
    SessionStage,
    SessionState,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/chat", tags=["chat"])

_DIALOGUE_AGENT_NAME = "dialogue"
_PROMPT_VERSION = "v1"


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
        )

    # ── Step 3: Handle handoff ready — no more dialogue needed ──────
    if orch_result.handoff_ready:
        latency_ms = (time.perf_counter() - start) * 1000
        return DialogueOutput(
            model_used="orchestrator",
            prompt_version=_PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary="Handoff ready — slot coverage threshold reached",
            assistant_response="충분한 정보가 수집되었습니다. 사전문진 보고서를 작성하겠습니다.",
            slot_updates={},
            risk_level=orch_result.safety_status.risk_level,
            requires_human_review=False,
            all_slots=dict(body.filled_slots),
            session_state=orch_result.session_state.model_dump(),
            handoff_ready=True,
        )

    # ── Step 4: DialogueAgent (proper agent with slot tracking + repetition prevention) ──
    state = orch_result.session_state
    dialogue_agent = DialogueAgent(model_router=model_router, prompt_loader=prompt_loader)

    try:
        dialogue_input = DialogueInput(
            session_id=body.session_id,
            request_id=body.request_id,
            user_message=body.user_message,
            conversation_history=body.conversation_history,
            filled_slots=body.filled_slots,
            session_state=state.model_dump() if hasattr(state, "model_dump") else state,
        )
        dialogue_output = await dialogue_agent.run(dialogue_input)
    except Exception as exc:
        logger.error("DialogueAgent failed: %s", exc)
        raise HTTPException(status_code=500, detail="Dialogue generation failed") from exc

    # ── Step 5: Update orchestrator state ──
    OrchestratorAgent.update_slots(state, dialogue_output.slot_updates)
    OrchestratorAgent.add_assistant_turn(state, dialogue_output.assistant_response)

    dialogue_output.session_state = state.model_dump() if hasattr(state, "model_dump") else state

    latency_ms = (time.perf_counter() - start) * 1000
    dialogue_output.latency_ms = latency_ms

    return dialogue_output
