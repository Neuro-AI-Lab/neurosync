"""Dev smoke — PLAN-2026-W30-INTEG Phase 3 (P3-1) `/ai/survey/plan` wiring +
substance->AUDITC mirror + proxy-scale caveat channel.

Not the durable qa suite (P3-2 owns that) — a developer smoke exercising the
new code paths end to end, offline/mocked throughout, before handoff.

Layers:
  1. Unit — `_DOMAIN_TO_INSTRUMENT["substance"]` mirror + `infer_instrument`/
     `infer_instrument_with_caveat` caveat resolution (native vs proxy).
  2. Unit — `AIClient.survey_plan` round-trips against a mock ai-server
     (`httpx.MockTransport`), no network.
  3. Integration — `POST /sessions/{id}/domain/infer` wired through the real
     ASGI app, `get_ai_client` overridden with a stub whose `survey_plan`
     returns a crafted `SurveyPlanResponse` — confirms `data.plan` carries
     scale/administration_mode/si_supplement/items, `recommendation_caveat`
     is stripped from the patient-facing response, and the caveat instead
     lands in a persisted `audit_logs` row (clinician/audit-reachable, not
     patient UI).

Hard constraints (mirrors test_phase2_domain_routing.py):
  - all live API keys forced to "" (BUG-052/058).
  - zero live LLM / outbound HTTP — guarded the same way.
  - throwaway `pgserver` only, no DGX Postgres touched.
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
        "apps/api/pyproject.toml/uv.lock yet — skipping gracefully rather "
        "than erroring the suite (mirrors test_phase2_domain_routing.py)."
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
    import httpx

    _real_post = httpx.AsyncClient.post

    async def _guarded_post(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> Any:
        transport = getattr(self, "_transport", None)
        if isinstance(transport, httpx.ASGITransport | httpx.MockTransport):
            return await _real_post(self, *args, **kwargs)
        raise AssertionError(
            "live HTTP call attempted — this test must only use a stub "
            "AIClient / dependency override, an in-process ASGITransport, or "
            "an httpx.MockTransport"
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _guarded_post)


# ─────────────────────── Layer 1: unit decision surface ───────────────────


def test_substance_mirrors_ai_server_canonical_scale() -> None:
    """(b) — mirrors ai-server's DOMAIN_TO_SCALE["substance"] == "AUDIT-C"
    (questionnaire_mapping.py:349); pre-fix this key was absent -> PHQ4."""
    from src.services.domain_routing import _DOMAIN_TO_INSTRUMENT

    assert _DOMAIN_TO_INSTRUMENT["substance"] == "AUDITC"


class _StubDomainAIClient:
    def __init__(self, *, response: Any) -> None:
        self._response = response

    async def domain_infer(self, payload: Any) -> Any:
        return self._response


@pytest.mark.asyncio
async def test_substance_top1_routes_to_auditc_not_phq4() -> None:
    from contracts.domain import DomainCandidate, DomainInferResponse

    from src.services.domain_routing import infer_instrument

    client = _StubDomainAIClient(
        response=DomainInferResponse(
            domain_candidates=[DomainCandidate(domain="substance", confidence=0.9)]
        )
    )
    result = await infer_instrument(ai_client=client, session_id=uuid.uuid4(), turns=[(1, "x")])
    assert result == "AUDITC"
    assert result != "PHQ4"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "domain,expect_caveat",
    [
        ("panic", True),
        ("substance", True),
        ("depression", False),
        ("anxiety", False),
        ("alcohol", False),
    ],
)
async def test_infer_instrument_with_caveat_only_for_proxy_routings(
    domain: str, expect_caveat: bool
) -> None:
    """(c) — proxy routings (panic->GAD7, substance->AUDITC) carry a
    non-None caveat; native routings (depression/anxiety/alcohol) do not."""
    from contracts.domain import DomainCandidate, DomainInferResponse

    from src.services.domain_routing import _PROXY_CAVEATS, infer_instrument_with_caveat

    client = _StubDomainAIClient(
        response=DomainInferResponse(
            domain_candidates=[DomainCandidate(domain=domain, confidence=0.9)]
        )
    )
    routing = await infer_instrument_with_caveat(
        ai_client=client, session_id=uuid.uuid4(), turns=[(1, "x")]
    )
    if expect_caveat:
        assert routing.caveat == _PROXY_CAVEATS[domain]
        assert routing.caveat is not None
    else:
        assert routing.caveat is None


@pytest.mark.asyncio
async def test_infer_instrument_bare_api_unaffected_by_caveat_refactor() -> None:
    """`infer_instrument` (bare-string API, used by existing durable tests)
    stays a thin string-returning wrapper after the refactor."""
    from contracts.domain import DomainCandidate, DomainInferResponse

    from src.services.domain_routing import infer_instrument

    client = _StubDomainAIClient(
        response=DomainInferResponse(
            domain_candidates=[DomainCandidate(domain="panic", confidence=0.9)]
        )
    )
    result = await infer_instrument(ai_client=client, session_id=uuid.uuid4(), turns=[(1, "x")])
    assert result == "GAD7"
    assert isinstance(result, str)


# ─────────────────── Layer 2: AIClient.survey_plan mock round-trip ────────


@pytest.mark.asyncio
async def test_ai_client_survey_plan_round_trips_against_mock_ai_server() -> None:
    """(a) — `AIClient.survey_plan` POSTs to `/ai/survey/plan` and parses a
    `SurveyPlanResponse` carrying scale/administration_mode/si_supplement/
    items, against a mock ai-server (`httpx.MockTransport`), no network."""
    import httpx
    from contracts.survey_plan import SurveyPlanRequest

    from src.services.ai_client import AIClient

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ai/survey/plan"
        return httpx.Response(
            200,
            json={
                "scale": "AUDIT-C",
                "administration_mode": "natural",
                "item_bank_version": "v1",
                "item_bank_provenance": "test-fixture",
                "instruction_ko": "다음 문항에 답해 주세요.",
                "items": [
                    {
                        "index": 1,
                        "text_ko": "문항1",
                        "response_min": 0,
                        "response_max": 4,
                    }
                ],
                "si_supplement": False,
                "si_supplement_item": None,
                "not_administrable_reason": None,
                "si_positive_action_ko": None,
                "si_positive_threshold": 1,
                "recommendation_caveat": "AUDIT-C는 알코올 전용 스크리너입니다.",
                "duplicate_administration": False,
                "refusal_guidance_ko": "거부 시 강요하지 마세요.",
            },
        )

    transport = httpx.MockTransport(_handler)
    client = AIClient(client=httpx.AsyncClient(transport=transport, base_url="http://ai-server.test"))
    response = await client.survey_plan(
        SurveyPlanRequest(recommended_questionnaire="AUDIT-C", recommendation_caveat=None)
    )
    assert response.scale == "AUDIT-C"
    assert response.administration_mode == "natural"
    assert response.si_supplement is False
    assert len(response.items) == 1
    assert response.recommendation_caveat == "AUDIT-C는 알코올 전용 스크리너입니다."


# ─────────────────────── Layer 3: integration path ────────────────────────


@pytest.fixture(scope="module")
def _throwaway_postgres_url() -> Any:
    pgdata = tempfile.mkdtemp(prefix="dev_phase3_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    srv.psql("CREATE DATABASE neurosync_dev_phase3;")
    uri = (
        srv.get_uri()
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("/postgres?", "/neurosync_dev_phase3?")
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
    import asyncio

    import alembic.command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import src.models  # noqa: F401
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
    from src.core.config import Settings
    from src.core.encryption import encrypt_str
    from src.models.session import Message, Session
    from src.models.user import User

    settings = Settings()
    patient = User(
        id=uuid.uuid4(),
        email=f"dev-phase3-{uuid.uuid4()}@example.test",
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
                "요즘 술이 아니라 다른 걸 자꾸 찾게 돼요",  # substance-shaped utterance
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
    """Stands in for `AIClient` at the route layer — `domain_infer` returns a
    substance top1 candidate, `survey_plan` returns a crafted plan echoing
    the request's `recommendation_caveat` (mirrors real ai-server's own
    pass-through echo, `apps/ai-server/src/routes/survey.py:205`)."""

    def __init__(self, domain_response: Any) -> None:
        self._domain_response = domain_response
        self.survey_plan_calls: list[Any] = []

    async def domain_infer(self, payload: Any) -> Any:
        return self._domain_response

    async def survey_plan(self, payload: Any) -> Any:
        from contracts.survey_plan import ItemBankItemPlan, SurveyPlanResponse

        self.survey_plan_calls.append(payload)
        return SurveyPlanResponse(
            scale=payload.recommended_questionnaire,
            administration_mode="natural",
            item_bank_version="v1",
            instruction_ko="다음 문항에 답해 주세요.",
            items=[
                ItemBankItemPlan(index=1, text_ko="문항1", response_min=0, response_max=4)
            ],
            si_supplement=False,
            recommendation_caveat=payload.recommendation_caveat,
        )


@pytest.mark.asyncio
async def test_domain_infer_route_wires_survey_plan_and_strips_caveat_from_patient_response(
    db_session, seeded_session_with_turn
) -> None:
    """(a)+(c) — the real `POST /sessions/{id}/domain/infer` route now calls
    `/ai/survey/plan` (mocked), returns `data.plan` with scale/
    administration_mode/si_supplement/items, NEVER forwards
    `recommendation_caveat` to the patient response, and persists the proxy
    caveat to `audit_logs` (clinician/audit-reachable) instead."""
    from contracts.domain import DomainCandidate, DomainInferResponse
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.models.audit_log import AuditLog

    patient, session_id = seeded_session_with_turn
    ai_response = DomainInferResponse(
        domain_candidates=[DomainCandidate(domain="substance", confidence=0.82)]
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
    assert body["data"]["instrument"] == "AUDITC"

    plan = body["data"]["plan"]
    assert plan["scale"] == "AUDIT-C"
    assert plan["administration_mode"] == "natural"
    assert plan["si_supplement"] is False
    assert len(plan["items"]) == 1
    assert "recommendation_caveat" not in plan, (
        "proxy caveat must never reach the patient-facing survey plan response"
    )

    # the plan request DID carry the caveat (clinician/audit channel populated).
    assert len(ai_stub.survey_plan_calls) == 1
    sent_request = ai_stub.survey_plan_calls[0]
    assert sent_request.recommendation_caveat is not None
    assert "AUDIT-C" in sent_request.recommendation_caveat

    # persisted, clinician/audit-reachable — never the patient response.
    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.resource_id == session_id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "survey.plan.proxy_caveat"
    assert rows[0].audit_metadata["scale"] == "AUDIT-C"
    assert "AUDIT-C" in rows[0].audit_metadata["caveat"]
