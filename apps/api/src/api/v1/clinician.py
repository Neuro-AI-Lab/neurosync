"""GET /api/v1/clinician/* — PRD §5.4 의료진 dashboard read-only.

All reads write an `audit_logs` row with the actor (clinician), action, and
target id. PRD §A "모든 민감정보 접근은 로그로 남긴다".
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.deps import require_role
from src.db import get_session
from src.models.audit_log import AuditLog
from src.models.user import User
from src.services.clinician import (
    get_patient_detail,
    get_session_detail,
    list_patients,
)

router = APIRouter(prefix="/clinician", tags=["clinician"])

# Reusable dependency: any clinician seat (clinician / org_admin / super_admin).
require_clinician = require_role("clinician", "org_admin", "super_admin")


async def _audit(
    db: AsyncSession,
    *,
    actor: User,
    request: Request,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id,
            actor_role=actor.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.get("/patients", response_model=dict)
async def list_patients_endpoint(
    request: Request,
    actor: Annotated[User, Depends(require_clinician)],
    db: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    items = await list_patients(db, limit=limit)
    await _audit(
        db,
        actor=actor,
        request=request,
        action="clinician.patients.list",
        resource_type="patient_list",
    )
    await db.commit()
    return {
        "success": True,
        "data": [item.model_dump(by_alias=True, mode="json") for item in items],
    }


@router.get("/patients/{patient_id}", response_model=dict)
async def get_patient_endpoint(
    patient_id: UUID,
    request: Request,
    actor: Annotated[User, Depends(require_clinician)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    detail = await get_patient_detail(db, patient_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PATIENT_NOT_FOUND", "message": "환자를 찾을 수 없어요."},
        )
    await _audit(
        db,
        actor=actor,
        request=request,
        action="clinician.patient.read",
        resource_type="patient",
        resource_id=patient_id,
    )
    await db.commit()
    return {"success": True, "data": detail.model_dump(by_alias=True, mode="json")}


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session_endpoint(
    session_id: UUID,
    request: Request,
    actor: Annotated[User, Depends(require_clinician)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    detail = await get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )
    await _audit(
        db,
        actor=actor,
        request=request,
        action="clinician.session.read",
        resource_type="session",
        resource_id=session_id,
    )
    await db.commit()
    return {"success": True, "data": detail.model_dump(by_alias=True, mode="json")}
