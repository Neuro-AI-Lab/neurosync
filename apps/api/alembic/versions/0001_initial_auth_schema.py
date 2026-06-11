"""initial auth schema — organizations, users, patient_profiles, consent_snapshots, audit_logs.

PRD §5.2. Demo: no FR-030 trigger / FR-027 guardian enforcement at DB layer
(those are Phase 2).

Revision ID: 0001
Revises:
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "role IN ('patient','clinician','org_admin','super_admin')",
            name="ck_users_role",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "patient_profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("name_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=False),
        sa.Column(
            "is_minor",
            sa.Boolean(),
            sa.Computed(
                "(EXTRACT(YEAR FROM CURRENT_DATE)::int - birth_year) < 14",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("gender", sa.Text()),
        sa.Column("phone_encrypted", sa.LargeBinary()),
        sa.Column("region", sa.Text()),
        sa.Column("emergency_contact_encrypted", sa.LargeBinary()),
        sa.Column("target_hospital_id", postgresql.UUID(as_uuid=True)),
        sa.Column("pseudonymized_at", sa.DateTime(timezone=True)),
        sa.Column("pseudonymous_id", sa.Text(), unique=True),
    )

    op.create_table(
        "consent_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("tos", sa.Boolean(), nullable=False),
        sa.Column("privacy", sa.Boolean(), nullable=False),
        sa.Column("sensitive", sa.Boolean(), nullable=False),
        sa.Column("risk_notification", sa.Boolean(), nullable=False),
        sa.Column("guardian_consent", postgresql.JSONB()),
        sa.Column("tos_version", sa.String(length=32), nullable=False),
        sa.Column("privacy_version", sa.String(length=32), nullable=False),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("collected_ip", postgresql.INET()),
        sa.Column("user_agent", sa.Text()),
    )
    op.create_index(
        "idx_consent_user", "consent_snapshots", ["user_id", "collected_at"]
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(start=1),
            primary_key=True,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("actor_role", sa.String(length=20), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text()),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ip", postgresql.INET()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("prev_hash", sa.LargeBinary()),
        sa.Column("record_hash", sa.LargeBinary()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_audit_logs_actor", "audit_logs", ["actor_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_audit_logs_actor", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("idx_consent_user", table_name="consent_snapshots")
    op.drop_table("consent_snapshots")
    op.drop_table("patient_profiles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
