"""Shared pytest fixtures — offline-suite env isolation (BUG-052).

Root cause (qa, BUG-052): `Settings` is a `pydantic-settings` `BaseSettings`
with `env_file=".env"`. Per pydantic-settings' own precedence rule, an env
var that is merely ABSENT from `os.environ` (the natural reading of "clear
the relevant API-key env", e.g. `unset UPSTAGE_API_KEY`) falls through to
the `.env` file's value — only a var that is PRESENT but EMPTY (`VAR=""`)
overrides it. `apps/ai-server/.env` carries a real, working key, so an
`unset`-style clear silently fails to gate the live-only tests
(`tests/test_deploy_contracts.py`'s `_upstage_key_available()`-gated
classes) and they execute real network calls — undetected, inside what
every prior "offline suite" gate report presented as a live-free run.

Fix: force each live-API env var to an explicit empty string UNLESS the
operator has ALREADY explicitly set it to a real value in `os.environ`
(not merely present in `.env`) — i.e. this never overrides an operator's
deliberate opt-in to a live run (`UPSTAGE_API_KEY=<real key> pytest ...`
still works exactly as before), it only closes the silent `.env` fallback
that fires when the var is simply unset/absent.

This MUST take effect before pytest collects `tests/test_deploy_contracts.
py` — that module's `@pytest.mark.skipif(not _upstage_key_available(), ...)`
decorators call `Settings()` at CLASS-BODY EXECUTION time, i.e. at
collection, not at test-run time. A conftest-level session-scoped autouse
fixture alone would run too late (after collection already evaluated the
skip condition against the un-forced env). `conftest.py` is imported by
pytest before it imports any test module in the same directory, so the
module-level call below is what actually closes the gap; the autouse
fixture re-asserts the same invariant for the duration of the test run as
a defensive second layer (e.g. against any test/fixture that mutates
`os.environ` mid-session) and is what a future test-infra reviewer expects
to find per this BUG's recommended fix shape.
"""

from __future__ import annotations

import os

import pytest

# The 4 live-API-key env vars this offline suite must never silently
# resolve via `.env` fallback (BUG-052's exact reproduction list).
_LIVE_API_KEY_VARS: tuple[str, ...] = (
    "UPSTAGE_API_KEY",
    "HIRA_API_KEY",
    "KAKAO_API_KEY",
    "NS_RAG_API_KEY",
)


def _force_empty_unless_explicitly_set() -> None:
    """For each live-API var, set it to "" only if it is not ALREADY
    present in `os.environ` — an operator who explicitly exported a real
    key to opt into a live run is never overridden; a var that is simply
    absent (the `unset`-style clear BUG-052 reproduced) is forced empty so
    `pydantic-settings` cannot fall through to `.env`."""
    for var in _LIVE_API_KEY_VARS:
        if var not in os.environ:
            os.environ[var] = ""


# Runs at conftest IMPORT time — before pytest collects any test module in
# this directory, and therefore before `test_deploy_contracts.py`'s
# module-level `@pytest.mark.skipif(not _upstage_key_available(), ...)`
# decorators evaluate `Settings()`. This is the line that actually closes
# BUG-052 (a fixture alone would run too late — see module docstring).
_force_empty_unless_explicitly_set()


@pytest.fixture(autouse=True, scope="session")
def _bug052_offline_env_isolation() -> None:
    """Session-scoped defensive re-assertion of the same invariant the
    module-level call above establishes at import time. Does not undo the
    module-level call's effect (same "never override an explicit opt-in"
    rule) — guards against any code path that mutates `os.environ` after
    collection but before/between test runs."""
    _force_empty_unless_explicitly_set()
