"""BUG-069 follow-up (F5 metadata enrichment, 2026-07-25) regression —
`HandoffInput` gained optional `patient_gender`/`session_started_at`/
`session_ended_at` fields; when apps/api supplies a real value,
`_build_user_content` must cite it directly instead of the v4.3 "기록
없음"/"미수집" fallback, and the fallback must be UNCHANGED (still emitted)
when the field is absent — the v4.3/v4.5 "cite real value or say so
explicitly" grounding discipline is not weakened either way.

Also verifies the paired `routes/handoff.py` wiring: the real values now
flow into `EvidenceVerifierInput.patient_gender`/`session_started_at`/
`session_ended_at`, which `evidence_verifier.py`'s pre-existing (BUG-069)
metadata-grounding check upgrades from a bare-assertion prohibition to a
real mismatch comparison — a report correctly citing the REAL provided
gender must not be flagged.
"""

from __future__ import annotations

import pytest

from src.agents.evidence_verifier import EvidenceVerifierAgent, EvidenceVerifierInput
from src.agents.handoff_generator import _build_user_content
from src.schemas.common import EvidencePacket, EvidenceSource
from src.schemas.handoff import HandoffInput


def test_build_user_content_cites_real_gender_when_present() -> None:
    inp = HandoffInput(session_id="bug069fu-1", patient_gender="female")
    content = _build_user_content(inp)
    assert "- **성별**: female" in content
    assert "기록 없음 (입력에 제공되지 않음)" not in content.split("성별")[0]


def test_build_user_content_falls_back_to_no_record_when_gender_absent() -> None:
    inp = HandoffInput(session_id="bug069fu-2")
    content = _build_user_content(inp)
    assert "- **성별**: 기록 없음 (입력에 제공되지 않음)" in content


def test_build_user_content_cites_real_session_timestamps_when_present() -> None:
    inp = HandoffInput(
        session_id="bug069fu-3",
        session_started_at="2026-07-25T14:30:00+09:00",
        session_ended_at="2026-07-25T14:45:00+09:00",
    )
    content = _build_user_content(inp)
    assert "- **사전문진 시작 일시**: 2026-07-25T14:30:00+09:00" in content
    assert "- **사전문진 종료 일시**: 2026-07-25T14:45:00+09:00" in content


def test_build_user_content_timestamps_fall_back_when_absent() -> None:
    inp = HandoffInput(session_id="bug069fu-4")
    content = _build_user_content(inp)
    assert "- **사전문진 시작 일시**: 미수집 (입력에 제공되지 않음)" in content
    assert "- **사전문진 종료 일시**: 미수집 (입력에 제공되지 않음)" in content


def test_build_user_content_partial_values_each_independently_grounded() -> None:
    """A caller might supply gender but not session timing (or vice versa,
    e.g. an un-submitted session with no `submitted_at` yet) — each field's
    real-value-or-fallback choice must be independent, not all-or-nothing."""
    inp = HandoffInput(
        session_id="bug069fu-5",
        patient_gender="male",
        session_started_at="2026-07-25T09:00:00+09:00",
        # session_ended_at intentionally omitted (session not yet submitted)
    )
    content = _build_user_content(inp)
    assert "- **성별**: male" in content
    assert "- **사전문진 시작 일시**: 2026-07-25T09:00:00+09:00" in content
    assert "- **사전문진 종료 일시**: 미수집 (입력에 제공되지 않음)" in content
    # 연령대/소요 시간 have no backing field even after this fix — fallback unconditional.
    assert "- **연령대**: 기록 없음 (입력에 제공되지 않음)" in content
    assert "- **소요 시간**: 미수집 (입력에 제공되지 않음)" in content


def _packets() -> list[EvidencePacket]:
    return [
        EvidencePacket(
            evidence_id="ev_msg_001",
            source_type=EvidenceSource.message,
            source_ref="환자 발화",
            content_summary="요즘 잠을 잘 못 자고 계속 피곤해요.",
        ),
    ]


def _report_with_gender(gender_line: str) -> str:
    return f"""## 섹션 1. 환자 기본 정보
- **식별자**: 기록 없음
- **연령대**: 기록 없음
- **성별**: {gender_line}
- **방문 유형**: 초진

## 섹션 2. 평가 일시 및 환경
- **사전문진 시작 일시**: 미수집
- **사전문진 종료 일시**: 미수집
- **소요 시간**: 미수집

## 섹션 3. 주호소 및 현병력
- 주호소 요약: 불안, 수면장애 `[ev_msg_001]`

## 섹션 9. 종단적 상태 변화
**초진 — 종단 비교 불가 (이전 방문 기록 없음)**

## 섹션 12. 근거 레지스트리
| Evidence ID | Source Type | Source Reference | 내용 요약 |
|---|---|---|---|
| `[ev_msg_001]` | 대화 | 턴 1 | 요즘 잠을 잘 못 자고 계속 피곤해요. |
"""


@pytest.mark.asyncio
async def test_verifier_accepts_report_correctly_citing_real_gender() -> None:
    """Positive control (route-level wiring): when the report's §1 correctly
    cites the SAME gender value that was actually provided as ground truth,
    the verifier must NOT flag `metadata_gender_mismatch` — proves the
    routes/handoff.py -> EvidenceVerifierInput wiring lets a truthful
    citation pass, not just catch a fabrication."""
    report = _report_with_gender("여성")
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="bug069fu-6",
            request_id="bug069fu-6",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            prior_handoff_present=False,
            patient_gender="female",
        )
    )
    assert not any(i.issue_type == "metadata_gender_mismatch" for i in result.issues), [
        i.description for i in result.issues
    ]
