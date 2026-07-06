"""T1-F5-VER-006: Evidence citation coverage verification."""
import pytest
from src.agents.evidence_verifier import EvidenceVerifierAgent, EvidenceVerifierInput
from src.schemas.common import EvidencePacket

agent = EvidenceVerifierAgent()

class TestEvidenceCoverage:
    """Verify evidence citation completeness in handoff reports."""

    @pytest.mark.asyncio
    async def test_full_coverage_passes(self):
        """All body references present in registry → no issues."""
        report = (
            "## 섹션 1. 환자 기본 정보\n환자 ID: test\n\n"
            "## 섹션 2. 평가 일시 및 환경\n2026-06-24\n\n"
            "## 섹션 3. 주호소 및 현병력\n불안 호소 [ev_msg_001]\n\n"
            "## 섹션 4. 주요 증상\n우울 영역 [ev_msg_002]\n\n"
            "## 섹션 5. CTRS 기반 위험도 평가\nCTRS 5\n\n"
            "## 섹션 6. 구조화 척도 결과\n해당 없음\n\n"
            "## 섹션 7. 과거 병력 및 현재 약물\n해당 없음\n\n"
            "## 섹션 8. 업로드 문서 요약\n해당 없음\n\n"
            "## 섹션 9. 종단적 상태 변화\n해당 없음\n\n"
            "## 섹션 10. 추가 정보 필요 사항\n전문가 검토 필요\n\n"
            "## 섹션 11. 추천 진료과 및 사유\n정신건강의학과 상담 고려\n\n"
            "## 섹션 12. 근거 레지스트리\n"
            "| [ev_msg_001] | 대화 | 턴1 | 불안 호소 |\n"
            "| [ev_msg_002] | 대화 | 턴2 | 우울 영역 |\n"
        )
        packets = [
            EvidencePacket(evidence_id="ev_msg_001", source_type="message", source_ref="turn1", content_summary="불안"),
            EvidencePacket(evidence_id="ev_msg_002", source_type="message", source_ref="turn2", content_summary="우울"),
        ]
        inp = EvidenceVerifierInput(session_id="t", report_markdown=report, evidence_packets=packets, ctrs_level=5)
        result = await agent.run(inp)
        dangling = [i for i in result.issues if i.issue_type in ("dangling_reference", "orphan_evidence")]
        assert len(dangling) == 0, f"Unexpected dangling issues: {dangling}"

    @pytest.mark.asyncio
    async def test_missing_registry_entry(self):
        """Body has [ev_msg_003] but registry doesn't → dangling."""
        report = (
            "## 섹션 3. 주호소 및 현병력\n불안 [ev_msg_001] 수면 [ev_msg_003]\n\n"
            "## 섹션 12. 근거 레지스트리\n| [ev_msg_001] | 대화 | 턴1 | 불안 |\n"
        )
        inp = EvidenceVerifierInput(session_id="t", report_markdown=report)
        result = await agent.run(inp)
        dangling = [i for i in result.issues if i.issue_type == "dangling_reference"]
        assert len(dangling) == 1
        assert "ev_msg_003" in dangling[0].description

    @pytest.mark.asyncio
    async def test_orphan_registry_entry(self):
        """Registry has [ev_msg_005] but body doesn't reference it → orphan."""
        report = (
            "## 섹션 3. 주호소 및 현병력\n불안 [ev_msg_001]\n\n"
            "## 섹션 12. 근거 레지스트리\n"
            "| [ev_msg_001] | 대화 | 턴1 | 불안 |\n"
            "| [ev_msg_005] | 대화 | 턴5 | 고립 |\n"
        )
        inp = EvidenceVerifierInput(session_id="t", report_markdown=report)
        result = await agent.run(inp)
        orphans = [i for i in result.issues if i.issue_type == "orphan_evidence"]
        assert len(orphans) == 1
        assert "ev_msg_005" in orphans[0].description

    @pytest.mark.asyncio
    async def test_no_evidence_in_clinical_section(self):
        """Clinical section with content but no evidence → unsupported claim."""
        report = (
            "## 섹션 3. 주호소 및 현병력\n환자가 심한 우울감과 불면을 호소하며 일상 기능이 저하됨\n\n"
            "## 섹션 12. 근거 레지스트리\n(없음)\n"
        )
        inp = EvidenceVerifierInput(session_id="t", report_markdown=report)
        result = await agent.run(inp)
        unsupported = [i for i in result.issues if i.issue_type == "unsupported_claim"]
        assert len(unsupported) >= 1
