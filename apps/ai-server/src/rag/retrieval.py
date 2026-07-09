"""RAG 런타임 검색 (async) — grounding 4슬롯 생성.

apps/api(WS chat)가 사용자 발화로 호출 → shared-contracts `Grounding` 반환 →
ChatRequest.grounding 으로 ai-server에 주입.

슬롯:
  1) similar_cases  남의 유사사례 (case_card)       — 벡터
  2) my_past        내 과거 (session_insights)        — 벡터 + patient 필터
  3) knowledge      정신과 지식 (qa)                  — 벡터
  4) follow_up      발화 임베딩→증상 NN → IDF 가중 후보질병 → 정보이득 후속질문

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

# ── follow_up (증상→후보질병→후속질문) 튜닝 상수 ──────────────────────────
# ① 증상 감지: 발화 임베딩과 rag.symptom.embedding 코사인 유사도 컷 / 최대 개수.
#    symptom 임베딩이 solar 'passage' 모델 + 짧은 증상명이라 절대 유사도가 낮은 regime
#    (실증상 0.18~0.35, 노이즈 0.11~0.14). 실발화 4종 분포 기준 0.18로 튜닝 —
#    실증상은 잡고 오탐(예: "손이 가요"→"자해" 0.159)은 배제. 코퍼스 갱신 시 재튜닝.
_SYMPTOM_SIM_THRESHOLD = 0.18
_SYMPTOM_TOPK = 8
# ②③ IDF 가중 후보질병 top-N / 반환할 후속질문 개수.
_DISEASE_TOPN = 5
_FOLLOWUP_Q = 3
# 변별력과 무관하게 최우선으로 물어야 하는 안전 증상(ontology BUCKETS의 canonical name).
_SAFETY_FLAGS = {"suicidal"}


def _rank_questions(rows: list[tuple[str, str]], n_q: int) -> list[str]:
    """③ 후속질문 확정: 안전 증상(자살/자해)을 정보이득과 무관하게 최우선 배치하고,
    나머지는 split_dist 오름차순(=정보이득 순, rows는 이미 정렬됨)으로 채워 n_q개.

    rows: [(name, name_ko)] — split_dist ASC로 정렬된 미관찰 후보증상."""
    safety = [nko or name for name, nko in rows if name in _SAFETY_FLAGS]
    rest = [nko or name for name, nko in rows if name not in _SAFETY_FLAGS]
    return (safety + rest)[:n_q]


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


async def _detect_symptoms(
    db: AsyncSession, qlit: str, *, threshold: float, k: int
) -> list[tuple[int, str, float]]:
    """① 발화 임베딩(qlit) 최근접 증상 top-k (코사인 유사도 ≥ threshold).

    이전 구현은 name_ko/synonyms 부분문자열 매칭이라 패러프레이즈·어미변화를 놓치고
    부정("불안하진 않아요")도 오탐했다. 이제 rag.symptom.embedding과의 벡터 유사도로
    의미 기반 감지 — LLM/에이전트 불필요, 발화 임베딩(qlit)은 상위에서 재사용."""
    rows = (
        await db.execute(
            text(
                """SELECT symptom_id, name_ko,
                          1 - (embedding <=> CAST(:q AS vector)) AS sim
                   FROM rag.symptom
                   WHERE embedding IS NOT NULL
                     AND 1 - (embedding <=> CAST(:q AS vector)) >= :th
                   ORDER BY embedding <=> CAST(:q AS vector)
                   LIMIT :k"""
            ),
            {"q": qlit, "th": threshold, "k": k},
        )
    ).fetchall()
    return [(sid, nko, round(float(sim), 3)) for sid, nko, sim in rows]


async def _followup(
    db: AsyncSession, present_ids: list[int], *, topn: int, n_q: int
) -> GroundingFollowup | None:
    """② IDF 가중 후보질병 top-N → ③ 후보를 절반으로 가르는 미관찰 증상(정보이득)."""
    if not present_ids:
        return None
    # ② IDF(specificity) 가중합으로 후보질병 랭킹. 흔한 증상(많은 질병에 걸림)은
    #    ln(N/df)가 작아 약하게, 희귀 증상은 강하게 → 단순 overlap 개수보다 변별력↑.
    cand = (
        await db.execute(
            text(
                """WITH w AS (
                     SELECT symptom_id,
                            ln((SELECT count(*) FROM rag.disease)::float
                               / count(*) OVER (PARTITION BY symptom_id)) AS weight
                     FROM rag.disease_symptom)
                   SELECT d.disease_id, d.name_ko, sum(w.weight) AS score
                   FROM rag.disease_symptom ds JOIN w USING (symptom_id)
                   JOIN rag.disease d USING (disease_id)
                   WHERE ds.symptom_id = ANY(:ids)
                   GROUP BY d.disease_id, d.name_ko
                   ORDER BY score DESC, d.disease_id
                   LIMIT :n"""
            ),
            {"ids": present_ids, "n": topn},
        )
    ).fetchall()
    if not cand:
        return None
    candidate_disease = cand[0][1]  # top-1 name_ko → 계약 필드
    cand_ids = [row[0] for row in cand]
    # ③ top-N 후보를 가장 균등하게 가르는(비율→0.5) 미관찰 증상 = 정보이득 최대 질문.
    #    LIMIT는 걸지 않고 split_dist 정렬만 — 안전증상 오버라이드를 _rank_questions에서.
    rows = (
        await db.execute(
            text(
                """SELECT s.name, s.name_ko,
                          abs(count(*)::float / :ncand - 0.5) AS split_dist
                   FROM rag.disease_symptom ds JOIN rag.symptom s USING (symptom_id)
                   WHERE ds.disease_id = ANY(:cids) AND ds.symptom_id <> ALL(:obs)
                   GROUP BY s.symptom_id, s.name, s.name_ko
                   ORDER BY split_dist ASC, s.symptom_id"""
            ),
            {"ncand": len(cand_ids), "cids": cand_ids, "obs": present_ids},
        )
    ).fetchall()
    return GroundingFollowup(
        candidate_disease=candidate_disease,
        follow_up_symptoms=_rank_questions([(r[0], r[1]) for r in rows], n_q),
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

    mentioned = await _detect_symptoms(
        db, qlit, threshold=_SYMPTOM_SIM_THRESHOLD, k=_SYMPTOM_TOPK
    )
    followup = await _followup(
        db, [m[0] for m in mentioned], topn=_DISEASE_TOPN, n_q=_FOLLOWUP_Q
    )

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
