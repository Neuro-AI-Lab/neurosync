"""POST /ai/ocr/parse — 응답 계약 (플랫폼이 소비하는 부분).

Single source of truth between apps/api (consumer) and apps/ai-server (producer).
PRD §0.3 contract — change requires both PRDs updated simultaneously.

ai-server가 Upstage Document Parse로 처방전/진단서를 파싱해 구조화 결과를 준다.
플랫폼은 이 응답을 모바일에 전달하고, 앱은 extracted_summary를 확인 카드로,
low_confidence_items를 "확인 필요" 배지로 렌더한다 (FR-048).

케이싱: **ai-server는 snake_case를 주고(필드명으로 파싱), 모바일에는 camelCase로
내보낸다**(serialization_alias + model_dump(by_alias=True)). 나머지 플랫폼 API와
동일한 camelCase 컨벤션 유지. ai-server 응답은 필드가 더 많으므로 extra="ignore".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal[
    "prescription", "diagnosis", "medical_record", "consultation", "lab_result", "unknown"
]


class OCRMedication(BaseModel):
    name: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    confidence: float = 1.0

    model_config = ConfigDict(extra="ignore")


class OCRSummary(BaseModel):
    diagnoses: list[str] = Field(default_factory=list)
    diagnosis_codes: list[str] = Field(default_factory=list, serialization_alias="diagnosisCodes")
    medications: list[OCRMedication] = Field(default_factory=list)
    department: str | None = None
    dates: list[str] = Field(default_factory=list)
    scale_scores: dict[str, int] = Field(default_factory=dict, serialization_alias="scaleScores")
    patient_name: str | None = Field(default=None, serialization_alias="patientName")
    patient_age: str | None = Field(default=None, serialization_alias="patientAge")
    patient_gender: str | None = Field(default=None, serialization_alias="patientGender")

    model_config = ConfigDict(extra="ignore")


class OCRLowConfidenceItem(BaseModel):
    block_id: str = Field(default="", serialization_alias="blockId")
    field: str = ""
    value: str = ""
    confidence: float = 0.0
    severity: Literal["info", "verify", "retry"] = "verify"
    message: str = "확인 필요"

    model_config = ConfigDict(extra="ignore")


class OCRParseResponse(BaseModel):
    document_type: DocumentType = Field(default="unknown", serialization_alias="documentType")
    ocr_vendor: str = Field(
        default="upstage_solar_document_parse", serialization_alias="ocrVendor"
    )
    extracted_summary: OCRSummary = Field(
        default_factory=OCRSummary, serialization_alias="extractedSummary"
    )
    low_confidence_items: list[OCRLowConfidenceItem] = Field(
        default_factory=list, serialization_alias="lowConfidenceItems"
    )
    page_count: int = Field(default=0, serialization_alias="pageCount")
    element_count: int = Field(default=0, serialization_alias="elementCount")

    model_config = ConfigDict(extra="ignore")
