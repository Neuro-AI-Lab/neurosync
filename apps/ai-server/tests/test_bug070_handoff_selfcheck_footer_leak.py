"""BUG-070 residual regression — v4.4's own "작성 후 자체 점검" self-check
discipline caused the model to append a RESULT SUMMARY after section 12
(e.g. "**점검 완료**: ... `` `<...>` `` 형태의 placeholder 문자열 없음"),
and that summary sentence itself quotes the literal `<...>` token (to
assert its absence) — which matches `evidence_verifier.py`'s existing
whole-report `_TEMPLATE_PLACEHOLDER_ARTIFACT_RE`, a false positive that
forces `metadata_template_artifact` regenerate on every attempt.

Live evidence (qa W2b re-verification, both real solar-pro3 sessions
exhausting 3/3 regenerate attempts): `experiments/EXP-031/logs_bug069/
resp_session1_v44_13722fd0.json`, `resp_session3_v44_new.json`,
`ai_server_stdout_v44.log`. The footer text asserted below is copied
VERBATIM from `resp_session1_v44_13722fd0.json`'s `report_markdown` field
(the exact self-check footer the model actually produced) — only the
surrounding 12-section shell is the project's own established
citation-safe fixture (mirrors `test_bug070_handoff_scale_placeholder_
leak.py`'s `_base_report` helper) so the test isolates the footer signal
from the separate, out-of-scope citation-completeness gap those two live
sessions also happen to carry (BUG-050 lineage, sections 3/7's non-table
"미수집" bullets — not part of this fix's scope).

Three things are asserted:
1. The REAL captured self-check footer, appended verbatim to an otherwise
   clean report, forces `regenerate` via `metadata_template_artifact` alone
   (reproduces the exact BUG-070-W2b live failure mode).
2. The same report with the footer removed (i.e. the v4.5-mandated
   "report ends at section 12" discipline) passes verification on attempt
   1 — convergence achieved.
3. A genuine data-cell `<...>` leak (e.g. an un-grounded section 6 cell)
   still forces regenerate regardless of the footer fix — true-positive
   detection is not weakened (BUG-070's original defect stays caught).
"""

from __future__ import annotations

import pytest

from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
)
from src.agents.handoff_generator import _PROMPT_VERSION
from src.schemas.common import EvidencePacket, EvidenceSource

# Copied verbatim from experiments/EXP-031/logs_bug069/
# resp_session1_v44_13722fd0.json's `report_markdown` field — the actual
# self-check footer the live model produced after v4.4's own "작성 후 자체
# 점검" item 5 instructed it to re-verify no `<...>` leak remained.
_REAL_LIVE_SELFCHECK_FOOTER = (
    "\n\n**점검 완료**:  \n"
    "- 12개 섹션 모두 존재  \n"
    "- 모든 `[ev_xxx_NNN]` 인용이 섹션 12에 등록  \n"
    "- 섹션 12에 미등록된 인용 없음  \n"
    "- 진단 확정 표현 없음  \n"
    "- `` `<...>` `` 형태의 placeholder 문자열 없음"
)


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


def _clean_report(section6: str) -> str:
    """A minimal 12-section report shell that is otherwise fully compliant
    (no citation gaps, no other verifier issues) — mirrors `test_bug070_
    handoff_scale_placeholder_leak.py`'s `_base_report` helper, so any
    `regenerate` verdict below is attributable ONLY to whatever is appended
    after section 12 (the self-check footer) or swapped into section 6, not
    to unrelated pre-existing warnings."""
    return f"""## 섹션 1. 환자 기본 정보
- **식별자**: 기록 없음
- **연령대**: 기록 없음
- **성별**: 기록 없음
- **방문 유형**: 초진

## 섹션 2. 평가 일시 및 환경
- **사전문진 시작 일시**: 미수집
- **사전문진 종료 일시**: 미수집
- **소요 시간**: 미수집

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
{section6}

## 섹션 7. 과거 병력 및 현재 약물
- 과거 정신건강 관련 진료 이력: 미수집 `[ev_msg_001]`

## 섹션 8. 업로드 문서 요약
- 해당 없음

## 섹션 9. 종단적 상태 변화
**초진 — 종단 비교 불가 (이전 방문 기록 없음)**

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


_SEC6_GROUNDED = (
    "| 척도명 | 총점 | Severity | 시행 일시 | 주요 양성 문항 |\n"
    "|---|---|---|---|---|\n"
    "| PHQ-9 | 10 `[ev_scale_001]` | moderate | 미수집 | 미수집 |\n"
)

_SEC6_LEAKED = (
    "| 척도명 | 총점 | Severity | 시행 일시 | 주요 양성 문항 |\n"
    "|---|---|---|---|---|\n"
    "| PHQ-9 | 10 `[ev_scale_001]` | moderate | `<시행 일시>` | `<주요 양성 문항>` |\n"
)


@pytest.mark.asyncio
async def test_real_live_selfcheck_footer_forces_regenerate() -> None:
    """BUG-070-W2b repro: the REAL captured self-check footer (verbatim from
    resp_session1_v44_13722fd0.json), appended to an otherwise-clean
    report, forces `regenerate` via `metadata_template_artifact` alone —
    this is the exact false-positive that exhausted 3/3 live attempts."""
    report = _clean_report(_SEC6_GROUNDED) + _REAL_LIVE_SELFCHECK_FOOTER
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="bug070-w2b-s1",
            request_id="bug070-w2b-r1",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            has_scale_scores=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.regenerate, [i.description for i in result.issues]
    assert any(i.issue_type == "metadata_template_artifact" for i in result.issues)


@pytest.mark.asyncio
async def test_clean_report_without_selfcheck_footer_converges() -> None:
    """v4.5 convergence guarantee: the SAME report, with the self-check
    footer removed (the v4.5-mandated "report ends at section 12, no
    meta-commentary after it" discipline), passes verification on the
    first attempt — no regenerate, no fail-open."""
    report = _clean_report(_SEC6_GROUNDED)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="bug070-w2b-s2",
            request_id="bug070-w2b-r2",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            has_scale_scores=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.passed, [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_genuine_data_cell_leak_still_forces_regenerate_without_footer() -> None:
    """Defense-in-depth: a genuine data-cell `<...>` leak in section 6 (the
    ORIGINAL BUG-070 defect) must still force `regenerate` even with no
    self-check footer present at all — the footer fix must not weaken
    true-positive detection of real template-placeholder leakage."""
    report = _clean_report(_SEC6_LEAKED)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="bug070-w2b-s3",
            request_id="bug070-w2b-r3",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            has_scale_scores=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.regenerate
    assert any(i.issue_type == "metadata_template_artifact" for i in result.issues)


def test_prompt_version_pinned_to_v4_5() -> None:
    """`handoff_generator.py`'s runtime pin points at the v4.5 fix."""
    assert _PROMPT_VERSION == "v4.5"


def test_v4_5_prompt_file_declares_selfcheck_output_suppression() -> None:
    """The pinned v4.5 prompt file actually contains the new "자체 점검
    결과 비노출" discipline (report ends at section 12, no self-check
    result text in output) — guards against the prompt file and the
    runtime pin drifting apart."""
    from pathlib import Path

    prompt_path = (
        Path(__file__).resolve().parent.parent
        / "prompts"
        / "handoff_generator"
        / "v4.5.system.md"
    )
    text = prompt_path.read_text(encoding="utf-8")
    assert "자체 점검 결과 비노출 규율" in text
    assert "섹션 12" in text
    # v4.4's body must remain byte-identical (addition-only convention) —
    # spot-check a v4.4-specific worked example survives untouched.
    assert "템플릿 placeholder 전 섹션 스윕 규율 (v4.4 추가" in text


def test_v4_4_prompt_file_untouched() -> None:
    """v4.5 is addition-only over v4.4 — the v4.4 file itself must not have
    been modified (old prompt versions are preserved, never edited)."""
    from pathlib import Path

    v44_path = (
        Path(__file__).resolve().parent.parent
        / "prompts"
        / "handoff_generator"
        / "v4.4.system.md"
    )
    text = v44_path.read_text(encoding="utf-8")
    assert "# NeuroSync Handoff Generator System Prompt v4.4" in text
    assert "자체 점검 결과 비노출 규율" not in text
