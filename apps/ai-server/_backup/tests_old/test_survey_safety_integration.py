"""T1-F3-VER-004: PHQ-9 Q9 suicidal item → Safety referral integration.

Tests that PHQ-9 scoring with Q9 >= 1 triggers safety_referral action,
and that the orchestrator's survey planner + scoring correctly flags
the safety concern. No LLM calls.
"""

from __future__ import annotations

import pytest

from src.agents.orchestrator import OrchestratorAgent
from src.schemas.orchestrator import SessionState
from src.scoring.survey_scorer import score_survey


class TestPHQ9SuicidalItemSafety:
    """PHQ-9 Q9 >= 1 must trigger safety_referral."""

    def test_q9_zero_no_safety(self):
        """Q9=0 → no safety referral."""
        result = score_survey("PHQ-9", [1, 1, 1, 0, 0, 0, 0, 0, 0])
        assert result.critical_item_positive is False
        assert result.recommended_action != "safety_referral"

    def test_q9_one_triggers_safety(self):
        """Q9=1 (several days) → safety_referral."""
        result = score_survey("PHQ-9", [0, 0, 0, 0, 0, 0, 0, 0, 1])
        assert result.critical_item_positive is True
        assert result.recommended_action == "safety_referral"
        assert len(result.critical_items) == 1
        assert result.critical_items[0]["flag"] == "suicidal_ideation"

    def test_q9_two_triggers_safety(self):
        """Q9=2 (more than half the days) → safety_referral."""
        result = score_survey("PHQ-9", [2, 2, 2, 2, 2, 2, 2, 2, 2])
        assert result.critical_item_positive is True
        assert result.recommended_action == "safety_referral"

    def test_q9_three_triggers_safety(self):
        """Q9=3 (nearly every day) → safety_referral."""
        result = score_survey("PHQ-9", [3, 3, 3, 3, 3, 3, 3, 3, 3])
        assert result.critical_item_positive is True
        assert result.recommended_action == "safety_referral"

    def test_severe_without_q9_no_safety_referral(self):
        """Severe PHQ-9 (total=20+) but Q9=0 → clinician_review, NOT safety_referral."""
        result = score_survey("PHQ-9", [3, 3, 3, 3, 3, 3, 3, 2, 0])
        assert result.severity == "severe"
        assert result.critical_item_positive is False
        assert result.recommended_action == "clinician_review"

    def test_mild_with_q9_safety_overrides_watchful(self):
        """Mild PHQ-9 but Q9=1 → safety_referral overrides watchful_waiting."""
        result = score_survey("PHQ-9", [0, 0, 1, 0, 0, 0, 0, 0, 1])
        assert result.severity == "minimal"
        assert result.critical_item_positive is True
        assert result.recommended_action == "safety_referral"


class TestOrchestratorSurveyPlan:
    """Survey planner recommends appropriate scales."""

    def test_always_recommends_phq9(self):
        state = SessionState(session_id="s1", slot_data={"chief_complaint": "우울"})
        recommended = OrchestratorAgent.plan_surveys(state)
        assert "PHQ-9" in recommended

    def test_anxiety_triggers_gad7(self):
        state = SessionState(
            session_id="s1",
            slot_data={
                "chief_complaint": "불안",
                "symptoms": {"anxiety": "높음"},
            },
        )
        recommended = OrchestratorAgent.plan_surveys(state)
        assert "GAD-7" in recommended

    def test_no_anxiety_no_gad7(self):
        state = SessionState(
            session_id="s1",
            slot_data={"chief_complaint": "우울", "symptoms": {}},
        )
        recommended = OrchestratorAgent.plan_surveys(state)
        assert "GAD-7" not in recommended

    def test_alcohol_triggers_audit_c(self):
        state = SessionState(
            session_id="s1",
            slot_data={"substance_use": "술 자주 마심"},
        )
        recommended = OrchestratorAgent.plan_surveys(state)
        assert "AUDIT-C" in recommended

    def test_mood_concern_triggers_who5(self):
        state = SessionState(
            session_id="s1",
            slot_data={"symptoms": {"mood": "우울", "energy": "저하"}},
        )
        recommended = OrchestratorAgent.plan_surveys(state)
        assert "WHO-5" in recommended

    def test_already_scored_not_recommended(self):
        state = SessionState(
            session_id="s1",
            slot_data={"chief_complaint": "우울"},
            scale_scores={"PHQ-9": {"total_score": 5}},
        )
        recommended = OrchestratorAgent.plan_surveys(state)
        assert "PHQ-9" not in recommended

    def test_phq4_fallback_when_no_phq9_gad7(self):
        """PHQ-4 recommended when neither PHQ-9 nor GAD-7 are scored."""
        state = SessionState(session_id="s1", slot_data={})
        recommended = OrchestratorAgent.plan_surveys(state)
        assert "PHQ-4" in recommended


class TestOrchestratorScoreAndCheck:
    """Orchestrator scoring updates state and detects safety."""

    def test_safe_score_updates_state(self):
        state = SessionState(session_id="s1")
        result, safety = OrchestratorAgent.score_and_check_safety(
            state, "PHQ-9", [1, 1, 1, 0, 0, 0, 0, 0, 0]
        )
        assert safety is False
        assert "PHQ-9" in state.scale_scores
        assert state.scale_scores["PHQ-9"]["total_score"] == 3

    def test_q9_positive_triggers_safety_flag(self):
        state = SessionState(session_id="s1")
        result, safety = OrchestratorAgent.score_and_check_safety(
            state, "PHQ-9", [2, 2, 2, 2, 2, 2, 2, 2, 2]
        )
        assert safety is True
        assert state.scale_scores["PHQ-9"]["critical_item_positive"] is True
        assert state.scale_scores["PHQ-9"]["recommended_action"] == "safety_referral"

    def test_gad7_no_safety_trigger(self):
        """GAD-7 has no suicide item → never triggers safety."""
        state = SessionState(session_id="s1")
        result, safety = OrchestratorAgent.score_and_check_safety(
            state, "GAD-7", [3, 3, 3, 3, 3, 3, 3]
        )
        assert safety is False
        assert state.scale_scores["GAD-7"]["severity"] == "severe"
