"""rag.session_insights.slots — 임상 슬롯(JSONB) 저장 컬럼.

시뮬레이션/실대화의 구조화 임상 슬롯(chief_complaint, history_of_present_illness,
past_psychiatric_history 등)을 세션별로 보관한다. session_insights는 세션 1:1 확장이며,
slots는 그 세션에서 추출된 유저 인포를 그대로 담는다(nullable — 기존 행 영향 없음).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE rag.session_insights ADD COLUMN IF NOT EXISTS slots JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE rag.session_insights DROP COLUMN IF EXISTS slots")
