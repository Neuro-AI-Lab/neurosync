"""POST /ai/phr/context — stateless PHR (개인건강기록) ingest endpoint.

Stateless compute principle (R2, matching `/ai/survey/plan`/`/ai/temporal/
analyze`/`/ai/handoff/report`): this route never reads or writes server-
side session state. Bundles arrive as request-body JSON objects, not file
paths — zero LLM, zero disk I/O, a thin wrapper over `src.phr_ingest`'s
already-file-I/O-free functions (`run_from_bundles` -> `summarize` ->
`to_system_prompt_note`/`to_handoff_snippet`).

Backend flow: POST bundles once at session start -> put the returned
`context` string into `patient_history_context` on every subsequent
`/ai/chat/respond` turn (`src.schemas.dialogue.DialogueInput.
patient_history_context`).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src import phr_ingest
from src.adapters.hira_drug_efficacy import HiraDrugEfficacyAdapter
from src.dependencies import get_hira_drug_efficacy_adapter
from src.schemas.phr import PhrContextRequest, PhrContextResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/phr", tags=["phr"])


def _get_efficacy_adapter() -> HiraDrugEfficacyAdapter | None:
    """HIRA_SERVICE_KEY 없으면 None — 로컬 캐시만 사용 (f1.py의 동일 lazy
    fallback 패턴, `_get_phr_efficacy_adapter`)."""
    try:
        return get_hira_drug_efficacy_adapter()
    except Exception as exc:
        logger.warning("Drug-efficacy adapter unavailable, cache-only: %s", exc)
        return None


@router.post("/context", response_model=PhrContextResponse)
async def context(
    body: PhrContextRequest,
    efficacy_adapter: HiraDrugEfficacyAdapter | None = Depends(_get_efficacy_adapter),
) -> PhrContextResponse:
    """Parse + summarize the posted MyHealthWay bundle(s), zero-LLM."""
    if not body.bundles:
        raise HTTPException(status_code=422, detail="bundles must be non-empty")

    summary = await phr_ingest.run_from_bundles(body.bundles, efficacy_adapter=efficacy_adapter)
    return PhrContextResponse(
        context=phr_ingest.to_system_prompt_note(summary),
        summary=summary,
        handoff_snippet=phr_ingest.to_handoff_snippet(summary),
    )
