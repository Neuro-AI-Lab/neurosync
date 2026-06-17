"""STT: audio_recordings, stt_transcriptions + consent_snapshots.voice.

PRD §5.2 — Phase 1b 1b.5 음성 입력 슬라이스 (FR-033~037).
- consent_snapshots.voice: 음성 녹음 별도 옵트인 (FR-034, 민감정보).
- audio_recordings: 원본 음성 파일 메타 + 48h 자동폐기 윈도 (FR-036).
- stt_transcriptions: 변환 텍스트(암호화) + 신뢰도/벤더/폴백체인 (FR-033/037).

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # FR-034 — voice consent opt-in (separate from the 4 base consents).
    op.add_column(
        "consent_snapshots",
        sa.Column(
            "voice", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    op.create_table(
        "audio_recordings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("encoding", sa.String(length=16), nullable=False),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column(
            "consent_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consent_snapshots.id"),
            nullable=False,
        ),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "encoding IN ('opus','pcm16')", name="ck_audio_recordings_encoding"
        ),
    )
    # FR-036 — purge job scans by delete_after for not-yet-deleted rows.
    op.create_index(
        "idx_audio_delete_after",
        "audio_recordings",
        ["delete_after"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "stt_transcriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "audio_recording_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("audio_recordings.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        ),
        sa.Column("text_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("vendor", sa.String(length=24), nullable=False),
        sa.Column("lang", sa.String(length=16), nullable=False, server_default="ko-KR"),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("fallback_chain", postgresql.JSONB()),
        sa.Column(
            "edited_by_user",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_stt_session", "stt_transcriptions", ["session_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_stt_session", table_name="stt_transcriptions")
    op.drop_table("stt_transcriptions")
    op.drop_index("idx_audio_delete_after", table_name="audio_recordings")
    op.drop_table("audio_recordings")
    op.drop_column("consent_snapshots", "voice")
