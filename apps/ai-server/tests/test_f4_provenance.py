"""F4 quick-dev provenance threading tests — `_archive/plans/f4_quick_dev_plan.md`
§2.6/§2.7, `PLAN-2026-W29-D`, `ADR-036` item 3.

Covers: F1 (`_apply_scenario_guideline`/`_apply_scenario_provenance` +
`F1Result` round-trip through `save_f1_result`), F2 (`_build_artifact`
reprojection), F3 (`run_f3_administration` reprojection). No live LLM/DB
call anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.f2 as f2
import src.f3 as f3
from src.f1 import F1Result, _apply_scenario_guideline, _apply_scenario_provenance, save_f1_result
from src.schemas.domain_inference import DomainInferenceOutput, RetrievalMeta
from src.scoring.item_bank import ScaleItem
from tests.f1_testkit import (
    StubDialogueAgent,
    StubSafetyAgent,
    StubSlotAgent,
    make_patient_fn,
    make_pipeline,
)
from tests.simulation.patient_llm import load_persona

# ── F1: isolation seam (§2.6 option C) ─────────────────────────────────


class TestApplyScenarioGuideline:
    def test_none_guideline_is_a_no_op(self) -> None:
        persona = load_persona("VP-001")
        before = persona.system_prompt
        _apply_scenario_guideline(persona, None)
        assert persona.system_prompt == before

    def test_empty_string_guideline_is_a_no_op(self) -> None:
        persona = load_persona("VP-001")
        before = persona.system_prompt
        _apply_scenario_guideline(persona, "")
        assert persona.system_prompt == before

    def test_non_none_guideline_reaches_system_prompt_appended_not_replacing(self) -> None:
        persona = load_persona("VP-001")
        before = persona.system_prompt
        marker = (
            "## 세션 시나리오 안내 (개발 검증용, 2026-01-01, 세션 1/11)\n"
            "- 현재 상태: ZZZ_MARKER_9999"
        )
        _apply_scenario_guideline(persona, marker)
        assert persona.system_prompt.startswith(before)
        assert "ZZZ_MARKER_9999" in persona.system_prompt

    def test_applied_after_prior_handoff_never_touches_that_text(self) -> None:
        persona = load_persona("VP-001")
        persona.system_prompt += "\n\n## 이전 상담 기록\n[이전 세션 요약]"
        before_with_handoff = persona.system_prompt
        _apply_scenario_guideline(persona, "## 세션 시나리오 안내\n- 현재 상태: X")
        assert before_with_handoff in persona.system_prompt
        prompt = persona.system_prompt
        assert prompt.index("이전 상담 기록") < prompt.index("세션 시나리오 안내")


class TestApplyScenarioProvenance:
    def test_none_values_leave_defaults_untouched(self) -> None:
        result = F1Result(session_id="s1", persona_id="VP-001", persona_name="test")
        _apply_scenario_provenance(result, None, None)
        assert result.scenario_pack_id is None
        assert result.arc_mode is None

    def test_non_none_values_are_threaded(self) -> None:
        result = F1Result(session_id="s1", persona_id="VP-001", persona_name="test")
        _apply_scenario_provenance(result, "VP-001_improvement_plateau_s01", "improvement_plateau")
        assert result.scenario_pack_id == "VP-001_improvement_plateau_s01"
        assert result.arc_mode == "improvement_plateau"


class TestF1ResultProvenanceReachesSavedArtifact:
    """Wave 2 done-when: `scenario_pack_id` reaches the saved
    conversation.json (via `asdict` -- any new dataclass field is captured
    for free, no serializer change needed)."""

    @pytest.mark.asyncio
    async def test_scenario_provenance_survives_save_and_reload(self, tmp_path: Path) -> None:
        pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), StubSlotAgent())
        result = await pipeline.run_session(
            patient_input_fn=make_patient_fn(["그냥 잠을 잘 못 자요."]),
            session_id="t-f4-prov", persona_id="VP-001", persona_name="test", max_turns=1,
        )
        _apply_scenario_provenance(result, "VP-001_improvement_plateau_s01", "improvement_plateau")

        paths = save_f1_result(result, output_dir=tmp_path)
        saved = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert saved["scenario_pack_id"] == "VP-001_improvement_plateau_s01"
        assert saved["arc_mode"] == "improvement_plateau"

    @pytest.mark.asyncio
    async def test_natural_session_has_none_provenance(self, tmp_path: Path) -> None:
        pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), StubSlotAgent())
        result = await pipeline.run_session(
            patient_input_fn=make_patient_fn(["그냥 잠을 잘 못 자요."]),
            session_id="t-f4-natural", persona_id="VP-001", persona_name="test", max_turns=1,
        )
        paths = save_f1_result(result, output_dir=tmp_path)
        saved = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert saved.get("scenario_pack_id") is None
        assert saved.get("arc_mode") is None

    def test_result_from_dict_reads_provenance_back(self) -> None:
        from src.f1 import _result_from_dict

        data = {
            "session_id": "s1", "persona_id": "VP-001", "persona_name": "t",
            "scenario_pack_id": "VP-001_improvement_plateau_s01", "arc_mode": "improvement_plateau",
        }
        result = _result_from_dict(data)
        assert result.scenario_pack_id == "VP-001_improvement_plateau_s01"
        assert result.arc_mode == "improvement_plateau"

    def test_result_from_dict_defaults_none_for_pre_f4_artifact(self) -> None:
        from src.f1 import _result_from_dict

        data = {"session_id": "s1", "persona_id": "VP-001", "persona_name": "t"}
        result = _result_from_dict(data)
        assert result.scenario_pack_id is None
        assert result.arc_mode is None


# ── F2: artifact reprojection ────────────────────────────────────────────


class TestF2ArtifactProvenanceReprojection:
    def _output(self) -> DomainInferenceOutput:
        return DomainInferenceOutput(
            model_used="test-model", prompt_version="v1", latency_ms=1.0, reason_summary="ok",
            domain_candidates=[], department_candidates=[], summary="",
            retrieval_meta=RetrievalMeta(mode="llm_only", chunks_returned=0, chunk_ids=[]),
        )

    def _minimal_artifact_kwargs(self) -> dict:
        return {
            "output": self._output(), "domain_candidates": [], "repro": {
                "git_head": "x", "model_used": "x", "prompt_version": "v1",
                "input_file": "x.json", "input_sha256": "x", "mode": "llm_only",
                "latency_ms": 1.0, "generated_at": "2026-01-01T00:00:00",
            },
            "chunk_texts": {}, "utterances": {}, "verdicts": [], "counts": {"accepted": 0},
            "filter_summary": {
                "candidates_before": 0, "candidates_after": 0, "candidates_eliminated": 0,
                "eliminated_domains": [], "evidence_stripped": 0,
                "evidence_stripped_risk_lexicon": 0,
            },
            "orphans": [], "session_id": "t", "persona_id": "VP-001",
        }

    def test_scenario_provenance_reprojected_when_present(self) -> None:
        artifact = f2._build_artifact(
            **self._minimal_artifact_kwargs(),
            scenario_pack_id="VP-001_improvement_plateau_s01",
            arc_mode="improvement_plateau",
        )
        assert artifact["scenario_pack_id"] == "VP-001_improvement_plateau_s01"
        assert artifact["arc_mode"] == "improvement_plateau"

    def test_scenario_provenance_defaults_none(self) -> None:
        artifact = f2._build_artifact(**self._minimal_artifact_kwargs())
        assert artifact["scenario_pack_id"] is None
        assert artifact["arc_mode"] is None


# ── F3: artifact reprojection ────────────────────────────────────────────


def _f2_artifact(*, scenario_pack_id: str | None = None, arc_mode: str | None = None) -> dict:
    data: dict = {
        "session_id": "s1", "persona_id": "VP-TEST",
        "ai_predicted_disease": {
            "candidates": [{"disease": "우울 삽화(우울증)", "similarity_score": 0.8}],
            "mode": "rag_live", "is_diagnostic": False,
            "recommended_questionnaire": None, "recommendation_caveat": None,
        },
    }
    if scenario_pack_id is not None:
        data["scenario_pack_id"] = scenario_pack_id
    if arc_mode is not None:
        data["arc_mode"] = arc_mode
    return data


def _write_artifact(tmp_path: Path, artifact: dict, name: str = "art.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    return path


class TestF3ArtifactProvenanceReprojection:
    @pytest.mark.asyncio
    async def test_provenance_reprojected_from_f2_artifact(self, tmp_path: Path) -> None:
        artifact = _f2_artifact(
            scenario_pack_id="VP-003_relapse_after_partial_improvement_s08",
            arc_mode="relapse_after_partial_improvement",
        )
        artifact_path = _write_artifact(tmp_path, artifact)

        async def _never_called(item: ScaleItem) -> int:
            raise AssertionError("must not be called for no_questionnaire_indicated")

        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path, answer_fn=_never_called,
            output_dir=tmp_path, vp_id="VP-TEST",
        )
        output = result["output"]
        assert output.scenario_pack_id == "VP-003_relapse_after_partial_improvement_s08"
        assert output.arc_mode == "relapse_after_partial_improvement"

    @pytest.mark.asyncio
    async def test_provenance_none_for_natural_artifact(self, tmp_path: Path) -> None:
        artifact = _f2_artifact()
        artifact_path = _write_artifact(tmp_path, artifact)

        async def _never_called(item: ScaleItem) -> int:
            raise AssertionError("must not be called for no_questionnaire_indicated")

        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path, answer_fn=_never_called,
            output_dir=tmp_path, vp_id="VP-TEST",
        )
        output = result["output"]
        assert output.scenario_pack_id is None
        assert output.arc_mode is None

    @pytest.mark.asyncio
    async def test_provenance_survives_saved_survey_json(self, tmp_path: Path) -> None:
        artifact = _f2_artifact(
            scenario_pack_id="VP-003_relapse_after_partial_improvement_s08",
            arc_mode="relapse_after_partial_improvement",
        )
        artifact_path = _write_artifact(tmp_path, artifact)

        async def _never_called(item: ScaleItem) -> int:
            raise AssertionError("must not be called for no_questionnaire_indicated")

        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path, answer_fn=_never_called,
            output_dir=tmp_path, vp_id="VP-TEST",
        )
        saved = json.loads(result["paths"]["json"].read_text(encoding="utf-8"))
        assert saved["scenario_pack_id"] == "VP-003_relapse_after_partial_improvement_s08"
        assert saved["arc_mode"] == "relapse_after_partial_improvement"
