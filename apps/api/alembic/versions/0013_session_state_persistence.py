"""sessions: session_state round-trip + clinical_escalation_required persistence.

PRD `docs/ai/integration_prd_f1f3_hospital.md` Phase 1 (contract1 wiring,
ADR-046 #2 decision 2 / Option A). Two additive columns on `sessions`:

- `session_state` (JSONB, nullable): the ADR-046 #2 opaque round-trip channel
  verbatim from `ChatResponse.session_state` (ai-server's own
  `schemas/orchestrator.py::SessionState.model_dump()`). Carries the ADR-044
  backstop fields (`asked_slot_counts`/`risk_screening_incomplete`/
  `handoff_delivered`) nested inside by their own key names — not smushed
  into an unrelated blob, just the ai-server-owned dict shape this contract
  always specified. Persisting this lets the WS gateway reload the PRIOR
  turn's state across reconnects (previously connection-scoped in-memory
  only, `apps/api/src/api/v1/sessions.py` session_state docstring note).
- `clinical_escalation_required` (Boolean, not null, default false): the
  4th ADR-044 field, ALSO already a distinctly-named top-level field on
  `ChatResponse`/`DialogueOutput` (mirrors `OrchestratorTurnResult.
  clinical_escalation_required`) — extracted into its own column (rather
  than left to a JSONB reach-through) so it is queryable/observable as the
  minimal consumer CVR-047 recommendation 3 asks for. Full counselor
  notification (F5) is a follow-up PRD's scope; this column plus the
  structured log in `services/chat.py::respond` are the Phase 1 minimum.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-22

ADR-047 chain-linearize (2026-07-26): renumbered 0011 -> 0013 and repointed
down_revision 0010 -> 0012. This file and 0012_risk_events_status_messages_
role_check_widen.py (renumbered 0012 -> 0014) both originally claimed
`revision = "0011"`/`"0012"` on a branch (#78) forked before `patient_
demographics` and `handoff_delivered_at` (#85, merged earlier at 2026-07-25
21:21) landed their own 0011/0012 files on Master — a same-ID collision that
Alembic silently resolves by dict-overwrite (last file loaded wins the
revision-map slot; the other becomes a permanently unreachable orphan head,
never applied by `alembic upgrade head`, no error raised). See ADR-047 in
discussion.md for the full chain audit. `0013_f1f3_backend_integration_
schema.py` (#79's idempotent catch-up for this same session_state/risk_
events/messages content) is retired as fully redundant now that this file
and 0014 are correctly chained.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "session_state",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "clinical_escalation_required",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "clinical_escalation_required")
    op.drop_column("sessions", "session_state")
