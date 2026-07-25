"""Regression test for BUG-065 (fixed this pass, EXP-031 fix_wave_design.md).

Pre-fix: `alembic/versions/0001_initial_auth_schema.py`'s `patient_profiles.
is_minor` column used `sa.Computed("(EXTRACT(YEAR FROM CURRENT_DATE)::int -
birth_year) < 14", persisted=True)` — PG16 rejects `CURRENT_DATE` (volatile)
inside a `GENERATED ALWAYS AS ... STORED` expression, so a genuinely fresh
`alembic upgrade head` could never complete past `0001`.

Fix (this pass): `is_minor` is now a plain `Boolean NOT NULL` column with no
DB-side computation (`0001`'s source edited in place — see its docstring);
the application sets the value explicitly at INSERT time
(`api/v1/auth.py::register`, via `_is_minor()`).

This test is the exact repro BUG-065 describes: spin up a THROWAWAY
`pgserver` Postgres (no DGX/demo DB touched), run the full `alembic upgrade
head` chain via subprocess (the real CLI entrypoint, not
`Base.metadata.create_all` — that would not have caught this bug, since the
test harness's own `create_all`-based fixture patches around exactly this
column), and assert it completes without raising. Completion criterion per
PLAN-2026-W30-FIXWAVE: "fresh throwaway PG에서 0001→head 전체 체인 무패치 통과."
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pgserver = pytest.importorskip(
    "pgserver",
    reason="test-only throwaway-Postgres helper not installed; skipping gracefully.",
)

# All live keys forced empty before any src.* import touches Settings()
# (BUG-052: unset alone does not gate live-only paths; only "" does).
for _key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "UPSTAGE_API_KEY",
    "HIRA_API_KEY",
    "KAKAO_API_KEY",
    "NS_RAG_API_KEY",
):
    os.environ.setdefault(_key, "")
    os.environ[_key] = ""

_APPS_API_ROOT = Path(__file__).resolve().parents[2]


def test_fresh_pgserver_alembic_upgrade_head_no_hand_patch():
    """BUG-065 completion criterion: fresh throwaway PG, `alembic upgrade
    head` from an EMPTY database, zero hand-patching, must not raise."""
    pgdata = tempfile.mkdtemp(prefix="bug065_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    try:
        srv.psql("CREATE DATABASE neurosync_bug065;")
        database_url = (
            srv.get_uri()
            .replace("postgresql://", "postgresql+asyncpg://")
            .replace("/postgres?", "/neurosync_bug065?")
        )

        env = dict(os.environ)
        env["DATABASE_URL"] = database_url

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(_APPS_API_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, (
            "`alembic upgrade head` failed against a fresh throwaway PG — "
            f"BUG-065 regression.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "InvalidObjectDefinitionError" not in result.stderr
        assert "generation expression is not immutable" not in result.stderr
    finally:
        srv.cleanup()


def test_is_minor_is_no_longer_a_generated_column():
    """Confirms the actual fix, not just the migration's success — the
    `patient_profiles.is_minor` column must be a plain column with no
    Postgres GENERATED expression, matching `models/patient_profile.py`."""
    from src.models.patient_profile import PatientProfile

    col = PatientProfile.__table__.c.is_minor
    assert col.computed is None, (
        "is_minor must not be a GENERATED/Computed column post-BUG-065-fix "
        f"(found: {col.computed!r})"
    )
    assert col.nullable is False
