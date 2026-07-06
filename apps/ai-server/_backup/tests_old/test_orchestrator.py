"""T1-F0-DEV-001 / T1-F0-VER-001: Orchestrator state machine tests.

Tests the OrchestratorAgent's state transitions, crisis flow,
slot coverage gating, and session state management.
No LLM calls — SafetyClassifier is mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.orchestrator import (
    OrchestratorAgent,
    _CRISIS_CTRS,
    _MAX_DIALOGUE_TURNS,
    _SLOT_COVERAGE_THRESHOLD,
)
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.orchestrator import (
    InputType,
    OrchestratorInput,
    SafetyStatus,
    SessionStage,
    SessionState,
    StageRecord,
)
from src.schemas.safety import SafetyOutput


# ── Fixtures ────────────────────────────────────────────────────────


def _make_safe_safety_output() -> SafetyOutput:
    """CTRS 5 (stable) safety output."""
    return SafetyOutput(
        model_used="test",
        prompt_version="v1",
        latency_ms=10,
        reason_summary="no risk detected",
        risk_level=RiskLevel.none,
        ctrs_level=CTRSLevel.STABLE,
        crisis_protocol_activated=False,
        requires_human_review=False,
        classifications=[],
    )


def _make_crisis_safety_output(ctrs: CTRSLevel = CTRSLevel.HIGH_RISK) -> SafetyOutput:
    """CTRS 1-2 crisis safety output."""
    risk = RiskLevel.critical if ctrs == CTRSLevel.EMERGENCY else RiskLevel.high
    return SafetyOutput(
        model_used="test",
        prompt_version="v1",
        latency_ms=10,
        reason_summary="crisis detected",
        risk_level=risk,
        ctrs_level=ctrs,
        crisis_protocol_activated=True,
        requires_human_review=True,
        classifications=[],
    )


def _make_orchestrator() -> OrchestratorAgent:
    """Create orchestrator with mocked dependencies."""
    return OrchestratorAgent.__new__(OrchestratorAgent)


def _make_input(
    raw_input: str = "안녕하세요",
    session_state: SessionState | None = None,
) -> OrchestratorInput:
    return OrchestratorInput(
        session_id="test-session",
        patient_id="pt-001",
        input_type=InputType.text,
        raw_input=raw_input,
        session_state=session_state,
    )


# ── State machine tests ────────────────────────────────────────────


class TestSessionStateInit:
    """Session state initialization and defaults."""

    def test_new_session_defaults(self):
        state = SessionState(session_id="s1")
        assert state.current_stage == SessionStage.input_received
        assert state.turn_count == 0
        assert state.slot_coverage == 0.0
        assert state.is_first_visit is True
        assert state.safety_status.ctrs_level == CTRSLevel.STABLE

    def test_session_state_serializable(self):
        state = SessionState(session_id="s1", patient_id="p1")
        data = state.model_dump()
        restored = SessionState.model_validate(data)
        assert restored.session_id == "s1"
        assert restored.patient_id == "p1"


class TestStageTransitions:
    """Verify correct stage progression through the pipeline."""

    @pytest.mark.asyncio
    async def test_safe_input_reaches_dialogue(self):
        """Safe input → safety_gate(pass) → context_retrieval → dialogue_loop."""
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(return_value=_make_safe_safety_output())

        inp = _make_input("요즘 잠을 못 자요")
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.dialogue_loop
        assert result.crisis_triggered is False
        assert result.session_state.turn_count == 1

        # Verify stage history includes expected stages
        stages = [r.stage for r in result.stage_history]
        assert SessionStage.input_received in stages
        assert SessionStage.safety_gate in stages
        assert SessionStage.context_retrieval in stages
        assert SessionStage.dialogue_loop in stages

    @pytest.mark.asyncio
    async def test_crisis_input_triggers_crisis_flow(self):
        """CTRS 2 input → safety_gate(crisis) → crisis_flow."""
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(
            return_value=_make_crisis_safety_output(CTRSLevel.HIGH_RISK)
        )

        inp = _make_input("죽고 싶어요")
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.crisis_flow
        assert result.crisis_triggered is True
        assert result.requires_human_review is True
        assert "1393" in result.assistant_response

    @pytest.mark.asyncio
    async def test_emergency_crisis_message(self):
        """CTRS 1 → emergency-specific message with 119."""
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(
            return_value=_make_crisis_safety_output(CTRSLevel.EMERGENCY)
        )

        inp = _make_input("자살 시도했어요")
        result = await agent.process_turn(inp)

        assert result.crisis_triggered is True
        assert "119" in result.assistant_response

    @pytest.mark.asyncio
    async def test_safety_failure_assumes_crisis(self):
        """Safety agent exception → assume CTRS 2, trigger crisis."""
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(side_effect=TimeoutError("LLM timeout"))

        inp = _make_input("test")
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.crisis_flow
        assert result.crisis_triggered is True
        assert result.session_state.safety_status.ctrs_level == CTRSLevel.HIGH_RISK

    @pytest.mark.asyncio
    async def test_second_turn_skips_context_retrieval(self):
        """Turn 2+ should not re-run context retrieval."""
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(return_value=_make_safe_safety_output())

        state = SessionState(session_id="s1", turn_count=1)
        inp = _make_input("잠이 안 와요", session_state=state)
        result = await agent.process_turn(inp)

        stages = [r.stage for r in result.stage_history]
        assert SessionStage.context_retrieval not in stages


class TestSlotCoverage:
    """Slot coverage calculation and dialogue exit gating."""

    def test_empty_slots_zero_coverage(self):
        agent = _make_orchestrator()
        state = SessionState(session_id="s1", slot_data={})
        agent._update_slot_coverage(state)
        assert state.slot_coverage == 0.0
        assert len(state.filled_slots) == 0

    def test_partial_slots_coverage(self):
        agent = _make_orchestrator()
        state = SessionState(
            session_id="s1",
            slot_data={
                "chief_complaint": "불안",
                "risk_factors": "없음",
                "symptoms": {"sleep": "불면"},
            },
        )
        agent._update_slot_coverage(state)
        assert len(state.filled_slots) == 3
        assert state.slot_coverage == 3 / 13  # 13 total slots

    def test_full_slots_coverage(self):
        agent = _make_orchestrator()
        slot_data = {
            "chief_complaint": "불안",
            "history_of_present_illness": "3개월 전부터",
            "past_psychiatric_history": "없음",
            "current_medications": "없음",
            "risk_factors": "없음",
            "symptoms": {
                "sleep": "불면",
                "appetite": "정상",
                "mood": "우울",
                "concentration": "저하",
                "energy": "저하",
                "anxiety": "높음",
            },
            "psychosocial_context": "직장 스트레스",
            "substance_use": "없음",
        }
        state = SessionState(session_id="s1", slot_data=slot_data)
        agent._update_slot_coverage(state)
        assert state.slot_coverage == 1.0
        assert len(state.missing_essential_slots) == 0

    def test_missing_essential_slots_tracked(self):
        agent = _make_orchestrator()
        state = SessionState(
            session_id="s1",
            slot_data={"chief_complaint": "불안"},
        )
        agent._update_slot_coverage(state)
        assert "chief_complaint" not in state.missing_essential_slots
        assert "risk_factors" in state.missing_essential_slots

    def test_slot_filled_checks_nested(self):
        assert OrchestratorAgent._slot_is_filled(
            {"symptoms": {"sleep": "불면"}}, "symptoms.sleep"
        )
        assert not OrchestratorAgent._slot_is_filled(
            {"symptoms": {"sleep": ""}}, "symptoms.sleep"
        )
        assert not OrchestratorAgent._slot_is_filled(
            {"symptoms": {}}, "symptoms.sleep"
        )

    def test_slot_filled_checks_dict_value(self):
        """Slot with {value: ..., evidence: ...} format."""
        assert OrchestratorAgent._slot_is_filled(
            {"chief_complaint": {"value": "불안", "evidence": []}},
            "chief_complaint",
        )
        assert not OrchestratorAgent._slot_is_filled(
            {"chief_complaint": {"value": "", "evidence": []}},
            "chief_complaint",
        )

    @pytest.mark.asyncio
    async def test_high_coverage_triggers_extraction(self):
        """When slot_coverage >= 0.7, orchestrator exits dialogue loop."""
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(return_value=_make_safe_safety_output())

        # Pre-fill enough slots to exceed threshold
        slot_data = {
            "chief_complaint": "불안",
            "history_of_present_illness": "3개월",
            "past_psychiatric_history": "없음",
            "current_medications": "없음",
            "risk_factors": "없음",
            "symptoms": {
                "sleep": "불면",
                "appetite": "정상",
                "mood": "우울",
                "concentration": "저하",
                "energy": "저하",
            },
            "psychosocial_context": "스트레스",
        }
        state = SessionState(
            session_id="s1",
            slot_data=slot_data,
            turn_count=1,  # not first turn
        )
        inp = _make_input("그냥 힘들어요", session_state=state)
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.completed
        assert result.handoff_ready is True

    @pytest.mark.asyncio
    async def test_max_turns_forces_extraction(self):
        """After MAX_DIALOGUE_TURNS, extraction is forced."""
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(return_value=_make_safe_safety_output())

        state = SessionState(
            session_id="s1",
            slot_data={},  # zero coverage
            turn_count=_MAX_DIALOGUE_TURNS - 1,  # will hit max after increment
        )
        inp = _make_input("test", session_state=state)
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.completed
        assert result.handoff_ready is True


class TestSlotUpdates:
    """Test slot update and conversation tracking helpers."""

    def test_update_flat_slot(self):
        state = SessionState(session_id="s1")
        OrchestratorAgent.update_slots(state, {"chief_complaint": "불안"})
        assert state.slot_data["chief_complaint"] == "불안"

    def test_update_nested_slot(self):
        state = SessionState(session_id="s1")
        OrchestratorAgent.update_slots(state, {"symptoms.sleep": "불면"})
        assert state.slot_data["symptoms"]["sleep"] == "불면"

    def test_add_assistant_turn(self):
        state = SessionState(session_id="s1")
        OrchestratorAgent.add_assistant_turn(state, "안녕하세요")
        assert len(state.conversation_history) == 1
        assert state.conversation_history[0]["role"] == "assistant"
        assert state.conversation_history[0]["content"] == "안녕하세요"


class TestStageHistory:
    """Verify audit trail is maintained correctly."""

    @pytest.mark.asyncio
    async def test_stage_history_recorded(self):
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(return_value=_make_safe_safety_output())

        inp = _make_input("hello")
        result = await agent.process_turn(inp)

        assert len(result.stage_history) >= 3  # input_received, safety_gate, context_retrieval
        for record in result.stage_history:
            assert isinstance(record, StageRecord)
            assert record.timestamp is not None

    @pytest.mark.asyncio
    async def test_crisis_stage_history(self):
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(
            return_value=_make_crisis_safety_output()
        )

        inp = _make_input("죽고 싶어요")
        result = await agent.process_turn(inp)

        crisis_records = [r for r in result.stage_history if r.result == "crisis"]
        assert len(crisis_records) >= 1


class TestInputValidation:
    """Edge cases and input validation."""

    @pytest.mark.asyncio
    async def test_empty_input_still_runs_safety(self):
        agent = _make_orchestrator()
        agent._safety_agent = AsyncMock()
        agent._safety_agent.run = AsyncMock(return_value=_make_safe_safety_output())

        inp = _make_input("")
        result = await agent.process_turn(inp)
        assert result.current_stage == SessionStage.dialogue_loop

    def test_input_type_enum(self):
        assert InputType.text == "text"
        assert InputType.stt_transcript == "stt_transcript"
        assert InputType.ocr_document == "ocr_document"

    def test_session_stage_enum_values(self):
        assert len(SessionStage) == 11  # 8 pipeline + crisis + completed + error
