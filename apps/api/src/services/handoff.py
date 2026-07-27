"""Handoff report orchestration (FR-010/018).

Async generation flow:
1. POST /submit creates a `generating` handoff_reports row (in the request txn).
2. A background task (`generate_report_task`) opens its own DB session, gathers
   the session's messages / questionnaires / risk events, calls
   apps/ai-server `/ai/handoff/generate`, and flips the row to `ready`/`failed`.
3. GET /report composes the response: deterministic facts (questionnaires, risk
   signals, patient demographics) are assembled here regardless of generation
   state, so the clinician sees *something* even while the narrative is pending.

NOTE: BackgroundTasks (in-process) is the Demo executor. The seam is
`generate_report_task(session_id)` — swapping it for a Celery task later is a
one-line change at the call site (PRD/PLAN 1b.3).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from contracts.handoff import HandoffRequest, ScaleScore, SlotData
from contracts.longitudinal import (
    DomainInferenceInput,
    HandoffReportRequest,
    LongitudinalSessionEntry,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.encryption import decrypt_str
from src.db import SessionLocal
from src.models.audit_log import AuditLog
from src.models.handoff import HandoffReport
from src.models.patient_profile import PatientProfile
from src.models.questionnaire import QuestionnaireResult
from src.models.session import Message, RiskEvent, Session
from src.models.user import User
from src.schemas.handoff import (
    HandoffReportOut,
    QuestionnaireScore,
    ReportPatient,
    ReportRiskSignal,
)
from src.services.ai_client import AIClient, AIClientError, get_ai_client
from src.services.clinician import _can_access_patient  # ISS-022: shared org-access rule

logger = logging.getLogger(__name__)


def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


def _profile_aad(user_id: uuid.UUID, column: str) -> bytes:
    return f"patient_profiles.{column}:{user_id}".encode()


async def create_pending_report(
    db: AsyncSession, *, session_id: uuid.UUID
) -> HandoffReport:
    """Create (or reset) the report row for a session, status=generating.

    Re-submission regenerates: an existing row is flipped back to generating.
    """
    existing = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = existing.scalar_one_or_none()
    if report is None:
        report = HandoffReport(session_id=session_id, status="generating")
        db.add(report)
    else:
        report.status = "generating"
        report.content = None
        report.failure_reason = None
        report.generated_at = None
    await db.flush()
    return report


async def _build_slots(db: AsyncSession, session_id: uuid.UUID) -> SlotData:
    """BUG-066 fix — resolves the fix_wave_design.md UNVERIFIED open item:
    apps/api DOES persist per-session slot data, in `Session.clinical_slots`
    (JSONB, populated in the background by `services/chat.py::
    _extract_slots_bg` — a flat dict keyed by ClinicalSlotAgent's
    canonical-12 slot names, per BUG-050). `_build_request` never read this
    column before this fix — every handoff request silently shipped
    `slots=SlotData()` (all-`None` defaults), which is why BUG-066's live
    probe found a vacuous 12-section report despite real filled slots
    existing in the DB. Unknown/stale dict keys (defensive — `clinical_slots`
    is caller-controlled JSONB, not schema-enforced) are filtered against
    `SlotData.model_fields` rather than passed through, so a stray key can
    never trip `SlotData`'s own `extra="forbid"`."""
    row = await db.execute(select(Session.clinical_slots).where(Session.id == session_id))
    raw = row.scalar_one_or_none() or {}
    filtered = {k: v for k, v in raw.items() if k in SlotData.model_fields}
    return SlotData(**filtered)


async def _build_patient_metadata(
    db: AsyncSession, session_id: uuid.UUID
) -> tuple[str | None, str | None, str | None]:
    """BUG-069 follow-up (F5 metadata enrichment, 2026-07-25): resolves the
    real `patient_gender`/`session_started_at`/`session_ended_at` values
    `HandoffRequest` gained additively — previously nothing threaded these
    into the handoff pipeline at all (v4.3's "기록 없음"/"미수집" fallback
    was the only rendering, by design, given that absence). Returns `(None,
    None, None)` per-field wherever the underlying row/column is missing —
    never guesses; `handoff_generator.py::_build_user_content` keeps its
    existing grounded fallback text for any `None` here."""
    sess_row = await db.execute(
        select(Session.created_at, Session.submitted_at, Session.patient_id).where(
            Session.id == session_id
        )
    )
    sess = sess_row.first()
    if sess is None:
        return None, None, None
    created_at, submitted_at, patient_id = sess

    gender_row = await db.execute(
        select(PatientProfile.gender).where(PatientProfile.user_id == patient_id)
    )
    gender = gender_row.scalar_one_or_none()

    return (
        gender,
        created_at.isoformat() if created_at is not None else None,
        submitted_at.isoformat() if submitted_at is not None else None,
    )


async def _build_request(
    db: AsyncSession, session_id: uuid.UUID
) -> HandoffRequest:
    """BUG-066 fix: assembles the REAL `HandoffInput`-shaped request
    (`conversation_history`/`scale_scores`/`risk_events`/`slots`) instead of
    the pre-fix invented `HandoffMessage`/`HandoffQuestionnaire`/
    `HandoffRiskSignal` shape ai-server's `extra`-permissive (pre-fix)
    `HandoffInput` silently dropped in full."""
    msg_rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    conversation_history: list[dict[str, str]] = []
    for m in msg_rows.scalars().all():
        try:
            content = decrypt_str(
                m.content_encrypted, aad=_message_aad(session_id, m.id)
            )
        except Exception:
            content = ""
        conversation_history.append({"role": m.role, "content": content})

    q_rows = await db.execute(
        select(QuestionnaireResult).where(
            QuestionnaireResult.session_id == session_id
        )
    )
    scale_scores = [
        ScaleScore(scale_name=q.type, total_score=q.total_score, severity=q.severity)
        for q in q_rows.scalars().all()
    ]

    r_rows = await db.execute(
        select(RiskEvent).where(RiskEvent.session_id == session_id)
    )
    risk_events: list[dict[str, str]] = [
        {
            "level": r.level,
            "category": r.category or "",
            "source_message_id": str(r.trigger_message_id) if r.trigger_message_id else "",
        }
        for r in r_rows.scalars().all()
    ]

    slots = await _build_slots(db, session_id)
    patient_gender, session_started_at, session_ended_at = await _build_patient_metadata(
        db, session_id
    )

    return HandoffRequest(
        session_id=str(session_id),
        slots=slots,
        conversation_history=conversation_history,
        scale_scores=scale_scores,
        risk_events=risk_events,
        patient_gender=patient_gender,
        session_started_at=session_started_at,
        session_ended_at=session_ended_at,
    )


# 문진 type(DB) → (ai-server 척도명, 만점). F4/F5 입력은 "PHQ-9" 형식을 기대한다.
_SCALE_META = {
    "PHQ9": ("PHQ-9", 27),
    "GAD7": ("GAD-7", 21),
    "AUDITC": ("AUDIT-C", 12),
    "PHQ4": ("PHQ-4", 12),
}
# 세션 대표 척도 우선순위 (F5는 세션당 단일 척도를 모델링).
_SCALE_PRIORITY = ("PHQ9", "GAD7", "AUDITC", "PHQ4")
# risk level → CTRS (1=응급 … 5=안정).
_RISK_TO_CTRS = {"critical": 1, "high": 2, "medium": 3, "low": 4, "none": 5}


def _display_vp(patient_id: uuid.UUID) -> str:
    """리포트 표시용 환자 코드. 원본 DB UUID는 개발자 정보라 노출 금지 —
    editorial 렌더의 `patient.id`·F4 차트 제목·FHIR `id`가 모두 vp_id를 그대로
    쓰므로, 여기서 비가역 축약 코드(`VP-XXXXXX`)로 바꿔 UUID 누출을 차단한다.
    템플릿의 VP-XXX 관례와도 맞아 build_report_json의 reportNo 파싱이 그대로 동작."""
    return f"VP-{patient_id.hex[:6].upper()}"


async def _patient_display_name(
    db: AsyncSession, patient_id: uuid.UUID
) -> str | None:
    """환자 실명(AES-256 복호화). F5 A0 헤더 `환자: {persona_name}`에 실려
    editorial 렌더에서 `mask()`로 마스킹 표기된다(예: 김서연→김○연). 프로필/키가
    없으면 None → F5는 '이름 없음'으로 우아하게 degrade(UUID 노출 없음)."""
    row = await db.execute(
        select(PatientProfile.name_encrypted).where(
            PatientProfile.user_id == patient_id
        )
    )
    enc = row.scalar_one_or_none()
    if enc is None:
        return None
    try:
        return decrypt_str(enc, aad=_profile_aad(patient_id, "name"))
    except Exception:
        return None


async def _build_longitudinal_sessions(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[LongitudinalSessionEntry]:
    """이 환자의 세션들을 F4/F5 입력(LongitudinalSessionEntry)으로 변환한다.

    데이터가 있는 세션(clinical_slots 또는 설문 결과 존재)만 시간순으로 담고,
    각 세션의 슬롯·대표 설문(F3)·위기단계(CTRS)를 채운다. F2 도메인추론은 API DB에
    저장되지 않으므로 비우고(A6/A7은 '정보 없음' 처리), F5가 우아하게 degrade한다."""
    srows = await db.execute(
        select(Session)
        .where(Session.patient_id == patient_id)
        .order_by(Session.created_at)
    )
    sessions = list(srows.scalars())

    # 환자 표시 정체성(실명 마스킹용 + 비-UUID 코드) — F5 A0 헤더/차트/FHIR가 소비.
    display_name = await _patient_display_name(db, patient_id)
    display_vp = _display_vp(patient_id)

    entries: list[LongitudinalSessionEntry] = []
    idx = 0
    for sess in sessions:
        slots = {k: str(v) for k, v in (sess.clinical_slots or {}).items() if v}

        # 대표 설문 1개 → F3 dict
        qrows = await db.execute(
            select(QuestionnaireResult).where(QuestionnaireResult.session_id == sess.id)
        )
        qmap = {q.type: q for q in qrows.scalars()}
        f3: dict | None = None
        for t in _SCALE_PRIORITY:
            if t in qmap:
                q = qmap[t]
                name, max_score = _SCALE_META.get(t, (t, None))
                f3 = {
                    "outcome": "administered",
                    "scale_name": name,
                    "total_score": q.total_score,
                    "max_score": max_score,
                    "severity": q.severity,
                    "responses": list(q.answers or ()),
                }
                break

        # 데이터가 전혀 없는 세션은 종단 시리즈에서 제외한다.
        if not slots and f3 is None:
            continue

        # 위기단계: 세션의 가장 심각한 위험신호 → CTRS.
        rrows = await db.execute(
            select(RiskEvent.level).where(RiskEvent.session_id == sess.id)
        )
        ctrs_vals = [
            _RISK_TO_CTRS.get(str(lvl), 5) for lvl in rrows.scalars() if lvl
        ]
        session_ctrs = min(ctrs_vals) if ctrs_vals else None

        # BUG-055 fail-loud: 위기 플래그를 세우면 risk_assessment를 반드시 실어야
        # 한다. session_state.slot_data.risk_assessment에서 가져오고, 없으면 근거가
        # 없는 위기 주장을 피하기 위해 crisis 플래그를 세우지 않는다(CTRS는 유지).
        state = sess.session_state or {}
        slot_data = state.get("slot_data") if isinstance(state, dict) else None
        risk_assessment = None
        if isinstance(slot_data, dict):
            ra = slot_data.get("risk_assessment")
            risk_assessment = str(ra) if ra else None
        crisis = bool(ctrs_vals and min(ctrs_vals) <= 2 and risk_assessment)

        entries.append(
            LongitudinalSessionEntry(
                session_index=idx,
                simulated_date=sess.created_at.date().isoformat(),
                final_slots=slots,
                session_ctrs=session_ctrs,
                crisis_triggered=crisis,
                risk_assessment=risk_assessment,
                f3=f3,
                session_id=str(sess.id),
                persona_name=display_name,
                persona_id=display_vp,
            )
        )
        idx += 1

    return entries


async def generate_report_task(
    session_id: uuid.UUID, *, ai_client: AIClient | None = None
) -> None:
    """Background entrypoint. Opens its own session; never raises to the caller.

    다세션(≥2)이면 사용자가 고도화한 결정론적 F4+F5 통합 리포트(12섹션 markdown +
    HL7 FHIR + editorial PDF + F4 차트)를 `/ai/handoff/report`로 생성한다. 초진
    단일세션이면 종단 비교가 불가하므로 기존 단일세션 서사(`/ai/handoff/generate`)로
    폴백한다."""
    client = ai_client or get_ai_client()
    async with SessionLocal() as db:
        try:
            srow = await db.execute(select(Session).where(Session.id == session_id))
            sess = srow.scalar_one_or_none()
            patient_id = sess.patient_id if sess else None

            entries = (
                await _build_longitudinal_sessions(db, patient_id)
                if patient_id
                else []
            )

            if len(entries) >= 2:
                # 사용자 고도화 F4+F5 풀 리포트 (결정론적, PDF/FHIR/차트 포함).
                report_req = HandoffReportRequest(
                    vp_id=_display_vp(patient_id),
                    sessions=entries,
                    domain_inference=DomainInferenceInput(),
                    include_charts=True,
                    include_pdf=True,
                )
                full = await client.handoff_report(report_req)
                await _mark_ready(db, session_id, content=full.model_dump(mode="json"))
                logger.info(
                    "handoff.report.full ready (sessions=%d, pdf=%s, charts=%d)",
                    len(entries),
                    bool(full.pdf_base64),
                    len(full.chart_pngs_base64 or []),
                )
                return

            # 초진 단일세션 — 종단 리포트 불가, 단일세션 서사로 폴백.
            request = await _build_request(db, session_id)
            response = await client.handoff_generate(request)
        except AIClientError as exc:
            logger.warning(
                "handoff.generate.failed",
                extra={"session_id": str(session_id), "error": str(exc)},
            )
            await _mark_failed(db, session_id, reason="ai_server_unavailable")
            return
        except Exception:  # noqa: BLE001 — defensive: a bg task must not crash silently
            logger.exception("handoff.generate.unexpected", extra={"session_id": str(session_id)})
            await _mark_failed(db, session_id, reason="internal_error")
            return

        await _mark_ready(db, session_id, content=response.model_dump(mode="json"))


async def _mark_ready(
    db: AsyncSession, session_id: uuid.UUID, *, content: dict
) -> None:
    row = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = row.scalar_one_or_none()
    if report is None:
        return
    report.status = "ready"
    report.content = content
    report.failure_reason = None
    report.generated_at = datetime.now(UTC)

    sess_row = await db.execute(select(Session).where(Session.id == session_id))
    sess = sess_row.scalar_one_or_none()
    if sess is not None:
        sess.status = "report_ready"

    db.add(
        AuditLog(
            actor_id=None,
            actor_role="system",
            action="handoff.report.ready",
            resource_type="handoff_report",
            resource_id=report.id,
            audit_metadata={"session_id": str(session_id)},
        )
    )
    await db.commit()


async def _mark_failed(
    db: AsyncSession, session_id: uuid.UUID, *, reason: str
) -> None:
    row = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = row.scalar_one_or_none()
    if report is None:
        return
    report.status = "failed"
    report.failure_reason = reason
    db.add(
        AuditLog(
            actor_id=None,
            actor_role="system",
            action="handoff.report.failed",
            resource_type="handoff_report",
            resource_id=report.id,
            audit_metadata={"session_id": str(session_id), "reason": reason},
        )
    )
    await db.commit()


async def build_report_response(
    db: AsyncSession,
    *,
    actor: User,
    session_id: uuid.UUID,
    require_delivered: bool = True,
) -> HandoffReportOut | None:
    """Compose the GET /report payload. Returns None if no report row exists,
    or if the session's patient is outside the actor's organization (ISS-022).

    v3 §6-B — 수동 전달: 기본적으로 **전달된 리포트만** 노출한다. 환자가
    [전달하기]를 누르기 전(delivered_at IS NULL)에는 의료진이 볼 수 없다. 리포트
    본문은 여전히 clinician 전용이며, 이 게이트는 '언제 보이는가'만 통제한다."""
    row = await db.execute(
        select(HandoffReport).where(HandoffReport.session_id == session_id)
    )
    report = row.scalar_one_or_none()
    if report is None:
        return None
    if require_delivered and report.delivered_at is None:
        # 아직 환자가 전달하지 않음 — 존재 자체를 노출하지 않는다(None → 404).
        return None

    sess_row = await db.execute(select(Session).where(Session.id == session_id))
    sess = sess_row.scalar_one_or_none()
    if sess is None:
        return None

    # ISS-022: org-scope — the session's patient must belong to the actor's org.
    hosp_row = await db.execute(
        select(PatientProfile.target_hospital_id).where(
            PatientProfile.user_id == sess.patient_id
        )
    )
    if not _can_access_patient(actor, hosp_row.scalar_one_or_none()):
        return None

    # Deterministic facts — always composed server-side (not AI output).
    q_rows = await db.execute(
        select(QuestionnaireResult).where(
            QuestionnaireResult.session_id == session_id
        )
    )
    questionnaires = [
        QuestionnaireScore(
            type=q.type, total_score=q.total_score, severity=q.severity
        )
        for q in q_rows.scalars().all()
    ]

    r_rows = await db.execute(
        select(RiskEvent)
        .where(RiskEvent.session_id == session_id)
        .order_by(RiskEvent.detected_at.desc())
    )
    risk_signals = [
        ReportRiskSignal(
            level=r.level,
            category=r.category,
            trigger_message_id=r.trigger_message_id,
        )
        for r in r_rows.scalars().all()
    ]

    patient = await _report_patient(db, sess.patient_id)

    return HandoffReportOut(
        report_id=report.id,
        session_id=session_id,
        status=report.status,
        generated_at=report.generated_at,
        failure_reason=report.failure_reason,
        patient=patient,
        questionnaires=questionnaires,
        risk_signals=risk_signals,
        narrative=report.content,
    )


async def _report_patient(
    db: AsyncSession, patient_id: uuid.UUID
) -> ReportPatient | None:
    row = await db.execute(
        select(PatientProfile).where(PatientProfile.user_id == patient_id)
    )
    profile = row.scalar_one_or_none()
    if profile is None:
        return None
    try:
        name = decrypt_str(
            profile.name_encrypted, aad=_profile_aad(patient_id, "name")
        )
    except Exception:
        name = "(이름 복호화 실패)"
    return ReportPatient(
        id=patient_id,
        name=name,
        birth_year=profile.birth_year,
        gender=profile.gender,
    )
