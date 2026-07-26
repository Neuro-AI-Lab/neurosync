"""AI server entry point.

Exposes:
- GET  /health
- POST /ai/safety/classify
- POST /ai/handoff/generate
- POST /ai/chat/respond
- POST /ai/slots/extract
- POST /ai/survey/score
- POST /ai/survey/plan (F3 administration plan — stateless, deployment_integration_plan.md R3)
- POST /ai/temporal/analyze (F4 longitudinal analysis — stateless, R1)
- POST /ai/handoff/report (F4+F5 hand-off report — stateless, R1)
- POST /ai/domain/infer (F2, standalone — not wired into orchestrator.py)
- POST /ai/ocr/parse
- POST /ai/stt/transcribe
- POST /ai/phr/context (PHR ingest — stateless, R2; POST once at session
  start, thread the returned context into subsequent /ai/chat/respond calls)

Stateless compute principle (R2): `/ai/temporal/analyze`/`/ai/handoff/report`/
`/ai/survey/plan`/`/ai/phr/context` never read or write server-side session
state — every call carries its own full input payload; the backend owns
patient/session identity + persistence.

RAG is in-process only, now and at deployment — there is no RAG HTTP API
(ADR-017: permanently out of scope). `src.rag.retrieval.retrieve_grounding`
/`retrieve_domain_chunks` are called directly with a local DB session (see
`src/f2.py:176-180`, `src/rag_chat.py`).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from src import __version__
from src.routes.chat import router as chat_router
from src.routes.domain import router as domain_router
from src.routes.handoff import router as handoff_router
from src.routes.nearby import router as nearby_router
from src.routes.ocr import router as ocr_router
from src.routes.phr import router as phr_router
from src.routes.safety import router as safety_router
from src.routes.sentiment import router as sentiment_router
from src.routes.slots import router as slots_router
from src.routes.stt import router as stt_router
from src.routes.survey import router as survey_router
from src.routes.temporal import router as temporal_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(
    title="Neuro-Sync AI Server",
    version=__version__,
    description="Multi-agent AI service — Safety, Chat, Handoff (+ STT, OCR planned).",
)

# ── Mount domain routers ──────────────────────────────────────────────
app.include_router(safety_router)
app.include_router(handoff_router)
app.include_router(chat_router)
app.include_router(slots_router)
app.include_router(survey_router)
app.include_router(sentiment_router)
app.include_router(temporal_router)
app.include_router(ocr_router)
app.include_router(stt_router)
# F2 (PLAN-2026-W28-C) — standalone route, NOT wired into orchestrator.py's
# 11-state machine (G-D gate defers production integration).
app.include_router(domain_router)
app.include_router(nearby_router)
app.include_router(phr_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "neuro-sync-ai-server",
        "version": __version__,
    }
