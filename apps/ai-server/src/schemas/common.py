"""Shared schema primitives used across all agents."""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    """Risk severity tiers — used by safety classifier and downstream gates."""

    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CTRSLevel(IntEnum):
    """Crisis Triage Rating Scale — 1 = most urgent, 5 = stable.

    Based on: 국립정신건강센터, 정신과적 응급상황에서의 현장대응안내 2.0
    """

    EMERGENCY = 1       # 초응급: 자살시도, 자해 행동, 타해, 약물 과다복용
    HIGH_RISK = 2       # 고위험: 구체적 자살 계획, 수단 보유, 강한 충동
    ACUTE = 3           # 급성기: 급성 환각/망상, 공황, 심한 우울 악화
    MODERATE = 4        # 중증/주의: 지속적 우울·불안, 기능 손상
    STABLE = 5          # 안정기: 위험 없음, 보호 요인 존재


CTRS_TO_RISK: dict[CTRSLevel, RiskLevel] = {
    CTRSLevel.EMERGENCY: RiskLevel.critical,
    CTRSLevel.HIGH_RISK: RiskLevel.high,
    CTRSLevel.ACUTE: RiskLevel.medium,
    CTRSLevel.MODERATE: RiskLevel.low,
    CTRSLevel.STABLE: RiskLevel.none,
}

RISK_TO_CTRS: dict[RiskLevel, CTRSLevel] = {v: k for k, v in CTRS_TO_RISK.items()}


class EvidenceSource(StrEnum):
    """Allowed evidence types for clinical claims."""

    message = "message"
    scale = "scale"
    document_block = "document_block"
    risk_event = "risk_event"
    prior_handoff = "prior_handoff"


class EvidencePacket(BaseModel):
    """Single evidence citation linking a claim to its source."""

    evidence_id: str = Field(..., description="e.g. ev_msg_001")
    source_type: EvidenceSource
    source_ref: str = Field(..., description="Human-readable source reference")
    content_summary: str = Field(..., description="Short summary of the evidence")


class ModelSelection(BaseModel):
    """Result of model routing — tells the caller which adapter/model to use."""

    adapter_name: str = Field(..., description="Registered adapter key, e.g. 'solar-pro3'")
    model_id: str = Field(..., description="Model identifier to pass to the API")
    tier: str = Field(default="primary", description="primary | secondary | fallback")
    supports_json_schema: bool = Field(
        default=False,
        description="Whether the adapter natively supports JSON schema response_format",
    )
    supports_json_object: bool = Field(
        default=False,
        description="Whether the adapter supports {type: json_object} response_format",
    )
    max_tokens: int | None = Field(default=None, description="Override max tokens if needed")
