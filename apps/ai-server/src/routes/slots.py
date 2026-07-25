"""POST /ai/slots/extract — Clinical slot extraction endpoint."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.agents.clinical_slot import ALL_SLOT_KEYS, ESSENTIAL_SLOT_KEYS, ClinicalSlotAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.grounding import evaluate_slot_grounding, verdict_to_slot_status
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.clinical_slot import ClinicalSlotInput, ClinicalSlotOutput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/slots", tags=["slots"])


def _get_slot_agent(
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> ClinicalSlotAgent:
    return ClinicalSlotAgent(model_router=model_router, prompt_loader=prompt_loader)


def _patient_utterances(conversation_history: list[dict[str, str]]) -> list[str]:
    return [
        m.get("content", "")
        for m in conversation_history
        if m.get("role") == "user" and m.get("content")
    ]


def _apply_grounding_filter(
    result: ClinicalSlotOutput,
    conversation_history: list[dict[str, str]],
    dialogue_target_slot: str | None = None,
) -> ClinicalSlotOutput:
    """BUG-049 (critical) structural fix: `POST /ai/slots/extract` previously
    shipped `ClinicalSlotAgent`'s raw LLM output with ZERO grounding — the
    exact gap a v4 prompt regression exploited (fabricated "없음(환자 부인)"
    for 5 slots whose topics were never raised yet in the transcript, and
    overwrote a genuine earlier positive value). This is the SAME "mirror
    gap" class as BUG-046/047: a real safeguard (`src.grounding`) exists
    and is exercised by `src/f1.py`'s own harness pipeline, but was never
    wired into this HTTP route at all.

    BUG-072 (full port): now calls `src.grounding.evaluate_slot_grounding`
    directly instead of the ad hoc `has_lexical_evidence`-only subset this
    function used to apply — closes the exact gap BUG-072 found: a bare
    single-word denial reply ("없어") to a directly-asked slot question
    structurally could never pass plain lexical-evidence matching (its own
    content token is boilerplate-stripped), so it needed the ask-evidence-
    gated negative-template branch `evaluate_slot_grounding` already has,
    which this function previously did not exercise. `dialogue_target_slot`
    (`ClinicalSlotInput`'s new field, BUG-073's single source of truth for
    "what did dialogue steering just ask about") is the one per-utterance
    ask-evidence hint this route's wire shape can construct — it tags the
    LAST patient utterance only (conservative: earlier utterances are
    never retroactively tagged as an answer to a slot question this route
    has no other record of).

    `src/f1.py`'s own `_filter_and_merge_slots`/`evaluate_slot_grounding`
    call is UNCHANGED by this function — `src/f1.py` calls
    `ClinicalSlotAgent.run()` directly in-process and never goes through
    this HTTP route, so there is no double-filtering risk."""
    patient_utterances = _patient_utterances(conversation_history)
    asked_slots: dict[int, str] | None = None
    if dialogue_target_slot and patient_utterances:
        asked_slots = {len(patient_utterances) - 1: dialogue_target_slot}

    kept: dict[str, Any] = {}
    slot_status: dict[str, str] = {}
    dropped: list[tuple[str, Any, str]] = []

    for key, value in result.extracted_slots.items():
        if not isinstance(value, str):
            dropped.append((key, value, "non-string value — extractor contract violation"))
            continue
        verdict = evaluate_slot_grounding(key, value, patient_utterances, asked_slots)
        if verdict.accepted:
            kept[key] = value
            slot_status[key] = verdict_to_slot_status(verdict)
        else:
            dropped.append((key, value, verdict.reason))

    for key, value, reason in dropped:
        logger.warning(
            "Grounding filter dropped slot '%s' (value=%r): %s", key, value, reason,
        )

    filled = [k for k in ALL_SLOT_KEYS if k in kept]
    missing = [k for k in ALL_SLOT_KEYS if k not in kept]
    essential_filled = [k for k in ESSENTIAL_SLOT_KEYS if k in filled]
    essential_missing = [k for k in ESSENTIAL_SLOT_KEYS if k not in filled]
    coverage = len(filled) / len(ALL_SLOT_KEYS) if ALL_SLOT_KEYS else 0.0

    return result.model_copy(
        update={
            "extracted_slots": kept,
            "filled_slots": filled,
            "missing_slots": missing,
            "essential_filled": essential_filled,
            "essential_missing": essential_missing,
            "slot_coverage": round(coverage, 2),
            "slot_status": slot_status,
        }
    )


@router.post("/extract", response_model=ClinicalSlotOutput)
async def extract(
    body: ClinicalSlotInput,
    agent: ClinicalSlotAgent = Depends(_get_slot_agent),
) -> ClinicalSlotOutput:
    """Extract clinical slots from conversation history.

    BUG-049: the extractor's raw output is passed through a transcript-
    evidence grounding filter (`_apply_grounding_filter`) before it ever
    reaches the wire — a fabricated/ungrounded value is dropped here, not
    shipped to the caller. This route is stateless (no session state
    persisted across calls, R2 principle) — merge semantics against a
    PRIOR turn's already-accepted values (e.g. never letting a later empty/
    denial value overwrite an earlier genuine positive one) are the
    caller's responsibility, since only the caller holds that history
    across calls; nothing here invents cross-call merge logic.
    """
    if not body.request_id:
        body.request_id = str(uuid.uuid4())

    logger.info(
        "Slot extract request_id=%s session_id=%s",
        body.request_id,
        body.session_id,
    )

    try:
        result = await agent.run(body)
    except Exception as exc:
        logger.error("Slot extraction failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Slot extraction failed") from exc

    result = _apply_grounding_filter(
        result, body.conversation_history, dialogue_target_slot=body.dialogue_target_slot
    )

    # ISS-042: log only fields that exist on ClinicalSlotOutput. The former
    # `safety_flag` was removed — safety judgment belongs to SafetyClassifier.
    logger.info(
        "Slot extract result: coverage=%.2f filled=%d missing=%d "
        "essential_missing=%d latency=%.0fms",
        result.slot_coverage,
        len(result.filled_slots),
        len(result.missing_slots),
        len(result.essential_missing),
        result.latency_ms,
    )
    return result
