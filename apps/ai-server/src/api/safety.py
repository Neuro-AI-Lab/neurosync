"""POST /ai/safety/classify — PRD §0.3 interface #2."""

from __future__ import annotations

from contracts.safety import SafetyRequest, SafetyResponse
from fastapi import APIRouter, status

from src.safety.classifier import classify

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/safety/classify",
    response_model=SafetyResponse,
    status_code=status.HTTP_200_OK,
    summary="Classify a single patient message for risk level",
)
async def classify_safety(payload: SafetyRequest) -> SafetyResponse:
    return classify(payload.message, prev_context=payload.prev_context)
