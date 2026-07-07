"""ISS-036 partial fix: handoff session CTRS = min over ALL turns incl. turn 0.

Previously turn 0 was excluded and the value fell back to 5, so a turn-0
crisis session was recorded as stable in the handoff report.
"""

from __future__ import annotations

from datetime import datetime

from src.f1 import F1Result, F1TurnLog, generate_handoff_from_result


def _turn(turn: int, ctrs: int, crisis: bool = False) -> F1TurnLog:
    return F1TurnLog(
        turn=turn,
        patient_message=f"msg {turn}",
        safety_ctrs=ctrs,
        safety_risk="high" if ctrs <= 2 else "none",
        safety_crisis=crisis,
        safety_categories=[],
        safety_flagged=[],
        agent_response=f"resp {turn}",
        slot_updates={},
        cumulative_slots={},
        slot_coverage=0.0,
        latency_ms=0.0,
        timestamp=datetime.now().isoformat(),
    )


def test_turn0_crisis_session_not_recorded_as_stable():
    result = F1Result(
        session_id="t", persona_id="VP-X", persona_name="X",
        crisis_triggered=True, crisis_turn=0, total_turns=0,
        turns=[_turn(0, 2, crisis=True)],
        started_at=datetime.now().isoformat(),
    )
    handoff = generate_handoff_from_result(result)
    assert "CTRS: 2단계" in handoff
    assert "CTRS: 5단계" not in handoff


def test_session_ctrs_is_min_over_all_turns_including_turn0():
    result = F1Result(
        session_id="t", persona_id="VP-X", persona_name="X",
        total_turns=2,
        turns=[_turn(0, 3), _turn(1, 5), _turn(2, 4)],
        started_at=datetime.now().isoformat(),
    )
    handoff = generate_handoff_from_result(result)
    assert "CTRS: 3단계" in handoff


def test_no_turns_reports_na():
    result = F1Result(
        session_id="t", persona_id="VP-X", persona_name="X",
        started_at=datetime.now().isoformat(),
    )
    handoff = generate_handoff_from_result(result)
    assert "CTRS: N/A" in handoff


def test_ungrounded_risk_slot_reports_not_assessed():
    """Without a grounded risk value the handoff must say the assessment was
    not performed — never the old fabricated-looking '확인 안 됨' claim."""
    result = F1Result(
        session_id="t", persona_id="VP-X", persona_name="X",
        total_turns=1,
        turns=[_turn(0, 5), _turn(1, 5)],
        started_at=datetime.now().isoformat(),
    )
    handoff = generate_handoff_from_result(result)
    assert "위험 평가 미수행" in handoff
