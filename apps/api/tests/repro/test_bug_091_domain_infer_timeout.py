"""Regression test for BUG-091 (fixed this pass).

Pre-fix: `ai_domain_timeout_seconds` defaulted to 4.5s, but `/ai/domain/infer`
(a solar-pro3 LLM call over `mode=rag`, 20 retrieved chunks, generating
multiple candidate lists) was observed live at 20.2s-30.6s wall-clock across
2/2 real DGX patient sessions (error.md BUG-091 reproduction, 2026-07-26:
session `574ad8ca` 30594ms, session `a16fb8c4` 20229ms — the latter's actual
(discarded) answer was the clinically correct `domain=depression`). apps/api
gave up on both calls well before ai-server produced an answer and shipped
the fallback PHQ4 instrument to both patients instead of the correctly
inferred instrument.

Fix (this pass): raised `ai_domain_timeout_seconds` default to 60.0s — ~2x
the observed 30.6s worst case, matching the margin-over-observed-p95
discipline already applied to `ai_chat_timeout_seconds` (BUG-081, 10s->90s)
and `ai_handoff_timeout_seconds` (BUG-068, 45s->90s). Mobile's
`INFER_TIMEOUT_MS` (apps/mobile/lib/domain.ts) was raised in lockstep to
75s (> server budget) so the server-side fallback/success verdict always
lands before the client's own fallback clock would fire.
"""

from __future__ import annotations

# The observed worst-case wall-clock for `/ai/domain/infer` across both live
# BUG-091 reproduction sessions (error.md, 2026-07-26).
_OBSERVED_WORST_CASE_SECONDS = 30.6


def test_domain_timeout_exceeds_observed_worst_case():
    from src.core.config import Settings

    settings = Settings()
    assert settings.ai_domain_timeout_seconds > _OBSERVED_WORST_CASE_SECONDS, (
        f"ai_domain_timeout_seconds={settings.ai_domain_timeout_seconds} does not "
        f"exceed the observed worst-case /ai/domain/infer latency "
        f"({_OBSERVED_WORST_CASE_SECONDS}s) — BUG-091 regression: apps/api would "
        "give up on domain routing before ai-server can answer, and every real "
        "session would fall back to PHQ4 regardless of the true clinical domain."
    )
    # Guard against an over-correction that silently masks a truly hung
    # ai-server for an unreasonable duration — keep a sane upper bound too.
    assert settings.ai_domain_timeout_seconds <= 300.0


def test_domain_infer_uses_the_configured_timeout(monkeypatch):
    """`AIClient.domain_infer` must pass `ai_domain_timeout_seconds` through
    unchanged to the underlying POST — the fix is a config value, not a code
    path; this guards against the call site being refactored to hardcode a
    different budget."""
    import inspect

    from src.services.ai_client import AIClient

    source = inspect.getsource(AIClient.domain_infer)
    assert "self._settings.ai_domain_timeout_seconds" in source, (
        "AIClient.domain_infer no longer reads its timeout from "
        "settings.ai_domain_timeout_seconds — BUG-091 regression risk (a "
        "hardcoded value would silently stop tracking config changes)"
    )
