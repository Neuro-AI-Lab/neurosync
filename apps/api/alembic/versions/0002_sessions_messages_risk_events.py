"""sessions, messages, risk_events.

PRD §5.2. Embedding (pgvector) deferred to Phase 2 RAG migration.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="in_progress"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('in_progress','submitted','report_ready','closed')",
            name="ck_sessions_status",
        ),
    )
    op.create_index("idx_sessions_patient", "sessions", ["patient_id", "status"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column(
            "input_modality",
            sa.String(length=10),
            nullable=False,
            server_default="text",
        ),
        sa.Column("stt_transcription_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user','ai','system')", name="ck_messages_role"),
        sa.CheckConstraint(
            "input_modality IN ('text','voice')", name="ck_messages_modality"
        ),
    )
    op.create_index("idx_messages_session", "messages", ["session_id", "created_at"])

    op.create_table(
        "risk_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id"),
        ),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=32)),
        sa.Column(
            "trigger_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id"),
        ),
        sa.Column(
            "context_message_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
        ),
        sa.Column("ai_evidence", postgresql.JSONB()),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="detected"
        ),
        sa.Column("notified_to", postgresql.JSONB()),
        sa.Column("legal_basis", sa.Text()),
        sa.Column(
            "consent_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consent_snapshots.id"),
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IN ('low','medium','high','critical')", name="ck_risk_events_level"
        ),
        sa.CheckConstraint(
            "status IN ('detected','acknowledged','resolved','dismissed')",
            name="ck_risk_events_status",
        ),
    )
    op.create_index(
        "idx_risk_events_patient", "risk_events", ["patient_id", "detected_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_risk_events_patient", table_name="risk_events")
    op.drop_table("risk_events")
    op.drop_index("idx_messages_session", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_sessions_patient", table_name="sessions")
    op.drop_table("sessions")
