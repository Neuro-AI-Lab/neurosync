"""Platform API entry point.

Phase 1a Day 3+ — Auth slice (FR-001/002/015/026).
WebSocket /sessions, Safety routing 등은 후속 슬라이스.
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src import __version__
from src.api.v1 import api_v1
from src.core.config import get_settings

logger = logging.getLogger(__name__)


async def _audio_purge_loop(interval_seconds: int) -> None:
    """FR-036 — periodically delete original audio past its 48h window.

    In-process convenience scheduler for the demo; production uses cron /
    Celery Beat (scripts/purge_audio.py). Never raises out of the loop.
    """
    from src.db import SessionLocal
    from src.services.stt import purge_expired_audio

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with SessionLocal() as db:
                purged = await purge_expired_audio(db)
            if purged:
                logger.info("audio.purge.cycle", extra={"purged": purged})
        except Exception:  # noqa: BLE001 — a scheduler must never crash the app
            logger.warning("audio.purge.cycle_failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    task: asyncio.Task | None = None
    if settings.audio_purge_interval_seconds > 0:
        task = asyncio.create_task(
            _audio_purge_loop(settings.audio_purge_interval_seconds)
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Neuro-Sync Platform API",
        version=__version__,
        description="Patient onboarding, intake sessions, WebSocket gateway, AI server proxy.",
        lifespan=lifespan,
    )

    # CORS — wildcard + credentials is forbidden by config validators in non-dev.
    # In dev with `["*"]`, drop credentials to avoid the Spec violation.
    is_wildcard = "*" in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=not is_wildcard,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        max_age=600,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "neuro-sync-api",
            "version": __version__,
        }

    app.include_router(api_v1)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            body = {
                "success": False,
                "error": {
                    "code": detail.get("code", "ERROR"),
                    "message": detail.get("message", str(detail)),
                    "details": detail.get("details", []),
                },
            }
        else:
            body = {
                "success": False,
                "error": {"code": "ERROR", "message": str(detail), "details": []},
            }
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "요청 본문이 올바르지 않습니다.",
                    "details": [
                        {
                            "field": ".".join(str(p) for p in err["loc"][1:]),
                            "message": err["msg"],
                        }
                        for err in exc.errors()
                    ],
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        # Never leak internal error message to clients (M-1).
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "내부 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
                    "details": [],
                },
            },
        )

    return app


app = create_app()
