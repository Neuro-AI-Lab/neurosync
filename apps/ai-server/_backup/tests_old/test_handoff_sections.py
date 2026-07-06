"""T1-F5-VER-005: 12-section completeness + CTRS-action alignment tests."""

import pytest

from src.agents.evidence_verifier import EvidenceVerifierAgent, EvidenceVerifierInput
from src.schemas.common import EvidencePacket


def _make_report(*section_nums: int, ctrs_action_text: str = "") -> str:
    """Build a minimal report with given section numbers."""
    parts = []
    for n in section_nums:
        title = {
            1: "환자 기본 정보", 2: "평가 일시 및 환경", 3: "주호소 및 현병력",
            4: "주요 증상", 5: "CTRS 기반 위험도 평가", 6: "구조화 척도 결과",
            7: "과거 병력 및 현재 약물", 8: "업로드 문서 요약", 9: "종단적 상태 변화",
            10: "추가 정보 필요 사항", 11: "추천 진료과 및 사유", 12: "근거 레지스트리",
        }.get(n, f"섹션 {n}")
        content = ctrs_action_text if n == 11 and ctrs_action_text else "해당 정보 없음"
        parts.append(f"## 섹션 {n}. {title}\n\n{content}\n")
    return "\n".join(parts)


def _agent() -> EvidenceVerifierAgent:
    return EvidenceVerifierAgent()


class TestSectionCompleteness:
    """Check _check_section_completeness validates mandatory sections."""

    @pytest.mark.asyncio
    async def test_all_12_present(self):
        report = _make_report(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report)
        result = await _agent().run(inp)
        section_issues = [i for i in result.issues if i.issue_type == "missing_section"]
        assert len(section_issues) == 0

    @pytest.mark.asyncio
    async def test_missing_mandatory_section_5(self):
        report = _make_report(1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12)  # no 5
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report)
        result = await _agent().run(inp)
        section_issues = [i for i in result.issues if i.issue_type == "missing_section"]
        assert any("섹션 5" in i.description for i in section_issues)
        assert any(i.severity == "error" for i in section_issues)

    @pytest.mark.asyncio
    async def test_missing_conditional_section_9_revisit(self):
        report = _make_report(1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12)  # no 9
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report, is_first_visit=False)
        result = await _agent().run(inp)
        section_issues = [i for i in result.issues if "섹션 9" in i.description]
        assert len(section_issues) == 1
        assert section_issues[0].severity == "warning"

    @pytest.mark.asyncio
    async def test_missing_section_9_first_visit_ok(self):
        report = _make_report(1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12)  # no 9
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report, is_first_visit=True)
        result = await _agent().run(inp)
        section_issues = [i for i in result.issues if "섹션 9" in i.description]
        assert len(section_issues) == 0  # first visit, section 9 not required


class TestCTRSActionAlignment:
    """Check _check_ctrs_action_alignment validates CTRS→action mapping."""

    @pytest.mark.asyncio
    async def test_ctrs1_with_119(self):
        report = _make_report(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
                              ctrs_action_text="즉시 119 응급전화 연락")
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report, ctrs_level=1)
        result = await _agent().run(inp)
        ctrs_issues = [i for i in result.issues if i.issue_type == "ctrs_action_mismatch"]
        assert len(ctrs_issues) == 0

    @pytest.mark.asyncio
    async def test_ctrs1_without_emergency(self):
        report = _make_report(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
                              ctrs_action_text="정신건강의학과 상담 권고")
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report, ctrs_level=1)
        result = await _agent().run(inp)
        ctrs_issues = [i for i in result.issues if i.issue_type == "ctrs_action_mismatch"]
        assert len(ctrs_issues) == 1
        assert ctrs_issues[0].severity == "error"

    @pytest.mark.asyncio
    async def test_ctrs5_no_requirements(self):
        report = _make_report(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
                              ctrs_action_text="자가관리 안내")
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report, ctrs_level=5)
        result = await _agent().run(inp)
        ctrs_issues = [i for i in result.issues if i.issue_type == "ctrs_action_mismatch"]
        assert len(ctrs_issues) == 0


class TestDanglingReferences:
    """Check _check_dangling_references detects orphan/missing evidence."""

    @pytest.mark.asyncio
    async def test_matching_refs(self):
        report = (
            "## 섹션 3. 주호소 및 현병력\n환자가 호소 [ev_msg_001]\n\n"
            "## 섹션 12. 근거 레지스트리\n| [ev_msg_001] | 대화 | 턴1 | 호소 |\n"
        )
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report)
        result = await _agent().run(inp)
        ref_issues = [i for i in result.issues if i.issue_type in ("dangling_reference", "orphan_evidence")]
        assert len(ref_issues) == 0

    @pytest.mark.asyncio
    async def test_body_ref_not_in_registry(self):
        report = (
            "## 섹션 3. 주호소 및 현병력\n환자가 호소 [ev_msg_001] [ev_msg_002]\n\n"
            "## 섹션 12. 근거 레지스트리\n| [ev_msg_001] | 대화 | 턴1 | 호소 |\n"
        )
        inp = EvidenceVerifierInput(session_id="test", report_markdown=report)
        result = await _agent().run(inp)
        dangling = [i for i in result.issues if i.issue_type == "dangling_reference"]
        assert len(dangling) == 1
        assert "ev_msg_002" in dangling[0].description
