"""Regression test for BUG-068 (fixed this pass, EXP-031 live re-verification).

Pre-fix: `ai_handoff_timeout_seconds` defaulted to 45.0s, but ai-server's
evidence-verifier worst case (3 regenerate attempts,
`routes/handoff.py::_MAX_REGENERATE_ATTEMPTS = 2`) was observed live at
48.1s total (attempt latencies 19:23:38.549 -> 19:24:26.656). ai-server
itself did NOT fail — it returned a 200 (degraded, `requires_human_review`)
result — but apps/api's httpx client had already given up, so
`generate_report_task` marked the report `status="failed",
failureReason="ai_server_unavailable"` for a session ai-server was about to
successfully (if degraded) complete.

`generate_report_task` is an async background task polled via
`GET /report/status` — no interactive request is blocked on this client
call — so there is no UX cost to a generous timeout margin.

Fix (this pass): raised `ai_handoff_timeout_seconds` default to 90.0s, comfortably
above the observed 48.1s worst case."""

from __future__ import annotations

# The exact worst-case wall-clock observed live for ai-server's 3-attempt
# evidence-verifier regenerate loop (error.md BUG-068 reproduction, EXP-031
# rerun 2026-07-23: 19:23:38.549 -> 19:24:26.656).
_OBSERVED_WORST_CASE_SECONDS = 48.1


def test_handoff_timeout_exceeds_observed_verifier_worst_case():
    from src.core.config import Settings

    settings = Settings()
    assert settings.ai_handoff_timeout_seconds > _OBSERVED_WORST_CASE_SECONDS, (
        f"ai_handoff_timeout_seconds={settings.ai_handoff_timeout_seconds} does "
        f"not exceed the observed worst-case verifier loop "
        f"({_OBSERVED_WORST_CASE_SECONDS}s) — BUG-068 regression: apps/api "
        "would give up right as ai-server was about to return a result."
    )
    # Guard against an over-correction that silently masks a truly hung
    # ai-server for an unreasonable duration — keep a sane upper bound too.
    assert settings.ai_handoff_timeout_seconds <= 300.0


def test_handoff_generate_uses_the_configured_timeout(monkeypatch):
    """`AIClient.handoff_generate` must pass `ai_handoff_timeout_seconds`
    through unchanged to the underlying POST — the fix is a config value,
    not a code path; this guards against the call site being refactored to
    hardcode a different budget."""
    import inspect

    from src.services.ai_client import AIClient

    source = inspect.getsource(AIClient.handoff_generate)
    assert "self._settings.ai_handoff_timeout_seconds" in source, (
        "AIClient.handoff_generate no longer reads its timeout from "
        "settings.ai_handoff_timeout_seconds — BUG-068 regression risk (a "
        "hardcoded value would silently stop tracking config changes)"
    )
