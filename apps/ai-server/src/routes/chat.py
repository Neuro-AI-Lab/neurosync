"""POST /ai/chat/respond — Dialogue endpoint with orchestrator-managed safety gate."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.orchestrator import OrchestratorAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.dialogue import DialogueInput, DialogueLLMResponse, DialogueOutput
from src.schemas.orchestrator import (
    OrchestratorInput,
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

    # ── Step 4: Dialogue LLM (orchestrator says it's safe to proceed) ──
    try:
        system_prompt = prompt_loader.load_system_prompt(_DIALOGUE_AGENT_NAME, _PROMPT_VERSION)
    except FileNotFoundError:
        logger.warning("Dialogue prompt not found, using minimal fallback")
        system_prompt = (
            "당신은 Neuro-Sync 정신건강 사전 문진 AI입니다. "
            "환자의 이야기를 경청하고, 100자 이내의 따뜻한 한국어로 응답합니다. "
            "JSON으로 응답하세요: {assistant_response, slot_updates, risk_level, "
            "requires_human_review, reason_summary}"
        )

    # Build slot context from orchestrator state
    state = orch_result.session_state
    filled_list = state.filled_slots
    missing_essential = state.missing_essential_slots

    parts = []
    if filled_list:
        parts.append(f"이미 수집된 슬롯: {', '.join(filled_list)}")
    if missing_essential:
        parts.append(
            f"아직 미수집된 필수 슬롯: {', '.join(missing_essential)}. "
            "이 중 하나를 자연스럽게 물어보세요. 이미 수집된 슬롯은 다시 묻지 마세요."
        )
    slot_context = f"\n\n[{' | '.join(parts)}]" if parts else ""

    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=system_prompt + slot_context),
    ]

    for turn in body.conversation_history[-8:]:
        messages.append(
            ChatMessage(role=turn.get("role", "user"), content=turn["content"])
        )

    messages.append(ChatMessage(role="user", content=body.user_message))

    selection = model_router.select_model(_DIALOGUE_AGENT_NAME, require_json=True)
    adapter = model_router.get_adapter(selection.adapter_name)
    assert isinstance(adapter, LLMAdapter)

    response_format: dict[str, Any] | None = None
    if selection.supports_json_schema or selection.supports_json_object:
        response_format = {"type": "json_object"}

    try:
        resp = await adapter.chat_timed(
            messages,
            model=selection.model_id,
            temperature=0.4,
            max_tokens=1024,
            response_format=response_format,
        )
        model_router.record_success(selection.adapter_name)
    except Exception as exc:
        logger.error("Dialogue LLM failed on %s: %s", selection.adapter_name, exc)
        model_router.record_failure(selection.adapter_name, exc)

        # Try fallback
        fallback = model_router.get_fallback(
            _DIALOGUE_AGENT_NAME, selection.adapter_name, str(exc)
        )
        if fallback is None:
            raise HTTPException(
                status_code=500, detail="Dialogue generation failed"
            ) from exc

        fb_adapter = model_router.get_adapter(fallback.adapter_name)
        assert isinstance(fb_adapter, LLMAdapter)
        fb_format: dict[str, Any] | None = None
        if fallback.supports_json_schema or fallback.supports_json_object:
            fb_format = {"type": "json_object"}

        resp = await fb_adapter.chat_timed(
            messages,
            model=fallback.model_id,
            temperature=0.4,
            max_tokens=1024,
            response_format=fb_format,
        )
        model_router.record_success(fallback.adapter_name)

    # ── Step 5: Parse dialogue response + update orchestrator state ──
    try:
        data = json.loads(resp.content)
        llm_resp = DialogueLLMResponse.model_validate(data)
    except (json.JSONDecodeError, Exception) as parse_exc:
        logger.warning("Failed to parse dialogue response as JSON: %s", parse_exc)
        llm_resp = DialogueLLMResponse(
            assistant_response=resp.content[:200],
            reason_summary="JSON parse failed — using raw response",
        )

    # Merge slots and update orchestrator state
    merged_slots = dict(body.filled_slots)
    merged_slots.update(llm_resp.slot_updates)

    OrchestratorAgent.update_slots(state, llm_resp.slot_updates)
    OrchestratorAgent.add_assistant_turn(state, llm_resp.assistant_response)

    latency_ms = (time.perf_counter() - start) * 1000

    return DialogueOutput(
        model_used=resp.model,
        prompt_version=_PROMPT_VERSION,
        latency_ms=latency_ms,
        reason_summary=llm_resp.reason_summary,
        assistant_response=llm_resp.assistant_response,
        slot_updates=llm_resp.slot_updates,
        risk_level=llm_resp.risk_level,
        requires_human_review=llm_resp.requires_human_review,
        all_slots=merged_slots,
        session_state=state.model_dump(),
    )
