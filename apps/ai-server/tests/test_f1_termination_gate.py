"""Mandatory SI probe gate: sessions may not end handoff-ready while
risk_assessment is un-grounded (T1-F1-DEV-018/022).
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

# One utterance covering all 7 non-risk questionable topics, so the extractor
# can legitimately (verbatim) fill everything except risk_assessment.
_U_FULL = (
    "석 달 전부터 잠을 못 자요. 불면이 제일 힘들어요. 정신과 진료는 처음이에요. "
    "당뇨 약을 먹고 있어요. 혼자 살아요. 가족 중에 우울증을 앓은 사람은 없어요. "
    "술은 주말에 한두 잔 마셔요."
)

# Verbatim-quoted extractor output (passes the grounding filter) + a fabricated
# risk denial (must be rejected — risk comes only from the probe).
_EXTRACTED = {
    "chief_complaint": "잠을 못 자요. 불면이 제일 힘들어요",
    "history_of_present_illness": "석 달 전부터 잠을 못 자요",
    "past_psychiatric_history": "정신과 진료는 처음",
    "medical_history": "당뇨 약을 먹고 있어요",
    "personal_social_history": "혼자 살아요",
    "family_history": "가족 중에 우울증을 앓은 사람은 없어요",
    "substance_use_history": "술은 주말에 한두 잔 마셔요",
    "risk_assessment": "자살/자해 사고 명시적 부인",
}

_U_SI_DENIAL = "아니요, 그런 생각은 전혀 없어요."


@pytest.mark.asyncio
async def test_session_cannot_end_until_risk_grounded():
    """All 7 other slots grounded at turn 0 → forced SI screen → grounded risk
    from the actual denial → session ends only after that (and turn >= 3)."""
    slots = StubSlotAgent(lambda inp, n: dict(_EXTRACTED) if n == 1 else {})
    dialogue = StubDialogueAgent()
    pipeline = make_pipeline(StubSafetyAgent(), dialogue, slots)

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_FULL, _U_SI_DENIAL, "네, 감사합니다."]),
        session_id="t",
        max_turns=8,
    )

    # fabricated risk denial from the extractor was discarded at turn 0
    assert "risk_assessment" in result.turns[0].slot_discards

    # the mandatory SI screen was forced via the probe injection mechanism
    screen_events = [e for e in result.probe_events if e["type"] == "si_screen"]
    assert screen_events and screen_events[0]["forced"] is True
    assert dialogue.probe_instructions[0] is not None  # turn 1 = SI screen turn
    assert any(e["type"] == "si_screen_result" for e in result.probe_events)

    # risk_assessment composed from the patient's ACTUAL answer
    slot_map = {s["key"]: s["value"] for s in result.final_slots}
    assert "부인" in slot_map["risk_assessment"]
    assert _U_SI_DENIAL[:10] in slot_map["risk_assessment"]
    assert slot_map["risk_assessment"] != "자살/자해 사고 명시적 부인"

    # ended handoff-ready only after risk was grounded (and not before turn 3)
    assert result.crisis_triggered is False
    assert result.total_turns == 3
    assert result.grounded_coverage == 1.0


@pytest.mark.asyncio
async def test_fabricated_fills_do_not_trigger_early_termination():
    """The 07-03 failure mode: extractor fabricates everything at turn 0.
    With the filter, nothing merges → no early handoff-ready termination."""
    fabricated = {
        "chief_complaint": "잠을 못 자고, 불안감이 심하다",
        "history_of_present_illness": "3개월 전부터 불면과 불안 시작. 직장 스트레스가 계기.",
        "past_psychiatric_history": "정신과 진료 경험 없음",
        "medical_history": "진단받은 신체 질환 없음, 복용 약 없음",
        "personal_social_history": "어머니와 주 2회 통화",
        "family_history": "모름",
        "substance_use_history": "주 1-2회 맥주 1캔, 수면제 미사용",
        "risk_assessment": "자살/자해 사고 명시적 부인",
        "mental_status_exam": "말투 차분, 피로감 관찰됨",
    }
    slots = StubSlotAgent(lambda inp, n: dict(fabricated))
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), slots)

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(
            ["그냥 너무 힘들어요."], filler="그냥 좀 그래요."
        ),
        session_id="t",
        max_turns=2,
    )

    # nothing fabricated survived the filter
    assert result.final_slots == []
    assert result.grounded_coverage == 0.0
    # session ran to max_turns — it did NOT end "handoff ready" at turn 0/1
    assert result.total_turns == 2
    # every extraction turn recorded the discards for audit
    for turn_log in result.turns:
        assert turn_log.slot_discards
        assert "risk_assessment" in turn_log.slot_discards


@pytest.mark.asyncio
async def test_carried_prior_risk_slot_still_requires_fresh_screen():
    """A revisit session with a carried risk_assessment must re-screen: the
    carried value alone does not satisfy the termination gate."""
    slots = StubSlotAgent(lambda inp, n: dict(_EXTRACTED) if n == 1 else {})
    prior = {"risk_assessment": "이전 세션: 자살 사고 부인"}
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), slots)

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_FULL, _U_SI_DENIAL, "네."]),
        session_id="t",
        max_turns=8,
        prior_slots=prior,
    )

    # a fresh SI screen happened despite the carried value
    assert any(e["type"] == "si_screen" for e in result.probe_events)
    slot_map = {s["key"]: s["value"] for s in result.final_slots}
    # and the final value was re-composed from THIS session's exchange
    assert _U_SI_DENIAL[:10] in slot_map["risk_assessment"]
