"""Safety Classifier agent — dual rule + LLM classification with danger-takes-priority merge."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.common import RISK_TO_CTRS, CTRSLevel, RiskLevel
from src.schemas.safety import SafetyClassification, SafetyInput, SafetyOutput

logger = logging.getLogger(__name__)

# ── Korean crisis keyword dictionary ──────────────────────────────────
# Ordered by severity — critical phrases first.
_CRITICAL_KEYWORDS: list[tuple[str, str]] = [
    ("자살", "suicidal_ideation"),
    ("죽고 싶", "suicidal_ideation"),
    ("죽고싶", "suicidal_ideation"),
    ("목숨", "suicidal_ideation"),
    ("끝내고 싶", "suicidal_ideation"),
    ("끝내고싶", "suicidal_ideation"),
    ("죽을", "suicidal_ideation"),
    ("죽어버리", "suicidal_ideation"),
    ("세상을 떠나", "suicidal_ideation"),
    ("유서", "suicidal_ideation"),
    ("자해", "self_harm"),
    ("손목을 긋", "self_harm"),
    ("손목을긋", "self_harm"),
    ("손목을 그", "self_harm"),
    ("손목을그", "self_harm"),
    ("칼로", "self_harm"),
    ("약을 많이 먹", "self_harm_overdose"),
    ("약을많이먹", "self_harm_overdose"),
    ("약물 과다", "self_harm_overdose"),
    ("약물과다", "self_harm_overdose"),
]

_HIGH_KEYWORDS: list[tuple[str, str]] = [
    ("죽고", "suicidal_ideation"),
    ("살고 싶지 않", "suicidal_ideation"),
    ("살고싶지않", "suicidal_ideation"),
    ("사라지고 싶", "suicidal_ideation"),
    ("사라지고싶", "suicidal_ideation"),
    ("없어지고 싶", "suicidal_ideation"),
    ("없어지고싶", "suicidal_ideation"),
    ("해치고 싶", "harm_to_others"),
    ("때리고 싶", "harm_to_others"),
    ("죽이고 싶", "harm_to_others"),
]

_MEDIUM_KEYWORDS: list[tuple[str, str]] = [
    ("힘들어서 못 살", "distress"),
    ("너무 힘들", "distress"),
    ("미치겠", "distress"),
    ("포기하고 싶", "despair"),
    ("희망이 없", "despair"),
    ("의미가 없", "despair"),
]

# Risk level ordering for comparison
_RISK_ORDER = {
    RiskLevel.none: 0,
    RiskLevel.low: 1,
    RiskLevel.medium: 2,
    RiskLevel.high: 3,
    RiskLevel.critical: 4,
}

_SAFETY_SYSTEM_PROMPT = """당신은 Neuro-Sync 안전 분류 AI입니다.
환자의 메시지를 분석하여 위험 수준을 분류합니다.

위험 수준:
- none: 위험 신호 없음
- low: 경미한 스트레스 표현
- medium: 주의가 필요한 정서적 고통 표현
- high: 자해/자살 암시 또는 타해 암시
- critical: 명시적 자살/자해 의도 또는 계획

반드시 아래 JSON 형식으로만 응답하세요:
{
  "risk_level": "none|low|medium|high|critical",
  "categories": ["카테고리"],
  "flagged_phrases": ["관련 문구"],
  "confidence": 0.0~1.0,
  "reason_summary": "한 줄 설명"
}"""


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher of two risk levels."""
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


class SafetyClassifierAgent(BaseAgent):
    """Dual-path safety classifier: rule-based + LLM, merged with danger-takes-priority."""

    def __init__(
        self,
        model_router: ModelRouter,
        prompt_loader: PromptLoader,
    ) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return "safety_classifier"

    def _rule_classify(self, text: str) -> tuple[RiskLevel, list[str], list[str]]:
        """Keyword-based classification — fast, deterministic, zero-latency.

        Returns:
            (risk_level, categories, flagged_phrases)
        """
        text_lower = text.lower().replace(" ", "")
        text_original = text.lower()

        level = RiskLevel.none
        categories: list[str] = []
        flagged: list[str] = []

        for keyword, category in _CRITICAL_KEYWORDS:
            normalized = keyword.replace(" ", "")
            if normalized in text_lower or keyword in text_original:
                level = _max_risk(level, RiskLevel.critical)
                if category not in categories:
                    categories.append(category)
                flagged.append(keyword)

        if level == RiskLevel.none:
            for keyword, category in _HIGH_KEYWORDS:
                normalized = keyword.replace(" ", "")
                if normalized in text_lower or keyword in text_original:
                    level = _max_risk(level, RiskLevel.high)
                    if category not in categories:
                        categories.append(category)
                    flagged.append(keyword)

        if level == RiskLevel.none:
            for keyword, category in _MEDIUM_KEYWORDS:
                normalized = keyword.replace(" ", "")
                if normalized in text_lower or keyword in text_original:
                    level = _max_risk(level, RiskLevel.medium)
                    if category not in categories:
                        categories.append(category)
                    flagged.append(keyword)

        return level, categories, flagged

    async def _llm_classify(
        self, text: str, conversation_history: list[dict[str, str]]
    ) -> tuple[SafetyClassification, str, float]:
        """LLM-based classification — nuanced understanding of context.

        Returns:
            (classification, model_used, latency_ms)
        """
        selection = self._router.select_model(
            self.agent_name, require_json=True
        )
        adapter = self._router.get_adapter(selection.adapter_name)

        messages = [ChatMessage(role="system", content=_SAFETY_SYSTEM_PROMPT)]

        # Add recent conversation context (last 4 turns max)
        for turn in conversation_history[-4:]:
            messages.append(ChatMessage(role=turn.get("role", "user"), content=turn["content"]))

        messages.append(ChatMessage(role="user", content=text))

        response_format = None
        if selection.supports_json_schema or selection.supports_json_object:
            response_format = {"type": "json_object"}

        try:
            assert isinstance(adapter, LLMAdapter)
            resp = await adapter.chat_timed(
                messages,
                model=selection.model_id,
                temperature=0.1,
                max_tokens=512,
                response_format=response_format,
            )
            self._router.record_success(selection.adapter_name)

            # Parse response
            try:
                data = json.loads(resp.content)
                classification = SafetyClassification.model_validate(data)
            except (json.JSONDecodeError, Exception) as parse_exc:
                logger.warning(
                    "Failed to parse LLM safety response: %s", parse_exc
                )
                classification = SafetyClassification(
                    risk_level=RiskLevel.none,
                    confidence=0.0,
                    reason_summary="LLM response parse failure — defaulting to none",
                )

            return classification, resp.model, resp.latency_ms

        except Exception as exc:
            logger.error("LLM safety classification failed: %s", exc)
            self._router.record_failure(selection.adapter_name, exc)

            # Try fallback
            fallback = self._router.get_fallback(
                self.agent_name, selection.adapter_name, str(exc)
            )
            if fallback:
                fallback_adapter = self._router.get_adapter(fallback.adapter_name)
                assert isinstance(fallback_adapter, LLMAdapter)
                fb_format = (
                    {"type": "json_object"}
                    if fallback.supports_json_schema or fallback.supports_json_object
                    else None
                )
                try:
                    resp = await fallback_adapter.chat_timed(
                        messages,
                        model=fallback.model_id,
                        temperature=0.1,
                        max_tokens=512,
                        response_format=fb_format,
                    )
                    self._router.record_success(fallback.adapter_name)
                    data = json.loads(resp.content)
                    classification = SafetyClassification.model_validate(data)
                    return classification, resp.model, resp.latency_ms
                except Exception as fb_exc:
                    logger.error("Fallback safety classification also failed: %s", fb_exc)

            # All LLM paths failed — return none for LLM path.
            # The merge with rule_classify result preserves any danger the rules found.
            # If BOTH rule + LLM fail to detect anything, the orchestrator's safety
            # timeout handler defaults to CTRS 2 as the safe-side fallback.
            return (
                SafetyClassification(
                    risk_level=RiskLevel.none,
                    confidence=0.0,
                    reason_summary="LLM classification unavailable — using rule engine only",
                ),
                "none",
                0.0,
            )

    async def run(self, inp: AgentInput, **kwargs: Any) -> SafetyOutput:
        """Execute dual-path classification and merge results."""
        start = time.perf_counter()

        if not isinstance(inp, SafetyInput):
            raise TypeError(f"Expected SafetyInput, got {type(inp).__name__}")

        # Run rule and LLM in parallel
        rule_result, llm_result = await asyncio.gather(
            asyncio.to_thread(
                self._rule_classify, inp.user_message
            ),
            self._llm_classify(inp.user_message, inp.conversation_history),
        )

        rule_level, rule_categories, rule_flagged = rule_result
        llm_classification, model_used, llm_latency = llm_result

        # ── Merge: danger-takes-priority ──────────────────────────────
        merged_level = _max_risk(rule_level, llm_classification.risk_level)

        # Special rule: if rule hits but LLM says none → keep at least medium
        if rule_level != RiskLevel.none and llm_classification.risk_level == RiskLevel.none:
            merged_level = _max_risk(merged_level, RiskLevel.medium)
            logger.info(
                "Rule hit (%s) but LLM=none → elevated to at least medium",
                rule_level,
            )

        # Merge categories and flagged phrases
        all_categories = list(dict.fromkeys(rule_categories + llm_classification.categories))
        all_flagged = list(dict.fromkeys(rule_flagged + llm_classification.flagged_phrases))

        # Confidence: prefer LLM confidence, boost if rule agrees
        confidence = llm_classification.confidence
        if rule_level != RiskLevel.none and llm_classification.risk_level != RiskLevel.none:
            confidence = min(1.0, confidence + 0.15)  # dual agreement boost

        latency_ms = (time.perf_counter() - start) * 1000

        # Map merged risk level to CTRS
        ctrs = RISK_TO_CTRS.get(merged_level, CTRSLevel.STABLE)

        # CTRS 1-2 = crisis (not just critical)
        crisis_activated = ctrs <= CTRSLevel.HIGH_RISK
        needs_review = ctrs <= CTRSLevel.ACUTE  # CTRS 1-3

        return SafetyOutput(
            model_used=model_used,
            prompt_version="v1",
            latency_ms=latency_ms,
            reason_summary=llm_classification.reason_summary or "Dual-path safety classification",
            risk_level=merged_level,
            categories=all_categories,
            flagged_phrases=all_flagged,
            confidence=confidence,
            rule_triggered=rule_level != RiskLevel.none,
            llm_risk_level=llm_classification.risk_level,
            rule_risk_level=rule_level,
            ctrs_level=ctrs,
            requires_human_review=needs_review,
            crisis_protocol_activated=crisis_activated,
        )
