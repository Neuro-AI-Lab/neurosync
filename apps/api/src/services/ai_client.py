"""httpx-based client for apps/ai-server.

PRD §0.3 — Platform calls AI server over internal HTTP. mTLS comes in Phase 4.
Timeouts mirror PRD §4.1 SLA budgets (with a small safety margin).
"""

from __future__ import annotations

import httpx
from contracts.safety import SafetyRequest, SafetyResponse

from src.core.config import Settings, get_settings


class AIClientError(RuntimeError):
    """Wraps any communication failure with apps/ai-server."""


class AIClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=2.0)
        self._owned = client is None

    async def safety_classify(self, payload: SafetyRequest) -> SafetyResponse:
        url = f"{self._settings.ai_server_url}/ai/safety/classify"
        try:
            resp = await self._client.post(url, json=payload.model_dump(mode="json"))
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIClientError(f"safety/classify failed: {exc}") from exc
        return SafetyResponse.model_validate(resp.json())

    async def aclose(self) -> None:
        if self._owned:
            await self._client.aclose()


_singleton: AIClient | None = None


def get_ai_client() -> AIClient:
    """FastAPI dependency — reuses one connection pool across requests."""
    global _singleton
    if _singleton is None:
        _singleton = AIClient()
    return _singleton
