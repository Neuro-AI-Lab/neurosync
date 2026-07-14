"""BUG-040 regression test — `SurveyResultOutput.threshold_caveat`'s
Pydantic `Field(description=...)` is now current, describing the adopted
Korean-primary AUDIT-C threshold instead of the superseded international-
only one.

Filed: `error.md` BUG-040. `CVR-018` Q1/Q4 / `ADR-034` decision 1 moved the
AUDIT-C severity threshold from the byte-frozen international value
(male/unknown >= 4, female >= 3, "not reconciled with Korean-population
evidence") to a Korean-primary value (male/unknown >= 6, female >= 5,
"adopted"). `apps/ai-server/src/scoring/item_bank.py::AUDIT_C_THRESHOLD_
CAVEAT` (the actual runtime VALUE of this field for an administered
AUDIT-C outcome) and the module-level docstring in
`apps/ai-server/src/schemas/survey_result.py` were both correctly updated
(`git diff 2351e07 99c2f45` for that file). The per-field
`Field(description=...)` attached to `SurveyResultOutput.threshold_caveat`
itself (a separate string, surfaced in the generated OpenAPI schema for
any API consumer) was NOT updated at `99c2f45` -- it still read "AUDIT-C:
the byte-frozen male>=4/female>=3 threshold's non-reconciliation with
Korean-population evidence", directly contradicting the field's own
runtime value for every AUDIT-C-administered artifact.

**Fix (this file, post-BUG-040):** `survey_result.py:178-190`'s
`description=` was rewritten to state the adopted Korean-primary
male>=6/female>=5 threshold (basis: Lee JH et al. 2018 KNHANES) with the
international male>=4/female>=3 cutoff (Bush et al. 1998) now described
correctly as non-adopted, non-action-driving metadata -- matching the
module docstring's wording and the field's actual runtime value. This test
is inverted from its pre-fix form (which locked in the stale description
as a documented defect) to instead assert the fixed wording and the
absence of the stale fragment.
"""

from __future__ import annotations

from src.schemas.survey_result import SurveyResultOutput


def test_threshold_caveat_field_description_reflects_adopted_threshold_bug_040() -> None:
    """BUG-040 fix: the `threshold_caveat` field's OpenAPI-facing
    description now describes the adopted Korean-primary male>=6/female>=5
    threshold (matching `AUDIT_C_THRESHOLD_CAVEAT`'s actual runtime value
    and the module docstring), not the superseded pre-ADR-034 international-
    only threshold.
    """
    field_info = SurveyResultOutput.model_fields["threshold_caveat"]
    description = field_info.description
    assert description is not None

    # The adopted Korean-primary threshold is now present.
    assert "male>=6/female>=5" in description, (
        "expected the adopted Korean-primary male>=6/female>=5 threshold in "
        "threshold_caveat's Field description -- if this assertion fails, "
        "BUG-040 has regressed."
    )

    # The stale pre-ADR-034 fragment must be gone.
    assert "male>=4/female>=3" not in description, (
        "the stale international-only male>=4/female>=3 fragment must not appear "
        "unqualified in threshold_caveat's Field description -- BUG-040 regression"
    )
