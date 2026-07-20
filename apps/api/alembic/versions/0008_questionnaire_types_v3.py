"""questionnaire_results.type 확장 (AUDITC/PHQ4) + sessions.clinical_slots

v3 FR-040 — 대화 종료 시 RAG top1 도메인으로 문진 1종을 고르므로, PHQ9/GAD7만
허용하던 CHECK 제약이 AUDIT-C·PHQ-4 저장을 막고 있었다 (PRD v3 §6-D, 미결 #7).

v3 FR-039 — 도메인 추정은 F1 임상 슬롯을 입력으로 받는다. 슬롯은 플랫폼 세션에
보관한다. `rag.session_insights.slots`는 VP 시뮬레이션(코퍼스) 테이블이므로 실환자
슬롯을 그쪽에 쓰면 RAG 코퍼스가 오염된다 — 반드시 분리한다.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1) 문진 유형 제약 확장
    op.execute("ALTER TABLE questionnaire_results DROP CONSTRAINT IF EXISTS ck_questionnaire_results_type")
    op.execute(
        "ALTER TABLE questionnaire_results ADD CONSTRAINT ck_questionnaire_results_type "
        "CHECK (type IN ('PHQ9','GAD7','AUDITC','PHQ4'))"
    )
    # type 컬럼이 String(8)이라 'AUDITC'(6)·'PHQ4'(4)는 그대로 들어간다 — 길이 변경 불필요.

    # 2) F1 임상 슬롯 보관 (세션 1:1, nullable — 기존 행 영향 없음)
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS clinical_slots JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS clinical_slots")
    op.execute("ALTER TABLE questionnaire_results DROP CONSTRAINT IF EXISTS ck_questionnaire_results_type")
    # ⚠️ 데이터 유실 주의: 이 downgrade는 upgrade가 허용했던 AUDITC/PHQ4 결과를
    # 삭제한다. 그 행들이 남아 있으면 좁은 CHECK 재적용이 실패하기 때문이다
    # (기존 행을 즉시 검증함). 되돌리기 전 반드시 백업할 것.
    op.execute("DELETE FROM questionnaire_results WHERE type IN ('AUDITC','PHQ4')")
    op.execute(
        "ALTER TABLE questionnaire_results ADD CONSTRAINT ck_questionnaire_results_type "
        "CHECK (type IN ('PHQ9','GAD7'))"
    )
