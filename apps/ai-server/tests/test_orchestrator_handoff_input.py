"""Issue #20: orchestrator._build_handoff_input must carry scale_scores + risk_events.

The handoff report is what the psychiatrist reads. The orchestrator collected
PHQ-9/GAD-7 scores (state.scale_scores) and safety/CTRS events
(state.safety_status), but _build_handoff_input() never populated
HandoffInput.scale_scores / HandoffInput.risk_events — silently dropping
depression severity and suicide-risk indicators from the report input.
"""

from __future__ import annotations

from src.agents.orchestrator import OrchestratorAgent
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.orchestrator import SafetyStatus, SessionState


def test_build_handoff_input_carries_scale_scores_and_risk_events() -> None:
    agent = OrchestratorAgent.__new__(OrchestratorAgent)
    state = SessionState(session_id="s1")
    state.scale_scores = {
        "PHQ-9": {
            "total_score": 21,
            "severity": "severe",
            "critical_item_positive": True,
            "recommended_action": "safety_referral",
        },
        # meta key used by the trend plotter — must NOT become a ScaleScore
        "_prior": {"PHQ-9": 15, "date": "2026-06-01"},
    }
    state.safety_status = SafetyStatus(
        ctrs_level=CTRSLevel.HIGH_RISK,
        risk_level=RiskLevel.high,
        crisis_triggered=True,
    )
    state.slot_data = {"chief_complaint": "우울감"}

    hi = agent._build_handoff_input(state)

    scale_names = [s.scale_name for s in hi.scale_scores]
    assert "PHQ-9" in scale_names, f"PHQ-9 dropped from handoff input: {hi.scale_scores}"
    assert "_prior" not in scale_names, "meta key '_prior' must be skipped"
    phq = next(s for s in hi.scale_scores if s.scale_name == "PHQ-9")
    assert phq.total_score == 21
    assert phq.severity == "severe"

    assert len(hi.risk_events) >= 1, f"risk events dropped from handoff input: {hi.risk_events}"
    assert hi.risk_events[0].get("risk_level") == "high"


def test_build_handoff_input_no_events_when_safe_first_visit() -> None:
    """Regression: a safe session with no scores yields empty scale_scores/risk_events."""
    agent = OrchestratorAgent.__new__(OrchestratorAgent)
    state = SessionState(session_id="s2")  # default safety_status = none, no scores

    hi = agent._build_handoff_input(state)

    assert hi.scale_scores == []
    assert hi.risk_events == []
