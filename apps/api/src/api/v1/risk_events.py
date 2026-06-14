"""PATCH /api/v1/risk_events/:id — FR-011/022.

The patient acknowledges a risk event from the /emergency screen, recording
whether they are alone. Only the owning patient may patch their own event.
Every write is audited (PRD §A).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.deps import require_role
from src.db import get_session
from src.models.audit_log import AuditLog
from src.models.session import RiskEvent
from src.models.user import User
from src.schemas.risk_event import RiskEventAckOut, RiskEventPatch

router = APIRouter(prefix="/risk_events", tags=["risk_events"])


@router.patch("/{risk_event_id}", response_model=dict)
async def acknowledge_risk_event(
    risk_event_id: UUID,
    body: RiskEventPatch,
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    row = await db.execute(
        select(RiskEvent).where(RiskEvent.id == risk_event_id)
    )
    event = row.scalar_one_or_none()
    # 404 (not 403) when it isn't the patient's own event — don't disclose
    # existence of other patients' risk events.
    if event is None or event.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RISK_EVENT_NOT_FOUND",
                "message": "위험 이벤트를 찾을 수 없어요.",
            },
        )

    event.alone_status = body.alone_status
    event.acknowledged_at = datetime.now(UTC)
    # Preserve terminal states (resolved/dismissed); only lift 'detected'.
    if event.status == "detected":
        event.status = "acknowledged"

    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="risk_event.acknowledge",
            resource_type="risk_event",
            resource_id=event.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            audit_metadata={"alone_status": body.alone_status},
        )
    )
    await db.commit()
    await db.refresh(event)

    return {
        "success": True,
        "data": RiskEventAckOut(
            id=event.id,
            status=event.status,
            alone_status=event.alone_status,
            acknowledged_at=event.acknowledged_at,
        ).model_dump(by_alias=True, mode="json"),
    }
