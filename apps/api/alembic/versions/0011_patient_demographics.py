"""인적사항 수집 항목 확장 (v3 수정 1 · 핸드오프 미결 #1).

가입 시 수집하는 사회인구학적 항목을 확장한다. 기존 birth_year·gender·region은
그대로 두고, 혼인 상태·동거 형태·학력·직업·고용상태·소득수준·종교 7개를 추가한다.

설계 결정:
  - 모두 NULLABLE — 선택 입력. 특히 소득수준·종교는 민감 항목이라 강제하지 않고
    'prefer_not'(응답 안 함) 코드를 허용한다(핸드오프 미결 #3, Consent 검토 대상).
  - 값은 코드(영문)로 저장하고 화면에서 한국어 라벨로 매핑 — gender/region과 동일
    패턴의 평문 Text(비-PII 범주형). 암호화 대상 아님.
  - CHECK는 nullable 허용(col IS NULL OR col IN (...)). occupation은 자유 서술이라
    CHECK 없음.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ENUM_COLUMNS = {
    "marital_status": ("single", "married", "divorced", "bereaved", "separated", "other"),
    "household_type": ("alone", "spouse", "parents", "children", "relatives", "other"),
    "education_level": ("middle_or_below", "high_school", "college", "graduate", "other"),
    "employment_status": (
        "employed",
        "self_employed",
        "unemployed",
        "student",
        "retired",
        "homemaker",
        "other",
    ),
    "income_level": ("low", "mid_low", "mid", "mid_high", "high", "prefer_not"),
    "religion": ("none", "protestant", "catholic", "buddhist", "won", "other", "prefer_not"),
}


def upgrade() -> None:
    # 자유 서술 항목.
    op.execute("ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS occupation TEXT")
    # 범주형 항목 + nullable-허용 CHECK.
    for col, values in _ENUM_COLUMNS.items():
        allowed = ", ".join(f"'{v}'" for v in values)
        op.execute(f"ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS {col} TEXT")
        op.execute(
            f"ALTER TABLE patient_profiles DROP CONSTRAINT IF EXISTS ck_patient_profiles_{col}"
        )
        op.execute(
            f"ALTER TABLE patient_profiles ADD CONSTRAINT ck_patient_profiles_{col} "
            f"CHECK ({col} IS NULL OR {col} IN ({allowed}))"
        )


def downgrade() -> None:
    for col in _ENUM_COLUMNS:
        op.execute(
            f"ALTER TABLE patient_profiles DROP CONSTRAINT IF EXISTS ck_patient_profiles_{col}"
        )
        op.execute(f"ALTER TABLE patient_profiles DROP COLUMN IF EXISTS {col}")
    op.execute("ALTER TABLE patient_profiles DROP COLUMN IF EXISTS occupation")
