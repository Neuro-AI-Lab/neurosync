"""Temporal Summary agent — rule-based longitudinal state comparison."""
from __future__ import annotations

import time
from typing import Any

from src.agents.base import AgentInput, BaseAgent
from src.schemas.temporal import (
    DomainDirection,
    DomainTrend,
    PlotPoint,
    SentimentTrend,
    TemporalSummaryInput,
    TemporalSummaryOutput,
)

SCALE_THRESHOLD = 5  # PHQ-9/GAD-7: delta >= 5 = clinically significant


class TemporalSummaryAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "temporal_summary"

    async def run(self, inp: AgentInput, **kwargs: Any) -> TemporalSummaryOutput:
        start = time.perf_counter()
        if not isinstance(inp, TemporalSummaryInput):
            raise TypeError(f"Expected TemporalSummaryInput, got {type(inp).__name__}")

        # First visit: all unknown
        if inp.is_first_visit:
            latency = (time.perf_counter() - start) * 1000
            return TemporalSummaryOutput(
                model_used="rule-engine",
                prompt_version="v1",
                latency_ms=latency,
                reason_summary="초진 환자 — 비교 기준 없음",
                overall_direction=DomainDirection.unknown,
                is_first_visit=True,
            )

        trends = []
        # PHQ-9
        trends.append(
            self._compare_scale(
                "PHQ-9",
                inp.current_scales.get("PHQ-9"),
                inp.prior_scales.get("PHQ-9"),
            )
        )
        # GAD-7
        trends.append(
            self._compare_scale(
                "GAD-7",
                inp.current_scales.get("GAD-7"),
                inp.prior_scales.get("GAD-7"),
            )
        )
        # CTRS (inverted: lower = worse)
        trends.append(self._compare_ctrs(inp.current_ctrs, inp.prior_ctrs))

        # Sentiment
        sentiment = self._compare_sentiment(
            inp.current_sentiment_polarity,
            inp.prior_sentiment_polarity,
        )

        # Overall direction: worsened takes priority, then majority vote
        directions = [t.direction for t in trends if t.direction != DomainDirection.unknown]
        if not directions:
            overall = DomainDirection.unknown
        elif any(d == DomainDirection.worsened for d in directions):
            overall = DomainDirection.worsened
        else:
            improved_count = sum(1 for d in directions if d == DomainDirection.improved)
            if improved_count > len(directions) / 2:
                overall = DomainDirection.improved
            elif improved_count == 0:
                overall = DomainDirection.unchanged
            else:
                overall = DomainDirection.unchanged

        # Plot data
        plot = []
        if inp.prior_date:
            plot.append(PlotPoint(
                date=inp.prior_date,
                phq9=inp.prior_scales.get("PHQ-9"),
                gad7=inp.prior_scales.get("GAD-7"),
                ctrs_level=inp.prior_ctrs,
                sentiment_polarity=inp.prior_sentiment_polarity,
            ))
        if inp.current_date:
            plot.append(PlotPoint(
                date=inp.current_date,
                phq9=inp.current_scales.get("PHQ-9"),
                gad7=inp.current_scales.get("GAD-7"),
                ctrs_level=inp.current_ctrs,
                sentiment_polarity=inp.current_sentiment_polarity,
            ))

        latency = (time.perf_counter() - start) * 1000
        return TemporalSummaryOutput(
            model_used="rule-engine",
            prompt_version="v1",
            latency_ms=latency,
            reason_summary=f"종단 비교: {overall.value}",
            overall_direction=overall,
            domain_trends=trends,
            sentiment_trend=sentiment,
            plot_data=plot,
            is_first_visit=False,
        )

    @staticmethod
    def _compare_scale(name: str, current: int | None, prior: int | None) -> DomainTrend:
        if current is None or prior is None:
            return DomainTrend(
                domain=name,
                direction=DomainDirection.unknown,
                evidence=[f"{name} 이전/현재 데이터 없음"],
            )
        delta = current - prior
        if delta <= -SCALE_THRESHOLD:
            direction = DomainDirection.improved
        elif delta >= SCALE_THRESHOLD:
            direction = DomainDirection.worsened
        else:
            direction = DomainDirection.unchanged
        return DomainTrend(
            domain=name,
            direction=direction,
            previous_value=prior,
            current_value=current,
            delta=delta,
            confidence=0.95,
            evidence=[f"{name} {prior} → {current} (delta {delta:+d})"],
        )

    @staticmethod
    def _compare_ctrs(current: int | None, prior: int | None) -> DomainTrend:
        if current is None or prior is None:
            return DomainTrend(
                domain="CTRS",
                direction=DomainDirection.unknown,
                evidence=["CTRS 이전/현재 데이터 없음"],
            )
        # CTRS: lower number = MORE dangerous. 5→4 = worsened, 3→4 = improved
        if current < prior:  # number decreased = risk increased = worsened
            direction = DomainDirection.worsened
        elif current > prior:  # number increased = risk decreased = improved
            direction = DomainDirection.improved
        else:
            direction = DomainDirection.unchanged
        direction_note = (
            "위험도 상승"
            if direction == DomainDirection.worsened
            else "위험도 감소"
            if direction == DomainDirection.improved
            else "변동 없음"
        )
        return DomainTrend(
            domain="CTRS",
            direction=direction,
            previous_value=prior,
            current_value=current,
            delta=current - prior,
            confidence=0.90,
            evidence=[f"CTRS {prior} → {current} ({direction_note})"],
        )

    @staticmethod
    def _compare_sentiment(current: float | None, prior: float | None) -> SentimentTrend:
        if current is None or prior is None:
            return SentimentTrend(direction=DomainDirection.unknown, note="Sentiment 데이터 없음")
        delta = round(current - prior, 10)
        if delta > 0.3:
            direction = DomainDirection.improved
        elif delta < -0.3:
            direction = DomainDirection.worsened
        else:
            direction = DomainDirection.unchanged
        return SentimentTrend(
            current_polarity=current,
            previous_polarity=prior,
            direction=direction,
            note=f"Polarity {prior:.2f} → {current:.2f} (delta {delta:+.2f})",
        )
