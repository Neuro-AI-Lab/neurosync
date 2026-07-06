"""T1-F1-DEV-019: grounded coverage redefinition (8 questionable slots).

A 0-dialogue-turn (turn-0 crisis) session must report grounded_coverage
computed only from turn-0 grounded values — never the old fixed ~80% that
came from fabricated fills.
"""

from __future__ import annotations

import pytest

from tests.f1_testkit import (
    StubDialogueAgent,
    StubSafetyAgent,
    StubSlotAgent,
    make_patient_fn,
    make_pipeline,
)

# The real VP-003 07-03 case: suicidal first message + fully fabricated
# extractor payload (echoed v1 prompt examples).
_U_CRISIS = "살고 싶지 않아요. 그냥 사라지고 싶은 생각이 들어요."
_VP003_PAYLOAD = {
    "chief_complaint": "살고 싶지 않음, 사라지고 싶은 생각",
    "history_of_present_illness": "현재 극심한 정서적 고통으로 인해 살고 싶지 않은 생각이 듦",
    "past_psychiatric_history": "정신과 진료 경험 없음",
    "medical_history": "진단받은 신체 질환 없음, 복용 약 없음",
    "personal_social_history": "지지체계 정보 없음",
    "family_history": "가족 정신질환 이력 모름",
    "substance_use_history": "음주/물질 사용 정보 없음",
    "mental_status_exam": "말투: 절망적, 감정: 극심한 우울감, 사고과정: 자살 사고 표현",
    "risk_assessment": "자살/자해 사고 명시적 표현",
}


@pytest.mark.asyncio
async def test_turn0_crisis_grounded_coverage_is_low_not_80pct():
    safety = StubSafetyAgent({_U_CRISIS: (2, ["suicidal_ideation"])})
    slots = StubSlotAgent(lambda inp, n: dict(_VP003_PAYLOAD))
    pipeline = make_pipeline(safety, StubDialogueAgent(), slots)

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_CRISIS]),
        session_id="t",
        max_turns=5,
    )

    assert result.crisis_triggered is True
    assert result.crisis_turn == 0
    assert result.total_turns == 0

    # only the patient-quoted chief complaint survives the filter
    kept = {s["key"] for s in result.final_slots}
    assert kept == {"chief_complaint"}
    assert result.grounded_coverage == pytest.approx(1 / 8)
    assert result.grounded_coverage != pytest.approx(0.8)

    # the fabricated fills are recorded as discards on turn 0
    discards = result.turns[0].slot_discards
    assert "risk_assessment" in discards
    assert "past_psychiatric_history" in discards

    # ISS-036 partial fix: session CTRS includes turn 0 (was: fell back to 5)
    assert result.session_ctrs == 2


@pytest.mark.asyncio
async def test_both_coverage_metrics_reported():
    """Legacy essential coverage is kept alongside grounded coverage."""
    utterance = "석 달 전부터 잠을 못 자요. 회사 스트레스 때문인 것 같아요."
    slots = StubSlotAgent(lambda inp, n: {
        "chief_complaint": "잠을 못 자요",
        "history_of_present_illness": "석 달 전부터 잠을 못 자요. 회사 스트레스 때문",
    } if n == 1 else {})
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), slots)

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([utterance], filler="그냥 그래요."),
        session_id="t",
        max_turns=2,
    )

    # grounded: 2/8 questionable slots
    assert result.grounded_coverage == pytest.approx(2 / 8)
    # legacy: 2/5 essential (chief + HPI; risk/MSE/assessment unfilled)
    assert result.slot_coverage == pytest.approx(2 / 5)
    # per-turn logs carry both metrics
    assert result.turns[0].grounded_coverage == pytest.approx(2 / 8)
    assert result.turns[0].slot_coverage == pytest.approx(2 / 5)


@pytest.mark.asyncio
async def test_patient_start_failure_reports_zero_coverage():
    async def failing_patient(_msg: str) -> str:
        raise RuntimeError("patient unavailable")

    pipeline = make_pipeline()
    result = await pipeline.run_session(
        patient_input_fn=failing_patient, session_id="t", max_turns=3
    )
    assert result.errors
    assert result.grounded_coverage == 0.0
    assert result.session_ctrs == 5  # no turns → default stable
