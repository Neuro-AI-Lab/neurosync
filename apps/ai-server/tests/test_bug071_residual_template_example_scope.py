"""BUG-071 residual false-positive (2026-07-25, EXP-032 live re-verification
— even with the bullet-list-exemption + dangling-reference-registry fixes
already applied, live regenerate-budget exhaustion (8/11/10 issues across 3
attempts) persisted).

Root cause (confirmed by source read): `_check_metadata_grounding`'s
`_TEMPLATE_EXAMPLE_ARTIFACT_RE` (`"(예: ...)"`) was scanned across the
ENTIRE `report_markdown`, but a parenthetical "(예: ...)" aside is ordinary,
legitimate Korean clinical-writing style in the free-text narrative
sections (e.g. "주요 스트레스 요인(예: 직장 내 갈등)이 확인됨") — not a
template-leak artifact. This issue type (`metadata_template_artifact`) is
in `_FORCE_REGENERATE_ISSUE_TYPES`, forcing `regenerate` on a SINGLE
occurrence regardless of `warning_count` — and a model's own phrasing habit
recurs across its 3 regenerate attempts within one session, so a single
legitimate narrative aside guaranteed non-convergence every time.

Fix: the "(예: ...)" scan is now scoped to sections 1-2 only (patient
identifier/gender/session-timing metadata — this check's own documented
scope, and where the ORIGINAL BUG-069 repro's literal worked-example leak
"익명화 ID (예: anon_20260723_001)" actually occurred). `<...>` template
placeholders (BUG-070's own §6 data-cell repro) stay a whole-report scan —
angle-bracket text essentially never occurs in legitimate Korean clinical
narrative, so BUG-070's detection power is unaffected.
"""

from __future__ import annotations

import pytest
from test_bug071_no_data_bullet_and_dangling_registry import _base_report, _packets

from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
)


@pytest.mark.asyncio
async def test_narrative_parenthetical_example_no_longer_forces_regenerate() -> None:
    """The false-positive this fix closes: a legitimate clinical aside in
    §3's narrative body must not trip `metadata_template_artifact` (and
    therefore must not force `regenerate` on its own)."""
    report = _base_report(
        section3=(
            "- 주호소 요약: 주요 스트레스 요인(예: 직장 내 갈등)이 확인됨, "
            "불안·수면장애 `[ev_msg_001]`"
        )
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s-bug071-residual-1",
            request_id="r-bug071-residual-1",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert not any(
        i.issue_type == "metadata_template_artifact" for i in result.issues
    ), [i.description for i in result.issues]
    assert result.action == VerifierAction.passed, [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_narrative_parenthetical_example_in_section7_also_not_flagged() -> None:
    """Same false-positive shape in §7 (another common narrative section)."""
    report = _base_report(
        section7=(
            "- **과거 정신건강 관련 진료 이력**: 최근 스트레스원(예: 이직 준비)"
            " 관련 상담 이력 있음 `[ev_msg_001]`"
        )
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s-bug071-residual-2",
            request_id="r-bug071-residual-2",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert not any(
        i.issue_type == "metadata_template_artifact" for i in result.issues
    ), [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_original_section1_identifier_worked_example_leak_still_caught() -> None:
    """Regression guard: the ORIGINAL BUG-069 repro this check exists for
    — §1's identifier field literally echoing the prompt's own worked
    example ("익명화 ID (예: anon_20260723_001)") — must still be flagged.
    Detection power for the actual template-leak class is preserved, only
    the narrative-section false positives are eliminated."""
    report = _base_report().replace(
        "- **식별자**: 기록 없음",
        "- **식별자**: 익명화 ID (예: `anon_20260723_001`)",
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s-bug071-residual-3",
            request_id="r-bug071-residual-3",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert any(
        i.issue_type == "metadata_template_artifact" for i in result.issues
    ), [i.description for i in result.issues]
    assert result.action == VerifierAction.regenerate


@pytest.mark.asyncio
async def test_section2_timestamp_worked_example_leak_still_caught() -> None:
    """Regression guard: the same worked-example-leak class in §2 (session
    timing) must also still be caught — §1-2 scope is the check's real
    boundary, not §1 alone."""
    report = _base_report().replace(
        "- **사전문진 시작 일시**: 미수집",
        "- **사전문진 시작 일시**: (예: 2026-07-23 14:00)",
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s-bug071-residual-4",
            request_id="r-bug071-residual-4",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert any(
        i.issue_type == "metadata_template_artifact" for i in result.issues
    ), [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_section6_angle_bracket_placeholder_leak_still_whole_report_scoped() -> None:
    """Regression guard: `<...>` template-placeholder detection (BUG-070's
    own §6 repro) must remain whole-report scoped — unaffected by the
    "(예: ...)" scope narrowing, since it is a DIFFERENT regex/check
    branch."""
    report = _base_report().replace(
        "## 섹션 6. 구조화 척도 결과\n"
        "| 척도명 | 총점 |\n"
        "|---|---|\n"
        "| PHQ-9 | 10 `[ev_scale_001]` |",
        "## 섹션 6. 구조화 척도 결과\n"
        "| 척도명 | 시행 일시 | 총점 |\n"
        "|---|---|---|\n"
        "| PHQ-9 | <시행 일시> | 10 `[ev_scale_001]` |",
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s-bug071-residual-5",
            request_id="r-bug071-residual-5",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert any(
        i.issue_type == "metadata_template_artifact" for i in result.issues
    ), [i.description for i in result.issues]
