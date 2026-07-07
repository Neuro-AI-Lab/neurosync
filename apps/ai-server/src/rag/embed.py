"""Upstage solar 임베딩 (passage/query, 4096차원).

비대칭: 문서=passage, 질의=query. 키 없거나 EMBED_DUMMY=1 이면 결정적 더미 벡터로
대체(키 없이 배관 관통). 환경변수(.env)로 설정 — apps/api는 pydantic-settings가 .env
로딩하므로 python-dotenv는 선택.

Upstage API Key 는 AI팀 발급(시크릿 §infra) — 본 프로젝트에선 apps/api도 RAG 질의
임베딩에 사용(런타임 1콜/턴, 코퍼스는 오프라인 1회).
"""

from __future__ import annotations

import hashlib
import os
import random

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pydantic-settings 가 .env 처리 — dotenv 없어도 OK
    pass

EMBED_DIM = 4096  # solar-embedding-1-large. schema vector(4096)와 일치해야 함.

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")
# 임베딩 전용 base URL. ai-server config의 채팅용 UPSTAGE_BASE_URL(.../v1)과 충돌 방지 —
# 임베딩은 반드시 /solar 접미가 필요하므로 독립 env(EMBED_BASE_URL)로 분리.
UPSTAGE_BASE_URL = os.getenv("EMBED_BASE_URL", "https://api.upstage.ai/v1/solar")
PASSAGE_MODEL = os.getenv("UPSTAGE_PASSAGE_MODEL", "solar-embedding-1-large-passage")
QUERY_MODEL = os.getenv("UPSTAGE_QUERY_MODEL", "solar-embedding-1-large-query")
USE_DUMMY = os.getenv("EMBED_DUMMY", "0") == "1" or not UPSTAGE_API_KEY

_client = None


def _dummy(text: str) -> list[float]:
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(EMBED_DIM)]


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=UPSTAGE_API_KEY, base_url=UPSTAGE_BASE_URL)
    return _client


def _embed(texts: list[str], model: str) -> list[list[float]]:
    if USE_DUMMY:
        return [_dummy(t) for t in texts]
    resp = _get_client().embeddings.create(model=model, input=texts)
    data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in data]


def embed_passages(texts: list[str]) -> list[list[float]]:
    return _embed(texts, PASSAGE_MODEL)


def embed_query(text: str) -> list[float]:
    return _embed([text], QUERY_MODEL)[0]


def to_pgvector(vec: list[float]) -> str:
    """파이썬 리스트 → pgvector 리터럴 '[..]'. SQL에서 ::vector / CAST(.. AS vector)."""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
