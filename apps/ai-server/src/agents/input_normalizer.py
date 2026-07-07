"""Input Normalizer agent — corrects STT errors, colloquialisms, and dialect.

Preserves all clinical content and safety-critical expressions.
On any failure, returns original text unchanged (safe fallback).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.adapters.base import ChatMessage
from src.agents.base import BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.input_normalizer import (
    InputNormalizerInput,
    InputNormalizerOutput,
    NormalizationChange,
)

logger = logging.getLogger(__name__)

# Safety-critical expressions that MUST survive normalization.
# Sourced from safety_classifier._CRITICAL_KEYWORDS + _HIGH_KEYWORDS.
_SAFETY_EXPRESSIONS: frozenset[str] = frozenset([
    # CRITICAL tier
    "자살", "죽고 싶", "죽고싶", "목숨", "끝내고 싶", "끝내고싶",
    "죽을", "죽어버리", "세상을 떠나", "유서",
    # ISS-038: bare "칼로" substring-matched benign words ("칼로리") — use
    # verb-anchored variants matching safety_classifier._CRITICAL_KEYWORDS.
    "자해", "손목을 긋", "손목을긋", "손목을 그", "손목을그",
    "칼로 긋", "칼로긋", "칼로 그", "칼로그", "칼로 손목", "칼로손목",
    "약을 많이 먹", "약을많이먹", "약물 과다", "약물과다",
    # HIGH tier
    "죽고", "살고 싶지 않", "살고싶지않", "사라지고 싶", "사라지고싶",
    "없어지고 싶", "없어지고싶",
    "해치고 싶", "때리고 싶", "죽이고 싶",
])

_PROMPT_VERSION = "v1"


class InputNormalizerAgent(BaseAgent):
    """Normalizes STT transcripts and text input for downstream agents."""

    def __init__(
        self,
        model_router: ModelRouter,
        prompt_loader: PromptLoader,
    ) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return "input_normalizer"

    async def run(self, inp: Any, **kwargs: Any) -> InputNormalizerOutput:
        """Normalize input text. Returns original on any failure."""
        if not isinstance(inp, InputNormalizerInput):
            raise TypeError(f"Expected InputNormalizerInput, got {type(inp).__name__}")

        start = time.perf_counter()

        # Empty input → immediate return
        if not inp.raw_text.strip():
            return InputNormalizerOutput(
                normalized_text="",
                original_text=inp.raw_text,
                changes=[],
                change_count=0,
            )

        try:
            result = await self._normalize(inp)
        except Exception as exc:
            logger.warning("InputNormalizer failed, returning original: %s", exc)
            result = self._safe_fallback(inp)

        result.latency_ms = (time.perf_counter() - start) * 1000
        return result

    async def _normalize(self, inp: InputNormalizerInput) -> InputNormalizerOutput:
        """Call LLM for normalization, then validate safety preservation."""
        try:
            system_prompt = self._prompt_loader.load_system_prompt(
                self.agent_name, _PROMPT_VERSION
            )
        except FileNotFoundError:
            logger.warning("InputNormalizer prompt not found, using minimal fallback")
            system_prompt = (
                "당신은 한국어 텍스트 정규화 시스템입니다. "
                "STT 전사 오류, 구어체, 방언을 표준어로 교정합니다. "
                "임상적 의미와 위험 표현은 절대 변경하지 않습니다. "
                "JSON으로 응답하세요: "
                "{normalized_text, changes: [{original, normalized, type, position}]}"
            )

        # Build user message
        user_parts = [f"입력 유형: {inp.input_type}", f"원문: {inp.raw_text}"]
        if inp.dialect_hint:
            user_parts.append(f"방언 힌트: {inp.dialect_hint}")
        user_message = "\n".join(user_parts)

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]

        selection = self._router.select_model(self.agent_name, require_json=True)
        adapter = self._router.get_adapter(selection.adapter_name)

        response_format = None
        if selection.supports_json_schema or selection.supports_json_object:
            response_format = {"type": "json_object"}

        resp = await adapter.chat_timed(
            messages,
            model=selection.model_id,
            temperature=0.1,
            max_tokens=2048,
            response_format=response_format,
        )
        self._router.record_success(selection.adapter_name)

        # Parse response
        data = json.loads(resp.content)
        normalized_text = data.get("normalized_text", inp.raw_text)
        raw_changes = data.get("changes", [])

        changes = []
        for c in raw_changes:
            changes.append(NormalizationChange(
                original=c.get("original", ""),
                normalized=c.get("normalized", ""),
                type=c.get("type", "typo"),
                position=c.get("position", {}),
            ))

        # Safety validation: ensure all safety expressions are preserved
        risk_preserved = self._verify_safety_expressions(inp.raw_text, normalized_text)
        if not risk_preserved:
            logger.error(
                "Safety expression lost during normalization — reverting to original"
            )
            return self._safe_fallback(inp, reason="safety expression lost")

        return InputNormalizerOutput(
            model_used=resp.model,
            prompt_version=_PROMPT_VERSION,
            reason_summary="normalization complete",
            normalized_text=normalized_text,
            original_text=inp.raw_text,
            changes=changes,
            change_count=len(changes),
            clinical_content_preserved=True,
            risk_expressions_preserved=True,
        )

    @staticmethod
    def _verify_safety_expressions(original: str, normalized: str) -> bool:
        """Check that any safety expression in the original is still in the normalized text."""
        original_stripped = original.replace(" ", "")
        normalized_stripped = normalized.replace(" ", "")

        for expr in _SAFETY_EXPRESSIONS:
            expr_stripped = expr.replace(" ", "")
            if expr_stripped in original_stripped and expr_stripped not in normalized_stripped:
                logger.error("Safety expression '%s' lost in normalization", expr)
                return False
        return True

    @staticmethod
    def _safe_fallback(
        inp: InputNormalizerInput, reason: str = "LLM failure"
    ) -> InputNormalizerOutput:
        """Return original text unchanged — safe fallback on any error."""
        return InputNormalizerOutput(
            prompt_version=_PROMPT_VERSION,
            reason_summary=f"fallback: {reason}",
            normalized_text=inp.raw_text,
            original_text=inp.raw_text,
            changes=[],
            change_count=0,
            clinical_content_preserved=True,
            risk_expressions_preserved=True,
        )
