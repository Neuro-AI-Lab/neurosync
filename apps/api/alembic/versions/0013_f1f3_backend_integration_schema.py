"""F1~F3 backend-api integration schema catch-up (PR #79 canonical merge).

`fix/backend-api-integration`'s model-source changes (Phase 1 ADR-046 #2
round-trip, BUG-063/064 role+status widening) were authored on a branch that
forked before Master's alembic chain reached `0011`/`0012` and never carried
its own migrations for these columns/constraints — this migration is the
catch-up so a fresh `alembic upgrade head` matches `src/models/session.py`
exactly (closes the same class of source/DB divergence BUG-065 fixed for
`patient_profiles.is_minor`).

Adds:
- `sessions.session_state` (JSONB, nullable) — ADR-046 #2 WS-reconnect
  round-trip carrier for the prior turn's `ChatResponse.session_state`.
- `sessions.clinical_escalation_required` (bool NOT NULL default false) —
  ADR-044 4th backstop field, queryable independent of `session_state`.
- `risk_events.status` widened `varchar(16)` -> `varchar(32)` + CHECK
  extended with `'pending_reclassify'` (BUG-063, M-1 conservative fallback
  when the safety classifier is unavailable).
- `messages` CHECK `ck_messages_role` extended with `'assistant'` (BUG-064
  additive step; storage keeps writing `'ai'`, `services/chat.py::respond`'s
  outbound seam-map is the interim `'ai'`->`'assistant'` translation).

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS session_state JSONB")
    op.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS clinical_escalation_required "
        "BOOLEAN NOT NULL DEFAULT false"
    )

    op.execute("ALTER TABLE risk_events ALTER COLUMN status TYPE VARCHAR(32)")
    op.execute("ALTER TABLE risk_events DROP CONSTRAINT IF EXISTS ck_risk_events_status")
    op.execute(
        "ALTER TABLE risk_events ADD CONSTRAINT ck_risk_events_status "
        "CHECK (status IN ('detected','acknowledged','resolved','dismissed',"
        "'pending_reclassify'))"
    )

    op.execute("ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_role")
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_role "
        "CHECK (role IN ('user','ai','system','assistant'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_role")
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_role "
        "CHECK (role IN ('user','ai','system'))"
    )

    op.execute("ALTER TABLE risk_events DROP CONSTRAINT IF EXISTS ck_risk_events_status")
    op.execute(
        "ALTER TABLE risk_events ADD CONSTRAINT ck_risk_events_status "
        "CHECK (status IN ('detected','acknowledged','resolved','dismissed'))"
    )
    op.execute("ALTER TABLE risk_events ALTER COLUMN status TYPE VARCHAR(16)")

    op.execute(
        "ALTER TABLE sessions DROP COLUMN IF EXISTS clinical_escalation_required"
    )
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS session_state")
