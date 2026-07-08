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
import logging
from typing import Any
from uuid import UUID

from contracts.chat import (
    Grounding,
    GroundingCase,
    GroundingFollowup,
    GroundingKnowledge,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.rag.crypto import decrypt_str, session_insights_aad
from src.rag.embed import embed_query, to_pgvector

logger = logging.getLogger(__name__)


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


def _dec(v: Any, *, aad: bytes | None = None) -> str | None:
    """situation_encrypted(BYTEA) 복호화 (S2, ADR-013).

    이전에는 여기서 그대로 utf-8 decode(errors='ignore')를 해 암호문이 깨진
    텍스트로 LLM 프롬프트 경로까지 흘러갈 수 있었다(S2 결함). 이제는 실제로
    복호화하며, ENCRYPTION_KEY 미설정이거나 복호화가 실패하면(태그 불일치 등)
    해당 필드를 명시적으로 제외한다(None) — 암호문이 절대 LLM 경로로 유입되지
    않는다. `rag/tooling/load_simulations.py`가 아직 이 필드를 평문 바이트로
    적재하는 레거시 코퍼스가 있다면, 그 행들도 여기서 복호화 실패로 제외된다
    (알려진 상호작용 — 로더 정합화는 이 파일의 범위 밖).
    """
    if v is None:
        return None
    try:
        return decrypt_str(bytes(v), aad=aad)
    except Exception as exc:
        logger.warning(
            "rag.retrieval.situation_decrypt_failed — field excluded from response "
            "(ENCRYPTION_KEY missing/mismatched or ciphertext malformed): %s", exc,
        )
        return None


async def retrieve_grounding(
    db: AsyncSession, utterance: str, *, patient_id: UUID | None = None, k: int = 3
) -> dict[str, Any]:
    """사용자 발화 → grounding(dict). embed_query는 동기(Upstage SDK)라 thread로 오프로드.

    my_past만 공유 계약(GroundingPast) 밖 필드(phq9/gad7/자살플래그/slots)를 담으므로
    계약을 건드리지 않고 dict로 반환 — 나머지 슬롯은 계약 모델로 만들어 model_dump."""
    qlit = to_pgvector(await asyncio.to_thread(embed_query, utterance))

    cases = await _topk(db, "case_card", "class, situation", {"q": qlit}, k)
    qa = await _topk(db, "qa", "question, answer", {"q": qlit}, k)

    past: list[Any] = []
    if patient_id is not None:
        past = await _topk(
            db,
            "session_insights",
            # session_id는 situation_encrypted 복호화 AAD 계산용으로만 select(S2).
            # FK(patient_id)·임베딩·미사용 컬럼(flags/intervention/embedding_model/
            # flag_source/generated_at)은 제외. slots(JSONB)에 임상 슬롯 전체가 들어있음.
            "session_id, class, situation_encrypted, phq9_score, gad7_score, "
            "flag_suicidal, slots",
            {"q": qlit, "pid": str(patient_id)},
            k,
            where="AND patient_id = :pid",
        )

    mentioned = await _detect_symptoms(db, utterance)
    followup = await _followup(db, [m[0] for m in mentioned])

    # my_past를 제외한 슬롯은 공유 계약 모델로 만들고 dict로 직렬화.
    grounding = Grounding(
        similar_cases=[
            GroundingCase(disease_class=c, situation=s, score=round(float(sc), 3))
            for c, s, sc in cases
        ],
        knowledge=[
            GroundingKnowledge(question=q, answer=a, score=round(float(sc), 3)) for q, a, sc in qa
        ],
        mentioned_symptoms=[m[1] for m in mentioned],
        follow_up=followup,
    )
    payload = grounding.model_dump()
    # my_past는 계약(GroundingPast: disease_class/situation/score) 밖 필드까지 담아
    # ai-server 로컬에서 dict로 확장(공유 contracts.chat 미변경).
    payload["my_past"] = [
        {
            "disease_class": c,
            "situation": _dec(s, aad=session_insights_aad(str(sid), "situation")),
            "score": round(float(sc), 3),
            "phq9_score": phq,
            "gad7_score": gad,
            "flag_suicidal": sui,
            "slots": slots,
        }
        for sid, c, s, phq, gad, sui, slots, sc in past
    ]
    return payload


# ── F2 Stage 1 — DomainInference 코드 검색 (PLAN-2026-W28-C C-2/C-3) ────────


async def retrieve_domain_chunks(
    db: AsyncSession, queries: list[str], *, k: int = 3
) -> list[dict[str, Any]]:
    """F2 Stage 1: chief_complaint/HPI/risk 슬롯 문자열 → rag.case_card + rag.qa top-k.

    chunk_id(`case_card:{card_id}`/`qa:{qa_id}`) + 본문 텍스트를 함께 반환한다 —
    REV-006 issue #1(rag_chunk evidence의 quote 내용 검증)이 나중에 실제 청크
    텍스트와 대조할 수 있도록, 감사 재현에 필요한 본문을 여기서부터 보존한다.
    ontology(symptom/disease follow_up 그래프)는 F2 스코프에 포함하지 않는다
    (follow_up은 chat 실시간 grounding 전용 — F2는 domain 추론이 목적).

    개별 쿼리/테이블 실패는 상위(f2.py)의 llm_only 강등 정책에 맡긴다 — 이
    함수 자체는 예외를 삼키지 않는다(호출자가 ANY failure를 잡아 강등).
    """
    seen: dict[str, dict[str, Any]] = {}
    for q in queries:
        if not q or not q.strip():
            continue
        qlit = to_pgvector(await asyncio.to_thread(embed_query, q))

        cases = await _topk(db, "case_card", "card_id, class, situation", {"q": qlit}, k)
        for card_id, cls, situation, score in cases:
            cid = f"case_card:{card_id}"
            seen.setdefault(cid, {
                "chunk_id": cid,
                "source_type": "case_card",
                "text": situation,
                "score": round(float(score), 3),
                "meta": {"class": cls},
            })

        qas = await _topk(db, "qa", "qa_id, specialty, question, answer", {"q": qlit}, k)
        for qa_id, specialty, question, answer, score in qas:
            cid = f"qa:{qa_id}"
            seen.setdefault(cid, {
                "chunk_id": cid,
                "source_type": "qa",
                "text": f"Q: {question}\nA: {answer}",
                "score": round(float(score), 3),
                "meta": {"specialty": specialty},
            })

    return list(seen.values())
