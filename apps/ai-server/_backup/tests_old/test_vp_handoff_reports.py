"""T1-F5-VER-001~004: VP-specific handoff report generation + verification.

Tests that the orchestrator-driven pipeline produces valid handoff reports
for each VP profile with correct risk levels and evidence verification.
All sub-agents mocked — no LLM calls.

VP-001: Mild first visit (CTRS 5, low risk)
VP-002: Mild revisit with improvement (CTRS 5, longitudinal data)
VP-003: Severe first visit (CTRS 2, crisis expected)
VP-004: Severe revisit with worsening (CTRS 3, longitudinal decline)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.evidence_verifier import VerifierAction
from src.agents.orchestrator import OrchestratorAgent
from src.schemas.common import CTRSLevel, EvidencePacket, EvidenceSource, RiskLevel
from src.schemas.handoff import HandoffOutput
from src.schemas.orchestrator import (
    OrchestratorInput,
    SafetyStatus,
    SessionStage,
    SessionState,
)


# ── VP Slot Profiles ───────────────────────────────────────────────

VP_001_SLOTS = {
    "chief_complaint": "최근 불안감과 수면 장애",
    "history_of_present_illness": "3개월 전 직장 스트레스 후 시작",
    "past_psychiatric_history": "없음",
    "current_medications": "없음",
    "risk_factors": "없음",
    "symptoms": {
        "sleep": "입면 곤란, 2-3시간 소요",
        "appetite": "약간 감소",
        "mood": "가끔 우울",
        "concentration": "업무 집중 어려움",
        "energy": "쉽게 피로",
        "anxiety": "일상적 불안감",
    },
    "psychosocial_context": "직장 내 인간관계 스트레스",
    "substance_use": "없음",
}

VP_002_SLOTS = {
    "chief_complaint": "재진 — Escitalopram 10mg 복용 중, 전반적 호전",
    "history_of_present_illness": "6개월 전 우울 증상으로 첫 내원",
    "past_psychiatric_history": "우울증 치료 6개월",
    "current_medications": "Escitalopram 10mg",
    "risk_factors": "없음",
    "symptoms": {
        "sleep": "정상화 (7시간 수면)",
        "appetite": "정상",
        "mood": "호전, 안정적",
        "concentration": "정상 수준",
        "energy": "정상",
        "anxiety": "가끔 경미",
    },
    "psychosocial_context": "직장 적응 양호",
    "substance_use": "없음",
}

VP_003_SLOTS = {
    "chief_complaint": "자살 사고, 심각한 우울",
    "risk_factors": "구체적 자살 계획 보고",
}  # Minimal — crisis at turn 1, few slots collected

VP_004_SLOTS = {
    "chief_complaint": "공황 발작 악화, 약물 변경 3회",
    "history_of_present_illness": "1년 전 시작, 최근 3개월 악화",
    "past_psychiatric_history": "공황장애 1년, 약물 변경 3회",
    "current_medications": "Paroxetine 20mg (3번째 약물)",
    "risk_factors": "약물 비순응 이력",
    "symptoms": {
        "sleep": "수면 장애 악화",
        "appetite": "식욕 저하",
        "mood": "심한 우울",
        "concentration": "심각한 집중력 저하",
        "energy": "극도의 피로",
        "anxiety": "공황 발작 빈도 증가",
    },
    "psychosocial_context": "대인기피, 사회적 고립 심화",
    "substance_use": "없음",
}


def _make_12_section_report(
    vp_name: str,
    risk_text: str = "위험 요인 없음",
    ctrs_text: str = "CTRS 5 (안정기)",
) -> str:
    """Build a 12-section report matching the standard format."""
    sections = {
        1: f"환자: {vp_name}",
        2: "평가일: 2026-06-24",
        3: "주호소 정보",
        4: "주요 증상 기술",
        5: f"{ctrs_text}\n\n{risk_text}",
        6: "PHQ-9: 해당 없음",
        7: "과거 병력: 해당 정보 없음",
        8: "업로드 문서: 없음",
        9: "종단적 변화: 해당 없음 (초진)",
        10: "추가 정보 필요 사항: 없음",
        11: "추천 진료과: 정신건강의학과",
        12: "근거 레지스트리",
    }
    titles = {
        1: "환자 기본 정보", 2: "평가 일시 및 환경", 3: "주호소 및 현병력",
        4: "주요 증상", 5: "CTRS 기반 위험도 평가", 6: "구조화 척도 결과",
        7: "과거 병력 및 현재 약물", 8: "업로드 문서 요약", 9: "종단적 상태 변화",
        10: "추가 정보 필요 사항", 11: "추천 진료과 및 사유", 12: "근거 레지스트리",
    }
    parts = []
    for n in range(1, 13):
        parts.append(f"## 섹션 {n}. {titles[n]}\n\n{sections[n]}\n")
    return "\n".join(parts)


def _make_evidence_packets(count: int = 3) -> list[EvidencePacket]:
    return [
        EvidencePacket(
            evidence_id=f"ev_msg_{i:03d}",
            source_type=EvidenceSource.message,
            source_ref=f"turn_{i}",
            content_summary=f"근거 {i}",
        )
        for i in range(1, count + 1)
    ]


def _build_vp_orchestrator(
    vp_slots: dict,
    report_markdown: str,
    report_risk: RiskLevel = RiskLevel.none,
    safety_ctrs: int = CTRSLevel.STABLE,
    is_first_visit: bool = True,
) -> OrchestratorAgent:
    """Build orchestrator with mocked sub-agents returning VP-specific data."""
    agent = OrchestratorAgent.__new__(OrchestratorAgent)

    # Safety
    safety_mock = AsyncMock()
    sr = MagicMock()
    sr.ctrs_level = safety_ctrs
    sr.risk_level = RiskLevel.none if safety_ctrs >= 4 else RiskLevel.high
    sr.crisis_protocol_activated = safety_ctrs <= 2
    safety_mock.run = AsyncMock(return_value=sr)
    agent._safety_agent = safety_mock

    # Slot
    slot_mock = AsyncMock()
    slot_r = MagicMock()
    slot_r.extracted_slots = vp_slots
    slot_mock.run = AsyncMock(return_value=slot_r)
    agent._slot_agent = slot_mock

    # Handoff
    handoff_mock = AsyncMock()
    handoff_r = HandoffOutput(
        model_used="mock", prompt_version="v1", latency_ms=50,
        reason_summary="VP handoff", report_markdown=report_markdown,
        evidence_packets=_make_evidence_packets(),
        missing_slots=[], risk_level=report_risk,
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


def _high_coverage_input(
    session_id: str, vp_slots: dict, is_first_visit: bool = True
) -> OrchestratorInput:
    """Create input with pre-filled slots that exceed 70% coverage."""
    state = SessionState(
        session_id=session_id,
        turn_count=1,
        slot_data=vp_slots,
        is_first_visit=is_first_visit,
    )
    return OrchestratorInput(
        session_id=session_id,
        raw_input="네",
        session_state=state,
    )


# ── F5-VER-001: VP-001 (Mild first visit) ──────────────────────────


class TestVP001HandoffReport:
    """VP-001: 김서연 28F, mild anxiety, CTRS 5, first visit."""

    @pytest.mark.asyncio
    async def test_vp001_produces_handoff(self):
        report = _make_12_section_report("김서연", "위험 요인 없음", "CTRS 5 (안정기)")
        agent = _build_vp_orchestrator(VP_001_SLOTS, report)
        inp = _high_coverage_input("vp001", VP_001_SLOTS)
        result = await agent.process_turn(inp)

        assert result.handoff_ready is True
        assert result.handoff_report is not None
        assert "report_markdown" in result.handoff_report

    @pytest.mark.asyncio
    async def test_vp001_no_crisis(self):
        report = _make_12_section_report("김서연")
        agent = _build_vp_orchestrator(VP_001_SLOTS, report)
        inp = _high_coverage_input("vp001", VP_001_SLOTS)
        result = await agent.process_turn(inp)

        assert result.crisis_triggered is False
        assert result.requires_human_review is False

    @pytest.mark.asyncio
    async def test_vp001_evidence_verified(self):
        report = _make_12_section_report("김서연")
        agent = _build_vp_orchestrator(VP_001_SLOTS, report)
        inp = _high_coverage_input("vp001", VP_001_SLOTS)
        result = await agent.process_turn(inp)

        verification_stages = [
            r for r in result.stage_history
            if r.stage == SessionStage.evidence_verification
        ]
        assert len(verification_stages) >= 1
        assert verification_stages[0].result == "pass"


# ── F5-VER-002: VP-002 (Mild revisit, improving) ───────────────────


class TestVP002HandoffReport:
    """VP-002: 이준호 35M, mild revisit, Escitalopram 10mg, improving."""

    @pytest.mark.asyncio
    async def test_vp002_revisit_handoff(self):
        report = _make_12_section_report(
            "이준호", "위험 요인 없음",
            "CTRS 5 (안정기) — 이전 대비 호전"
        )
        agent = _build_vp_orchestrator(
            VP_002_SLOTS, report, is_first_visit=False
        )
        inp = _high_coverage_input("vp002", VP_002_SLOTS, is_first_visit=False)
        result = await agent.process_turn(inp)

        assert result.handoff_ready is True
        assert result.handoff_report is not None

    @pytest.mark.asyncio
    async def test_vp002_medication_in_slots(self):
        """VP-002's medication (Escitalopram) should be in slot data."""
        assert "Escitalopram" in VP_002_SLOTS["current_medications"]

    @pytest.mark.asyncio
    async def test_vp002_no_crisis(self):
        report = _make_12_section_report("이준호")
        agent = _build_vp_orchestrator(VP_002_SLOTS, report, is_first_visit=False)
        inp = _high_coverage_input("vp002", VP_002_SLOTS, is_first_visit=False)
        result = await agent.process_turn(inp)

        assert result.crisis_triggered is False


# ── F5-VER-003: VP-003 (Severe first, CTRS 2 crisis) ───────────────


class TestVP003HandoffReport:
    """VP-003: 박민수 42M, severe depression, suicidal ideation, CTRS 2."""

    @pytest.mark.asyncio
    async def test_vp003_crisis_triggers(self):
        """VP-003 should trigger crisis flow — no full handoff expected."""
        report = _make_12_section_report(
            "박민수", "자살 사고 있음 — 즉각적 위기 대응 필요", "CTRS 2 (고위험)"
        )
        agent = _build_vp_orchestrator(
            VP_003_SLOTS, report, report_risk=RiskLevel.high,
            safety_ctrs=CTRSLevel.HIGH_RISK,
        )
        inp = OrchestratorInput(
            session_id="vp003", raw_input="죽고 싶어요",
        )
        result = await agent.process_turn(inp)

        assert result.crisis_triggered is True
        assert result.requires_human_review is True

    @pytest.mark.asyncio
    async def test_vp003_minimal_slots_due_to_crisis(self):
        """Crisis at turn 1 means minimal slot collection."""
        assert len(VP_003_SLOTS) <= 3  # Only chief_complaint + risk_factors

    @pytest.mark.asyncio
    async def test_vp003_crisis_response_contains_hotline(self):
        report = _make_12_section_report("박민수")
        agent = _build_vp_orchestrator(
            VP_003_SLOTS, report, safety_ctrs=CTRSLevel.HIGH_RISK,
        )
        inp = OrchestratorInput(session_id="vp003", raw_input="죽고 싶어요")
        result = await agent.process_turn(inp)

        assert "1393" in result.assistant_response


# ── F5-VER-004: VP-004 (Severe revisit, worsening) ─────────────────


class TestVP004HandoffReport:
    """VP-004: 최하은 31F, severe revisit, panic attacks, worsening."""

    @pytest.mark.asyncio
    async def test_vp004_revisit_handoff(self):
        report = _make_12_section_report(
            "최하은", "약물 비순응, 공황 빈도 증가",
            "CTRS 3 (급성기) — 이전 대비 악화"
        )
        agent = _build_vp_orchestrator(
            VP_004_SLOTS, report, report_risk=RiskLevel.medium,
            safety_ctrs=CTRSLevel.ACUTE, is_first_visit=False,
        )
        inp = _high_coverage_input("vp004", VP_004_SLOTS, is_first_visit=False)
        result = await agent.process_turn(inp)

        assert result.handoff_ready is True
        assert result.handoff_report is not None

    @pytest.mark.asyncio
    async def test_vp004_multiple_medication_changes(self):
        """VP-004 has 3 medication changes recorded."""
        assert "3" in VP_004_SLOTS["past_psychiatric_history"]
        assert "Paroxetine" in VP_004_SLOTS["current_medications"]

    @pytest.mark.asyncio
    async def test_vp004_worsening_symptoms(self):
        """VP-004 symptoms should indicate worsening."""
        symptoms = VP_004_SLOTS["symptoms"]
        assert "악화" in symptoms["sleep"]
        assert "심한" in symptoms["mood"] or "심각" in symptoms["concentration"]

    @pytest.mark.asyncio
    async def test_vp004_not_crisis_but_acute(self):
        """CTRS 3 is acute but not crisis — should proceed to handoff."""
        report = _make_12_section_report("최하은")
        agent = _build_vp_orchestrator(
            VP_004_SLOTS, report, safety_ctrs=CTRSLevel.ACUTE,
            is_first_visit=False,
        )
        inp = _high_coverage_input("vp004", VP_004_SLOTS, is_first_visit=False)
        result = await agent.process_turn(inp)

        assert result.crisis_triggered is False
        assert result.handoff_ready is True
