"""Regression test for BUG-063 (fixed this pass, EXP-031 fix_wave_design.md).

Pre-fix: `src/models/session.py`'s `RiskEvent.status` was `String(16)` with a
CHECK excluding `'pending_reclassify'` (17 chars > 16) — the exact value
`services/safety.py::handle_unavailable_classifier` unconditionally writes
on every classifier-unavailable turn. The live demo DB only avoided
crashing because it was hand-patched (outside any migration) to
`varchar(32)` + an updated CHECK.

Fix (this pass): model source is `String(32)` + migration `0012` widens the
column and CHECK to match (additive, no data risk). This test checks BOTH
the model source (offline, no DB) and a live migrated fresh DB's actual
constraint text (so a source/DB divergence, BUG-063's exact defect, cannot
recur silently).
"""

from __future__ import annotations

import os
import tempfile

import pytest

pgserver = pytest.importorskip(
    "pgserver",
    reason="test-only throwaway-Postgres helper not installed; skipping gracefully.",
)

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


def test_model_source_status_length_and_check():
    """Offline (no DB): model source itself must declare a length that fits
    'pending_reclassify' (17 chars) and the CHECK clause must include it —
    BUG-063's defect was specifically source/DB divergence, so the source
    itself (not just a live DB) must be correct."""
    from src.models.session import RiskEvent

    status_col = RiskEvent.__table__.c.status
    assert status_col.type.length >= 32, (
        f"RiskEvent.status length={status_col.type.length} — too short for "
        "'pending_reclassify' (17 chars); BUG-063 regression"
    )

    check_clauses = [
        str(c.sqltext) for c in RiskEvent.__table__.constraints if hasattr(c, "sqltext")
    ]
    assert any("pending_reclassify" in c for c in check_clauses), (
        f"no CHECK constraint on RiskEvent.status includes 'pending_reclassify': "
        f"{check_clauses!r}"
    )


def test_fresh_migrated_db_status_column_and_check_match_model():
    """Live (throwaway pgserver, `alembic upgrade head`): the ACTUAL DB
    column length + CHECK clause after migration 0012 must match what
    `handle_unavailable_classifier` needs — closes the exact BUG-063 gap
    (model/migration source vs. what was only ever true on a hand-patched
    DB)."""
    import subprocess
    import sys
    from pathlib import Path

    apps_api_root = Path(__file__).resolve().parents[2]
    pgdata = tempfile.mkdtemp(prefix="bug063_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    try:
        srv.psql("CREATE DATABASE neurosync_bug063;")
        database_url = (
            srv.get_uri()
            .replace("postgresql://", "postgresql+asyncpg://")
            .replace("/postgres?", "/neurosync_bug063?")
        )
        env = dict(os.environ)
        env["DATABASE_URL"] = database_url
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(apps_api_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"migration chain failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        sync_url = (
            srv.get_uri().replace("/postgres?", "/neurosync_bug063?")
        )
        import psycopg

        with psycopg.connect(sync_url.replace("postgresql://", "postgresql://")) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_name='risk_events' AND column_name='status'"
                )
                (length,) = cur.fetchone()
                assert length == 32, f"expected varchar(32), found varchar({length})"

                cur.execute(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid='risk_events'::regclass AND conname='ck_risk_events_status'"
                )
                (constraint_def,) = cur.fetchone()
                assert "pending_reclassify" in constraint_def, (
                    f"CHECK missing 'pending_reclassify': {constraint_def!r}"
                )
    finally:
        srv.cleanup()
