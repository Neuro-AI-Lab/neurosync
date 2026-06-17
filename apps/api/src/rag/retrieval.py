"""RAG 런타임 검색 (async) — grounding 4슬롯 생성.

apps/api(WS chat)가 사용자 발화로 호출 → shared-contracts `Grounding` 반환 →
ChatRequest.grounding 으로 ai-server에 주입.

슬롯:
  1) similar_cases  남의 유사사례 (case_card)       — 벡터
  2) my_past        내 과거 (session_insights)        — 벡터 + patient 필터
  3) knowledge      정신과 지식 (qa)                  — 벡터
  4) follow_up      언급 증상 → 후보 질병 → 미확인 증상 — 심볼릭 그래프

pgvector 연산은 raw SQL(text())로 — asyncpg 위에서 그대로 동작(추가 의존성 없음).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from contracts.chat import (
    Grounding,
    GroundingCase,
    GroundingFollowup,
    GroundingKnowledge,
    GroundingPast,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.rag.embed import embed_query, to_pgvector


async def _topk(
    db: AsyncSession, table: str, cols: str, params: dict[str, Any], k: int, where: str = ""
) -> list[Any]:
    sql = text(
        f"""SELECT {cols}, 1 - (embedding <=> CAST(:q AS vector)) AS score
            FROM rag.{table}
            WHERE embedding IS NOT NULL {where}
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT :k"""
    )
    return (await db.execute(sql, {**params, "k": k})).fetchall()


async def _detect_symptoms(db: AsyncSession, utterance: str) -> list[tuple[int, str]]:
    """발화에 증상 한글명/동의어가 등장하면 해당 증상으로 간주 (LLM 추출의 자리표시).
    TODO: ai-server 구조화 추출(40 플래그)로 교체하면 정확도↑ (MedRAG 변별자질 확장)."""
    rows = (
        await db.execute(text("SELECT symptom_id, name, name_ko, synonyms FROM rag.symptom"))
    ).fetchall()
    hits: list[tuple[int, str]] = []
    for sid, name, name_ko, synonyms in rows:
        terms = [name_ko or name] + list(synonyms or [])
        if any(t and t in utterance for t in terms):
            hits.append((sid, name_ko or name))
    return hits


async def _followup(db: AsyncSession, mentioned_ids: list[int]) -> GroundingFollowup | None:
    if not mentioned_ids:
        return None
    row = (
        await db.execute(
            text(
                """SELECT d.disease_id, d.name_ko, count(*) AS overlap
                   FROM rag.disease_symptom ds JOIN rag.disease d USING (disease_id)
                   WHERE ds.symptom_id = ANY(:ids)
                   GROUP BY d.disease_id, d.name_ko
                   ORDER BY overlap DESC, d.disease_id LIMIT 1"""
            ),
            {"ids": mentioned_ids},
        )
    ).fetchone()
    if not row:
        return None
    did, dname, _ = row
    unconfirmed = (
        await db.execute(
            text(
                """SELECT s.name_ko
                   FROM rag.disease_symptom ds JOIN rag.symptom s USING (symptom_id)
                   WHERE ds.disease_id = :did AND ds.symptom_id <> ALL(:ids)"""
            ),
            {"did": did, "ids": mentioned_ids},
        )
    ).fetchall()
    return GroundingFollowup(
        candidate_disease=dname, follow_up_symptoms=[r[0] for r in unconfirmed]
    )


def _dec(v: Any) -> str:
    return bytes(v).decode("utf-8", "ignore") if v is not None else ""


async def retrieve_grounding(
    db: AsyncSession, utterance: str, *, patient_id: UUID | None = None, k: int = 3
) -> Grounding:
    """사용자 발화 → grounding. embed_query는 동기(Upstage SDK)라 thread로 오프로드."""
    qlit = to_pgvector(await asyncio.to_thread(embed_query, utterance))

    cases = await _topk(db, "case_card", "class, situation", {"q": qlit}, k)
    qa = await _topk(db, "qa", "question, answer", {"q": qlit}, k)

    past: list[Any] = []
    if patient_id is not None:
        past = await _topk(
            db,
            "session_insights",
            "class, situation_encrypted",
            {"q": qlit, "pid": str(patient_id)},
            k,
            where="AND patient_id = :pid",
        )

    mentioned = await _detect_symptoms(db, utterance)
    followup = await _followup(db, [m[0] for m in mentioned])

    return Grounding(
        similar_cases=[
            GroundingCase(disease_class=c, situation=s, score=round(float(sc), 3))
            for c, s, sc in cases
        ],
        my_past=[
            GroundingPast(disease_class=c, situation=_dec(s), score=round(float(sc), 3))
            for c, s, sc in past
        ],
        knowledge=[
            GroundingKnowledge(question=q, answer=a, score=round(float(sc), 3)) for q, a, sc in qa
        ],
        mentioned_symptoms=[m[1] for m in mentioned],
        follow_up=followup,
    )
