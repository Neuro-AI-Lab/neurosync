"""httpx-based client for apps/ai-server.

PRD §0.3 — Platform calls AI server over internal HTTP. mTLS comes in Phase 4.
Timeouts mirror PRD §4.1 SLA budgets (with a small safety margin).
"""

from __future__ import annotations

import httpx
from contracts.chat import ChatRequest, ChatResponse
from contracts.handoff import HandoffRequest, HandoffResponse
from contracts.safety import SafetyRequest, SafetyResponse
from contracts.stt import STTRequest, STTResponse

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

    async def chat_respond(self, payload: ChatRequest) -> ChatResponse:
        """POST /ai/chat/respond. Best-effort dialogue turn (non-streaming).

        First-token SLA is 800ms but the full reply may take a few seconds, so
        this uses its own timeout independent of the safety budget."""
        url = f"{self._settings.ai_server_url}/ai/chat/respond"
        try:
            resp = await self._client.post(
                url,
                json=payload.model_dump(mode="json"),
                timeout=self._settings.ai_chat_timeout_seconds,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIClientError(f"chat/respond failed: {exc}") from exc
        return ChatResponse.model_validate(resp.json())

    async def stt_transcribe(self, payload: STTRequest) -> STTResponse:
        """POST /ai/stt/transcribe. PRD §4.1 SLA < 2,000ms; the AI server runs
        its own vendor fallback chain within this budget."""
        url = f"{self._settings.ai_server_url}/ai/stt/transcribe"
        try:
            resp = await self._client.post(
                url,
                json=payload.model_dump(mode="json"),
                timeout=self._settings.ai_stt_timeout_seconds,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIClientError(f"stt/transcribe failed: {exc}") from exc
        return STTResponse.model_validate(resp.json())

    async def handoff_generate(self, payload: HandoffRequest) -> HandoffResponse:
        """POST /ai/handoff/generate. Generation budget is generous (PRD §4.1
        p95 < 30s) so this call uses its own longer timeout."""
        url = f"{self._settings.ai_server_url}/ai/handoff/generate"
        try:
            resp = await self._client.post(
                url,
                json=payload.model_dump(mode="json"),
                timeout=self._settings.ai_handoff_timeout_seconds,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIClientError(f"handoff/generate failed: {exc}") from exc
        return HandoffResponse.model_validate(resp.json())

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
