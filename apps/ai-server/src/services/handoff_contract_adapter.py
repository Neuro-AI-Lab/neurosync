"""Lossless conversion from the shared handoff contract to the local agent input."""

from __future__ import annotations

from typing import Final

from contracts.handoff import HandoffRequest, HandoffRiskSignal

from src.schemas.handoff import HandoffInput, RiskEvent, RiskLevelLabel, ScaleScore

_RISK_LEVELS: Final[dict[str, RiskLevelLabel]] = {
    "none": "none",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}


def _adapt_risk_signal(signal: HandoffRiskSignal) -> RiskEvent:
    values: dict[str, str] = {"level": signal.level}
    recognized = _RISK_LEVELS.get(signal.level.strip().lower())
    if recognized is not None:
        values["risk_level"] = recognized
    if signal.category is not None:
        values["category"] = signal.category
    if signal.source_message_id is not None:
        values["source_message_id"] = str(signal.source_message_id)
    return RiskEvent.model_validate(values)


def adapt_handoff_request(request: HandoffRequest) -> HandoffInput:
    """Preserve every official request field in the local generator shape."""
    return HandoffInput(
        session_id=str(request.session_id),
        conversation_history=[
            {
                "message_id": str(message.message_id),
                "role": message.role,
                "content": message.content,
            }
            for message in request.messages
        ],
        scale_scores=[
            ScaleScore(
                scale_name=questionnaire.type,
                total_score=questionnaire.total_score,
                severity=questionnaire.severity,
            )
            for questionnaire in request.questionnaires
        ],
        ocr_documents=[
            {"document_id": f"doc-{index}", "content": content}
            for index, content in enumerate(request.doc_texts, start=1)
        ],
        risk_events=[_adapt_risk_signal(signal) for signal in request.risk_signals],
    )
