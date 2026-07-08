"""AI server entry point.

Exposes:
- GET  /health
- POST /ai/safety/classify
- POST /ai/handoff/generate
- POST /ai/chat/respond
- POST /ai/slots/extract
- POST /ai/survey/score
- POST /ai/ocr/parse
- POST /ai/stt/transcribe
- POST /ai/rag/grounding (bearer-token auth, NS_RAG_API_KEY — ADR-013)
- POST /ai/domain/infer (F2, standalone — not wired into orchestrator.py)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from src import __version__
from src.rag.route import router as rag_router
from src.routes.chat import router as chat_router
from src.routes.domain import router as domain_router
from src.routes.handoff import router as handoff_router
from src.routes.ocr import router as ocr_router
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
app.include_router(rag_router)
app.include_router(ocr_router)
app.include_router(stt_router)
# F2 (PLAN-2026-W28-C) — standalone route, NOT wired into orchestrator.py's
# 11-state machine (G-D gate defers production integration).
app.include_router(domain_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "neuro-sync-ai-server",
        "version": __version__,
    }
