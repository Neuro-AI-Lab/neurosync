"""Evidence Verifier agent — checks handoff reports for unsupported claims and violations."""

from __future__ import annotations

import logging
import re
import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput, BaseAgent
from src.schemas.common import EvidencePacket

logger = logging.getLogger(__name__)


class VerifierAction(StrEnum):
    """Outcome of evidence verification."""

    passed = "pass"
    reject = "reject"
    regenerate = "regenerate"


class VerifierIssue(BaseModel):
    """A single issue found during verification."""

    issue_type: str = Field(
        ...,
        description="unsupported_claim | diagnosis_violation | treatment_violation",
    )
    description: str
    location: str = Field(default="", description="Section or line reference in the report")
    severity: str = Field(default="warning", description="warning | error")


class EvidenceVerifierInput(AgentInput):
    """Input to the evidence verifier."""

    report_markdown: str = Field(..., description="The handoff report to verify")
    evidence_packets: list[EvidencePacket] = Field(default_factory=list)
    is_first_visit: bool = Field(default=True)
    has_scale_scores: bool = Field(default=False)
    has_ocr_documents: bool = Field(default=False)
    ctrs_level: int | None = Field(default=None, description="CTRS 1-5 for action alignment check")


class EvidenceVerifierOutput(AgentOutput):
    """Output from the evidence verifier."""

    action: VerifierAction = Field(default=VerifierAction.passed)
    issues: list[VerifierIssue] = Field(default_factory=list)
    unsupported_claim_count: int = Field(default=0)
    diagnosis_violation_count: int = Field(default=0)
    treatment_violation_count: int = Field(default=0)


# ── Diagnosis / treatment violation patterns ──────────────────────────

_DIAGNOSIS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"우울증\s*(입니다|이[시세]|으로\s*판단|으로\s*진단)", re.IGNORECASE),
    re.compile(r"조현병\s*(입니다|이[시세]|으로\s*판단|으로\s*진단)", re.IGNORECASE),
    re.compile(r"불안장애\s*(입니다|이[시세]|으로\s*판단|으로\s*진단)", re.IGNORECASE),
    re.compile(r"(진단|확진)\s*(합니다|됩니다|내립니다)", re.IGNORECASE),
    re.compile(r"diagnosed\s+with", re.IGNORECASE),
]

_TREATMENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(복용|투약|처방)\s*(하세요|하십시오|해야\s*합니다|을\s*권고)", re.IGNORECASE),
    re.compile(r"(용량|mg|밀리그램)\s*(을\s*)?(늘리|줄이|조절|변경)", re.IGNORECASE),
    re.compile(r"(치료법|요법)\s*(을\s*)?(추천|권고|제안)", re.IGNORECASE),
    re.compile(r"prescri(be|ption)", re.IGNORECASE),
]

# Evidence ID pattern: [ev_xxx_nnn]
_EVIDENCE_REF_RE = re.compile(r"\[ev_\w+_\d{3}\]")


class EvidenceVerifierAgent(BaseAgent):
    """Verifies handoff reports for evidence integrity and policy compliance.

    Checks:
    1. Unsupported claims — clinical statements without evidence IDs
    2. Diagnosis violations — asserting a diagnosis (forbidden)
    3. Treatment violations — prescribing or recommending treatment (forbidden)
    """

    @property
    def agent_name(self) -> str:
        return "evidence_verifier"

    async def run(self, inp: AgentInput, **kwargs: Any) -> EvidenceVerifierOutput:
        start = time.perf_counter()

        if not isinstance(inp, EvidenceVerifierInput):
            raise TypeError(f"Expected EvidenceVerifierInput, got {type(inp).__name__}")

        issues: list[VerifierIssue] = []
        known_ids = {ep.evidence_id for ep in inp.evidence_packets}

        # ── Check 1: Unsupported claims ──────────────────────────────
        unsupported = self._check_unsupported_claims(inp.report_markdown, known_ids)
        issues.extend(unsupported)

        # ── Check 2: Diagnosis violations ────────────────────────────
        diag_violations = self._check_diagnosis_violations(inp.report_markdown)
        issues.extend(diag_violations)

        # ── Check 3: Treatment violations ────────────────────────────
        treat_violations = self._check_treatment_violations(inp.report_markdown)
        issues.extend(treat_violations)

        # ── Check 4: 12-section completeness ─────────────────────────
        section_issues = self._check_section_completeness(
            inp.report_markdown,
            inp.is_first_visit,
            inp.has_scale_scores,
            inp.has_ocr_documents,
        )
        issues.extend(section_issues)

        # ── Check 5: CTRS-action alignment ───────────────────────────
        if inp.ctrs_level is not None:
            ctrs_issues = self._check_ctrs_action_alignment(inp.report_markdown, inp.ctrs_level)
            issues.extend(ctrs_issues)

        # ── Check 6: Dangling references ─────────────────────────────
        ref_issues = self._check_dangling_references(inp.report_markdown)
        issues.extend(ref_issues)

        # ── Determine action ─────────────────────────────────────────
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        if error_count > 0:
            action = VerifierAction.reject
        elif warning_count >= 3:
            action = VerifierAction.regenerate
        else:
            action = VerifierAction.passed

        latency_ms = (time.perf_counter() - start) * 1000

        return EvidenceVerifierOutput(
            model_used="rule-engine",
            prompt_version="v1",
            latency_ms=latency_ms,
            reason_summary=(
                f"Verification: {action.value} "
                f"({error_count} errors, {warning_count} warnings)"
            ),
            action=action,
            issues=issues,
            unsupported_claim_count=len(unsupported),
            diagnosis_violation_count=len(diag_violations),
            treatment_violation_count=len(treat_violations),
        )

    def _check_unsupported_claims(
        self, report: str, known_ids: set[str]
    ) -> list[VerifierIssue]:
        """Find sections with clinical content but no evidence citations."""
        issues: list[VerifierIssue] = []

        # Split by section headers
        sections = re.split(r"(?m)^###?\s+", report)

        for section in sections:
            if not section.strip():
                continue

            lines = section.strip().split("\n")
            section_title = lines[0].strip() if lines else "unknown"
            section_body = "\n".join(lines[1:]) if len(lines) > 1 else ""

            # Skip sections that don't need evidence (metadata sections)
            skip_sections = {"missing information", "evidence table", "누락", "근거 표"}
            if any(skip in section_title.lower() for skip in skip_sections):
                continue

            # Check if section has substantive content but no evidence refs
            has_content = len(section_body.strip()) > 20
            has_refs = bool(_EVIDENCE_REF_RE.search(section_body))

            if has_content and not has_refs:
                issues.append(
                    VerifierIssue(
                        issue_type="unsupported_claim",
                        description=(
                            f"Section '{section_title}' contains clinical content "
                            "without evidence citations"
                        ),
                        location=section_title,
                        severity="warning",
                    )
                )

        # Also check for dangling references (cited IDs not in evidence packets)
        cited_ids = set(_EVIDENCE_REF_RE.findall(report))
        for cited in cited_ids:
            clean_id = cited.strip("[]")
            if clean_id not in known_ids:
                issues.append(
                    VerifierIssue(
                        issue_type="unsupported_claim",
                        description=(
                            f"Evidence ID {cited} referenced but not found "
                            "in evidence packets"
                        ),
                        location="report",
                        severity="warning",
                    )
                )

        return issues

    def _check_diagnosis_violations(self, report: str) -> list[VerifierIssue]:
        """Check for forbidden diagnostic assertions."""
        issues: list[VerifierIssue] = []
        for pattern in _DIAGNOSIS_PATTERNS:
            for match in pattern.finditer(report):
                issues.append(
                    VerifierIssue(
                        issue_type="diagnosis_violation",
                        description=f"Diagnostic assertion detected: '{match.group()}'",
                        location=f"near: ...{report[max(0,match.start()-20):match.end()+20]}...",
                        severity="error",
                    )
                )
        return issues

    def _check_treatment_violations(self, report: str) -> list[VerifierIssue]:
        """Check for forbidden treatment/prescription recommendations."""
        issues: list[VerifierIssue] = []
        for pattern in _TREATMENT_PATTERNS:
            for match in pattern.finditer(report):
                issues.append(
                    VerifierIssue(
                        issue_type="treatment_violation",
                        description=f"Treatment recommendation detected: '{match.group()}'",
                        location=f"near: ...{report[max(0,match.start()-20):match.end()+20]}...",
                        severity="error",
                    )
                )
        return issues

    # ── New checks (Sprint 2) ────────────────────────────────────────

    _SECTION_HEADER_RE = re.compile(r"^##\s+섹션\s+(\d+)\.", re.MULTILINE)

    _ALWAYS_REQUIRED = {1, 2, 3, 4, 5, 10, 11, 12}

    def _check_section_completeness(
        self,
        report: str,
        is_first_visit: bool,
        has_scale_scores: bool,
        has_ocr_documents: bool,
    ) -> list[VerifierIssue]:
        """Check that all mandatory sections are present."""
        issues: list[VerifierIssue] = []
        found_sections = {int(m.group(1)) for m in self._SECTION_HEADER_RE.finditer(report)}

        # Always required
        for s in self._ALWAYS_REQUIRED:
            if s not in found_sections:
                issues.append(VerifierIssue(
                    issue_type="missing_section",
                    description=f"섹션 {s} 누락 (필수)",
                    location=f"섹션 {s}",
                    severity="error",
                ))

        # Conditional: section 6 (scales), 7 (past history — always include),
        # section 8 (OCR), and section 9 (longitudinal).
        if has_scale_scores and 6 not in found_sections:
            issues.append(VerifierIssue(
                issue_type="missing_section",
                description="섹션 6 (구조화 척도 결과) 누락 — 척도 점수가 제공되었으므로 필수",
                location="섹션 6",
                severity="warning",
            ))
        if has_ocr_documents and 8 not in found_sections:
            issues.append(VerifierIssue(
                issue_type="missing_section",
                description="섹션 8 (업로드 문서 요약) 누락 — OCR 문서가 제공되었으므로 필수",
                location="섹션 8",
                severity="warning",
            ))
        if not is_first_visit and 9 not in found_sections:
            issues.append(VerifierIssue(
                issue_type="missing_section",
                description="섹션 9 (종단적 상태 변화) 누락 — 재진 환자이므로 필수",
                location="섹션 9",
                severity="warning",
            ))

        return issues

    def _check_ctrs_action_alignment(self, report: str, ctrs_level: int) -> list[VerifierIssue]:
        """Verify CTRS level matches recommended actions in section 11."""
        issues: list[VerifierIssue] = []

        # Extract section 11 content
        sec11_match = re.search(
            r"##\s+섹션\s+11\..+?(?=##\s+섹션\s+12\.|\Z)", report, re.DOTALL
        )
        if not sec11_match:
            return issues  # section 11 missing is caught by completeness check

        sec11 = sec11_match.group()

        if ctrs_level <= 1 and not re.search(r"119|112|응급", sec11):
            issues.append(VerifierIssue(
                issue_type="ctrs_action_mismatch",
                description="CTRS 1 (초응급)인데 섹션 11에 119/112/응급 안내가 없음",
                location="섹션 11",
                severity="error",
            ))
        elif ctrs_level == 2 and not re.search(r"109|119|긴급|위기상담", sec11):
            issues.append(VerifierIssue(
                issue_type="ctrs_action_mismatch",
                description="CTRS 2 (고위험)인데 섹션 11에 109/119/긴급/위기상담 안내가 없음",
                location="섹션 11",
                severity="error",
            ))
        elif ctrs_level == 3 and not re.search(r"정신건강의학과|109|위기", sec11):
            issues.append(VerifierIssue(
                issue_type="ctrs_action_mismatch",
                description="CTRS 3 (급성기)인데 섹션 11에 정신건강의학과/109/위기 안내가 없음",
                location="섹션 11",
                severity="warning",
            ))

        return issues

    def _check_dangling_references(self, report: str) -> list[VerifierIssue]:
        """Check for evidence IDs in body not in registry and vice versa."""
        issues: list[VerifierIssue] = []

        # Split at section 12
        sec12_match = re.search(r"##\s+섹션\s+12\.", report)
        if not sec12_match:
            return issues

        body = report[:sec12_match.start()]
        registry = report[sec12_match.start():]

        body_refs = set(_EVIDENCE_REF_RE.findall(body))
        registry_refs = set(_EVIDENCE_REF_RE.findall(registry))

        # Body refs not in registry
        for ref in body_refs - registry_refs:
            issues.append(VerifierIssue(
                issue_type="dangling_reference",
                description=f"{ref} 본문에 인용되었지만 섹션 12 근거 레지스트리에 없음",
                location="섹션 12",
                severity="warning",
            ))

        # Registry refs not in body
        for ref in registry_refs - body_refs:
            issues.append(VerifierIssue(
                issue_type="orphan_evidence",
                description=f"{ref} 섹션 12에 등록되었지만 본문에서 인용되지 않음",
                location="섹션 12",
                severity="warning",
            ))

        return issues
