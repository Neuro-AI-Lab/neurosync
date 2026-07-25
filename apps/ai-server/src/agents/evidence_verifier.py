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
    # BUG-069 (2026-07-23) — metadata-grounding check inputs. `prior_handoff_
    # present` is the caller's ground truth for whether a REAL prior handoff
    # was supplied (distinct from `is_first_visit`, since a caller could in
    # principle mark `is_first_visit=False` without actually supplying prior
    # handoff text — the section-9 trend prohibition below requires BOTH
    # signals to agree a real longitudinal comparison is possible).
    # `patient_gender`/`session_started_at`/`session_ended_at` are optional
    # ground-truth values: `HandoffInput` does not carry these today (a
    # separate, deferred apps/api-side gap — see `handoff_generator.py`'s
    # `_build_user_content` docstring), so callers currently pass `None` for
    # all three, and the metadata check below treats `None` as "this field
    # was never grounded in the input" — meaning ANY specific-looking
    # assertion in the narrative is necessarily fabricated. If a future
    # caller supplies real values here, the check upgrades to a mismatch
    # comparison instead of a bare-assertion prohibition.
    prior_handoff_present: bool = Field(default=False)
    patient_gender: str | None = Field(default=None)
    session_started_at: str | None = Field(default=None)
    session_ended_at: str | None = Field(default=None)


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

# BUG-050 (2026-07-21): section-title "섹션 N." number extraction, and the
# "해당 없음"-only table detector, used by `_check_unsupported_claims`'s two
# targeted over-strictness fixes — see that method's own docstring for the
# live-reproduction evidence behind both.
_SECTION_NUMBER_TITLE_RE = re.compile(r"^섹션\s+(\d+)\.")
_ADMINISTRATIVE_SECTION_NUMBERS = {1, 2}

_TABLE_ROW_RE = re.compile(r"^\|.*\|$", re.MULTILINE)
_TABLE_DIVIDER_RE = re.compile(r"^\|[\s:|-]+\|$")
_NO_DATA_PLACEHOLDER_TOKENS = {"해당", "없음", "해당 없음", "-", "", "해당없음", "N/A", "n/a"}

# BUG-071 (2026-07-23): a section whose "no data" content is rendered as a
# markdown bullet list (`- **label**: 기록 없음`) rather than a table — the
# v4.3+ prompt's own §3/§7 convention for "no data collected" fields —
# needs the same all-placeholder exemption `_is_no_data_placeholder_section`
# already grants table-shaped sections. `_NO_DATA_MARKER_RE` (BUG-069) is
# reused as the marker vocabulary so both checks stay in lockstep.
_BULLET_LINE_RE = re.compile(r"^[-*]\s+(.*)$")

# BUG-069 (2026-07-23): the v4.3-mandated first-visit safe-fallback phrase
# for section 9 ("초진 — 종단 비교 불가 (이전 방문 기록 없음)") is prose, not
# a table, so it does not match `_is_no_data_placeholder_section` above — a
# session correctly following the new prompt discipline would otherwise trip
# `_check_unsupported_claims`'s generic "clinical content without citation"
# warning on its own compliant output. This is an administrative
# no-comparison-possible declaration (system-authored, not a patient-stated
# fact), exactly the same class already exempted for sections 1/2/6/10.
_FIRST_VISIT_NO_TREND_MARKER_RE = re.compile(r"종단\s*비교\s*불가")

# BUG-069 (2026-07-23): metadata-grounding + first-visit-trend check patterns.
_SECTION_BODY_RE_TEMPLATE = r"##\s+섹션\s+{n}\..*?(?=##\s+섹션\s+\d+\.|\Z)"
# BUG-071: "해당 정보 없음" (the actual §3/§7 bullet-list phrasing) is the
# same no-data declaration as "해당 없음" with an optional "정보" infix —
# broadened so both the metadata check (unchanged behavior on gender/
# timestamp values) and the new bullet-section exemption recognize it.
_NO_DATA_MARKER_RE = re.compile(r"기록\s*없음|미수집|확인\s*필요|해당\s*(?:정보\s*)?없음")
_GENDER_LINE_RE = re.compile(r"\*?\*?성별\*?\*?\s*[:：]\s*(.+)")
_GENDER_ASSERT_RE = re.compile(r"남성|여성|male|female", re.IGNORECASE)
_TIMESTAMP_LINE_RE = re.compile(
    r"\*?\*?(사전문진\s*(?:시작|종료)\s*일시|소요\s*시간)\*?\*?\s*[:：]\s*(.+)"
)
_TIMESTAMP_VALUE_RE = re.compile(r"\d{1,2}\s*:\s*\d{2}|\d+\s*분|\d{4}-\d{2}-\d{2}")
_TEMPLATE_EXAMPLE_ARTIFACT_RE = re.compile(r"\(\s*예\s*[:：]")
_TEMPLATE_PLACEHOLDER_ARTIFACT_RE = re.compile(r"<[^<>\n]{2,40}>")

# BUG-069: issue types that force a `regenerate` verdict on their own,
# independent of the warning_count>=3 threshold (see `run()`).
_FORCE_REGENERATE_ISSUE_TYPES = frozenset(
    {
        "metadata_gender_mismatch",
        "metadata_ungrounded_timestamp",
        "metadata_template_artifact",
        "first_visit_trend_violation",
    }
)


def _is_no_data_placeholder_section(section_body: str) -> bool:
    """True when `section_body` is ENTIRELY a markdown table whose every
    data row (header/divider rows excluded) contains only "해당 없음"/"-"
    placeholder cells — i.e. the section explicitly states no data exists,
    rather than asserting any patient-specific fact. A section mixing
    placeholder rows with ANY other prose/data still requires evidence
    (this only exempts the all-placeholder case)."""
    stripped = section_body.strip()
    if not stripped:
        return False
    rows = _TABLE_ROW_RE.findall(stripped)
    if not rows:
        return False
    # Every non-table-syntax line in the section must be part of a table
    # row — a stray prose sentence outside the table still needs evidence.
    non_row_lines = [
        line for line in stripped.split("\n")
        if line.strip() and not _TABLE_ROW_RE.match(line.strip())
    ]
    if non_row_lines:
        return False
    data_rows = [r for r in rows[1:] if not _TABLE_DIVIDER_RE.match(r.strip())]
    if not data_rows:
        return False
    for row in data_rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if any(cell not in _NO_DATA_PLACEHOLDER_TOKENS for cell in cells):
            return False
    return True


def _is_no_data_bullet_section(section_body: str) -> bool:
    """BUG-071: the bullet-list counterpart of
    `_is_no_data_placeholder_section` above — True when `section_body` is
    ENTIRELY a markdown bullet list (`- label: value` / `- **label**:
    value`) whose every bullet's value is ONLY a "no data collected" marker
    (기록 없음/미수집/확인 필요/해당 없음 — the same `_NO_DATA_MARKER_RE`
    vocabulary BUG-069's metadata check already uses), i.e. the section
    explicitly declares nothing was collected for every one of its fields,
    rather than asserting any patient-specific fact. A bullet whose value
    contains the marker PLUS any other substantive text, or any non-bullet
    prose line, still requires evidence — this only exempts the
    all-placeholder-bullets case (same strictness discipline as the table
    variant)."""
    stripped = section_body.strip()
    if not stripped:
        return False
    lines = [line for line in stripped.split("\n") if line.strip()]
    bullet_matches = [_BULLET_LINE_RE.match(line.strip()) for line in lines]
    if not bullet_matches or any(m is None for m in bullet_matches):
        return False
    for match in bullet_matches:
        content = match.group(1).strip()
        # Split "label: value" (bold-label form or plain) at the first
        # colon; if there is no colon, the whole bullet is the value.
        parts = re.split(r"[:：]", content, maxsplit=1)
        value = parts[-1].strip() if len(parts) > 1 else content
        if not _NO_DATA_MARKER_RE.search(value):
            return False
        # The value must be nothing MORE than the marker (plus trivial
        # surrounding punctuation) — a bullet like "기록 없음, 다만 환자가
        # X라고 언급함" still asserts a patient-specific fact and must not
        # be exempted.
        residual = _NO_DATA_MARKER_RE.sub("", value).strip(" .()·,`")
        if residual:
            return False
    return True


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
        ref_issues = self._check_dangling_references(inp.report_markdown, known_ids)
        issues.extend(ref_issues)

        # ── Check 7: Metadata grounding (BUG-069) ────────────────────
        metadata_issues = self._check_metadata_grounding(
            inp.report_markdown,
            patient_gender=inp.patient_gender,
            session_started_at=inp.session_started_at,
            session_ended_at=inp.session_ended_at,
        )
        issues.extend(metadata_issues)

        # ── Check 8: First-visit longitudinal trend prohibition (BUG-069) ──
        trend_issues = self._check_first_visit_longitudinal_trend(
            inp.report_markdown,
            is_first_visit=inp.is_first_visit,
            prior_handoff_present=inp.prior_handoff_present,
        )
        issues.extend(trend_issues)

        # ── Determine action ─────────────────────────────────────────
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        if error_count > 0:
            action = VerifierAction.reject
        elif warning_count >= 3 or any(
            i.issue_type in _FORCE_REGENERATE_ISSUE_TYPES for i in issues
        ):
            # BUG-069: fabricated-metadata/first-visit-trend issues force a
            # regenerate on their own, independent of the warning_count>=3
            # threshold — a single fabricated gender or invented prior-visit
            # baseline is exactly the class of defect the BUG-049 lineage
            # treats as never-tolerable, not something to average away
            # against otherwise-clean warnings.
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
        """Find sections with clinical content but no evidence citations.

        BUG-050 (2026-07-21): live reproduction on a real 12-turn, 100%-
        coverage session showed this check firing on sections that were
        never asserting a patient-specific claim at all — an honest
        "해당 없음"(not applicable) data table (섹션 6, no scale
        administered) and the report's own limitations/missing-info
        disclaimer section (섹션 10, "추가 정보 필요 사항") — plus the
        report's administrative header sections (섹션 1/2, encounter
        metadata — `docs/ai/agents/04_clinical_slot.md`'s own "시스템
        영역" classification, never a patient-stated fact to cite). Two
        targeted, evidence-based exemptions added; every OTHER section
        (3, 4, 5, 7, 9, 11, 12 — the actual clinical-content sections)
        keeps the exact same evidence-citation requirement as before —
        this is not a blanket relaxation.
        """
        issues: list[VerifierIssue] = []

        # Split by section headers
        sections = re.split(r"(?m)^###?\s+", report)

        for section in sections:
            if not section.strip():
                continue

            lines = section.strip().split("\n")
            section_title = lines[0].strip() if lines else "unknown"
            section_body = "\n".join(lines[1:]) if len(lines) > 1 else ""

            # Skip sections that don't need evidence (metadata sections).
            # "추가 정보 필요" (BUG-050): the Korean-language equivalent of
            # this list's own pre-existing English "missing information"
            # entry — the report's actual section 10 heading is always
            # Korean ("섹션 10. 추가 정보 필요 사항"), which never matched
            # the English-only keyword this list already intended to catch.
            skip_sections = {
                "missing information", "evidence table", "누락", "근거 표",
                "추가 정보 필요",
            }
            if any(skip in section_title.lower() for skip in skip_sections):
                continue

            # Administrative/system-authored sections (BUG-050): sections
            # 1-2 map to `encounter_metadata` (진료 기본정보/평가 일시 및
            # 환경) — system/administrative content, never a patient-
            # stated clinical claim requiring evidence.
            section_number_match = _SECTION_NUMBER_TITLE_RE.match(section_title)
            if section_number_match and int(section_number_match.group(1)) in (
                _ADMINISTRATIVE_SECTION_NUMBERS
            ):
                continue

            # "해당 없음"-only data table (BUG-050): a section whose only
            # data-row content declares that no data exists (e.g. no
            # structured scale was administered) asserts nothing about the
            # patient — nothing to cite.
            if _is_no_data_placeholder_section(section_body):
                continue

            # "기록 없음"/"미수집"-only bullet list (BUG-071): the same
            # no-data declaration as the table exemption above, just
            # rendered as a bullet list — the v4.3+ prompt's actual §3/§7
            # convention for "no data collected" fields (live-reproduced in
            # BUG-071's residual-non-convergence finding).
            if _is_no_data_bullet_section(section_body):
                continue

            # First-visit no-comparison-possible marker (BUG-069): section
            # 9's mandated safe-fallback phrase for first-visit/no-prior-
            # handoff sessions is an administrative declaration, not a
            # patient-specific clinical claim — exempt it the same way the
            # two exemptions above exempt their own no-data declarations.
            if section_number_match and int(section_number_match.group(1)) == 9 and (
                _FIRST_VISIT_NO_TREND_MARKER_RE.search(section_body)
            ):
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

    def _check_dangling_references(
        self, report: str, known_ids: set[str]
    ) -> list[VerifierIssue]:
        """Check for evidence IDs in body not in registry and vice versa.

        BUG-071 (2026-07-23): live reproduction showed a body citing a
        GENUINE evidence ID (present in `known_ids`, i.e. actually supplied
        via `evidence_packets`) that section 12's own registry table simply
        forgot to list — an incomplete-registry defect, not a fabricated
        citation. The pre-existing code flagged this identically to a
        citation of an ID that does not exist at all, driving the same
        `dangling_reference` warning either way and inflating warning_count
        toward the regenerate threshold on otherwise-clean, genuinely-cited
        reports. `_check_unsupported_claims` already runs the real
        fabrication check (body ref not in `known_ids` at all) as its own
        `unsupported_claim` issue — so a body ref missing from the registry
        but present in `known_ids` is downgraded here to NOT be flagged
        (registry-completeness is cosmetic once the citation itself is
        verified genuine); a body ref missing from BOTH the registry AND
        `known_ids` still gets caught by `_check_unsupported_claims`'s
        existing fabrication check, so detection power for real dangling
        (fabricated) references is unchanged."""
        issues: list[VerifierIssue] = []

        # Split at section 12
        sec12_match = re.search(r"##\s+섹션\s+12\.", report)
        if not sec12_match:
            return issues

        body = report[:sec12_match.start()]
        registry = report[sec12_match.start():]

        body_refs = set(_EVIDENCE_REF_RE.findall(body))
        registry_refs = set(_EVIDENCE_REF_RE.findall(registry))

        # Body refs not in registry AND not a genuinely-supplied evidence ID
        # — a ref that IS in `known_ids` is a real citation the registry
        # merely forgot to list (see docstring above); a ref in neither is
        # a fabricated citation, already caught by `_check_unsupported_
        # claims`, so we don't double-flag it here either.
        for ref in body_refs - registry_refs:
            clean_id = ref.strip("[]")
            if clean_id in known_ids:
                continue
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

    @staticmethod
    def _extract_section_body(report: str, section_num: int) -> str | None:
        """Return section `section_num`'s body text (heading excluded), or
        None if that section heading is absent — used by the BUG-069
        metadata-grounding and first-visit-trend checks below."""
        pattern = re.compile(
            _SECTION_BODY_RE_TEMPLATE.format(n=section_num), re.DOTALL
        )
        match = pattern.search(report)
        return match.group() if match else None

    def _check_metadata_grounding(
        self,
        report: str,
        *,
        patient_gender: str | None,
        session_started_at: str | None,
        session_ended_at: str | None,
    ) -> list[VerifierIssue]:
        """BUG-069: sections 1/2 request patient gender/age/session-timing
        fields that `HandoffInput` does not carry at all today (confirmed —
        `handoff_generator.py`'s `_build_user_content` never serializes
        them). Any specific-looking assertion of these fields when the
        caller supplied no ground truth (`None`) is therefore necessarily
        fabricated, not merely unverifiable — this check flags it. If a
        future caller DOES supply ground truth, this upgrades to a mismatch
        comparison instead of a bare-assertion prohibition. Also flags the
        v4.3 prompt's own worked-example text ("(예: ...)", scoped to
        sections 1-2 only — BUG-071 residual false-positive, see the check
        site below) or unresolved `<...>` template placeholders (whole-
        report scan) leaking into the final output verbatim.
        """
        issues: list[VerifierIssue] = []

        sec1 = self._extract_section_body(report, 1) or ""
        gender_match = _GENDER_LINE_RE.search(sec1)
        if gender_match:
            value = gender_match.group(1).strip()
            if _GENDER_ASSERT_RE.search(value) and not _NO_DATA_MARKER_RE.search(value):
                if patient_gender is None:
                    issues.append(VerifierIssue(
                        issue_type="metadata_gender_mismatch",
                        description=(
                            f"섹션 1이 입력에 전혀 제공되지 않은 성별을 단정: '{value}' "
                            "(patient_gender 없음 — 날조)"
                        ),
                        location="섹션 1",
                        severity="warning",
                    ))
                else:
                    stated_female = bool(re.search(r"여성|female", value, re.IGNORECASE))
                    stated_male = bool(re.search(r"남성|male", value, re.IGNORECASE))
                    actual = patient_gender.strip().lower()
                    actual_female = actual in ("female", "여성", "f")
                    actual_male = actual in ("male", "남성", "m")
                    mismatch = (stated_female and actual_male) or (stated_male and actual_female)
                    if mismatch:
                        issues.append(VerifierIssue(
                            issue_type="metadata_gender_mismatch",
                            description=(
                                f"섹션 1의 성별('{value}')이 입력 patient_gender"
                                f"('{patient_gender}')와 불일치"
                            ),
                            location="섹션 1",
                            severity="warning",
                        ))

        sec2 = self._extract_section_body(report, 2) or ""
        for label, value in _TIMESTAMP_LINE_RE.findall(sec2):
            value = value.strip()
            if _NO_DATA_MARKER_RE.search(value):
                continue
            if _TIMESTAMP_VALUE_RE.search(value) and (
                session_started_at is None and session_ended_at is None
            ):
                issues.append(VerifierIssue(
                    issue_type="metadata_ungrounded_timestamp",
                    description=(
                        f"섹션 2의 '{label}'이 입력에 제공되지 않은 구체 시각을 단정: "
                        f"'{value}' (session_started_at/session_ended_at 없음 — 날조)"
                    ),
                    location="섹션 2",
                    severity="warning",
                ))

        # BUG-071 residual false-positive (2026-07-25, live re-verification
        # — EXP-032 track B/final, 3-attempt regenerate exhaustion persisted
        # even after the bullet-list-exemption + dangling-reference-registry
        # fixes above): `_TEMPLATE_EXAMPLE_ARTIFACT_RE` (`"(예: ...)"`) was
        # scanned across the ENTIRE report, but "(예: ...)" parenthetical
        # asides are ordinary, legitimate Korean clinical-writing style in
        # the free-text narrative sections (3/4/5/7/9/11 — e.g. "주요
        # 스트레스 요인(예: 직장 내 갈등)이 확인됨") — not a template-leak
        # artifact at all. This issue type is in `_FORCE_REGENERATE_ISSUE_
        # TYPES` (forces `regenerate` on a SINGLE occurrence, independent of
        # `warning_count`), and a model's phrasing habit is stable across
        # its own 3 regenerate attempts within one session — so a single
        # legitimate "(예: ...)" aside anywhere in the narrative guarantees
        # non-convergence across the entire retry budget, every time.
        #
        # The BUG-069 original repro this check exists for was scoped to
        # §1's identifier field specifically ("익명화 ID (예:
        # anon_20260723_001)" — a literal worked-example value echoed
        # verbatim into a metadata field, not a narrative aside). Narrowing
        # the "(예: ...)" scan to sections 1-2 (this method's own documented
        # scope — patient identifier/gender/session-timing metadata, per
        # this method's docstring) preserves that exact detection while
        # eliminating the narrative-section false positives: metadata
        # fields are short structured labels ("성별: ...", "식별자: ...")
        # where a worked-example annotation is unambiguously a template
        # leak, never legitimate clinical prose. `_TEMPLATE_PLACEHOLDER_
        # ARTIFACT_RE` (`"<...>"`, BUG-070's own §6 data-cell repro) stays
        # whole-report — angle-bracket placeholders essentially never occur
        # in legitimate Korean clinical narrative, so its false-positive
        # risk is negligible and BUG-070's detection power must not shrink.
        sec1_sec2 = sec1 + "\n" + sec2
        if _TEMPLATE_EXAMPLE_ARTIFACT_RE.search(sec1_sec2):
            issues.append(VerifierIssue(
                issue_type="metadata_template_artifact",
                description=(
                    "섹션 1-2(환자 식별자/성별/세션 시각)에 프롬프트 템플릿의 "
                    "예시 표기가 그대로 노출됨 (예: '(예: ...)' 형태)"
                ),
                location="섹션 1-2",
                severity="warning",
            ))
        if _TEMPLATE_PLACEHOLDER_ARTIFACT_RE.search(report):
            issues.append(VerifierIssue(
                issue_type="metadata_template_artifact",
                description=(
                    "보고서에 미치환 템플릿 placeholder 표기가 그대로 노출됨 "
                    "(예: '<...>' 형태)"
                ),
                location="report",
                severity="warning",
            ))

        return issues

    def _check_first_visit_longitudinal_trend(
        self,
        report: str,
        *,
        is_first_visit: bool,
        prior_handoff_present: bool,
    ) -> list[VerifierIssue]:
        """BUG-069: a first-visit session with no real prior handoff must
        never present a longitudinal "이전" comparison in section 9 — doing
        so fabricates a prior-visit baseline and asserts a directional
        clinical trend (e.g. "PHQ-9 악화") that cannot exist for that
        patient. Requires BOTH `is_first_visit` and an absent
        `prior_handoff_present` to agree before enforcing (a caller that
        marks `is_first_visit=False` without actually supplying prior
        handoff text is a separate, pre-existing contract concern, not this
        check's job)."""
        if not is_first_visit or prior_handoff_present:
            return []

        sec9 = self._extract_section_body(report, 9)
        if not sec9:
            return []

        rows = [
            line.strip() for line in sec9.split("\n")
            if line.strip().startswith("|") and not _TABLE_DIVIDER_RE.match(line.strip())
        ]
        if len(rows) < 2:
            return []

        data_rows = rows[1:]  # skip the header row
        for row in data_rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if len(cells) < 4:
                continue
            prior_cell = cells[3]
            if re.search(r"\d", prior_cell):
                return [VerifierIssue(
                    issue_type="first_visit_trend_violation",
                    description=(
                        "초진(이전 handoff 없음) 세션인데 섹션 9가 존재하지 않는 이전 "
                        f"방문의 구체적 수치('{prior_cell}')를 인용해 종단 추세를 주장함"
                    ),
                    location="섹션 9",
                    severity="warning",
                )]

        return []
