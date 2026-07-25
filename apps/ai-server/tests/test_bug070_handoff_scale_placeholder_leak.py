"""BUG-070 regression — section 6 (구조화 척도 결과) template placeholder
leak, and the paired generator/route-level convergence fix.

BUG-070 is the same defect class BUG-069 closed for sections 1/2, now
observed in section 6: `ScaleScore` (`src/schemas/handoff.py`) carries only
`scale_name`/`total_score`/`severity` — no administration timestamp, no
per-item positive-symptom list — yet the template's "시행 일시"/"주요 양성
문항" columns show literal `<...>` placeholder tokens. Live evidence
(`experiments/EXP-031/logs_bug069/resp_session1_*.json`/`resp_session2_*.
json`) shows the generator echoing `` `<시행 일시>` ``/`` `<주요 양성
문항>` `` verbatim into the final report, and `ai_server_stdout.log` shows
`EvidenceVerifierAgent`'s EXISTING `<...>`-leak check
(`_check_metadata_grounding`'s `metadata_template_artifact`, added by the
v4.3/BUG-069 fix, and NOT scoped to sections 1/2 — it scans the whole
report) correctly firing `regenerate` on every one of 3 attempts, but the
generator never converging within the budget (fail-open exhaustion, not a
missed detection).

Three things are asserted here:
1. The verifier's pre-existing generic `<...>` check catches a §6 leak
   exactly as it does a §1/§2 leak (no verifier code change was needed for
   detection — this locks that in as a regression guard).
2. `_build_user_content` (the paired generator-side fix) now emits explicit,
   literal "미수집" grounding text for each administered scale's 시행
   일시/주요 양성 문항 sub-fields — the same "give the model real text to
   copy instead of blank space to invent from" strategy v4.3 used for
   gender/age/timestamps.
3. A route-level convergence check: when the generator (stubbed, since this
   suite runs fully offline with empty-string LLM keys) actually follows the
   v4.4 discipline and renders a compliant §6 (no `<...>` leak, "미수집" in
   the ungrounded sub-fields), the `/ai/handoff/generate` pipeline passes
   verification on the FIRST attempt — no regenerate loop consumed, no
   fail-open `requires_human_review` warning shipped. This is the
   contractual guarantee the BUG-070 fix restores: IF the generator honors
   the grounded text `_build_user_content` now supplies, THEN the pipeline
   converges instead of exhausting its regenerate budget.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
)
from src.agents.handoff_generator import _build_user_content
from src.schemas.common import EvidencePacket, EvidenceSource
from src.schemas.handoff import HandoffInput, HandoffOutput, ScaleScore


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


def _base_report(section6: str) -> str:
    """A minimal 12-section report shell (mirrors
    `test_evidence_verifier_bug069_metadata_grounding.py`'s own helper),
    with section 6 swappable per fixture and sections 1/2/9 already
    v4.3-compliant (fully grounded) so this suite isolates the §6 signal."""
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


_SEC6_LEAKED = (
    "| 척도명 | 총점 | Severity | 시행 일시 | 주요 양성 문항 |\n"
    "|---|---|---|---|---|\n"
    "| PHQ-9 | 10 `[ev_scale_001]` | moderate | `<시행 일시>` | `<주요 양성 문항>` |\n"
)

_SEC6_GROUNDED = (
    "| 척도명 | 총점 | Severity | 시행 일시 | 주요 양성 문항 |\n"
    "|---|---|---|---|---|\n"
    "| PHQ-9 | 10 `[ev_scale_001]` | moderate | 미수집 | 미수집 |\n"
)


@pytest.mark.asyncio
async def test_section6_template_placeholder_leak_forces_regenerate() -> None:
    """BUG-070 repro: §6 echoes the prompt template's own literal
    `<시행 일시>`/`<주요 양성 문항>` placeholder tokens — the verifier's
    pre-existing (BUG-069/v4.3) `<...>`-leak check must catch this exactly
    as it catches a §1/§2 leak, since that check scans the whole report
    body, not just sections 1/2."""
    report = _base_report(_SEC6_LEAKED)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="bug070-s1",
            request_id="bug070-r1",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            has_scale_scores=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.regenerate
    assert any(i.issue_type == "metadata_template_artifact" for i in result.issues)


@pytest.mark.asyncio
async def test_section6_grounded_missing_data_passes() -> None:
    """Negative control: §6 correctly renders "미수집" (no `<...>` leak) for
    the structurally-absent 시행 일시/주요 양성 문항 sub-fields — must NOT
    trigger regenerate. Proves the check doesn't over-fire on compliant
    "미수집" output (false-positive guard)."""
    report = _base_report(_SEC6_GROUNDED)
    verifier = EvidenceVerifierAgent()
    result = await verifier.run(
        EvidenceVerifierInput(
            session_id="bug070-s2",
            request_id="bug070-r2",
            report_markdown=report,
            evidence_packets=_packets(),
            is_first_visit=True,
            has_scale_scores=True,
            prior_handoff_present=False,
        )
    )
    assert result.action == VerifierAction.passed, [i.description for i in result.issues]


def test_build_user_content_grounds_scale_administration_subfields() -> None:
    """`_build_user_content` (paired generator-side fix) must emit explicit,
    literal "미수집" text for each administered scale's 시행 일시/주요 양성
    문항 sub-fields — giving the model real grounded text to copy instead
    of the blank space it previously filled by echoing the template's own
    `<...>` placeholder tokens (BUG-070 root cause)."""
    inp = HandoffInput(
        session_id="bug070-build",
        scale_scores=[
            ScaleScore(scale_name="PHQ-9", total_score=10, severity="moderate"),
            ScaleScore(scale_name="GAD-7", total_score=7, severity="mild"),
        ],
    )
    content = _build_user_content(inp)
    assert "시행 일시: 미수집" in content
    assert "주요 양성 문항: 미수집" in content
    # Each administered scale gets its own grounding lines, not one shared note.
    assert content.count("시행 일시: 미수집") == 2
    assert content.count("주요 양성 문항: 미수집") == 2


def test_build_user_content_no_scale_grounding_when_no_scales_administered() -> None:
    """No scale-score block (and therefore no 시행 일시/주요 양성 문항
    grounding lines) is emitted when no scales were administered — the
    grounding note only applies conditionally, mirroring the existing
    `if inp.scale_scores:` guard."""
    inp = HandoffInput(session_id="bug070-build-empty", scale_scores=[])
    content = _build_user_content(inp)
    assert "문진 점수" not in content
    assert "시행 일시" not in content


# ── Route-level convergence check ───────────────────────────────────────


class _CompliantStubHandoffGeneratorAgent:
    """Stub generator returning a v4.4-compliant report (§6 grounded, no
    `<...>` leak) on every call — simulates what the fixed prompt discipline
    is expected to produce, without depending on a live LLM (this suite runs
    fully offline). Used to lock in the CONVERGENCE contract: an actually-
    compliant generator output must pass verification on the first attempt,
    not merely be caught-and-regenerated."""

    call_count = 0

    async def run(self, inp: HandoffInput, **kwargs: object) -> HandoffOutput:
        type(self).call_count += 1
        return HandoffOutput(
            session_id=inp.session_id,
            request_id=inp.request_id,
            model_used="stub",
            prompt_version="v4.4-stub",
            report_markdown=_base_report(_SEC6_GROUNDED),
            evidence_packets=_packets(),
        )


@pytest.fixture
def _reset_stub_call_count():
    _CompliantStubHandoffGeneratorAgent.call_count = 0
    yield
    _CompliantStubHandoffGeneratorAgent.call_count = 0


def test_compliant_section6_converges_on_first_attempt(_reset_stub_call_count) -> None:
    """BUG-070 convergence guarantee: IF the generator honors the grounded
    "미수집" text `_build_user_content` now supplies for §6's structurally-
    absent sub-fields, THEN the `/ai/handoff/generate` pipeline passes
    verification on attempt 1 — no regenerate loop consumed, no fail-open
    `requires_human_review` warning shipped. This is the exact opposite of
    the BUG-070 live repro (3/3 attempts exhausted, `ai_server_stdout.log`)."""
    from src.main import app
    from src.routes import handoff as handoff_route

    app.dependency_overrides[handoff_route._get_handoff_agent] = (
        lambda: _CompliantStubHandoffGeneratorAgent()
    )
    try:
        client = TestClient(app)
        resp = client.post(
            "/ai/handoff/generate",
            json={
                "session_id": "bug070-route-1",
                "scale_scores": [
                    {"scale_name": "PHQ-9", "total_score": 10, "severity": "moderate"}
                ],
                "is_first_visit": True,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["requires_human_review"] is False
        assert "<" not in body["report_markdown"].split("섹션 6")[1].split("섹션 7")[0]
        assert _CompliantStubHandoffGeneratorAgent.call_count == 1, (
            "compliant §6 output should pass verification on the FIRST "
            "attempt — a call_count > 1 means the pipeline regenerated "
            "unnecessarily against a report that was already clean"
        )
    finally:
        app.dependency_overrides.pop(handoff_route._get_handoff_agent, None)
