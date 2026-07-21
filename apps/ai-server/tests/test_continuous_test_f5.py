"""`src.continuous_test`'s F5 stage + standalone replay CLI —
`_archive/plans/f5_quick_dev_plan.md`, `PLAN-2026-W29-E`, `ADR-037`. No live
LLM/HTTP/DB anywhere in this file: every fixture is a synthetic ledger +
F1-F4 artifact set written directly under `tmp_path` (this file has zero
runtime dependency on `experiments/` or `docs/ai/simulation_results/` —
mirrors `tests/test_continuous_test_f4.py`'s own discipline).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import src.continuous_test as ct

# ── Fixture helpers (synthetic F1/F2/F3/F4 artifacts, never real ones) ──


def _write_conversation(
    tmp_path: Path,
    persona_id: str,
    session_index: int,
    *,
    simulated_date: str = "2026-01-01",
    session_ctrs: int | None = 4,
    crisis_triggered: bool = False,
    final_slots: list[dict[str, str]] | None = None,
    persona_name: str = "테스트",
    model: str = "solar-pro3-test",
) -> Path:
    vp_dir = tmp_path / persona_id
    vp_dir.mkdir(parents=True, exist_ok=True)
    path = vp_dir / f"{persona_id}_202601{session_index:02d}_000000_conversation.json"
    path.write_text(
        json.dumps(
            {
                "session_id": f"f1_{persona_id}",
                "persona_id": persona_id,
                "persona_name": persona_name,
                "session_index": session_index,
                "simulated_date": simulated_date,
                "model": model,
                "final_slots": final_slots
                if final_slots is not None
                else [
                    {"key": "chief_complaint", "value": "잠을 잘 못 잠"},
                    {"key": "history_of_present_illness", "value": "3개월 전부터 지속"},
                ],
                "session_ctrs": session_ctrs,
                "crisis_triggered": crisis_triggered,
                "crisis_turn": None,
                "risk_floor": None,
                "probe_events": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _write_domain_inference(
    tmp_path: Path,
    persona_id: str,
    session_index: int,
    *,
    with_candidates: bool = True,
    department_candidates: list[dict] | None = None,
    validation_errors: list[dict] | None = None,
) -> Path:
    """`validation_errors` (`ADR-038` Decision 2a / `VAL-016`): the
    artifact's own top-level field mirroring a real Pydantic atomic-parse
    failure — `None`/absent by default (matches the common case)."""
    vp_dir = tmp_path / persona_id
    vp_dir.mkdir(parents=True, exist_ok=True)
    path = vp_dir / f"{persona_id}_202601{session_index:02d}_010000_domain_inference.json"
    artifact: dict = {
        "domain_candidates": [{"domain": "depression", "confidence": 0.7}],
        "department_candidates": (
            department_candidates
            if department_candidates is not None
            else [
                {
                    "department": "정신건강의학과",
                    "reason": "우울 증상",
                    "domain_ref": "depression",
                }
            ]
        ),
        "ai_predicted_disease": {
            "candidates": [
                {"disease": "우울 삽화(우울증)", "similarity_score": 0.5}
            ]
            if with_candidates
            else [],
            "mode": "rag_live",
            "is_diagnostic": False,
            "recommended_questionnaire": "PHQ-9",
            "recommendation_caveat": None,
        },
    }
    if validation_errors is not None:
        artifact["validation_errors"] = validation_errors
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    return path


def _write_survey(
    tmp_path: Path,
    persona_id: str,
    session_index: int,
    *,
    outcome: str = "administered",
    scale_name: str = "PHQ-9",
    total_score: int = 15,
    critical_item_positive: bool = False,
) -> Path:
    vp_dir = tmp_path / persona_id
    vp_dir.mkdir(parents=True, exist_ok=True)
    path = vp_dir / f"{persona_id}_202601{session_index:02d}_020000_survey.json"
    score_result = (
        {
            "scale_name": scale_name,
            "total_score": total_score,
            "max_score": 27,
            "severity": "moderate",
            "critical_item_positive": critical_item_positive,
            "subscale_scores": {},
        }
        if outcome == "administered"
        else None
    )
    path.write_text(
        json.dumps(
            {
                "outcome": outcome,
                "scale_name": scale_name if outcome == "administered" else None,
                "item_bank_version": "v1" if outcome == "administered" else None,
                "responses": [2] * 9 if outcome == "administered" else [],
                "score_result": score_result,
                "safety_referral": False,
                "administration_mode": "natural",
                "threshold_caveat": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _ledger_entry(
    session_index: int,
    conv_path: Path | None,
    di_path: Path | None,
    *,
    simulated_date: str = "2026-01-01",
    f3: dict | None = "__default__",  # type: ignore[assignment]
    survey_path: Path | None = None,
    outcome: str = "administered",
    scale_name: str = "PHQ-9",
    total_score: int = 15,
    safety_referral: bool = False,
    final_slots: dict[str, str] | None = None,
) -> dict:
    if f3 == "__default__":
        f3 = {
            "outcome": outcome,
            "scale_name": scale_name if outcome == "administered" else None,
            "administration_mode": "natural",
            "item_bank_version": "v1" if outcome == "administered" else None,
            "item_bank_provenance": "v1 test provenance" if outcome == "administered" else None,
            "responses": [2] * 9 if outcome == "administered" else [],
            "total_score": total_score if outcome == "administered" else None,
            "max_score": 27 if outcome == "administered" else None,
            "severity": "moderate" if outcome == "administered" else None,
            "subscale_scores": {},
            "safety_referral": safety_referral,
            "threshold_caveat": None,
            "safety_pathway": None,
            "answer_mode": "llm",
            "survey_artifact_path": str(survey_path) if survey_path else None,
            "scale_scores_path": None,
            "scenario_pack_id": None,
            "arc_mode": None,
        }
    return {
        "session_index": session_index,
        "simulated_date": simulated_date,
        "is_revisit": session_index > 1,
        "final_slots": final_slots if final_slots is not None else {"chief_complaint": "x"},
        "missing_slots": [],
        "repro": {"model": "m", "prompt_version": "v"},
        "conversation_path": str(conv_path) if conv_path else None,
        "domain_inference_path": str(di_path) if di_path else None,
        "f3": f3,
        "scenario_pack_id": None,
        "arc_mode": None,
        "written_at": "2026-01-01T00:00:00",
    }


def _write_temporal(tmp_path: Path, persona_id: str, *, ts: str = "20260101_120000") -> Path:
    from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput

    vp_dir = tmp_path / persona_id
    vp_dir.mkdir(parents=True, exist_ok=True)
    output = LongitudinalAnalysisOutput(
        vp_id=persona_id,
        n_sessions=2,
        ctrs_series=[
            CTRSSeriesPoint(session_index=1, simulated_date="2026-01-01", session_ctrs=4),
            CTRSSeriesPoint(session_index=2, simulated_date="2026-01-08", session_ctrs=4),
        ],
    )
    path = vp_dir / f"{persona_id}_{ts}_temporal.json"
    path.write_text(
        json.dumps(output.model_dump(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def _write_chart_png(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(path, format="PNG")


def _build_two_session_fixture(
    tmp_path: Path, persona_id: str = "VP-TEST", *, chart_keys: tuple[str, ...] = ()
) -> Path:
    """A complete, self-consistent 2-session ledger + F1/F2/F3/F4 artifact
    set — the happy-path fixture every "degrades gracefully" test above
    starts from and mutates one thing at a time."""
    ledger_path = ct._ledger_path(persona_id, tmp_path)
    for i, score in enumerate([20, 10], start=1):
        conv = _write_conversation(tmp_path, persona_id, i, simulated_date=f"2026-01-0{i}")
        di = _write_domain_inference(tmp_path, persona_id, i)
        survey = _write_survey(tmp_path, persona_id, i, total_score=score)
        ct._append_ledger_entry(
            ledger_path,
            _ledger_entry(
                i, conv, di, simulated_date=f"2026-01-0{i}",
                survey_path=survey, total_score=score,
            ),
        )
    temporal_path = _write_temporal(tmp_path, persona_id)
    for key in chart_keys:
        _write_chart_png(
            temporal_path.parent / f"{persona_id}_20260101_120000_temporal_{key}.png"
        )
    return temporal_path


# ── _build_f5_f3_administration ─────────────────────────────────────────


class TestBuildF5F3Administration:
    def test_backfills_critical_item_positive_from_survey_json(self, tmp_path: Path) -> None:
        survey = _write_survey(tmp_path, "VP-X", 1, critical_item_positive=True, total_score=22)
        entry = _ledger_entry(1, None, None, survey_path=survey, total_score=22)
        admin = ct._build_f5_f3_administration(entry)
        assert admin is not None
        assert admin.critical_item_positive is True
        assert admin.total_score == 22

    def test_no_f3_subobject_returns_none(self) -> None:
        entry = {"session_index": 1, "simulated_date": "2026-01-01", "f3": None}
        assert ct._build_f5_f3_administration(entry) is None

    def test_missing_survey_file_degrades_to_none_critical_item_positive(
        self, tmp_path: Path
    ) -> None:
        bogus = tmp_path / "nope_survey.json"
        entry = _ledger_entry(1, None, None, survey_path=bogus, total_score=10)
        admin = ct._build_f5_f3_administration(entry)
        assert admin is not None
        assert admin.critical_item_positive is None

    def test_unrecognized_outcome_returns_none(self) -> None:
        entry = _ledger_entry(1, None, None, f3={"outcome": "some_future_outcome"})
        assert ct._build_f5_f3_administration(entry) is None


# ── _build_f5_domain_inference_snapshot (ADR-038 Decision 2a, VAL-016) ──


class TestBuildF5DomainInferenceSnapshot:
    def test_validation_errors_present_threaded_true(self, tmp_path: Path) -> None:
        di_path = _write_domain_inference(
            tmp_path,
            "VP-X",
            1,
            department_candidates=[],
            validation_errors=[
                {
                    "type": "missing",
                    "loc": ["domain_candidates", 0, "evidence", 0, "source_id"],
                    "msg": "Field required",
                }
            ],
        )
        snap = ct._build_f5_domain_inference_snapshot(str(di_path))
        assert snap.validation_errors_present is True
        assert snap.department_candidates == ()

    def test_validation_errors_absent_threaded_false(self, tmp_path: Path) -> None:
        di_path = _write_domain_inference(tmp_path, "VP-X", 1)
        snap = ct._build_f5_domain_inference_snapshot(str(di_path))
        assert snap.validation_errors_present is False

    def test_validation_errors_empty_list_threaded_false(self, tmp_path: Path) -> None:
        """An explicit empty list is the same "no validation drop" fact as
        a wholly-absent field -- `bool([])` is `False`, matching the
        real-artifact convention (`validation_errors: null` when clean)."""
        di_path = _write_domain_inference(tmp_path, "VP-X", 1, validation_errors=[])
        snap = ct._build_f5_domain_inference_snapshot(str(di_path))
        assert snap.validation_errors_present is False

    def test_no_path_degrades_to_empty_snapshot_validation_errors_false(self) -> None:
        snap = ct._build_f5_domain_inference_snapshot(None)
        assert snap.ai_predicted_disease is None
        assert snap.department_candidates == ()
        assert snap.validation_errors_present is False


# ── _run_f5_report ────────────────────────────────────────────────────────


class TestRunF5Report:
    def test_explicit_temporal_path_beats_lexically_newer_stale_file(
        self, tmp_path: Path
    ) -> None:
        persona_id = "VP-EXACT-F4"
        current_path = _build_two_session_fixture(tmp_path, persona_id)
        stale_path = _write_temporal(tmp_path, persona_id, ts="99991231_235959")
        stale_data = json.loads(stale_path.read_text(encoding="utf-8"))
        stale_data["n_sessions"] = 99
        stale_path.write_text(json.dumps(stale_data), encoding="utf-8")

        paths = ct._run_f5_report(persona_id, tmp_path, current_path)

        markdown = paths["markdown"].read_text(encoding="utf-8")
        assert "(2세션" in markdown
        assert "(99세션" not in markdown

    def test_missing_exact_temporal_path_fails_without_glob_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        persona_id = "VP-MISSING-EXACT-F4"
        current_path = _build_two_session_fixture(tmp_path, persona_id)
        _write_temporal(tmp_path, persona_id, ts="99991231_235959")
        current_path.unlink()

        def _unexpected_glob(*_args, **_kwargs):
            raise AssertionError("live F5 must not search for a replacement temporal artifact")

        monkeypatch.setattr(ct, "_find_latest_f5_temporal_artifact", _unexpected_glob)

        with pytest.raises(FileNotFoundError, match=current_path.name):
            ct._run_f5_report(persona_id, tmp_path, current_path)

    def test_happy_path_builds_all_three_outputs(self, tmp_path: Path) -> None:
        temporal_path = _build_two_session_fixture(
            tmp_path, "VP-TEST",
            chart_keys=(
                "scales_ctrs_sentiment", "ctrs_zoom", "disease_similarity", "domain_confidence",
            ),
        )
        paths = ct._run_f5_report("VP-TEST", tmp_path, temporal_path)
        assert set(paths) == {"markdown", "pdf", "fhir"}
        for p in paths.values():
            assert p.exists()
            assert p.stat().st_size > 0

        from src.services.f5_report import validate_fhir_bundle

        bundle = json.loads(paths["fhir"].read_text(encoding="utf-8"))
        assert validate_fhir_bundle(bundle) == []

        md = paths["markdown"].read_text(encoding="utf-8")
        assert "scales_ctrs_sentiment" in md
        assert "disease_similarity" in md

    def test_all_sessions_slot_overview_built_from_ledger_final_slots(self, tmp_path: Path) -> None:
        """Task 1 (all-session slot maximization), full pipeline: each
        ledger entry's OWN `final_slots` field (never re-read from
        `conversation.json` — `_run_f5_report` sources it straight off the
        already-loaded ledger entries) feeds `SessionSlotSnapshot`, and the
        rendered markdown shows the change-history across sessions."""
        persona_id = "VP-SLOTHIST"
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        conv1 = _write_conversation(tmp_path, persona_id, 1, simulated_date="2026-01-01")
        di1 = _write_domain_inference(tmp_path, persona_id, 1)
        survey1 = _write_survey(tmp_path, persona_id, 1, total_score=20)
        ct._append_ledger_entry(
            ledger_path,
            _ledger_entry(
                1, conv1, di1, simulated_date="2026-01-01", survey_path=survey1,
                final_slots={"chief_complaint": "2주 전부터 불면"},
            ),
        )
        conv2 = _write_conversation(tmp_path, persona_id, 2, simulated_date="2026-01-08")
        di2 = _write_domain_inference(tmp_path, persona_id, 2)
        survey2 = _write_survey(tmp_path, persona_id, 2, total_score=10)
        ct._append_ledger_entry(
            ledger_path,
            _ledger_entry(
                2, conv2, di2, simulated_date="2026-01-08", survey_path=survey2,
                final_slots={"chief_complaint": "수면 개선 추세"},
            ),
        )
        temporal_path = _write_temporal(tmp_path, persona_id)

        paths = ct._run_f5_report(persona_id, tmp_path, temporal_path)
        md = paths["markdown"].read_text(encoding="utf-8")
        section = md.split("## 전체 세션 요약")[1].split("## 시행된 설문")[0]
        assert "S1: '2주 전부터 불면'" in section
        assert "S2: '수면 개선 추세'" in section
        assert "2회차" in section  # provenance for the LATEST value

    def test_validation_errors_flow_end_to_end_into_a7_disclosure(self, tmp_path: Path) -> None:
        """ADR-038 Decision 2a / VAL-016, full pipeline: a domain_inference
        artifact carrying validation_errors + empty department_candidates
        on the LATEST session must produce the validation-dropped wording
        (not a bare 정보 없음) in the rendered markdown. CVR-026 Finding 5
        (major): the internal ticket ID itself must NOT appear inline in
        the clinician-facing A7 body — only in the 각주 시스템 참고
        subsection (relocated, never dropped)."""
        persona_id = "VP-VALERR"
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        conv1 = _write_conversation(tmp_path, persona_id, 1, simulated_date="2026-01-01")
        di1 = _write_domain_inference(tmp_path, persona_id, 1)
        survey1 = _write_survey(tmp_path, persona_id, 1, total_score=20)
        ct._append_ledger_entry(
            ledger_path,
            _ledger_entry(1, conv1, di1, simulated_date="2026-01-01", survey_path=survey1),
        )
        conv2 = _write_conversation(tmp_path, persona_id, 2, simulated_date="2026-01-08")
        di2 = _write_domain_inference(
            tmp_path,
            persona_id,
            2,
            department_candidates=[],
            validation_errors=[
                {
                    "type": "missing",
                    "loc": ["domain_candidates", 0, "evidence", 0, "source_id"],
                    "msg": "Field required",
                }
            ],
        )
        survey2 = _write_survey(tmp_path, persona_id, 2, total_score=10)
        ct._append_ledger_entry(
            ledger_path,
            _ledger_entry(2, conv2, di2, simulated_date="2026-01-08", survey_path=survey2),
        )
        temporal_path = _write_temporal(tmp_path, persona_id)

        paths = ct._run_f5_report(persona_id, tmp_path, temporal_path)
        md = paths["markdown"].read_text(encoding="utf-8")
        a7_section = md.split("## 권장 진료과 및 후속 조치")[1].split("## 임상 종합 소견")[0]
        assert "VAL-016" not in a7_section  # internal ticket ID relocated, not inline
        assert "정보 없음 (권장 진료과 없음)" not in a7_section  # old bare wording gone
        assert "이번 실행에서는 진료과 후보가 산출되지 않았습니다" in a7_section  # honest KO note
        assert "VAL-016" in md.split("## 각주")[1]  # relocated, not dropped

    def test_fewer_than_2_ledger_entries_raises_insufficient_sessions(
        self, tmp_path: Path
    ) -> None:
        persona_id = "VP-SOLO"
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        conv = _write_conversation(tmp_path, persona_id, 1)
        ct._append_ledger_entry(ledger_path, _ledger_entry(1, conv, None))

        with pytest.raises(ct.F5InsufficientSessionsError, match="needs >=2"):
            ct._run_f5_report(persona_id, tmp_path, tmp_path / "unused-temporal.json")

    def test_missing_temporal_json_raises_named_failure_directing_to_f4(
        self, tmp_path: Path
    ) -> None:
        persona_id = "VP-NOF4"
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        for i in (1, 2):
            conv = _write_conversation(tmp_path, persona_id, i, simulated_date=f"2026-01-0{i}")
            di = _write_domain_inference(tmp_path, persona_id, i)
            ct._append_ledger_entry(
                ledger_path, _ledger_entry(i, conv, di, simulated_date=f"2026-01-0{i}")
            )
        # deliberately no *_temporal.json written this run

        missing_temporal_path = tmp_path / persona_id / "current_temporal.json"
        with pytest.raises(FileNotFoundError, match="run F4 first"):
            ct._run_f5_report(persona_id, tmp_path, missing_temporal_path)

    def test_missing_conversation_file_raises_named_failure(self, tmp_path: Path) -> None:
        persona_id = "VP-NOCONV"
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        conv1 = _write_conversation(tmp_path, persona_id, 1, simulated_date="2026-01-01")
        di1 = _write_domain_inference(tmp_path, persona_id, 1)
        ct._append_ledger_entry(
            ledger_path, _ledger_entry(1, conv1, di1, simulated_date="2026-01-01")
        )
        missing_conv = tmp_path / persona_id / "does_not_exist_conversation.json"
        ct._append_ledger_entry(
            ledger_path,
            _ledger_entry(2, missing_conv, None, simulated_date="2026-01-08"),
        )
        temporal_path = _write_temporal(tmp_path, persona_id)

        with pytest.raises(FileNotFoundError, match="conversation.json not found"):
            ct._run_f5_report(persona_id, tmp_path, temporal_path)

    def test_chart_missing_tolerance_only_present_charts_referenced(
        self, tmp_path: Path
    ) -> None:
        persona_id = "VP-CHARTS"
        temporal_path = _build_two_session_fixture(
            tmp_path, persona_id, chart_keys=("scales_ctrs_sentiment", "ctrs_zoom")
        )
        # disease_similarity / domain_confidence deliberately never written
        # (mirrors EXP-023 VP-003's own real gap, per the wave-1 handoff note).
        paths = ct._run_f5_report(persona_id, tmp_path, temporal_path)
        md = paths["markdown"].read_text(encoding="utf-8")
        assert "scales_ctrs_sentiment" in md
        assert "ctrs_zoom" in md
        assert "disease_similarity" not in md
        assert "domain_confidence" not in md
        assert "정보 없음 (차트 없음)" not in md  # 2 charts DID render, not the all-absent branch

    def test_no_charts_at_all_renders_absent_marker(self, tmp_path: Path) -> None:
        persona_id = "VP-NOCHARTS"
        temporal_path = _build_two_session_fixture(tmp_path, persona_id, chart_keys=())
        paths = ct._run_f5_report(persona_id, tmp_path, temporal_path)
        md = paths["markdown"].read_text(encoding="utf-8")
        assert "정보 없음 (차트 없음)" in md

    def test_f3_never_administered_persona_renders_a5_absent_marked(
        self, tmp_path: Path
    ) -> None:
        persona_id = "VP-NOF3"
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        for i in (1, 2):
            conv = _write_conversation(tmp_path, persona_id, i, simulated_date=f"2026-01-0{i}")
            di = _write_domain_inference(tmp_path, persona_id, i)
            ct._append_ledger_entry(
                ledger_path,
                _ledger_entry(
                    i, conv, di, simulated_date=f"2026-01-0{i}",
                    outcome="no_questionnaire_indicated",
                ),
            )
        temporal_path = _write_temporal(tmp_path, persona_id)

        paths = ct._run_f5_report(persona_id, tmp_path, temporal_path)
        md = paths["markdown"].read_text(encoding="utf-8")
        assert "정보 없음 (전체 세션 중 시행된 설문 없음)" in md

    def test_write_dir_overrides_where_output_lands_read_stays_at_out_dir(
        self, tmp_path: Path
    ) -> None:
        persona_id = "VP-SPLIT"
        temporal_path = _build_two_session_fixture(tmp_path, persona_id)
        write_dir = tmp_path / "elsewhere"
        paths = ct._run_f5_report(
            persona_id, tmp_path, temporal_path, write_dir=write_dir
        )
        for p in paths.values():
            assert p.exists()
            assert p.is_relative_to(write_dir)


# ── run_f5_stage (STAGE_REGISTRY entry point) ───────────────────────────


class TestRunF5Stage:
    @pytest.mark.asyncio
    async def test_fails_closed_when_exact_temporal_path_is_missing_even_with_stale_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        persona_id = "VP-STAGE-EXACT"
        current_path = _build_two_session_fixture(tmp_path, persona_id)
        _write_temporal(tmp_path, persona_id, ts="99991231_235959")
        current_path.unlink()

        def _unexpected_glob(*_args, **_kwargs):
            raise AssertionError("live F5 must not search for a replacement temporal artifact")

        monkeypatch.setattr(ct, "_find_latest_f5_temporal_artifact", _unexpected_glob)
        ctx = ct.ChainContext(
            persona_id=persona_id,
            max_turns=1,
            k=1,
            out_dir=tmp_path,
            scale_scores_path=None,
            f4_temporal_path=current_path,
        )

        result = await ct.run_f5_stage(ctx)

        assert result.status == "fail"
        assert current_path.name in result.detail

    @pytest.mark.asyncio
    async def test_skips_when_fewer_than_2_ledger_entries(self, tmp_path: Path) -> None:
        persona_id = "VP-SOLO2"
        conv = _write_conversation(tmp_path, persona_id, 1)
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        ct._append_ledger_entry(ledger_path, _ledger_entry(1, conv, None))

        ctx = ct.ChainContext(
            persona_id=persona_id,
            max_turns=1,
            k=1,
            out_dir=tmp_path,
            scale_scores_path=None,
            f4_temporal_path=tmp_path / "unused-temporal.json",
        )
        result = await ct.run_f5_stage(ctx)
        assert result.status == "skip"
        assert "needs >=2" in result.detail

    @pytest.mark.asyncio
    async def test_fails_named_when_temporal_json_missing(self, tmp_path: Path) -> None:
        persona_id = "VP-NOF4-2"
        ledger_path = ct._ledger_path(persona_id, tmp_path)
        for i in (1, 2):
            conv = _write_conversation(tmp_path, persona_id, i, simulated_date=f"2026-01-0{i}")
            ct._append_ledger_entry(
                ledger_path, _ledger_entry(i, conv, None, simulated_date=f"2026-01-0{i}")
            )

        ctx = ct.ChainContext(
            persona_id=persona_id,
            max_turns=1,
            k=1,
            out_dir=tmp_path,
            scale_scores_path=None,
            f4_temporal_path=tmp_path / persona_id / "current_temporal.json",
        )
        result = await ct.run_f5_stage(ctx)
        assert result.status == "fail"
        assert "run F4 first" in result.detail

    @pytest.mark.asyncio
    async def test_passes_and_writes_artifacts(self, tmp_path: Path) -> None:
        persona_id = "VP-STAGE-PASS"
        temporal_path = _build_two_session_fixture(tmp_path, persona_id)

        ctx = ct.ChainContext(
            persona_id=persona_id,
            max_turns=1,
            k=1,
            out_dir=tmp_path,
            scale_scores_path=None,
            f4_temporal_path=temporal_path,
        )
        result = await ct.run_f5_stage(ctx)
        assert result.status == "pass"
        assert set(result.artifacts) == {"markdown", "pdf", "fhir"}
        assert all(p.exists() for p in result.artifacts.values())

    @pytest.mark.asyncio
    async def test_stage_registry_f5_entry_is_implemented(self) -> None:
        f5_stage = next(s for s in ct.STAGE_REGISTRY if s.name == "F5")
        assert f5_stage.implemented is True
        assert f5_stage.run is ct.run_f5_stage


# ── Standalone replay CLI (`--f5-from-artifacts`) ───────────────────────


class TestF5ReplayCli:
    def test_resolves_temporal_history_once_and_passes_path_explicitly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        persona_id = "VP-REPLAY-RESOLVE"
        base = tmp_path / "artifacts_root"
        selected_path = _build_two_session_fixture(base, persona_id)
        artifacts_dir = base / persona_id
        resolved_paths: list[Path] = []
        report_paths: list[Path] = []

        def _resolve_once(candidate_persona_id: str, candidate_base: Path | None) -> Path:
            assert candidate_persona_id == persona_id
            assert candidate_base == base
            resolved_paths.append(selected_path)
            return selected_path

        def _report(
            candidate_persona_id: str,
            candidate_base: Path | None,
            f4_temporal_path: Path,
            *,
            write_dir: Path | None = None,
        ) -> dict[str, Path]:
            assert candidate_persona_id == persona_id
            assert candidate_base == base
            assert write_dir == base
            report_paths.append(f4_temporal_path)
            return {
                "markdown": artifacts_dir / "report.md",
                "pdf": artifacts_dir / "report.pdf",
                "fhir": artifacts_dir / "report.json",
            }

        monkeypatch.setattr(ct, "_find_latest_f5_temporal_artifact", _resolve_once)
        monkeypatch.setattr(ct, "_run_f5_report", _report)

        exit_code = ct._run_f5_replay_cli(artifacts_dir, out_dir=None)

        assert exit_code == 0
        assert resolved_paths == [selected_path]
        assert report_paths == [selected_path]

    def test_default_out_writes_into_artifacts_dir_itself(self, tmp_path: Path) -> None:
        persona_id = "VP-REPLAY"
        base = tmp_path / "artifacts_root"
        _build_two_session_fixture(base, persona_id)
        artifacts_dir = base / persona_id

        exit_code = ct._run_f5_replay_cli(artifacts_dir, out_dir=None)
        assert exit_code == 0
        produced = list(artifacts_dir.glob("*_handoff.md"))
        assert len(produced) == 1

    def test_explicit_out_writes_under_out_persona_subfolder(self, tmp_path: Path) -> None:
        persona_id = "VP-REPLAY2"
        base = tmp_path / "artifacts_root"
        _build_two_session_fixture(base, persona_id)
        artifacts_dir = base / persona_id
        out_dir = tmp_path / "scratch_out"

        exit_code = ct._run_f5_replay_cli(artifacts_dir, out_dir=out_dir)
        assert exit_code == 0
        produced = list((out_dir / persona_id).glob("*_handoff_fhir.json"))
        assert len(produced) == 1

    def test_nonexistent_artifacts_dir_returns_1(self, tmp_path: Path, capsys) -> None:
        exit_code = ct._run_f5_replay_cli(tmp_path / "does-not-exist", out_dir=None)
        assert exit_code == 1
        assert "not found" in capsys.readouterr().out

    def test_insufficient_sessions_reported_as_failure_not_traceback(
        self, tmp_path: Path, capsys
    ) -> None:
        persona_id = "VP-REPLAY-SOLO"
        base = tmp_path / "artifacts_root"
        conv = _write_conversation(base, persona_id, 1)
        ledger_path = ct._ledger_path(persona_id, base)
        ct._append_ledger_entry(ledger_path, _ledger_entry(1, conv, None))
        artifacts_dir = base / persona_id

        exit_code = ct._run_f5_replay_cli(artifacts_dir, out_dir=None)
        assert exit_code == 1
        assert "F5 replay failed" in capsys.readouterr().out


class TestCliF5FromArtifactsFlag:
    def test_default_is_none(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.f5_from_artifacts is None

    def test_override_sets_value(self) -> None:
        args = ct.build_arg_parser().parse_args(["--f5-from-artifacts", "/tmp/some/dir"])
        assert args.f5_from_artifacts == "/tmp/some/dir"


class TestF5ReplayCliSubprocess:
    """One real subprocess invocation of `python -m src.continuous_test
    --f5-from-artifacts ... --out ...` — proves the CLI wiring (argparse ->
    `_main` short-circuit -> `_run_f5_replay_cli`) end-to-end, not just the
    Python-level function call the other tests above exercise. Fully
    hermetic (synthetic `tmp_path` fixture, no `experiments/`/`docs/ai`
    dependency, no network)."""

    def test_subprocess_invocation_produces_outputs_in_out_dir(self, tmp_path: Path) -> None:
        persona_id = "VP-SUBPROC"
        base = tmp_path / "artifacts_root"
        _build_two_session_fixture(base, persona_id)
        artifacts_dir = base / persona_id
        out_dir = tmp_path / "subprocess_out"

        repo_ai_server = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable, "-m", "src.continuous_test",
                "--f5-from-artifacts", str(artifacts_dir),
                "--out", str(out_dir),
            ],
            cwd=str(repo_ai_server),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "F5 hand-off report complete" in result.stdout
        produced = list((out_dir / persona_id).glob("*_handoff.pdf"))
        assert len(produced) == 1


class TestF5ChainWiring:
    """Round-1 review blocker: with --sessions>1 F5 never ran (registry
    bypassed), and with --sessions 1 F5 ran BEFORE the session's own ledger
    entry existed. F5 must run from the post-ledger path after F4."""

    @staticmethod
    async def _fake_f1(persona_id, max_turns, followup_from=None, **kwargs):
        from src.f1 import F1Result

        session_index = kwargs["session_index"]
        return F1Result(
            session_id=f"f1_{persona_id}_s{session_index}",
            persona_id=persona_id,
            persona_name="테스트",
            session_index=session_index,
            is_revisit=session_index > 1,
            model="stub-model",
            prompt_version="v3",
            final_slots=[{"key": "chief_complaint", "value": "cc"}],
        )

    @pytest.mark.asyncio
    async def test_multi_session_runs_f5_after_f4_with_exact_json_path_over_complete_ledger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []
        ledger_len_at_f5_call: list[int] = []
        temporal_paths_at_f5_call: list[Path | None] = []
        f4_temporal_path = tmp_path / "current-multi-temporal.json"

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            conv_paths.append(_write_conversation(tmp_path, persona_id, session_index))
            return await TestF5ChainWiring._fake_f1(
                persona_id, max_turns, followup_from, **kwargs
            )

        async def _fake_run_f2_stage(f2_ctx):
            return ct.StageResult("F2", "pass", "ok")

        async def _fake_f4(persona_id, out_dir):
            return ct.StageResult(
                "F4", "pass", "ok", artifacts={"json": f4_temporal_path}
            )

        async def _fake_f5(f5_ctx):
            entries = json.loads(
                ct._ledger_path(f5_ctx.persona_id, f5_ctx.out_dir).read_text(encoding="utf-8")
            )
            ledger_len_at_f5_call.append(len(entries))
            temporal_paths_at_f5_call.append(f5_ctx.f4_temporal_path)
            return ct.StageResult("F5", "pass", "ok")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_run_f2_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])
        monkeypatch.setattr(ct, "_run_f4_analysis", _fake_f4)
        monkeypatch.setattr(ct, "run_f5_stage", _fake_f5)

        results = await ct.run_multi_session_chain(
            "VP-W1",
            n_sessions=2,
            max_turns=3,
            k=3,
            out_dir=tmp_path,
            scale_scores_path=None,
            answer_mode="expected",
            run_f4=True,
        )
        names = [r.name for r in results]
        assert "F5" in names, f"F5 stage never ran in multi-session chain: {names}"
        assert names.index("F5") > names.index("F4")
        assert ledger_len_at_f5_call == [2], (
            f"F5 must run over the COMPLETE 2-entry ledger, saw {ledger_len_at_f5_call}"
        )
        assert temporal_paths_at_f5_call == [f4_temporal_path]

    @pytest.mark.asyncio
    async def test_multi_session_skips_f5_when_f4_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            conv_paths.append(_write_conversation(tmp_path, persona_id, session_index))
            return await TestF5ChainWiring._fake_f1(
                persona_id, max_turns, followup_from, **kwargs
            )

        async def _fake_run_f2_stage(f2_ctx):
            return ct.StageResult("F2", "pass", "ok")

        async def _fake_f4_fail(persona_id, out_dir):
            return ct.StageResult("F4", "fail", "boom")

        f5_calls: list[str] = []

        async def _fake_f5(f5_ctx):
            f5_calls.append(f5_ctx.persona_id)
            return ct.StageResult("F5", "pass", "ok")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_run_f2_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])
        monkeypatch.setattr(ct, "_run_f4_analysis", _fake_f4_fail)
        monkeypatch.setattr(ct, "run_f5_stage", _fake_f5)

        results = await ct.run_multi_session_chain(
            "VP-W1B",
            n_sessions=1,
            max_turns=3,
            k=3,
            out_dir=tmp_path,
            scale_scores_path=None,
            answer_mode="expected",
            run_f4=True,
        )
        f5_results = [r for r in results if r.name == "F5"]
        assert f5_calls == [], "F5 must not execute when F4 failed"
        assert f5_results and f5_results[0].status == "skip"

    @pytest.mark.asyncio
    async def test_multi_session_skips_f5_when_f4_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # codex P1: F4 "warn" (fewer than 2 readable ledger entries) writes NO
        # fresh *_temporal.json, so F5 must be skipped — otherwise it would read
        # a STALE temporal from an earlier run and emit a passing report mixing
        # the current header with old longitudinal data.
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            conv_paths.append(_write_conversation(tmp_path, persona_id, session_index))
            return await TestF5ChainWiring._fake_f1(
                persona_id, max_turns, followup_from, **kwargs
            )

        async def _fake_run_f2_stage(f2_ctx):
            return ct.StageResult("F2", "pass", "ok")

        async def _fake_f4_warn(persona_id, out_dir):
            return ct.StageResult("F4", "warn", "only 1/2 ledger entries had readable artifacts")

        f5_calls: list[str] = []

        async def _fake_f5(f5_ctx):
            f5_calls.append(f5_ctx.persona_id)
            return ct.StageResult("F5", "pass", "ok")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_run_f2_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])
        monkeypatch.setattr(ct, "_run_f4_analysis", _fake_f4_warn)
        monkeypatch.setattr(ct, "run_f5_stage", _fake_f5)

        results = await ct.run_multi_session_chain(
            "VP-W1WARN",
            n_sessions=1,
            max_turns=3,
            k=3,
            out_dir=tmp_path,
            scale_scores_path=None,
            answer_mode="expected",
            run_f4=True,
        )
        f5_results = [r for r in results if r.name == "F5"]
        assert f5_calls == [], "F5 must not execute when F4 only warned (no fresh temporal)"
        assert f5_results and f5_results[0].status == "skip"

    @pytest.mark.asyncio
    async def test_single_session_runs_f4_then_passes_exact_json_path_to_f5_after_ledger_append(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Round-2 review blocker (codex): F4 and F5 both read the session
        ledger, so BOTH must run AFTER this session's entry is appended —
        otherwise F4's longitudinal window is one session short of, and
        inconsistent with, F5's header. Assert both observe the SAME complete
        (1-entry) ledger snapshot and are ordered F4 -> F5 -> F6."""
        import argparse

        conv_path = _write_conversation(tmp_path, "VP-W1S", 1)
        ledger_len_at_f4_call: list[int] = []
        ledger_len_at_f5_call: list[int] = []
        temporal_paths_at_f5_call: list[Path | None] = []
        f4_temporal_path = tmp_path / "current-single-temporal.json"
        captured: dict = {}

        async def _fake_run_chain(ctx, stages=None):
            ctx.conversation_path = conv_path
            stage_names = [s.name for s in (stages if stages is not None else ct.STAGE_REGISTRY)]
            assert "F4" not in stage_names and "F5" not in stage_names, (
                f"F4 and F5 must be deferred out of run_chain, got {stage_names}"
            )
            return [
                ct.StageResult(n, "pass" if n != "F6" else "skip", "ok") for n in stage_names
            ]

        async def _fake_f4(ctx):
            entries = json.loads(
                ct._ledger_path(ctx.persona_id, ctx.out_dir).read_text(encoding="utf-8")
            )
            ledger_len_at_f4_call.append(len(entries))
            return ct.StageResult(
                "F4", "pass", "ok", artifacts={"json": f4_temporal_path}
            )

        async def _fake_f5(f5_ctx):
            entries = json.loads(
                ct._ledger_path(f5_ctx.persona_id, f5_ctx.out_dir).read_text(encoding="utf-8")
            )
            ledger_len_at_f5_call.append(len(entries))
            temporal_paths_at_f5_call.append(f5_ctx.f4_temporal_path)
            return ct.StageResult("F5", "pass", "ok")

        monkeypatch.setattr(ct, "run_chain", _fake_run_chain)
        monkeypatch.setattr(ct, "run_f4_stage", _fake_f4)
        monkeypatch.setattr(ct, "run_f5_stage", _fake_f5)
        monkeypatch.setattr(
            ct, "print_report", lambda ctx, results: captured.update(results=results)
        )

        args = argparse.Namespace(
            persona="VP-W1S",
            sessions=1,
            max_turns=3,
            k=3,
            out=str(tmp_path),
            scale_scores=None,
            start_from_conversation=None,
            answer_mode="expected",
            force_questionnaire=None,
            patient_sex=None,
            scenario_pack=None,
            no_f4=False,
            f5_from_artifacts=None,
            session_interval_days=14,
        )
        rc = await ct._main(args)
        assert rc == 0
        assert ledger_len_at_f4_call == [1], (
            "F4 must run AFTER the single-session ledger entry is appended, "
            f"saw ledger lengths {ledger_len_at_f4_call}"
        )
        assert ledger_len_at_f5_call == [1], (
            "F5 must run AFTER the single-session ledger entry is appended, "
            f"saw ledger lengths {ledger_len_at_f5_call}"
        )
        assert ledger_len_at_f4_call == ledger_len_at_f5_call, (
            "F4 and F5 must observe the SAME ledger snapshot (codex consistency fix)"
        )
        assert temporal_paths_at_f5_call == [f4_temporal_path]
        names = [r.name for r in captured["results"]]
        assert "F4" in names and "F5" in names and "F6" in names
        assert names.index("F4") < names.index("F5") < names.index("F6")


class TestF5StagePartialExport:
    """Round-2 review blocker (codex): a PDF export failure inside
    save_f5_result must NOT be reported as a clean F5 pass. run_f5_stage
    surfaces it as 'warn' (md+FHIR still produced) so the report and the
    replay CLI can detect the missing clinical artifact."""

    @pytest.mark.asyncio
    async def test_run_f5_stage_warns_when_pdf_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        md = tmp_path / "VP-PDF_handoff.md"
        md.write_text("ok", encoding="utf-8")
        fhir = tmp_path / "VP-PDF_handoff_fhir.json"
        fhir.write_text("{}", encoding="utf-8")

        def _fake_report(persona_id, out_dir, f4_temporal_path, *, write_dir=None):
            return {"markdown": md, "fhir": fhir}

        monkeypatch.setattr(ct, "_run_f5_report", _fake_report)
        ctx = ct.ChainContext(
            persona_id="VP-PDF",
            max_turns=0,
            k=0,
            out_dir=tmp_path,
            scale_scores_path=None,
            f4_temporal_path=tmp_path / "current-temporal.json",
        )
        result = await ct.run_f5_stage(ctx)
        assert result.status == "warn"
        assert "PDF" in result.detail

    @pytest.mark.asyncio
    async def test_run_f5_stage_passes_when_all_artifacts_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        md = tmp_path / "VP-OK_handoff.md"
        md.write_text("ok", encoding="utf-8")

        def _fake_report(persona_id, out_dir, f4_temporal_path, *, write_dir=None):
            return {
                "markdown": md,
                "pdf": tmp_path / "VP-OK_handoff.pdf",
                "fhir": tmp_path / "VP-OK_handoff_fhir.json",
            }

        monkeypatch.setattr(ct, "_run_f5_report", _fake_report)
        ctx = ct.ChainContext(
            persona_id="VP-OK",
            max_turns=0,
            k=0,
            out_dir=tmp_path,
            scale_scores_path=None,
            f4_temporal_path=tmp_path / "current-temporal.json",
        )
        result = await ct.run_f5_stage(ctx)
        assert result.status == "pass"


class TestChainReturnCode:
    """codex P2: a partial F5 export (md/FHIR written, PDF missing → F5 'warn')
    must make the regular chain exit NONZERO (2), matching the replay CLI, so
    automation detects the missing clinical artifact even without a hard fail."""

    def test_partial_f5_export_exits_nonzero(self) -> None:
        results = [
            ct.StageResult("F1", "pass", "ok"),
            ct.StageResult("F5", "warn", "PDF export failed — md/FHIR written"),
        ]
        assert ct._chain_return_code(results) == 2

    def test_hard_fail_dominates_partial_export(self) -> None:
        results = [
            ct.StageResult("F5", "warn", "pdf missing"),
            ct.StageResult("F4", "fail", "boom"),
        ]
        assert ct._chain_return_code(results) == 1

    def test_clean_run_exits_zero(self) -> None:
        results = [ct.StageResult("F1", "pass", "ok"), ct.StageResult("F5", "pass", "ok")]
        assert ct._chain_return_code(results) == 0

    def test_benign_non_f5_warn_stays_zero(self) -> None:
        # An F4 'warn' (insufficient data) is not a missing artifact -> exit 0.
        results = [ct.StageResult("F4", "warn", "only 1/2 readable")]
        assert ct._chain_return_code(results) == 0
