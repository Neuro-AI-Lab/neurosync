"""POST /ai/domain/infer — DomainInference full F2 artifact endpoint.

Standalone route — NOT wired into orchestrator.py or the 11-state machine
(PLAN-2026-W28-C C-3: production integration is deferred to gate G-D).

Backend-integration closure (2026-07-20, EXP-028 finding — all 3 handoff
reports had empty disease_similarity charts): the previous version of this
route ran ONLY Stage 2 (DomainInferenceAgent's certified LLM call) and
returned its raw output — no whitelist cascade, no AI-predicted-disease
population, no recommended_questionnaire. The backend needs the FULL F2
artifact (post-cascade domain_candidates, top-5 ai_predicted_disease with
similarity_score, recommended_questionnaire) as F3-plan/F4-F5-trend-chart
input. This route now reuses `src.f2`'s existing code-side functions
VERBATIM (no reimplemented logic) to produce that full artifact:

  1. Stage 1 retrieval, in-process against the live DB, ONLY when the
     caller has not already supplied `retrieved_chunks` (backward
     compatible with a caller that already ran its own Stage 1) — via
     `src.rag_trigger.decide_policy_a` (query composition + the single-
     choke-point risk-lexicon filter, REV-022 Issues 9/10) then
     `src.f2.run_stage1` (never raises; DB/embedding failure gracefully
     degrades to `mode="llm_only"`, exactly as `src.f2._run` does).
  2. Stage 2 — `DomainInferenceAgent.run()`, unchanged, still the ONLY
     certified LLM call.
  3. The whitelist cascade — `filter_domain_candidates`/
     `find_orphan_departments` (`src.eval.f2_grounding`, ADR-014) — applied
     to the LLM output before it ships, same as `src.f2._run`.
  4. `ai_predicted_disease` — `src.f2._build_ai_predicted_disease_populated`
     (RAG-mode with chunks) or `_build_ai_predicted_disease` (llm_only
     stub), the SAME mode-gated graceful-degradation `src.f2._run` uses.

A caller that wants the harness's additional audit artifacts (evidence
whitelist verdict counts, repro metadata, markdown report) still needs the
`src/f2.py` CLI harness — this route ships the F3/F4/F5-consumable subset
only.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.agents.domain_inference import DomainInferenceAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.eval.f2_grounding import filter_domain_candidates, find_orphan_departments
from src.f2 import (
    _build_ai_predicted_disease,
    _build_ai_predicted_disease_populated,
    run_stage1,
)
from src.prompts.loader import PromptLoader
from src.rag_trigger import decide_policy_a
from src.routing.model_router import ModelRouter
from src.schemas.ai_predicted_disease import AIPredictedDiseaseOutput
from src.schemas.domain_inference import (
    DomainInferenceInput,
    DomainInferRouteResponse,
    RetrievedChunk,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/domain", tags=["domain"])


def _get_domain_agent(
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> DomainInferenceAgent:
    return DomainInferenceAgent(model_router=model_router, prompt_loader=prompt_loader)


async def _run_stage1_in_process(body: DomainInferenceInput) -> list[dict[str, Any]]:
    """Mirrors `src.f2._run`'s own Stage-1 sequencing verbatim: the RAG
    trigger (query composition + risk-lexicon filter) decides WHETHER and
    WITH WHAT queries to retrieve; `run_stage1` never raises (DB/embedding
    failure degrades to llm_only). Mutates `body.retrieved_chunks`/
    `retrieval_mode` in place so the subsequent `agent.run(body)` call sees
    them, same as `DomainInferenceInput`'s own documented contract."""
    trigger = decide_policy_a(body.final_slots, body.turns, body.probe_events)
    if not trigger.retrieve:
        body.retrieval_mode = "llm_only"
        return []

    mode, raw_chunks = await run_stage1(
        body.final_slots, no_rag=False, k=3, queries_override=trigger.queries
    )
    body.retrieval_mode = mode
    if raw_chunks:
        body.retrieved_chunks = [RetrievedChunk(**c) for c in raw_chunks]
    return raw_chunks


@router.post("/infer", response_model=DomainInferRouteResponse)
async def infer(
    body: DomainInferenceInput,
    agent: DomainInferenceAgent = Depends(_get_domain_agent),
) -> DomainInferRouteResponse:
    """Full F2 artifact — Stage 1 (in-process, graceful degradation) + Stage
    2 (certified LLM) + whitelist cascade + AI-predicted-disease population.
    """
    if not body.request_id:
        body.request_id = str(uuid.uuid4())

    if body.retrieved_chunks:
        # Caller already ran its own Stage 1 — respected as-is (backward
        # compatible with the route's original contract).
        raw_chunks: list[dict[str, Any]] = [c.model_dump() for c in body.retrieved_chunks]
    else:
        raw_chunks = await _run_stage1_in_process(body)

    logger.info(
        "Domain infer request_id=%s session_id=%s mode=%s chunks=%d",
        body.request_id, body.session_id, body.retrieval_mode, len(raw_chunks),
    )

    try:
        output = await agent.run(body)
    except Exception as exc:
        logger.error("Domain inference failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Domain inference failed") from exc

    chunk_texts = {c["chunk_id"]: c["text"] for c in raw_chunks}
    utterances = {f"turn_{t.turn}": t.patient_message for t in body.turns}
    filtered_candidates, _verdicts, _counts = filter_domain_candidates(
        output.domain_candidates, chunk_texts=chunk_texts, utterances=utterances
    )
    orphan_departments = find_orphan_departments(filtered_candidates, output.department_candidates)

    ai_predicted_disease: AIPredictedDiseaseOutput
    if body.retrieval_mode == "rag" and raw_chunks:
        try:
            from src.dependencies import get_sessionmaker

            sessionmaker = get_sessionmaker()
            async with sessionmaker() as db:
                ai_predicted_disease = await _build_ai_predicted_disease_populated(db, raw_chunks)
        except Exception as exc:  # noqa: BLE001 — population failure must not crash the route
            logger.warning(
                "domain.ai_predicted_disease.population_failed — falling back to "
                "experimental_unpopulated (domain_candidates unaffected): %s", exc,
            )
            ai_predicted_disease = _build_ai_predicted_disease()
    else:
        ai_predicted_disease = _build_ai_predicted_disease()

    logger.info(
        "Domain infer result: %d domain candidates, %d department candidates, "
        "%d ai_predicted_disease candidates, latency=%.0fms",
        len(filtered_candidates), len(output.department_candidates),
        len(ai_predicted_disease.candidates), output.latency_ms,
    )

    return DomainInferRouteResponse(
        session_id=body.session_id,
        request_id=body.request_id,
        model_used=output.model_used,
        prompt_version=output.prompt_version,
        latency_ms=output.latency_ms,
        domain_candidates=filtered_candidates,
        department_candidates=output.department_candidates,
        orphan_departments=orphan_departments,
        summary=output.summary,
        retrieval_meta=output.retrieval_meta,
        ai_predicted_disease=ai_predicted_disease,
    )
