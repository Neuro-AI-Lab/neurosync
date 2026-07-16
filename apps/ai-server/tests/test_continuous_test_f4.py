"""`src.continuous_test`'s F4 stage + scenario-pack threading —
`docs/ai/f4_quick_dev_plan.md`, `PLAN-2026-W29-D`, `ADR-036`. No live
LLM/DB anywhere in this file: F1 is monkeypatched (mirrors
`tests/test_continuous_test_f3.py`'s existing convention), F2/F3 are
stubbed trivially since this file's focus is F4 assembly + scenario-pack
threading, not F2/F3 machinery (already covered elsewhere).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.continuous_test as ct
from src.f1 import F1Result
from tests.simulation.scenario_pack import (
    VP_001_IMPROVEMENT_PLATEAU,
    VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT,
)


def _write_conversation(
    tmp_path: Path, persona_id: str, session_index: int, *,
    session_ctrs: int = 5, crisis_triggered: bool = False, turns: list[dict] | None = None,
    scenario_pack_id: str | None = None, arc_mode: str | None = None,
    probe_events: list[dict] | None = None, risk_floor: int | None = None,
    session_sentiment: dict | None = None,
) -> Path:
    vp_dir = tmp_path / persona_id
    vp_dir.mkdir(parents=True, exist_ok=True)
    path = vp_dir / f"{persona_id}_202601{session_index:02d}_000000_conversation.json"
    path.write_text(
        json.dumps({
            "session_id": f"f1_{persona_id}", "persona_id": persona_id,
            "session_ctrs": session_ctrs, "crisis_triggered": crisis_triggered, "crisis_turn": None,
            "probe_events": probe_events or [], "risk_floor": risk_floor,
            "turns": turns or [{"turn": 0, "sentiment": {"polarity": 0.1, "risk_signal": False}}],
            "session_sentiment": session_sentiment or {},
            "scenario_pack_id": scenario_pack_id, "arc_mode": arc_mode,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _write_domain_inference(tmp_path: Path, persona_id: str, session_index: int) -> Path:
    vp_dir = tmp_path / persona_id
    vp_dir.mkdir(parents=True, exist_ok=True)
    path = vp_dir / f"{persona_id}_202601{session_index:02d}_010000_domain_inference.json"
    path.write_text(
        json.dumps({
            "domain_candidates": [{"domain": "anxiety", "confidence": 0.6}],
            "ai_predicted_disease": {
                "candidates": [{"disease": "우울 삽화(우울증)", "similarity_score": 0.5}],
                "mode": "rag_live", "is_diagnostic": False,
                "recommended_questionnaire": "PHQ-9", "recommendation_caveat": None,
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _ledger_entry(
    session_index: int, conv_path: Path, di_path: Path | None, *,
    total_score: int | None = 10, administered: bool = True,
    scenario_pack_id: str | None = None, arc_mode: str | None = None,
) -> dict:
    return {
        "session_index": session_index, "simulated_date": f"2026-01-{session_index:02d}",
        "is_revisit": session_index > 1, "final_slots": {"chief_complaint": "x"},
        "missing_slots": [], "repro": {"model": "m", "prompt_version": "v"},
        "conversation_path": str(conv_path),
        "domain_inference_path": str(di_path) if di_path else None,
        "f3": {
            "outcome": "administered" if administered else "no_questionnaire_indicated",
            "scale_name": "PHQ-9" if administered else None,
            "total_score": total_score if administered else None,
            "max_score": 27, "severity": "moderate" if administered else None,
            "subscale_scores": {}, "safety_referral": False,
        },
        "scenario_pack_id": scenario_pack_id, "arc_mode": arc_mode,
        "written_at": "2026-01-01T00:00:00",
    }


class TestBuildSessionRecord:
    def test_reads_all_dims_from_artifacts(self, tmp_path: Path) -> None:
        conv = _write_conversation(
            tmp_path, "VP-001", 1, session_ctrs=4,
            scenario_pack_id="VP-001_improvement_plateau_s01",
            arc_mode="improvement_plateau",
            turns=[{"turn": 0, "sentiment": {"polarity": 0.2, "risk_signal": True}}],
        )
        di = _write_domain_inference(tmp_path, "VP-001", 1)
        entry = _ledger_entry(1, conv, di, scenario_pack_id="VP-001_improvement_plateau_s01",
                               arc_mode="improvement_plateau")
        record = ct._build_session_record(entry)
        assert record is not None
        assert record.session_ctrs == 4
        assert record.scenario_pack_id == "VP-001_improvement_plateau_s01"
        assert record.arc_mode == "improvement_plateau"
        assert record.turn_sentiment_polarities == [0.2]
        assert record.turn_risk_signal_count == 1
        assert record.domain_candidates == [{"domain": "anxiety", "confidence": 0.6}]
        assert record.f3 is not None and record.f3["total_score"] == 10

    def test_missing_conversation_path_returns_none(self) -> None:
        entry = {"session_index": 1, "simulated_date": "2026-01-01"}
        assert ct._build_session_record(entry) is None

    def test_nonexistent_conversation_file_returns_none(self, tmp_path: Path) -> None:
        entry = {
            "session_index": 1, "simulated_date": "2026-01-01",
            "conversation_path": str(tmp_path / "nope.json"),
        }
        assert ct._build_session_record(entry) is None

    def test_missing_domain_inference_degrades_gracefully(self, tmp_path: Path) -> None:
        conv = _write_conversation(tmp_path, "VP-001", 1)
        entry = _ledger_entry(1, conv, None)
        record = ct._build_session_record(entry)
        assert record is not None
        assert record.domain_candidates == []
        assert record.ai_predicted_disease is None


class TestRunF4Analysis:
    @pytest.mark.asyncio
    async def test_skips_when_fewer_than_2_ledger_entries(self, tmp_path: Path) -> None:
        conv = _write_conversation(tmp_path, "VP-001", 1)
        ledger_path = ct._ledger_path("VP-001", tmp_path)
        ct._append_ledger_entry(ledger_path, _ledger_entry(1, conv, None))

        result = await ct._run_f4_analysis("VP-001", tmp_path)
        assert result.status == "skip"
        assert "needs >=2" in result.detail

    @pytest.mark.asyncio
    async def test_passes_with_2_valid_entries_and_writes_artifacts(self, tmp_path: Path) -> None:
        ledger_path = ct._ledger_path("VP-001", tmp_path)
        for i, score in enumerate([15, 8], start=1):
            conv = _write_conversation(tmp_path, "VP-001", i)
            di = _write_domain_inference(tmp_path, "VP-001", i)
            ct._append_ledger_entry(ledger_path, _ledger_entry(i, conv, di, total_score=score))

        result = await ct._run_f4_analysis("VP-001", tmp_path)
        assert result.status == "pass"
        assert "overall_direction" in result.detail
        assert result.artifacts["json"].exists()
        saved = json.loads(result.artifacts["json"].read_text(encoding="utf-8"))
        # session_ctrs/sentiment are identical across both fixture sessions
        # (unchanged) -- only the PHQ-9 dimension itself carries a real
        # signal here, so assert on that TrendVerdict specifically rather
        # than the majority-vote overall_direction (which correctly reads
        # "unchanged" when only 1 of 3 voting dimensions improves).
        phq9_verdict = next(
            tv for tv in saved["trend_verdicts"] if tv["dimension"] == "phq9_total"
        )
        assert phq9_verdict["direction"] == "improved"

    @pytest.mark.asyncio
    async def test_warns_when_entries_present_but_artifacts_unreadable(
        self, tmp_path: Path
    ) -> None:
        ledger_path = ct._ledger_path("VP-001", tmp_path)
        ct._append_ledger_entry(
            ledger_path, {"session_index": 1, "simulated_date": "2026-01-01"}
        )
        ct._append_ledger_entry(
            ledger_path, {"session_index": 2, "simulated_date": "2026-01-08"}
        )
        result = await ct._run_f4_analysis("VP-001", tmp_path)
        assert result.status == "warn"

    @pytest.mark.asyncio
    async def test_run_f4_stage_delegates_to_run_f4_analysis(self, tmp_path: Path) -> None:
        ledger_path = ct._ledger_path("VP-001", tmp_path)
        for i, score in enumerate([20, 10], start=1):
            conv = _write_conversation(tmp_path, "VP-001", i)
            di = _write_domain_inference(tmp_path, "VP-001", i)
            ct._append_ledger_entry(ledger_path, _ledger_entry(i, conv, di, total_score=score))

        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path, scale_scores_path=None
        )
        result = await ct.run_f4_stage(ctx)
        assert result.status == "pass"


def _make_f1_result(session_index: int) -> F1Result:
    return F1Result(
        session_id=f"f1_VP-001_s{session_index}", persona_id="VP-001", persona_name="Test",
        session_index=session_index, is_revisit=session_index > 1,
        model="stub-model", prompt_version="v3",
        final_slots=[{"key": "chief_complaint", "value": "cc"}],
    )


class TestScenarioPackIsolationInvariantEndToEnd:
    """Isolation invariant, test-proven at the production seam
    (`f1._run_simulation`) — the exact call this session's F1 stage
    makes."""

    @pytest.mark.asyncio
    async def test_only_own_sessions_guideline_reaches_run_simulation_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_guidelines: list[str | None] = []
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            captured_guidelines.append(kwargs.get("scenario_guideline"))
            conv_path = _write_conversation(
                tmp_path, persona_id, session_index,
                scenario_pack_id=kwargs.get("scenario_pack_id"), arc_mode=kwargs.get("arc_mode"),
            )
            conv_paths.append(conv_path)
            return _make_f1_result(session_index)

        async def _fake_f2_stage(f2_ctx):
            return ct.StageResult("F2", "skip", "stubbed for this test")

        async def _fake_f3_stage(f2_ctx):
            return ct.StageResult("F3", "skip", "stubbed for this test")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_f2_stage)
        monkeypatch.setattr(ct, "run_f3_stage", _fake_f3_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        pack = VP_001_IMPROVEMENT_PLATEAU
        results = await ct.run_multi_session_chain(
            "VP-001", n_sessions=len(pack), max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, scenario_pack=pack, run_f4=False,
        )
        assert len(captured_guidelines) == 11
        assert all(g is not None for g in captured_guidelines)

        for i, session in enumerate(pack):
            own_text = captured_guidelines[i]
            assert own_text is not None
            assert session.state_descriptor_ko in own_text
            for other in pack:
                if other.session_index == session.session_index:
                    continue
                fragment = other.state_descriptor_ko[:24]
                assert fragment not in own_text, (
                    f"session {session.session_index}'s F1 call leaked session "
                    f"{other.session_index}'s content"
                )
        assert all(r.status != "fail" for r in results)

    @pytest.mark.asyncio
    async def test_natural_run_has_none_guideline_every_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_guidelines: list[str | None] = []
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            captured_guidelines.append(kwargs.get("scenario_guideline"))
            conv_path = _write_conversation(tmp_path, persona_id, session_index)
            conv_paths.append(conv_path)
            return _make_f1_result(session_index)

        async def _fake_f2_stage(f2_ctx):
            return ct.StageResult("F2", "skip", "stubbed")

        async def _fake_f3_stage(f2_ctx):
            return ct.StageResult("F3", "skip", "stubbed")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_f2_stage)
        monkeypatch.setattr(ct, "run_f3_stage", _fake_f3_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        await ct.run_multi_session_chain(
            "VP-001", n_sessions=2, max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, scenario_pack=None, run_f4=False,
        )
        assert captured_guidelines == [None, None]


class TestScenarioPackDateScheduling:
    @pytest.mark.asyncio
    async def test_day_offsets_from_pack_override_uniform_interval(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_dates: list[str] = []
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            captured_dates.append(kwargs["simulated_date"])
            conv_path = _write_conversation(tmp_path, persona_id, session_index)
            conv_paths.append(conv_path)
            return _make_f1_result(session_index)

        async def _fake_f2_stage(f2_ctx):
            return ct.StageResult("F2", "skip", "stubbed")

        async def _fake_f3_stage(f2_ctx):
            return ct.StageResult("F3", "skip", "stubbed")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_f2_stage)
        monkeypatch.setattr(ct, "run_f3_stage", _fake_f3_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        from datetime import date

        pack = VP_001_IMPROVEMENT_PLATEAU
        await ct.run_multi_session_chain(
            "VP-001", n_sessions=len(pack), max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, scenario_pack=pack, run_f4=False,
            base_date=date(2026, 1, 1),
        )
        expected = [
            (date(2026, 1, 1).toordinal() + s.day_offset) for s in pack
        ]
        from datetime import date as date_cls

        assert captured_dates == [date_cls.fromordinal(o).isoformat() for o in expected]
        # Non-uniform cadence proven directly: weekly early, monthly late.
        assert captured_dates[1] == "2026-01-08"  # +7
        assert captured_dates[-1] == "2026-07-03"  # +183

    @pytest.mark.asyncio
    async def test_mismatched_pack_length_raises(self, tmp_path: Path) -> None:
        pack = VP_001_IMPROVEMENT_PLATEAU
        with pytest.raises(ValueError, match="must match exactly"):
            await ct.run_multi_session_chain(
                "VP-001", n_sessions=3, max_turns=1, k=1, out_dir=tmp_path,
                scale_scores_path=None, scenario_pack=pack,
            )


class TestLedgerCarriesScenarioProvenance:
    @pytest.mark.asyncio
    async def test_ledger_entries_carry_scenario_pack_id_and_arc_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            conv_path = _write_conversation(
                tmp_path, persona_id, session_index,
                scenario_pack_id=kwargs.get("scenario_pack_id"), arc_mode=kwargs.get("arc_mode"),
            )
            conv_paths.append(conv_path)
            result = _make_f1_result(session_index)
            result.scenario_pack_id = kwargs.get("scenario_pack_id")
            result.arc_mode = kwargs.get("arc_mode")
            return result

        async def _fake_f2_stage(f2_ctx):
            return ct.StageResult("F2", "skip", "stubbed")

        async def _fake_f3_stage(f2_ctx):
            return ct.StageResult("F3", "skip", "stubbed")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_f2_stage)
        monkeypatch.setattr(ct, "run_f3_stage", _fake_f3_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        pack = VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT
        await ct.run_multi_session_chain(
            "VP-003", n_sessions=len(pack), max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, scenario_pack=pack, run_f4=False,
        )

        ledger_path = ct._ledger_path("VP-003", tmp_path)
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(entries) == 11
        for i, entry in enumerate(entries, start=1):
            assert entry["scenario_pack_id"] == f"VP-003_relapse_after_partial_improvement_s{i:02d}"
            assert entry["arc_mode"] == "relapse_after_partial_improvement"


class TestRunF4PostLoopStep:
    @pytest.mark.asyncio
    async def test_run_f4_true_by_default_appends_f4_stage_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []
        di_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            conv_path = _write_conversation(tmp_path, persona_id, session_index)
            conv_paths.append(conv_path)
            return _make_f1_result(session_index)

        async def _fake_f2_stage(f2_ctx):
            di_path = _write_domain_inference(tmp_path, f2_ctx.persona_id, len(di_paths) + 1)
            di_paths.append(di_path)
            f2_ctx.domain_inference_path = di_path
            return ct.StageResult("F2", "pass", "ok")

        async def _fake_f3_stage(f2_ctx):
            return ct.StageResult("F3", "skip", "stubbed")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_f2_stage)
        monkeypatch.setattr(ct, "run_f3_stage", _fake_f3_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        results = await ct.run_multi_session_chain(
            "VP-001", n_sessions=2, max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None,
        )
        assert results[-1].name == "F4"
        # F3 was stubbed to "skip" every session -> no "f3" ledger content ->
        # F4 assembly still runs (>=2 ledger entries exist) but with no
        # scale data -> "skip"/"warn"/"pass" are all acceptable non-crash
        # outcomes here; the key assertion is that F4 was invoked at all.
        assert results[-1].status in ("pass", "warn", "skip")

    @pytest.mark.asyncio
    async def test_run_f4_false_skips_post_loop_step(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            conv_path = _write_conversation(tmp_path, persona_id, session_index)
            conv_paths.append(conv_path)
            return _make_f1_result(session_index)

        async def _fake_f2_stage(f2_ctx):
            return ct.StageResult("F2", "skip", "stubbed")

        async def _fake_f3_stage(f2_ctx):
            return ct.StageResult("F3", "skip", "stubbed")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_f2_stage)
        monkeypatch.setattr(ct, "run_f3_stage", _fake_f3_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        results = await ct.run_multi_session_chain(
            "VP-001", n_sessions=2, max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, run_f4=False,
        )
        assert "F4" not in [r.name for r in results]


class TestCliScenarioPackFlag:
    def test_default_is_none(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.scenario_pack is None

    def test_override_vp001(self) -> None:
        args = ct.build_arg_parser().parse_args(["--scenario-pack", "VP-001"])
        assert args.scenario_pack == "VP-001"

    def test_invalid_choice_rejected(self) -> None:
        with pytest.raises(SystemExit):
            ct.build_arg_parser().parse_args(["--scenario-pack", "VP-999"])

    def test_all_registry_vps_accepted(self) -> None:
        from tests.simulation.scenario_pack import _SCENARIO_PACKS

        for vp_id in sorted(_SCENARIO_PACKS):
            args = ct.build_arg_parser().parse_args(["--scenario-pack", vp_id])
            assert args.scenario_pack == vp_id

    def test_no_f4_flag_default_false(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.no_f4 is False
