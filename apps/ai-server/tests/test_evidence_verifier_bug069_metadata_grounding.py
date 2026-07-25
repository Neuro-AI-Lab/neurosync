"""BUG-069 regression — `EvidenceVerifierAgent` must force `regenerate` on
fabricated handoff-narrative metadata (gender mismatch/ungrounded-assertion,
ungrounded session timestamps, template-example artifact leakage) and on a
first-visit session that fabricates a longitudinal "이전" trend in section 9.

Fixtures below are built directly from `error.md` BUG-069's reproduction
evidence (`experiments/EXP-031/logs_rerun/S14_clinician_get_report_bugfix.
json`'s `narrative.report_markdown`) — same shape of §1 gender assertion,
§2 timestamp assertion, §1 identifier "(예: ...)" artifact, and §9
fabricated-prior-baseline trend table for a `초진` (first-visit) session
with no prior handoff.
"""

from __future__ import annotations

import pytest

from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
)
from src.schemas.common import EvidencePacket, EvidenceSource


def _packets() -> list[EvidencePacket]:
    return [
        EvidencePacket(
            evidence_id="ev_msg_001",
            source_type=EvidenceSource.message,
            source_ref="환자 발화",
            content_summary="요즘 잠을 잘 못 자고 계속 피곤해요.",
        ),
        EvidencePacket(
            evidence_id="ev_scale_001",
            source_type=EvidenceSource.scale,
            source_ref="PHQ9",
            content_summary="PHQ9: 10 (moderate)",
        ),
    ]


def _base_report(section1: str, section2: str, section9: str) -> str:
    """A minimal 12-section report shell matching the real template's
    section-title contract, with sections 1/2/9 swappable per fixture."""
    return f"""## 섹션 1. 환자 기본 정보
{section1}

## 섹션 2. 평가 일시 및 환경
{section2}

## 섹션 3. 주호소 및 현병력
- 주호소 요약: 불안, 수면장애 `[ev_msg_001]`

## 섹션 4. 주요 증상
| 영역 후보 | 주요 근거 | 신뢰도 |
|---|---|---|
| 우울 영역 | `[ev_msg_001]` | 높음 |

## 섹션 5. CTRS 기반 위험도 평가
| 항목 | 내용 |
|---|---|
| **CTRS 단계** | 4 `[ev_scale_001]` |

## 섹션 6. 구조화 척도 결과
| 척도명 | 총점 |
|---|---|
| PHQ-9 | 10 `[ev_scale_001]` |

## 섹션 7. 과거 병력 및 현재 약물
- 과거 정신건강 관련 진료 이력: 미수집 `[ev_msg_001]`

## 섹션 8. 업로드 문서 요약
- 해당 없음

## 섹션 9. 종단적 상태 변화
{section9}

## 섹션 10. 추가 정보 필요 사항
- 미수집 slot: 없음
- 본 보고서는 AI 보조 사전문진 결과이며, 진단이 아닙니다.

## 섹션 11. 추천 진료과 및 사유
| CTRS | 권장 조치 |
|---|---|
| 4 | 정신건강의학과 상담 고려 `[ev_msg_001]` |

## 섹션 12. 근거 레지스트리
| Evidence ID | Source Type | Source Reference | 내용 요약 |
|---|---|---|---|
| `[ev_msg_001]` | 대화 | 턴 1 | 요즘 잠을 잘 못 자고 계속 피곤해요. |
| `[ev_scale_001]` | 척도 | PHQ-9 결과 | 10, moderate |
"""


_GROUNDED_SECTION1 = (
    "- **식별자**: 기록 없음\n- **연령대**: 기록 없음\n"
    "- **성별**: 기록 없음\n- **방문 유형**: 초진"
)
_GROUNDED_SECTION2 = (
    "- **사전문진 시작 일시**: 미수집\n- **사전문진 종료 일시**: 미수집\n"
    "- **소요 시간**: 미수집"
)
_GROUNDED_SECTION9_FIRST_VISIT = "**초진 — 종단 비교 불가 (이전 방문 기록 없음)**"


@pytest.mark.asyncio
async def test_grounded_first_visit_report_passes() -> None:
    """A report following the v4.3 metadata discipline (기록 없음/미수집
    everywhere ungrounded, no §9 trend table) must NOT trigger regenerate —
    a negative control proving the new checks don't over-fire on compliant
    output."""
    report = _base_report(_GROUNDED_SECTION1, _GROUNDED_SECTION2, _GROUNDED_SECTION9_FIRST_VISIT)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s1",
            request_id="r1",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.passed, [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_ungrounded_gender_assertion_forces_regenerate() -> None:
    """BUG-069 repro: §1 asserts a specific gender ('남성') when the caller
    supplied no `patient_gender` ground truth at all — necessarily
    fabricated."""
    section1 = (
        "- **식별자**: 기록 없음\n- **연령대**: 30대 (추정)\n"
        "- **성별**: 남성\n- **방문 유형**: 초진"
    )
    report = _base_report(section1, _GROUNDED_SECTION2, _GROUNDED_SECTION9_FIRST_VISIT)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s2",
            request_id="r2",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
            patient_gender=None,
        )
    )
    assert result.action == VerifierAction.regenerate
    assert any(i.issue_type == "metadata_gender_mismatch" for i in result.issues)


@pytest.mark.asyncio
async def test_gender_mismatch_against_ground_truth_forces_regenerate() -> None:
    """When ground truth IS available (future apps/api enrichment), a
    stated gender that contradicts it must also force regenerate."""
    section1 = (
        "- **식별자**: 기록 없음\n- **연령대**: 기록 없음\n"
        "- **성별**: 남성\n- **방문 유형**: 초진"
    )
    report = _base_report(section1, _GROUNDED_SECTION2, _GROUNDED_SECTION9_FIRST_VISIT)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s3",
            request_id="r3",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
            patient_gender="female",
        )
    )
    assert result.action == VerifierAction.regenerate
    assert any(i.issue_type == "metadata_gender_mismatch" for i in result.issues)


@pytest.mark.asyncio
async def test_ungrounded_timestamp_assertion_forces_regenerate() -> None:
    """BUG-069 repro: §2 asserts specific clock times/duration when the
    caller supplied no session timing ground truth at all."""
    section2 = (
        "- **사전문진 시작 일시**: 2026-07-23 14:30\n"
        "- **사전문진 종료 일시**: 2026-07-23 14:45\n"
        "- **소요 시간**: 15분"
    )
    report = _base_report(_GROUNDED_SECTION1, section2, _GROUNDED_SECTION9_FIRST_VISIT)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s4",
            request_id="r4",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.regenerate
    assert any(i.issue_type == "metadata_ungrounded_timestamp" for i in result.issues)


@pytest.mark.asyncio
async def test_template_example_artifact_leak_forces_regenerate() -> None:
    """BUG-069 repro: §1's identifier literally echoes the prompt's own
    "(예: ...)" worked-example annotation as if it were a real value."""
    section1 = (
        "- **식별자**: 익명화 ID (예: `anon_20260723_001`)\n"
        "- **연령대**: 기록 없음\n- **성별**: 기록 없음\n- **방문 유형**: 초진"
    )
    report = _base_report(section1, _GROUNDED_SECTION2, _GROUNDED_SECTION9_FIRST_VISIT)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s5",
            request_id="r5",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.regenerate
    assert any(i.issue_type == "metadata_template_artifact" for i in result.issues)


@pytest.mark.asyncio
async def test_first_visit_fabricated_longitudinal_trend_forces_regenerate() -> None:
    """BUG-069 repro: a first-visit session (no prior handoff) whose §9
    fabricates a prior PHQ-9/CTRS/sleep baseline to assert an "악화" trend —
    the exact REV-019-escalated failure pattern (directional clinical
    inference error, not just a labeling inconsistency)."""
    section9 = (
        "| 도메인 | 변화 | 현재 | 이전 | 근거 |\n"
        "|---|---|---|---|---|\n"
        "| 수면 | 악화 | 3시간 미만 | 6시간 이상 | `[ev_msg_001]` |\n"
        "| PHQ-9 | 악화 | 10점 | 0점 (초진) | `[ev_scale_001]` |\n"
    )
    report = _base_report(_GROUNDED_SECTION1, _GROUNDED_SECTION2, section9)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s6",
            request_id="r6",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.regenerate
    assert any(i.issue_type == "first_visit_trend_violation" for i in result.issues)


@pytest.mark.asyncio
async def test_returning_patient_with_real_prior_handoff_trend_is_allowed() -> None:
    """Negative control: a returning-patient session (`is_first_visit=False`,
    `prior_handoff_present=True`) presenting the SAME §9 trend-table shape
    must NOT trigger the first-visit-trend check — the prohibition is
    scoped to fabricated (first-visit / no-prior-handoff) longitudinal
    claims only, not to legitimate longitudinal reporting."""
    section9 = (
        "| 도메인 | 변화 | 현재 | 이전 | 근거 |\n"
        "|---|---|---|---|---|\n"
        "| PHQ-9 | 악화 | 10점 | 5점 | `[ev_scale_001]`, `[ev_handoff_001]` |\n"
    )
    report = _base_report(
        "- **식별자**: 기록 없음\n- **연령대**: 기록 없음\n"
        "- **성별**: 기록 없음\n- **방문 유형**: 재진",
        _GROUNDED_SECTION2,
        section9,
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s7",
            request_id="r7",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=False,
            prior_handoff_present=True,
        )
    )
    assert not any(i.issue_type == "first_visit_trend_violation" for i in result.issues)
