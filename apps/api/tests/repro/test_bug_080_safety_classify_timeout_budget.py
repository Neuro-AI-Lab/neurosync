"""Regression test for BUG-080 (fixed this pass, EXP-032 live re-verification).

Pre-fix: `AIClient.safety_classify` was the only LLM-backed `AIClient`
method with no dedicated `timeout=` kwarg at its `_post` call site — it
silently fell back to the bare `httpx.AsyncClient(timeout=2.0)` constructor
default. ai-server's `/ai/safety/classify` unconditionally makes a real
Upstage LLM call (`_llm_classify`, unless the rule level is already
`>= high`) whose live latency was observed at 952-4373ms across 2 sessions/
9 turns (`error.md` BUG-080 reproduction table). Every latency `>2000ms`
tripped the client-side timeout — 4/6 turns (67%) in one session, 2/3 in
another — and fell open into `classifier_unavailable`, full-blocking
ordinary, non-crisis chat turns.

Fix (this pass): added a dedicated `ai_safety_timeout_seconds` setting
(default 6.0s, mirroring the pattern every other `AIClient` method already
uses) and threaded it through `safety_classify`'s `_post` call.
"""

from __future__ import annotations

import asyncio
import inspect

import httpx
import pytest

# The exact worst-case latency observed live for a real Upstage
# `/ai/safety/classify` call (error.md BUG-080 reproduction, EXP-032
# 2026-07-25: session `fb5380bb...` turn latencies 1807/1481/3265/952/3008/
# 2456ms).
_OBSERVED_WORST_CASE_SECONDS = 4.373


def test_safety_timeout_exceeds_observed_worst_case():
    from src.core.config import Settings

    settings = Settings()
    assert settings.ai_safety_timeout_seconds > _OBSERVED_WORST_CASE_SECONDS, (
        f"ai_safety_timeout_seconds={settings.ai_safety_timeout_seconds} does "
        f"not exceed the observed worst-case classify latency "
        f"({_OBSERVED_WORST_CASE_SECONDS}s) — BUG-080 regression: an "
        "ordinary, benign turn would trip the client-side timeout and "
        "fail-open into classifier_unavailable full-block."
    )
    # Sane upper bound — a safety-gate call sitting in the interactive
    # pre-gate path should not be allowed to silently balloon.
    assert settings.ai_safety_timeout_seconds <= 30.0


def test_safety_classify_no_longer_uses_the_bare_2s_client_default():
    """The constructor-level `httpx.AsyncClient(timeout=2.0)` default
    still exists (other legacy call sites may rely on it), but
    `safety_classify`'s OWN call site must pass an explicit `timeout=`
    kwarg through `_post` — source-level guard against the call site being
    refactored back to the implicit default."""
    from src.services.ai_client import AIClient

    source = inspect.getsource(AIClient.safety_classify)
    assert "timeout=self._settings.ai_safety_timeout_seconds" in source, (
        "AIClient.safety_classify no longer passes an explicit timeout — "
        "BUG-080 regression risk (falls back to the bare 2.0s httpx "
        "constructor default)."
    )


class _SlowTransport(httpx.AsyncBaseTransport):
    """Mock transport that sleeps past a *narrow* timeout before replying
    — proves `safety_classify` fails fast under a tight budget (pre-fix
    behavior) and succeeds once the budget is widened (post-fix behavior),
    without depending on ai-server or real Upstage latency.

    A bare custom `AsyncBaseTransport` does not enforce httpx's per-request
    `timeout=` kwarg on its own (only the real `HTTPTransport`/httpcore
    stack does) — this transport reads the read-timeout httpx already
    stashed on `request.extensions["timeout"]` and races its own delay
    against it via `asyncio.wait_for`, so the mock genuinely reproduces a
    client-side timeout rather than always succeeding regardless of the
    configured budget."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        timeout_cfg = request.extensions.get("timeout") or {}
        read_timeout = timeout_cfg.get("read")
        if read_timeout is not None:
            try:
                await asyncio.wait_for(asyncio.sleep(self._delay), timeout=read_timeout)
            except TimeoutError as exc:
                raise httpx.ReadTimeout("mock read timeout", request=request) from exc
        else:
            await asyncio.sleep(self._delay)
        return httpx.Response(
            200,
            json={
                "risk_level": "low",
                "categories": [],
                "flagged_phrases": [],
                "confidence": 0.9,
                "ctrs_level": 5,
                "requires_human_review": False,
                "crisis_protocol_activated": False,
                "model_used": "stub",
                "prompt_version": "v1",
                "latency_ms": self._delay * 1000,
                "reason_summary": "stub",
            },
        )


def _make_safety_request():
    from contracts.safety import SafetyRequest

    return SafetyRequest(
        session_id="test-session-bug080",
        user_message="오늘 기분이 좀 나아요.",
        conversation_history=[],
    )


def test_safety_classify_fails_fast_under_a_tight_client_timeout():
    """Mirrors the pre-fix shape: a slow-but-successful ai-server response
    (3s, inside the 952-4373ms observed live range) against a 2.0s budget
    must raise AIClientError — reproduces the fail-open trigger."""
    from src.core.config import Settings
    from src.services.ai_client import AIClient, AIClientError

    client = httpx.AsyncClient(transport=_SlowTransport(3.0))
    settings = Settings(ai_safety_timeout_seconds=2.0)
    ai_client = AIClient(client=client, settings=settings)

    with pytest.raises(AIClientError):
        asyncio.run(ai_client.safety_classify(_make_safety_request()))


def test_safety_classify_succeeds_within_the_widened_default_budget():
    """Same 3s-slow mock response against the fixed 6.0s default budget —
    must succeed (BUG-080's whole point: the budget now exceeds real
    observed latency)."""
    from src.core.config import Settings
    from src.services.ai_client import AIClient

    client = httpx.AsyncClient(transport=_SlowTransport(3.0))
    settings = Settings()
    assert settings.ai_safety_timeout_seconds == 6.0
    ai_client = AIClient(client=client, settings=settings)

    result = asyncio.run(ai_client.safety_classify(_make_safety_request()))
    assert result.risk_level == "low"
