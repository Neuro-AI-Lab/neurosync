"""Regression test for BUG-092 (open) — live-discovered during
PLAN-2026-W31-WEBDASH's real-stack apps/web <-> apps/api <-> DB
verification.

Live repro (2026-07-27, qa): logged in as the documented demo clinician
(`clinician@neurosync.demo`, `docs/PROGRESS.md:126-138`) through the real
`apps/web` HTTP path (login -> cookie -> server-component fetch ->
apps/api), and separately hit `GET /api/v1/clinician/patients` directly
against apps/api with the same bearer token. Both returned an EMPTY list
(`{"success":true,"data":[]}`) even though the demo DB had 5 real seeded
patients. `GET /api/v1/clinician/patients/{id}` and
`GET /api/v1/clinician/sessions/{id}` for real, existing IDs both 404'd.

Root cause: `scripts/seed_demo.py::_make_persona` (PR #13, `d04c808`) never
sets `PatientProfile.target_hospital_id` — every seeded patient has it
`NULL`. `src/services/clinician.py`'s org-scope filter (PR #22, `c718809`,
ISS-022) requires `PatientProfile.target_hospital_id == actor.
organization_id`; the demo clinician DOES have a real `organization_id`.
`NULL == <uuid>` is never true in SQL, so every demo patient is
structurally excluded — contradicting the module's own docstring ("every
authenticated clinician sees every patient").

This test reproduces the live shape (clinician with a real
`organization_id`, patient profile whose `target_hospital_id` mirrors
whatever `seed_demo.py` currently sets it to) against a throwaway schema
(no live/demo DB touched) and asserts the CORRECT, expected behavior —
patients in the clinician's care ARE visible. It was RED (documented the
bug) against pre-fix `target_hospital_id=None`; ADR-049 chose backfill
(seed sets `target_hospital_id=<clinician's organization_id>`, org-scope
policy unchanged) over relaxing the "no-org == visible" policy, so the
fixture below now mirrors that post-fix seed shape and the test is GREEN.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.patient_profile import PatientProfile

# conftest.py patches `PatientProfile.is_minor`'s column to
# `server_default=text("false")` (a TEST-ONLY convenience for callers that
# omit `is_minor`). SQLAlchemy's `Mapper._insert_cols_as_none` iterates
# every server_default and does a bare `not col.server_default` — a
# `TextClause` has no `__bool__`, so ANY insert of `PatientProfile` (this
# is the first test module in the suite to construct one via the ORM
# directly) raises `TypeError: Boolean value of this clause is not
# defined`. Not part of BUG-092 — a separate, pre-existing conftest gap
# with zero prior coverage — worked around locally here since we always
# pass `is_minor` explicitly and don't need the server_default at all.
from src.models.patient_profile import PatientProfile as _PatientProfile  # noqa: E402
from src.models.session import Session
from src.models.user import Organization, User
from src.services.clinician import get_patient_detail, get_session_detail, list_patients

_PatientProfile.__table__.c.is_minor.server_default = None


@pytest_asyncio.fixture
async def clinician_and_patient(db_session: AsyncSession):
    org = Organization(id=uuid.uuid4(), name="demo hospital", type="clinic")
    db_session.add(org)
    await db_session.flush()

    clinician = User(
        email="clinician@neurosync.demo.test",
        password_hash="x",
        role="clinician",
        organization_id=org.id,
    )
    db_session.add(clinician)
    await db_session.flush()

    patient = User(email="patient@demo.test", password_hash="x", role="patient")
    db_session.add(patient)
    await db_session.flush()

    profile = PatientProfile(
        user_id=patient.id,
        name_encrypted=b"not-really-encrypted-test-blob",
        birth_year=1996,
        is_minor=False,
        gender="female",
        # BUG-092 fix (ADR-049, option a): scripts/seed_demo.py now assigns
        # the demo clinician's organization_id to every seeded patient's
        # target_hospital_id, so this fixture mirrors seed_demo.py's
        # post-fix, real, current behavior. Org-scope policy itself
        # (services/clinician.py) is unchanged — this data now satisfies
        # it instead of violating it.
        target_hospital_id=org.id,
    )
    db_session.add(profile)
    await db_session.flush()

    session = Session(
        patient_id=patient.id,
        status="report_ready",
        submitted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.flush()

    return clinician, patient, session


@pytest.mark.asyncio
async def test_bug092_demo_shaped_patient_is_visible_in_list(
    db_session: AsyncSession, clinician_and_patient
):
    clinician, patient, _session = clinician_and_patient

    items = await list_patients(db_session, actor=clinician, limit=50)

    assert any(i.user_id == patient.id for i in items), (
        "BUG-092: a patient seeded exactly like scripts/seed_demo.py "
        "(target_hospital_id=None) must be visible to the demo clinician "
        "(organization_id set) — got an empty/missing list because the "
        "org-scope filter (PR #22) excludes NULL-hospital patients"
    )


@pytest.mark.asyncio
async def test_bug092_demo_shaped_patient_detail_is_reachable(
    db_session: AsyncSession, clinician_and_patient
):
    clinician, patient, _session = clinician_and_patient

    detail = await get_patient_detail(db_session, actor=clinician, patient_id=patient.id)

    assert detail is not None, (
        "BUG-092: get_patient_detail 404s (returns None) for a real, "
        "existing patient seeded exactly like the live demo data"
    )


@pytest.mark.asyncio
async def test_bug092_demo_shaped_session_detail_is_reachable(
    db_session: AsyncSession, clinician_and_patient
):
    clinician, _patient, session = clinician_and_patient

    detail = await get_session_detail(db_session, actor=clinician, session_id=session.id)

    assert detail is not None, (
        "BUG-092: get_session_detail 404s (returns None) for a real, "
        "existing session seeded exactly like the live demo data"
    )
