"""Backfill questionnaire_results.type hyphen -> non-hyphen before 0010's CHECK narrows it (DB-F2).

0008 converted existing PHQ9/GAD7 rows to hyphenated form (PHQ-9/GAD-7) and
widened the CHECK to 5 hyphenated scales (PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C).
0010 narrows the CHECK to 4 *non-hyphenated* scales (PHQ9/GAD7/AUDITC/PHQ4)
without reversing 0008's UPDATE first — so any DB still carrying hyphenated
rows from the 0008 window fails 0010's `ADD CONSTRAINT` validation (existing
rows violate the new CHECK) and 0010 never applies.

DGX DB probe (2026-07-22, ai-server DATABASE_URL, single read-only
`SELECT type, COUNT(*) FROM questionnaire_results GROUP BY type ORDER BY
type`) confirmed this is not theoretical: live rows exist as `PHQ-9`(7),
`GAD-7`(5), `AUDIT-C`(1). A CHECK constraint, once successfully added,
enforces continuously on all rows — these hyphenated rows could not persist
under 0010's non-hyphenated CHECK if it were active, so this DB is still on
0008's hyphenated constraint and 0010's `ADD CONSTRAINT` has never
succeeded there.

This must therefore run *before* 0010, not after: a migration placed after
0010 in the chain cannot unblock 0010's own failing upgrade step (alembic
stops the `upgrade head` run at the first failing revision). Inserted as
0009a with 0010's `down_revision` repointed here, rather than rewriting
0010's own upgrade()/downgrade() bodies (0010 may already be applied
cleanly in other environments — this migration's upgrade() is idempotent
and a no-op wherever no hyphenated rows remain).

Caveat: retroactively inserting a node before an already-applied revision
is a known alembic pitfall for any OTHER environment already stamped at
head '0010' or later (that DB would never run 0009a). No such environment
is known to exist for this project; the DGX DB is confirmed pre-0010 by
the probe above, and a from-scratch install runs the full chain in order.

Revision ID: 0009a
Revises: 0009
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op

revision: str = "0009a"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None

# Hyphenated (0008-era) -> non-hyphenated (0010-target) scale name map.
# WHO-5 has no entry: it never had a non-hyphenated counterpart in 0010's
# CHECK (F4 longitudinal-only scale, out of F1-F3 scope) — see DB-F1 fix in
# apps/ai-server/src/rag/tooling/load_simulations.py for the loader side.
_HYPHEN_TO_PLAIN = {
    "PHQ-9": "PHQ9",
    "GAD-7": "GAD7",
    "AUDIT-C": "AUDITC",
    "PHQ-4": "PHQ4",
}


def upgrade() -> None:
    # Selective UPDATE — touches only rows still in hyphenated form; a no-op
    # wherever a DB has no such rows (idempotent, safe to re-run/re-apply).
    for hyphenated, plain in _HYPHEN_TO_PLAIN.items():
        op.execute(
            f"UPDATE questionnaire_results SET type='{plain}' WHERE type='{hyphenated}'"
        )
    # If a WHO-5 row exists here (none observed in the DGX probe), it is left
    # untouched and 0010's ADD CONSTRAINT will still reject it — WHO-5 was
    # never in scope for this table (F4 longitudinal only).


def downgrade() -> None:
    # Intentionally a no-op. By the time this downgrade runs, 0010's own
    # downgrade has already executed (alembic downgrades in reverse order):
    # it deleted AUDITC/PHQ4 rows and re-added the old non-hyphenated
    # CHECK (PHQ9/GAD7 only). Reversing PHQ9->PHQ-9/GAD7->GAD-7 here would
    # require dropping/re-adding that constraint again, only for 0008's own
    # downgrade to immediately no-op past it (0008's downgrade converts
    # PHQ-9/GAD-7 back to PHQ9/GAD7, which is already the state left after
    # this no-op) and re-install the same original 2-value constraint.
    # Leaving the data in non-hyphenated form here is harmless: 0008's
    # downgrade UPDATE statements simply match zero rows and its final
    # `CHECK (type IN ('PHQ9','GAD7'))` still holds for the actual data.
    pass
