"""POST /ai/rag/grounding — 발화 → RAG grounding (ai-server 내부에서 DB 직접 조회).

RETIRED — NOT DELETED (ADR-017/REV-013, 2026-07-09). This router is no longer
mounted in `src.main.app` — RAG HTTP serving is now a permanent, categorical
out-of-scope decision (in-process only, now and at deployment; see ADR-017).
`rag_chat.py` no longer calls this route either — it now calls
`retrieve_grounding()` in-process, mirroring `src/f2.py:176-180`'s pattern.

This file is kept in the tree (not deleted) so the auth-gated HTTP contract
is still readable/testable in isolation (`tests/rag/test_route_auth.py` now
mounts this router into a standalone app, not `src.main.app`). Remounting
this router in `main.py` requires a fresh ADR + VAL-005 reopening review —
unauthorized re-open is prohibited (REV-013 §2's explicit reversal
safeguard). If remounted, `src/rag/auth.py`'s `NS_RAG_API_KEY` fail-closed
bearer auth MUST stay wired via this router's `dependencies=[...]`.

Historical docstring (pre-retirement): grounding을 HTTP로 노출하는 엔드포인트.
과거 apps/api의 POST /rag/grounding(삭제됨)을 대체 — ai-server가 스스로
retrieve_grounding()을 실행했다. patient_id를 넘겨야 my_past(내 과거)가 조회된다.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.dependencies import get_sessionmaker
from src.rag.auth import require_rag_api_key
from src.rag.retrieval import retrieve_grounding

logger = logging.getLogger(__name__)

# ADR-013/VAL-005: bearer-token auth applied to THIS router only (src/rag/auth.py).
router = APIRouter(
    prefix="/ai/rag", tags=["rag"], dependencies=[Depends(require_rag_api_key)]
)


class GroundingQuery(BaseModel):
    """발화 + (선택)patient_id → grounding 요청."""

    utterance: str = Field(min_length=1)
    patient_id: str | None = Field(default=None, description="환자 UUID. 없으면 my_past 미조회.")
    k: int = Field(default=3, ge=1, le=10, description="슬롯별 top-k")


# my_past가 공유 계약(Grounding) 밖 필드(slots 등)를 담으므로 response_model 미지정 →
# retrieve_grounding이 만든 dict를 그대로 직렬화(계약은 나머지 슬롯 생성에만 사용).
@router.post("/grounding")
async def grounding(q: GroundingQuery) -> dict:
    pid: UUID | None = None
    if q.patient_id:
        try:
            pid = UUID(q.patient_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="patient_id가 UUID 형식이 아닙니다"
            ) from exc

    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as db:
            return await retrieve_grounding(db, q.utterance, patient_id=pid, k=q.k)
    except Exception as exc:  # noqa: BLE001 — DB/임베딩 실패를 500으로 명시 반환
        logger.warning("rag.grounding.failed", exc_info=True)
        raise HTTPException(status_code=500, detail=f"grounding 실패: {exc}") from exc
