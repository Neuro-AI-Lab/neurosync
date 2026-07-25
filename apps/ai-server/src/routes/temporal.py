"""POST /ai/temporal/analyze — stateless F4 longitudinal-series analysis
(`docs/ai/deployment_integration_plan.md` R1). A THIN wrapper over
`src.f4.analyze_longitudinal_series` (pure, deterministic, zero-LLM) — no
engine logic here or in `src.services.stateless_longitudinal`, which only
converts the request payload into `src.f4`'s own harness-input dataclasses,
the same conversion `src/continuous_test.py` already does from ledger files.
`/analyze` computes the full N-session trend-verdict series `src.f4`
produces, matching what `src/continuous_test.py`'s F4 stage writes to
`*_temporal.json`.

The former `POST /ai/temporal/summarize` (pairwise, LLM-narrated, backed by
the `temporal_summary` agent) has been retired — its deterministic
comparators now live in `src.temporal_compare` and are used by F4 as
supplementary per-pair evidence; `/analyze` is the sole live surface.
"""
from __future__ import annotations

import logging

from contracts.longitudinal import TemporalAnalyzeRequest
from fastapi import APIRouter, HTTPException

from src import f4
from src.schemas.longitudinal import LongitudinalAnalysisOutput
from src.services.stateless_longitudinal import build_series_input, sorted_sessions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/temporal", tags=["temporal"])


@router.post("/analyze", response_model=LongitudinalAnalysisOutput)
async def analyze(body: TemporalAnalyzeRequest) -> LongitudinalAnalysisOutput:
    """Stateless F4 longitudinal analysis — `body.sessions` mirrors the
    session-ledger entry shape (`contracts.longitudinal.
    LongitudinalSessionEntry`); this route never reads a ledger file or any
    other server-side session state (R2, stateless compute principle).
    Raises 422 on a `ValueError` from `analyze_longitudinal_series` itself
    (empty `sessions`, or not sorted after this route's own sort — cannot
    happen given the sort below, kept as a defensive re-check since the
    engine's own contract requires it)."""
    if not body.sessions:
        raise HTTPException(status_code=422, detail="sessions must not be empty")
    sessions = sorted_sessions(body.sessions)
    series_input = build_series_input(body.vp_id, sessions)
    try:
        return f4.analyze_longitudinal_series(series_input)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
