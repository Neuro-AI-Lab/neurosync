"""오프라인 툴링용 sync psycopg 연결.

런타임은 async SQLAlchemy(asyncpg)지만 적재/임베딩 배치는 sync가 단순.
DATABASE_URL의 SQLAlchemy 드라이버 접두(+asyncpg/+psycopg)를 떼고 psycopg로 연결.
"""

from __future__ import annotations

import os

import psycopg


def _dsn() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://neurosync:dev@localhost:5432/neurosync")
    return url.replace("+asyncpg", "").replace("+psycopg", "")


def connect() -> psycopg.Connection:
    return psycopg.connect(_dsn())
