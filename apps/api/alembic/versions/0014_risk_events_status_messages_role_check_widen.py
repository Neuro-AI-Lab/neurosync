"""risk_events.status widen + pending_reclassify + messages.role CHECK widen.

BUG-063 fix: `risk_events.status` source (`src/models/session.py`) was still
`String(16)` with a CHECK excluding `'pending_reclassify'` (17 chars > 16),
which `services/safety.py::handle_unavailable_classifier` unconditionally
writes on every classifier-unavailable turn. The live demo DB only avoided
crashing because someone hand-patched it directly to `varchar(32)` + an
updated CHECK, outside any migration — this migration makes a genuinely
fresh DB match that already-correct runtime shape.

- `ALTER COLUMN status TYPE varchar(32)`: PG treats widening a `varchar(N)`
  to `varchar(M>N)` as metadata-only (no table rewrite, no data risk).
- CHECK drop+recreate adding `'pending_reclassify'`: additive value, no
  existing row can violate a strictly-more-permissive CHECK.

BUG-064 fix (additive step only — see error.md BUG-064 / fix_wave_design.md
§(c) for the deferred full-rename follow-up): `messages.role`'s CHECK is
widened to also allow `'assistant'`. This does NOT retire `services/
chat.py`'s `'ai'`->`'assistant'` outbound seam-map (storage still writes
`'ai'` after this migration) — it only removes the schema-level obstacle to
a future full rename, which is explicitly out of this wave's scope (data
backfill risk, scheduled as its own follow-up PR per the design doc).

Both constraint changes use `IF EXISTS`/guard-safe raw SQL so a partial-apply
retry is idempotent (0008->0010 migration-gap precedent).

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-23

ADR-047 chain-linearize (2026-07-26): renumbered 0012 -> 0014 and repointed
down_revision 0011 -> 0013 (was a same-ID collision with #85's 0011/0012;
see 0013_session_state_persistence.py's docstring and ADR-047 in
discussion.md for the full audit).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # (b) risk_events.status: widen + CHECK additive value.
    op.execute("ALTER TABLE risk_events ALTER COLUMN status TYPE VARCHAR(32)")
    op.execute("ALTER TABLE risk_events DROP CONSTRAINT IF EXISTS ck_risk_events_status")
    op.create_check_constraint(
        "ck_risk_events_status",
        "risk_events",
        "status IN ('detected','acknowledged','resolved','dismissed','pending_reclassify')",
    )

    # (c) messages.role: additive CHECK widening only (storage still writes
    # 'ai' — see module docstring; full rename is an explicit follow-up).
    op.execute("ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_role")
    op.create_check_constraint(
        "ck_messages_role",
        "messages",
        "role IN ('user','ai','system','assistant')",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_role")
    op.create_check_constraint(
        "ck_messages_role",
        "messages",
        "role IN ('user','ai','system')",
    )

    op.execute("ALTER TABLE risk_events DROP CONSTRAINT IF EXISTS ck_risk_events_status")
    op.create_check_constraint(
        "ck_risk_events_status",
        "risk_events",
        "status IN ('detected','acknowledged','resolved','dismissed')",
    )
    op.execute("ALTER TABLE risk_events ALTER COLUMN status TYPE VARCHAR(16)")
