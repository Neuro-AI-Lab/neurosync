"""Test fixtures — async Postgres + FastAPI test client.

Strategy:
- Session-scoped engine connects to `<DATABASE_URL>` with database name replaced by
  `neurosync_test`. We CREATE/DROP the test database around the session so tests
  don't pollute dev data.
- `Base.metadata.create_all` applies the schema directly (faster than alembic for
  unit/integration tests). Migration correctness is verified separately by `make
  migrate`.
- Per-test fixture wraps each test in a SAVEPOINT and rolls back so tests stay
  isolated without recreating tables.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings, get_settings
from src.db import Base, get_session
from src.main import create_app

# Skip the whole test module if no Postgres is reachable — keeps unit tests
# (test_security.py) runnable without a DB.
DEFAULT_DEV_DB = "postgresql+asyncpg://neurosync:dev@localhost:5432/neurosync"
SOURCE_URL = os.environ.get("DATABASE_URL", DEFAULT_DEV_DB)


def _swap_db_name(url: str, new_name: str) -> str:
    parsed = urlparse(url)
    # path is "/dbname"
    return urlunparse(parsed._replace(path=f"/{new_name}"))


TEST_DB_NAME = "neurosync_test"
TEST_URL = _swap_db_name(SOURCE_URL, TEST_DB_NAME)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _ensure_test_database() -> bool:
    """Create the test database if it doesn't exist. Return True on success."""
    admin_url = _swap_db_name(SOURCE_URL, "postgres")
    try:
        admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            existing = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if existing.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        await admin.dispose()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def engine():
    available = await _ensure_test_database()
    if not available:
        pytest.skip("Postgres not reachable — skipping integration tests")
    eng = create_async_engine(TEST_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test session, rolled back at the end. Outer transaction + SAVEPOINT."""
    SessionMaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = SessionMaker(bind=conn)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
def test_settings() -> Settings:
    """Test settings — `app_env="test"` permits weakened Argon2 for fast tests.

    Validators in `core/config.py` enforce PRD §4.5.2 minimums in staging/production.
    """
    return Settings(
        _env_file=None,  # don't leak developer .env into tests
        app_env="test",
        database_url=TEST_URL,
        jwt_secret_key="test-only-jwt-secret-32bytes-min__padding",
        encryption_key="ZGV2LTMyLWJ5dGVzLW9ubHktRE8tTk9ULVVTRS1GT1I=",
        argon2_memory_cost_kib=8,  # 8 KiB — fast for tests, validators block in prod
        argon2_time_cost=1,
        argon2_parallelism=1,
    )


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: _yield(db_session)
    app.dependency_overrides[get_settings] = lambda: test_settings

    return TestClient(app)


async def _yield(session: AsyncSession):
    yield session
