"""Regression test for BUG-087 (fixed this pass).

Pre-fix: `apps/api/src/main.py` never called `logging.basicConfig`/`dictConfig`
anywhere. Every application-level `logger.warning`/`.info` call under `src/`
(e.g. `services/chat.py`'s `chat.respond.unavailable` on `AIClientError`)
propagated to a root logger with zero handlers and was silently dropped —
0 WARNING/ERROR lines appeared in `apps_api_stdout.log` across a live session
that included a confirmed real failure (BUG-086).

This is deliberately NOT a `caplog`-based test: `caplog` attaches its own
handler directly to the root logger, which would pass even with the bug
present (BUG-087's own recommended repro explicitly calls this out — caplog's
handler injection does not exercise the actual, unconfigured process). Instead
this spawns a real subprocess that imports `src.main` exactly the way
`uvicorn src.main:app` does, then emits a probe log line and asserts it is
visible on the process's real stdout — the same channel `apps_api_stdout.log`
captures in the deployed stack.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2]


def test_app_import_configures_root_logger_and_emits_to_stdout() -> None:
    """Importing `src.main` must leave the root logger able to emit to stdout."""
    probe = (
        "import logging\n"
        "import src.main  # noqa: F401 — triggers the BUG-087 fix at import time\n"
        "logging.getLogger('src.some.module').warning('bug087-probe-line')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(_API_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "bug087-probe-line" in result.stdout, (
        f"expected probe line on stdout, got stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "WARNING" in result.stdout


def test_log_level_env_var_controls_verbosity() -> None:
    """LOG_LEVEL=ERROR must suppress INFO-level app logs (env-controlled level)."""
    probe = (
        "import logging\n"
        "import src.main  # noqa: F401\n"
        "logging.getLogger('src.some.module').info('bug087-info-should-be-suppressed')\n"
        "logging.getLogger('src.some.module').error('bug087-error-should-appear')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(_API_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LOG_LEVEL": "ERROR"},
    )
    assert result.returncode == 0, result.stderr
    assert "bug087-info-should-be-suppressed" not in result.stdout
    assert "bug087-error-should-appear" in result.stdout
