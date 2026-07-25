"""BUG-069 follow-up (F5 metadata enrichment, 2026-07-25) regression —
`services/handoff.py::_build_request` now threads the REAL
`PatientProfile.gender`/`Session.created_at`/`Session.submitted_at` values
into `HandoffRequest.patient_gender`/`session_started_at`/
`session_ended_at` (previously always `None`, forcing ai-server's v4.3+
"기록 없음"/"미수집" fallback even when the platform actually had the
data).

Pattern mirrors `test_bug_076_medium_si_riskevent.py`/
`test_cvr051_crisis_escalation_wire.py`: own throwaway `pgserver` Postgres,
`Base.metadata.create_all` schema, no live LLM/HTTP.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio

pgserver = pytest.importorskip(
    "pgserver",
    reason=(
        "test-only throwaway-Postgres helper not declared in "
        "apps/api/pyproject.toml/uv.lock yet; skipping gracefully."
    ),
)

for _key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "UPSTAGE_API_KEY", "SKT_A_X_API_KEY"):
    os.environ[_key] = ""


@pytest.fixture(scope="module")
def _throwaway_postgres_url() -> Any:
    pgdata = tempfile.mkdtemp(prefix="qa_bug069fu_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    srv.psql("CREATE DATABASE neurosync_qa_bug069fu;")
    uri = (
        srv.get_uri()
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("/postgres?", "/neurosync_qa_bug069fu?")
    )
    os.environ["DATABASE_URL"] = uri
    from src.core.config import get_settings

    get_settings.cache_clear()
    try:
        yield uri
    finally:
        get_settings.cache_clear()
        srv.cleanup()


@pytest.fixture(scope="module")
def _migrated_engine(_throwaway_postgres_url: str):
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    import src.models  # noqa: F401 — register all tables on Base.metadata
    from src.db import Base
    from src.models.patient_profile import PatientProfile

    # `tests/conftest.py` (auto-loaded for the whole session regardless of
    # which test file is running) sets `is_minor.server_default = text(
    # "false")` as a TEST-ONLY convenience for callers that omit
    # `is_minor=`. That `TextClause` object crashes SQLAlchemy's ORM
    # `_insert_cols_as_none` mapper-cache computation (`bool(TextClause(...))`
    # raises) the FIRST time any INSERT is emitted against this table via a
    # fresh `Base.metadata.create_all`-schema'd engine (this file's own
    # throwaway-Postgres fixture, independent of `conftest.py`'s own
    # DB) — every `PatientProfile(...)` construction below supplies
    # `is_minor=` explicitly, so the default is never actually needed;
    # clearing it avoids tripping that SQLAlchemy quirk for this file's
    # engine.
    PatientProfile.__table__.c.is_minor.server_default = None

    async def _create_schema() -> None:
        engine = create_async_engine(_throwaway_postgres_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(_create_schema())
    return _throwaway_postgres_url


@pytest_asyncio.fixture
async def db_session(_migrated_engine: str) -> AsyncGenerator[Any, None]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

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


async def _seed_patient_and_session(
    db_session, *, gender: str | None, submitted: bool
) -> uuid.UUID:
    from src.core.encryption import encrypt_str
    from src.models.patient_profile import PatientProfile
    from src.models.session import Session
    from src.models.user import User

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"qa-bug069fu-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role="patient",
    )
    db_session.add(user)
    await db_session.flush()

    profile = PatientProfile(
        user_id=user_id,
        name_encrypted=encrypt_str(
            "홍길동", aad=f"patient_profiles.name:{user_id}".encode()
        ),
        birth_year=1990,
        is_minor=False,
        gender=gender,
    )
    db_session.add(profile)

    sess = Session(
        id=uuid.uuid4(),
        patient_id=user_id,
        status="submitted" if submitted else "in_progress",
        submitted_at=datetime.now(UTC) if submitted else None,
    )
    db_session.add(sess)
    await db_session.commit()
    return sess.id


@pytest.mark.asyncio
async def test_build_patient_metadata_returns_real_gender_and_timestamps(db_session):
    from src.services.handoff import _build_patient_metadata

    session_id = await _seed_patient_and_session(db_session, gender="female", submitted=True)

    gender, started_at, ended_at = await _build_patient_metadata(db_session, session_id)

    assert gender == "female"
    assert started_at is not None, "Session.created_at (server_default=now()) must be populated"
    assert ended_at is not None, "submitted session must carry a real submitted_at"
    # ISO-8601 round-trips.
    datetime.fromisoformat(started_at)
    datetime.fromisoformat(ended_at)


@pytest.mark.asyncio
async def test_build_patient_metadata_none_when_not_submitted_or_no_gender(db_session):
    """A session still `in_progress` (never submitted) has no
    `submitted_at`; a patient with no `gender` on file returns `None` for
    that field — both must surface as `None`, not an invented placeholder,
    so ai-server's existing fallback keeps firing correctly for them."""
    from src.services.handoff import _build_patient_metadata

    session_id = await _seed_patient_and_session(db_session, gender=None, submitted=False)

    gender, started_at, ended_at = await _build_patient_metadata(db_session, session_id)

    assert gender is None
    assert started_at is not None  # created_at is always set
    assert ended_at is None


@pytest.mark.asyncio
async def test_build_request_threads_metadata_into_handoff_request(db_session):
    from src.services.handoff import _build_request

    session_id = await _seed_patient_and_session(db_session, gender="male", submitted=True)

    req = await _build_request(db_session, session_id)

    assert req.patient_gender == "male"
    assert req.session_started_at is not None
    assert req.session_ended_at is not None
