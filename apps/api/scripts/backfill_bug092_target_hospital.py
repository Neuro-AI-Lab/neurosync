"""One-off backfill for BUG-092 (error.md).

`scripts/seed_demo.py::_make_persona` never set `PatientProfile.
target_hospital_id` before this fix, so any DB already seeded from a
pre-fix run has every patient stuck at `target_hospital_id=NULL`, which
the org-scope filter (`src/services/clinician.py`, ISS-022/PR #22) treats
as invisible to every clinician. `_main` in `seed_demo.py` is idempotent by
early-exiting once `CLINICIAN_EMAIL` exists, so simply re-running the seed
does NOT repair already-seeded rows — this script does that repair
in-place instead.

Scope: this is a local single-tenant demo/dev DB with exactly one
organization and one clinician account (per ADR-049 — org-scope policy
itself is unchanged). Every `patient_profiles` row with a NULL
`target_hospital_id` is assigned to that one clinician's `organization_id`
(there is no other org for them to plausibly belong to in this DB). This
script is not meant to run against a multi-tenant/production DB with more
than one organization — it refuses to guess in that case.

Run from apps/api:
    uv run python -m scripts.backfill_bug092_target_hospital
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from src.db import SessionLocal
from src.models.patient_profile import PatientProfile
from src.models.user import Organization, User


async def _main() -> None:
    async with SessionLocal() as db:
        org_count_row = await db.execute(select(Organization.id))
        org_ids = [row[0] for row in org_count_row.all()]
        if len(org_ids) != 1:
            print(
                f"refusing to backfill: expected exactly 1 organization in this "
                f"DB, found {len(org_ids)} — this script only handles the "
                f"single-tenant local demo DB shape"
            )
            return

        clinician_row = await db.execute(
            select(User).where(User.email == "clinician@neurosync.demo")
        )
        clinician = clinician_row.scalar_one_or_none()
        if clinician is None:
            print("no demo clinician found — nothing to backfill")
            return
        if clinician.organization_id is None:
            print("demo clinician has no organization_id — nothing to backfill")
            return
        org_id = clinician.organization_id

        rows = await db.execute(
            select(PatientProfile, User)
            .join(User, User.id == PatientProfile.user_id)
            .where(
                User.role == "patient",
                PatientProfile.target_hospital_id.is_(None),
            )
        )
        pairs = rows.all()
        if not pairs:
            print("no NULL target_hospital_id rows among patients — nothing to do")
            return

        for profile, _user in pairs:
            profile.target_hospital_id = org_id

        await db.commit()
        print(f"backfilled {len(pairs)} patient_profiles.target_hospital_id -> {org_id}")


if __name__ == "__main__":
    asyncio.run(_main())
