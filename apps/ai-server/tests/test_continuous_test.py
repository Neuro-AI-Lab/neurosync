"""src.continuous_test — structure/import smoke tests (Track C harness).

No live DB/LLM anywhere in this file (mirrors `test_f2_pipeline.py`'s C-4
mock-based constraint) — this only proves the module imports cleanly, the
stage registry is correctly shaped (F1-F5 real, F6 an explicit logged skip
stub), the chain runner's skip/halt-on-fail semantics work end to end on
synthetic stages, the CLI parses as documented, and the DSN-masking helper
never leaks a password. The live F1->F2->F3 chain run is out of scope here
(experiment-tracker's job, behind the mandatory gates). F3's own stage
behavior (`run_f3_stage`, ledger `"f3"` sub-object, session chaining) is
covered in `tests/test_continuous_test_f3.py`; F5's own stage behavior
(`run_f5_stage`, `--f5-from-artifacts` replay CLI) is covered in
`tests/test_continuous_test_f5.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.continuous_test as ct


class TestStageRegistryShape:
    def test_f1_through_f5_are_implemented(self) -> None:
        """F4 flips to implemented once `src/f4.py` ships (`PLAN-2026-W29-D`,
        `ADR-036`); F5 flips once `src/f5.py` ships (`PLAN-2026-W29-E`,
        `ADR-037`) — the exact extension seam `STAGE_REGISTRY`'s own
        docstring describes."""
        by_name = {s.name: s for s in ct.STAGE_REGISTRY}
        for name in ("F1", "F2", "F3", "F4", "F5"):
            assert by_name[name].implemented is True
            assert callable(by_name[name].run)

    def test_f6_is_an_explicit_logged_skip_stub(self) -> None:
        by_name = {s.name: s for s in ct.STAGE_REGISTRY}
        stage = by_name["F6"]
        assert stage.implemented is False
        assert stage.run is None
        assert stage.note, "F6 must carry a non-empty explanatory note (never silent)"

    def test_registry_order_is_f1_through_f6(self) -> None:
        assert [s.name for s in ct.STAGE_REGISTRY] == ["F1", "F2", "F3", "F4", "F5", "F6"]


class TestRunChainSkipAndHaltSemantics:
    """Chain runner logic on synthetic stages — no real F1/F2 involved."""

    @pytest.mark.asyncio
    async def test_all_implemented_stages_pass(self) -> None:
        async def _ok(ctx: ct.ChainContext) -> ct.StageResult:
            return ct.StageResult("A", "pass", "ok")

        async def _ok2(ctx: ct.ChainContext) -> ct.StageResult:
            return ct.StageResult("B", "pass", "ok")

        stages = [ct.Stage("A", True, _ok), ct.Stage("B", True, _ok2)]
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None
        )
        results = await ct.run_chain(ctx, stages)
        assert [r.status for r in results] == ["pass", "pass"]

    @pytest.mark.asyncio
    async def test_unimplemented_stage_never_silently_dropped(self) -> None:
        stages = [
            ct.Stage("A", False, None, note="not built yet"),
        ]
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None
        )
        results = await ct.run_chain(ctx, stages)
        assert len(results) == 1
        assert results[0].status == "skip"
        assert "not built yet" in results[0].detail

    @pytest.mark.asyncio
    async def test_failure_halts_chain_and_marks_downstream_skip(self) -> None:
        async def _fail(ctx: ct.ChainContext) -> ct.StageResult:
            return ct.StageResult("A", "fail", "boom")

        async def _never_called(ctx: ct.ChainContext) -> ct.StageResult:
            raise AssertionError("downstream stage must not run after a hard failure")

        stages = [
            ct.Stage("A", True, _fail),
            ct.Stage("B", True, _never_called),
            ct.Stage("C", False, None, note="also unimplemented"),
        ]
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None
        )
        results = await ct.run_chain(ctx, stages)
        assert [r.status for r in results] == ["fail", "skip", "skip"]
        assert "upstream stage failed" in results[1].detail

    @pytest.mark.asyncio
    async def test_warn_status_does_not_halt_chain(self) -> None:
        async def _warn(ctx: ct.ChainContext) -> ct.StageResult:
            return ct.StageResult("A", "warn", "db outage masked as llm_only")

        async def _still_runs(ctx: ct.ChainContext) -> ct.StageResult:
            return ct.StageResult("B", "pass", "ran fine")

        stages = [ct.Stage("A", True, _warn), ct.Stage("B", True, _still_runs)]
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None
        )
        results = await ct.run_chain(ctx, stages)
        assert [r.status for r in results] == ["warn", "pass"]


class TestF1StageSkipsWhenPreseeded:
    """--start-from-conversation path: F1 stage must not attempt a live run
    when ctx.conversation_path is already populated."""

    @pytest.mark.asyncio
    async def test_f1_stage_skips_live_run_when_conversation_preseeded(
        self, tmp_path: Path
    ) -> None:
        fake_conv = tmp_path / "fake_conversation.json"
        fake_conv.write_text("{}", encoding="utf-8")
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None,
            conversation_path=fake_conv,
        )
        result = await ct.run_f1_stage(ctx)
        assert result.status == "skip"
        assert "start-from-conversation" in result.detail


class TestF2StageSkipsWithoutUpstreamConversation:
    @pytest.mark.asyncio
    async def test_f2_stage_skips_when_no_conversation_path(self) -> None:
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None
        )
        result = await ct.run_f2_stage(ctx)
        assert result.status == "skip"
        assert "no F1 conversation.json" in result.detail


class TestArtifactGlobHelpers:
    def test_find_latest_f2_artifact_picks_newest_by_sorted_glob(self, tmp_path: Path) -> None:
        persona_dir = tmp_path / "VP-001"
        persona_dir.mkdir()
        older = persona_dir / "VP-001_20260101_000000_domain_inference.json"
        newer = persona_dir / "VP-001_20260102_000000_domain_inference.json"
        older.write_text("{}", encoding="utf-8")
        newer.write_text("{}", encoding="utf-8")

        found = ct._find_latest_f2_artifact("VP-001", tmp_path)
        assert found == newer

    def test_find_latest_f2_artifact_none_when_missing(self, tmp_path: Path) -> None:
        assert ct._find_latest_f2_artifact("VP-999", tmp_path) is None

    def test_read_f2_mode_extracts_repro_mode(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.json"
        path.write_text('{"repro": {"mode": "rag"}}', encoding="utf-8")
        assert ct._read_f2_mode(path) == "rag"

    def test_read_f2_mode_unknown_on_malformed_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        assert ct._read_f2_mode(path) == "unknown"


class TestMaskDsnNeverLeaksPassword:
    def test_password_is_masked(self) -> None:
        masked = ct._mask_dsn("postgresql+asyncpg://neurosync:s3cr3t@223.194.33.26:28881/neurosync")
        assert "s3cr3t" not in masked
        assert "***" in masked
        assert "neurosync" in masked  # username/db name are not secrets

    def test_dsn_without_password_is_returned_as_is(self) -> None:
        masked = ct._mask_dsn("postgresql+asyncpg://localhost:5432/neurosync")
        assert masked == "postgresql+asyncpg://localhost:5432/neurosync"

    def test_unparseable_dsn_does_not_raise(self) -> None:
        # Must degrade gracefully, never crash the harness over a log line.
        assert ct._mask_dsn("::::not a url::::") is not None


class TestCliArgParsing:
    def test_defaults(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.persona == "VP-001"
        assert args.max_turns == 10
        assert args.k == 3
        assert args.out is None
        assert args.scale_scores is None
        assert args.start_from_conversation is None

    def test_overrides(self) -> None:
        args = ct.build_arg_parser().parse_args(
            [
                "--persona", "VP-003",
                "--max-turns", "6",
                "--k", "5",
                "--out", "/tmp/out",
                "--scale-scores", "/tmp/scores.json",
                "--start-from-conversation", "/tmp/conv.json",
            ]
        )
        assert args.persona == "VP-003"
        assert args.max_turns == 6
        assert args.k == 5
        assert args.out == "/tmp/out"
        assert args.scale_scores == "/tmp/scores.json"
        assert args.start_from_conversation == "/tmp/conv.json"


class TestMainRejectsMissingStartFromConversationPath:
    @pytest.mark.asyncio
    async def test_missing_path_returns_1_without_running_stages(self, tmp_path: Path) -> None:
        args = ct.build_arg_parser().parse_args(
            ["--persona", "VP-001", "--start-from-conversation", str(tmp_path / "nope.json")]
        )
        rc = await ct._main(args)
        assert rc == 1
