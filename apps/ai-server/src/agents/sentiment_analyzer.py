"""Sentiment Analyzer agent — per-utterance emotion classification + session summary.

Two modes:
  Mode A (per-utterance): Classify emotions for a single patient utterance.
  Mode B (session-level): Aggregate all utterance results into a session report.

This agent's output is consumed by:
  - TemporalSummaryAgent (sentiment trend in plot_data)
  - HandoffGeneratorAgent (per-utterance tags in Section 8)
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from typing import Any

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.sentiment import (
    EmotionScore,
    PerUtteranceTag,
    PolarityPoint,
    SentimentSessionInput,
    SentimentSessionOutput,
    SentimentUtteranceInput,
    SentimentUtteranceOutput,
)

logger = logging.getLogger(__name__)

# PLAN-2026-W28 C1: v2 (prompt_redesign_v3.md §2.5) — applies to utterance mode
# only. Session mode (_analyze_session) never calls the LLM / loads a prompt
# file, so its "v1" literal below is a dead-path label, not a real prompt pin;
# it is intentionally left unchanged (out of this bump's scope).
PROMPT_VERSION = "v2"


class SentimentAnalyzerAgent(BaseAgent):
    """Dual-mode sentiment analyzer for mental health conversations."""

    def __init__(self, model_router: ModelRouter, prompt_loader: PromptLoader) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return "sentiment_analyzer"

    async def run(self, inp: AgentInput, **kwargs: Any) -> AgentInput:
        """Dispatch to Mode A or Mode B based on input type."""
        if isinstance(inp, SentimentUtteranceInput):
            return await self._analyze_utterance(inp)
        elif isinstance(inp, SentimentSessionInput):
            return await self._analyze_session(inp)
        else:
            raise TypeError(
                "Expected SentimentUtteranceInput or SentimentSessionInput, "
                f"got {type(inp).__name__}"
            )

    async def _analyze_utterance(self, inp: SentimentUtteranceInput) -> SentimentUtteranceOutput:
        """Mode A: Analyze a single patient utterance."""
        start = time.perf_counter()

        # BUG-021: makes a degraded run machine-visible on this agent's own
        # output artifact, not just a WARNING log line — same pattern as
        # ClinicalSlotAgent/DialogueAgent/InputNormalizerAgent/
        # SafetyClassifierAgent/DomainInferenceAgent. Mode B (_analyze_session)
        # never loads a prompt file (see module docstring / PROMPT_VERSION
        # comment) so it has no fallback-catch site to instrument.
        prompts_degraded = False
        try:
            system_prompt = self._prompt_loader.load_system_prompt(
                "sentiment_analyzer", PROMPT_VERSION
            )
        except FileNotFoundError:
            logger.warning("sentiment_analyzer prompt not found, using fallback")
            system_prompt = (
                "환자 발화의 감정을 분석하세요. JSON 출력: "
                "{turn_index, emotions: [{label, intensity}], polarity, arousal, "
                "evidence_phrase, risk_signal}"
            )
            prompts_degraded = True

        mode_instruction = (
            "\n\n[MODE: utterance]\n"
            f"[turn_index: {inp.turn_index}]\n"
            "위 utterance 모드로 단일 발화를 분석하세요."
        )

        messages = [
            ChatMessage(role="system", content=system_prompt + mode_instruction),
        ]
        for ctx in inp.conversation_context[-3:]:
            messages.append(ChatMessage(role=ctx.get("role", "user"), content=ctx["content"]))
        messages.append(ChatMessage(role="user", content=inp.utterance))

        selection = self._router.select_model(self.agent_name, require_json=True)
        adapter = self._router.get_adapter(selection.adapter_name)
        assert isinstance(adapter, LLMAdapter)

        resp_format = (
            {"type": "json_object"}
            if (selection.supports_json_schema or selection.supports_json_object)
            else None
        )

        try:
            resp = await adapter.chat_timed(
                messages,
                model=selection.model_id,
                temperature=0.2,
                max_tokens=512,
                response_format=resp_format,
            )
            self._router.record_success(selection.adapter_name)
            data = json.loads(resp.content)
        except Exception as exc:
            logger.warning("Sentiment utterance analysis failed: %s", exc)
            data = {}

        emotions = [
            EmotionScore(**emotion)
            for emotion in data.get(
                "emotions",
                [{"label": "neutral", "intensity": 0.5}],
            )
        ]
        latency_ms = (time.perf_counter() - start) * 1000

        return SentimentUtteranceOutput(
            model_used=getattr(resp, "model", "unknown") if "resp" in dir() else "fallback",
            prompt_version=PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary=f"Utterance sentiment: {emotions[0].label if emotions else 'unknown'}",
            turn_index=inp.turn_index,
            emotions=emotions,
            polarity=data.get("polarity", 0.0),
            arousal=data.get("arousal", "medium"),
            evidence_phrase=data.get("evidence_phrase", ""),
            risk_signal=data.get("risk_signal", False),
            prompts_degraded=prompts_degraded,
        )

    async def _analyze_session(self, inp: SentimentSessionInput) -> SentimentSessionOutput:
        """Mode B: Aggregate per-utterance results into session report."""
        start = time.perf_counter()

        if not inp.per_utterance_results:
            return SentimentSessionOutput(
                model_used="aggregation",
                prompt_version="v1",
                latency_ms=0.0,
                reason_summary="No utterance results to aggregate",
                signal_strength="none",
            )

        # Aggregate emotions
        emotion_counts: Counter[str] = Counter()
        total_polarity = 0.0
        trajectory: list[PolarityPoint] = []
        tags: list[PerUtteranceTag] = []
        max_negative_intensity = 0.0

        for r in inp.per_utterance_results:
            for e in r.emotions:
                emotion_counts[e.label] += 1
                if e.label in ("anxiety", "sadness", "anger", "despair", "fear"):
                    max_negative_intensity = max(max_negative_intensity, e.intensity)
            total_polarity += r.polarity
            trajectory.append(PolarityPoint(turn=r.turn_index, polarity=r.polarity))
            tags.append(PerUtteranceTag(
                turn=r.turn_index,
                emotions=[e.label for e in r.emotions],
                polarity=r.polarity,
            ))

        # Compute distribution
        total_emotion_mentions = sum(emotion_counts.values()) or 1
        distribution = {
            k: round(v / total_emotion_mentions, 2)
            for k, v in emotion_counts.most_common()
        }

        # Dominant emotions (top 2)
        dominant = [k for k, _ in emotion_counts.most_common(2)]

        # Signal strength
        negative_count = sum(
            emotion_counts.get(e, 0)
            for e in ("anxiety", "sadness", "anger", "despair", "fear")
        )
        if negative_count == 0:
            strength = "none"
        elif max_negative_intensity < 0.5:
            strength = "mild"
        elif max_negative_intensity < 0.7 or negative_count <= 3:
            strength = "moderate"
        else:
            strength = "strong"

        # Emotional shift detection
        shift_detected = False
        shift_desc = ""
        if len(trajectory) >= 3:
            midpoint = len(trajectory) // 2
            first_half = sum(p.polarity for p in trajectory[:midpoint]) / max(
                midpoint,
                1,
            )
            second_half = sum(p.polarity for p in trajectory[midpoint:]) / max(
                len(trajectory) - midpoint,
                1,
            )
            if abs(first_half - second_half) > 0.3:
                shift_detected = True
                direction = "악화" if second_half < first_half else "호전"
                shift_desc = (
                    f"대화 전반부 polarity {first_half:.1f} → "
                    f"후반부 {second_half:.1f} ({direction})"
                )

        # Repeated patterns
        repeated = [
            f"{label} 표현 {count}회 반복"
            for label, count in emotion_counts.most_common()
            if count >= 3
        ]

        latency_ms = (time.perf_counter() - start) * 1000

        return SentimentSessionOutput(
            model_used="aggregation",
            prompt_version="v1",
            latency_ms=latency_ms,
            reason_summary=f"Session sentiment: {dominant}, strength={strength}",
            dominant_emotions=dominant,
            emotion_distribution=distribution,
            polarity_trajectory=trajectory,
            signal_strength=strength,
            emotional_shift_detected=shift_detected,
            shift_description=shift_desc,
            repeated_patterns=repeated,
            per_utterance_tags=tags,
        )
