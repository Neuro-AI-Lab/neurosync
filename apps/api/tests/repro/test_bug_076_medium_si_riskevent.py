"""BUG-076 regression (option A, CVR-055/056-supported) — a MEDIUM-level
safety result carrying a suicide/self-harm-family category now persists a
`RiskEvent` (status="pending_reclassify") instead of being logged-only.

CVR-055's finding: this session's ONLY structured safety signal was a
(previously mis-scored) `risk_assessment` slot text — with `handle_safety_
result` discarding every MEDIUM result outright ("RiskEvent skipped...to
keep the table focused on actionable events"), a passive-SI/CTRS-3-shaped
disclosure could leave ZERO clinician-reviewable trace in `risk_events`
even when correctly scored. CVR-055 recommended "옵션 A" (MEDIUM + SI
signal -> persist a RiskEvent) over "옵션 B" (log-severity only, invisible
to a clinician who doesn't open the raw session).

This fix is deliberately narrow and additive:
  - Client-facing routing/notification policy is UNCHANGED (`handle_safety_
    result` still returns `None` for MEDIUM — no `routeTo`, no hotlines
    payload, no consent/notification dispatch).
  - Only MEDIUM + `RiskCategory.SUICIDE`/`RiskCategory.SELF_HARM` persists;
    a plain MEDIUM with a non-SI category (e.g. `ACUTE_DISTRESS`) keeps the
    pre-existing log-only behavior (negative control below) — this is not a
    blanket "persist every MEDIUM" change.

Pattern mirrors `tests/test_cvr051_crisis_escalation_wire.py`: own
throwaway `pgserver` Postgres, `Base.metadata.create_all` schema, no live
LLM/HTTP.
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
        "apps/api/pyproject.toml/uv.lock yet; skipping gracefully."
    ),
)

for _key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "UPSTAGE_API_KEY", "SKT_A_X_API_KEY"):
    os.environ[_key] = ""


@pytest.fixture(scope="module")
def _throwaway_postgres_url() -> Any:
    pgdata = tempfile.mkdtemp(prefix="qa_bug076_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    srv.psql("CREATE DATABASE neurosync_qa_bug076;")
    uri = (
        srv.get_uri()
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("/postgres?", "/neurosync_qa_bug076?")
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


@pytest_asyncio.fixture
async def seeded_session(db_session) -> Any:
    from src.models.session import Session
    from src.models.user import User

    patient = User(
        id=uuid.uuid4(),
        email=f"qa-bug076-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role="patient",
    )
    db_session.add(patient)
    await db_session.flush()
    sess = Session(id=uuid.uuid4(), patient_id=patient.id, status="in_progress")
    db_session.add(sess)
    await db_session.commit()
    return patient.id, sess.id


async def _seed_message(db_session, session_id: uuid.UUID) -> uuid.UUID:
    """RiskEvent.trigger_message_id is a real FK to `messages` — insert a
    minimal real Message row rather than an arbitrary UUID for the
    persistence-path test (the non-SI/LOW negative controls below never
    reach the INSERT, so they use a bare `uuid.uuid4()` safely)."""
    from src.core.encryption import encrypt_str
    from src.models.session import Message

    message_id = uuid.uuid4()
    db_session.add(
        Message(
            id=message_id,
            session_id=session_id,
            role="user",
            content_encrypted=encrypt_str(
                "아침에 눈을 안 떴으면 좋겠어",
                aad=f"messages.content:{session_id}:{message_id}".encode(),
            ),
            input_modality="text",
        )
    )
    await db_session.flush()
    return message_id


def _medium_assessment(category: str):
    from contracts.safety import RiskCategory, RiskLevel, SafetyAssessment, SafetyEvidence

    return SafetyAssessment(
        level=RiskLevel.MEDIUM,
        category=RiskCategory(category),
        evidence=SafetyEvidence(
            matched_keywords=["눈을 안 떴으면"], classifier="test", confidence=0.6
        ),
        latency_ms=5,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["suicide", "self_harm"])
async def test_medium_si_category_persists_risk_event(db_session, seeded_session, category):
    """BUG-076 fix: MEDIUM + suicide/self_harm category persists a RiskEvent
    (status=pending_reclassify), and the client-facing return value is still
    None (no routing/notification change)."""
    from sqlalchemy import select

    from src.models.session import RiskEvent
    from src.services.safety import handle_safety_result

    patient_id, session_id = seeded_session
    trigger_message_id = await _seed_message(db_session, session_id)

    payload = await handle_safety_result(
        db_session,
        patient_id=patient_id,
        session_id=session_id,
        trigger_message_id=trigger_message_id,
        context_message_ids=[],
        safety=_medium_assessment(category),
        consent=None,
    )
    await db_session.commit()

    assert payload is None, "MEDIUM must still produce no client-facing routing payload"

    rows = await db_session.execute(select(RiskEvent).where(RiskEvent.session_id == session_id))
    events = rows.scalars().all()
    assert len(events) == 1, f"expected exactly one RiskEvent for category={category!r}"
    event = events[0]
    assert event.level == "medium"
    assert event.category == category
    assert event.status == "pending_reclassify"
    assert event.trigger_message_id == trigger_message_id
    assert event.notified_to is None


@pytest.mark.asyncio
async def test_medium_non_si_category_stays_log_only(db_session, seeded_session):
    """Negative control: a plain MEDIUM with a non-SI category (e.g.
    acute_distress) must NOT persist a RiskEvent — the pre-existing
    log-only behavior is unchanged for this case, this fix is scoped to
    SI-family categories only."""
    from sqlalchemy import select

    from src.models.session import RiskEvent
    from src.services.safety import handle_safety_result

    patient_id, session_id = seeded_session

    payload = await handle_safety_result(
        db_session,
        patient_id=patient_id,
        session_id=session_id,
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        safety=_medium_assessment("acute_distress"),
        consent=None,
    )
    await db_session.commit()

    assert payload is None

    rows = await db_session.execute(select(RiskEvent).where(RiskEvent.session_id == session_id))
    assert rows.scalars().all() == []


@pytest.mark.asyncio
async def test_low_level_unaffected(db_session, seeded_session):
    """Regression guard: LOW level (even with an SI category, which
    shouldn't happen in practice but isolates the level-gate) still returns
    None with no RiskEvent — this fix only touches the MEDIUM branch."""
    from contracts.safety import RiskCategory, RiskLevel, SafetyAssessment, SafetyEvidence
    from sqlalchemy import select

    from src.models.session import RiskEvent
    from src.services.safety import handle_safety_result

    patient_id, session_id = seeded_session

    payload = await handle_safety_result(
        db_session,
        patient_id=patient_id,
        session_id=session_id,
        trigger_message_id=uuid.uuid4(),
        context_message_ids=[],
        safety=SafetyAssessment(
            level=RiskLevel.LOW,
            category=RiskCategory.SUICIDE,
            evidence=SafetyEvidence(matched_keywords=[], classifier="test", confidence=0.1),
            latency_ms=1,
        ),
        consent=None,
    )
    await db_session.commit()

    assert payload is None
    rows = await db_session.execute(select(RiskEvent).where(RiskEvent.session_id == session_id))
    assert rows.scalars().all() == []
