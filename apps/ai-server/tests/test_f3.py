"""`src.f3` — F2-driven questionnaire administration (production engine).

`docs/ai/f3_quick_dev_plan.md`, ADR-031/ADR-032, T1-F3-VER-007..013. No live
LLM/DB anywhere in this file — `answer_fn` is always a plain local coroutine.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

import src.f2 as f2
import src.f3 as f3
from src.schemas.survey_result import RecommendationProvenance, SurveyResultOutput
from src.scoring.item_bank import ScaleItem


def _artifact(
    *,
    recommended_questionnaire: str | None = "PHQ-9",
    recommendation_caveat: str | None = None,
    candidates: list[dict] | None = None,
    persona_id: str | None = "VP-TEST",
    session_id: str = "s1",
    include_ai_predicted_disease: bool = True,
) -> dict:
    if candidates is None:
        candidates = [{"disease": "우울 삽화(우울증)", "similarity_score": 0.8}]
    data: dict = {"session_id": session_id, "persona_id": persona_id}
    if include_ai_predicted_disease:
        data["ai_predicted_disease"] = {
            "candidates": candidates,
            "mode": "rag_live",
            "is_diagnostic": False,
            "recommended_questionnaire": recommended_questionnaire,
            "recommendation_caveat": recommendation_caveat,
        }
    return data


def _write_artifact(tmp_path: Path, artifact: dict, name: str = "art.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    return path


def _fixed_answer_fn(values: list[int]):
    it = iter(values)

    async def _fn(item: ScaleItem) -> int:
        return next(it)

    return _fn


async def _never_called(item: ScaleItem) -> int:
    raise AssertionError("answer_fn must not be called")


# ── §3 F2 -> F3 trigger flow / resolve_outcome ──────────────────────────


class TestResolveOutcome:
    def test_none_recommendation_is_no_questionnaire_indicated(self) -> None:
        outcome, entry = f3.resolve_outcome(None)
        assert outcome == f3.NO_QUESTIONNAIRE_OUTCOME
        assert entry is None

    def test_populated_scale_is_administered(self) -> None:
        outcome, entry = f3.resolve_outcome("PHQ-9")
        assert outcome == f3.ADMINISTERED_OUTCOME
        assert entry is not None and entry.populated is True

    def test_unpopulated_scale_is_item_bank_unpopulated(self, caplog) -> None:
        # WHO-5 is item bank v1's only remaining unpopulated scale
        # (PLAN-2026-W29-A) — GAD-7/PHQ-4/AUDIT-C are populated now.
        with caplog.at_level(logging.WARNING):
            outcome, entry = f3.resolve_outcome("WHO-5")
        assert outcome == f3.UNPOPULATED_OUTCOME
        assert entry is not None and entry.populated is False
        assert any("SKIPPED-item-bank-unpopulated" in r.message for r in caplog.records)

    def test_unrecognized_scale_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            f3.resolve_outcome("NOT-A-SCALE")  # type: ignore[arg-type]


class TestResolveRecommendationFromArtifact_NoneHandling:
    """None-handling: an artifact missing `ai_predicted_disease` entirely
    (pre-Track-B shape) must degrade gracefully, never crash."""

    def test_missing_ai_predicted_disease_key_degrades_to_no_recommendation(self) -> None:
        artifact = _artifact(include_ai_predicted_disease=False)
        rec = f3.resolve_recommendation_from_artifact(artifact)
        assert rec.recommended_questionnaire is None
        assert rec.recommendation_caveat is None
        assert rec.top_candidate_disease is None
        assert rec.top_candidate_similarity_score is None

    def test_empty_candidates_list_yields_no_top_candidate(self) -> None:
        artifact = _artifact(recommended_questionnaire=None, candidates=[])
        rec = f3.resolve_recommendation_from_artifact(artifact)
        assert rec.top_candidate_disease is None
        assert rec.recommended_questionnaire is None

    def test_populated_artifact_resolves_all_fields(self) -> None:
        artifact = _artifact(
            recommended_questionnaire="PHQ-9",
            recommendation_caveat="mania blind spot caveat",
        )
        rec = f3.resolve_recommendation_from_artifact(artifact)
        assert rec.recommended_questionnaire == "PHQ-9"
        assert rec.recommendation_caveat == "mania blind spot caveat"
        assert rec.top_candidate_disease == "우울 삽화(우울증)"
        assert rec.top_candidate_similarity_score == 0.8

    def test_load_recommendation_reads_file_and_resolves(self, tmp_path: Path) -> None:
        path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="AUDIT-C"))
        rec = f3.load_recommendation(path)
        assert rec.recommended_questionnaire == "AUDIT-C"

    def test_load_recommendation_missing_file_raises_loudly(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            f3.load_recommendation(tmp_path / "nope.json")


# ── administer_survey: unpopulated-skip / clamp / retry ─────────────────


class TestAdministerSurveyUnpopulatedSkip:
    @pytest.mark.asyncio
    async def test_unpopulated_scale_raises_never_improvises(self) -> None:
        with pytest.raises(ValueError, match="unpopulated"):
            await f3.administer_survey("WHO-5", _never_called)

    @pytest.mark.asyncio
    async def test_answer_fn_never_called_for_unpopulated_scale(self) -> None:
        with pytest.raises(ValueError):
            await f3.administer_survey("WHO-5", _never_called)


class TestClampResponse:
    def test_in_range_value_passes_through_unchanged(self) -> None:
        item = ScaleItem(index=1, text_ko="x", response_min=0, response_max=3)
        assert f3._clamp_response(2, item) == 2

    def test_above_max_is_clamped_with_warning(self, caplog) -> None:
        item = ScaleItem(index=1, text_ko="x", response_min=0, response_max=3)
        with caplog.at_level(logging.WARNING):
            value = f3._clamp_response(9, item)
        assert value == 3
        assert any("clamped_to=3" in r.message for r in caplog.records)

    def test_below_min_is_clamped_with_warning(self, caplog) -> None:
        item = ScaleItem(index=1, text_ko="x", response_min=0, response_max=4)
        with caplog.at_level(logging.WARNING):
            value = f3._clamp_response(-5, item)
        assert value == 0
        assert any("clamped_to=0" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_administer_survey_clamps_out_of_range_answer_fn_values(self) -> None:
        # PHQ-9 range is 0-3; feed one deliberately out-of-range raw value.
        responses, score_result = await f3.administer_survey(
            "PHQ-9", _fixed_answer_fn([1, 1, 99, 1, 1, 0, 1, 0, 0])
        )
        assert responses == [1, 1, 3, 1, 1, 0, 1, 0, 0]
        assert score_result.total_score == sum(responses) == 8


# ── Scoring correctness vs hand-computed totals/bands (all 5 scales) ────
# score_survey itself is REUSED unmodified (not re-implemented) — these
# tests prove F3's own item-bank ranges/administer_survey path produce the
# SAME hand-computed totals/bands as score_survey's own published cutoffs
# (T1-F3-VER-007/008).


class TestScoringCorrectnessBoundaryFixtures:
    @pytest.mark.asyncio
    async def test_phq9_boundary_cutoffs_5_10_15_20(self) -> None:
        cases = [
            ([0] * 9, 0, "minimal"),
            ([0, 0, 0, 0, 1, 1, 1, 1, 1], 5, "mild"),  # boundary: total=5 -> mild
            ([1, 1, 1, 1, 1, 1, 1, 1, 2], 10, "moderate"),  # total=10 -> moderate
            ([2, 2, 2, 2, 2, 1, 1, 1, 2], 15, "moderately_severe"),  # total=15
            ([3, 3, 3, 3, 2, 2, 2, 2, 0], 20, "severe"),  # total=20 -> severe
        ]
        for responses, expected_total, expected_severity in cases:
            got_responses, score_result = await f3.administer_survey(
                "PHQ-9", _fixed_answer_fn(responses)
            )
            assert got_responses == responses
            assert score_result.total_score == expected_total == sum(responses)
            assert score_result.severity == expected_severity

    @pytest.mark.asyncio
    async def test_phq9_q9_positive_triggers_safety_referral_field(self) -> None:
        responses = [0, 0, 0, 0, 0, 0, 0, 0, 1]  # Q9 = 1
        _, score_result = await f3.administer_survey("PHQ-9", _fixed_answer_fn(responses))
        assert score_result.critical_item_positive is True
        assert score_result.recommended_action == "safety_referral"

    @pytest.mark.asyncio
    async def test_phq9_q9_zero_no_referral(self) -> None:
        responses = [1, 1, 1, 1, 1, 0, 0, 0, 0]
        _, score_result = await f3.administer_survey("PHQ-9", _fixed_answer_fn(responses))
        assert score_result.critical_item_positive is False

    @pytest.mark.asyncio
    async def test_audit_c_sex_thresholds(self) -> None:
        # total=3: below male/unknown threshold(4), at/above female threshold(3).
        responses = [1, 1, 1]
        _, male_result = await f3.administer_survey(
            "AUDIT-C", _fixed_answer_fn(responses), patient_sex="male"
        )
        assert male_result.severity == "low_risk"
        _, female_result = await f3.administer_survey(
            "AUDIT-C", _fixed_answer_fn(responses), patient_sex="female"
        )
        assert female_result.severity == "hazardous_drinking"

    @pytest.mark.asyncio
    async def test_audit_c_max_score_and_range(self) -> None:
        responses = [4, 4, 4]
        _, score_result = await f3.administer_survey("AUDIT-C", _fixed_answer_fn(responses))
        assert score_result.total_score == 12 == score_result.max_score


# ── run_f3_administration: full flow, all 3 outcomes ────────────────────


class TestRunF3AdministrationAdministered:
    @pytest.mark.asyncio
    async def test_administered_outcome_full_artifact(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire="PHQ-9", recommendation_caveat="mood caveat"),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([1, 1, 2, 1, 1, 0, 1, 0, 0]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
        )
        output = result["output"]
        assert result["outcome"] == f3.ADMINISTERED_OUTCOME
        assert output.outcome == "administered"
        assert output.vp_id == "VP-TEST"
        assert output.session_id == "s1"
        assert output.scale_name == "PHQ-9"
        assert output.item_bank_version == "v1"
        assert output.responses == [1, 1, 2, 1, 1, 0, 1, 0, 0]
        assert output.score_result is not None
        assert output.score_result.total_score == 7
        assert output.safety_referral is False
        assert output.recommendation_provenance.top_candidate_disease == "우울 삽화(우울증)"
        assert output.recommendation_provenance.recommendation_caveat == "mood caveat"
        assert output.answer_mode == "expected"
        assert output.is_diagnostic is False
        assert output.administration_mode == "natural"
        assert output.threshold_caveat is None  # PHQ-9 isn't in _SEVERITY_CAVEATS (AUDIT-C/GAD-7)

        json_path = result["paths"]["json"]
        report_path = result["paths"]["report"]
        scale_scores_path = result["paths"]["scale_scores"]
        assert json_path.exists()
        assert report_path.exists()
        assert scale_scores_path.exists()
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert saved["outcome"] == "administered"

    @pytest.mark.asyncio
    async def test_scale_scores_projection_round_trips_into_f2_load_scale_scores(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="AUDIT-C"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([4, 3, 4]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
        )
        scale_scores_path = result["paths"]["scale_scores"]

        loaded = f2._load_scale_scores(str(scale_scores_path))
        assert len(loaded) == 1
        assert loaded[0].scale_name == "AUDIT-C"
        assert loaded[0].total_score == 11
        assert loaded[0].severity == result["output"].score_result.severity

    @pytest.mark.asyncio
    async def test_audit_c_administered_carries_threshold_caveat(self, tmp_path: Path) -> None:
        """CVR-016 condition 3 / ADR-033 decision 2: AUDIT-C severity output
        must carry the Korean-population non-reconciliation caveat — never
        silently shipped bare."""
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="AUDIT-C"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([4, 3, 4]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
        )
        output = result["output"]
        assert output.threshold_caveat is not None
        assert "Seong" in output.threshold_caveat
        assert "Woo" in output.threshold_caveat
        # Threshold itself unchanged (byte-frozen) — severity still computed
        # by the untouched survey_scorer.py band.
        assert output.score_result.severity == "hazardous_drinking"

    @pytest.mark.asyncio
    async def test_gad7_administered_carries_band_caveat(self, tmp_path: Path) -> None:
        """CVR-016 binding condition 1 / CVR-017 binding condition 1 /
        REV-039 correction D: GAD-7 severity output must carry the same
        structural caveat AUDIT-C carries — the Korean-language band-sourcing
        citation was retracted this mission and the bands rest on
        international-convention-only evidence."""
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="GAD-7"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([2, 2, 2, 2, 2, 2, 2]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
        )
        output = result["output"]
        assert output.outcome == "administered"
        assert output.scale_name == "GAD-7"
        assert output.threshold_caveat is not None
        assert "Spitzer" in output.threshold_caveat
        assert "retract" in output.threshold_caveat.lower()
        # Bands themselves unchanged (byte-frozen) — severity still computed
        # by the untouched survey_scorer.py band.
        assert output.score_result.total_score == 14
        assert output.score_result.severity is not None

        saved = json.loads(result["paths"]["json"].read_text(encoding="utf-8"))
        assert saved["threshold_caveat"] is not None
        assert "Spitzer" in saved["threshold_caveat"]

    @pytest.mark.asyncio
    async def test_phq4_administered_carries_no_caveat(self, tmp_path: Path) -> None:
        """Only AUDIT-C and GAD-7 are in `_SEVERITY_CAVEATS` — every other
        populated scale (e.g. PHQ-4) must stay `None`, unaffected by this
        mission's addition."""
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="PHQ-4"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([1, 1, 1, 1]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
        )
        assert result["output"].threshold_caveat is None


class TestRunF3AdministrationForcedScale:
    """`forced_scale` (`PLAN-2026-W29-A` step 6 / `ADR-033` decision 6) —
    the production entry point's override kwarg. Default `None` must
    preserve every pre-existing caller's exact behavior."""

    @pytest.mark.asyncio
    async def test_default_none_preserves_natural_behavior(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="PHQ-9"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([0, 0, 0, 0, 0, 0, 0, 0, 0]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
        )
        assert result["output"].scale_name == "PHQ-9"
        assert result["output"].administration_mode == "natural"

    @pytest.mark.asyncio
    async def test_forced_scale_overrides_f2_recommendation(self, tmp_path: Path) -> None:
        # F2 recommended PHQ-9; forced_scale overrides to GAD-7.
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="PHQ-9"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([1, 1, 1, 1, 1, 1, 1]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
            forced_scale="GAD-7",
        )
        output = result["output"]
        assert output.scale_name == "GAD-7"
        assert output.administration_mode == "forced"
        assert output.outcome == "administered"
        assert output.score_result.total_score == 7
        # F2's ACTUAL recommendation is still carried for traceability, even
        # though it did not drive this administration.
        assert output.recommendation_provenance.top_candidate_disease == "우울 삽화(우울증)"

    @pytest.mark.asyncio
    async def test_forced_scale_works_when_f2_recommended_nothing(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire=None))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([4, 3, 4]),
            answer_mode="expected",
            output_dir=tmp_path / "out",
            forced_scale="AUDIT-C",
        )
        output = result["output"]
        assert output.scale_name == "AUDIT-C"
        assert output.administration_mode == "forced"
        assert output.outcome == "administered"

    @pytest.mark.asyncio
    async def test_forced_unpopulated_scale_never_improvises(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="PHQ-9"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_never_called,
            output_dir=tmp_path / "out",
            forced_scale="WHO-5",
        )
        output = result["output"]
        assert output.outcome == f3.UNPOPULATED_OUTCOME
        assert output.administration_mode == "forced"
        assert output.responses == []


class TestRunF3AdministrationSkipOutcomes:
    @pytest.mark.asyncio
    async def test_no_questionnaire_indicated_answer_fn_never_called(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire=None))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_never_called,
            output_dir=tmp_path / "out",
        )
        output = result["output"]
        assert result["outcome"] == f3.NO_QUESTIONNAIRE_OUTCOME
        assert output.scale_name is None
        assert output.responses == []
        assert output.score_result is None
        assert output.safety_referral is False
        assert output.item_bank_version is None
        assert output.item_bank_provenance is None
        # survey.json + .md are always written; scale_scores.json is not.
        assert "json" in result["paths"] and "report" in result["paths"]
        assert "scale_scores" not in result["paths"]

    @pytest.mark.asyncio
    async def test_item_bank_unpopulated_answer_fn_never_called(self, tmp_path: Path) -> None:
        # WHO-5 is item bank v1's only remaining unpopulated scale.
        artifact_path = _write_artifact(tmp_path, _artifact(recommended_questionnaire="WHO-5"))
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_never_called,
            output_dir=tmp_path / "out",
        )
        output = result["output"]
        assert result["outcome"] == f3.UNPOPULATED_OUTCOME
        assert output.scale_name == "WHO-5"
        assert output.responses == []
        assert output.score_result is None
        assert output.item_bank_version == "v1"
        assert output.item_bank_provenance.startswith("unpopulated-v1")
        assert "scale_scores" not in result["paths"]

    @pytest.mark.asyncio
    async def test_missing_persona_id_falls_back_to_session_id(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire=None, persona_id=None, session_id="sess-only"),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path, answer_fn=_never_called,
            output_dir=tmp_path / "out",
        )
        assert result["output"].vp_id == "sess-only"


# ── save_f3_result / _build_report — naming + outcome-conditional writes ──


class TestSaveF3Result:
    def test_administered_writes_scale_scores_file(self, tmp_path: Path) -> None:
        output = SurveyResultOutput(
            vp_id="VP-Z", session_id="s", timestamp="t", outcome="administered",
            scale_name="PHQ-9", item_bank_version="v0",
            item_bank_provenance="construct-labels-v0, persona-file-sourced, non-validated",
            responses=[1, 1, 1, 1, 1, 1, 1, 1, 1],
            score_result={
                "scale_name": "PHQ-9", "total_score": 9, "max_score": 27, "severity": "mild",
            },
            recommendation_provenance=RecommendationProvenance(),
        )
        paths = f3.save_f3_result(output, tmp_path)
        assert paths["json"].name.endswith("_survey.json")
        assert paths["report"].name.endswith("_survey.md")
        assert paths["scale_scores"].name.endswith("_scale_scores.json")
        assert paths["json"].parent.name == "VP-Z"

    def test_skip_outcome_writes_no_scale_scores_file(self, tmp_path: Path) -> None:
        output = SurveyResultOutput(
            vp_id="VP-Z", session_id="s", timestamp="t", outcome="no_questionnaire_indicated",
            recommendation_provenance=RecommendationProvenance(),
        )
        paths = f3.save_f3_result(output, tmp_path)
        assert "scale_scores" not in paths
        assert "PHQ" not in paths["report"].read_text(encoding="utf-8")  # sanity: no phantom scale


# ── Schema-layer checks (extra=forbid, is_diagnostic fixed) ─────────────


class TestSurveyResultOutputSchema:
    def _valid_kwargs(self) -> dict:
        return dict(
            vp_id="VP-1", session_id="s1", timestamp="2026-01-01T00:00:00",
            outcome="no_questionnaire_indicated",
            recommendation_provenance=RecommendationProvenance(),
        )

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SurveyResultOutput(**self._valid_kwargs(), unexpected_field="x")  # type: ignore[arg-type]

    def test_is_diagnostic_always_false(self) -> None:
        out = SurveyResultOutput(**self._valid_kwargs())
        assert out.is_diagnostic is False

    def test_invalid_outcome_literal_rejected(self) -> None:
        kwargs = self._valid_kwargs()
        kwargs["outcome"] = "made_up_outcome"
        with pytest.raises(ValidationError):
            SurveyResultOutput(**kwargs)

    def test_administration_mode_defaults_to_natural(self) -> None:
        out = SurveyResultOutput(**self._valid_kwargs())
        assert out.administration_mode == "natural"

    def test_administration_mode_accepts_forced(self) -> None:
        out = SurveyResultOutput(**self._valid_kwargs(), administration_mode="forced")
        assert out.administration_mode == "forced"

    def test_administration_mode_invalid_literal_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SurveyResultOutput(**self._valid_kwargs(), administration_mode="made_up_mode")

    def test_threshold_caveat_defaults_to_none(self) -> None:
        out = SurveyResultOutput(**self._valid_kwargs())
        assert out.threshold_caveat is None

    def test_threshold_caveat_accepts_a_string(self) -> None:
        out = SurveyResultOutput(**self._valid_kwargs(), threshold_caveat="some caveat")
        assert out.threshold_caveat == "some caveat"

    def test_extra_field_still_forbidden_with_new_fields_present(self) -> None:
        """`extra="forbid"` must still hold after this mission's schema
        additions (`administration_mode`/`threshold_caveat`) — a new field
        elsewhere in the model must not accidentally loosen the model
        config."""
        with pytest.raises(ValidationError):
            SurveyResultOutput(
                **self._valid_kwargs(), administration_mode="forced", unexpected_field="x"
            )  # type: ignore[arg-type]

    def test_module_shares_no_import_with_handoff_schema(self) -> None:
        """Standalone-by-design invariant (this module's own half) —
        `src.schemas.survey_result` must never import `src.schemas.handoff`.
        Checked against the actual compiled import graph (not a source-text
        grep, which would also match this file's own docstring prose)."""
        import src.schemas.survey_result as survey_result_module

        assert not hasattr(survey_result_module, "SlotData")
        assert not hasattr(survey_result_module, "HandoffInput")
        module_names = {
            getattr(v, "__module__", None) for v in vars(survey_result_module).values()
        }
        assert "src.schemas.handoff" not in module_names
