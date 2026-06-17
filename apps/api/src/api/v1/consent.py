"""POST /api/v1/consent/voice — toggle voice (STT) consent (FR-034).

Consent is append-only (PRD §5.2): toggling appends a NEW snapshot carrying the
latest base consents with `voice` updated, so the history is preserved.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.deps import require_role
from src.db import get_session
from src.models.audit_log import AuditLog
from src.models.consent import ConsentSnapshot
from src.models.user import User
from src.schemas.stt import VoiceConsentIn, VoiceConsentOut

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/voice")
async def set_voice_consent(
    body: VoiceConsentIn,
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    latest_row = await db.execute(
        select(ConsentSnapshot)
        .where(ConsentSnapshot.user_id == patient.id)
        .order_by(desc(ConsentSnapshot.collected_at))
        .limit(1)
    )
    latest = latest_row.scalar_one_or_none()
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NO_CONSENT_SNAPSHOT",
                "message": "기존 동의 정보가 없어요.",
            },
        )

    snapshot = ConsentSnapshot(
        user_id=patient.id,
        tos=latest.tos,
        privacy=latest.privacy,
        sensitive=latest.sensitive,
        risk_notification=latest.risk_notification,
        voice=body.voice,
        guardian_consent=latest.guardian_consent,
        tos_version=latest.tos_version,
        privacy_version=latest.privacy_version,
        collected_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(snapshot)
    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="consent.voice.update",
            resource_type="consent_snapshot",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            audit_metadata={"voice": body.voice},
        )
    )
    await db.commit()
    await db.refresh(snapshot)
    return {
        "success": True,
        "data": VoiceConsentOut(
            voice=snapshot.voice, consent_snapshot_id=snapshot.id
        ).model_dump(by_alias=True, mode="json"),
    }
