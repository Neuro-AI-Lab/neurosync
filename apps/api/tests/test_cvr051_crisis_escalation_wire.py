"""Committed regression test for CVR-051 (clinical-validator) — the
`/ai/chat/respond` crisis-signal wire-drop.

CVR-051's finding: ai-server runs its OWN, second, conversation-history-
aware `SafetyClassifierAgent` invocation inside its orchestrator
(`apps/ai-server/src/agents/orchestrator.py`). When that gate fires a
genuine crisis (`orch_result.crisis_triggered=True`), the signal was
dropped end-to-end — no `RiskEvent`, no `risk:detected` WS emission, no
escalation flag; only the crisis message text (with hotline numbers)
reached the client as an ordinary chat bubble.

The fix (this pass, RM-1): `ChatResponse.crisis_triggered` (new field,
mirrors `DialogueOutput.crisis_triggered`, itself new) is now consumed by
`src/services/chat.py::respond()`, which reuses the SAME
`handle_safety_result` escalation mechanism the pre-gate safety path
already uses to persist a `RiskEvent` and produce the `risk:detected`
payload — returned here as `respond()`'s `riskDetected` key (popped and
re-emitted as its own WS frame by `src/api/v1/sessions.py::_handle_message`,
verified separately by inspection, not re-tested here since it requires a
live WebSocket harness).

Deliberately independent of `tests/conftest.py` (BUG-057) — same pattern
as `test_phase1_session_state_persistence.py`: own throwaway `pgserver`
Postgres, own migrated engine, `_StubAIClient` (no `httpx`, no live LLM).

Hard constraints:
  - all live API keys forced to "" (BUG-052 — unset alone does not gate).
  - zero live LLM / outbound HTTP: `httpx.AsyncClient.post` monkeypatched
    to raise if reached at all.
  - no DGX Postgres touched — `pgserver` throwaway instance only.
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
        "dependency manifest); skipping gracefully rather than erroring."
    ),
)

# All live keys forced empty BEFORE any src.* import touches Settings()
# (BUG-052: unset alone does not gate live-only paths; only "" does).
for _key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "UPSTAGE_API_KEY",
    "SKT_A_X_API_KEY",
):
    os.environ[_key] = ""


@pytest.fixture(scope="module")
def _throwaway_postgres_url() -> Any:
    pgdata = tempfile.mkdtemp(prefix="qa_cvr051_pgdata_")
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    srv.psql("CREATE DATABASE neurosync_qa_cvr051;")
    uri = (
        srv.get_uri()
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("/postgres?", "/neurosync_qa_cvr051?")
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
def _migrated_engine(_throwaway_postgres_url: str):
    """Schema via `Base.metadata.create_all` (same TEST-ONLY workaround
    `tests/conftest.py` uses — `patient_profiles.is_minor` is a Postgres
    GENERATED column whose expression uses `CURRENT_DATE`, which Postgres
    rejects as "not immutable" for a STORED generated column outside a
    real `alembic` migration's raw SQL). `RiskEvent`'s table (this fix's
    only DB dependency, per the RM-1 brief's no-migration-needed
    constraint) is created here identically to how it exists at head —
    this file makes no claim about any specific migration, only that the
    fix's own read/write against `RiskEvent` behaves as expected."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import src.models  # noqa: F401 — register all tables on Base.metadata
    from src.db import Base
    from src.models.patient_profile import PatientProfile

    is_minor_col = PatientProfile.__table__.c.is_minor
    is_minor_col.computed = None
    is_minor_col.server_default = text("false")

    async def _create_schema() -> None:
        engine = create_async_engine(_throwaway_postgres_url, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(_create_schema())
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
    from src.models.session import Session
    from src.models.user import User

    patient = User(
        id=uuid.uuid4(),
        email=f"qa-cvr051-{uuid.uuid4()}@example.test",
        password_hash="not-a-real-hash",
        role="patient",
    )
    db_session.add(patient)
    await db_session.flush()
    sess = Session(id=uuid.uuid4(), patient_id=patient.id, status="in_progress")
    db_session.add(sess)
    await db_session.commit()
    return sess.id


class _StubAIClient:
    """No `httpx`, no live LLM — scripted `ChatResponse` per call."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[Any] = []

    async def chat_respond(self, payload: Any) -> Any:
        self.calls.append(payload)
        return self._responses.pop(0)

    async def slots_extract(self, payload: Any) -> Any:
        from contracts.slots import SlotsExtractResponse

        return SlotsExtractResponse(extracted_slots={})


def _crisis_response(
    *, risk_level: str = "critical", risk_categories: list[str] | None = None
) -> Any:
    from contracts.chat import ChatResponse

    return ChatResponse(
        assistant_response="지금 많이 힘드시군요. 자살예방상담전화 1393으로 연락해보세요.",
        session_state={
            "asked_slot_counts": {},
            "risk_screening_incomplete": True,
            "clinical_escalation_required": False,
            "handoff_delivered": False,
        },
        risk_level=risk_level,
        requires_human_review=True,
        crisis_triggered=True,
        risk_categories=risk_categories or [],
    )


def _normal_response() -> Any:
    from contracts.chat import ChatResponse

    return ChatResponse(
        assistant_response="네, 조금 더 말씀해주시겠어요?",
        session_state={
            "asked_slot_counts": {"chief_complaint": 1},
            "risk_screening_incomplete": True,
            "clinical_escalation_required": False,
            "handoff_delivered": False,
        },
        risk_level="low",
        requires_human_review=False,
        crisis_triggered=False,
    )


@pytest.fixture(autouse=True)
def _forbid_live_http(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    async def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "live HTTP call attempted — this test must only use _StubAIClient"
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _forbidden)


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


@pytest.mark.asyncio
async def test_orchestrator_crisis_produces_risk_event_and_wire_payload(
    db_session, seeded_session
):
    """CVR-051 core fix: `crisis_triggered=True` on the ai-server response
    must produce a persisted `RiskEvent` (HIGH/CRITICAL, same table the
    pre-gate path writes) and a `riskDetected` payload shaped exactly like
    `handle_safety_result`'s own `RiskDetectedPayload` — not just the
    chat-bubble text."""
    from sqlalchemy import select

    from src.core.config import Settings
    from src.models.session import RiskEvent
    from src.services.chat import respond as chat_respond

    session_id = seeded_session
    settings = Settings()

    await _post_user_turn(db_session, session_id, settings, "다 끝내고 싶어요")
    ai_client = _StubAIClient([_crisis_response(risk_level="critical")])

    payload = await chat_respond(
        db_session,
        ai_client=ai_client,
        session_id=session_id,
        settings=settings,
        session_state=None,
    )
    await db_session.commit()

    assert payload is not None
    # The crisis message text itself is unchanged/unaffected by this fix.
    assert "1393" in payload["content"]

    risk_detected = payload["riskDetected"]
    assert risk_detected is not None, (
        "CVR-051 regression: crisis_triggered=True produced no riskDetected "
        "payload — the signal was dropped again"
    )
    assert risk_detected["level"] == "critical"
    assert risk_detected["routeTo"] in ("/emergency", "/self_hotline")
    assert risk_detected["hotlines"]
    assert uuid.UUID(risk_detected["riskEventId"])

    rows = await db_session.execute(
        select(RiskEvent).where(RiskEvent.session_id == session_id)
    )
    events = rows.scalars().all()
    assert len(events) == 1, "exactly one RiskEvent must be persisted for this crisis turn"
    assert events[0].level == "critical"
    assert events[0].status == "detected"


@pytest.mark.asyncio
async def test_non_crisis_turn_produces_no_risk_event(db_session, seeded_session):
    """Negative control: an ordinary (non-crisis) turn must NOT create a
    RiskEvent or a riskDetected payload — this fix is additive, not a
    blanket escalation on every turn."""
    from sqlalchemy import select

    from src.core.config import Settings
    from src.models.session import RiskEvent
    from src.services.chat import respond as chat_respond

    session_id = seeded_session
    settings = Settings()

    await _post_user_turn(db_session, session_id, settings, "요즘 잠을 잘 못 자요")
    ai_client = _StubAIClient([_normal_response()])

    payload = await chat_respond(
        db_session,
        ai_client=ai_client,
        session_id=session_id,
        settings=settings,
        session_state=None,
    )
    await db_session.commit()

    assert payload is not None
    assert payload["riskDetected"] is None

    rows = await db_session.execute(
        select(RiskEvent).where(RiskEvent.session_id == session_id)
    )
    assert rows.scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("risk_categories", "expected_category"),
    [
        pytest.param(["suicidal_ideation"], "suicide", id="suicidal_ideation-suicide"),
        pytest.param(["harm_to_others"], "other_harm", id="harm_to_others-other_harm"),
        pytest.param(["self_harm"], "self_harm", id="self_harm-self_harm"),
        pytest.param(
            [],
            "self_harm",
            id="empty-fallback-self_harm-NOT-other_harm",
        ),
        pytest.param(
            ["distress", "harm_to_others", "suicidal_ideation"],
            "suicide",
            id="multi-tag-priority-resolves-to-suicide",
        ),
    ],
)
async def test_orchestrator_crisis_category_threads_to_riskevent(
    db_session, seeded_session, risk_categories, expected_category
):
    """BUG-059/CVR-051 category-fidelity follow-up: `ChatResponse.
    risk_categories` (ai-server's real category signal, threaded through
    `SafetyStatus.categories` -> `DialogueOutput.risk_categories`) must
    resolve to the CORRECT `RiskCategory` on the persisted `RiskEvent` and
    the wire `riskDetected.category`, per `_CRISIS_CATEGORY_PRIORITY`'s
    documented priority order — not the pre-fix hardcoded `OTHER_HARM`
    placeholder. The empty-list case is the fail-closed/no-signal case and
    must fall back to `self_harm` (the crisis-bypass pathway's own
    self-harm/suicide-oriented trigger), never silently default to
    `other_harm` again."""
    from sqlalchemy import select

    from src.core.config import Settings
    from src.models.session import RiskEvent
    from src.services.chat import respond as chat_respond

    session_id = seeded_session
    settings = Settings()

    await _post_user_turn(db_session, session_id, settings, "다 끝내고 싶어요")
    ai_client = _StubAIClient(
        [_crisis_response(risk_level="critical", risk_categories=risk_categories)]
    )

    payload = await chat_respond(
        db_session,
        ai_client=ai_client,
        session_id=session_id,
        settings=settings,
        session_state=None,
    )
    await db_session.commit()

    assert payload is not None
    risk_detected = payload["riskDetected"]
    assert risk_detected is not None
    assert risk_detected["category"] == expected_category, (
        f"risk_categories={risk_categories!r} should map to "
        f"{expected_category!r}, wire payload got "
        f"{risk_detected['category']!r}"
    )

    rows = await db_session.execute(
        select(RiskEvent).where(RiskEvent.session_id == session_id)
    )
    events = rows.scalars().all()
    assert len(events) == 1
    assert events[0].category == expected_category, (
        "persisted RiskEvent.category must match the mapped value, not the "
        "old hardcoded OTHER_HARM placeholder"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("risk_categories", "expected_category", "expected_evidence_subset", "forbidden_evidence"),
    [
        pytest.param(
            ["suicidal_ideation", "harm_to_others"],
            "suicide",
            [
                "ai_category:suicidal_ideation",
                "ai_category:harm_to_others",
                "category_source:detected",
            ],
            ["category_source:fallback_default"],
            id="cooccurring-suicide-plus-harm_to_others-both-tags-survive",
        ),
        pytest.param(
            [],
            "self_harm",
            ["category_source:fallback_default"],
            ["ai_category:", "category_source:detected"],
            id="empty-fallback-marked-as-fallback-not-detected",
        ),
        pytest.param(
            ["self_harm"],
            "self_harm",
            ["ai_category:self_harm", "category_source:detected"],
            ["category_source:fallback_default"],
            id="detected-only-self_harm-marked-detected",
        ),
    ],
)
async def test_crisis_evidence_keywords_persist_on_riskevent(
    db_session,
    seeded_session,
    risk_categories,
    expected_category,
    expected_evidence_subset,
    forbidden_evidence,
):
    """CVR-051 RM-8 follow-up (findings 1+2), verified at the persisted
    `RiskEvent` level (not just the `_crisis_evidence_keywords` helper in
    isolation): the JSONB `RiskEvent.ai_evidence["matched_keywords"]`
    actually written to the DB must carry the FULL category tag list (a
    co-occurring `harm_to_others` alongside a `suicidal_ideation`-derived
    `SUICIDE` primary category must be recoverable) and must distinguish a
    genuinely-detected category list from the empty-list safe-default
    fallback. `RiskEvent.category` (the single-value priority-mapped
    primary) must be unaffected by this evidence-only change."""
    from sqlalchemy import select

    from src.core.config import Settings
    from src.models.session import RiskEvent
    from src.services.chat import respond as chat_respond

    session_id = seeded_session
    settings = Settings()

    await _post_user_turn(db_session, session_id, settings, "다 끝내고 싶어요")
    ai_client = _StubAIClient(
        [_crisis_response(risk_level="critical", risk_categories=risk_categories)]
    )

    payload = await chat_respond(
        db_session,
        ai_client=ai_client,
        session_id=session_id,
        settings=settings,
        session_state=None,
    )
    await db_session.commit()

    assert payload is not None
    risk_detected = payload["riskDetected"]
    assert risk_detected is not None
    assert risk_detected["category"] == expected_category

    rows = await db_session.execute(
        select(RiskEvent).where(RiskEvent.session_id == session_id)
    )
    events = rows.scalars().all()
    assert len(events) == 1, "exactly one RiskEvent must be persisted for this crisis turn"
    persisted = events[0]
    assert persisted.category == expected_category, (
        "single-value primary category mapping must be unchanged by the "
        "evidence-only fix"
    )

    ai_evidence = persisted.ai_evidence
    assert isinstance(ai_evidence, dict), "ai_evidence must be the JSONB dict, not None/omitted"
    matched_keywords = ai_evidence["matched_keywords"]
    assert isinstance(matched_keywords, list)
    for expected in expected_evidence_subset:
        assert expected in matched_keywords, (
            f"persisted RiskEvent.ai_evidence['matched_keywords']={matched_keywords!r} "
            f"missing expected tag {expected!r} for risk_categories={risk_categories!r}"
        )
    for forbidden in forbidden_evidence:
        assert not any(kw.startswith(forbidden) or kw == forbidden for kw in matched_keywords), (
            f"persisted RiskEvent.ai_evidence['matched_keywords']={matched_keywords!r} "
            f"unexpectedly contains {forbidden!r} for risk_categories={risk_categories!r}"
        )


@pytest.mark.asyncio
async def test_patient_facing_surfaces_carry_no_evidence_or_category_tags(
    db_session, seeded_session
):
    """NFR v3-2: `matched_keywords`/`ai_category:*`/evidence must never reach
    the patient-facing wire. Checks BOTH the `riskDetected` payload dict AND
    the full `ai:complete` dict (`payload` itself, minus the `riskDetected`
    key the WS gateway pops off per `chat.py`'s own docstring) for any
    evidence-shaped key or `ai_category:`-prefixed string value, recursively
    — not just an exact-keys check, so a nested leak would also be caught."""
    import json

    from src.core.config import Settings
    from src.services.chat import respond as chat_respond

    session_id = seeded_session
    settings = Settings()

    await _post_user_turn(db_session, session_id, settings, "다 끝내고 싶어요")
    ai_client = _StubAIClient(
        [
            _crisis_response(
                risk_level="critical",
                risk_categories=["suicidal_ideation", "harm_to_others"],
            )
        ]
    )

    payload = await chat_respond(
        db_session,
        ai_client=ai_client,
        session_id=session_id,
        settings=settings,
        session_state=None,
    )
    await db_session.commit()

    assert payload is not None
    risk_detected = payload["riskDetected"]
    assert risk_detected is not None

    # riskDetected: exact key set is the documented RiskDetectedPayload shape —
    # no evidence/matched_keywords/ai_category key was added to it.
    assert set(risk_detected.keys()) == {
        "level",
        "category",
        "riskEventId",
        "triggerMessageId",
        "routeTo",
        "hotlines",
        "reason",
    }

    # Full ai:complete dict (everything `respond()` returns, patient-facing
    # once the WS gateway pops `riskDetected` back out into its own frame) —
    # serialize and scan for any leaked evidence marker string anywhere,
    # including nested values.
    serialized = json.dumps(payload, default=str)
    assert "matched_keywords" not in serialized
    assert "ai_category:" not in serialized
    assert "category_source:" not in serialized
