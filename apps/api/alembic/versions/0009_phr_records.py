"""PHR(개인건강기록) 정규화 적재 자리 — 마이헬스웨이 FHIR 샘플의 조제/진료
이벤트를 필드별로 추출해 담는 단일 테이블 rag.phr_records.

설계 결정(사용자 승인):
  - 단일 테이블: 투약(medication)·방문(visit)을 record_type으로 구분해 한 테이블에
    통합. 각 유형 전용 컬럼은 반대 유형 행에서 NULL.
  - 위치: rag 스키마(0008 longitudinal_series 등 파이프라인 산출물과 통일).
  - 컬럼은 src/schemas/phr.py의 MedicationEvent/HealthcareVisit/PatientMeta 필드와
    1:1 대응. 추출은 agents/patient_history.py 파서가 담당(스키마는 자리만).
  - 멱등: id를 로더가 uuid5로 결정론적 생성 → 재적재 시 ON CONFLICT(id)로 무중복.
  - 환자명: 시뮬 샘플은 fake 페르소나명이라 원문(patient_name) 저장. 실데이터
    전환 시 암호화(후속 phase). 이 마이그레이션은 스키마만 만든다.

CHECK는 모두 nullable 허용(col IS NULL OR col IN (...)) — 유형 전용 컬럼이 반대
유형 행에서 NULL이어야 하므로.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rag.phr_records (
            id            UUID PRIMARY KEY,
            patient_id    UUID NOT NULL REFERENCES users(id),
            persona_id    TEXT NOT NULL,
            record_type   TEXT NOT NULL
                          CHECK (record_type IN ('medication','visit')),
            source_file   TEXT,

            -- 환자 메타(파일의 Patient 리소스; 행마다 반복 저장)
            mhid          TEXT,
            patient_name  TEXT,
            rn_masked     TEXT,

            -- 공통(조제일 또는 방문일 / 약국명 또는 요양기관명)
            event_date       DATE,
            facility_name    TEXT,
            facility_address TEXT,

            -- medication 전용 (visit 행에서는 NULL)
            kd_code              TEXT,
            hira_ingredient_code TEXT,
            product_name         TEXT,
            ingredient_name      TEXT,
            days_supply          INT,
            daily_frequency      INT,
            dose_per_take        NUMERIC,
            dose_form_text       TEXT,
            efficacy_class_no    INT,
            efficacy_class_name  TEXT,
            psychotropic_class   TEXT
                CHECK (psychotropic_class IS NULL OR psychotropic_class IN
                    ('PSYCHONEUROTIC','SEDATIVE_HYPNOTIC','NON_PSYCHIATRIC','UNKNOWN')),

            -- visit 전용 (medication 행에서는 NULL)
            facility_kind   TEXT
                CHECK (facility_kind IS NULL OR facility_kind IN
                    ('pharmacy','medical','insurer','other')),
            claim_type      TEXT
                CHECK (claim_type IS NULL OR claim_type IN
                    ('pharmacy','professional','institutional','oral','vision','other')),
            total_cost      NUMERIC(12,2),
            diagnosis_codes JSONB,

            ingested_at   TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_phr_records_patient "
        "ON rag.phr_records(patient_id, event_date DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag.phr_records")
