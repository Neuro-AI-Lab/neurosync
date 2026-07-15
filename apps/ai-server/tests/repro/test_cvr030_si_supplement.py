"""CVR-030 remediation regression tests — standalone item-9-equivalent SI
check for a crisis_triggered session administering a REAL non-PHQ-9 F2
recommendation (e.g. AUDIT-C).

`src.f3.resolve_effective_scale`'s safety-net rule only fires when F2
yielded NO recommendation at all (CVR-028 Finding 1). A crisis_triggered
session where F2 DID recommend a real, non-PHQ-9 scale would otherwise
get ZERO SI-specific screening that session — the gap this remediation
closes via `resolve_si_supplement_needed`/`administer_si_supplement`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.f3 as f3
from src.scoring.item_bank import ScaleItem
from src.scoring.survey_scorer import is_phq9_item9_positive


def _artifact(
    *,
    recommended_questionnaire: str | None = "AUDIT-C",
    crisis_triggered: bool = False,
    session_ctrs: int | None = None,
    persona_id: str = "VP-TEST",
    session_id: str = "s1",
) -> dict:
    return {
        "session_id": session_id,
        "persona_id": persona_id,
        "ai_predicted_disease": {
            "candidates": [{"disease": "알코올 사용장애", "similarity_score": 0.7}],
            "mode": "rag_live",
            "is_diagnostic": False,
            "recommended_questionnaire": recommended_questionnaire,
            "recommendation_caveat": None,
        },
        "crisis_triggered": crisis_triggered,
        "session_ctrs": session_ctrs,
    }


def _write_artifact(tmp_path: Path, artifact: dict, name: str = "art.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    return path


def _fixed_answer_fn(values: list[int]):
    it = iter(values)

    async def _fn(item: ScaleItem) -> int:
        return next(it)

    return _fn


_AUDIT_C_ZEROS = [0, 0, 0]


class TestResolveSiSupplementNeeded:
    """Mutation-checked: every branch of the AND flips the outcome."""

    def test_crisis_natural_non_phq9_needs_supplement(self) -> None:
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True)
        )
        assert f3.resolve_si_supplement_needed(rec, "AUDIT-C", "natural") is True

    def test_not_crisis_triggered_no_supplement(self) -> None:
        """Flips crisis_triggered False -> must NOT need supplement."""
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=False)
        )
        assert f3.resolve_si_supplement_needed(rec, "AUDIT-C", "natural") is False

    def test_safety_net_mode_no_supplement(self) -> None:
        """administration_mode='safety_net' means the scale IS already
        PHQ-9 (item 9 already covered) — must NOT need supplement."""
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=True)
        )
        assert f3.resolve_si_supplement_needed(rec, "PHQ-9", "safety_net") is False

    def test_forced_mode_no_supplement(self) -> None:
        """A harness-only --force-questionnaire override is out of scope
        for a production safety rule."""
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True)
        )
        assert f3.resolve_si_supplement_needed(rec, "GAD-7", "forced") is False

    def test_natural_phq9_no_supplement(self) -> None:
        """F2 naturally recommended PHQ-9 itself — item 9 already covered."""
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire="PHQ-9", crisis_triggered=True)
        )
        assert f3.resolve_si_supplement_needed(rec, "PHQ-9", "natural") is False

    def test_effective_scale_none_no_supplement(self) -> None:
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=True)
        )
        assert f3.resolve_si_supplement_needed(rec, None, "natural") is False


class TestAdministerSiSupplement:
    @pytest.mark.asyncio
    async def test_reuses_phq9_item_9_verbatim(self) -> None:
        from src.scoring.item_bank import ITEM_BANK

        captured: list[ScaleItem] = []

        async def _fn(item: ScaleItem) -> int:
            captured.append(item)
            return 2

        response, positive = await f3.administer_si_supplement(_fn)
        assert response == 2
        assert positive is True
        assert len(captured) == 1
        assert captured[0].index == 9
        assert captured[0] is ITEM_BANK["PHQ-9"].items[8]

    @pytest.mark.asyncio
    async def test_negative_response_not_critical(self) -> None:
        response, positive = await f3.administer_si_supplement(_fixed_answer_fn([0]))
        assert response == 0
        assert positive is False

    @pytest.mark.asyncio
    async def test_positivity_matches_shared_threshold_rule(self) -> None:
        """Same rule `_score_phq9` itself uses — single source of truth."""
        for value in range(0, 4):
            _resp, positive = await f3.administer_si_supplement(_fixed_answer_fn([value]))
            assert positive == is_phq9_item9_positive(value)


class TestRunF3AdministrationSiSupplement:
    @pytest.mark.asyncio
    async def test_crisis_natural_audit_c_administers_supplement(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn(_AUDIT_C_ZEROS),
            output_dir=tmp_path,
            vp_id="VP-TEST",
            si_supplement_answer_fn=_fixed_answer_fn([1]),
        )
        assert result["output"].scale_name == "AUDIT-C"
        si = result["si_supplement"]
        assert si["needed"] is True
        assert si["administered"] is True
        si_output = si["output"]
        assert si_output.scale_name == "PHQ-9"
        assert si_output.administration_mode == "si_supplement"
        assert si_output.responses == [1]
        assert si_output.safety_referral is True
        assert si_output.score_result is None
        assert si["paths"]["json"].exists()
        assert si["paths"]["json"].name.endswith("_si_supplement.json")
        assert si["paths"]["report"].exists()

    @pytest.mark.asyncio
    async def test_own_record_never_merged_into_main_survey_artifact(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn(_AUDIT_C_ZEROS),
            output_dir=tmp_path,
            vp_id="VP-TEST",
            si_supplement_answer_fn=_fixed_answer_fn([0]),
        )
        main = result["output"]
        assert main.scale_name == "AUDIT-C"
        assert main.responses == _AUDIT_C_ZEROS
        assert main.administration_mode == "natural"
        saved = json.loads(result["paths"]["json"].read_text(encoding="utf-8"))
        assert saved["scale_name"] == "AUDIT-C"

    @pytest.mark.asyncio
    async def test_no_supplement_answer_fn_skips_but_never_crashes(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn(_AUDIT_C_ZEROS),
            output_dir=tmp_path,
            vp_id="VP-TEST",
            # si_supplement_answer_fn intentionally omitted
        )
        si = result["si_supplement"]
        assert si["needed"] is True
        assert si["administered"] is False
        assert si["output"] is None
        assert si["paths"] is None

    @pytest.mark.asyncio
    async def test_not_crisis_triggered_never_administers_supplement(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=False),
        )

        async def _should_not_be_called(item: ScaleItem) -> int:
            raise AssertionError("si_supplement_answer_fn must not be called")

        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn(_AUDIT_C_ZEROS),
            output_dir=tmp_path,
            vp_id="VP-TEST",
            si_supplement_answer_fn=_should_not_be_called,
        )
        si = result["si_supplement"]
        assert si["needed"] is False
        assert si["administered"] is False

    @pytest.mark.asyncio
    async def test_crisis_safety_net_phq9_never_administers_supplement(
        self, tmp_path: Path
    ) -> None:
        """F2 gave NO recommendation -> safety-net PHQ-9 already covers
        item 9 -> supplement must not additionally fire."""
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire=None, crisis_triggered=True),
        )

        async def _should_not_be_called(item: ScaleItem) -> int:
            raise AssertionError("si_supplement_answer_fn must not be called")

        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([0] * 9),
            output_dir=tmp_path,
            vp_id="VP-TEST",
            si_supplement_answer_fn=_should_not_be_called,
        )
        assert result["output"].scale_name == "PHQ-9"
        assert result["output"].administration_mode == "safety_net"
        si = result["si_supplement"]
        assert si["needed"] is False
        assert si["administered"] is False


class TestResolveAdministrationMode:
    def test_forced_wins(self) -> None:
        assert f3.resolve_administration_mode("GAD-7", True) == "forced"

    def test_safety_net_when_triggered_and_not_forced(self) -> None:
        assert f3.resolve_administration_mode(None, True) == "safety_net"

    def test_natural_otherwise(self) -> None:
        assert f3.resolve_administration_mode(None, False) == "natural"


class TestSiSupplementSafetyPathwayRouting:
    """`src.continuous_test._route_si_supplement_safety_pathway`."""

    def test_positive_response_triggers_safety_pathway(self) -> None:
        from src.continuous_test import _route_si_supplement_safety_pathway

        result = _route_si_supplement_safety_pathway("VP-TEST", 2)
        assert result["safety_triggered"] is True
        assert result["critical_item_positive"] is True
        assert result["recommended_action"] == "safety_referral"

    def test_negative_response_does_not_trigger(self) -> None:
        from src.continuous_test import _route_si_supplement_safety_pathway

        result = _route_si_supplement_safety_pathway("VP-TEST", 0)
        assert result["safety_triggered"] is False
        assert result["critical_item_positive"] is False
        assert result["recommended_action"] == "none"

    def test_agrees_with_full_phq9_administration_on_same_value(self) -> None:
        """The supplement's routing outcome must never disagree with what a
        full PHQ-9 administration would conclude for the same item-9
        value (CVR-030's own single-source-of-truth requirement)."""
        from src.continuous_test import _route_si_supplement_safety_pathway
        from src.scoring.survey_scorer import score_survey

        for value in range(0, 4):
            responses = [0] * 8 + [value]
            full_result = score_survey("PHQ-9", responses)
            supp_result = _route_si_supplement_safety_pathway("VP-TEST", value)
            assert supp_result["critical_item_positive"] == full_result.critical_item_positive
            assert (supp_result["recommended_action"] == "safety_referral") == (
                full_result.recommended_action == "safety_referral"
            )
