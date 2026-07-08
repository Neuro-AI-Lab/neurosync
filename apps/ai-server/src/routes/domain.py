"""POST /ai/domain/infer — DomainInference Stage-2 endpoint (F2).

Standalone route — NOT wired into orchestrator.py or the 11-state machine
(PLAN-2026-W28-C C-3: production integration is deferred to gate G-D). This
route exposes Stage 2 (LLM candidate generation) only; Stage 1 retrieval and
the evidence whitelist audit are the `src/f2.py` validation harness's job, not
this route's — a caller that wants the fabrication-0 guarantee must run the
harness, not just this endpoint.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.agents.domain_inference import DomainInferenceAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.domain_inference import DomainInferenceInput, DomainInferenceOutput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/domain", tags=["domain"])


def _get_domain_agent(
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> DomainInferenceAgent:
    return DomainInferenceAgent(model_router=model_router, prompt_loader=prompt_loader)


@router.post("/infer", response_model=DomainInferenceOutput)
async def infer(
    body: DomainInferenceInput,
    agent: DomainInferenceAgent = Depends(_get_domain_agent),
) -> DomainInferenceOutput:
    """Stage 2 only — caller supplies retrieved_chunks/retrieval_mode (Stage 1 is external)."""
    if not body.request_id:
        body.request_id = str(uuid.uuid4())

    logger.info(
        "Domain infer request_id=%s session_id=%s mode=%s",
        body.request_id, body.session_id, body.retrieval_mode,
    )

    try:
        result = await agent.run(body)
    except Exception as exc:
        logger.error("Domain inference failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Domain inference failed") from exc

    logger.info(
        "Domain infer result: %d domain candidates, %d department candidates, latency=%.0fms",
        len(result.domain_candidates), len(result.department_candidates), result.latency_ms,
    )
    return result
