"""Regression test for BUG-064 (additive step fixed this pass, per
fix_wave_design.md §(c) — full role-rename explicitly deferred/out-of-wave).

Pre-fix: ai-server's Upstage-backed chat API rejects the platform's
DB-native `role='ai'` from the 2nd conversational turn onward. The interim
mitigation (`services/chat.py::respond`, `'ai'`->`'assistant'` outbound-only
map) stays in place — storage still writes `'ai'`. This wave's fix is the
additive DB/model-source step only: `messages.role`'s CHECK now ALSO allows
`'assistant'` (migration 0012 + `models/session.py`), closing the
schema-level obstacle without doing the full storage-rename backfill (an
explicit, deferred follow-up per the design doc).

This test checks: (1) the model source CHECK includes 'assistant' (offline),
(2) the outbound seam-map in `services/chat.py::respond` still maps every
'ai' -> 'assistant' before it leaves the process (guards the interim
mitigation against regression, per BUG-064's own recommended repro), and (3)
a fresh migrated DB's live CHECK matches the model source (closing BUG-064's
actual defect: source/DB divergence)."""

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


def test_model_source_role_check_includes_assistant():
    from src.models.session import Message

    check_clauses = [
        str(c.sqltext) for c in Message.__table__.constraints if hasattr(c, "sqltext")
    ]
    role_checks = [c for c in check_clauses if "role" in c]
    assert role_checks, "no CHECK constraint found on messages.role"
    assert any("'assistant'" in c for c in role_checks), (
        f"messages.role CHECK does not include 'assistant': {role_checks!r}"
    )
    # Additive-only per the design: 'ai' must still be valid too (storage
    # still writes it — the full rename is an explicit, deferred follow-up).
    assert any("'ai'" in c for c in role_checks)


def test_outbound_seam_map_still_maps_ai_to_assistant():
    """BUG-064's own recommended repro: the interim mitigation (still in
    place — full rename is deferred) must keep mapping every outbound
    context message's role='ai' to 'assistant' before it reaches ai-server,
    or a live Upstage call would 400 again from the 2nd turn on.

    BUG-067 factored this seam-map into a single shared helper
    (`_to_llm_role`/`_to_llm_history`) so every outbound conversation_history
    builder (not just `respond`'s) goes through it. This test now checks the
    helper directly, plus that `respond` actually calls it, rather than
    grepping for an inline literal that no longer exists post-refactor.
    """
    import inspect

    from src.services.chat import _to_llm_role, respond

    assert _to_llm_role("ai") == "assistant"
    assert _to_llm_role("user") == "user"
    assert _to_llm_role("system") == "system"

    source = inspect.getsource(respond)
    assert "_to_llm_history(" in source, (
        "services/chat.py::respond no longer routes its outbound "
        "conversation_history through the shared _to_llm_history seam-map — "
        "BUG-064 regression risk (unmapped 'ai' 400s at Upstage from the 2nd "
        "turn on)"
    )


def test_fresh_migrated_db_role_check_matches_model():
    import subprocess
    import sys
    from pathlib import Path

    apps_api_root = Path(__file__).resolve().parents[2]
    pgdata = tempfile.mkdtemp(prefix="bug064_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    try:
        srv.psql("CREATE DATABASE neurosync_bug064;")
        database_url = (
            srv.get_uri()
            .replace("postgresql://", "postgresql+asyncpg://")
            .replace("/postgres?", "/neurosync_bug064?")
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

        sync_url = srv.get_uri().replace("/postgres?", "/neurosync_bug064?")
        import psycopg

        with psycopg.connect(sync_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid='messages'::regclass AND conname='ck_messages_role'"
                )
                (constraint_def,) = cur.fetchone()
                assert "assistant" in constraint_def
                assert "'ai'" in constraint_def
    finally:
        srv.cleanup()
