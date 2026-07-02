"""Safety Classifier agent — Rule screening + LLM contextual judgment.

Architecture (C 방식):
  1. Rule Engine: 빠른 1차 키워드 스크리닝 (위험 후보 감지)
  2. LLM Engine: 문맥 기반 최종 판정 (부정, 시제, 뉘앙스 이해)

Merge 전략:
  - Rule이 medium 이하 → LLM 결과를 최종 판정으로 사용
  - Rule이 high/critical → Rule이 감지한 키워드를 LLM에 전달, LLM이 최종 판정
  - LLM 장애 시 → Rule 결과를 safety net으로 사용
  - LLM이 독립적으로 감지한 위험은 Rule 미감지여도 반영
"""

from __future__ import annotations

import asyncio
import json
import logging
import re as _re
import time
from typing import Any

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.common import CTRSLevel, RISK_TO_CTRS, RiskLevel
from src.schemas.safety import SafetyClassification, SafetyInput, SafetyOutput

logger = logging.getLogger(__name__)

# ── Korean crisis keyword dictionary ──────────────────────────────────

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

# ── Risk level ordering ─────────────────────────────────────────────

_RISK_ORDER = {
    RiskLevel.none: 0,
    RiskLevel.low: 1,
    RiskLevel.medium: 2,
    RiskLevel.high: 3,
    RiskLevel.critical: 4,
}

# ── LLM Prompt ─────────────────────────────────────────────────────

_LLM_FALLBACK_PROMPT = (
    "환자 메시지의 위험 수준을 분류하세요. "
    "risk_level: none|low|medium|high|critical. "
    "JSON 출력: {risk_level, categories, flagged_phrases, confidence, reason_summary}"
)

_LLM_RULE_CONTEXT_TEMPLATE = """
[키워드 스크리닝 결과]
1차 스크리닝에서 아래 키워드가 감지되었습니다. 하지만 키워드만으로는 실제 위험을 정확히 판단할 수 없습니다.
전체 대화 문맥을 고려하여 최종 위험도를 판정해 주세요.

감지된 키워드: {flagged_phrases}
스크리닝 위험 수준: {rule_level}
감지 카테고리: {categories}

특히 다음을 확인하세요:
- 환자가 해당 키워드를 부정하는 맥락에서 사용했는가? (예: "~없어요", "~아니에요")
- 과거 경험을 이야기하는 것인가, 현재 의도를 표현하는 것인가?
- 상담사의 질문을 반복하는 것인가, 자신의 생각을 표현하는 것인가?

문맥 판단 결과가 키워드 스크리닝과 다르면, 문맥 판단을 우선하세요."""


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


class SafetyClassifierAgent(BaseAgent):
    """Safety classifier: Rule screening → LLM contextual judgment.

    Rule Engine = 빠른 1차 스크리닝 (위험 후보 감지)
    LLM Engine = 문맥 기반 최종 판정 (최종 결정권)
    """

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

    # ── Rule Engine (1차 스크리닝) ──────────────────────────────────

    def _rule_classify(self, text: str) -> tuple[RiskLevel, list[str], list[str]]:
        """Keyword-based 1st-pass screening.

        Returns (risk_level, categories, flagged_phrases).
        This is a CANDIDATE, not the final judgment.
        """
        text_lower = text.lower().replace(" ", "")
        text_original = text.lower()

        level = RiskLevel.none
        categories: list[str] = []
        flagged: list[str] = []

        def _match(keyword: str) -> bool:
            normalized = keyword.replace(" ", "")
            return normalized in text_lower or keyword in text_original

        for keyword, category in _CRITICAL_KEYWORDS:
            if _match(keyword):
                level = _max_risk(level, RiskLevel.critical)
                if category not in categories:
                    categories.append(category)
                flagged.append(keyword)

        if level == RiskLevel.none:
            for keyword, category in _HIGH_KEYWORDS:
                if _match(keyword):
                    level = _max_risk(level, RiskLevel.high)
                    if category not in categories:
                        categories.append(category)
                    flagged.append(keyword)

        if level == RiskLevel.none:
            for keyword, category in _MEDIUM_KEYWORDS:
                if _match(keyword):
                    level = _max_risk(level, RiskLevel.medium)
                    if category not in categories:
                        categories.append(category)
                    flagged.append(keyword)

        return level, categories, flagged

    # ── LLM Engine (최종 판정) ─────────────────────────────────────

    async def _llm_classify(
        self,
        text: str,
        conversation_history: list[dict[str, str]],
        rule_context: str | None = None,
    ) -> tuple[SafetyClassification, str, float]:
        """LLM-based contextual classification — final arbiter.

        Args:
            rule_context: Optional rule screening results to inject into prompt.
                          When provided, LLM sees the flagged keywords and is asked
                          to make a contextual judgment.
        """
        selection = self._router.select_model(
            self.agent_name, require_json=True
        )
        adapter = self._router.get_adapter(selection.adapter_name)

        # Load prompt from MD file (PromptLoader), fallback to minimal
        try:
            system_prompt = self._prompt_loader.load_system_prompt("safety_classifier", "v1")
        except FileNotFoundError:
            logger.warning("Safety classifier prompt not found, using fallback")
            system_prompt = _LLM_FALLBACK_PROMPT

        if rule_context:
            system_prompt += "\n\n" + rule_context

        messages = [ChatMessage(role="system", content=system_prompt)]

        # Add recent conversation context
        for turn in conversation_history[-6:]:
            messages.append(ChatMessage(
                role=turn.get("role", "user"),
                content=turn["content"],
            ))

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

            try:
                data = json.loads(resp.content)
                classification = SafetyClassification.model_validate(data)
            except (json.JSONDecodeError, Exception) as parse_exc:
                logger.warning("Failed to parse LLM safety response: %s", parse_exc)
                classification = SafetyClassification(
                    risk_level=RiskLevel.none,
                    confidence=0.0,
                    reason_summary="LLM response parse failure",
                )

            return classification, resp.model, resp.latency_ms

        except Exception as exc:
            logger.error("LLM safety classification failed: %s", exc)
            self._router.record_failure(selection.adapter_name, exc)

            # Try fallback adapter
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
                    logger.error("Fallback safety also failed: %s", fb_exc)

            # All LLM unavailable — return None so caller uses rule fallback
            return (
                SafetyClassification(
                    risk_level=RiskLevel.none,
                    confidence=0.0,
                    reason_summary="LLM unavailable",
                ),
                "none",
                0.0,
            )

    # ── Main: Rule screening → LLM judgment ────────────────────────

    async def run(self, inp: AgentInput, **kwargs: Any) -> SafetyOutput:
        """Rule screening → LLM contextual judgment.

        Flow:
          1. Rule engine scans for crisis keywords (fast, deterministic)
          2. If rule detects high/critical:
             - Pass flagged keywords + context to LLM for final judgment
             - LLM can downgrade (부정 문맥) or confirm
          3. If rule detects medium or less:
             - LLM independently classifies (may catch things rules miss)
          4. If LLM unavailable:
             - Fall back to rule result (safety net)
        """
        start = time.perf_counter()

        if not isinstance(inp, SafetyInput):
            raise TypeError(f"Expected SafetyInput, got {type(inp).__name__}")

        # Step 1: Rule screening (synchronous, fast)
        rule_level, rule_categories, rule_flagged = self._rule_classify(
            inp.user_message
        )

        logger.info(
            "Rule screening: level=%s, flagged=%s",
            rule_level, rule_flagged,
        )

        # Step 2: LLM classification
        rule_context = None
        if _RISK_ORDER[rule_level] >= _RISK_ORDER[RiskLevel.high]:
            # Rule detected high/critical → pass keywords to LLM for contextual review
            rule_context = _LLM_RULE_CONTEXT_TEMPLATE.format(
                flagged_phrases=", ".join(rule_flagged),
                rule_level=rule_level.value,
                categories=", ".join(rule_categories),
            )

        llm_classification, model_used, llm_latency = await self._llm_classify(
            inp.user_message, inp.conversation_history, rule_context,
        )

        llm_available = model_used != "none"

        # Step 3: Determine final level
        if llm_available:
            if _RISK_ORDER[rule_level] >= _RISK_ORDER[RiskLevel.high]:
                # Rule flagged high/critical → LLM is the final arbiter
                final_level = llm_classification.risk_level
                logger.info(
                    "Rule=%s → LLM judgment=%s (LLM is final arbiter)",
                    rule_level, final_level,
                )
            else:
                # Rule didn't flag high → use LLM result directly
                # But if LLM catches something rules missed, respect it
                final_level = llm_classification.risk_level
        else:
            # LLM unavailable → rule result is the safety net
            final_level = rule_level
            logger.warning("LLM unavailable — using rule result as fallback: %s", rule_level)

        # Merge categories and flagged phrases
        all_categories = list(dict.fromkeys(
            rule_categories + llm_classification.categories
        ))
        all_flagged = list(dict.fromkeys(
            rule_flagged + llm_classification.flagged_phrases
        ))

        confidence = llm_classification.confidence if llm_available else 0.5

        latency_ms = (time.perf_counter() - start) * 1000

        # Map to CTRS
        ctrs = RISK_TO_CTRS.get(final_level, CTRSLevel.STABLE)
        crisis_activated = ctrs <= CTRSLevel.HIGH_RISK  # CTRS 1-2
        needs_review = ctrs <= CTRSLevel.ACUTE  # CTRS 1-3

        return SafetyOutput(
            model_used=model_used,
            prompt_version="v1",
            latency_ms=latency_ms,
            reason_summary=llm_classification.reason_summary or "Rule screening + LLM judgment",
            risk_level=final_level,
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
