"""BUG-071 regression — `EvidenceVerifierAgent` must not fail-open-loop a
genuinely-compliant handoff report into regenerate-budget exhaustion via two
pre-existing (BUG-050/BUG-069-lineage) over-strictness mechanisms isolated
during v4.5 live re-verification:

(a) `_is_no_data_placeholder_section` only exempted an ALL-placeholder
    markdown TABLE from the "clinical content without citation" check — the
    v4.3+ prompt's actual §3/§7 convention renders "no data collected"
    fields as a markdown BULLET LIST (`- **label**: 기록 없음`), which was
    never exempted and tripped `unsupported_claim` on every compliant
    report.
(b) `_check_dangling_references` compared body-cited evidence IDs against
    ONLY section 12's own registry table, not the full `evidence_packets`
    ground truth — a body citing a GENUINE evidence ID that the registry
    table simply forgot to list was flagged identically to citing an ID
    that does not exist at all, double-counting toward warning_count>=3.

Both fixes must NOT weaken real fabrication detection: a bullet mixing a
no-data marker with actual patient-specific content, and a body citing an
evidence ID that is neither registered NOR a real `evidence_packets` member,
must still be caught (see the negative-control/regression tests below).

Fixtures are built directly from error.md BUG-071's v4.5 live-reproduction
evidence (session 1's saved `report_markdown`: §7 bullet "기록 없음" content
tripping `unsupported_claim`, and body-cited `[ev_msg_005]`/`[ev_msg_006]`
absent from section 12's registry tripping `dangling_reference`).
"""

from __future__ import annotations

import pytest

from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
    _is_no_data_bullet_section,
)
from src.schemas.common import EvidencePacket, EvidenceSource


def _packets(extra_ids: list[str] | None = None) -> list[EvidencePacket]:
    packets = [
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
    for eid in extra_ids or []:
        packets.append(
            EvidencePacket(
                evidence_id=eid,
                source_type=EvidenceSource.message,
                source_ref="환자 발화",
                content_summary="추가 발화 내용",
            )
        )
    return packets


_GROUNDED_SECTION1 = (
    "- **식별자**: 기록 없음\n- **연령대**: 기록 없음\n"
    "- **성별**: 기록 없음\n- **방문 유형**: 초진"
)
_GROUNDED_SECTION2 = (
    "- **사전문진 시작 일시**: 미수집\n- **사전문진 종료 일시**: 미수집\n"
    "- **소요 시간**: 미수집"
)
_GROUNDED_SECTION9_FIRST_VISIT = "**초진 — 종단 비교 불가 (이전 방문 기록 없음)**"


def _base_report(
    *,
    section3: str = "- 주호소 요약: 불안, 수면장애 `[ev_msg_001]`",
    section7: str = "- 과거 정신건강 관련 진료 이력: 미수집 `[ev_msg_001]`",
    section4_5_extra_refs: str = "",
    registry_extra_rows: str = "",
) -> str:
    """The real 12-section template shell, §3/§7 swappable to exercise the
    bullet no-data exemption, and body/registry ref lists swappable to
    exercise the dangling-reference-vs-registry check."""
    return f"""## 섹션 1. 환자 기본 정보
{_GROUNDED_SECTION1}

## 섹션 2. 평가 일시 및 환경
{_GROUNDED_SECTION2}

## 섹션 3. 주호소 및 현병력
{section3}

## 섹션 4. 주요 증상
| 영역 후보 | 주요 근거 | 신뢰도 |
|---|---|---|
| 우울 영역 | `[ev_msg_001]`{section4_5_extra_refs} | 높음 |

## 섹션 5. CTRS 기반 위험도 평가
| 항목 | 내용 |
|---|---|
| **CTRS 단계** | 4 `[ev_scale_001]` |

## 섹션 6. 구조화 척도 결과
| 척도명 | 총점 |
|---|---|
| PHQ-9 | 10 `[ev_scale_001]` |

## 섹션 7. 과거 병력 및 현재 약물
{section7}

## 섹션 8. 업로드 문서 요약
- 해당 없음

## 섹션 9. 종단적 상태 변화
{_GROUNDED_SECTION9_FIRST_VISIT}

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
{registry_extra_rows}
"""


# ── (a) bullet-list no-data exemption ─────────────────────────────────


def test_is_no_data_bullet_section_all_markers_true() -> None:
    body = (
        "- **과거 정신건강 관련 진료 이력**: 기록 없음\n"
        "- **현재 복용 약물**: 미수집\n"
        "- **가족력**: 해당 없음"
    )
    assert _is_no_data_bullet_section(body) is True


def test_is_no_data_bullet_section_mixed_content_false() -> None:
    """Regression guard: a bullet mixing the marker with a real assertion
    must NOT be exempted — detection power preserved."""
    body = (
        "- **과거 정신건강 관련 진료 이력**: 기록 없음\n"
        "- **현재 복용 약물**: 미수집, 다만 환자가 수면제 복용을 언급함"
    )
    assert _is_no_data_bullet_section(body) is False


def test_is_no_data_bullet_section_non_bullet_prose_false() -> None:
    body = "환자는 특별한 과거력이 없다고 진술함."
    assert _is_no_data_bullet_section(body) is False


@pytest.mark.asyncio
async def test_bullet_no_data_section_no_longer_triggers_unsupported_claim() -> None:
    """BUG-071 repro (a): §7 rendered as a bullet list of 'no data
    collected' fields, with NO evidence citation, must not force
    regenerate — the report is a genuinely clean, compliant first-visit
    report and should converge on attempt 1."""
    report = _base_report(
        section7=(
            "- **과거 정신건강 관련 진료 이력**: 기록 없음\n"
            "- **현재 복용 약물**: 기록 없음\n"
            "- **가족력**: 해당 정보 없음"
        )
    )
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
    assert not any(i.issue_type == "unsupported_claim" for i in result.issues)


@pytest.mark.asyncio
async def test_bullet_section_with_real_content_still_flagged() -> None:
    """Regression guard: a §7 bullet list asserting REAL clinical content
    with no evidence citation must still trigger `unsupported_claim` —
    the bullet exemption must not become a blanket §3/§7 free pass."""
    report = _base_report(
        section7=(
            "- **과거 정신건강 관련 진료 이력**: 2020년 우울증으로 입원 치료 이력 있음\n"
            "- **현재 복용 약물**: 없음"
        )
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s2",
            request_id="r2",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert any(
        i.issue_type == "unsupported_claim" and "섹션 7" in i.location
        for i in result.issues
    ), [i.description for i in result.issues]


# ── (b) dangling-reference vs registry-vs-known_ids ───────────────────


@pytest.mark.asyncio
async def test_genuine_evidence_id_missing_from_registry_not_flagged() -> None:
    """BUG-071 repro (b): body cites `[ev_msg_005]`/`[ev_msg_006]` — REAL
    evidence IDs present in `evidence_packets` — that section 12's own
    registry table simply forgot to list. Must not be flagged
    `dangling_reference` (registry-incompleteness is cosmetic once the
    citation itself is verified genuine)."""
    report = _base_report(
        section4_5_extra_refs=", `[ev_msg_005]`, `[ev_msg_006]`",
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s3",
            request_id="r3",
            report_markdown=report,
            evidence_packets=_packets(extra_ids=["ev_msg_005", "ev_msg_006"]),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert not any(i.issue_type == "dangling_reference" for i in result.issues), [
        i.description for i in result.issues
    ]
    assert result.action == VerifierAction.passed, [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_fabricated_evidence_id_still_flagged() -> None:
    """Regression guard: a body citing an evidence ID that is NEITHER in
    section 12's registry NOR in the real `evidence_packets` set (i.e.
    genuinely fabricated, not just under-registered) must still be caught
    — detection power for real dangling/fabricated citations is preserved,
    just surfaced as `unsupported_claim` (the pre-existing, unmodified
    known_ids check) instead of a duplicate `dangling_reference`."""
    report = _base_report(
        section4_5_extra_refs=", `[ev_msg_999]`",
    )
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
    assert any(
        i.issue_type == "unsupported_claim" and "ev_msg_999" in i.description
        for i in result.issues
    ), [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_orphan_registry_entry_still_flagged() -> None:
    """Regression guard: a registry row never cited in the body is a
    distinct, unmodified check (`orphan_evidence`) and must still fire —
    the BUG-071 fix only touches the known-ID exemption for body-cited
    refs, not registry-side orphan detection."""
    report = _base_report(
        registry_extra_rows="| `[ev_msg_007]` | 대화 | 턴 3 | 인용되지 않은 근거 |",
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s5",
            request_id="r5",
            report_markdown=report,
            evidence_packets=_packets(extra_ids=["ev_msg_007"]),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert any(
        i.issue_type == "orphan_evidence" and "ev_msg_007" in i.description
        for i in result.issues
    ), [i.description for i in result.issues]


@pytest.mark.asyncio
async def test_v45_live_repro_shape_now_converges_clean() -> None:
    """End-to-end BUG-071 repro: reconstructs the actual v4.5 live-session
    shape (bullet-list §7 no-data content + genuine-but-unregistered
    ev_msg_005/006 body refs) that previously exhausted the 3-attempt
    regenerate budget and forced `requires_human_review`. Must now pass on
    attempt 1."""
    report = _base_report(
        section3="- 주호소 요약: 불안, 수면장애 `[ev_msg_001]`",
        section7=(
            "- **과거 정신건강 관련 진료 이력**: 기록 없음\n"
            "- **현재 복용 약물**: 기록 없음"
        ),
        section4_5_extra_refs=", `[ev_msg_005]`, `[ev_msg_006]`",
    )
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="s6",
            request_id="r6",
            report_markdown=report,
            evidence_packets=_packets(extra_ids=["ev_msg_005", "ev_msg_006"]),
            is_first_visit=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.passed, [i.description for i in result.issues]
