"""AI server entry point.

Phase 1a Day 1~2 부트스트랩 — /health 만 노출.
5개 인터페이스(/ai/chat/respond, /ai/safety/classify, /ai/stt/transcribe,
/ai/ocr/parse, /ai/handoff/generate)는 각 도메인 라우터로 추가 예정.
"""

from fastapi import FastAPI

from src import __version__
from src.api.safety import router as safety_router

app = FastAPI(
    title="Neuro-Sync AI Server",
    version=__version__,
    description="5 HTTP interfaces consumed by Platform API.",
)

app.include_router(safety_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "neuro-sync-ai-server",
        "version": __version__,
    }
