"""Committed regression test for Phase 2 domain routing — PRD §4/§5.4
(`docs/ai/integration_prd_f1f3_hospital.md`) completion criteria, and the
panic->GAD7 fix (`_DOMAIN_TO_INSTRUMENT["panic"] = "GAD7"`,
ADR-046 #2 / contract4 fix).

Three layers, offline/mocked throughout:
  1. Unit decision surface — `src.services.domain_routing.infer_instrument`
     exercised directly for all 9 `DomainName` values plus the fallback
     edge cases (below-confidence, no-candidate, empty-turns, ai-server
     exception).
  2. Integration path — the real `POST /sessions/{id}/domain/infer` route
     (`src/api/v1/sessions.py::infer_domain`), wired through `create_app()`,
     with `get_ai_client` mocked (no live HTTP) and DB/auth dependencies
     overridden against a throwaway Postgres.
  3. VP-004-style panic scenario reproduction — a panic-shaped top1
     candidate (as VP-004's `fluctuating_panic_recurrence` arc would
     naturally elicit) routed end-to-end through the same integration path,
     confirming it lands on GAD7 and not the pre-fix PHQ4 fallback.

Deliberately independent of `tests/conftest.py` (BUG-058: the sync
`starlette.TestClient` + anyio-portal cross-loop defect in that fixture set
makes HTTP-surface tests unreliable there) — this module builds its own
throwaway Postgres (`pgserver`, no-root, DGX never touched) and uses
`httpx.AsyncClient(transport=ASGITransport(app=app))` for the one test that
needs to hit the real ASGI route, exactly the pattern
`test_phase1_session_state_persistence.py` established.

Hard constraints:
  - all live API keys forced to "" (BUG-052/058 — unset alone does not gate;
    only "" reliably disables live-only paths).
  - zero live LLM / outbound HTTP: `AIClient` is replaced everywhere by an
    in-process stub (unit layer) or a `get_ai_client` dependency override
    returning a stub (integration layer); `httpx.AsyncClient.post` is
    monkeypatched to raise if anything ever reaches it, as a hard guard.
  - no DGX Postgres (223.194.33.26:28881) touched — `pgserver` throwaway
    instance only, torn down at test end.
"""

from __future__ import annotations

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
        "apps/api/pyproject.toml/uv.lock yet (qa does not edit the "
        "dependency manifest — see REV-008 resolution note in error.md); "
        "skipping gracefully rather than erroring the suite."
    ),
)

# All live keys forced empty BEFORE any src.* import touches Settings()
# (BUG-052/058: unset alone does not gate live-only paths; only "" does).
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
    """Hard guard: any attempt to actually reach the network via httpx (the
    real `AIClient`'s transport, which defaults to a real socket transport)
    fails the test loudly instead of silently succeeding against a
    live/mocked server. In-process ASGI-transport calls (the httpx test
    client driving `ASGITransport(app=app)` against our own app object, used
    by the integration-layer tests below) are explicitly allowed through —
    those never leave the process."""
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


# ─────────────────────────── Layer 1: unit decision surface ───────────────

# The 9-domain decision table (PRD §4/§5.4 P2-2). Domains with no dedicated
# scale (substance/trauma/sleep/psychosis/other) fall to FALLBACK_INSTRUMENT.
DOMAIN_TO_EXPECTED_INSTRUMENT: dict[str, str] = {
    "anxiety": "GAD7",
    "depression": "PHQ9",
    "alcohol": "AUDITC",
    # PLAN-2026-W30-INTEG P3-1(b): mirrors ai-server canonical
    # DOMAIN_TO_SCALE["substance"] == "AUDIT-C" (previously PHQ4 fallback gap,
    # CVR-049 register #3).
    "substance": "AUDITC",
    "trauma": "PHQ4",
    "sleep": "PHQ4",
    "psychosis": "PHQ4",
    "other": "PHQ4",
    "panic": "GAD7",  # ADR-046 #2 fix under regression test here
}


class _StubDomainAIClient:
    """Duck-typed stand-in for `AIClient` exposing only `domain_infer` — no
    `httpx`, no live call."""

    def __init__(self, *, response: Any = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.called = False

    async def domain_infer(self, payload: Any) -> Any:
        self.called = True
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "domain,expected_instrument",
    sorted(DOMAIN_TO_EXPECTED_INSTRUMENT.items()),
)
async def test_domain_decision_table(domain: str, expected_instrument: str) -> None:
    """PRD §5.4 P2-2 — 9-domain top1 candidate -> resolved instrument."""
    from contracts.domain import DomainCandidate, DomainInferResponse

    from src.services.domain_routing import infer_instrument

    response = DomainInferResponse(
        domain_candidates=[DomainCandidate(domain=domain, confidence=0.9)]
    )
    client = _StubDomainAIClient(response=response)

    result = await infer_instrument(
        ai_client=client,
        session_id=uuid.uuid4(),
        turns=[(1, "관련 발화")],
    )

    assert result == expected_instrument, (
        f"domain={domain!r} expected -> {expected_instrument}, got {result}"
    )
    assert client.called, "ai_client.domain_infer was not invoked"


@pytest.mark.asyncio
async def test_below_confidence_falls_back_to_phq4() -> None:
    """Candidate present but below MIN_CONFIDENCE (0.35) -> PHQ4."""
    from contracts.domain import DomainCandidate, DomainInferResponse

    from src.services.domain_routing import infer_instrument

    response = DomainInferResponse(
        domain_candidates=[DomainCandidate(domain="panic", confidence=0.10)]
    )
    client = _StubDomainAIClient(response=response)

    result = await infer_instrument(
        ai_client=client, session_id=uuid.uuid4(), turns=[(1, "hi")]
    )
    assert result == "PHQ4"


@pytest.mark.asyncio
async def test_no_candidate_falls_back_to_phq4() -> None:
    """Empty domain_candidates list -> PHQ4."""
    from contracts.domain import DomainInferResponse

    from src.services.domain_routing import infer_instrument

    client = _StubDomainAIClient(response=DomainInferResponse(domain_candidates=[]))

    result = await infer_instrument(
        ai_client=client, session_id=uuid.uuid4(), turns=[(1, "hi")]
    )
    assert result == "PHQ4"


@pytest.mark.asyncio
async def test_empty_turns_falls_back_to_phq4_without_calling_ai_client() -> None:
    """No utterances -> immediate PHQ4 fallback, ai_client never touched."""
    from src.services.domain_routing import infer_instrument

    client = _StubDomainAIClient(exc=AssertionError("must not be called"))

    result = await infer_instrument(ai_client=client, session_id=uuid.uuid4(), turns=[])
    assert result == "PHQ4"
    assert client.called is False


@pytest.mark.asyncio
async def test_ai_server_exception_falls_back_to_phq4() -> None:
    """Any exception from the ai-server call (timeout/5xx/validation) -> PHQ4,
    never raised out of `infer_instrument` ("라우팅은 실패하지 않는다")."""
    from src.services.domain_routing import infer_instrument

    client = _StubDomainAIClient(exc=RuntimeError("simulated ai-server 5xx"))

    result = await infer_instrument(
        ai_client=client, session_id=uuid.uuid4(), turns=[(1, "hi")]
    )
    assert result == "PHQ4"


# ─────────────────────── Layer 2 & 3: integration path ────────────────────


@pytest.fixture(scope="module")
def _throwaway_postgres_url() -> Any:
    """Self-contained throwaway Postgres — no conftest, no DGX (mirrors
    test_phase1_session_state_persistence.py's fixture verbatim)."""
    pgdata = tempfile.mkdtemp(prefix="qa_phase2_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    srv.psql("CREATE DATABASE neurosync_qa_phase2;")
    uri = (
        srv.get_uri()
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("/postgres?", "/neurosync_qa_phase2?")
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
    """Same alembic-0010->head bootstrap as test_phase1 — brings the schema
    fully to head (including the tables `domain/infer`'s route touches:
    sessions, messages, users)."""
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
                await conn.execute(
                    text("ALTER TABLE sessions DROP COLUMN session_state")
                )
                await conn.execute(
                    text(
                        "ALTER TABLE sessions DROP COLUMN clinical_escalation_required"
                    )
                )
        finally:
            await baseline_engine.dispose()

    asyncio.run(_create_pre_0011_baseline())

    alembic_dir = os.path.join(os.path.dirname(__file__), "..", "alembic")
    cfg = Config()
    cfg.set_main_option("script_location", os.path.abspath(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", _throwaway_postgres_url)
    alembic.command.stamp(cfg, "0010")
    alembic.command.upgrade(cfg, "head")

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
async def seeded_session_with_turn(db_session) -> Any:
    """A patient + an in_progress session with one decryptable user message
    — the route's `turns` source and the FK graph `domain/infer` needs."""
    from src.core.config import Settings
    from src.core.encryption import encrypt_str
    from src.models.session import Message, Session
    from src.models.user import User

    settings = Settings()
    patient = User(
        id=uuid.uuid4(),
        email=f"qa-phase2-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role="patient",
    )
    db_session.add(patient)
    await db_session.flush()

    sess = Session(id=uuid.uuid4(), patient_id=patient.id, status="in_progress")
    db_session.add(sess)
    await db_session.flush()

    message_id = uuid.uuid4()
    aad = f"messages.content:{sess.id}:{message_id}".encode()
    db_session.add(
        Message(
            id=message_id,
            session_id=sess.id,
            role="user",
            content_encrypted=encrypt_str(
                "요즘 갑자기 숨이 막히고 심장이 두근거려요",  # panic-shaped utterance
                aad=aad,
                settings=settings,
            ),
            input_modality="text",
        )
    )
    await db_session.commit()
    return patient, sess.id


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


class _StubRouteAIClient:
    """`get_ai_client`-override stand-in exposing `domain_infer` +
    `survey_plan` — PLAN-2026-W30-INTEG P3-1(a) added a `survey_plan` call to
    the same route, so the double needs both methods now. `survey_plan`
    returns a minimal echo response (mirrors real ai-server's own
    pass-through of `recommendation_caveat`)."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[Any] = []

    async def domain_infer(self, payload: Any) -> Any:
        self.calls.append(payload)
        return self._response

    async def survey_plan(self, payload: Any) -> Any:
        from contracts.survey_plan import SurveyPlanResponse

        return SurveyPlanResponse(
            scale=payload.recommended_questionnaire,
            administration_mode="natural",
            si_supplement=False,
            recommendation_caveat=payload.recommendation_caveat,
        )


@pytest.mark.asyncio
async def test_domain_infer_route_resolves_panic_to_gad7(
    db_session, seeded_session_with_turn
) -> None:
    """Integration path: `POST /sessions/{id}/domain/infer` wired through the
    real ASGI app (`create_app()`), with `get_ai_client` mocked returning a
    panic top1 candidate — confirms the wire-level response resolves to
    GAD7, offline."""
    from contracts.domain import DomainCandidate, DomainInferResponse
    from httpx import ASGITransport, AsyncClient

    patient, session_id = seeded_session_with_turn
    ai_response = DomainInferResponse(
        domain_candidates=[DomainCandidate(domain="panic", confidence=0.82)]
    )
    ai_stub = _StubRouteAIClient(ai_response)
    app = _make_app_with_overrides(db_session, patient, ai_stub)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/sessions/{session_id}/domain/infer",
            headers={"Authorization": "Bearer irrelevant-override-bypasses-decode"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["instrument"] == "GAD7", (
        f"panic top1 candidate did not resolve to GAD7 at the wire level: {body}"
    )
    assert len(ai_stub.calls) == 1, "route did not call ai_client.domain_infer exactly once"
    # NFR v3-2: no domain/disease string ever leaves the module in the response.
    assert "panic" not in resp.text.lower()


@pytest.mark.asyncio
async def test_vp004_style_panic_scenario_reproduces_gad7_not_phq4_fallback(
    db_session, seeded_session_with_turn
) -> None:
    """PRD §4/§7 'VP-004류 panic 시나리오 재현' — a panic-shaped candidate as
    VP-004's `fluctuating_panic_recurrence` arc would elicit (recurrent
    panic-attack-pattern top1, moderate-high confidence, alongside a lower
    -confidence secondary anxiety candidate reflecting the DSM-5 comorbidity
    the scenario models) must route to GAD7 end-to-end, not the pre-fix
    PHQ4 fallback that `_DOMAIN_TO_INSTRUMENT` lacked before ADR-046 #2."""
    from contracts.domain import DomainCandidate, DomainInferResponse
    from httpx import ASGITransport, AsyncClient

    patient, session_id = seeded_session_with_turn
    vp004_style_response = DomainInferResponse(
        domain_candidates=[
            DomainCandidate(domain="panic", confidence=0.77),
            DomainCandidate(domain="anxiety", confidence=0.41),
        ],
        summary="recurrent fluctuating panic pattern (VP-004-style)",
    )
    ai_stub = _StubRouteAIClient(vp004_style_response)
    app = _make_app_with_overrides(db_session, patient, ai_stub)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/sessions/{session_id}/domain/infer",
            headers={"Authorization": "Bearer irrelevant-override-bypasses-decode"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["instrument"] == "GAD7", (
        "VP-004-style panic scenario regressed to the pre-fix PHQ4 fallback "
        f"instead of routing panic top1 -> GAD7: {body}"
    )
    assert body["data"]["instrument"] != "PHQ4"
