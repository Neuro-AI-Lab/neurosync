"""Abstract base classes for vendor adapters."""

from __future__ import annotations

import abc
import time
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """Simplified chat message for adapter interface."""

    role: str  # system | user | assistant
    content: str


class ChatResponse(BaseModel):
    """Unified response from any LLM adapter."""

    content: str
    model: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    latency_ms: float = 0.0
    raw_response: Any | None = None


class VendorAdapter(abc.ABC):
    """Base class for all vendor integrations (LLM, STT, OCR, etc.)."""

    @property
    @abc.abstractmethod
    def adapter_name(self) -> str:
        """Unique identifier for this adapter, matching registry keys."""

    @abc.abstractmethod
    async def healthcheck(self) -> bool:
        """Return True if the vendor endpoint is reachable."""

    @abc.abstractmethod
    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *payload* with secrets/PII masked for logging."""


class LLMAdapter(VendorAdapter):
    """Specialised base for text-generation adapters (OpenAI-compatible)."""

    @abc.abstractmethod
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Send a chat completion request and return a unified response."""

    async def chat_timed(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        """Wrapper that automatically records latency_ms."""
        start = time.perf_counter()
        resp = await self.chat(messages, **kwargs)
        resp.latency_ms = (time.perf_counter() - start) * 1000
        return resp
