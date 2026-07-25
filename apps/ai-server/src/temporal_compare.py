"""Pure, zero-LLM temporal comparators — deterministic scale/CTRS/sentiment deltas.

Moved from `src/agents/temporal_summary.py`; the `TemporalSummaryAgent` shell
(and its standalone `/summarize` route) has been retired — its role merged
into F4 (`src/f4.py`), which is the sole live consumer of these comparators
(per-pair supplementary evidence, never the trend basis; see F4's own
module docstring, Criterion 0). Function names/bodies kept identical to the
retired agent's static methods to minimize churn in callers/tests.
"""
from __future__ import annotations

from src.schemas.temporal import DomainDirection, DomainTrend, SentimentTrend

SCALE_THRESHOLD = 5  # PHQ-9/GAD-7: delta >= 5 = clinically significant


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
