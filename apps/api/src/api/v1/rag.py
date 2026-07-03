"""POST /api/v1/rag/grounding — RAG grounding 조회 (읽기 전용, 진단/테스트용).

chat 파이프라인이 매 턴 부르는 retrieve_grounding를 HTTP로 한 번 더 노출하는
얇은 래퍼. 흐름·스키마·계약 변경 없음. ai-server는 안 탐 (RAG는 api 안에서 끝남).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.deps import require_role
from src.db import get_session
from src.models.user import User
from src.rag.retrieval import retrieve_grounding

router = APIRouter(prefix="/rag", tags=["rag"])


class GroundingProbeIn(BaseModel):
    utterance: str = Field(min_length=1, description="사용자 발화")
    k: int = Field(default=3, ge=1, le=10, description="슬롯별 top-k")
    model_config = ConfigDict(extra="forbid")


@router.post("/grounding")
async def probe_grounding(
    body: GroundingProbeIn,
    _: Annotated[User, Depends(require_role("clinician"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    grounding = await retrieve_grounding(db, body.utterance, k=body.k)
    return {"success": True, "data": grounding.model_dump(mode="json")}
