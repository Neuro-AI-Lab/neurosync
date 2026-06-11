"""Safety Guard v1 — keyword-first, LLM-second.

Demo scope:
- KEYWORDS dict (Korean self-harm/suicide/distress). Longest-match wins.
- LLM stub: when no keyword matches, return LOW with confidence 0. Real LLM
  classifier lands in the next AI slice (Anthropic/Solar/A.X selection).

PRD §4.1 SLA: p95 < 1000 ms. Keyword path is microseconds; LLM stub is
synthetic 5ms.
"""

from __future__ import annotations

import time

from contracts.safety import RiskCategory, RiskLevel, SafetyEvidence, SafetyResponse

from src.safety.keywords import KEYWORDS


def _keyword_match(text: str) -> tuple[str, RiskLevel, RiskCategory, float] | None:
    """Return the longest-matching keyword entry, if any."""
    lower = text.lower()
    matches = [k for k in KEYWORDS if k[0] in lower]
    if not matches:
        return None
    return max(matches, key=lambda k: len(k[0]))


def classify(message: str, prev_context: list[str] | None = None) -> SafetyResponse:
    started = time.perf_counter()
    prev_context = prev_context or []

    match = _keyword_match(message)
    if match is not None:
        phrase, level, category, confidence = match
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SafetyResponse(
            level=level,
            category=category,
            evidence=SafetyEvidence(
                matched_keywords=[phrase],
                classifier="keyword-v1",
                confidence=confidence,
            ),
            latency_ms=elapsed_ms,
        )

    # LLM stub — next AI slice replaces with real classifier.
    # Tiny synthetic delay to keep the latency_ms field meaningful.
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    return SafetyResponse(
        level=RiskLevel.LOW,
        category=RiskCategory.NONE,
        evidence=SafetyEvidence(
            matched_keywords=[],
            classifier="llm-stub-v0",
            confidence=0.0,
        ),
        latency_ms=elapsed_ms,
    )
