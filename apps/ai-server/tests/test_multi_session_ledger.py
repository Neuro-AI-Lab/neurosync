"""PLAN-2026-W28-Q W2 (plan §3 "Multi-session + question induction"):
per-VP append-only session ledger + `continuous_test.py` multi-session
chaining.

No live DB/LLM (mirrors `test_continuous_test.py`'s own C-4 mock-based
constraint) — `f1._run_simulation`/`run_f2_stage` are monkeypatched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.continuous_test as ct
from src.f1 import F1Result


class TestLedgerPath:
    def test_ledger_path_naming_convention(self, tmp_path: Path) -> None:
        path = ct._ledger_path("VP-001", tmp_path)
        assert path == tmp_path / "VP-001" / "VP-001_session_ledger.json"


class TestLoadAndAppendLedgerEntry:
    def test_missing_file_loads_empty_list(self, tmp_path: Path) -> None:
        assert ct._load_ledger(tmp_path / "nope.json") == []

    def test_corrupt_file_loads_empty_list_not_crash(self, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.json"
        path.write_text("not json{{{", encoding="utf-8")
        assert ct._load_ledger(path) == []

    def test_append_creates_parent_dirs_and_is_append_only(self, tmp_path: Path) -> None:
        path = tmp_path / "VP-001" / "VP-001_session_ledger.json"
        assert not path.parent.exists()

        ct._append_ledger_entry(path, {"session_index": 1})
        ct._append_ledger_entry(path, {"session_index": 2})

        entries = json.loads(path.read_text(encoding="utf-8"))
        assert [e["session_index"] for e in entries] == [1, 2]


def _make_f1_result(
    session_index: int, *, final_slots: dict[str, str], is_revisit: bool
) -> F1Result:
    return F1Result(
        session_id=f"f1_VP-001_s{session_index}",
        persona_id="VP-001",
        persona_name="Test",
        session_index=session_index,
        is_revisit=is_revisit,
        model="stub-model",
        prompt_version="v3",
        final_slots=[{"key": k, "value": v} for k, v in final_slots.items()],
    )


class TestRunMultiSessionChain:
    @pytest.mark.asyncio
    async def test_two_sessions_chain_via_followup_seam_and_write_ledger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []
        followup_args: list[str | None] = []

        async def _fake_run_simulation(
            persona_id, max_turns, followup_from=None, **kwargs
        ):
            followup_args.append(followup_from)
            session_index = kwargs["session_index"]
            vp_dir = tmp_path / persona_id
            vp_dir.mkdir(parents=True, exist_ok=True)
            conv_path = vp_dir / f"{persona_id}_2026010{session_index}_000000_conversation.json"
            conv_path.write_text("{}", encoding="utf-8")
            conv_paths.append(conv_path)
            return _make_f1_result(
                session_index,
                final_slots={"chief_complaint": f"session {session_index} cc"},
                is_revisit=session_index > 1,
            )

        async def _fake_run_f2_stage(f2_ctx):
            return ct.StageResult("F2", "pass", "ok", artifacts={})

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_run_f2_stage)
        monkeypatch.setattr(
            ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1]
        )

        results = await ct.run_multi_session_chain(
            "VP-001", n_sessions=2, max_turns=3, k=3, out_dir=tmp_path,
            scale_scores_path=None,
        )

        # F3 stage is now real (PLAN-2026-W28-V) — the fake F2 stage above
        # never sets f2_ctx.domain_inference_path, so F3 "skip"s each
        # session (no upstream artifact to read); it is still one
        # StageResult per session, never silently dropped.
        assert [r.status for r in results] == ["pass", "pass", "skip", "pass", "pass", "skip"]
        assert [r.name for r in results] == [
            "F1[session=1]", "F2[session=1]", "F3[session=1]",
            "F1[session=2]", "F2[session=2]", "F3[session=2]",
        ]
        # session 1 has no followup; session 2 follows up from session 1's
        # OWN saved artifact path (never a "latest for persona" lookup).
        assert followup_args == [None, str(conv_paths[0])]

        ledger_path = ct._ledger_path("VP-001", tmp_path)
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert [e["session_index"] for e in entries] == [1, 2]
        assert [e["is_revisit"] for e in entries] == [False, True]
        assert entries[0]["final_slots"] == {"chief_complaint": "session 1 cc"}
        assert entries[1]["missing_slots"], "session 2 should report some missing slots"
        assert entries[0]["repro"] == {"model": "stub-model", "prompt_version": "v3"}
        # F3 stage never produced a survey.json this test (no domain_inference
        # artifact) — the ledger key is present with a null value, never absent.
        assert "f3" in entries[0] and entries[0]["f3"] is None

    @pytest.mark.asyncio
    async def test_f1_failure_halts_chain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _failing_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            raise RuntimeError("boom")

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _failing_run_simulation)

        results = await ct.run_multi_session_chain(
            "VP-001", n_sessions=3, max_turns=3, k=3, out_dir=tmp_path,
            scale_scores_path=None,
        )

        assert len(results) == 1
        assert results[0].status == "fail"
        assert not ct._ledger_path("VP-001", tmp_path).exists()


class TestCliSessionsFlag:
    def test_defaults(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.sessions == 1
        assert args.session_interval_days == ct.DEFAULT_SESSION_INTERVAL_DAYS

    def test_overrides(self) -> None:
        args = ct.build_arg_parser().parse_args(
            ["--sessions", "3", "--session-interval-days", "7"]
        )
        assert args.sessions == 3
        assert args.session_interval_days == 7

    @pytest.mark.asyncio
    async def test_sessions_and_start_from_conversation_are_mutually_exclusive(
        self, tmp_path: Path
    ) -> None:
        conv = tmp_path / "conv.json"
        conv.write_text("{}", encoding="utf-8")
        args = ct.build_arg_parser().parse_args(
            ["--sessions", "2", "--start-from-conversation", str(conv)]
        )
        rc = await ct._main(args)
        assert rc == 1


class TestProductionNeverReadsLedger:
    """AVC-03 (`docs/ai/validation_plan_f1f2_continuous.md` §6) / REV-022
    standing rule: no production module (f1.py, f2.py, f3.py) references the
    session ledger."""

    def test_f1_f2_f3_never_reference_session_ledger(self) -> None:
        repo_src = Path(__file__).resolve().parents[1] / "src"
        for name in ("f1.py", "f2.py", "f3.py"):
            source = (repo_src / name).read_text(encoding="utf-8")
            assert "session_ledger" not in source, (
                f"{name} references the harness-only session ledger — REV-022 finding"
            )
