"""CVR-031 remediation: `contracts.survey_plan` schema-level contract tests.

Covers the 2 major + 3 minor findings that are contract-shape concerns
(route-level behavior for the same findings is covered separately in
`tests/test_deployment_stateless_routes.py::TestSurveyPlanRoute`):

- Finding 1: `ItemBankItemPlan.is_si_item` + `SurveyPlanResponse.
  si_positive_action_ko`/`si_positive_threshold` exist and hold their
  documented defaults.
- Finding 2: `SurveyPlanRequest.from_orchestrator_turn` maps
  `crisis_triggered`/`safety_status.ctrs_level` correctly, including the
  safety-first missing-data rule.
"""

from __future__ import annotations

from enum import IntEnum

import pytest
from contracts.survey_plan import (
    REFUSAL_GUIDANCE_KO,
    SI_POSITIVE_ACTION_KO,
    ItemBankItemPlan,
    SurveyPlanRequest,
    SurveyPlanResponse,
)


class _CTRSLevel(IntEnum):
    """Stand-in for `src.schemas.common.CTRSLevel` — deliberately a
    SEPARATE IntEnum (not imported from ai-server) to prove the adapter is
    duck-typed, not coupled to that specific enum class."""

    EMERGENCY = 1
    HIGH_RISK = 2
    ACUTE = 3
    MODERATE = 4
    STABLE = 5


class _SafetyStatus:
    """Stand-in for `src.schemas.orchestrator.SafetyStatus` — a plain
    object with a `.ctrs_level` attribute, no ai-server import."""

    def __init__(self, ctrs_level: IntEnum) -> None:
        self.ctrs_level = ctrs_level


class TestItemBankItemPlanIsSiItem:
    def test_default_false(self):
        item = ItemBankItemPlan(index=1, text_ko="x", response_min=0, response_max=3)
        assert item.is_si_item is False

    def test_explicit_true(self):
        item = ItemBankItemPlan(
            index=9, text_ko="si item", response_min=0, response_max=3, is_si_item=True
        )
        assert item.is_si_item is True


class TestSurveyPlanResponseSiActionability:
    def test_si_positive_threshold_matches_phq9_item9_rule(self):
        """Mirrors src.scoring.survey_scorer.is_phq9_item9_positive (>= 1)."""
        resp = SurveyPlanResponse()
        assert resp.si_positive_threshold == 1

    def test_si_positive_action_ko_reuses_crisis_hotline_text(self):
        resp = SurveyPlanResponse(si_positive_action_ko=SI_POSITIVE_ACTION_KO)
        assert "109" in resp.si_positive_action_ko
        assert "119" in resp.si_positive_action_ko

    def test_default_none_when_no_si_item(self):
        resp = SurveyPlanResponse()
        assert resp.si_positive_action_ko is None

    def test_refusal_guidance_constant_present(self):
        assert "강요" in REFUSAL_GUIDANCE_KO


class TestFromOrchestratorTurn:
    def test_maps_ctrs_enum_to_int(self):
        req = SurveyPlanRequest.from_orchestrator_turn(
            crisis_triggered=False,
            safety_status=_SafetyStatus(_CTRSLevel.HIGH_RISK),
        )
        assert req.session_ctrs == 2
        assert isinstance(req.session_ctrs, int)
        assert not isinstance(req.session_ctrs, IntEnum)

    def test_maps_ctrs_dict_shape(self):
        req = SurveyPlanRequest.from_orchestrator_turn(
            crisis_triggered=False,
            safety_status={"ctrs_level": _CTRSLevel.ACUTE},
        )
        assert req.session_ctrs == 3

    def test_crisis_triggered_passthrough_true(self):
        req = SurveyPlanRequest.from_orchestrator_turn(
            crisis_triggered=True,
            safety_status=_SafetyStatus(_CTRSLevel.STABLE),
        )
        assert req.crisis_triggered is True
        assert req.session_ctrs == 5

    def test_missing_safety_status_does_not_disable_crisis_triggered(self):
        """Safety-first rule: absent safety_status must NOT silently
        disable the safety net — crisis_triggered=True stays True even
        with zero CTRS information; session_ctrs alone falls back to
        None, which resolve_effective_scale treats as "no CTRS data",
        not as "not high-acuity" (crisis_triggered=True already covers
        that branch on its own)."""
        req = SurveyPlanRequest.from_orchestrator_turn(
            crisis_triggered=True,
            safety_status=None,
        )
        assert req.crisis_triggered is True
        assert req.session_ctrs is None

    def test_safety_status_present_but_no_ctrs_level_attr(self):
        req = SurveyPlanRequest.from_orchestrator_turn(
            crisis_triggered=True,
            safety_status=object(),
        )
        assert req.crisis_triggered is True
        assert req.session_ctrs is None

    def test_passthrough_f2_fields(self):
        req = SurveyPlanRequest.from_orchestrator_turn(
            crisis_triggered=False,
            safety_status=_SafetyStatus(_CTRSLevel.STABLE),
            recommended_questionnaire="PHQ-9",
            recommendation_caveat="mania blind spot",
            top_candidate_disease="depression",
            top_candidate_similarity_score=0.9,
            administered_scale="GAD-7",
        )
        assert req.recommended_questionnaire == "PHQ-9"
        assert req.recommendation_caveat == "mania blind spot"
        assert req.top_candidate_disease == "depression"
        assert req.top_candidate_similarity_score == pytest.approx(0.9)
        assert req.administered_scale == "GAD-7"

    def test_returns_valid_survey_plan_request(self):
        req = SurveyPlanRequest.from_orchestrator_turn(crisis_triggered=False)
        assert isinstance(req, SurveyPlanRequest)
