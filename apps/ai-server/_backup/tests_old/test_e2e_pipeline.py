"""T1-F0-VER-001: Orchestrator full pipeline end-to-end test.

Tests the complete state machine from input_received through handoff_delivery
for safe, crisis, and handoff-ready scenarios. All sub-agents mocked.
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


def _wire_orchestrator(
    safety_ctrs: int = CTRSLevel.STABLE,
    safety_risk: str = RiskLevel.none,
    crisis: bool = False,
) -> OrchestratorAgent:
    """Create orchestrator with all sub-agents mocked."""
    agent = OrchestratorAgent.__new__(OrchestratorAgent)

    # Safety
    safety_mock = AsyncMock()
    sr = MagicMock()
    sr.ctrs_level = safety_ctrs
    sr.risk_level = safety_risk
    sr.crisis_protocol_activated = crisis
    safety_mock.run = AsyncMock(return_value=sr)
    agent._safety_agent = safety_mock

    # Slot
    slot_mock = AsyncMock()
    slot_r = MagicMock()
    slot_r.extracted_slots = {}
    slot_mock.run = AsyncMock(return_value=slot_r)
    agent._slot_agent = slot_mock

    # Handoff
    handoff_mock = AsyncMock()
    handoff_r = HandoffOutput(
        model_used="mock", prompt_version="v1", latency_ms=0,
        reason_summary="test", report_markdown=_SAMPLE_REPORT,
        evidence_packets=[], missing_slots=[], risk_level=RiskLevel.none,
    )
    handoff_mock.run = AsyncMock(return_value=handoff_r)
    agent._handoff_agent = handoff_mock

    # Verifier
    verifier_mock = AsyncMock()
    vr = MagicMock()
    vr.action = VerifierAction.passed
    vr.issues = []
    verifier_mock.run = AsyncMock(return_value=vr)
    agent._verifier_agent = verifier_mock

    return agent


_SAMPLE_REPORT = "\n".join(
    f"## 섹션 {n}. 섹션제목{n}\n\n내용 {n}\n" for n in range(1, 13)
)


class TestE2EFullPipeline:
    """Complete pipeline: input → safety → context → dialogue → extraction → handoff → verify → deliver."""

    @pytest.mark.asyncio
    async def test_safe_first_turn_reaches_dialogue(self):
        """First turn, safe input → goes through safety+context → lands in dialogue_loop."""
        agent = _wire_orchestrator()
        inp = OrchestratorInput(session_id="e2e-1", patient_id="pt-1", raw_input="안녕하세요")
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.dialogue_loop
        assert result.crisis_triggered is False
        assert result.session_state.turn_count == 1
        # Should have passed through: input_received, safety_gate, context_retrieval, dialogue_loop
        stages = [r.stage for r in result.stage_history]
        assert SessionStage.input_received in stages
        assert SessionStage.safety_gate in stages
        assert SessionStage.context_retrieval in stages

    @pytest.mark.asyncio
    async def test_crisis_input_skips_dialogue(self):
        """Crisis input → safety_gate → crisis_flow. No dialogue, no handoff."""
        agent = _wire_orchestrator(
            safety_ctrs=CTRSLevel.HIGH_RISK,
            safety_risk=RiskLevel.high,
            crisis=True,
        )
        inp = OrchestratorInput(session_id="e2e-2", raw_input="죽고 싶어요")
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.crisis_flow
        assert result.crisis_triggered is True
        assert result.requires_human_review is True
        assert result.handoff_ready is False
        assert "1393" in result.assistant_response or "119" in result.assistant_response

    @pytest.mark.asyncio
    async def test_high_coverage_triggers_full_pipeline(self):
        """When slots are full, pipeline runs: extraction → handoff → verify → deliver."""
        agent = _wire_orchestrator()
        state = SessionState(
            session_id="e2e-3",
            turn_count=1,
            slot_data={
                "chief_complaint": "불안",
                "history_of_present_illness": "3개월",
                "past_psychiatric_history": "없음",
                "current_medications": "없음",
                "risk_factors": "없음",
                "symptoms": {
                    "sleep": "불면", "appetite": "정상", "mood": "우울",
                    "concentration": "저하", "energy": "저하",
                },
                "psychosocial_context": "직장 스트레스",
            },
        )
        inp = OrchestratorInput(session_id="e2e-3", raw_input="네", session_state=state)
        result = await agent.process_turn(inp)

        assert result.current_stage == SessionStage.completed
        assert result.handoff_ready is True
        assert result.handoff_report is not None
        assert "report_markdown" in result.handoff_report
        # All pipeline stages recorded
        stages = [r.stage for r in result.stage_history]
        assert SessionStage.slot_extraction in stages
        assert SessionStage.handoff_generation in stages
        assert SessionStage.evidence_verification in stages
        assert SessionStage.handoff_delivery in stages

    @pytest.mark.asyncio
    async def test_multi_turn_dialogue_then_handoff(self):
        """Simulate multiple turns: safe dialogue → accumulate slots → trigger handoff."""
        agent = _wire_orchestrator()

        # Turn 1: first turn, low coverage
        inp1 = OrchestratorInput(session_id="multi", raw_input="요즘 잠을 못 자요")
        r1 = await agent.process_turn(inp1)
        assert r1.current_stage == SessionStage.dialogue_loop
        assert r1.handoff_ready is False

        # Turn 2: add slots externally, still low
        state = r1.session_state
        OrchestratorAgent.update_slots(state, {"chief_complaint": "불면", "symptoms.sleep": "불면"})
        inp2 = OrchestratorInput(session_id="multi", raw_input="네, 2주 정도요", session_state=state)
        r2 = await agent.process_turn(inp2)
        assert r2.current_stage == SessionStage.dialogue_loop

        # Turn 3: fill enough slots to trigger handoff (>=70%)
        state3 = r2.session_state
        OrchestratorAgent.update_slots(state3, {
            "history_of_present_illness": "2주",
            "past_psychiatric_history": "없음",
            "current_medications": "없음",
            "risk_factors": "없음",
            "symptoms.appetite": "저하",
            "symptoms.mood": "우울",
            "symptoms.concentration": "저하",
            "symptoms.energy": "저하",
            "symptoms.anxiety": "높음",
            "psychosocial_context": "스트레스",
        })
        inp3 = OrchestratorInput(session_id="multi", raw_input="네", session_state=state3)
        r3 = await agent.process_turn(inp3)

        assert r3.current_stage == SessionStage.completed
        assert r3.handoff_ready is True
        assert r3.session_state.turn_count == 3

    @pytest.mark.asyncio
    async def test_safety_timeout_defaults_to_crisis(self):
        """Safety agent timeout → CTRS 2 assumed → crisis flow."""
        agent = _wire_orchestrator()
        agent._safety_agent.run = AsyncMock(side_effect=TimeoutError("timeout"))

        inp = OrchestratorInput(session_id="e2e-timeout", raw_input="test")
        result = await agent.process_turn(inp)

        assert result.crisis_triggered is True
        assert result.session_state.safety_status.ctrs_level == CTRSLevel.HIGH_RISK

    @pytest.mark.asyncio
    async def test_session_state_persists_across_turns(self):
        """Verify conversation_history and turn_count accumulate."""
        agent = _wire_orchestrator()

        inp1 = OrchestratorInput(session_id="persist", raw_input="첫 번째 메시지")
        r1 = await agent.process_turn(inp1)
        assert r1.session_state.turn_count == 1
        assert len(r1.session_state.conversation_history) == 1

        state = r1.session_state
        inp2 = OrchestratorInput(session_id="persist", raw_input="두 번째 메시지", session_state=state)
        r2 = await agent.process_turn(inp2)
        assert r2.session_state.turn_count == 2
        assert len(r2.session_state.conversation_history) == 2

    @pytest.mark.asyncio
    async def test_stage_history_is_audit_trail(self):
        """Every stage transition is recorded with timestamp and agent."""
        agent = _wire_orchestrator()
        inp = OrchestratorInput(session_id="audit", raw_input="test")
        result = await agent.process_turn(inp)

        for record in result.stage_history:
            assert record.timestamp is not None
            assert record.agent != ""
            assert record.result in ("pass", "skip", "continue", "crisis", "fail")
