"""Platform API entry point.

Phase 1a Day 1~2 부트스트랩 — /health 만 노출.
실제 라우터(/api/v1/auth, /api/v1/sessions, WS) 는 Phase 1a Day 3~ 부터 추가.
"""

from fastapi import FastAPI

from src import __version__

app = FastAPI(
    title="Neuro-Sync Platform API",
    version=__version__,
    description="Patient onboarding, intake sessions, WebSocket gateway, AI server proxy.",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "neuro-sync-api",
        "version": __version__,
    }
