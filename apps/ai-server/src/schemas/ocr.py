"""Schemas for the OCR Document agent.

Contract mirrors docs/ai/agents/07_ocr.md + apps/ai-server/prompts/ocr/v1.system.md
(non-LLM adapter spec). Consumers: F1 pipeline (session context injection)
+ /ai/ocr/parse route.

Confidence gate (4-tier, per spec §Confidence Threshold):
    ≥ 0.9        → 정상 출력 (needs_verification=False)
    0.7 ≤ x < 0.9 → low_confidence_items 포함 (info)
    0.5 ≤ x < 0.7 → needs_verification=True (확인 필요)
    < 0.5         → value nulled (재시도 권장)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import AgentInput, AgentOutput

# Confidence gate thresholds (apps/ai-server/prompts/ocr/v1.system.md §Confidence Threshold)
CONFIDENCE_HIGH = 0.9
CONFIDENCE_LOW = 0.7
CONFIDENCE_VERIFY = 0.5

DocumentType = Literal[
    "diagnosis",
    "prescription",
    "consultation",  # 상담기록 (spec: v1.system.md §문서 유형 분류)
    "lab_result",    # 검사결과 (spec)
    "unknown",
]

# Source markers per spec §핵심 구분 — every extracted value must indicate it
# came from OCR, not AI-inferred.
SourceType = Literal["document", "ocr_extracted"]


class BoundingBox(BaseModel):
    """Element position in the source document (pixel coordinates)."""

    x: float = Field(..., description="Left edge")
    y: float = Field(..., description="Top edge")
    width: float = Field(..., description="Element width")
    height: float = Field(..., description="Element height")
    page: int = Field(default=1, description="1-indexed page number")

    model_config = ConfigDict(extra="ignore")


class OCRBlock(BaseModel):
    """One extracted element from the document.

    Confidence gate (spec):
        ≥ 0.9        : needs_verification=False, source="ocr_extracted"
        0.7 ≤ x < 0.9: needs_verification=False, listed in low_confidence_items
        0.5 ≤ x < 0.7: needs_verification=True (확인 필요)
        < 0.5        : value emptied, needs_verification=True (재시도 권장)
    """

    block_id: str = Field(..., description="Stable identifier within a response")
    field: str = Field(
        ...,
        description=(
            "Semantic label (e.g. 'medication_name', 'department', 'diagnosis_code'). "
            "Falls back to Upstage category ('table', 'paragraph', 'heading1') when "
            "no semantic mapping is available."
        ),
    )
    value: str = Field(..., description="Extracted text (empty when confidence < 0.5)")
    confidence: float = Field(..., ge=0.0, le=1.0)
    bounding_box: BoundingBox | None = None
    needs_verification: bool = Field(
        default=False,
        description=(
            "True when confidence < 0.7 or field is safety-sensitive. "
            "Clinician must review before treating value as authoritative."
        ),
    )
    source: SourceType = Field(
        default="ocr_extracted",
        description=(
            "Provenance marker (spec §핵심 구분): 'document' or 'ocr_extracted'. "
            "Enforces that this value is FROM the source document, NOT AI-diagnosed."
        ),
    )
    category: str = Field(
        default="",
        description="Raw Upstage element category (table/paragraph/heading1/etc.)",
    )


class Medication(BaseModel):
    """Structured medication row aggregated from block-level extraction."""

    name: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractedSummary(BaseModel):
    """High-level structured summary aggregated from blocks."""

    diagnoses: list[str] = Field(default_factory=list)
    diagnosis_codes: list[str] = Field(
        default_factory=list, description="ICD/KCD codes when detected"
    )
    medications: list[Medication] = Field(default_factory=list)
    department: str | None = None
    dates: list[str] = Field(default_factory=list)
    scale_scores: dict[str, int] = Field(
        default_factory=dict,
        description="Detected clinical scale scores, e.g. {'PHQ-9': 7, 'GAD-7': 8}",
    )
    patient_name: str | None = None
    patient_age: str | None = None
    patient_gender: str | None = None


class LowConfidenceItem(BaseModel):
    """Item that needs human attention (2-tier severity, per spec)."""

    block_id: str
    field: str
    value: str
    confidence: float
    severity: Literal["info", "verify", "retry"] = Field(
        default="verify",
        description=(
            "info: 0.7~0.9 (display but flag), "
            "verify: 0.5~0.7 (확인 필요), "
            "retry: < 0.5 (재시도 권장)"
        ),
    )
    message: str = "확인 필요"


class OCRInput(AgentInput):
    """Input for OCR Agent (metadata only — bytes passed alongside via caller)."""

    patient_id: str = Field(..., description="Pseudonymous patient identifier")
    document_type_hint: DocumentType = Field(
        default="unknown",
        description=(
            "Optional hint about document type. When 'unknown', the agent tries "
            "to infer type from content."
        ),
    )
    filename: str = Field(default="document.pdf")
    confidence_threshold: float = Field(
        default=CONFIDENCE_LOW,
        ge=0.0,
        le=1.0,
        description=(
            "Legacy override for the 4-tier gate. Values below this appear in "
            "low_confidence_items. Default = 0.7 per spec § Confidence Threshold."
        ),
    )


class OCROutput(AgentOutput):
    """Output from the OCR Agent."""

    session_id: str
    patient_id: str
    document_type: DocumentType
    ocr_vendor: str = Field(default="upstage_solar_document_parse")

    blocks: list[OCRBlock] = Field(default_factory=list)
    extracted_summary: ExtractedSummary = Field(default_factory=ExtractedSummary)
    low_confidence_items: list[LowConfidenceItem] = Field(default_factory=list)

    # Raw formats — useful for downstream agents (Handoff, Dialogue)
    raw_markdown: str = Field(default="", description="Full markdown extraction")
    raw_text: str = Field(default="", description="Full plain text extraction")

    # Book-keeping
    page_count: int = Field(default=0, ge=0)
    element_count: int = Field(default=0, ge=0)
    timestamp: str = Field(default="")
