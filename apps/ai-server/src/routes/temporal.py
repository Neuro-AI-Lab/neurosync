"""POST /ai/temporal/summarize — Longitudinal state comparison."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.agents.temporal_summary import TemporalSummaryAgent
from src.schemas.temporal import TemporalSummaryInput, TemporalSummaryOutput

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/temporal", tags=["temporal"])


def _get_agent() -> TemporalSummaryAgent:
    return TemporalSummaryAgent()


@router.post("/summarize", response_model=TemporalSummaryOutput)
async def summarize(
    body: TemporalSummaryInput,
    agent: TemporalSummaryAgent = Depends(_get_agent),
):
    if not body.request_id:
        body.request_id = str(uuid.uuid4())
    logger.info(
        "Temporal summarize request_id=%s patient=%s first_visit=%s",
        body.request_id,
        body.patient_id,
        body.is_first_visit,
    )
    try:
        result = await agent.run(body)
    except Exception as exc:
        logger.error("Temporal summary failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Temporal summary failed") from exc
    logger.info(
        "Temporal result: overall=%s trends=%d",
        result.overall_direction,
        len(result.domain_trends),
    )
    return result
