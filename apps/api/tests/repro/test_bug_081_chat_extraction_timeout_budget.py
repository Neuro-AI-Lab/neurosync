"""Regression test for BUG-081 (fixed this pass, EXP-032 live re-verification).

Pre-fix: `ai_chat_timeout_seconds` defaulted to 10.0s, but ai-server's
`OrchestratorAgent._execute_pipeline` runs its ENTIRE post-dialogue
pipeline (slot_extraction + handoff_generation + the evidence-verifier's
up-to-3-attempt regenerate loop — the SAME chain BUG-068 measured at 48.1s
worst case for the regenerate loop alone) synchronously, inside the SAME
`/ai/chat/respond` call, whenever a turn crosses the slot-coverage/risk-
grounded threshold (confirmed by source read: `_execute_pipeline` awaits
`_run_post_dialogue_pipeline` directly — no background-task split on the
ai-server side, unlike apps/api's own `services/chat.py::
_extract_slots_bg`). A live instance ran ~30s and was still running when
the prior 10.0s client budget gave up — the turn (including a genuine,
already-computed SI grounding) was silently dropped (`respond()` returns
`None`, caller emits no `ai:complete`/`risk:detected` frame at all).

Fix (this pass): raised `ai_chat_timeout_seconds` default to 90.0s,
mirroring `ai_handoff_timeout_seconds`'s own BUG-068 margin, since this is
structurally the same regenerate-loop chain plus one extra LLM call (slot
extraction)."""

from __future__ import annotations

import inspect

# The exact worst-case wall-clock observed live for ai-server's 3-attempt
# evidence-verifier regenerate loop alone (error.md BUG-068 reproduction,
# EXP-031 rerun 2026-07-23: 19:23:38.549 -> 19:24:26.656). BUG-081's own
# chain additionally prepends a slot-extraction LLM call before this loop
# even starts, so this is a conservative (not inflated) floor.
_OBSERVED_REGENERATE_LOOP_WORST_CASE_SECONDS = 48.1

# The BUG-081 live repro's own observed elapsed time before apps/api's
# prior 10.0s budget gave up (extraction chain was still running).
_OBSERVED_BUG_081_LIVE_ELAPSED_SECONDS = 30.0


def test_chat_timeout_exceeds_both_observed_worst_cases():
    from src.core.config import Settings

    settings = Settings()
    for observed in (
        _OBSERVED_REGENERATE_LOOP_WORST_CASE_SECONDS,
        _OBSERVED_BUG_081_LIVE_ELAPSED_SECONDS,
    ):
        assert settings.ai_chat_timeout_seconds > observed, (
            f"ai_chat_timeout_seconds={settings.ai_chat_timeout_seconds} does "
            f"not exceed an observed worst case ({observed}s) — BUG-081 "
            "regression: apps/api would give up on a turn ai-server is "
            "still genuinely computing, silently dropping it (including a "
            "safety-relevant grounding, per the live repro)."
        )
    # Sane upper bound — an interactive chat turn's budget should not be
    # allowed to silently balloon past the handoff-generate budget it now
    # mirrors.
    assert settings.ai_chat_timeout_seconds <= 120.0


def test_chat_respond_uses_the_configured_timeout():
    """`AIClient.chat_respond` must pass `ai_chat_timeout_seconds` through
    unchanged to the underlying POST — guards against the call site being
    refactored to hardcode a different budget."""
    from src.services.ai_client import AIClient

    source = inspect.getsource(AIClient.chat_respond)
    assert "self._settings.ai_chat_timeout_seconds" in source, (
        "AIClient.chat_respond no longer reads its timeout from "
        "settings.ai_chat_timeout_seconds — BUG-081 regression risk."
    )
