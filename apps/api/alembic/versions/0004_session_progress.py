"""sessions: intake progress columns (FR-004).

`collected_items` / `progress_ratio` track AI-reported intake completeness for
the patient-facing progress bar. AI computes which of the structured items are
collected; the platform persists the latest snapshot.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "progress_ratio",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "collected_items",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "collected_items")
    op.drop_column("sessions", "progress_ratio")
