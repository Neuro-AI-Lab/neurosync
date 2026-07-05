"""LG K-EXAONE adapter via Friendli dedicated endpoint."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import openai

from src.adapters.base import ChatMessage, ChatResponse, LLMAdapter
from src.config import Settings

logger = logging.getLogger(__name__)

# Friendli-specific extra_body — always disable thinking/reasoning exposure
_FRIENDLI_EXTRA_BODY: dict[str, Any] = {
    "chat_template_kwargs": {"enable_thinking": False},
    "parse_reasoning": True,
    "include_reasoning": False,
}


class KExaoneAdapter(LLMAdapter):
    """Adapter for LG K-EXAONE on Friendli dedicated endpoints.

    Key differences from standard OpenAI:
    - Model param = endpoint ID (not model name)
    - Uses ``extra_body`` for Friendli-specific fields
    - Supports ``response_format: {"type": "json_object"}`` (NOT json_schema)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = openai.AsyncOpenAI(
            api_key=settings.lg_k_exaone_api_key,
            base_url=settings.lg_k_exaone_base_url,
        )
        self._default_model = settings.lg_k_exaone_endpoint_id

    @property
    def adapter_name(self) -> str:
        return "k-exaone"

    async def healthcheck(self) -> bool:
        try:
            resp = await self._client.models.list()
            return len(resp.data) > 0
        except Exception:
            logger.warning("k-exaone healthcheck failed", exc_info=True)
            return False

    def redact_for_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(payload)
        for key in ("api_key", "authorization", "Authorization"):
            if key in redacted:
                redacted[key] = "***REDACTED***"
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
        if not model_id:
            raise ValueError("K-EXAONE endpoint ID not configured (lg_k_exaone_endpoint_id)")

        extra_body = dict(_FRIENDLI_EXTRA_BODY)
        if extra_params:
            extra_body.update(extra_params)

        params: dict[str, Any] = {
            "model": model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": extra_body,
        }

        # K-EXAONE supports json_object but NOT json_schema
        if response_format is not None:
            fmt_type = response_format.get("type", "")
            if fmt_type == "json_schema":
                # Downgrade to json_object — caller must embed schema in prompt
                params["response_format"] = {"type": "json_object"}
                logger.info("k-exaone: downgraded json_schema → json_object")
            else:
                params["response_format"] = response_format

        logger.debug("k-exaone request: %s", self.redact_for_log(params))

        try:
            completion = await self._client.chat.completions.create(**params)
        except openai.APIStatusError as exc:
            logger.error("k-exaone API error %s: %s", exc.status_code, exc.message)
            raise
        except openai.APIConnectionError:
            logger.error("k-exaone connection error")
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
