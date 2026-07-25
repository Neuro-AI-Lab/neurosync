"""Committed regression test for Phase 1 session_state / clinical_escalation
persistence — REV-008 (critic) resolution #1.

REV-008's major finding: the Phase 1 pass (session_state turn-to-turn +
WS-reconnect persistence, `clinical_escalation_required` consumer) was
verified against an *ephemeral* throwaway Postgres with no committed
artifact — nothing in the repo could reproduce that claim. This file is
the durable, re-runnable replacement.

Deliberately independent of `tests/conftest.py`: BUG-057 documents two
defects in that file's fixtures (the `lambda: _yield(db_session)`
dependency-override pattern, and `event_loop` session-scoping vs
`pytest-asyncio==1.4.0`) that are unrelated to `src/` and out of this
test's scope to fix. This module does not import or request any
`conftest.py` fixture — it builds its own throwaway Postgres
(`pgserver`, embeddable, no-root, DGX never touched) and its own engine
directly, then exercises `src/services/chat.py::respond` (the actual
Phase 1 production function) with a stub `AIClient` (no `httpx`, no
live LLM call) plus the exact reconnect-reload query
`src/api/v1/sessions.py::session_chat` uses.

Covers PRD Phase 1 completion criteria (`docs/ai/integration_prd_f1f3_hospital.md`
§4) via code path, not claim:
  1. real `alembic` 0010 -> head (0011) migration applied to a throwaway DB
     (`alembic/versions/0011_session_state_persistence.py`'s own
     `upgrade()`, invoked through `alembic.command`, not re-implemented).
  2. `session_state` (carrying the ADR-044 4 fields nested under their own
     keys) persists turn-to-turn on `Session.session_state`
     (`chat.py:243-244`).
  3. the WS-reconnect reseed query in `sessions.py:551-561`
     (`select(Session.patient_id, Session.session_state)...`) reloads the
     last-persisted value — reproduced verbatim here rather than only
     asserting the column value.
  4. `clinical_escalation_required=True` fires both the DB column
     (`chat.py:244`) and the structured log consumer
     (`chat.py:252-260`, `chat.clinical_escalation.flagged`).

Hard constraints (unchanged from the ephemeral pass this replaces):
  - all live API keys forced to "" (BUG-052 — unset alone does not gate).
  - zero live LLM / outbound HTTP: `AIClient.chat_respond` is replaced by an
    in-process stub; `httpx.AsyncClient.post` is monkeypatched to raise if
    anything ever reaches it, as a hard guard rather than an assumption.
  - no DGX Postgres (223.194.33.26:28881) touched — `pgserver` throwaway
    instance only, torn down at test end.

Test-only dependency note: `pgserver` is NOT declared in
`apps/api/pyproject.toml` / `uv.lock` (qa scope excludes editing the
dependency manifest — filemanager's call). If it is not importable in the
environment this runs in, the whole module is skipped rather than erroring
(`pytest.importorskip` below) — see this file's regression-test entry in
error.md BUG-057 resolution / REV-008 for the "needs declaring" note.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

pgserver = pytest.importorskip(
    "pgserver",
    reason=(
        "test-only throwaway-Postgres helper not declared in "
        "apps/api/pyproject.toml/uv.lock yet (qa does not edit the "
        "dependency manifest — see REV-008 resolution note in error.md); "
        "skipping gracefully rather than erroring the suite."
    ),
)

# All live keys forced empty BEFORE any src.* import touches Settings()
# (BUG-052: unset alone does not gate live-only paths; only "" does).
for _key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "UPSTAGE_API_KEY",
    "SKT_A_X_API_KEY",
):
    os.environ[_key] = ""


@pytest.fixture(scope="module")
def _throwaway_postgres_url() -> Any:
    """Self-contained throwaway Postgres — no conftest, no DGX.

    `cleanup_mode="delete"` removes the pgdata dir on `.cleanup()`; the
    tmpdir itself is also independently removed to leave zero artifacts.
    """
    pgdata = tempfile.mkdtemp(prefix="qa_phase1_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    srv.psql("CREATE DATABASE neurosync_qa_phase1;")
    uri = (
        srv.get_uri()
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("/postgres?", "/neurosync_qa_phase1?")
    )
    os.environ["DATABASE_URL"] = uri
    # `src.core.config.get_settings` is `@lru_cache`d — some other test
    # module's collection-time import may have already memoized a
    # `Settings()` built before this env var was set (e.g. the default
    # `localhost:5432` URL). Clear it here so `alembic/env.py`'s own
    # `get_settings().database_url` read picks up THIS throwaway DB
    # instead of silently reusing a stale cached instance.
    from src.core.config import get_settings

    get_settings.cache_clear()
    try:
        yield uri
    finally:
        get_settings.cache_clear()
        srv.cleanup()


@pytest.fixture(scope="module")
def _migrated_engine(_throwaway_postgres_url: str):
    """Bootstrap schema up to (equivalent of) revision 0010, then run the
    REAL `alembic upgrade head` — i.e. actually execute
    `0011_session_state_persistence.py`'s `upgrade()` against Postgres,
    not a re-implementation of it.

    Deliberately a *synchronous* fixture: `alembic/env.py` calls
    `asyncio.run(...)` internally, which raises `RuntimeError: asyncio.run()
    cannot be called from a running event loop` if invoked from inside an
    `async def` fixture under pytest-asyncio. Running the baseline-schema
    setup and the alembic commands here (outside any event loop) sidesteps
    that entirely — this file makes zero use of `conftest.py`'s
    session-scoped `event_loop` fixture (BUG-057 root cause 2).

    `Base.metadata.create_all` (rather than replaying migrations 0001-0010
    one at a time) is used only to reach the pre-0011 baseline quickly;
    this mirrors the same TEST-ONLY workaround `tests/conftest.py` already
    uses for the *unrelated*, pre-existing `patient_profiles.is_minor`
    generated-column-immutability defect (migration 0001, PG rejects
    CURRENT_DATE in a STORED generated column) — not something this pass
    introduces or is scoped to fix. The two Phase 1 columns are then
    dropped to reproduce the exact pre-0011 shape before alembic adds them
    back for real.
    """
    import asyncio

    import alembic.command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import src.models  # noqa: F401 — register all tables on Base.metadata
    from src.db import Base
    from src.models.patient_profile import PatientProfile

    is_minor_col = PatientProfile.__table__.c.is_minor
    is_minor_col.computed = None
    is_minor_col.server_default = text("false")

    async def _create_pre_0011_baseline() -> None:
        baseline_engine = create_async_engine(_throwaway_postgres_url, echo=False)
        try:
            async with baseline_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(
                    text("ALTER TABLE sessions DROP COLUMN session_state")
                )
                await conn.execute(
                    text(
                        "ALTER TABLE sessions DROP COLUMN clinical_escalation_required"
                    )
                )
        finally:
            await baseline_engine.dispose()

    asyncio.run(_create_pre_0011_baseline())

    alembic_dir = os.path.join(os.path.dirname(__file__), "..", "alembic")
    cfg = Config()
    cfg.set_main_option("script_location", os.path.abspath(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", _throwaway_postgres_url)
    alembic.command.stamp(cfg, "0010")
    alembic.command.upgrade(cfg, "head")  # <- real 0011 upgrade() executes here

    async def _verify_columns() -> set[str]:
        verify_engine = create_async_engine(_throwaway_postgres_url, echo=False)
        try:
            async with verify_engine.connect() as conn:
                cols = await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='sessions' "
                        "AND column_name IN "
                        "('session_state','clinical_escalation_required')"
                    )
                )
                return {row[0] for row in cols.fetchall()}
        finally:
            await verify_engine.dispose()

    found = asyncio.run(_verify_columns())
    assert found == {"session_state", "clinical_escalation_required"}, (
        f"alembic 0010->head did not add the expected Phase 1 columns: {found}"
    )

    # Yield the URL, not a bound `AsyncEngine` — pytest-asyncio's DEFAULT
    # loop scope is per-TEST-FUNCTION, so a single module-scoped engine's
    # pooled asyncpg connections get created inside test A's event loop and
    # then handed to test B's *different* event loop, producing exactly
    # the `InterfaceError: another operation is in progress` cross-loop
    # corruption BUG-057 documents for `conftest.py`'s own session-scoped
    # `event_loop` fixture. `db_session` below builds a fresh, `NullPool`
    # engine per test instead (no connection survives across a test
    # boundary), sidestepping that class of bug entirely rather than
    # relying on the same pattern that broke `conftest.py`.
    return _throwaway_postgres_url


@pytest_asyncio.fixture
async def db_session(_migrated_engine: str) -> AsyncGenerator[Any, None]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    # `NullPool`: a brand-new asyncpg connection per checkout, discarded
    # (not pooled) at checkin — guarantees no connection outlives this
    # test's own event loop.
    engine = create_async_engine(_migrated_engine, echo=False, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, autoflush=False, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(db_session) -> Any:
    """A minimal patient + in-progress session row — the FK graph
    `Session.patient_id -> users.id` requires a real user row."""
    from src.models.session import Session
    from src.models.user import User

    patient = User(
        id=uuid.uuid4(),
        email=f"qa-phase1-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role="patient",
    )
    db_session.add(patient)
    await db_session.flush()  # patient row must exist before the FK-dependent insert
    sess = Session(id=uuid.uuid4(), patient_id=patient.id, status="in_progress")
    db_session.add(sess)
    await db_session.commit()
    return sess.id


class _StubAIClient:
    """In-process stand-in for `src.services.ai_client.AIClient` — no
    `httpx`, no live LLM. `chat_respond` returns a scripted `ChatResponse`
    per call so each simulated turn can carry its own
    `clinical_escalation_required`/`session_state`."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[Any] = []

    async def chat_respond(self, payload: Any) -> Any:
        self.calls.append(payload)
        return self._responses.pop(0)

    async def slots_extract(self, payload: Any) -> Any:
        from contracts.slots import SlotsExtractResponse

        return SlotsExtractResponse(extracted_slots={})


def _chat_response(*, session_state: dict[str, Any], escalation: bool) -> Any:
    from contracts.chat import ChatResponse

    return ChatResponse(
        assistant_response="ack",
        session_state=session_state,
        clinical_escalation_required=escalation,
        risk_level="high" if escalation else "low",
        requires_human_review=escalation,
    )


@pytest.fixture(autouse=True)
def _forbid_live_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard guard, not an assumption: any attempt to actually reach the
    network via httpx (i.e. the real `AIClient`) fails the test loudly
    instead of silently succeeding against a live/mocked server."""
    import httpx

    async def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "live HTTP call attempted — this test must only use _StubAIClient"
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _forbidden)


async def _post_user_turn(db_session, session_id, settings, text: str) -> None:
    """Mirrors `chat.py::_message_aad` exactly — the real code decrypts with
    `aad=f"messages.content:{session_id}:{message_id}".encode()`
    (`chat.py:47-48`); a mismatched AAD here would make `_recent_messages`
    silently skip the row as undecryptable (its own documented best-effort
    behavior) and falsely look like a Phase 1 wiring bug."""
    from src.core.encryption import encrypt_str
    from src.models.session import Message

    message_id = uuid.uuid4()
    db_session.add(
        Message(
            id=message_id,
            session_id=session_id,
            role="user",
            content_encrypted=encrypt_str(
                text,
                aad=f"messages.content:{session_id}:{message_id}".encode(),
                settings=settings,
            ),
            input_modality="text",
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_session_state_persists_turn_to_turn(db_session, seeded_session):
    """PRD §4 Phase1 / ADR-046 #2: `Session.session_state` round-trips and
    accumulates across two consecutive turns via `chat.py::respond` — the
    actual production function, not a re-implementation."""
    from src.core.config import Settings
    from src.services.chat import respond as chat_respond

    session_id = seeded_session
    settings = Settings()

    # Turn 1 — no prior session_state (None on first turn, per docstring).
    await _post_user_turn(db_session, session_id, settings, "hello")
    turn1_state = {
        "asked_slot_counts": {"chief_complaint": 1},
        "risk_screening_incomplete": True,
        "clinical_escalation_required": False,
        "handoff_delivered": False,
    }
    ai_client = _StubAIClient(
        [_chat_response(session_state=turn1_state, escalation=False)]
    )
    payload1 = await chat_respond(
        db_session,
        ai_client=ai_client,
        session_id=session_id,
        settings=settings,
        session_state=None,
    )
    await db_session.commit()

    assert payload1 is not None
    assert payload1["sessionState"] == turn1_state

    from sqlalchemy import select

    from src.models.session import Session

    row = await db_session.execute(select(Session).where(Session.id == session_id))
    sess = row.scalar_one()
    assert sess.session_state == turn1_state
    assert sess.clinical_escalation_required is False

    # Turn 2 — caller threads turn 1's returned sessionState back in
    # (mirrors `sessions.py::_handle_message`'s `next_session_state`).
    await _post_user_turn(db_session, session_id, settings, "still here")
    turn2_state = {
        "asked_slot_counts": {"chief_complaint": 1, "onset": 1},
        "risk_screening_incomplete": False,
        "clinical_escalation_required": False,
        "handoff_delivered": False,
    }
    ai_client2 = _StubAIClient(
        [_chat_response(session_state=turn2_state, escalation=False)]
    )
    payload2 = await chat_respond(
        db_session,
        ai_client=ai_client2,
        session_id=session_id,
        settings=settings,
        session_state=payload1["sessionState"],
    )
    await db_session.commit()

    assert payload2 is not None
    # The turn-2 request carried turn-1's state forward (round-trip channel).
    assert ai_client2.calls[0].session_state == turn1_state

    row2 = await db_session.execute(select(Session).where(Session.id == session_id))
    sess2 = row2.scalar_one()
    assert sess2.session_state == turn2_state, (
        "session_state did not persist/update turn-to-turn on Session.session_state"
    )


@pytest.mark.asyncio
async def test_session_state_survives_ws_reconnect_reseed_query(
    db_session, seeded_session
):
    """Reproduces `src/api/v1/sessions.py::session_chat`'s exact reconnect
    reseed query (`select(Session.patient_id, Session.session_state)`,
    sessions.py:551-561) against a session whose state was persisted by a
    PRIOR (now-closed) connection, proving the round-trip survives a
    reconnect rather than only a single open WS connection."""
    from sqlalchemy import select

    from src.models.session import Session

    session_id = seeded_session
    persisted_state = {
        "asked_slot_counts": {"chief_complaint": 2},
        "risk_screening_incomplete": False,
        "clinical_escalation_required": False,
        "handoff_delivered": True,
    }

    # Simulate the FIRST connection's last-persisted write (what
    # chat.py::respond would have committed before this connection closed).
    row = await db_session.execute(select(Session).where(Session.id == session_id))
    sess = row.scalar_one()
    sess.session_state = persisted_state
    await db_session.commit()

    # Simulate a WS reconnect: a fresh query, exactly as
    # `sessions.py::session_chat` runs on `ws.accept()`, with no in-memory
    # state carried over from the prior connection.
    reconnect_row = await db_session.execute(
        select(Session.patient_id, Session.session_state).where(
            Session.id == session_id
        )
    )
    reconnect_result = reconnect_row.one_or_none()
    assert reconnect_result is not None
    reloaded_session_state = reconnect_result[1]

    assert reloaded_session_state == persisted_state, (
        "WS-reconnect reseed query did not reload the last-persisted "
        "session_state — reconnect would incorrectly restart from None"
    )


@pytest.mark.asyncio
async def test_clinical_escalation_required_fires_log_and_db_column(
    db_session, seeded_session, caplog
):
    """CVR-047 recommendation 3 minimal consumer: `clinical_escalation_required
    == True` must (a) persist on `Session.clinical_escalation_required` and
    (b) emit the structured `chat.clinical_escalation.flagged` warning log
    (`chat.py:252-260`) — both from one real `respond()` call, not asserted
    separately/aspirationally."""
    import logging

    from sqlalchemy import select

    from src.core.config import Settings
    from src.models.session import Session
    from src.services.chat import respond as chat_respond

    session_id = seeded_session
    settings = Settings()

    await _post_user_turn(db_session, session_id, settings, "I want to hurt myself")

    escalation_state = {
        "asked_slot_counts": {},
        "risk_screening_incomplete": True,
        "clinical_escalation_required": True,
        "handoff_delivered": False,
    }
    ai_client = _StubAIClient(
        [_chat_response(session_state=escalation_state, escalation=True)]
    )

    with caplog.at_level(logging.WARNING, logger="src.services.chat"):
        payload = await chat_respond(
            db_session,
            ai_client=ai_client,
            session_id=session_id,
            settings=settings,
            session_state=None,
        )
        await db_session.commit()

    assert payload is not None
    assert payload["clinicalEscalationRequired"] is True

    row = await db_session.execute(select(Session).where(Session.id == session_id))
    sess = row.scalar_one()
    assert sess.clinical_escalation_required is True, (
        "clinical_escalation_required=True from ai-server did not persist "
        "onto Session.clinical_escalation_required"
    )

    flagged = [r for r in caplog.records if r.message == "chat.clinical_escalation.flagged"]
    assert len(flagged) == 1, (
        "expected exactly one chat.clinical_escalation.flagged log record "
        f"when clinical_escalation_required=True, got {len(flagged)}"
    )
    assert flagged[0].session_id == str(session_id)
    assert flagged[0].risk_level == "high"
    assert flagged[0].requires_human_review is True
