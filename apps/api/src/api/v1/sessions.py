"""POST /sessions + WS /sessions/:id/chat.

Phase 1a Day 8+ — establishes the WebSocket gateway, runs every user message
through the AI Safety classifier, and emits `risk:detected` when warranted.

Authentication / authorization (PRD §5.1 C-7):
- Token MUST arrive in the `auth:connect` initial frame payload — never in
  URL query / Sec-WebSocket-Protocol headers.
- 5-second handshake budget enforced via anyio.fail_after; timeout closes
  with code 1008 explicitly.
- Origin header validated against `settings.cors_ws_origins`.

Idempotency (C-2 hardening):
- Per-connection bounded LRU (`OrderedDict`) caps at `settings.ws_idempotency_cache_size`.
- Replays of the same key get the cached ack back so the client stays in sync.

Conservative classifier fallback (M-1):
- AI server failure → `handle_unavailable_classifier` writes a `pending_reclassify`
  RiskEvent and replies with a self-hotline payload (consent-aware). Silence is
  unacceptable in a life-safety domain.

Per-message AAD (M-3):
- `messages.content` AAD includes the message UUID, not just the session, so
  cross-record swaps fail GCM verification.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import anyio
from contracts.safety import SafetyRequest
from contracts.survey_plan import SurveyPlanRequest
from contracts.temporal import (
    Direction,
    TemporalPlotPoint,
    TemporalSummarizeResponse,
)
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from src.core.config import Settings, get_settings
from src.core.deps import require_role
from src.core.encryption import decrypt_str, encrypt_str
from src.core.file_security import FileSecurityError, validate_upload
from src.core.security import TokenError, decode_token
from src.db import SessionLocal, get_session
from src.models.audit_log import AuditLog
from src.models.handoff import HandoffReport
from src.models.patient_profile import PatientProfile
from src.models.questionnaire import QuestionnaireResult
from src.models.session import Message, Session
from src.models.user import User
from src.schemas.handoff import SubmitAccepted
from src.schemas.questionnaire import QuestionnaireResultOut, QuestionnaireSubmit
from src.schemas.session import (
    SessionListItemOut,
    SessionOut,
    WSAuthConnect,
    WSUserMessage,
)
from src.services.ai_client import AIClient, AIClientError, get_ai_client
from src.services.chat import respond as chat_turn

# ISS-022: shared org-access rule (handoff.py도 동일 임포트)
from src.services.clinician import _can_access_patient
from src.services.domain_routing import infer_instrument_with_caveat
from src.services.handoff import (
    build_report_response,
    create_pending_report,
    generate_report_task,
)
from src.services.questionnaire import AI_SCALE_NAME, QuestionnaireError, upsert_result
from src.services.safety import (
    handle_safety_result,
    handle_unavailable_classifier,
    latest_consent_snapshot,
    to_safety_assessment,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

CONTEXT_PREV_TURNS = 5


# ────────── REST ──────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    sess = Session(patient_id=patient.id, status="in_progress")
    db.add(sess)
    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="session.create",
            resource_type="session",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    await db.refresh(sess)
    return {
        "success": True,
        "data": SessionOut(
            session_id=sess.id, status=sess.status, created_at=sess.created_at
        ).model_dump(by_alias=True, mode="json"),
    }


SESSIONS_LIST_MAX = 100


@router.get("")
async def list_sessions(
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """S09 records (기록 조회) — the patient's own session history.

    Own-data-only by construction (`Session.patient_id == patient.id` in the
    query itself, not a post-filter) — never leaks another patient's
    sessions. `has_report` is a plain existence check against
    `handoff_reports`, independent of report `status` (a `generating`/
    `failed` report still counts as "exists" for this list view; the client
    resolves the actual phase via the existing `/report/status` route when
    the user opens a record).
    """
    rows = await db.execute(
        select(Session)
        .where(Session.patient_id == patient.id)
        .order_by(Session.created_at.desc())
        .limit(SESSIONS_LIST_MAX)
    )
    sessions = list(rows.scalars().all())
    if not sessions:
        return {"success": True, "data": {"sessions": []}}

    session_ids = [s.id for s in sessions]
    report_rows = await db.execute(
        select(HandoffReport.session_id).where(HandoffReport.session_id.in_(session_ids))
    )
    session_ids_with_report = {row[0] for row in report_rows.all()}

    items = [
        SessionListItemOut(
            session_id=s.id,
            status=s.status,
            created_at=s.created_at,
            progress_ratio=s.progress_ratio,
            has_report=s.id in session_ids_with_report,
        ).model_dump(by_alias=True, mode="json")
        for s in sessions
    ]
    return {"success": True, "data": {"sessions": items}}


async def _owned_in_progress_session(
    db: AsyncSession, *, session_id: UUID, patient_id: UUID
) -> Session:
    """Load a session the patient owns, or raise 404/409.

    Patient-facing writes (questionnaires, submit) are only valid while the
    session is still `in_progress` — FR-010 freezes the session after submit.
    """
    row = await db.execute(select(Session).where(Session.id == session_id))
    sess = row.scalar_one_or_none()
    if sess is None or sess.patient_id != patient_id:
        # Don't leak existence of other patients' sessions.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )
    if sess.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SESSION_NOT_EDITABLE",
                "message": "이미 제출된 문진은 수정할 수 없어요.",
            },
        )
    return sess


@router.post("/{session_id}/questionnaires", status_code=status.HTTP_201_CREATED)
async def submit_questionnaire(
    session_id: UUID,
    body: QuestionnaireSubmit,
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    ai_client: Annotated[AIClient, Depends(get_ai_client)],
) -> dict:
    await _owned_in_progress_session(
        db, session_id=session_id, patient_id=patient.id
    )

    # AUDIT-C 절사점은 성별 의존(한국 기준 여성이 더 낮음) — 프로필 gender를
    # 채점에 전달한다. 없으면 "unknown". male/female만 인정.
    gender_row = await db.execute(
        select(PatientProfile.gender).where(PatientProfile.user_id == patient.id)
    )
    gender = gender_row.scalar_one_or_none()
    patient_sex = gender if gender in ("male", "female") else "unknown"

    try:
        # v3 FR-040 — 채점은 ai-server 결정론적 채점기에 위임(AUDIT-C 한국 절사점,
        # PHQ-9 9번 critical item). 장애 시 서비스 내부에서 로컬 컷오프로 폴백한다.
        result, critical = await upsert_result(
            db,
            session_id=session_id,
            qtype=body.type,
            answers=body.answers,
            ai_client=ai_client,
            patient_sex=patient_sex,
        )
    except QuestionnaireError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="session.questionnaire.submit",
            resource_type="questionnaire_result",
            resource_id=result.id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            audit_metadata={"type": body.type, "session_id": str(session_id)},
        )
    )
    await db.commit()
    await db.refresh(result)
    return {
        "success": True,
        "data": QuestionnaireResultOut(
            id=result.id,
            type=result.type,
            total_score=result.total_score,
            severity=result.severity,
            completed_at=result.completed_at,
            critical_item_positive=critical,
        ).model_dump(by_alias=True, mode="json"),
    }


def _message_aad(session_id: UUID, message_id: UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


# 도메인 추정 근거로 쓸 최근 환자 발화 상한 (모바일 5초 상한 보호).
DOMAIN_INFER_MAX_TURNS = 20


@router.post("/{session_id}/domain/infer")
async def infer_domain(
    session_id: UUID,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    ai_client: Annotated[AIClient, Depends(get_ai_client)],
) -> dict:
    """v3 FR-039 — 대화 종료 후 top1 문진 도구를 결정한다 (§6-A 프록시).

    응답은 도구 ID 하나뿐이다. 추정된 질환/도메인 문자열은 절대 내려보내지
    않는다 (v3 원칙 1 / NFR v3-2) — 클라이언트가 화면에 병명을 띄울 수 없도록
    애초에 값을 주지 않는 것이 유일하게 믿을 수 있는 방법이다.

    라우팅은 실패하지 않는다. 어떤 오류든 폴백 문진으로 응답한다.
    """
    sess = await _owned_in_progress_session(
        db, session_id=session_id, patient_id=patient.id
    )

    # 최근 발화만 근거로 쓴다 — 모바일 5초 상한 안에서 복호화가 끝나야 하므로
    # 무제한 로딩을 막는다(긴 세션 → 타임아웃 → 안전 방향인 폴백이지만 피한다).
    msg_rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .limit(DOMAIN_INFER_MAX_TURNS)
    )
    recent = list(reversed(msg_rows.scalars().all()))
    turns: list[tuple[int, str]] = []
    decrypt_failures = 0
    for i, m in enumerate(recent, start=1):
        try:
            content = decrypt_str(m.content_encrypted, aad=_message_aad(session_id, m.id))
        except Exception:
            decrypt_failures += 1
            continue
        if content.strip():
            turns.append((i, content))
    if decrypt_failures:
        # 내용은 남기지 않는다 — 키 오설정 등 관측성 확보용 카운트만.
        logger.warning(
            "domain/infer: %d message(s) failed to decrypt (session=%s)",
            decrypt_failures,
            session_id,
        )

    routing = await infer_instrument_with_caveat(
        ai_client=ai_client,
        session_id=session_id,
        turns=turns,
        clinical_slots=sess.clinical_slots or {},
        # BUG-059: previously never threaded, so `DomainInferRequest.
        # crisis_triggered` sent to ai-server was always False. Same value
        # already forwarded for the survey/plan `crisis_triggered` below
        # (`sess.clinical_escalation_required`, the ADR-044 screening
        # backstop signal) — ai-server's live domain route does not
        # reproject this field or use it as selection evidence, so this is
        # additive/inert today, not a behavior change.
        crisis_triggered=bool(sess.clinical_escalation_required),
    )
    instrument = routing.instrument

    # PLAN-2026-W30-INTEG P3-1(a)/(c) — F2 routing -> F3 plan. Best-effort: a
    # plan-call failure never blocks the patient-facing instrument response
    # (same "라우팅은 실패하지 않는다" posture as infer_instrument itself).
    plan_data: dict[str, Any] | None = None
    try:
        plan_response = await ai_client.survey_plan(
            SurveyPlanRequest(
                recommended_questionnaire=AI_SCALE_NAME.get(instrument),
                recommendation_caveat=routing.caveat,
                crisis_triggered=bool(sess.clinical_escalation_required),
            )
        )
    except AIClientError as exc:
        logger.warning(
            "survey plan call failed, patient response stays instrument-only (session=%s): %s",
            session_id,
            exc,
        )
    else:
        if routing.caveat:
            # Clinician/audit-facing only (P3-0 consult safety constraint) —
            # persisted to audit_logs, never returned in this endpoint's
            # patient-facing response body below.
            db.add(
                AuditLog(
                    actor_id=patient.id,
                    actor_role="patient",
                    action="survey.plan.proxy_caveat",
                    resource_type="session",
                    resource_id=session_id,
                    audit_metadata={"scale": plan_response.scale, "caveat": routing.caveat},
                )
            )
            await db.commit()
            logger.info(
                "survey plan: proxy caveat recorded for clinician/audit review "
                "(session=%s, scale=%s)",
                session_id,
                plan_response.scale,
            )
        plan_data = plan_response.model_dump(mode="json")
        # Never forward the caveat itself to the patient survey UI (safety constraint).
        plan_data.pop("recommendation_caveat", None)

    data: dict[str, Any] = {"instrument": instrument}
    if plan_data is not None:
        data["plan"] = plan_data
    return {"success": True, "data": data}


@router.post("/{session_id}/documents/ocr", status_code=status.HTTP_201_CREATED)
async def parse_document(
    session_id: UUID,
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    ai_client: Annotated[AIClient, Depends(get_ai_client)],
    settings: Annotated[Settings, Depends(get_settings)],
    document: Annotated[UploadFile, File()],
    document_type_hint: Annotated[str, Form()] = "unknown",
) -> dict:
    """v3 FR-048 — 대화 중 첨부한 처방전/진단서를 OCR로 구조화한다.

    플랫폼이 파일을 검증(FR-028)한 뒤 ai-server /ai/ocr/parse로 프록시한다.
    확정 반영은 클라이언트가 확인 화면에서 [확인 완료]를 눌러야 이뤄지므로,
    이 엔드포인트는 추출만 하고 리포트에 자동 반영하지 않는다.
    """
    await _owned_in_progress_session(db, session_id=session_id, patient_id=patient.id)

    data = await document.read()
    # FR-028 — 크기·형식·매직넘버 검증. 정규 content-type을 ai-server로 넘긴다.
    try:
        content_type = validate_upload(
            data,
            declared_content_type=document.content_type,
            max_bytes=settings.ocr_max_bytes,
        )
    except FileSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    try:
        result = await ai_client.ocr_parse(
            document=data,
            filename=document.filename or "document",
            content_type=content_type,
            session_id=str(session_id),
            patient_id=str(patient.id),
            document_type_hint=document_type_hint,
        )
    except AIClientError as exc:
        logger.warning("ocr parse failed (session=%s): %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "OCR_UNAVAILABLE",
                "message": "문서 인식에 실패했어요. 잠시 후 다시 시도해 주세요.",
            },
        ) from exc

    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="session.document.ocr",
            resource_type="session",
            resource_id=session_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            # 문서 내용은 로그에 남기지 않는다 — 유형/건수만.
            audit_metadata={
                "document_type": result.document_type,
                "low_confidence_count": len(result.low_confidence_items),
            },
        )
    )
    await db.commit()
    # by_alias — 모바일에는 camelCase로 (나머지 API와 동일 컨벤션).
    return {"success": True, "data": result.model_dump(by_alias=True, mode="json")}


HANDOFF_ESTIMATED_SECONDS = 30

require_clinician = require_role("clinician", "org_admin", "super_admin")


@router.post("/{session_id}/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_session(
    session_id: UUID,
    request: Request,
    background: BackgroundTasks,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """FR-010 — freeze the session and queue Handoff generation (FR-018).

    Generation runs out-of-band (BackgroundTasks now, Celery later); the client
    polls report status. 202 Accepted with the report id.
    """
    sess = await _owned_in_progress_session(
        db, session_id=session_id, patient_id=patient.id
    )
    sess.status = "submitted"
    sess.submitted_at = datetime.now(UTC)

    report = await create_pending_report(db, session_id=session_id)
    db.add(
        AuditLog(
            actor_id=patient.id,
            actor_role="patient",
            action="session.submit",
            resource_type="session",
            resource_id=session_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    # Kick the generation after the response is sent. Failures are captured
    # inside the task and surfaced via report.status = 'failed'.
    background.add_task(generate_report_task, session_id)

    return {
        "success": True,
        "data": SubmitAccepted(
            session_id=session_id,
            status="report_generating",
            report_id=report.id,
            estimated_seconds=HANDOFF_ESTIMATED_SECONDS,
        ).model_dump(by_alias=True, mode="json"),
    }


@router.get("/{session_id}/report/status", response_model=dict)
async def get_report_status(
    session_id: UUID,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """FR-013/018 — patient polls Handoff generation status.

    STATUS ONLY: the report body stays clinician-only (screen-spec §S-12), so
    this never returns report content — just generating / ready / failed.
    """
    srow = await db.execute(select(Session).where(Session.id == session_id))
    sess = srow.scalar_one_or_none()
    if sess is None or sess.patient_id != patient.id:
        # Don't leak existence of other patients' sessions.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )
    rrow = await db.execute(
        select(HandoffReport)
        .where(HandoffReport.session_id == session_id)
        .order_by(HandoffReport.created_at.desc())
        .limit(1)
    )
    report = rrow.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_NOT_FOUND", "message": "리포트를 찾을 수 없어요."},
        )
    return {
        "success": True,
        "data": {"status": report.status, "reportId": str(report.id)},
    }


# 환자에게 보여줄 수 있는 슬롯(자기보고 정보) 화이트리스트. AI 추정질환/신호강도/
# evidence 등 clinician 전용 필드는 절대 포함하지 않는다(비노출 원칙).
_PATIENT_SLOT_FIELDS: dict[str, str] = {
    "chief_complaint": "주호소",
    "history_of_present_illness": "현병력",
}
# 문진 심각도(내부 코드) → 환자용 순화 라벨.
_SEVERITY_KO = {
    "none": "해당 없음", "minimal": "최소", "mild": "경도",
    "moderate": "중등도", "moderately_severe": "중등도-중증", "severe": "중증",
}


@router.get("/{session_id}/report/summary", response_model=dict)
async def get_report_summary(
    session_id: UUID,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """FR-013/018 — 환자 본인용 문진 리포트 요약(F5 완료 후).

    clinician 전용 전체 핸드오프(AI 추정질환·신호강도·evidence 등)는 제외하고,
    **환자 자기보고 기반 정보**(주호소·현병력)와 **본인 설문 결과**(점수·심각도)만
    결정론적으로 반환한다. 리포트가 아직 준비되지 않았으면 status만 돌려준다.
    """
    srow = await db.execute(select(Session).where(Session.id == session_id))
    sess = srow.scalar_one_or_none()
    if sess is None or sess.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )
    rrow = await db.execute(
        select(HandoffReport)
        .where(HandoffReport.session_id == session_id)
        .order_by(HandoffReport.created_at.desc())
        .limit(1)
    )
    report = rrow.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_NOT_FOUND", "message": "리포트를 찾을 수 없어요."},
        )
    # 아직 생성 중/실패면 본문 없이 상태만 — 모바일이 폴링/에러 처리.
    if report.status != "ready":
        return {"success": True, "data": {"status": report.status, "ready": False}}

    slots = sess.clinical_slots or {}
    self_reported = [
        {"key": k, "label": label, "value": str(slots[k]).strip()}
        for k, label in _PATIENT_SLOT_FIELDS.items()
        if slots.get(k)
    ]
    q_rows = await db.execute(
        select(QuestionnaireResult).where(QuestionnaireResult.session_id == session_id)
    )
    questionnaires = [
        {
            "scale": _SCALE_NAME.get(q.type, q.type),
            "totalScore": q.total_score,
            "severity": q.severity,
            "severityLabel": _SEVERITY_KO.get(q.severity, q.severity),
        }
        for q in q_rows.scalars().all()
    ]
    return {
        "success": True,
        "data": {
            "status": report.status,
            "ready": True,
            "generatedAt": (
                report.generated_at.isoformat() if report.generated_at else None
            ),
            "selfReported": self_reported,
            "questionnaires": questionnaires,
            # 환자용 고지 — 진단이 아니라 의료진 상담 자료임을 명시.
            "disclaimer": (
                "이 요약은 자가보고와 설문을 정리한 자료로, 의학적 진단이 아닙니다. "
                "정확한 평가는 의료진과 상담해 주세요."
            ),
        },
    }


# 문진 type(DB) → ai-server 척도명. F4 입력은 "PHQ-9" 형식을 기대한다.
_SCALE_NAME = {"PHQ9": "PHQ-9", "GAD7": "GAD-7", "AUDITC": "AUDIT-C", "PHQ4": "PHQ-4"}


async def _session_scales(db: AsyncSession, session_id: UUID) -> dict[str, int]:
    """세션의 문진 결과를 {척도명: 총점} 맵으로. 표준 척도 점수만(환자 응답 기반)."""
    rows = await db.execute(
        select(QuestionnaireResult).where(QuestionnaireResult.session_id == session_id)
    )
    return {_SCALE_NAME.get(r.type, r.type): r.total_score for r in rows.scalars()}


def _pairwise_direction(current: dict[str, int], prior: dict[str, int]) -> Direction:
    """F4의 척도 방향 규칙과 동일한 결정론적 pairwise 판정. 표준 척도는 점수가
    **낮을수록 호전**(PHQ-9/GAD-7/AUDIT-C/PHQ-4). 두 방문에 공통으로 존재하는
    대표 척도(우선순위: PHQ-9 → GAD-7 → AUDIT-C → PHQ-4)의 총점 변화로 판정한다."""
    for scale in ("PHQ-9", "GAD-7", "AUDIT-C", "PHQ-4"):
        if scale in current and scale in prior:
            delta = current[scale] - prior[scale]
            if delta < 0:
                return "improved"
            if delta > 0:
                return "worsened"
            return "unchanged"
    return "unknown"


def _trend_point(scales: dict[str, int], date: str, label: str) -> TemporalPlotPoint:
    """모바일 추이 차트용 포인트. 표준 척도 점수(환자 본인 응답)만 싣는다."""
    return TemporalPlotPoint(
        date=date,
        phq9=scales.get("PHQ-9"),
        gad7=scales.get("GAD-7"),
        events=[label],
    )


@router.get("/{session_id}/report/trend", response_model=dict)
async def get_report_trend(
    session_id: UUID,
    actor: Annotated[
        User, Depends(require_role("patient", "clinician", "org_admin", "super_admin"))
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """수정 7 — 리포트 점수 추이 차트용 F4 종단 추론 (plot_data 바인딩).

    환자(본인 세션) 또는 의료진(소속 기관 환자, ISS-022 org-scope)이 조회한다.
    이번 세션과 같은 환자의 직전(더 이른) 세션 문진 점수를 비교해 방향과 시각화
    포인트를 돌려준다. 표준 척도 점수(환자 본인 응답 기반)만 시각화하고 AI 추정
    도메인·질환명은 넣지 않는다(NFR v3-2). 직전 세션이 없으면 첫 방문으로 처리.
    """
    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
    )
    srow = await db.execute(select(Session).where(Session.id == session_id))
    sess = srow.scalar_one_or_none()
    if sess is None:
        raise not_found
    # 권한: 환자는 본인 세션만, 의료진은 소속 기관 환자만. 어떤 실패든 404로 통일해
    # 다른 환자 세션의 존재를 노출하지 않는다.
    if actor.role == "patient":
        if sess.patient_id != actor.id:
            raise not_found
    else:
        hosp = await db.execute(
            select(PatientProfile.target_hospital_id).where(
                PatientProfile.user_id == sess.patient_id
            )
        )
        if not _can_access_patient(actor, hosp.scalar_one_or_none()):
            raise not_found
        # §6-B — 의료진은 전달된 리포트만 볼 수 있다. 미전달(또는 리포트 미생성)
        # 세션은 척도 점수 추이도 노출하지 않는다 — /report 게이트와 동일 불변식.
        drow = await db.execute(
            select(HandoffReport.delivered_at).where(
                HandoffReport.session_id == session_id
            )
        )
        if drow.scalar_one_or_none() is None:
            raise not_found

    current_scales = await _session_scales(db, session_id)

    # 같은 환자의 직전 세션 중 문진 결과가 있는 가장 최근 것을 이전 방문으로.
    prow = await db.execute(
        select(Session)
        .where(
            Session.patient_id == sess.patient_id,
            Session.created_at < sess.created_at,
        )
        .order_by(Session.created_at.desc())
    )
    prior_scales: dict[str, int] = {}
    prior_date = ""
    for prior in prow.scalars():
        scales = await _session_scales(db, prior.id)
        if scales:
            prior_scales = scales
            prior_date = prior.created_at.date().isoformat()
            break

    # 환자용 2점 추이는 자기 척도 점수의 결정론적 pairwise 비교로 계산한다(F4의
    # 척도 방향 규칙과 동일: 점수↓=호전). ai-server /ai/temporal/analyze는 세션당
    # 단일 척도·리치 입력(f3·sentiment)을 요구하는 N-세션 엔진이라, 환자 차트가
    # 필요로 하는 PHQ-9·GAD-7 동시 pairwise와 형태가 다르다 — cross-service 호출
    # 없이 여기서 산출해 502(폐기된 summarize 라우트 호출)를 제거한다.
    is_first_visit = not prior_scales
    current_date = sess.created_at.date().isoformat()

    plot_data: list[TemporalPlotPoint] = []
    if not is_first_visit:
        plot_data.append(_trend_point(prior_scales, prior_date, "이전 방문"))
    plot_data.append(_trend_point(current_scales, current_date, "이번 방문"))

    overall_direction: Direction = (
        "unknown" if is_first_visit else _pairwise_direction(current_scales, prior_scales)
    )

    result = TemporalSummarizeResponse(
        overall_direction=overall_direction,
        plot_data=plot_data,
        is_first_visit=is_first_visit,
    )
    # by_alias — 모바일에는 camelCase (나머지 API와 동일 컨벤션).
    return {"success": True, "data": result.model_dump(by_alias=True, mode="json")}


@router.post("/{session_id}/report/deliver", response_model=dict)
async def deliver_report(
    session_id: UUID,
    request: Request,
    patient: Annotated[User, Depends(require_role("patient"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """v3 수정 7 · §6-B — 환자가 보관 중인 리포트를 의료진에게 전달한다.

    submit 시점엔 리포트가 '보관'(delivered_at NULL)으로만 생성된다. 환자가 이
    엔드포인트를 호출해야 delivered_at이 채워지고 의료진 조회에 노출된다. 이미
    전달된 리포트는 멱등적으로 기존 전달 시각을 그대로 돌려준다(이중 전달 방지)."""
    srow = await db.execute(select(Session).where(Session.id == session_id))
    sess = srow.scalar_one_or_none()
    if sess is None or sess.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없어요."},
        )

    rrow = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = rrow.scalar_one_or_none()
    if report is None or report.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "REPORT_NOT_READY", "message": "아직 전달할 수 있는 리포트가 없어요."},
        )

    if report.delivered_at is None:
        report.delivered_at = datetime.now(UTC)
        db.add(
            AuditLog(
                actor_id=patient.id,
                actor_role="patient",
                action="session.report.deliver",
                resource_type="handoff_report",
                resource_id=report.id,
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()

    return {
        "success": True,
        "data": {"delivered": True, "deliveredAt": report.delivered_at.isoformat()},
    }


@router.get("/{session_id}/report", response_model=dict)
async def get_report(
    session_id: UUID,
    request: Request,
    actor: Annotated[User, Depends(require_clinician)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """FR-017/018 — clinician reads the Handoff report. Every read is audited."""
    report = await build_report_response(db, actor=actor, session_id=session_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REPORT_NOT_FOUND",
                "message": "리포트를 찾을 수 없어요.",
            },
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            actor_role=actor.role,
            action="clinician.report.read",
            resource_type="handoff_report",
            resource_id=report.report_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    return {
        "success": True,
        "data": report.model_dump(by_alias=True, mode="json"),
    }


# ────────── WebSocket helpers ──────────


async def _send_error_and_close(ws: WebSocket, code: int, reason: str) -> None:
    """Emit auth:error then close. Safe to call before/after accept()."""
    if ws.client_state == WebSocketState.CONNECTED:
        try:
            await ws.send_json({"type": "auth:error", "payload": {"code": reason}})
        except Exception:
            pass
    try:
        await ws.close(code=code)
    except Exception:
        pass


def _origin_allowed(ws: WebSocket, settings: Settings) -> bool:
    if "*" in settings.cors_ws_origins:
        return True  # dev only — validator blocks this in non-dev
    origin = ws.headers.get("origin")
    return origin is not None and origin in settings.cors_ws_origins


def _token_in_url_or_subprotocol(ws: WebSocket) -> bool:
    """PRD C-7: reject if token is smuggled outside the auth:connect frame."""
    if "token" in ws.query_params or "access_token" in ws.query_params:
        return True
    subprotocol = ws.headers.get("sec-websocket-protocol")
    if subprotocol and ("token" in subprotocol.lower() or "bearer" in subprotocol.lower()):
        return True
    return False


async def _await_auth_connect(
    ws: WebSocket, settings: Settings
) -> tuple[UUID, str] | None:
    """Wait for the initial auth:connect frame. Returns (user_id, role) or None.

    Closes the socket with 1008 on any failure (per PRD §5.1 C-7).
    """
    try:
        with anyio.fail_after(settings.ws_auth_handshake_seconds):
            try:
                raw = await ws.receive_json()
            except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
                await _send_error_and_close(ws, 1008, "AUTH_FRAME_INVALID")
                return None
    except TimeoutError:
        await _send_error_and_close(ws, 1008, "AUTH_TIMEOUT")
        return None

    try:
        frame = WSAuthConnect.model_validate(raw)
    except ValidationError:
        await _send_error_and_close(ws, 1008, "AUTH_FRAME_INVALID")
        return None

    try:
        claims = decode_token(
            frame.payload.access_token, expected_type="access", settings=settings
        )
    except TokenError as exc:
        await _send_error_and_close(ws, 1008, exc.code.value)
        return None

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError):
        await _send_error_and_close(ws, 1008, "TOKEN_INVALID")
        return None

    return user_id, str(claims.get("role", "patient"))


async def _persist_user_message(
    db: AsyncSession,
    *,
    session_id: UUID,
    content: str,
    input_modality: str,
    stt_transcription_id: UUID | None,
    settings: Settings,
) -> Message:
    # M-3: pre-generate id so AAD binds the ciphertext to this exact row.
    message_id = uuid.uuid4()
    msg = Message(
        id=message_id,
        session_id=session_id,
        role="user",
        content_encrypted=encrypt_str(
            content,
            aad=f"messages.content:{session_id}:{message_id}".encode(),
            settings=settings,
        ),
        input_modality=input_modality,
        stt_transcription_id=stt_transcription_id,
    )
    db.add(msg)
    await db.flush()
    return msg


async def _recent_message_ids(
    db: AsyncSession, session_id: UUID, limit: int
) -> list[UUID]:
    res = await db.execute(
        select(Message.id)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(res.scalars().all())
    rows.reverse()  # oldest-first for context
    return rows


# ────────── WebSocket route ──────────


@router.websocket("/{session_id}/chat")
async def session_chat(
    ws: WebSocket,
    session_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    ai_client: Annotated[AIClient, Depends(get_ai_client)],
) -> None:
    # M-5: Origin + URL token checks BEFORE accept so attackers don't even
    # get an open channel.
    if not _origin_allowed(ws, settings):
        await ws.close(code=1008)
        return
    if _token_in_url_or_subprotocol(ws):
        await ws.close(code=1008)
        return

    await ws.accept()
    auth = await _await_auth_connect(ws, settings)
    if auth is None:
        return
    user_id, role = auth

    # Authorize session — only the owner can open this WS. Also reload the
    # PRIOR turn's `session_state` (Phase 1, ADR-046 #2 wiring) so a
    # reconnect resumes from the persisted round-trip state rather than
    # always starting `None` again (`services/chat.py::respond` persists it
    # each turn via `Session.session_state`).
    async with SessionLocal() as db:
        owner_row = await db.execute(
            select(Session.patient_id, Session.session_state).where(
                Session.id == session_id
            )
        )
        owner_row_result = owner_row.one_or_none()
        owner = owner_row_result[0] if owner_row_result is not None else None
        persisted_session_state: dict[str, Any] | None = (
            owner_row_result[1] if owner_row_result is not None else None
        )
        if owner is None or owner != user_id:
            await _send_error_and_close(ws, 1008, "SESSION_NOT_AUTHORIZED")
            return

        db.add(
            AuditLog(
                actor_id=user_id,
                actor_role=role,
                action="ws.session.connect",
                resource_type="session",
                resource_id=session_id,
            )
        )
        await db.commit()

    await ws.send_json(
        {
            "type": "auth:connected",
            "payload": {"sessionId": str(session_id)},
        }
    )

    # C-2: bounded LRU. Key → cached response frames for replay. A single
    # user:message can fan out to multiple frames (ack + ai:complete).
    idem_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    # ADR-046 #2 round-trip channel (contract1, `services.chat.respond`'s own
    # `session_state` param docstring): seeded from the DB-persisted prior
    # turn's `Session.session_state` (Phase 1 fix — previously always
    # started `None` on a reconnect since no DB column existed yet, PRD
    # §5.1 Option B note). Every `user:message` frame on this WS threads the
    # PRIOR turn's `ChatResponse.session_state` back into the next
    # `/ai/chat/respond` call; `services/chat.py::respond` persists the
    # latest value back to `Session.session_state` after each turn.
    session_state: dict[str, Any] | None = persisted_session_state

    try:
        while True:
            try:
                raw = await ws.receive_json()
            except (json.JSONDecodeError, ValueError):
                await ws.send_json(
                    {"type": "error", "payload": {"code": "FRAME_DECODE_FAILED"}}
                )
                continue

            if not isinstance(raw, dict):
                await ws.send_json(
                    {"type": "error", "payload": {"code": "FRAME_NOT_OBJECT"}}
                )
                continue

            frame_type = raw.get("type")
            if frame_type != "user:message":
                await ws.send_json(
                    {
                        "type": "error",
                        "payload": {"code": "FRAME_UNEXPECTED", "got": str(frame_type)},
                    }
                )
                continue

            try:
                frame = WSUserMessage.model_validate(raw)
            except ValidationError as exc:
                await ws.send_json(
                    {
                        "type": "error",
                        "payload": {
                            "code": "FRAME_INVALID",
                            "details": exc.errors(include_url=False),
                        },
                    }
                )
                continue

            cached = idem_cache.get(frame.payload.idempotency_key)
            if cached is not None:
                # Replay the same frames so the client stays consistent.
                idem_cache.move_to_end(frame.payload.idempotency_key)
                for frame_out in cached:
                    await ws.send_json(frame_out)
                continue

            frames, session_state = await _handle_message(
                settings=settings,
                ai_client=ai_client,
                user_id=user_id,
                session_id=session_id,
                frame=frame,
                session_state=session_state,
            )

            idem_cache[frame.payload.idempotency_key] = frames
            if len(idem_cache) > settings.ws_idempotency_cache_size:
                idem_cache.popitem(last=False)

            for frame_out in frames:
                await ws.send_json(frame_out)

    except WebSocketDisconnect:
        pass
    finally:
        # M-2 follow-up: disconnect audit could go here when we're sure
        # we always reach `finally`. (Best-effort, swallow errors.)
        try:
            async with SessionLocal() as db:
                db.add(
                    AuditLog(
                        actor_id=user_id,
                        actor_role=role,
                        action="ws.session.disconnect",
                        resource_type="session",
                        resource_id=session_id,
                    )
                )
                await db.commit()
        except Exception:
            logger.warning("ws.session.disconnect audit failed", exc_info=True)


async def _handle_message(
    *,
    settings: Settings,
    ai_client: AIClient,
    user_id: UUID,
    session_id: UUID,
    frame: WSUserMessage,
    session_state: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Returns (frames, next_session_state) — `next_session_state` is the
    ADR-046 #2 round-trip value the caller must thread into the NEXT call's
    `session_state` param (unchanged from the input when this turn never
    reached the AI dialogue call, e.g. a risk-interrupt or safety-classifier
    failure short-circuit below)."""
    started = time.perf_counter()

    async with SessionLocal() as db:
        msg = await _persist_user_message(
            db,
            session_id=session_id,
            content=frame.payload.content,
            input_modality=frame.payload.input_modality,
            stt_transcription_id=frame.payload.stt_transcription_id,
            settings=settings,
        )
        await db.commit()
        trigger_message_id = msg.id

    # Call AI Safety (no DB session held during network IO).
    safety_unavailable = False
    safety = None
    try:
        # BUG-062 fix: `SafetyRequest` now mirrors ai-server's real
        # `SafetyInput` (session_id/user_message/conversation_history) — the
        # pre-gate call has no multi-turn context of its own (single-message
        # classification), so `conversation_history` stays empty, matching
        # this call site's pre-fix behavior (the old `prev_context` field was
        # never populated either). Translate the wire response into the
        # platform's internal `SafetyAssessment` via the single-source
        # `to_safety_assessment` (relocated from `ai_client.py`'s interim
        # adapter into `services/safety.py`'s domain layer).
        wire_safety = await ai_client.safety_classify(
            SafetyRequest(session_id=str(session_id), user_message=frame.payload.content)
        )
        safety = to_safety_assessment(wire_safety)
    except AIClientError as exc:
        logger.warning("safety.unavailable", extra={"error": str(exc)})
        safety_unavailable = True

    async with SessionLocal() as db:
        context_ids = await _recent_message_ids(
            db, session_id, CONTEXT_PREV_TURNS
        )
        consent = await latest_consent_snapshot(db, user_id)

        if safety_unavailable:
            payload = await handle_unavailable_classifier(
                db,
                patient_id=user_id,
                session_id=session_id,
                trigger_message_id=trigger_message_id,
                context_message_ids=context_ids,
                consent=consent,
            )
        else:
            assert safety is not None
            payload = await handle_safety_result(
                db,
                patient_id=user_id,
                session_id=session_id,
                trigger_message_id=trigger_message_id,
                context_message_ids=context_ids,
                safety=safety,
                consent=consent,
            )
        await db.commit()

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # HIGH/CRITICAL — the dialogue is interrupted (PRD §5.1): risk only, no AI reply.
    if payload is not None:
        return [{"type": "risk:detected", "payload": payload}], session_state

    safety_level_str = safety.level.value if safety is not None else "unknown"
    frames: list[dict[str, Any]] = [
        {
            "type": "user:message:received",
            "payload": {
                "messageId": str(trigger_message_id),
                "idempotencyKey": frame.payload.idempotency_key,
                "safetyLevel": safety_level_str,
                "latencyMs": elapsed_ms,
            },
        }
    ]

    # FR-004 — best-effort AI dialogue turn (LOW/MEDIUM only). Failure is
    # swallowed inside chat_turn so the chat keeps flowing.
    async with SessionLocal() as db:
        ai_payload = await chat_turn(
            db,
            ai_client=ai_client,
            session_id=session_id,
            settings=settings,
            session_state=session_state,
        )
        await db.commit()
    next_session_state = session_state
    if ai_payload is not None:
        # CVR-051 fix: ai-server's own orchestrator-internal safety gate
        # (conversation-history-aware, distinct from the pre-gate call
        # above) fired a crisis on this turn — `chat_turn` (`services/
        # chat.py::respond`) already ran the SAME `handle_safety_result`
        # escalation the pre-gate path uses and threaded the resulting
        # payload through as `riskDetected`. Emit it as its own
        # `risk:detected` frame (identical shape/semantics to the
        # pre-gate emission above) BEFORE `ai:complete`, then strip the
        # key so the wire-contract-typed `ai:complete` payload is
        # unchanged from before this fix.
        risk_detected = ai_payload.pop("riskDetected", None)
        if risk_detected is not None:
            frames.append({"type": "risk:detected", "payload": risk_detected})
        frames.append({"type": "ai:complete", "payload": ai_payload})
        # ADR-046 #2 round-trip: only advance the carried state when this
        # turn actually reached the AI dialogue call and got one back —
        # a failed/unavailable turn (ai_payload is None) keeps the last
        # good state instead of clobbering it with None.
        next_session_state = ai_payload.get("sessionState", session_state)

    return frames, next_session_state


__all__ = ["router"]
