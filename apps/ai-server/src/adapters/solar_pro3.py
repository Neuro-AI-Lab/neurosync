"""Upstage Solar Pro3 adapter — OpenAI-compatible with native json_schema support."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import openai

from src.adapters.base import ChatMessage, ChatResponse, LLMAdapter
from src.config import Settings

logger = logging.getLogger(__name__)


class SolarPro3Adapter(LLMAdapter):
    """Adapter for Upstage Solar Pro3 via OpenAI-compatible API.

    Capabilities:
    - Native ``response_format`` with ``json_schema`` type
    - ``reasoning_effort`` parameter support
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # REV-001 Issue 5: explicit client timeout, no longer the openai
        # SDK's 10-minute default — see `Settings.llm_client_timeout_s`.
        self._client = openai.AsyncOpenAI(
            api_key=settings.upstage_api_key,
            base_url=settings.upstage_base_url,
            timeout=settings.llm_client_timeout_s,
        )
        self._default_model = settings.upstage_chat_model

    @property
    def adapter_name(self) -> str:
        return "solar-pro3"

    async def healthcheck(self) -> bool:
        try:
            resp = await self._client.models.list()
            return len(resp.data) > 0
        except Exception:
            logger.warning("solar-pro3 healthcheck failed", exc_info=True)
            return False

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(payload)
        for key in ("api_key", "authorization", "Authorization"):
            if key in redacted:
                redacted[key] = "***REDACTED***"
        # Redact content of system messages (may contain prompt IP)
        if "messages" in redacted:
            redacted["messages"] = [
                {**m, "content": m["content"][:80] + "..." if m.get("role") == "system" else m}
                if isinstance(m, dict)
                else m
                for m in redacted["messages"]
            ]
        return redacted

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
        model_id = model or self._default_model
        params: dict[str, Any] = {
            "model": model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Solar Pro3 supports native json_schema response_format
        if response_format is not None:
            params["response_format"] = response_format

        # Merge extra params (e.g. reasoning_effort)
        if extra_params:
            for k, v in extra_params.items():
                if k not in params:
                    params[k] = v

        logger.debug("solar-pro3 request: %s", self.redact_for_log(params))

        try:
            completion = await self._client.chat.completions.create(**params)
        except openai.APIStatusError as exc:
            logger.error("solar-pro3 API error %s: %s", exc.status_code, exc.message)
            raise
        except openai.APIConnectionError:
            logger.error("solar-pro3 connection error")
            raise

        choice = completion.choices[0]
        usage = (
            {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }
            if completion.usage
            else None
        )

        return ChatResponse(
            content=choice.message.content or "",
            model=completion.model,
            finish_reason=choice.finish_reason,
            usage=usage,
        )
