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

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
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
