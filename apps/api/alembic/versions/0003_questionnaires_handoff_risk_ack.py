"""questionnaire_results, handoff_reports, risk_events ack columns.

PRD §5.2 — Phase 1b 문진 + Handoff 배관 슬라이스.
- questionnaire_results: PHQ-9 / GAD-7 응답 + 총점 + severity (FR-006/007).
- handoff_reports: 세션당 1개 구조화 리포트, 비동기 생성 상태 추적 (FR-010/018).
- risk_events: 환자 "혼자 계신가요?" 응답 + 확인 시각 (FR-011/022).

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questionnaire_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=8), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('PHQ9','GAD7')", name="ck_questionnaire_results_type"
        ),
        # One result per (session, type); resubmission upserts the latest.
        sa.UniqueConstraint(
            "session_id", "type", name="uq_questionnaire_results_session_type"
        ),
    )
    op.create_index(
        "idx_questionnaire_results_session",
        "questionnaire_results",
        ["session_id"],
    )

    op.create_table(
        "handoff_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        # generating → ready → failed. Content is null until ready.
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="generating"
        ),
        sa.Column("content", postgresql.JSONB()),
        sa.Column("failure_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('generating','ready','failed')",
            name="ck_handoff_reports_status",
        ),
    )

    # FR-011/022 — 환자 응급 화면 응답 추적.
    op.add_column(
        "risk_events",
        sa.Column("alone_status", sa.String(length=16)),
    )
    op.add_column(
        "risk_events",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    )
    op.create_check_constraint(
        "ck_risk_events_alone_status",
        "risk_events",
        "alone_status IS NULL OR alone_status IN ('alone','with_someone')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_risk_events_alone_status", "risk_events", type_="check"
    )
    op.drop_column("risk_events", "acknowledged_at")
    op.drop_column("risk_events", "alone_status")

    op.drop_table("handoff_reports")
    op.drop_index(
        "idx_questionnaire_results_session", table_name="questionnaire_results"
    )
    op.drop_table("questionnaire_results")
