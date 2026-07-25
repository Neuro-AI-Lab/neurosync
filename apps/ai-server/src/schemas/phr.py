"""PHR (개인건강기록) 도메인 스키마 — Neuro-Sync F1 소비용 typed 모델.

Layer 1(myhealthway_reader의 dict 추출) → Layer 2(이 스키마의 Pydantic 검증)의
계약. 국내 마이헬스웨이 프로파일 원본 편차를 흡수한 후 F1 다른 계층이 안전하게
사용할 수 있는 형태.

설계 문서: _archive/plans/phr_integration_plan.md
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import AgentInput, AgentOutput
from src.data.psychotropic_classification import PsychotropicClass, is_psychiatric

FacilityKind = Literal["pharmacy", "medical", "insurer", "other"]
ClaimType = Literal["pharmacy", "professional", "institutional", "oral", "vision", "other"]


class PatientMeta(BaseModel):
    """PHR 환자 식별 정보 — 원문 성명은 저장 금지, 해시로만."""

    mhid: str = Field(..., description="마이헬스웨이 ID (평문 저장 허용)")
    name_hash: str = Field(..., description="sha256(name)[:16] — 원문 로그 방지")
    rn_masked: str = Field(default="", description="주민번호 원본 그대로 (마스킹 포맷 유지)")

    model_config = ConfigDict(extra="ignore")


class MedicationEvent(BaseModel):
    """단일 조제 이벤트 (MedicationDispense + 인라인 Medication 요약)."""

    dispensed_at: date | None = Field(default=None, description="whenPrepared / whenHandedOver")
    pharmacy: str = Field(default="", description="조제 약국명")
    pharmacy_address: str | None = None

    # 약품 식별
    kd_code: str = Field(default="", description="KDCode (biz.kpis.or.kr)")
    hira_ingredient_code: str | None = Field(
        default=None, description="HIRA 성분코드"
    )
    product_name: str = Field(default="", description="상품명")
    ingredient_name: str | None = Field(
        default=None, description="영문 성분명 (INN)"
    )

    # 복용 정보
    days_supply: int | None = Field(default=None, ge=0, description="총 조제일수")
    daily_frequency: int | None = Field(default=None, ge=0, description="1일 복용 횟수")
    dose_per_take: float | None = Field(default=None, ge=0, description="회당 용량")
    dose_form_text: str = Field(default="", description="'1정' 등 자유 텍스트")

    # 약효분류 (HIRA 의약품성분약효정보조회서비스 결과 — authoritative)
    efficacy_class_no: int | None = Field(
        default=None, description="약효분류번호 meftDivNo (예: 117 정신신경용제)"
    )
    efficacy_class_name: str = Field(
        default="", description="약효분류명 divNm (예: '정신신경용제')"
    )
    # 파생 정신과 약물군 (약효분류번호 → PsychotropicClass)
    psychotropic_class: PsychotropicClass = Field(
        default="UNKNOWN",
        description="정신과 약물군 (약효분류번호 기반). 미조회 시 UNKNOWN.",
    )

    model_config = ConfigDict(extra="ignore")

    @property
    def is_psychotropic(self) -> bool:
        return is_psychiatric(self.psychotropic_class)


class HealthcareVisit(BaseModel):
    """단일 방문/청구 이벤트 (ExplanationOfBenefit 요약)."""

    visited_at: date | None = Field(default=None, description="billablePeriod.start")
    facility_name: str = Field(default="", description="요양기관명")
    facility_kind: FacilityKind = Field(default="other")
    facility_address: str | None = None
    claim_type: ClaimType = Field(default="other", description="type.coding[0].code")
    total_cost: Decimal | None = Field(default=None, description="total.value (KRW)")
    diagnosis_codes: list[str] = Field(
        default_factory=list,
        description="ICD-10 등 상병코드. 국내 프로파일에서는 마스킹돼 빈 배열일 수 있음.",
    )

    model_config = ConfigDict(extra="ignore")


class PhrLoadInput(AgentInput):
    """`PatientHistoryAgent.run()` 입력 계약."""

    bundle_paths: list[str] = Field(
        default_factory=list,
        description="PHR JSON 파일 경로 (여러 개 병합 가능)",
    )


class PhrSummary(AgentOutput):
    """PHR 병합 요약 — F1 세션·Handoff 소비 계약."""

    patient: PatientMeta
    medications: list[MedicationEvent] = Field(default_factory=list)
    visits: list[HealthcareVisit] = Field(default_factory=list)

    # 파생 지표 (patient_history agent가 계산)
    psychotropic_medications: list[MedicationEvent] = Field(
        default_factory=list,
        description="is_psychotropic=True 만 필터",
    )
    has_psychiatric_history: bool = Field(
        default=False,
        description="psychotropic_medications 존재 or 정신과 방문 이력",
    )
    date_range: tuple[date, date] | None = Field(
        default=None,
        description="(min, max) 커버 기간 — 조제일 · 방문일 통합",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 통계 헬퍼
    total_medication_events: int = Field(default=0)
    total_visits: int = Field(default=0)
    psychiatric_visit_count: int = Field(
        default=0,
        description="facility_name에 '정신' 포함 방문 수 (v1 heuristic)",
    )

    model_config = ConfigDict(extra="ignore")


class PhrContextRequest(BaseModel):
    """`POST /ai/phr/context` 요청 — stateless (R2): 파일 경로가 아니라 원본
    MyHealthWay bundle JSON 객체를 request body로 받는다. 백엔드가 세션
    시작 시 1회 호출 — 반환된 `context`를 이후 매 `/ai/chat/respond` 턴의
    `patient_history_context`에 그대로 넣는다."""

    session_id: str | None = Field(
        default=None, description="옵션 — 로깅/추적용, 서버 세션 상태를 만들지 않음"
    )
    bundles: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "MyHealthWay 원본 bundle JSON 객체 목록 "
            "(`{'publicData': [...], ...}` 컨테이너, 여러 개 병합 가능)"
        ),
    )


class PhrContextResponse(BaseModel):
    """`POST /ai/phr/context` 응답."""

    context: str = Field(
        ...,
        description=(
            "DialogueInput.patient_history_context로 그대로 전달할 자연어 요약 "
            "(`src.phr_ingest.to_system_prompt_note`의 출력, 그 이상도 이하도 아님)"
        ),
    )
    summary: PhrSummary = Field(..., description="구조화된 PHR 병합 요약 전체")
    handoff_snippet: dict[str, Any] = Field(
        ...,
        description="`src.phr_ingest.to_handoff_snippet`의 출력 — Handoff 문서 삽입용",
    )
