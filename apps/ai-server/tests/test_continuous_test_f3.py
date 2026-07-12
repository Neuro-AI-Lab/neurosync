"""`src.continuous_test`'s F3 stage — `docs/ai/f3_quick_dev_plan.md` §6,
ADR-032. No live LLM/DB anywhere in this file: `run_f3_stage` is exercised
against a synthetic `domain_inference.json` artifact with `--answer-mode
expected` (deterministic, reads a real repo persona file, zero LLM), and
`SurveyAnswerLLM`/live-K-EXAONE construction is monkeypatched out for the
`llm`-mode selection test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.continuous_test as ct
from src.f1 import F1Result


def _write_domain_inference_artifact(
    tmp_path: Path,
    *,
    persona_id: str = "VP-001",
    recommended_questionnaire: str | None = "PHQ-9",
) -> Path:
    persona_dir = tmp_path / persona_id
    persona_dir.mkdir(parents=True, exist_ok=True)
    path = persona_dir / f"{persona_id}_20260101_000000_domain_inference.json"
    path.write_text(
        json.dumps(
            {
                "session_id": f"{persona_id}_session",
                "persona_id": persona_id,
                "ai_predicted_disease": {
                    "candidates": [{"disease": "우울 삽화(우울증)", "similarity_score": 0.8}],
                    "mode": "rag_live",
                    "is_diagnostic": False,
                    "recommended_questionnaire": recommended_questionnaire,
                    "recommendation_caveat": None,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


class TestRunF3StageSkipWhenNoDomainInference:
    @pytest.mark.asyncio
    async def test_skips_when_domain_inference_path_is_none(self) -> None:
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "skip"
        assert "no domain_inference.json" in result.detail


class TestRunF3StageExpectedModeAdministered:
    @pytest.mark.asyncio
    async def test_administered_outcome_writes_survey_and_scale_scores(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_domain_inference_artifact(tmp_path, persona_id="VP-001")
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "outcome=administered" in result.detail
        assert "scale=PHQ-9" in result.detail
        assert ctx.f3_survey_path is not None and ctx.f3_survey_path.exists()
        assert ctx.f3_scale_scores_path is not None and ctx.f3_scale_scores_path.exists()

        saved = json.loads(ctx.f3_survey_path.read_text(encoding="utf-8"))
        assert saved["outcome"] == "administered"
        assert saved["scale_name"] == "PHQ-9"
        assert saved["answer_mode"] == "expected"
        assert sum(saved["responses"]) == 7  # VP-001 documented PHQ-9 total


class TestRunF3StageExpectedModeUnpopulated:
    @pytest.mark.asyncio
    async def test_unpopulated_outcome_never_calls_answer_fn(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire="GAD-7"
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        # VP-001 has no "### GAD-7 예상 항목별 점수" table — if this stage
        # accidentally tried to construct/call an expected_answer_fn for
        # GAD-7, it would raise. It must not.
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "outcome=item_bank_unpopulated" in result.detail
        assert ctx.f3_scale_scores_path is None


class TestRunF3StageNoQuestionnaireIndicated:
    @pytest.mark.asyncio
    async def test_no_questionnaire_outcome(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire=None
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "outcome=no_questionnaire_indicated" in result.detail
        assert ctx.f3_scale_scores_path is None


class TestRunF3StageLLMModeConstructsSurveyAnswerLLM:
    @pytest.mark.asyncio
    async def test_llm_mode_builds_survey_answer_llm_from_real_persona(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the `llm`-mode wiring calls `load_persona` +
        `SurveyAnswerLLM` (never `expected_answer_fn`) — the LLM call itself
        is mocked via `_ask` so no live K-EXAONE credentials/network are
        needed."""
        from unittest.mock import AsyncMock

        from tests.simulation import survey_answer_llm as sal_module

        original_init = sal_module.SurveyAnswerLLM.__init__

        def _patched_init(self, persona, api_key=None, base_url=None, model=None):
            original_init(self, persona, api_key="k", model="m")

        monkeypatch.setattr(sal_module.SurveyAnswerLLM, "__init__", _patched_init)
        monkeypatch.setattr(sal_module.SurveyAnswerLLM, "_ask", AsyncMock(return_value="1"))

        artifact_path = _write_domain_inference_artifact(tmp_path, persona_id="VP-001")
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="llm",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "outcome=administered" in result.detail
        saved = json.loads(ctx.f3_survey_path.read_text(encoding="utf-8"))
        assert saved["answer_mode"] == "llm"
        assert saved["responses"] == [1] * 9


class TestRunF3StageFailure:
    @pytest.mark.asyncio
    async def test_run_raising_is_reported_as_fail_not_crash(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "does_not_exist.json"
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=bad_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "fail"
        assert "F3 run raised" in result.detail


class TestBuildF3LedgerSubobject:
    def test_none_when_no_survey_path(self) -> None:
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=None, scale_scores_path=None
        )
        assert ct._build_f3_ledger_subobject(ctx) is None

    @pytest.mark.asyncio
    async def test_full_shape_for_administered_outcome(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(tmp_path, persona_id="VP-001")
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        await ct.run_f3_stage(ctx)
        sub = ct._build_f3_ledger_subobject(ctx)
        assert sub is not None
        expected_keys = {
            "outcome", "scale_name", "item_bank_version", "item_bank_provenance",
            "responses", "total_score", "max_score", "severity", "subscale_scores",
            "safety_referral", "answer_mode", "recommendation_provenance",
            "survey_artifact_path", "scale_scores_path",
        }
        assert set(sub.keys()) == expected_keys
        assert sub["outcome"] == "administered"
        assert sub["scale_name"] == "PHQ-9"
        assert sub["total_score"] == 7
        assert sub["scale_scores_path"] is not None

    @pytest.mark.asyncio
    async def test_present_with_null_score_fields_for_unpopulated_outcome(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire="GAD-7"
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        await ct.run_f3_stage(ctx)
        sub = ct._build_f3_ledger_subobject(ctx)
        assert sub is not None
        assert sub["outcome"] == "item_bank_unpopulated"
        assert sub["total_score"] is None
        assert sub["scale_scores_path"] is None


def _make_f1_result(session_index: int, *, final_slots: dict[str, str]) -> F1Result:
    return F1Result(
        session_id=f"f1_VP-001_s{session_index}", persona_id="VP-001", persona_name="Test",
        session_index=session_index, is_revisit=session_index > 1,
        model="stub-model", prompt_version="v3",
        final_slots=[{"key": k, "value": v} for k, v in final_slots.items()],
    )


class TestRunMultiSessionChainF3Integration:
    """`run_multi_session_chain` — F3 stage insertion + ledger "f3"
    sub-object + session-to-session scale_scores chaining (plan §6
    items 3/4)."""

    @pytest.mark.asyncio
    async def test_f3_stage_appears_and_ledger_carries_f3_subobject(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            vp_dir = tmp_path / persona_id
            vp_dir.mkdir(parents=True, exist_ok=True)
            conv_path = vp_dir / f"{persona_id}_2026010{session_index}_000000_conversation.json"
            conv_path.write_text("{}", encoding="utf-8")
            conv_paths.append(conv_path)
            return _make_f1_result(session_index, final_slots={"chief_complaint": "cc"})

        async def _fake_run_f2_stage(f2_ctx):
            f2_ctx.domain_inference_path = _write_domain_inference_artifact(
                tmp_path, persona_id="VP-001",
                recommended_questionnaire="PHQ-9" if f2_ctx.persona_id == "VP-001" else None,
            )
            return ct.StageResult("F2", "pass", "ok", artifacts={})

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_run_f2_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        results = await ct.run_multi_session_chain(
            "VP-001", n_sessions=1, max_turns=3, k=3, out_dir=tmp_path,
            scale_scores_path=None, answer_mode="expected",
        )
        assert [r.name for r in results] == ["F1[session=1]", "F2[session=1]", "F3[session=1]"]
        assert results[2].status == "pass"

        ledger_path = ct._ledger_path("VP-001", tmp_path)
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["f3"] is not None
        assert entries[0]["f3"]["outcome"] == "administered"
        assert entries[0]["f3"]["total_score"] == 7

    @pytest.mark.asyncio
    async def test_session2_f2_receives_session1_f3_scale_scores_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Closes the plan §6 item 4 gap: session 2's F2 call must receive
        session 1's OWN F3 scale_scores.json, not the (here: absent) static
        CLI arg."""
        conv_paths: list[Path] = []
        f2_scale_scores_args: list[str | None] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            vp_dir = tmp_path / persona_id
            vp_dir.mkdir(parents=True, exist_ok=True)
            conv_path = vp_dir / f"{persona_id}_2026010{session_index}_000000_conversation.json"
            conv_path.write_text("{}", encoding="utf-8")
            conv_paths.append(conv_path)
            return _make_f1_result(session_index, final_slots={"chief_complaint": "cc"})

        async def _fake_run_f2_stage(f2_ctx):
            f2_scale_scores_args.append(f2_ctx.scale_scores_path)
            f2_ctx.domain_inference_path = _write_domain_inference_artifact(
                tmp_path, persona_id="VP-001", recommended_questionnaire="PHQ-9"
            )
            return ct.StageResult("F2", "pass", "ok", artifacts={})

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_run_f2_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        await ct.run_multi_session_chain(
            "VP-001", n_sessions=2, max_turns=3, k=3, out_dir=tmp_path,
            scale_scores_path="/static/cli-arg-scores.json", answer_mode="expected",
        )

        assert f2_scale_scores_args[0] == "/static/cli-arg-scores.json"  # session 1: static arg
        # session 2: session 1's OWN F3 scale_scores.json (never the static arg).
        assert f2_scale_scores_args[1] is not None
        assert f2_scale_scores_args[1] != "/static/cli-arg-scores.json"
        assert f2_scale_scores_args[1].endswith("_scale_scores.json")
        assert Path(f2_scale_scores_args[1]).exists()

    @pytest.mark.asyncio
    async def test_falls_back_to_static_arg_when_prior_session_not_administered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_paths: list[Path] = []
        f2_scale_scores_args: list[str | None] = []

        async def _fake_run_simulation(persona_id, max_turns, followup_from=None, **kwargs):
            session_index = kwargs["session_index"]
            vp_dir = tmp_path / persona_id
            vp_dir.mkdir(parents=True, exist_ok=True)
            conv_path = vp_dir / f"{persona_id}_2026010{session_index}_000000_conversation.json"
            conv_path.write_text("{}", encoding="utf-8")
            conv_paths.append(conv_path)
            return _make_f1_result(session_index, final_slots={"chief_complaint": "cc"})

        async def _fake_run_f2_stage(f2_ctx):
            f2_scale_scores_args.append(f2_ctx.scale_scores_path)
            # Every session: NO recommendation -> F3 outcome=no_questionnaire_indicated
            # -> no scale_scores.json produced.
            f2_ctx.domain_inference_path = _write_domain_inference_artifact(
                tmp_path, persona_id="VP-001", recommended_questionnaire=None
            )
            return ct.StageResult("F2", "pass", "ok", artifacts={})

        import src.f1 as f1_module

        monkeypatch.setattr(f1_module, "_run_simulation", _fake_run_simulation)
        monkeypatch.setattr(ct, "run_f2_stage", _fake_run_f2_stage)
        monkeypatch.setattr(ct, "_find_latest_f1_conversation", lambda persona_id: conv_paths[-1])

        await ct.run_multi_session_chain(
            "VP-001", n_sessions=2, max_turns=3, k=3, out_dir=tmp_path,
            scale_scores_path="/static/cli-arg-scores.json", answer_mode="expected",
        )

        assert f2_scale_scores_args == [
            "/static/cli-arg-scores.json", "/static/cli-arg-scores.json",
        ]


class TestSingleSessionLedgerGapFix:
    """`run_chain` (`--sessions 1` path via `_main`) previously wrote no
    ledger entry at all (plan §6 item 5) — now it does."""

    @pytest.mark.asyncio
    async def test_main_writes_single_session_ledger_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = tmp_path / "VP-001" / "VP-001_20260101_000000_conversation.json"
        conv_path.parent.mkdir(parents=True, exist_ok=True)
        conv_path.write_text(
            json.dumps(
                {
                    "final_slots": [{"key": "chief_complaint", "value": "불안감"}],
                    "model": "stub", "prompt_version": "v3",
                }
            ),
            encoding="utf-8",
        )
        artifact_path = _write_domain_inference_artifact(tmp_path, persona_id="VP-001")

        async def _fake_run_f1_stage(ctx):
            ctx.conversation_path = conv_path
            return ct.StageResult("F1", "pass", "ok", artifacts={"conversation": conv_path})

        async def _fake_run_f2_stage(ctx):
            ctx.domain_inference_path = artifact_path
            return ct.StageResult("F2", "pass", "ok", artifacts={"domain_inference": artifact_path})

        monkeypatch.setattr(
            ct, "STAGE_REGISTRY",
            [
                ct.Stage("F1", True, _fake_run_f1_stage),
                ct.Stage("F2", True, _fake_run_f2_stage),
                ct.Stage("F3", True, ct.run_f3_stage),
            ],
        )

        args = ct.build_arg_parser().parse_args(
            ["--persona", "VP-001", "--out", str(tmp_path), "--answer-mode", "expected"]
        )
        rc = await ct._main(args)
        assert rc == 0

        ledger_path = ct._ledger_path("VP-001", tmp_path)
        assert ledger_path.exists()
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["session_index"] == 1
        assert entries[0]["is_revisit"] is False
        assert entries[0]["final_slots"] == {"chief_complaint": "불안감"}
        assert entries[0]["f3"] is not None
        assert entries[0]["f3"]["outcome"] == "administered"

    @pytest.mark.asyncio
    async def test_no_ledger_entry_when_f1_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _failing_f1_stage(ctx):
            return ct.StageResult("F1", "fail", "boom")

        monkeypatch.setattr(
            ct, "STAGE_REGISTRY", [ct.Stage("F1", True, _failing_f1_stage)]
        )
        args = ct.build_arg_parser().parse_args(["--persona", "VP-001", "--out", str(tmp_path)])
        rc = await ct._main(args)
        assert rc == 1
        assert not ct._ledger_path("VP-001", tmp_path).exists()


class TestCliAnswerModeFlag:
    def test_default_is_llm(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.answer_mode == "llm"

    def test_override_expected(self) -> None:
        args = ct.build_arg_parser().parse_args(["--answer-mode", "expected"])
        assert args.answer_mode == "expected"

    def test_invalid_choice_rejected(self) -> None:
        with pytest.raises(SystemExit):
            ct.build_arg_parser().parse_args(["--answer-mode", "bogus"])
