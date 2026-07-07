"""POST /ai/slots/extract — Clinical slot extraction endpoint."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.agents.clinical_slot import ClinicalSlotAgent
from src.dependencies import get_model_router, get_prompt_loader
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


@router.post("/extract", response_model=ClinicalSlotOutput)
async def extract(
    body: ClinicalSlotInput,
    agent: ClinicalSlotAgent = Depends(_get_slot_agent),
) -> ClinicalSlotOutput:
    """Extract clinical slots from conversation history."""
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
