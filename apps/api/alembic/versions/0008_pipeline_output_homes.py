"""F1~F5 파이프라인 산출물의 DB 자리 확보 — 문진 타입 확장, session_insights
추론 컬럼(F2), 종단 시계열 테이블(F4), handoff 산출물 컬럼(F5).

연동(트리거/앱/엔드포인트)은 후속 phase이며, 이 마이그레이션은 스키마만 만든다.
추가 컬럼은 모두 nullable, 신규 테이블은 IF NOT EXISTS → 기존 행/재실행 무영향.

  (1) questionnaire_results.type CHECK: PHQ9/GAD7 →
        PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C (F3 survey_scorer의 ScaleName 표기).
        기존 행(구 제약상 PHQ9/GAD7만 존재 가능)을 하이픈 표기로 먼저 이관.
  (2) rag.session_insights: ai_predicted_disease/grounding(JSONB) +
        recommended_questionnaire(TEXT). class(3분류 도메인)는 유지, 미접촉.
  (3) rag.longitudinal_series: F4 종단 시계열. (patient_id, scale, measured_at)
        UNIQUE로 재적재 멱등성 확보.
  (4) handoff_reports: pdf_url(TEXT) + fhir(JSONB) — F5 산출물 자리.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # (1) 문진 타입 → F3 scorer 표기 5종. 구 제약(PHQ9/GAD7만 허용)이 하이픈
    #     표기를 거부하므로 먼저 제약을 제거한 뒤 기존행을 이관하고 새 제약을 건다.
    op.drop_constraint(
        "ck_questionnaire_results_type", "questionnaire_results", type_="check"
    )
    op.execute("UPDATE questionnaire_results SET type='PHQ-9' WHERE type='PHQ9'")
    op.execute("UPDATE questionnaire_results SET type='GAD-7' WHERE type='GAD7'")
    op.create_check_constraint(
        "ck_questionnaire_results_type",
        "questionnaire_results",
        "type IN ('PHQ-9','GAD-7','PHQ-4','WHO-5','AUDIT-C')",
    )

    # (2) F2 추론 결과 자리 (class 3분류 도메인은 유지, 미접촉)
    op.execute(
        "ALTER TABLE rag.session_insights ADD COLUMN IF NOT EXISTS ai_predicted_disease JSONB"
    )
    op.execute("ALTER TABLE rag.session_insights ADD COLUMN IF NOT EXISTS grounding JSONB")
    op.execute(
        "ALTER TABLE rag.session_insights ADD COLUMN IF NOT EXISTS recommended_questionnaire TEXT"
    )

    # (3) F4 종단 시계열. UNIQUE로 재적재 멱등성 확보.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rag.longitudinal_series (
            id           BIGSERIAL PRIMARY KEY,
            patient_id   UUID NOT NULL REFERENCES users(id),
            session_id   UUID REFERENCES sessions(id) ON DELETE CASCADE,
            scale        TEXT NOT NULL,
            total_score  INT,
            severity     TEXT,
            measured_at  TIMESTAMPTZ NOT NULL,
            series       JSONB,
            generated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (patient_id, scale, measured_at)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ls_patient "
        "ON rag.longitudinal_series(patient_id, measured_at DESC)"
    )

    # (4) F5 산출물 자리
    op.execute("ALTER TABLE handoff_reports ADD COLUMN IF NOT EXISTS pdf_url TEXT")
    op.execute("ALTER TABLE handoff_reports ADD COLUMN IF NOT EXISTS fhir JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE handoff_reports DROP COLUMN IF EXISTS fhir")
    op.execute("ALTER TABLE handoff_reports DROP COLUMN IF EXISTS pdf_url")

    op.execute("DROP TABLE IF EXISTS rag.longitudinal_series")

    op.execute(
        "ALTER TABLE rag.session_insights DROP COLUMN IF EXISTS recommended_questionnaire"
    )
    op.execute("ALTER TABLE rag.session_insights DROP COLUMN IF EXISTS grounding")
    op.execute(
        "ALTER TABLE rag.session_insights DROP COLUMN IF EXISTS ai_predicted_disease"
    )

    # 구 제약(PHQ9/GAD7)으로 복원. 새 제약이 하이픈 없는 표기를 거부하므로 먼저
    # 제약을 제거한 뒤 이관한다. PHQ-4/WHO-5/AUDIT-C 행이 있으면 새 구 제약을
    # 위반하므로 강등 전 해당 행을 정리해야 한다(신규 표기라 실무상 드묾).
    op.drop_constraint(
        "ck_questionnaire_results_type", "questionnaire_results", type_="check"
    )
    op.execute("UPDATE questionnaire_results SET type='PHQ9' WHERE type='PHQ-9'")
    op.execute("UPDATE questionnaire_results SET type='GAD7' WHERE type='GAD-7'")
    op.create_check_constraint(
        "ck_questionnaire_results_type",
        "questionnaire_results",
        "type IN ('PHQ9','GAD7')",
    )
