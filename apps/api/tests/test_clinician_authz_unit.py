"""Issue #22: pure-function unit tests for clinician→patient org authorization.

DB-free / async-free: verifies the PRD §0.1 access rule
("환자 데이터는 본인 + 본인이 진료받는 기관의 의료진만 read") independent of the
broken async DB test fixtures. The DB-integration coverage lives in
test_clinician.py (cross-org endpoint tests).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from src.services.clinician import _can_access_patient


def _actor(role: str, org):
    return SimpleNamespace(role=role, organization_id=org)


def test_super_admin_can_access_any_patient() -> None:
    assert _can_access_patient(_actor("super_admin", None), uuid.uuid4()) is True


def test_clinician_can_access_same_org_patient() -> None:
    org = uuid.uuid4()
    assert _can_access_patient(_actor("clinician", org), org) is True


def test_clinician_cannot_access_other_org_patient() -> None:
    assert _can_access_patient(_actor("clinician", uuid.uuid4()), uuid.uuid4()) is False


def test_org_admin_cannot_access_other_org_patient() -> None:
    assert _can_access_patient(_actor("org_admin", uuid.uuid4()), uuid.uuid4()) is False


def test_orgless_clinician_denied() -> None:
    assert _can_access_patient(_actor("clinician", None), uuid.uuid4()) is False


def test_patient_without_hospital_denied() -> None:
    org = uuid.uuid4()
    assert _can_access_patient(_actor("clinician", org), None) is False
