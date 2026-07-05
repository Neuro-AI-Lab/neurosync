"""POST /ai/sentiment/* — Sentiment analysis endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.agents.sentiment_analyzer import SentimentAnalyzerAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.sentiment import (
    SentimentSessionInput,
    SentimentSessionOutput,
    SentimentUtteranceInput,
    SentimentUtteranceOutput,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/sentiment", tags=["sentiment"])


def _get_agent(
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> SentimentAnalyzerAgent:
    return SentimentAnalyzerAgent(model_router=model_router, prompt_loader=prompt_loader)


@router.post("/utterance", response_model=SentimentUtteranceOutput)
async def analyze_utterance(
    body: SentimentUtteranceInput,
    agent: SentimentAnalyzerAgent = Depends(_get_agent),
):
    if not body.request_id:
        body.request_id = str(uuid.uuid4())
    logger.info("Sentiment utterance request_id=%s turn=%d", body.request_id, body.turn_index)
    try:
        return await agent.run(body)
    except Exception as exc:
        logger.error("Sentiment utterance failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Sentiment analysis failed") from exc


@router.post("/session", response_model=SentimentSessionOutput)
async def analyze_session(
    body: SentimentSessionInput,
    agent: SentimentAnalyzerAgent = Depends(_get_agent),
):
    if not body.request_id:
        body.request_id = str(uuid.uuid4())
    logger.info(
        "Sentiment session request_id=%s results=%d",
        body.request_id,
        len(body.per_utterance_results),
    )
    try:
        return await agent.run(body)
    except Exception as exc:
        logger.error("Sentiment session failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Sentiment session analysis failed") from exc
