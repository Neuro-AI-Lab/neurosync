"""T1-F0-VER-002: 4-VP integrated simulation test.

Simulates all 4 virtual patient profiles through the orchestrator pipeline
and validates that each VP follows its expected clinical trajectory.
All sub-agents mocked — no LLM calls.

VP-001: Mild first → dialogue → handoff (CTRS 5)
VP-002: Mild revisit → dialogue → handoff with longitudinal data (CTRS 5)
VP-003: Severe first → crisis at turn 1 (CTRS 2)
VP-004: Severe revisit → dialogue → handoff with worsening (CTRS 3)
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


# ── VP profiles ────────────────────────────────────────────────────

VP_PROFILES = {
    "VP-001": {
        "name": "김서연", "age": 28, "sex": "F",
        "severity": "mild", "visit": "first",
        "expected_ctrs": CTRSLevel.STABLE,
        "expected_crisis": False,
        "expected_handoff": True,
        "slots": {
            "chief_complaint": "불안감과 수면 장애",
            "history_of_present_illness": "3개월 전부터",
            "past_psychiatric_history": "없음",
            "current_medications": "없음",
            "risk_factors": "없음",
            "symptoms": {
                "sleep": "입면 곤란", "appetite": "감소",
                "mood": "우울", "concentration": "저하",
                "energy": "피로", "anxiety": "높음",
            },
            "psychosocial_context": "직장 스트레스",
            "substance_use": "없음",
        },
    },
    "VP-002": {
        "name": "이준호", "age": 35, "sex": "M",
        "severity": "mild", "visit": "revisit",
        "expected_ctrs": CTRSLevel.STABLE,
        "expected_crisis": False,
        "expected_handoff": True,
        "slots": {
            "chief_complaint": "재진, 전반적 호전",
            "history_of_present_illness": "6개월 전 우울증",
            "past_psychiatric_history": "우울증 6개월 치료",
            "current_medications": "Escitalopram 10mg",
            "risk_factors": "없음",
            "symptoms": {
                "sleep": "정상", "appetite": "정상",
                "mood": "안정", "concentration": "정상",
                "energy": "정상", "anxiety": "경미",
            },
            "psychosocial_context": "직장 적응 양호",
            "substance_use": "없음",
        },
    },
    "VP-003": {
        "name": "박민수", "age": 42, "sex": "M",
        "severity": "severe", "visit": "first",
        "expected_ctrs": CTRSLevel.HIGH_RISK,
        "expected_crisis": True,
        "expected_handoff": False,  # Crisis → no full handoff
        "slots": {
            "chief_complaint": "자살 사고",
            "risk_factors": "구체적 계획 보고",
        },
    },
    "VP-004": {
        "name": "최하은", "age": 31, "sex": "F",
        "severity": "severe", "visit": "revisit",
        "expected_ctrs": CTRSLevel.ACUTE,
        "expected_crisis": False,  # CTRS 3 = acute, not crisis
        "expected_handoff": True,
        "slots": {
            "chief_complaint": "공황 발작 악화",
            "history_of_present_illness": "1년 전 시작, 3개월 악화",
            "past_psychiatric_history": "공황장애 1년, 약물 3회 변경",
            "current_medications": "Paroxetine 20mg",
            "risk_factors": "약물 비순응",
            "symptoms": {
                "sleep": "악화", "appetite": "저하",
                "mood": "심한 우울", "concentration": "심각한 저하",
                "energy": "극도 피로", "anxiety": "공황 빈도 증가",
            },
            "psychosocial_context": "사회적 고립",
            "substance_use": "없음",
        },
    },
}

_SAMPLE_REPORT = "\n".join(
    f"## 섹션 {n}. 제목{n}\n\n내용\n" for n in range(1, 13)
)


def _build_vp_orchestrator(profile: dict) -> OrchestratorAgent:
    """Create orchestrator mocked for a specific VP."""
    agent = OrchestratorAgent.__new__(OrchestratorAgent)
    ctrs = profile["expected_ctrs"]
    is_crisis = profile["expected_crisis"]

    safety_mock = AsyncMock()
    sr = MagicMock()
    sr.ctrs_level = ctrs
    sr.risk_level = RiskLevel.high if ctrs <= 2 else (RiskLevel.medium if ctrs == 3 else RiskLevel.none)
    sr.crisis_protocol_activated = is_crisis
    safety_mock.run = AsyncMock(return_value=sr)
    agent._safety_agent = safety_mock

    slot_mock = AsyncMock()
    slot_r = MagicMock()
    slot_r.extracted_slots = profile["slots"]
    slot_mock.run = AsyncMock(return_value=slot_r)
    agent._slot_agent = slot_mock

    handoff_mock = AsyncMock()
    handoff_r = HandoffOutput(
        model_used="mock", prompt_version="v1", latency_ms=0,
        reason_summary="VP handoff", report_markdown=_SAMPLE_REPORT,
        evidence_packets=[], missing_slots=[],
        risk_level=RiskLevel.none,
    )
    handoff_mock.run = AsyncMock(return_value=handoff_r)
    agent._handoff_agent = handoff_mock

    verifier_mock = AsyncMock()
    vr = MagicMock()
    vr.action = VerifierAction.passed
    vr.issues = []
    verifier_mock.run = AsyncMock(return_value=vr)
    agent._verifier_agent = verifier_mock

    return agent


class TestFourVPIntegratedSimulation:
    """Run all 4 VPs through the orchestrator and validate trajectories."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vp_id", ["VP-001", "VP-002", "VP-003", "VP-004"])
    async def test_vp_crisis_expectation(self, vp_id: str):
        """Each VP triggers crisis or not, as expected."""
        profile = VP_PROFILES[vp_id]
        agent = _build_vp_orchestrator(profile)

        if profile["expected_crisis"]:
            inp = OrchestratorInput(session_id=vp_id, raw_input="죽고 싶어요")
        else:
            state = SessionState(
                session_id=vp_id, turn_count=1,
                slot_data=profile["slots"],
                is_first_visit=profile["visit"] == "first",
            )
            inp = OrchestratorInput(session_id=vp_id, raw_input="네", session_state=state)

        result = await agent.process_turn(inp)
        assert result.crisis_triggered == profile["expected_crisis"], (
            f"{vp_id}: expected crisis={profile['expected_crisis']}, got {result.crisis_triggered}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vp_id", ["VP-001", "VP-002", "VP-004"])
    async def test_non_crisis_vp_reaches_handoff(self, vp_id: str):
        """Non-crisis VPs with sufficient slots → handoff_ready."""
        profile = VP_PROFILES[vp_id]
        agent = _build_vp_orchestrator(profile)
        state = SessionState(
            session_id=vp_id, turn_count=1,
            slot_data=profile["slots"],
            is_first_visit=profile["visit"] == "first",
        )
        inp = OrchestratorInput(session_id=vp_id, raw_input="네", session_state=state)
        result = await agent.process_turn(inp)

        assert result.handoff_ready is True
        assert result.handoff_report is not None

    @pytest.mark.asyncio
    async def test_vp003_crisis_has_no_handoff(self):
        """VP-003 (crisis) should NOT produce a handoff report."""
        profile = VP_PROFILES["VP-003"]
        agent = _build_vp_orchestrator(profile)
        inp = OrchestratorInput(session_id="VP-003", raw_input="죽고 싶어요")
        result = await agent.process_turn(inp)

        assert result.crisis_triggered is True
        assert result.handoff_ready is False
        assert result.handoff_report is None

    @pytest.mark.asyncio
    async def test_all_vps_have_valid_stage_history(self):
        """All 4 VPs produce non-empty stage history."""
        for vp_id, profile in VP_PROFILES.items():
            agent = _build_vp_orchestrator(profile)
            if profile["expected_crisis"]:
                inp = OrchestratorInput(session_id=vp_id, raw_input="죽고 싶어요")
            else:
                state = SessionState(
                    session_id=vp_id, turn_count=1,
                    slot_data=profile["slots"],
                    is_first_visit=profile["visit"] == "first",
                )
                inp = OrchestratorInput(session_id=vp_id, raw_input="네", session_state=state)

            result = await agent.process_turn(inp)
            assert len(result.stage_history) >= 2, f"{vp_id}: too few stage records"

    @pytest.mark.asyncio
    async def test_revisit_vps_flag_correctly(self):
        """VP-002 and VP-004 are revisits; VP-001 and VP-003 are first visits."""
        assert VP_PROFILES["VP-001"]["visit"] == "first"
        assert VP_PROFILES["VP-002"]["visit"] == "revisit"
        assert VP_PROFILES["VP-003"]["visit"] == "first"
        assert VP_PROFILES["VP-004"]["visit"] == "revisit"

    @pytest.mark.asyncio
    async def test_severe_vps_have_risk_factors(self):
        """VP-003 and VP-004 must have risk_factors in slots."""
        assert "risk_factors" in VP_PROFILES["VP-003"]["slots"]
        assert "risk_factors" in VP_PROFILES["VP-004"]["slots"]
        assert VP_PROFILES["VP-003"]["slots"]["risk_factors"] != "없음"
        assert VP_PROFILES["VP-004"]["slots"]["risk_factors"] != "없음"

    @pytest.mark.asyncio
    async def test_simulation_summary(self):
        """Run all 4 VPs and collect summary statistics."""
        results = {}
        for vp_id, profile in VP_PROFILES.items():
            agent = _build_vp_orchestrator(profile)
            if profile["expected_crisis"]:
                inp = OrchestratorInput(session_id=vp_id, raw_input="죽고 싶어요")
            else:
                state = SessionState(
                    session_id=vp_id, turn_count=1,
                    slot_data=profile["slots"],
                    is_first_visit=profile["visit"] == "first",
                )
                inp = OrchestratorInput(session_id=vp_id, raw_input="네", session_state=state)

            result = await agent.process_turn(inp)
            results[vp_id] = {
                "crisis": result.crisis_triggered,
                "handoff": result.handoff_ready,
                "stage": str(result.current_stage),
                "stages_count": len(result.stage_history),
            }

        # VP-001: safe → handoff
        assert results["VP-001"]["crisis"] is False
        assert results["VP-001"]["handoff"] is True

        # VP-002: safe revisit → handoff
        assert results["VP-002"]["crisis"] is False
        assert results["VP-002"]["handoff"] is True

        # VP-003: crisis → no handoff
        assert results["VP-003"]["crisis"] is True
        assert results["VP-003"]["handoff"] is False

        # VP-004: acute but not crisis → handoff
        assert results["VP-004"]["crisis"] is False
        assert results["VP-004"]["handoff"] is True
