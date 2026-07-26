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

DB-F2b (2026-07-26, live DGX replay): the fix above shipped 0009a's
UPDATE-before-0010 ordering, but missed a second constraint-order bug in
0009a itself. At the point 0009a's upgrade() runs, 0008's CHECK
(`ck_questionnaire_results_type`, hyphenated values only — see 0008's
`create_check_constraint`) is still the live constraint on the table;
0010 is the migration that eventually narrows it, and 0010 runs *after*
0009a. So the UPDATE statements below, which rewrite rows to
'PHQ9'/'GAD7'/'AUDITC'/'PHQ4', violate 0008's still-active hyphenated-only
CHECK directly (`CheckViolationError`) — confirmed live against the DGX DB
(stamped at 0009, 0009a not yet applied there; rows were exactly the
PHQ-9(7)/GAD-7(5)/AUDIT-C(1) set from the probe cited above; transaction
rolled back, 0009 left intact). Fix: drop 0008's CHECK at the start of
this migration's upgrade() (guarded `IF EXISTS`, mirroring 0008's own
drop-before-update-then-recreate pattern), then run the UPDATEs. No new
CHECK is (re-)created here — 0010's own `ADD CONSTRAINT` (itself preceded
by `DROP CONSTRAINT IF EXISTS`) runs immediately next in the same
`upgrade head` invocation and re-establishes it; the gap with no CHECK
active never spans more than this one non-interactive migration run. No
environment is known to have this file's old upgrade() body already
applied and stamped at 0009a — the DGX DB (the only non-fresh environment
touched by this migration) is confirmed pre-0009a by the replay above, so
editing this revision's body in place (rather than adding a 0009b) is
safe. Verified via a DGX-shaped throwaway-DB regression: apply through
0009, seed the exact hyphenated rows with 0008's CHECK still live, then
`upgrade head` — must complete with no data loss and the final
non-hyphenated CHECK in force; plus the existing fresh 0001->head chain
regression (BUG-065's test) re-run to confirm no fresh-DB regression.

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
    # DB-F2b: 0008's CHECK (hyphenated values only) is still the live
    # constraint here — 0010 hasn't narrowed it yet. Drop it first so the
    # UPDATE below (which writes non-hyphenated values) doesn't violate it.
    # IF EXISTS: a from-scratch chain or any DB where it's already absent
    # for any reason is unaffected (no-op). 0010's own ADD CONSTRAINT
    # (guarded by its own DROP CONSTRAINT IF EXISTS) runs immediately next
    # and re-establishes a CHECK, so no lasting state change here.
    op.execute(
        "ALTER TABLE questionnaire_results DROP CONSTRAINT IF EXISTS "
        "ck_questionnaire_results_type"
    )
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
