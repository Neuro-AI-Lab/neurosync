"""Orchestrator session state and I/O schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.schemas.common import CTRSLevel, RiskLevel


class SessionStage(StrEnum):
    """State machine stages for the orchestrator pipeline."""

    input_received = "input_received"
    safety_gate = "safety_gate"
    context_retrieval = "context_retrieval"
    dialogue_loop = "dialogue_loop"
    slot_extraction = "slot_extraction"
    handoff_generation = "handoff_generation"
    evidence_verification = "evidence_verification"
    handoff_delivery = "handoff_delivery"
    crisis_flow = "crisis_flow"
    completed = "completed"
    error = "error"


class InputType(StrEnum):
    """Input modality types."""

    text = "text"
    stt_transcript = "stt_transcript"
    ocr_document = "ocr_document"


class StageRecord(BaseModel):
    """Single entry in the stage transition history."""

    stage: SessionStage
    agent: str = Field(default="", description="Agent that handled this stage")
    result: str = Field(default="", description="pass | fail | crisis | skip")
    timestamp: datetime = Field(default_factory=datetime.now)
    detail: str = Field(default="", description="Optional detail about outcome")


class SafetyStatus(BaseModel):
    """Current safety classification state."""

    ctrs_level: CTRSLevel = CTRSLevel.STABLE
    risk_level: RiskLevel = RiskLevel.none
    crisis_triggered: bool = False
    last_checked_at: datetime | None = None


class SessionState(BaseModel):
    """Persistent session state that survives across turns.

    This is the core data structure the Orchestrator mutates as it moves
    through pipeline stages.  It is designed to be serializable so that
    it can be persisted to a DB or cache for crash recovery.
    """

    session_id: str
    patient_id: str = ""
    current_stage: SessionStage = SessionStage.input_received
    safety_status: SafetyStatus = Field(default_factory=SafetyStatus)
    slot_data: dict[str, Any] = Field(default_factory=dict)
    filled_slots: list[str] = Field(default_factory=list)
    missing_essential_slots: list[str] = Field(default_factory=list)
    slot_coverage: float = 0.0
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    stage_history: list[StageRecord] = Field(default_factory=list)
    turn_count: int = 0
    is_first_visit: bool = True
    scale_scores: dict[str, Any] = Field(default_factory=dict)
    error_log: list[str] = Field(default_factory=list)


# ── Orchestrator I/O ────────────────────────────────────────────────


class OrchestratorInput(BaseModel):
    """Per-turn input to the orchestrator."""

    session_id: str
    patient_id: str = ""
    input_type: InputType = InputType.text
    raw_input: str = ""
    session_state: SessionState | None = None
    # For first turn, session_state may be None → orchestrator creates it.


class OrchestratorTurnResult(BaseModel):
    """Per-turn output from the orchestrator.

    Contains the assistant response (if any), updated session state,
    and flags for the caller.
    """

    session_id: str
    current_stage: SessionStage
    assistant_response: str = ""
    safety_status: SafetyStatus = Field(default_factory=SafetyStatus)
    slot_coverage: float = 0.0
    crisis_triggered: bool = False
    requires_human_review: bool = False
    handoff_ready: bool = False
    handoff_report: dict[str, Any] | None = None
    session_state: SessionState
    stage_history: list[StageRecord] = Field(default_factory=list)
    error: str | None = None
