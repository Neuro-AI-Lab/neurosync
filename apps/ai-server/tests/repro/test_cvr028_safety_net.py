"""CVR-028 Finding 1 (clinical-blocking) regression tests — F3 crisis
safety-net questionnaire path.

`discussion.md` CVR-028: VP-003 (5/11 crisis sessions, `crisis_triggered=
True`) had 0/11 F3 administrations — every session fell back to
`llm_only` with zero domain candidates, so `ai_predicted_disease.
recommended_questionnaire` was `None` every time and F3 always resolved
`no_questionnaire_indicated`. The single highest-acuity patient in the
cohort handed off with zero quantified severity/SI-item data.

Fix (`src.f3.resolve_effective_scale`): when F2 yields no recommendation
AND the session is high-acuity (`crisis_triggered=True` or
`session_ctrs<=2`), default-administer PHQ-9 (the SI-item-bearing
instrument), recorded with `administration_mode="safety_net"` — a
provenance marker distinct from `"natural"` (F2-driven) — never
overriding a real F2 recommendation or a `--force-questionnaire` override.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.f3 as f3
from src.scoring.item_bank import ScaleItem


def _artifact(
    *,
    recommended_questionnaire: str | None = None,
    crisis_triggered: bool = False,
    session_ctrs: int | None = None,
    persona_id: str = "VP-TEST",
    session_id: str = "s1",
) -> dict:
    return {
        "session_id": session_id,
        "persona_id": persona_id,
        "ai_predicted_disease": {
            "candidates": [],
            "mode": "experimental_unpopulated",
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


# PHQ-9 has 9 items, response range 0-3 — 9 zeros is a valid, safe fixture
# (no critical-item false-positive noise in these tests, which are about
# scale SELECTION, not scoring).
_PHQ9_ZEROS = [0] * 9


class TestResolveRecommendationFromArtifactCarriesRiskContext:
    def test_crisis_triggered_and_session_ctrs_reprojected(self) -> None:
        artifact = _artifact(crisis_triggered=True, session_ctrs=1)
        rec = f3.resolve_recommendation_from_artifact(artifact)
        assert rec.crisis_triggered is True
        assert rec.session_ctrs == 1

    def test_defaults_for_pre_fix_artifact_missing_the_keys(self) -> None:
        artifact = _artifact()
        del artifact["crisis_triggered"]
        del artifact["session_ctrs"]
        rec = f3.resolve_recommendation_from_artifact(artifact)
        assert rec.crisis_triggered is False
        assert rec.session_ctrs is None


class TestResolveEffectiveScale:
    """Precedence: forced > F2 recommendation > safety net > None."""

    def test_forced_scale_always_wins(self) -> None:
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True)
        )
        scale, triggered = f3.resolve_effective_scale(rec, forced_scale="GAD-7")
        assert scale == "GAD-7"
        assert triggered is False

    def test_f2_recommendation_used_when_present_even_if_crisis(self) -> None:
        """The safety net never overrides a REAL F2 recommendation."""
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True)
        )
        scale, triggered = f3.resolve_effective_scale(rec)
        assert scale == "AUDIT-C"
        assert triggered is False

    def test_no_recommendation_and_crisis_triggered_defaults_to_phq9(self) -> None:
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=True)
        )
        scale, triggered = f3.resolve_effective_scale(rec)
        assert scale == f3.SAFETY_NET_SCALE == "PHQ-9"
        assert triggered is True

    def test_no_recommendation_and_low_ctrs_defaults_to_phq9(self) -> None:
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=False, session_ctrs=2)
        )
        scale, triggered = f3.resolve_effective_scale(rec)
        assert scale == "PHQ-9"
        assert triggered is True

    def test_ctrs_boundary_3_triggers_safety_net(self) -> None:
        """CVR-029 (major, accepted): threshold widened <=2 -> <=3 — VP-003
        reproduction showed 8/11 sessions with critical-level rule hits
        while crisis_triggered stayed False at the CTRS-3 boundary."""
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=False, session_ctrs=3)
        )
        scale, triggered = f3.resolve_effective_scale(rec)
        assert scale == "PHQ-9"
        assert triggered is True

    def test_ctrs_boundary_4_does_not_trigger_safety_net(self) -> None:
        """session_ctrs<=3 only (CVR-029) — CTRS=4 is not the crisis-adjacent band."""
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=False, session_ctrs=4)
        )
        scale, triggered = f3.resolve_effective_scale(rec)
        assert scale is None
        assert triggered is False

    def test_no_recommendation_and_not_high_acuity_stays_none(self) -> None:
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=False, session_ctrs=5)
        )
        scale, triggered = f3.resolve_effective_scale(rec)
        assert scale is None
        assert triggered is False

    def test_session_ctrs_none_and_not_crisis_stays_none(self) -> None:
        rec = f3.resolve_recommendation_from_artifact(
            _artifact(recommended_questionnaire=None, crisis_triggered=False, session_ctrs=None)
        )
        scale, triggered = f3.resolve_effective_scale(rec)
        assert scale is None
        assert triggered is False


class TestRunF3AdministrationSafetyNet:
    @pytest.mark.asyncio
    async def test_crisis_session_with_no_f2_recommendation_administers_phq9(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire=None, crisis_triggered=True, session_ctrs=1),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn(_PHQ9_ZEROS),
            answer_mode="expected",
            output_dir=tmp_path,
            vp_id="VP-003",
        )
        output = result["output"]
        assert output.outcome == f3.ADMINISTERED_OUTCOME
        assert output.scale_name == "PHQ-9"
        assert output.administration_mode == "safety_net"

    @pytest.mark.asyncio
    async def test_non_crisis_session_with_no_f2_recommendation_stays_no_questionnaire(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire=None, crisis_triggered=False, session_ctrs=5),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn(_PHQ9_ZEROS),
            answer_mode="expected",
            output_dir=tmp_path,
            vp_id="VP-NONCRISIS",
        )
        output = result["output"]
        assert output.outcome == f3.NO_QUESTIONNAIRE_OUTCOME
        assert output.administration_mode == "natural"

    @pytest.mark.asyncio
    async def test_safety_net_never_overrides_real_f2_recommendation(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire="AUDIT-C", crisis_triggered=True),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([0, 0, 0]),
            answer_mode="expected",
            output_dir=tmp_path,
            vp_id="VP-AUDIT",
        )
        output = result["output"]
        assert output.scale_name == "AUDIT-C"
        assert output.administration_mode == "natural"

    @pytest.mark.asyncio
    async def test_forced_scale_wins_over_safety_net(self, tmp_path: Path) -> None:
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire=None, crisis_triggered=True),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn([0] * 7),  # GAD-7 has 7 items
            answer_mode="expected",
            output_dir=tmp_path,
            vp_id="VP-FORCED",
            forced_scale="GAD-7",
        )
        output = result["output"]
        assert output.scale_name == "GAD-7"
        assert output.administration_mode == "forced"

    @pytest.mark.asyncio
    async def test_safety_net_survey_json_is_readable_by_ledger_projection(
        self, tmp_path: Path
    ) -> None:
        """The saved artifact's administration_mode is what
        `continuous_test._build_f3_ledger_subobject` reprojects verbatim —
        this proves the marker actually reaches the persisted JSON."""
        artifact_path = _write_artifact(
            tmp_path,
            _artifact(recommended_questionnaire=None, crisis_triggered=True),
        )
        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_fixed_answer_fn(_PHQ9_ZEROS),
            answer_mode="expected",
            output_dir=tmp_path,
            vp_id="VP-LEDGER",
        )
        saved = json.loads(result["paths"]["json"].read_text(encoding="utf-8"))
        assert saved["administration_mode"] == "safety_net"
        assert saved["scale_name"] == "PHQ-9"
