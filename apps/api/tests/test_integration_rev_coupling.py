"""PLAN-2026-W30-INTEG-REV (R1, qa) — single-session-lifecycle cross-phase
coupling verification.

The F1-F3 integration was built in phases (7c1e7f8 -> b513379 -> 5e7b503 ->
37c38b2), each with its own gate and its own isolated-fixture test suite.
Nothing before this file has run ONE session through chat roundtrip -> slots
-> domain infer (3 cases) -> survey plan -> score -> WS-reconnect seed as a
SINGLE coupled lifecycle. This file exists to explicitly probe the three
named cross-phase coupling hypotheses (verbatim from the mission brief):

  H1: P1's session_state persistence interferes with P2/P3 routes in the
      SAME session (stale/overwritten session_state, WS-reconnect seed
      dropping fields).
  H2: `clinical_escalation_required` (chat path) correctly flows into
      survey/plan's `crisis_triggered` (`sessions.py:289`) and drives
      `si_supplement` end-to-end, not just in isolation.
  H3: the survey-plan path's caveat-strip (`sessions.py:320-322` pop) does
      NOT accidentally strip anything from the chat response path, and no
      proxy-caveat text leaks to any patient-facing response.

Deliberately independent of `tests/conftest.py` (BUG-058) — same pattern as
test_phase1_session_state_persistence.py / test_phase2_domain_routing.py /
test_phase3_survey_plan.py: own throwaway `pgserver`, own `alembic
stamp 0010 -> upgrade head` (0011 upgrade() runs for real), own ASGITransport
client, own hard httpx.AsyncClient.post guard.

Hard constraints:
  - all live API keys forced to "" (BUG-052/058 — unset alone does not gate).
  - zero live LLM / outbound HTTP — ai-server responses are stubbed at the
    `AIClient`/`get_ai_client` boundary; only in-process ASGITransport calls
    against this repo's own app are allowed through the guard.
  - no DGX Postgres touched — throwaway pgserver only.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

pgserver = pytest.importorskip(
    "pgserver",
    reason=(
        "test-only throwaway-Postgres helper not declared in "
        "apps/api/pyproject.toml/uv.lock yet — skipping gracefully rather "
        "than erroring the suite (mirrors test_phase1/2/3's own pattern)."
    ),
)

for _key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "UPSTAGE_API_KEY",
    "HIRA_API_KEY",
    "KAKAO_API_KEY",
    "NS_RAG_API_KEY",
    "SKT_A_X_API_KEY",
):
    os.environ[_key] = ""


@pytest.fixture(autouse=True)
def _forbid_live_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard guard: only in-process ASGITransport calls against our own app
    are allowed through; any real network attempt fails the test loudly."""
    import httpx

    _real_post = httpx.AsyncClient.post

    async def _guarded_post(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> Any:
        transport = getattr(self, "_transport", None)
        if isinstance(transport, httpx.ASGITransport):
            return await _real_post(self, *args, **kwargs)
        raise AssertionError(
            "live HTTP call attempted — this test must only use a stub "
            "AIClient / dependency override, or an in-process ASGITransport"
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _guarded_post)


# ─────────────────────── throwaway Postgres + alembic 0010->head ──────────


@pytest.fixture(scope="module")
def _throwaway_postgres_url() -> Any:
    pgdata = tempfile.mkdtemp(prefix="qa_integ_rev_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    srv.psql("CREATE DATABASE neurosync_qa_integ_rev;")
    uri = (
        srv.get_uri()
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("/postgres?", "/neurosync_qa_integ_rev?")
    )
    os.environ["DATABASE_URL"] = uri
    from src.core.config import get_settings

    get_settings.cache_clear()
    try:
        yield uri
    finally:
        get_settings.cache_clear()
        srv.cleanup()


@pytest.fixture(scope="module")
def _migrated_engine(_throwaway_postgres_url: str) -> str:
    """Bootstrap to pre-0011 baseline via `Base.metadata.create_all`, stamp
    0010, then run the REAL `alembic upgrade head` (0011's own `upgrade()`
    executes here) — mirrors test_phase1/2/3 verbatim. 0009a/0010 are already
    baked into `Base.metadata` (models reflect head), so the create_all +
    drop-then-alembic-add pattern exercises exactly the 0010->0011 seam this
    mission's own success criterion names."""
    import asyncio

    import alembic.command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import src.models  # noqa: F401 — register all tables on Base.metadata
    from src.db import Base
    from src.models.patient_profile import PatientProfile

    is_minor_col = PatientProfile.__table__.c.is_minor
    is_minor_col.computed = None
    is_minor_col.server_default = text("false")

    async def _create_pre_0011_baseline() -> None:
        baseline_engine = create_async_engine(_throwaway_postgres_url, echo=False)
        try:
            async with baseline_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(text("ALTER TABLE sessions DROP COLUMN session_state"))
                await conn.execute(
                    text("ALTER TABLE sessions DROP COLUMN clinical_escalation_required")
                )
        finally:
            await baseline_engine.dispose()

    asyncio.run(_create_pre_0011_baseline())

    alembic_dir = os.path.join(os.path.dirname(__file__), "..", "alembic")
    cfg = Config()
    cfg.set_main_option("script_location", os.path.abspath(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", _throwaway_postgres_url)
    alembic.command.stamp(cfg, "0010")
    alembic.command.upgrade(cfg, "head")  # <- real 0011 upgrade() executes here

    async def _verify_columns() -> set[str]:
        verify_engine = create_async_engine(_throwaway_postgres_url, echo=False)
        try:
            async with verify_engine.connect() as conn:
                cols = await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='sessions' "
                        "AND column_name IN "
                        "('session_state','clinical_escalation_required')"
                    )
                )
                return {row[0] for row in cols.fetchall()}
        finally:
            await verify_engine.dispose()

    found = asyncio.run(_verify_columns())
    assert found == {"session_state", "clinical_escalation_required"}, (
        f"alembic 0010->head did not add the expected Phase 1 columns: {found}"
    )

    return _throwaway_postgres_url


@pytest_asyncio.fixture
async def db_session(_migrated_engine: str) -> AsyncGenerator[Any, None]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_migrated_engine, echo=False, poolclass=NullPool)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, autoflush=False, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(db_session) -> Any:
    """ONE patient + ONE in_progress session — the single session_id threaded
    through the entire lifecycle in the test below."""
    from src.models.session import Session
    from src.models.user import User

    patient = User(
        id=uuid.uuid4(),
        email=f"qa-integ-rev-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role="patient",
    )
    db_session.add(patient)
    await db_session.flush()
    sess = Session(id=uuid.uuid4(), patient_id=patient.id, status="in_progress")
    db_session.add(sess)
    await db_session.commit()
    return patient, sess.id


# ─────────────────────────────── stubs ─────────────────────────────────────


class _StubChatAIClient:
    """Stand-in for `AIClient.chat_respond`/`slots_extract` — no httpx."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[Any] = []

    async def chat_respond(self, payload: Any) -> Any:
        self.calls.append(payload)
        return self._responses.pop(0)

    async def slots_extract(self, payload: Any) -> Any:
        from contracts.slots import SlotsExtractResponse

        return SlotsExtractResponse(extracted_slots={})


def _chat_response(*, session_state: dict[str, Any], escalation: bool) -> Any:
    from contracts.chat import ChatResponse

    return ChatResponse(
        assistant_response="ack",
        session_state=session_state,
        clinical_escalation_required=escalation,
        risk_level="high" if escalation else "low",
        requires_human_review=escalation,
    )


async def _post_user_turn(db_session, session_id, settings, text: str) -> None:
    from src.core.encryption import encrypt_str
    from src.models.session import Message

    message_id = uuid.uuid4()
    db_session.add(
        Message(
            id=message_id,
            session_id=session_id,
            role="user",
            content_encrypted=encrypt_str(
                text,
                aad=f"messages.content:{session_id}:{message_id}".encode(),
                settings=settings,
            ),
            input_modality="text",
        )
    )
    await db_session.flush()


def _make_app_with_overrides(db_session, patient, ai_client_stub: Any) -> Any:
    from src.core.deps import get_current_user
    from src.db import get_session
    from src.main import create_app
    from src.services.ai_client import get_ai_client

    async def _override_get_session():
        yield db_session

    async def _override_get_current_user():
        return patient

    def _override_get_ai_client():
        return ai_client_stub

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_ai_client] = _override_get_ai_client
    return app


class _RecordingDomainAIClient:
    """Route-level `get_ai_client` override exposing `domain_infer` +
    `survey_plan` — records every `survey_plan` request so the test can
    assert `crisis_triggered` actually arrived (H2), and mirrors real
    ai-server's own `si_supplement` = f(crisis_triggered) resolution
    (`apps/ai-server/src/f3.py::resolve_si_supplement_needed`, simplified:
    a crisis-triggered proxy-scale routing supplements SI) so the coupling
    is exercised, not just echoed."""

    def __init__(self, domain_response: Any) -> None:
        self._domain_response = domain_response
        self.domain_infer_calls: list[Any] = []
        self.survey_plan_calls: list[Any] = []

    async def domain_infer(self, payload: Any) -> Any:
        self.domain_infer_calls.append(payload)
        return self._domain_response

    async def survey_plan(self, payload: Any) -> Any:
        from contracts.survey_plan import SurveyPlanResponse

        self.survey_plan_calls.append(payload)
        # Simplified mirror of ai-server's real si_supplement logic: a
        # crisis_triggered session administering a PROXY (caveat-bearing)
        # scale gets the SI-supplement item; native scales / non-crisis
        # sessions do not. This is intentionally NOT a tautology against
        # `payload.crisis_triggered` alone — it also requires a caveat
        # (proxy-scale) to be present, matching CVR-030's real condition.
        si_needed = bool(payload.crisis_triggered) and payload.recommendation_caveat is not None
        return SurveyPlanResponse(
            scale=payload.recommended_questionnaire,
            administration_mode="si_supplement-plan" if si_needed else "natural",
            si_supplement=si_needed,
            recommendation_caveat=payload.recommendation_caveat,
        )


class _StubScoreAIClient:
    """Stand-in for `AIClient.survey_score` — always the AI-success path,
    with values structurally unreachable by the local-fallback path
    (mirrors test_phase3_survey_score_smoke.py's non-tautology design)."""

    def __init__(self, *, total_score: int, max_score: int, severity: str, critical: bool) -> None:
        self._total_score = total_score
        self._max_score = max_score
        self._severity = severity
        self._critical = critical
        self.called = False

    async def survey_score(self, payload: Any) -> Any:
        from contracts.survey import SurveyScoreResponse

        self.called = True
        return SurveyScoreResponse(
            scale_name=payload.scale_name,
            total_score=self._total_score,
            max_score=self._max_score,
            severity=self._severity,
            critical_item_positive=self._critical,
        )


# ───────────────────────── the single lifecycle test ───────────────────────


@pytest.mark.asyncio
async def test_full_session_lifecycle_cross_phase_coupling(
    db_session, seeded_session, caplog
) -> None:
    from sqlalchemy import select
    from src.core.config import Settings
    from src.models.audit_log import AuditLog
    from src.models.session import Session
    from src.services.chat import respond as chat_respond
    from src.services.questionnaire import score_with_ai

    patient, session_id = seeded_session
    settings = Settings()

    # ── Step 1: chat turn 1 — no escalation, session_state seeded ─────────
    await _post_user_turn(db_session, session_id, settings, "안녕하세요")
    turn1_state = {
        "asked_slot_counts": {"chief_complaint": 1},
        "risk_screening_incomplete": True,
        "clinical_escalation_required": False,
        "handoff_delivered": False,
    }
    ai1 = _StubChatAIClient([_chat_response(session_state=turn1_state, escalation=False)])
    payload1 = await chat_respond(
        db_session, ai_client=ai1, session_id=session_id, settings=settings, session_state=None
    )
    await db_session.commit()
    assert payload1["sessionState"] == turn1_state

    # ── Step 2: chat turn 2 — escalation fires (ADR-044 4 fields) ──────────
    await _post_user_turn(db_session, session_id, settings, "죽고 싶다는 생각이 계속 들어요")
    turn2_state = {
        "asked_slot_counts": {"chief_complaint": 1, "onset": 1},
        "risk_screening_incomplete": True,
        "clinical_escalation_required": True,
        "handoff_delivered": False,
    }
    ai2 = _StubChatAIClient([_chat_response(session_state=turn2_state, escalation=True)])
    payload2 = await chat_respond(
        db_session,
        ai_client=ai2,
        session_id=session_id,
        settings=settings,
        session_state=payload1["sessionState"],
    )
    await db_session.commit()
    assert payload2["clinicalEscalationRequired"] is True

    row = (await db_session.execute(select(Session).where(Session.id == session_id))).scalar_one()
    assert row.session_state == turn2_state
    assert row.clinical_escalation_required is True
    for field in (
        "asked_slot_counts",
        "risk_screening_incomplete",
        "clinical_escalation_required",
        "handoff_delivered",
    ):
        assert field in row.session_state, f"ADR-044 field {field!r} missing after persist"

    # H3 (partial, chat side): the chat response payload never carries any
    # caveat-shaped key — the strip logic in the survey-plan path has
    # nothing to accidentally strip here because caveats never touch chat.
    assert not any("caveat" in k.lower() for k in payload2), (
        "chat response payload unexpectedly carries a caveat-shaped field "
        f"— got keys {list(payload2)}"
    )

    # ── Step 3: domain infer — panic (proxy, crisis session) ───────────────
    from contracts.domain import DomainCandidate, DomainInferResponse
    from httpx import ASGITransport, AsyncClient

    panic_stub = _RecordingDomainAIClient(
        DomainInferResponse(domain_candidates=[DomainCandidate(domain="panic", confidence=0.8)])
    )
    app = _make_app_with_overrides(db_session, patient, panic_stub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_panic = await client.post(
            f"/api/v1/sessions/{session_id}/domain/infer",
            headers={"Authorization": "Bearer irrelevant-override-bypasses-decode"},
        )
    assert resp_panic.status_code == 200, resp_panic.text
    body_panic = resp_panic.json()
    assert body_panic["data"]["instrument"] == "GAD7"
    plan_panic = body_panic["data"]["plan"]
    assert "recommendation_caveat" not in plan_panic, (
        "H3 violated: proxy caveat leaked into the patient-facing plan response"
    )

    # H2: escalation (True, from Step 2) must have flowed into the
    # survey/plan request's crisis_triggered, and driven si_supplement.
    assert len(panic_stub.survey_plan_calls) == 1
    sent = panic_stub.survey_plan_calls[0]
    assert sent.crisis_triggered is True, (
        "H2 violated: clinical_escalation_required=True on the session did "
        "not flow into SurveyPlanRequest.crisis_triggered"
    )
    assert plan_panic["si_supplement"] is True, (
        "H2 violated: crisis_triggered=True + proxy-scale routing did not "
        "drive si_supplement=True end-to-end"
    )

    # caveat persisted to audit_logs (clinician-facing), never patient response.
    audit_rows = (
        await db_session.execute(select(AuditLog).where(AuditLog.resource_id == session_id))
    ).scalars().all()
    caveat_rows = [r for r in audit_rows if r.action == "survey.plan.proxy_caveat"]
    assert len(caveat_rows) == 1
    assert "GAD-7" in caveat_rows[0].audit_metadata["caveat"] or caveat_rows[0].audit_metadata["scale"] == "GAD-7"

    # H1: domain/infer must NOT have touched session_state at all.
    row_after_panic = (
        await db_session.execute(select(Session).where(Session.id == session_id))
    ).scalar_one()
    assert row_after_panic.session_state == turn2_state, (
        "H1 violated: domain/infer route interfered with the chat-persisted "
        "session_state"
    )

    # ── Step 4: domain infer — substance (proxy, second proxy check) ──────
    substance_stub = _RecordingDomainAIClient(
        DomainInferResponse(
            domain_candidates=[DomainCandidate(domain="substance", confidence=0.75)]
        )
    )
    app2 = _make_app_with_overrides(db_session, patient, substance_stub)
    transport2 = ASGITransport(app=app2)
    async with AsyncClient(transport=transport2, base_url="http://test") as client:
        resp_sub = await client.post(
            f"/api/v1/sessions/{session_id}/domain/infer",
            headers={"Authorization": "Bearer irrelevant-override-bypasses-decode"},
        )
    assert resp_sub.status_code == 200, resp_sub.text
    body_sub = resp_sub.json()
    assert body_sub["data"]["instrument"] == "AUDITC"
    plan_sub = body_sub["data"]["plan"]
    assert "recommendation_caveat" not in plan_sub
    assert substance_stub.survey_plan_calls[0].crisis_triggered is True
    audit_rows_sub = (
        await db_session.execute(select(AuditLog).where(AuditLog.resource_id == session_id))
    ).scalars().all()
    caveat_rows_sub = [r for r in audit_rows_sub if r.action == "survey.plan.proxy_caveat"]
    assert len(caveat_rows_sub) == 2, "expected a SECOND independent proxy-caveat audit row"

    # ── Step 5: domain infer — general/non-proxy (depression -> PHQ9, no caveat) ──
    general_stub = _RecordingDomainAIClient(
        DomainInferResponse(
            domain_candidates=[DomainCandidate(domain="depression", confidence=0.7)]
        )
    )
    app3 = _make_app_with_overrides(db_session, patient, general_stub)
    transport3 = ASGITransport(app=app3)
    async with AsyncClient(transport=transport3, base_url="http://test") as client:
        resp_gen = await client.post(
            f"/api/v1/sessions/{session_id}/domain/infer",
            headers={"Authorization": "Bearer irrelevant-override-bypasses-decode"},
        )
    assert resp_gen.status_code == 200, resp_gen.text
    body_gen = resp_gen.json()
    assert body_gen["data"]["instrument"] == "PHQ9"
    plan_gen = body_gen["data"]["plan"]
    assert plan_gen["si_supplement"] is False, (
        "native (non-proxy) routing must not get si_supplement even under "
        "crisis_triggered=True — CVR-030's own precondition (proxy AND crisis)"
    )
    audit_rows_gen = (
        await db_session.execute(select(AuditLog).where(AuditLog.resource_id == session_id))
    ).scalars().all()
    caveat_rows_gen = [r for r in audit_rows_gen if r.action == "survey.plan.proxy_caveat"]
    assert len(caveat_rows_gen) == 2, (
        "native (non-proxy) domain infer must NOT add a proxy_caveat audit row"
    )

    # H1 (again, after 3 domain/infer round trips): session_state still intact.
    row_final = (
        await db_session.execute(select(Session).where(Session.id == session_id))
    ).scalar_one()
    assert row_final.session_state == turn2_state, (
        "H1 violated: repeated domain/infer calls interfered with the "
        "chat-persisted session_state across the session's lifecycle"
    )

    # ── Step 6: score — canonical ai-server result used, zero local fallback ──
    with caplog.at_level(logging.WARNING, logger="src.services.questionnaire"):
        score_stub = _StubScoreAIClient(total_score=15, max_score=21, severity="severe", critical=True)
        total, severity, critical = await score_with_ai(
            "GAD7", [3, 3, 3, 3, 1, 1, 1], ai_client=score_stub, session_id=session_id
        )
    assert score_stub.called is True
    assert (total, severity, critical) == (15, "severe", True), (
        "score_with_ai did not return the ai-server canonical result"
    )
    fallback_logs = [
        r for r in caplog.records if "fell back to local cutoffs" in r.message
    ]
    assert len(fallback_logs) == 0, "unexpected local-cutoff fallback fired for an AI-success call"

    # ── Step 7: WS-reconnect reseed — verify DB-persisted session_state
    # (ADR-044 4 fields intact) re-seeds a fresh connection exactly. ────────
    reconnect_row = await db_session.execute(
        select(Session.patient_id, Session.session_state).where(Session.id == session_id)
    )
    reconnect_result = reconnect_row.one_or_none()
    assert reconnect_result is not None
    reloaded_state = reconnect_result[1]
    assert reloaded_state == turn2_state, (
        "WS-reconnect reseed query did not reload the exact last-persisted "
        "session_state — reconnect would silently drop fields or restart None"
    )
    for field in (
        "asked_slot_counts",
        "risk_screening_incomplete",
        "clinical_escalation_required",
        "handoff_delivered",
    ):
        assert field in reloaded_state, (
            f"WS-reconnect reseed dropped ADR-044 field {field!r}"
        )
