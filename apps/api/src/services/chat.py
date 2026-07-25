"""AI dialogue turn orchestration (FR-004).

Called by the WebSocket gateway after the safety check clears (LOW/MEDIUM). It:
1. builds the conversation context (decrypted, oldest-first) for the AI server,
2. calls POST /ai/chat/respond (ADR-046 #2 shape — `ChatRequest.user_message`/
   `conversation_history`/`filled_slots`/`session_state`),
3. persists the assistant reply (encrypted, AAD-bound like user messages),
4. updates the session's intake progress (ratio + collected items) when
   ai-server supplies it this turn,
5. returns the `ai:complete` payload (camelCase) for the client, including the
   round-tripped `session_state` for the WS caller to thread into the next turn.

Best-effort by design: ANY failure returns None so the chat keeps flowing — the
safety pipeline has already done its job and the dialogue is non-critical. Token
streaming (`ai:token`) is deferred until the AI server exposes SSE.

NOTE (ADR-046 #2 / PRD §5.1 Option A): the previous `grounding`-injection field
on `ChatRequest` is gone — it never had a matching field on ai-server's own
`DialogueInput` (this route's real wire contract) and `_build_grounding` below
always resolved to `None` in practice anyway (RAG lives in ai-server's own
`src.rag`, not here). Dropped rather than carried as dead code.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from contracts.chat import ChatMessage, ChatRequest
from contracts.safety import RiskCategory, RiskLevel, SafetyAssessment, SafetyEvidence
from contracts.slots import SlotsExtractRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.encryption import decrypt_str, encrypt_str
from src.db import SessionLocal
from src.models.session import Message, Session
from src.services.ai_client import AIClient, AIClientError
from src.services.safety import (
    RiskDetectedPayload,
    handle_safety_result,
    latest_consent_snapshot,
    map_crisis_category,
)

logger = logging.getLogger(__name__)

CHAT_CONTEXT_TURNS = 20

# BUG-075 fix: ai-server's `DialogueOutput`/`ChatResponse` has no `progress`
# field at all (`result.progress` is always `None` on every real call — see
# BUG-075's own reproduction) — the progress bar was structurally frozen at
# 0%/its DB defaults forever. Fix direction (b) from that entry: compute
# `progress_ratio`/`collected_items` on THIS side from the round-tripped
# `session_state` dict every `ChatResponse` already carries (ai-server's own
# `SessionState.model_dump()` shape — `slot_coverage`/`filled_slots` keys are
# always present), rather than waiting on an ai-server schema change. This
# is a single source of truth: no second, independently-computed coverage
# number.
#
# `_INTAKE_TOTAL_ITEMS` mirrors ai-server's own coverage denominator
# (`src.agents.clinical_slot.PATIENT_FILLABLE_SLOTS`, 7 of 12 canonical
# slots — excludes risk_assessment/encounter_metadata/clinical_assessment/
# treatment_plan/mental_status_exam) so `ratio` (already computed over that
# denominator server-side, threaded as `session_state["slot_coverage"]`)
# and `total_items` stay fraction-consistent (closes the previous "13
# hardcoded, but ratio computed over a different denominator" drift). This
# is a plain int, not an import — apps/api has no dependency on ai-server's
# own package — kept in sync manually; a mismatch would only ever under/
# over-state the progress bar's item COUNT display, never the trusted
# `ratio` itself (services/chat.py never recomputes ratio from this count).
_INTAKE_TOTAL_ITEMS = 7


def _progress_fields_from_session_state(
    session_state: dict[str, Any] | None,
) -> tuple[float | None, list[str] | None]:
    """BUG-075: pull `(slot_coverage, filled_slots)` out of the round-
    tripped `session_state` dict (ai-server's `SessionState.model_dump()`
    shape) — the source of truth this module now derives the progress bar
    from, instead of the never-populated `ChatResponse.progress`. Returns
    `(None, None)` for a missing/malformed `session_state` (first turn, or
    any shape apps/api does not recognize) — never raises."""
    state = session_state or {}
    slot_coverage = state.get("slot_coverage")
    filled_slots = state.get("filled_slots")
    return (
        slot_coverage if isinstance(slot_coverage, (int, float)) else None,
        filled_slots if isinstance(filled_slots, list) else None,
    )


def _message_aad(session_id: uuid.UUID, message_id: uuid.UUID) -> bytes:
    return f"messages.content:{session_id}:{message_id}".encode()


def _to_llm_role(role: str) -> str:
    """Map the platform's DB-native message role onto the LLM-facing role.

    Platform stores assistant turns as role='ai' (messages CHECK); LLM APIs
    (chat, slots-extract, and any future sibling call) only accept
    'assistant'. BUG-064 fixed this at `respond`'s call site only; BUG-067
    found `_extract_slots` sending the raw, unmapped role and 400ing at
    Upstage from the 2nd turn onward. Every outbound conversation_history
    builder must go through this one seam so a third sibling can't drift
    again.
    """
    return "assistant" if role == "ai" else role


def _to_llm_history(context: list[ChatMessage]) -> list[dict[str, str]]:
    """Build an LLM-facing conversation_history, mapping roles via `_to_llm_role`."""
    return [{"role": _to_llm_role(m.role), "content": m.content} for m in context]


async def _recent_messages(
    db: AsyncSession, session_id: uuid.UUID, *, limit: int
) -> list[ChatMessage]:
    rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    msgs = list(rows.scalars().all())
    msgs.reverse()  # oldest-first for the model
    out: list[ChatMessage] = []
    for m in msgs:
        try:
            content = decrypt_str(
                m.content_encrypted, aad=_message_aad(session_id, m.id)
            )
        except Exception:
            continue  # skip an unreadable turn rather than poison the context
        out.append(ChatMessage(role=m.role, content=content))
    return out


async def _recent_message_ids(
    db: AsyncSession, session_id: uuid.UUID, *, limit: int
) -> list[uuid.UUID]:
    """Mirrors `api.v1.sessions._recent_message_ids` (private there, this
    module can't import across the services/router boundary) — used only
    to give the CVR-051 escalation path (below) the same audit-trail
    `context_message_ids` shape `handle_safety_result` already expects
    from the pre-gate caller."""
    rows = await db.execute(
        select(Message.id)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    ids = list(rows.scalars().all())
    ids.reverse()  # oldest-first, matches the pre-gate caller's convention
    return ids


# CVR-051: ai-server's `risk_level` string values ("high"/"critical") match
# `contracts.safety.RiskLevel`'s member values 1:1 (both lowercase); this
# maps the wire string back to the enum `handle_safety_result` requires.
# Defaults to HIGH (never silently drops the escalation) for any value the
# safety-gate contract does not otherwise use as a crisis level.
_CRISIS_RISK_LEVEL_MAP: dict[str, RiskLevel] = {
    "critical": RiskLevel.CRITICAL,
    "high": RiskLevel.HIGH,
}

# BUG-060/CVR-051 follow-up, relocated by the BUG-062 fix wave: the
# category-tag -> `RiskCategory` priority map is now a SINGLE source
# (`services/safety.py::CRISIS_CATEGORY_PRIORITY`/`map_crisis_category`),
# shared with the pre-gate `/ai/safety/classify` translation
# (`services/safety.py::to_safety_assessment`). This wrapper keeps the
# orchestrator-crisis-specific fallback (`SELF_HARM`, not `NONE` —see
# docstring below) as the only thing still local to this module.


def _map_crisis_category(categories: list[str]) -> RiskCategory:
    """Map ai-server's merged category tags to the correct `RiskCategory`,
    via the single-source `services/safety.py::map_crisis_category`.

    BUG-060/CVR-051 follow-up: replaces the previous hardcoded
    `RiskCategory.OTHER_HARM` placeholder (wrong for this pathway's actual
    self-harm/suicide-oriented trigger, `_CRISIS_MESSAGES`). Falls back to
    `RiskCategory.SELF_HARM` — not `OTHER_HARM`/`NONE` — when ai-server
    sends no category tag for this turn, because the crisis-bypass CTRS
    band this pathway fires on is self-harm/suicide-oriented by
    construction (see `agents/orchestrator.py::_CRISIS_MESSAGES`, 109
    자살예방상담전화); an empty category list is a safe-default case, not
    evidence of harm to others. This is why this pathway passes its own
    `default=RiskCategory.SELF_HARM` rather than using
    `map_crisis_category`'s own default (`NONE`) — the pre-gate safety-
    classify path (`services/safety.py::to_safety_assessment`) has no such
    self-harm-oriented prior and correctly keeps `NONE` as its default.

    NOTE: this collapses a co-occurring multi-category turn (e.g.
    suicidal_ideation + harm_to_others) down to ONE priority-ranked
    `RiskCategory` — required for triage sorting/routing, which is
    single-value by contract. The full tag list is NOT lost: see
    `_crisis_evidence_keywords` below, which threads it onto the
    clinician-facing `SafetyEvidence.matched_keywords` so it survives
    into `RiskEvent.ai_evidence` (CVR-051 RM-8 follow-up finding 1).
    """
    return map_crisis_category(categories, default=RiskCategory.SELF_HARM)


# CVR-051 RM-8 follow-up (finding 1 + 2): `matched_keywords` was hardcoded
# `[]` for this pathway, so (a) a co-occurring category dropped by
# `_map_crisis_category`'s single-value collapse (e.g. `harm_to_others`
# alongside a `suicidal_ideation`-triggered `RiskCategory.SUICIDE`) was
# unrecoverable from any clinician-facing artifact, and (b) the
# `RiskCategory.SELF_HARM` empty-list fallback was indistinguishable from
# a genuinely detected `self_harm` tag on the dashboard. Both encoded here
# as sentinel strings inside the EXISTING `matched_keywords: list[str]`
# field (no `SafetyEvidence`/`RiskEvent` schema change, no migration) —
# `handle_safety_result` copies this list verbatim into the JSONB
# `RiskEvent.ai_evidence` (`services/safety.py`), which is queryable and
# already documented as "Surfaced in audit + clinician UI"
# (`contracts/safety.py::SafetyEvidence`). Patient-facing surfaces
# (`ai:complete`/`risk:detected`, built from `RiskDetectedPayload` /
# `_payload_for` in `services/safety.py`) never read `matched_keywords` —
# this stays clinician/audit-only (NFR v3-2).
_EVIDENCE_CATEGORY_PREFIX = "ai_category:"
_EVIDENCE_SOURCE_DETECTED = "category_source:detected"
_EVIDENCE_SOURCE_FALLBACK_DEFAULT = "category_source:fallback_default"


def _crisis_evidence_keywords(categories: list[str]) -> list[str]:
    """Full ai-server category list + fallback/detected source, as evidence.

    - Non-empty `categories`: every tag ai-server sent this turn, prefixed
      `ai_category:`, plus `category_source:detected` — so a clinician can
      recover a co-occurring `harm_to_others` even when `_map_crisis_category`
      picked `SUICIDE` as the single-value primary `category`.
    - Empty `categories` (ai-server sent no tag this turn): just
      `category_source:fallback_default`, marking that `_map_crisis_category`'s
      `RiskCategory.SELF_HARM` return is the safe-default placeholder, not an
      actually-detected self_harm tag.
    """
    if not categories:
        return [_EVIDENCE_SOURCE_FALLBACK_DEFAULT]
    return [f"{_EVIDENCE_CATEGORY_PREFIX}{tag}" for tag in categories] + [
        _EVIDENCE_SOURCE_DETECTED
    ]


async def _handle_orchestrator_crisis(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    ai_risk_level: str,
    ai_risk_categories: list[str] | None = None,
) -> RiskDetectedPayload | None:
    """CVR-051 fix: mirror the pre-gate escalation path for a crisis
    detected by ai-server's OWN conversation-history-aware safety gate
    inside the orchestrator (`ChatResponse.crisis_triggered`), so this
    second gate produces the SAME structured RiskEvent + `risk:detected`
    payload the pre-gate `handle_safety_result` call already produces for
    `apps/api`'s own pre-gate classification — rather than only the crisis
    message text landing as an ordinary chat bubble (CVR-051's finding).

    Reuses `handle_safety_result` directly (not a parallel mechanism) by
    constructing the `SafetyAssessment` it expects from the fields ai-server
    already returned this turn. `category` is derived from `ai_risk_
    categories` (`ChatResponse.risk_categories`, BUG-060/CVR-051 follow-up)
    via `_map_crisis_category` — no longer the hardcoded `OTHER_HARM`
    placeholder this function used before the follow-up fix (that value is
    literally "harm to others"/'타해' and was wrong for this pathway's
    actual self-harm/suicide-oriented trigger, `_CRISIS_MESSAGES`).

    RM-8 follow-up (findings 1/2): `evidence.matched_keywords` is no longer
    hardcoded `[]` — see `_crisis_evidence_keywords` for what it now carries
    (full category list + fallback/detected source marker), clinician-facing
    only.
    """
    trigger_message_id = await _recent_message_ids(db, session_id, limit=1)
    if not trigger_message_id:
        logger.warning(
            "chat.crisis.no_trigger_message session_id=%s", session_id
        )
        return None
    context_message_ids = await _recent_message_ids(db, session_id, limit=CHAT_CONTEXT_TURNS)
    consent = await latest_consent_snapshot(db, patient_id)

    safety = SafetyAssessment(
        level=_CRISIS_RISK_LEVEL_MAP.get(ai_risk_level, RiskLevel.HIGH),
        category=_map_crisis_category(ai_risk_categories or []),
        evidence=SafetyEvidence(
            matched_keywords=_crisis_evidence_keywords(ai_risk_categories or []),
            classifier="ai-server-orchestrator-crisis-gate",
            confidence=1.0,
        ),
        latency_ms=0,
    )
    return await handle_safety_result(
        db,
        patient_id=patient_id,
        session_id=session_id,
        trigger_message_id=trigger_message_id[-1],
        context_message_ids=context_message_ids,
        safety=safety,
        consent=consent,
    )


# 파이어-앤-포겟 태스크 GC 방지용 강한 참조.
_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _dialogue_target_slot(session_state: dict[str, Any] | None) -> str | None:
    """BUG-072/073: pull ai-server's single-source-of-truth "what is
    dialogue asking about this turn" field (`SessionState.
    dialogue_target_slot`) out of the round-tripped `session_state` dict,
    so `/ai/slots/extract` gets the same ask-evidence hint the HTTP route
    (`routes/slots.py`) and the in-process post-dialogue extraction
    (`agents/orchestrator.py`) both now use. `None` on any shape mismatch
    (first turn, stale/foreign session_state) — never raises."""
    if not session_state:
        return None
    value = session_state.get("dialogue_target_slot")
    return value if isinstance(value, str) and value else None


async def _extract_slots_bg(
    *,
    session_id: uuid.UUID,
    context: list[ChatMessage],
    ai_client: AIClient,
    session_state: dict[str, Any] | None = None,
) -> None:
    """응답 경로 밖에서 슬롯을 추출·저장한다 (별도 DB 세션).

    요청 스코프 db는 응답과 함께 커밋/종료되므로 여기서 재사용하면 안 된다.
    """
    try:
        async with SessionLocal() as bg_db:
            row = await bg_db.execute(select(Session).where(Session.id == session_id))
            sess = row.scalar_one_or_none()
            if sess is None:
                return
            sess.clinical_slots = await _extract_slots(
                ai_client=ai_client,
                session_id=session_id,
                context=context,
                current=sess.clinical_slots or {},
                session_state=session_state,
            )
            await bg_db.commit()
    except Exception:  # noqa: BLE001 — 배경 작업이라 어떤 실패도 대화에 영향 없음
        logger.warning("slots.extract.bg.failed", exc_info=True)


async def _extract_slots(
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    context: list[ChatMessage],
    current: dict[str, Any],
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """F1 임상 슬롯 증분 추출 (best-effort).

    주호소·수면·과거력 등을 대화에서 누적한다. 이 값이 F2 도메인 추정의
    `final_slots`과 F5 핸드오프의 구조화 근거가 된다.

    실패는 무시하고 기존 슬롯을 그대로 반환한다 — 슬롯 추출 때문에 대화가
    끊기면 안 된다. 저장은 호출자가 플랫폼 sessions 테이블에만 한다
    (rag.session_insights는 VP 코퍼스 테이블이라 실환자 데이터 금지).
    """
    try:
        result = await ai_client.slots_extract(
            SlotsExtractRequest(
                session_id=str(session_id),
                conversation_history=_to_llm_history(context),
                current_slots=current,
                dialogue_target_slot=_dialogue_target_slot(session_state),
            )
        )
    except AIClientError as exc:
        logger.info("slots.extract.unavailable", extra={"error": str(exc)})
        return current
    except Exception:  # noqa: BLE001 — 배경 작업이라 대화를 막지 않는다
        logger.warning("slots.extract.failed", exc_info=True)
        return current

    merged = {**current, **(result.extracted_slots or {})}
    return merged


async def respond(
    db: AsyncSession,
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    settings: Settings,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Generate + persist one assistant turn. Returns the ai:complete payload
    or None if generation failed (caller simply omits the AI reply).

    `session_state`: ADR-046 #2 round-trip channel — the PRIOR turn's
    `ChatResponse.session_state` (opaque dict), `None` on the session's first
    turn (or when the caller has not yet reloaded it from the DB, e.g. a
    fresh reconnect before `api/v1/sessions.py` seeds it from
    `Session.session_state`). The caller (WS gateway) holds this
    connection-scoped, in-memory across turns within one connection; the
    returned payload's `sessionState` key is what the caller must feed back
    in as this param on the NEXT call.

    Phase 1 (PRD §5.1 Option A wiring): this call ALSO persists the turn's
    `result.session_state` and `result.clinical_escalation_required` onto
    `Session` (committed by the caller's surrounding `db.commit()`), so the
    round-trip survives a WS reconnect and not just a single open
    connection.
    """
    try:
        context = await _recent_messages(db, session_id, limit=CHAT_CONTEXT_TURNS)
        if not context or context[-1].role != "user":
            # DialogueInput.user_message requires the CURRENT user turn —
            # nothing to respond to without one (e.g. called out of order).
            logger.warning("chat.respond.no_user_message session_id=%s", session_id)
            return None
        user_message = context[-1].content
        # See `_to_llm_role`/`_to_llm_history` — one shared seam-map for
        # every outbound conversation_history builder (BUG-064, BUG-067).
        conversation_history = _to_llm_history(context[:-1])

        sess_row = await db.execute(select(Session).where(Session.id == session_id))
        sess = sess_row.scalar_one_or_none()
        filled_slots: dict[str, str] = dict(sess.clinical_slots or {}) if sess is not None else {}

        result = await ai_client.chat_respond(
            ChatRequest(
                session_id=session_id,
                user_message=user_message,
                conversation_history=conversation_history,
                filled_slots=filled_slots,
                session_state=session_state,
            )
        )
    except AIClientError as exc:
        logger.info("chat.respond.unavailable", extra={"error": str(exc)})
        return None
    except Exception:  # noqa: BLE001 — dialogue is best-effort, never break the WS
        logger.warning("chat.respond.failed", exc_info=True)
        return None

    # CVR-051 fix: ai-server's own conversation-history-aware safety gate
    # (inside its orchestrator) fired on THIS turn — mirror the pre-gate
    # `handle_safety_result` escalation (RiskEvent + `risk:detected`
    # payload) so this second gate's crisis signal is not silently dropped
    # (previously only `result.assistant_response`'s crisis message text
    # reached the client, as an ordinary chat bubble). Best-effort: any
    # failure here must not block the assistant reply already generated.
    risk_detected: dict[str, Any] | None = None
    if result.crisis_triggered and sess is not None:
        try:
            payload = await _handle_orchestrator_crisis(
                db,
                session_id=session_id,
                patient_id=sess.patient_id,
                ai_risk_level=result.risk_level,
                ai_risk_categories=result.risk_categories,
            )
            if payload is not None:
                risk_detected = dict(payload)
        except Exception:  # noqa: BLE001 — escalation failure must not drop the reply
            logger.warning(
                "chat.crisis.escalation_failed session_id=%s", session_id, exc_info=True
            )

    # Persist the assistant reply (AAD bound to its own row id).
    ai_message_id = uuid.uuid4()
    db.add(
        Message(
            id=ai_message_id,
            session_id=session_id,
            role="ai",
            content_encrypted=encrypt_str(
                result.assistant_response,
                aad=_message_aad(session_id, ai_message_id),
                settings=settings,
            ),
            input_modality="text",
        )
    )

    # BUG-075 fix: `result.progress` is structurally always `None` (ai-
    # server's `DialogueOutput` has no `progress` field to populate it from
    # — see this module's own `_INTAKE_TOTAL_ITEMS` docstring), so deriving
    # progress from it froze every session's progress bar at its DB
    # defaults forever. Compute directly from the round-tripped
    # `session_state` dict instead — ai-server's own `SessionState.
    # model_dump()` shape always carries `slot_coverage`/`filled_slots`,
    # computed server-side every turn (`OrchestratorAgent.
    # _update_slot_coverage`) — single source of truth, no second
    # independently-computed ratio. Keeps the session's last-known values
    # (never resets to 0) only when `session_state` itself is absent this
    # turn (e.g. an error path that short-circuited before the orchestrator
    # ran).
    state_slot_coverage, state_filled_slots = _progress_fields_from_session_state(
        result.session_state
    )
    if sess is not None:
        if state_slot_coverage is not None:
            sess.progress_ratio = max(0.0, min(1.0, float(state_slot_coverage)))
        if state_filled_slots is not None:
            sess.collected_items = state_filled_slots
        collected_items = sess.collected_items
        total_items = _INTAKE_TOTAL_ITEMS
        ratio = sess.progress_ratio

        # Phase 1 (ADR-046 #2 wiring) — persist the round-trip channel + the
        # ADR-044 4th field so a reconnect can reload the prior turn's state
        # (`api/v1/sessions.py` WS-open path) instead of only ever seeing
        # `None` again. `result.session_state` already carries
        # `asked_slot_counts`/`risk_screening_incomplete`/`handoff_delivered`
        # nested under their own key names (ai-server's
        # `SessionState.model_dump()` shape) — stored verbatim, not
        # re-derived or flattened.
        sess.session_state = result.session_state
        sess.clinical_escalation_required = result.clinical_escalation_required

        # Minimal consumer (CVR-047 recommendation 3): DB persistence of the
        # flag alone is not a clinical action, so surface it as a distinctly
        # named, structured (alert-greppable) log event in addition to the
        # column above — this is the Phase 1 floor, not the full counselor
        # notification pipeline (F5 is a follow-up PRD's scope; that would
        # consume this log/column, not replace it).
        if result.clinical_escalation_required:
            logger.warning(
                "chat.clinical_escalation.flagged",
                extra={
                    "session_id": str(session_id),
                    "risk_level": result.risk_level,
                    "requires_human_review": result.requires_human_review,
                },
            )
    else:
        collected_items = state_filled_slots if state_filled_slots is not None else []
        total_items = _INTAKE_TOTAL_ITEMS
        ratio = (
            max(0.0, min(1.0, float(state_slot_coverage)))
            if state_slot_coverage is not None else 0.0
        )

    # F1 — 임상 슬롯 추출은 두 번째 AI 왕복이라, 응답 경로에서 await하면 답변이
    # 그만큼 늦어진다(최악 chat+slots 예산 합). 응답을 먼저 돌려주고 슬롯은 별도
    # 태스크 + 별도 DB 세션에서 누적한다. 실패해도 대화엔 영향 없다.
    # BUG-072/073: thread this turn's round-tripped `session_state` too, so
    # the background extraction call can populate `dialogue_target_slot`
    # (the ask-evidence hint) — see `_dialogue_target_slot`.
    _spawn(
        _extract_slots_bg(
            session_id=session_id,
            context=context,
            ai_client=ai_client,
            session_state=result.session_state,
        )
    )

    return {
        "messageId": str(ai_message_id),
        "content": result.assistant_response,
        "modelUsed": result.model_used,
        "progress": {
            "collectedItems": collected_items,
            "totalItems": total_items,
            "ratio": ratio,
        },
        # ADR-046 #2 round-trip fields — caller threads `sessionState` back
        # into the next turn's `respond(session_state=...)` call.
        "sessionState": result.session_state,
        "riskLevel": result.risk_level,
        "requiresHumanReview": result.requires_human_review,
        "handoffReady": result.handoff_ready,
        "handoffReport": result.handoff_report,
        "clinicalEscalationRequired": result.clinical_escalation_required,
        # CVR-051 fix: present only when ai-server's own orchestrator-
        # internal safety gate fired a crisis on this turn — the caller
        # (`api/v1/sessions.py::_handle_message`) pops this key and emits
        # it as a separate `risk:detected` WS frame (the same payload
        # shape the pre-gate `handle_safety_result` path already emits),
        # then ships the rest of this dict as `ai:complete` unchanged.
        "riskDetected": risk_detected,
    }
