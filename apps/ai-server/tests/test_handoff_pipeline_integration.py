"""T1-F5-DEV-005: Handoff pipeline integration tests.

Tests that the orchestrator correctly drives the post-dialogue pipeline:
ClinicalSlotAgent → HandoffGenerator → EvidenceVerifier with retry loop.
All sub-agents mocked — no LLM calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.evidence_verifier import VerifierAction
from src.agents.orchestrator import OrchestratorAgent
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.handoff import HandoffOutput
from src.schemas.orchestrator import (
    OrchestratorInput,
    SessionStage,
    SessionState,
)


def _make_orchestrator_with_mocks() -> tuple[OrchestratorAgent, dict]:
    """Create an orchestrator with all sub-agents mocked."""
    agent = OrchestratorAgent.__new__(OrchestratorAgent)

    # Mock safety agent (always safe)
    safety_mock = AsyncMock()
    safety_result = MagicMock()
    safety_result.ctrs_level = CTRSLevel.STABLE
    safety_result.risk_level = RiskLevel.none
    safety_result.crisis_protocol_activated = False
    safety_mock.run = AsyncMock(return_value=safety_result)
    agent._safety_agent = safety_mock

    # Mock slot agent
    slot_mock = AsyncMock()
    slot_result = MagicMock()
    slot_result.extracted_slots = {"chief_complaint": "불안"}
    slot_mock.run = AsyncMock(return_value=slot_result)
    agent._slot_agent = slot_mock

    # Mock handoff agent
    handoff_mock = AsyncMock()
    handoff_result = HandoffOutput(
        model_used="test",
        prompt_version="v1",
        latency_ms=10,
        reason_summary="test",
        report_markdown="## 섹션 1. 환자 기본 정보\n\n내용\n",
        evidence_packets=[],
        missing_slots=[],
        risk_level=RiskLevel.none,
    )
    handoff_mock.run = AsyncMock(return_value=handoff_result)
    agent._handoff_agent = handoff_mock

    # Mock verifier agent
    verifier_mock = AsyncMock()
    verifier_result = MagicMock()
    verifier_result.action = VerifierAction.passed
    verifier_result.issues = []
    verifier_mock.run = AsyncMock(return_value=verifier_result)
    agent._verifier_agent = verifier_mock

    mocks = {
        "safety": safety_mock,
        "slot": slot_mock,
        "handoff": handoff_mock,
        "verifier": verifier_mock,
    }
    return agent, mocks


def _make_high_coverage_state() -> SessionState:
    """State with enough slots to trigger post-dialogue pipeline.

    Uses the current 12-section slot schema (10/12 = 0.83 >= 0.7 threshold).
    """
    return SessionState(
        session_id="s1",
        turn_count=1,  # not first turn → skip context_retrieval
        slot_data={
            "encounter_metadata": "2026-07-06 초진",
            "chief_complaint": "불안",
            "history_of_present_illness": "3개월",
            "past_psychiatric_history": "없음",
            "medical_history": "없음",
            "personal_social_history": "직장인",
            "family_history": "없음",
            "substance_use_history": "없음",
            "mental_status_exam": "불안 정동",
            "risk_assessment": "자살사고 부인",
        },
    )


class TestHandoffPipelineIntegration:
    """Full pipeline: slot → handoff → verify → deliver."""

    @pytest.mark.asyncio
    async def test_full_pipeline_passes(self):
        """Orchestrator runs all sub-agents and returns handoff_ready."""
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        inp = OrchestratorInput(
            session_id="s1",
            raw_input="test",
            session_state=state,
        )
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.completed
        assert result.handoff_ready is True
        assert result.handoff_report is not None
        assert "report_markdown" in result.handoff_report

    @pytest.mark.asyncio
    async def test_slot_agent_called(self):
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        await agent.process_turn(inp)

        mocks["slot"].run.assert_called_once()

    @pytest.mark.asyncio
    async def test_handoff_agent_called(self):
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        await agent.process_turn(inp)

        mocks["handoff"].run.assert_called_once()

    @pytest.mark.asyncio
    async def test_verifier_called(self):
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        await agent.process_turn(inp)

        mocks["verifier"].run.assert_called_once()

    @pytest.mark.asyncio
    async def test_verifier_regenerate_retries(self):
        """Verifier returns regenerate → handoff called again."""
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        # First call → regenerate, second → pass
        regen_result = MagicMock()
        regen_result.action = VerifierAction.regenerate
        regen_result.issues = [MagicMock(description="test issue")]

        pass_result = MagicMock()
        pass_result.action = VerifierAction.passed
        pass_result.issues = []

        mocks["verifier"].run = AsyncMock(side_effect=[regen_result, pass_result])

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        result = await agent.process_turn(inp)

        assert result.handoff_ready is True
        assert result.handoff_report is not None
        assert mocks["handoff"].run.call_count == 2

    @pytest.mark.asyncio
    async def test_verifier_reject_records_error(self):
        """Verifier reject → handoff_report is None, error logged.

        REV-001 fix (critic, `discussion.md`): `handoff_ready` used to be
        hardcoded `True` here regardless of `handoff_report` — a rejected
        handoff shipped a fake "ready" signal to the client with no report
        reachable through the wire contract. `handoff_ready` now reflects
        reality: False whenever `handoff_report` is None, including this
        reject path (current_stage is still `completed` — the pipeline DID
        run to completion, it just produced no usable report).
        """
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        reject_result = MagicMock()
        reject_result.action = VerifierAction.reject
        reject_result.issues = [MagicMock(description="fatal issue")]
        mocks["verifier"].run = AsyncMock(return_value=reject_result)

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.completed  # pipeline still completes
        assert result.handoff_ready is False  # but no valid report was ever produced
        assert result.handoff_report is None  # no valid report
        assert len(result.session_state.error_log) >= 1

    @pytest.mark.asyncio
    async def test_slot_agent_failure_continues(self):
        """Slot extraction failure → pipeline continues with existing slots."""
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        mocks["slot"].run = AsyncMock(side_effect=RuntimeError("LLM down"))

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        result = await agent.process_turn(inp)

        assert result.handoff_ready is True
        # Handoff still called despite slot failure
        mocks["handoff"].run.assert_called_once()

    @pytest.mark.asyncio
    async def test_handoff_input_built_from_state(self):
        """Verify HandoffInput is correctly built from session state."""
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        await agent.process_turn(inp)

        # Check handoff was called with proper input
        call_args = mocks["handoff"].run.call_args
        handoff_input = call_args[0][0]
        assert handoff_input.session_id == "s1"
        assert handoff_input.slots.chief_complaint == "불안"

    @pytest.mark.asyncio
    async def test_stage_history_records_pipeline(self):
        """Stage history includes all pipeline stages."""
        agent, mocks = _make_orchestrator_with_mocks()
        state = _make_high_coverage_state()

        inp = OrchestratorInput(session_id="s1", raw_input="test", session_state=state)
        result = await agent.process_turn(inp)

        stages = [r.stage for r in result.stage_history]
        assert SessionStage.slot_extraction in stages
        assert SessionStage.handoff_generation in stages
        assert SessionStage.evidence_verification in stages
        assert SessionStage.handoff_delivery in stages
