"""SKT A.X (A.X-K1) LLM adapter — no native JSON mode, prompt-only + repair."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from src.adapters.base import ChatMessage, ChatResponse, LLMAdapter
from src.config import Settings

logger = logging.getLogger(__name__)

# ── Rate limiting ──────────────────────────────────────────────────────
_DEFAULT_MAX_CONCURRENT = 3

# ── Retry config ───────────────────────────────────────────────────────
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 1.0  # 1s → 2s → 4s


class AkLlmAdapter(LLMAdapter):
    """Adapter for SKT A.X-K1 LLM.

    Constraints:
    - NO native ``response_format`` — uses prompt-only JSON + Pydantic validation
    - Rate-limited to 3 concurrent requests via asyncio.Semaphore
    - Exponential backoff on transient failures (1s → 2s → 4s)
    """

    def __init__(self, settings: Settings, max_concurrent: int = _DEFAULT_MAX_CONCURRENT) -> None:
        self._settings = settings
        self._client = openai.AsyncOpenAI(
            api_key=settings.skt_a_x_api_key,
            base_url=settings.skt_a_x_rest_base_url.rstrip("/") + "/v1",
        )
        self._default_model = settings.skt_a_x_llm_model
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def adapter_name(self) -> str:
        return "ak-llm"

    async def healthcheck(self) -> bool:
        try:
            resp = await self._client.models.list()
            return len(resp.data) > 0
        except Exception:
            logger.warning("ak-llm healthcheck failed", exc_info=True)
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
        """Send chat completion with rate limiting and exponential backoff.

        ``response_format`` is IGNORED at the API level — A.X-K1 does not
        support it.  JSON compliance is enforced via prompt instructions and
        post-hoc Pydantic validation (see :meth:`chat_json`).
        """
        model_id = model or self._default_model
        params: dict[str, Any] = {
            "model": model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if extra_params:
            for k, v in extra_params.items():
                if k not in params:
                    params[k] = v

        # NOTE: response_format intentionally omitted — not supported

        logger.debug("ak-llm request: %s", self.redact_for_log(params))

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            async with self._semaphore:
                try:
                    completion = await self._client.chat.completions.create(**params)
                    break
                except openai.RateLimitError as exc:
                    last_exc = exc
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "ak-llm rate-limited (attempt %d/%d), retrying in %.1fs",
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                except openai.APIStatusError as exc:
                    if exc.status_code >= 500:
                        last_exc = exc
                        wait = _BACKOFF_BASE_S * (2**attempt)
                        logger.warning(
                            "ak-llm server error %s (attempt %d/%d), retrying in %.1fs",
                            exc.status_code,
                            attempt + 1,
                            _MAX_RETRIES,
                            wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise
                except openai.APIConnectionError as exc:
                    last_exc = exc
                    wait = _BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "ak-llm connection error (attempt %d/%d), retrying in %.1fs",
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
        else:
            raise RuntimeError(
                f"ak-llm failed after {_MAX_RETRIES} retries"
            ) from last_exc

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

    async def chat_json(
        self,
        messages: Sequence[ChatMessage],
        schema_cls: type[BaseModel],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        extra_params: dict[str, Any] | None = None,
    ) -> tuple[BaseModel, ChatResponse]:
        """Chat + parse + validate as *schema_cls*, with 1 repair retry.

        Returns:
            Tuple of (parsed Pydantic model, raw ChatResponse).

        Raises:
            ValueError: If JSON cannot be parsed/validated after repair retry.
        """
        resp = await self.chat_timed(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_params=extra_params,
        )

        # First attempt — parse + validate
        parsed, error = self._try_parse(resp.content, schema_cls)
        if parsed is not None:
            return parsed, resp

        # Repair retry — ask the model to fix its own output
        logger.info("ak-llm: repair retry for %s (error: %s)", schema_cls.__name__, error)
        repair_msg = ChatMessage(
            role="user",
            content=(
                f"Your previous JSON output had a validation error:\n{error}\n\n"
                f"Please output ONLY valid JSON matching the schema. No markdown fences."
            ),
        )
        repair_messages = list(messages) + [
            ChatMessage(role="assistant", content=resp.content),
            repair_msg,
        ]
        resp2 = await self.chat_timed(
            repair_messages,
            model=model,
            temperature=0.1,
            max_tokens=max_tokens,
            extra_params=extra_params,
        )

        parsed2, error2 = self._try_parse(resp2.content, schema_cls)
        if parsed2 is not None:
            resp2.latency_ms += resp.latency_ms  # accumulate total
            return parsed2, resp2

        raise ValueError(
            f"ak-llm: failed to produce valid {schema_cls.__name__} after repair. "
            f"Last error: {error2}"
        )

    @staticmethod
    def _try_parse(
        raw: str, schema_cls: type[BaseModel]
    ) -> tuple[BaseModel | None, str | None]:
        """Attempt to extract JSON from raw text and validate against schema."""
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (possibly ```json)
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return None, f"JSON parse error: {exc}"

        try:
            return schema_cls.model_validate(data), None
        except ValidationError as exc:
            return None, f"Validation error: {exc}"
