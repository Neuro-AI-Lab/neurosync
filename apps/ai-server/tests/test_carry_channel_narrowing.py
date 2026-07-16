"""AVC-02 support test (`_archive/plans/validation_plan_f1f2_continuous.md` §6,
qa detection procedure #5): "the carry channel contains only
final_slots/missing_slots-shaped content, never raw risk_assessment prose."

Covers `src.f1._compose_carry_content` (PLAN-2026-W28-Q W2) — the function
that replaced the old `generate_handoff_from_result()`-based full-prose
`--followup-from` payload (which used to inject raw CTRS/crisis-protocol
narrative and the risk_assessment slot's own prose value into both the
patient-simulator prompt and the dialogue history).
"""

from __future__ import annotations

from src.f1 import F1Result, F1TurnLog, _compose_carry_content, generate_handoff_from_result
from src.grounding import QUESTIONABLE_SLOT_KEYS, RISK_SLOT_KEY

_FINAL_SLOTS_WITH_RISK = {
    "chief_complaint": "불면과 우울감",
    "history_of_present_illness": "석 달 전부터 잠을 못 잠",
    "risk_assessment": "자살/자해 사고 표현 있음 — 환자 발화: \"죽고 싶어요\"",
}
_MISSING = ["family_history", "substance_use_history"]


class TestComposedCarryContentShape:
    def test_final_slots_render_as_flat_key_value_lines(self) -> None:
        content = _compose_carry_content(_FINAL_SLOTS_WITH_RISK, _MISSING)
        assert "- chief_complaint: 불면과 우울감" in content
        assert "- history_of_present_illness: 석 달 전부터 잠을 못 잠" in content

    def test_missing_slots_listed(self) -> None:
        content = _compose_carry_content(_FINAL_SLOTS_WITH_RISK, _MISSING)
        assert "family_history" in content
        assert "substance_use_history" in content

    def test_risk_assessment_key_and_value_never_cross(self) -> None:
        """The zero-tolerance AVC-02 assertion: risk_assessment's raw prose
        value (SI-probe exchange narrative) must never appear, and the key
        itself is dropped rather than rendered empty."""
        content = _compose_carry_content(_FINAL_SLOTS_WITH_RISK, _MISSING)
        assert "죽고 싶어요" not in content
        assert "자살" not in content
        assert "자해" not in content
        assert f"- {RISK_SLOT_KEY}:" not in content

    def test_no_ctrs_or_crisis_protocol_narrative(self) -> None:
        """The old full-prose Handoff Report's dedicated risk/crisis
        sections ("[2. 위기 분류 (Crisis Triage)]", CTRS level narrative)
        must never appear — only the flat final_slots+missing_slots shape."""
        content = _compose_carry_content(_FINAL_SLOTS_WITH_RISK, _MISSING)
        assert "위기 분류" not in content
        assert "CTRS" not in content
        assert "위기 프로토콜" not in content

    def test_empty_final_slots_and_missing_produce_placeholder_text(self) -> None:
        content = _compose_carry_content({}, [])
        assert "(수집된 정보 없음)" in content
        assert "(없음)" in content

    def test_content_is_a_strict_subset_of_final_slots_plus_missing_slots(self) -> None:
        """Every non-boilerplate slot-shaped line traces back to
        final_slots (minus risk_assessment) or missing_slots — nothing else
        is synthesized."""
        content = _compose_carry_content(_FINAL_SLOTS_WITH_RISK, _MISSING)
        licensed_keys = (set(_FINAL_SLOTS_WITH_RISK) - {RISK_SLOT_KEY}) | set(_MISSING)
        for line in content.split("\n"):
            if line.startswith("- ") and ":" in line:
                key = line[2:].split(":", 1)[0]
                assert key in licensed_keys, f"unexpected key crossed the carry channel: {key!r}"


class TestContrastAgainstOldFullProseChannel:
    """Confirms the OLD full-prose channel (`generate_handoff_from_result`)
    really did leak risk_assessment prose + CTRS narrative — the exact
    overreach `_compose_carry_content` was built to close."""

    def test_old_handoff_report_contained_risk_assessment_and_ctrs_prose(self) -> None:
        result = F1Result(
            session_id="t-avc02-contrast", persona_id="VP-X", persona_name="X",
            total_turns=1,
            crisis_triggered=False,
            final_slots=[
                {"key": k, "value": v} for k, v in _FINAL_SLOTS_WITH_RISK.items()
            ],
            turns=[
                F1TurnLog(
                    turn=0, patient_message="msg", safety_ctrs=3, safety_risk="medium",
                    safety_crisis=False, safety_categories=[], safety_flagged=[],
                    agent_response="resp", slot_updates={}, cumulative_slots={},
                    slot_coverage=0.0, latency_ms=0.0, timestamp="2026-01-01T00:00:00",
                )
            ],
            started_at="2026-01-01T00:00:00",
        )
        old_handoff = generate_handoff_from_result(result)
        # This is exactly what the old channel exposed — proves the
        # narrowing was solving a real, reproducible overreach, not a
        # hypothetical one.
        assert "죽고 싶어요" in old_handoff
        assert "CTRS" in old_handoff


def test_missing_slots_drawn_from_questionable_slot_keys_convention() -> None:
    """Sanity: the composer's `missing_slots` parameter is expected to be a
    subset of QUESTIONABLE_SLOT_KEYS (the caller's convention, `f1.py`
    `_run_simulation`) — key names only, never values."""
    missing = [k for k in QUESTIONABLE_SLOT_KEYS if k not in _FINAL_SLOTS_WITH_RISK]
    content = _compose_carry_content(_FINAL_SLOTS_WITH_RISK, missing)
    for key in missing:
        assert key in content
