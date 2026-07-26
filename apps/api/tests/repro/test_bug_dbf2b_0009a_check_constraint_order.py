"""Regression test for DB-F2b (fixed this pass — 0009a's own upgrade()
docstring, `apps/api/alembic/versions/0009a_questionnaire_type_hyphen_backfill.py`).

Pre-fix: 0009a's upgrade() ran `UPDATE questionnaire_results SET
type='PHQ9'/'GAD7'/'AUDITC'/'PHQ4' WHERE type='PHQ-9'/...` while 0008's
CHECK constraint (`ck_questionnaire_results_type`, hyphenated values only —
`type IN ('PHQ-9','GAD-7','PHQ-4','WHO-5','AUDIT-C')`) was still the *live*
constraint on the table (0010, which narrows the CHECK to the
non-hyphenated set, runs strictly after 0009a). So the UPDATE violated the
still-active old CHECK directly (`CheckViolationError`), independent of
0010's own `ADD CONSTRAINT` step — confirmed live against the DGX DB
(stamped at revision 0009, carrying real hyphenated rows: PHQ-9(7)/
GAD-7(5)/AUDIT-C(1); transaction rolled back, 0009 left intact).

This test reproduces that exact DGX-shaped state on a THROWAWAY pgserver
Postgres (no DGX/demo DB touched): run `alembic upgrade 0009` via the real
CLI, seed hyphenated rows directly with 0008's CHECK still live, then run
`alembic upgrade head` and assert it completes without raising, with no
data loss (rows land as PHQ9/GAD7/AUDITC/PHQ4) and the final CHECK is the
narrow non-hyphenated one from 0010.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
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

# Exact hyphenated scale set DB-F2b's docstring cites from the DGX probe,
# plus PHQ-4 (also in 0009a's backfill map, no live DGX row observed but
# covered here for completeness).
_HYPHEN_TO_PLAIN = {
    "PHQ-9": "PHQ9",
    "GAD-7": "GAD7",
    "AUDIT-C": "AUDITC",
    "PHQ-4": "PHQ4",
}


def _run_alembic(revision: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=str(_APPS_API_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_dgx_shaped_pre_0009a_hyphenated_rows_survive_upgrade_head():
    """DB-F2b completion criterion: a DB stamped at 0009 with real
    hyphenated questionnaire_results rows (0008's CHECK still live) must
    reach `head` cleanly via `upgrade head`, converting rows to the plain
    (non-hyphenated) form with zero data loss."""
    pgdata = tempfile.mkdtemp(prefix="bug_dbf2b_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    try:
        dbname = "neurosync_bug_dbf2b"
        srv.psql(f"CREATE DATABASE {dbname};")
        base_uri = srv.get_uri()
        database_url = base_uri.replace("postgresql://", "postgresql+asyncpg://").replace(
            "/postgres?", f"/{dbname}?"
        )

        # 1) Advance to 0009 — the DGX-confirmed pre-0009a stamp.
        result_0009 = _run_alembic("0009", database_url)
        assert result_0009.returncode == 0, (
            "setup step `alembic upgrade 0009` failed.\n"
            f"stdout:\n{result_0009.stdout}\nstderr:\n{result_0009.stderr}"
        )

        # 2) Seed the exact DGX-shaped state: a user, one session per
        #    hyphenated type (uq_questionnaire_results_session_type is
        #    (session_id, type)), and one questionnaire_results row per
        #    hyphenated scale — while 0008's hyphenated-only CHECK is the
        #    live constraint (0010 hasn't run yet).
        user_id = uuid.uuid4()
        seed_sql_parts = [
            f"""
            INSERT INTO users (id, email, password_hash, role, created_at)
            VALUES ('{user_id}', 'dbf2b-repro@example.com', 'x', 'patient', now());
            """
        ]
        for hyphenated in _HYPHEN_TO_PLAIN:
            session_id = uuid.uuid4()
            row_id = uuid.uuid4()
            seed_sql_parts.append(
                f"""
                INSERT INTO sessions (id, patient_id, status, created_at)
                VALUES ('{session_id}', '{user_id}', 'in_progress', now());
                INSERT INTO questionnaire_results
                    (id, session_id, type, answers, total_score, severity, completed_at)
                VALUES
                    ('{row_id}', '{session_id}', '{hyphenated}', '{{}}'::jsonb, 5, 'mild', now());
                """
            )
        seed_sql = "\\c {}\n{}".format(dbname, "\n".join(seed_sql_parts))
        srv.psql(seed_sql)

        # Sanity: the old (0008) CHECK is indeed the live constraint and
        # accepted the hyphenated seed rows (would have raised on psql
        # otherwise — `psql` errors surface via CalledProcessError).
        check_def = srv.psql(
            f"\\c {dbname}\nSELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_questionnaire_results_type';"
        )
        assert "PHQ-9" in check_def, (
            f"expected 0008's hyphenated CHECK to still be live pre-0009a; got: {check_def}"
        )

        # 3) The actual regression: `upgrade head` from this DGX-shaped
        #    pre-0009a state must not raise CheckViolationError.
        result_head = _run_alembic("head", database_url)
        assert result_head.returncode == 0, (
            "`alembic upgrade head` failed against a DGX-shaped pre-0009a DB "
            f"carrying hyphenated rows — DB-F2b regression.\n"
            f"stdout:\n{result_head.stdout}\nstderr:\n{result_head.stderr}"
        )
        assert "CheckViolationError" not in result_head.stderr

        # 4) No data loss: all 4 seeded rows survive, converted to plain form.
        rows = srv.psql(
            f"\\c {dbname}\nSELECT type, count(*) FROM questionnaire_results "
            "GROUP BY type ORDER BY type;"
        )
        for hyphenated, plain in _HYPHEN_TO_PLAIN.items():
            assert hyphenated not in rows, (
                f"hyphenated value {hyphenated} should have been backfilled: {rows}"
            )
            assert plain in rows, f"expected converted value {plain} present: {rows}"

        # 5) Final CHECK is 0010's narrow non-hyphenated set.
        final_check = srv.psql(
            f"\\c {dbname}\nSELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_questionnaire_results_type';"
        )
        assert "PHQ9" in final_check and "PHQ-9" not in final_check, (
            f"expected 0010's non-hyphenated CHECK post-head; got: {final_check}"
        )
    finally:
        srv.cleanup()


def test_fresh_pgserver_upgrade_head_still_clean_with_0009a_fix():
    """Non-regression: the DB-F2b fix (dropping 0008's CHECK at the start
    of 0009a's upgrade()) must not break the from-scratch chain covered by
    BUG-065's fresh-DB regression — a from-scratch DB has zero hyphenated
    rows, so 0009a's UPDATEs are no-ops either way, but the added `DROP
    CONSTRAINT IF EXISTS` must not itself raise on a table that already has
    the constraint from 0008's upgrade()."""
    pgdata = tempfile.mkdtemp(prefix="bug_dbf2b_fresh_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    try:
        dbname = "neurosync_bug_dbf2b_fresh"
        srv.psql(f"CREATE DATABASE {dbname};")
        database_url = (
            srv.get_uri()
            .replace("postgresql://", "postgresql+asyncpg://")
            .replace("/postgres?", f"/{dbname}?")
        )
        result = _run_alembic("head", database_url)
        assert result.returncode == 0, (
            "fresh `alembic upgrade head` regressed after the DB-F2b fix.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        srv.cleanup()
