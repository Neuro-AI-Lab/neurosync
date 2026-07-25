"""리포트 수동 전달 (v3 수정 7 · §6-B · 핸드오프 미결 #2).

리포트를 자동 전달하지 않고 "보관 → 환자 열람 → [전달하기]" 흐름으로 바꾼다.
handoff_reports에 delivered_at을 추가한다. NULL = 보관(환자만 열람), 값 있음 =
의료진에게 전달됨. 의료진 조회(build_report_response)는 delivered_at IS NOT NULL만
노출한다.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE handoff_reports ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE handoff_reports DROP COLUMN IF EXISTS delivered_at")
