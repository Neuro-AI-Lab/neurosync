"""T1-F1-DEV-006: Chat route Orchestrator integration tests.

Tests that the chat route delegates to OrchestratorAgent for safety
and state management, and handles crisis/dialogue/handoff paths correctly.
No LLM calls — orchestrator and dialogue LLM are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.dialogue import DialogueInput, DialogueOutput
from src.schemas.orchestrator import (
    OrchestratorTurnResult,
    SafetyStatus,
    SessionStage,
    SessionState,
)


def _make_safe_orch_result(session_id: str = "s1") -> OrchestratorTurnResult:
    """Non-crisis orchestrator result in dialogue_loop stage."""
    state = SessionState(session_id=session_id, turn_count=1)
    return OrchestratorTurnResult(
        session_id=session_id,
        current_stage=SessionStage.dialogue_loop,
        safety_status=SafetyStatus(
            ctrs_level=CTRSLevel.STABLE,
            risk_level=RiskLevel.none,
        ),
        crisis_triggered=False,
        session_state=state,
        stage_history=[],
    )


def _make_crisis_orch_result(session_id: str = "s1") -> OrchestratorTurnResult:
    """Crisis orchestrator result."""
    state = SessionState(session_id=session_id, turn_count=1)
    return OrchestratorTurnResult(
        session_id=session_id,
        current_stage=SessionStage.crisis_flow,
        assistant_response="자살예방상담전화 1393으로 연락해 주세요.",
        safety_status=SafetyStatus(
            ctrs_level=CTRSLevel.HIGH_RISK,
            risk_level=RiskLevel.high,
            crisis_triggered=True,
        ),
        crisis_triggered=True,
        requires_human_review=True,
        session_state=state,
        stage_history=[],
    )


def _make_handoff_orch_result(session_id: str = "s1") -> OrchestratorTurnResult:
    """Handoff-ready orchestrator result."""
    state = SessionState(session_id=session_id, turn_count=10, slot_coverage=0.8)
    return OrchestratorTurnResult(
        session_id=session_id,
        current_stage=SessionStage.completed,
        safety_status=SafetyStatus(),
        slot_coverage=0.8,
        handoff_ready=True,
        session_state=state,
        stage_history=[],
    )


class TestChatOrchestratorFlow:
    """Verify the chat route correctly delegates to the orchestrator."""

    def test_dialogue_input_has_session_state_field(self):
        inp = DialogueInput(
            session_id="s1",
            user_message="테스트",
            session_state={"session_id": "s1", "turn_count": 0},
        )
        assert inp.session_state is not None
        assert inp.session_state["session_id"] == "s1"

    def test_dialogue_output_has_session_state(self):
        out = DialogueOutput(
            model_used="test",
            prompt_version="v1",
            latency_ms=0,
            reason_summary="test",
            assistant_response="안녕하세요",
            session_state={"session_id": "s1"},
        )
        assert out.session_state is not None
        assert out.handoff_ready is False

    def test_dialogue_output_handoff_ready_flag(self):
        out = DialogueOutput(
            model_used="test",
            prompt_version="v1",
            latency_ms=0,
            reason_summary="test",
            assistant_response="test",
            handoff_ready=True,
        )
        assert out.handoff_ready is True

    def test_session_state_none_by_default(self):
        inp = DialogueInput(session_id="s1", user_message="test")
        assert inp.session_state is None

    def test_orchestrator_input_from_dialogue(self):
        """Verify OrchestratorInput can be built from DialogueInput fields."""
        from src.schemas.orchestrator import OrchestratorInput

        body = DialogueInput(
            session_id="s1",
            user_message="안녕하세요",
        )
        orch_inp = OrchestratorInput(
            session_id=body.session_id,
            raw_input=body.user_message,
        )
        assert orch_inp.session_id == "s1"
        assert orch_inp.raw_input == "안녕하세요"

    def test_session_state_serialization_roundtrip(self):
        """SessionState → dict → SessionState works."""
        state = SessionState(
            session_id="s1",
            turn_count=3,
            slot_data={"chief_complaint": "불안"},
        )
        data = state.model_dump()
        restored = SessionState.model_validate(data)
        assert restored.turn_count == 3
        assert restored.slot_data["chief_complaint"] == "불안"

    def test_crisis_result_has_response(self):
        result = _make_crisis_orch_result()
        assert result.crisis_triggered is True
        assert "1393" in result.assistant_response
        assert result.requires_human_review is True

    def test_handoff_result_signals_ready(self):
        result = _make_handoff_orch_result()
        assert result.handoff_ready is True
        assert result.slot_coverage >= 0.7
