"""`src.continuous_test`'s F3 stage — `_archive/plans/f3_quick_dev_plan.md` §6,
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
import src.f3 as f3
from src.f1 import F1Result


def _write_domain_inference_artifact(
    tmp_path: Path,
    *,
    persona_id: str = "VP-001",
    recommended_questionnaire: str | None = "PHQ-9",
    crisis_triggered: bool = False,
    session_ctrs: int | None = None,
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
                # CVR-028 Finding 1 safety-net wiring.
                "crisis_triggered": crisis_triggered,
                "session_ctrs": session_ctrs,
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
        # WHO-5 is item bank v1's only remaining unpopulated scale
        # (PLAN-2026-W29-A) — GAD-7/PHQ-4/AUDIT-C are populated now.
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire="WHO-5"
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        # If this stage accidentally tried to construct/call an
        # expected_answer_fn for an unpopulated scale, `_build_survey_answer_fn`
        # would only ever be reached for outcome=="administered" — this
        # proves it never is for WHO-5.
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


class TestRunF3StageSafetyNetCvr028:
    """CVR-028 Finding 1 at the harness (F2->F3 chain) consumption seam —
    proves the same `f3.resolve_effective_scale` seam `run_f3_administration`
    uses is also what `run_f3_stage`'s own pre-computation (needed to build
    `answer_fn` before the F3 call) resolves against, so the two never
    disagree about which outcome/scale this session gets."""

    @pytest.mark.asyncio
    async def test_crisis_session_no_f2_recommendation_administers_phq9(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire=None,
            crisis_triggered=True,
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "outcome=administered" in result.detail
        assert "scale=PHQ-9" in result.detail
        assert "administration_mode=safety_net" in result.detail
        assert ctx.f3_survey_path is not None
        saved = json.loads(ctx.f3_survey_path.read_text(encoding="utf-8"))
        assert saved["administration_mode"] == "safety_net"

    @pytest.mark.asyncio
    async def test_low_ctrs_session_no_f2_recommendation_administers_phq9(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire=None,
            session_ctrs=1,
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "administration_mode=safety_net" in result.detail

    @pytest.mark.asyncio
    async def test_non_crisis_session_no_f2_recommendation_unaffected(
        self, tmp_path: Path
    ) -> None:
        """No regression to the pre-existing, still-legitimate
        no_questionnaire_indicated outcome for a genuinely low-acuity,
        no-recommendation session."""
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire=None,
            crisis_triggered=False, session_ctrs=5,
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "outcome=no_questionnaire_indicated" in result.detail
        assert "administration_mode=natural" in result.detail


class TestRunF3StageSiSupplementCvr030:
    """CVR-030 remediation at the harness (F2->F3 chain) consumption seam
    — crisis_triggered + a REAL non-PHQ-9 F2 recommendation (VP-012's own
    documented AUDIT-C table) additionally administers the standalone SI
    supplement, using VP-012's own documented PHQ-9 item 9 score (0, per
    `docs/ai/personas/VP-012_first_visit_alcohol.md`)."""

    @pytest.mark.asyncio
    async def test_crisis_audit_c_administers_si_supplement(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-012", recommended_questionnaire="AUDIT-C",
            crisis_triggered=True,
        )
        ctx = ct.ChainContext(
            persona_id="VP-012", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "scale=AUDIT-C" in result.detail
        assert "si_supplement_needed=True" in result.detail
        assert "si_supplement_administered=True" in result.detail
        assert ctx.f3_si_supplement_pathway is not None
        # VP-012's documented item 9 score is 0 -> not critical.
        assert ctx.f3_si_supplement_pathway["safety_triggered"] is False
        assert "si_supplement_json" in result.artifacts
        assert result.artifacts["si_supplement_json"].exists()

    @pytest.mark.asyncio
    async def test_not_crisis_triggered_no_supplement_in_ledger(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-012", recommended_questionnaire="AUDIT-C",
            crisis_triggered=False,
        )
        ctx = ct.ChainContext(
            persona_id="VP-012", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "si_supplement_needed" not in result.detail
        assert ctx.f3_si_supplement_pathway is None
        assert "si_supplement_json" not in result.artifacts

    @pytest.mark.asyncio
    async def test_ledger_subobject_carries_si_supplement_pathway(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-012", recommended_questionnaire="AUDIT-C",
            crisis_triggered=True,
        )
        ctx = ct.ChainContext(
            persona_id="VP-012", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        await ct.run_f3_stage(ctx)
        sub = ct._build_f3_ledger_subobject(ctx)
        assert sub is not None
        assert sub["si_supplement_pathway"] is not None
        assert sub["si_supplement_pathway"]["safety_triggered"] is False

    @pytest.mark.asyncio
    async def test_ledger_subobject_null_when_not_needed(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-012", recommended_questionnaire="AUDIT-C",
            crisis_triggered=False,
        )
        ctx = ct.ChainContext(
            persona_id="VP-012", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        await ct.run_f3_stage(ctx)
        sub = ct._build_f3_ledger_subobject(ctx)
        assert sub is not None
        assert sub["si_supplement_pathway"] is None


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

        def _patched_init(self, persona, api_key=None, base_url=None, model=None, scale_name=None):
            original_init(self, persona, api_key="k", model="m", scale_name=scale_name)

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
            "outcome", "scale_name", "administration_mode", "item_bank_version",
            "item_bank_provenance", "responses", "total_score", "max_score", "severity",
            "subscale_scores", "safety_referral", "threshold_caveat", "safety_pathway",
            "answer_mode", "recommendation_provenance", "survey_artifact_path",
            "scale_scores_path",
        }
        expected_keys |= {"scenario_pack_id", "arc_mode"}  # F4 quick-dev provenance, ADR-036 item 3
        expected_keys |= {"si_supplement_pathway"}  # CVR-030 remediation
        assert set(sub.keys()) == expected_keys
        assert sub["outcome"] == "administered"
        assert sub["scale_name"] == "PHQ-9"
        assert sub["administration_mode"] == "natural"
        assert sub["total_score"] == 7
        assert sub["scale_scores_path"] is not None
        # PHQ-9 item-9 safety-pathway wiring (PLAN-2026-W29-A step 3): fires
        # for every administered PHQ-9 outcome, regardless of Q9 value.
        assert sub["safety_pathway"] is not None
        assert sub["safety_pathway"]["safety_pathway_invoked"] is True
        assert sub["safety_pathway"]["safety_triggered"] is False  # VP-001 doc Q9=0

    @pytest.mark.asyncio
    async def test_present_with_null_score_fields_for_unpopulated_outcome(
        self, tmp_path: Path
    ) -> None:
        # WHO-5 is item bank v1's only remaining unpopulated scale.
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire="WHO-5"
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
        assert sub["safety_pathway"] is None  # only fires for administered PHQ-9
        assert sub["scale_scores_path"] is None

    @pytest.mark.asyncio
    async def test_threshold_caveat_reprojects_for_gad7(self, tmp_path: Path) -> None:
        """CVR-017 binding condition 1 / REV-039 correction D: the ledger's
        "f3" sub-object must carry GAD-7's band caveat the same way it
        already carries AUDIT-C's threshold caveat — both reprojected
        verbatim from the saved survey.json, never recomputed by the
        harness (no persona GAD-7 item-level table is required — this
        drives `src.f3` directly with a fixed answer_fn, no LLM/expected-
        table dependency)."""
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-001", recommended_questionnaire="GAD-7"
        )

        async def _answer_fn(item):
            return 2

        result = await f3.run_f3_administration(
            domain_inference_path=artifact_path,
            answer_fn=_answer_fn,
            answer_mode="expected",
            output_dir=tmp_path / "out",
            vp_id="VP-001",
        )
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected", f3_survey_path=result["paths"]["json"],
        )
        sub = ct._build_f3_ledger_subobject(ctx)
        assert sub is not None
        assert sub["outcome"] == "administered"
        assert sub["scale_name"] == "GAD-7"
        assert sub["threshold_caveat"] is not None
        assert "Spitzer" in sub["threshold_caveat"]
        assert "retract" in sub["threshold_caveat"].lower()


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
            run_f4=False,  # this test's scope is F3 integration, not F4 (covered separately)
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


class TestCliForceQuestionnaireFlag:
    """`PLAN-2026-W29-A` step 6 / `ADR-033` decision 6."""

    def test_default_is_none(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.force_questionnaire is None

    def test_override_gad7(self) -> None:
        args = ct.build_arg_parser().parse_args(["--force-questionnaire", "GAD-7"])
        assert args.force_questionnaire == "GAD-7"

    def test_all_supported_scales_are_valid_choices(self) -> None:
        for scale in ("PHQ-9", "GAD-7", "PHQ-4", "WHO-5", "AUDIT-C"):
            args = ct.build_arg_parser().parse_args(["--force-questionnaire", scale])
            assert args.force_questionnaire == scale

    def test_invalid_choice_rejected(self) -> None:
        with pytest.raises(SystemExit):
            ct.build_arg_parser().parse_args(["--force-questionnaire", "NOT-A-SCALE"])


class TestRunF3StageForcedScale:
    @pytest.mark.asyncio
    async def test_forced_scale_overrides_f2_recommendation_administered_outcome(
        self, tmp_path: Path
    ) -> None:
        # F2 recommends PHQ-9; ctx.forced_scale overrides to AUDIT-C
        # (VP-012 has a documented AUDIT-C table, so answer_mode="expected"
        # works with zero LLM).
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-012", recommended_questionnaire="PHQ-9"
        )
        ctx = ct.ChainContext(
            persona_id="VP-012", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected", forced_scale="AUDIT-C",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "administration_mode=forced" in result.detail
        assert "scale=AUDIT-C" in result.detail
        saved = json.loads(ctx.f3_survey_path.read_text(encoding="utf-8"))
        assert saved["scale_name"] == "AUDIT-C"
        assert saved["administration_mode"] == "forced"
        assert saved["threshold_caveat"] is not None  # AUDIT-C is in _SEVERITY_CAVEATS

    @pytest.mark.asyncio
    async def test_no_forced_scale_is_natural_mode(self, tmp_path: Path) -> None:
        artifact_path = _write_domain_inference_artifact(tmp_path, persona_id="VP-001")
        ctx = ct.ChainContext(
            persona_id="VP-001", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        assert ctx.forced_scale is None
        result = await ct.run_f3_stage(ctx)
        assert "administration_mode=natural" in result.detail


class TestPhq9SafetyPathwayWiring:
    """`PLAN-2026-W29-A` step 3 (mission directive): item-9 >= 1 on a PHQ-9
    administration deterministically routes to the EXISTING safety
    machinery, `OrchestratorAgent.score_and_check_safety` — proven by
    directly confirming that method actually ran (mocked + asserted-called
    in the first test; genuinely exercised, unmocked, in the rest), never
    merely a string in the score result."""

    def test_route_phq9_safety_pathway_calls_the_existing_orchestrator_method(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.agents.orchestrator import OrchestratorAgent
        from src.scoring.survey_scorer import score_survey

        captured: dict[str, object] = {}

        def _fake_score_and_check_safety(state, scale_name, responses, patient_sex="unknown"):
            captured["state"] = state
            captured["scale_name"] = scale_name
            captured["responses"] = responses
            result = score_survey(scale_name, responses, patient_sex=patient_sex)
            return result, result.recommended_action == "safety_referral"

        monkeypatch.setattr(
            OrchestratorAgent,
            "score_and_check_safety",
            staticmethod(_fake_score_and_check_safety),
        )

        positive_responses = [0, 0, 0, 0, 0, 0, 0, 0, 2]  # Q9 = 2, positive
        outcome = ct._route_phq9_safety_pathway("VP-TEST", positive_responses)

        # Proves the REAL orchestrator method was actually invoked with the
        # right arguments — not a locally re-derived flag.
        assert captured["scale_name"] == "PHQ-9"
        assert captured["responses"] == positive_responses
        assert outcome["safety_pathway_invoked"] is True
        assert outcome["safety_triggered"] is True
        assert outcome["recommended_action"] == "safety_referral"
        assert outcome["critical_item_positive"] is True

    def test_route_phq9_safety_pathway_negative_item9_no_trigger(self) -> None:
        # NOT mocked — exercises the real OrchestratorAgent.score_and_check_safety.
        negative_responses = [1, 1, 1, 0, 0, 0, 0, 0, 0]  # Q9 = 0
        outcome = ct._route_phq9_safety_pathway("VP-TEST", negative_responses)
        assert outcome["safety_pathway_invoked"] is True
        assert outcome["safety_triggered"] is False
        assert outcome["critical_item_positive"] is False

    @pytest.mark.asyncio
    async def test_run_f3_stage_item9_positive_invokes_safety_pathway_end_to_end(
        self, tmp_path: Path
    ) -> None:
        """VP-003's documented PHQ-9 table has Q9=2 (positive) — end-to-end
        through `run_f3_stage` with the deterministic expected answer_fn,
        zero LLM, and the real (unmocked) safety machinery."""
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-003", recommended_questionnaire="PHQ-9"
        )
        ctx = ct.ChainContext(
            persona_id="VP-003", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert ctx.f3_safety_pathway is not None
        assert ctx.f3_safety_pathway["safety_pathway_invoked"] is True
        assert ctx.f3_safety_pathway["safety_triggered"] is True
        assert "safety_pathway_triggered=True" in result.detail

        sub = ct._build_f3_ledger_subobject(ctx)
        assert sub is not None
        assert sub["safety_pathway"]["safety_triggered"] is True

    @pytest.mark.asyncio
    async def test_run_f3_stage_non_phq9_scale_never_routes_safety_pathway(
        self, tmp_path: Path
    ) -> None:
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-012", recommended_questionnaire="AUDIT-C"
        )
        ctx = ct.ChainContext(
            persona_id="VP-012", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="expected",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert ctx.f3_safety_pathway is None


class TestResolvePatientSex:
    """REV-041 Resolution 2: `_resolve_patient_sex` — explicit override
    always wins; otherwise derived from the persona's own Section 1 성별
    row via `load_persona` (Issue 2 / Resolution 2)."""

    def test_explicit_override_wins_regardless_of_persona(self) -> None:
        # VP-012 is documented male; an explicit override must still win.
        assert ct._resolve_patient_sex("VP-012", "female") == "female"

    def test_explicit_unknown_override_is_respected_verbatim(self) -> None:
        # VP-001 is documented female; "unknown" must not be silently
        # replaced by the persona's own value once explicitly passed.
        assert ct._resolve_patient_sex("VP-001", "unknown") == "unknown"

    def test_none_override_derives_from_real_persona_male(self) -> None:
        assert ct._resolve_patient_sex("VP-012", None) == "male"

    def test_none_override_derives_from_real_persona_female(self) -> None:
        assert ct._resolve_patient_sex("VP-001", None) == "female"


_FEMALE_AUDIT_C_PERSONA_MD = """# VP-778: 테스트 페르소나 — 테스트환자

## 1. Demographics

| 항목 | 값 |
|---|---|
| 이름 | 테스트 (가명) |
| 성별 | 여성 |

## 5. Expected dialogue patterns
- 예시 발화: "테스트 발화입니다."

## 6. Patient LLM simulation prompt

```
당신은 테스트 환자입니다. 항상 1문장으로 짧게 답하세요.
```
"""


class TestRunF3StagePatientSexWiring:
    """REV-041 Resolution 2, end-to-end through `run_f3_stage`: a
    female-sex persona (§1 성별 = 여성, auto-derived — no explicit
    `--patient-sex`) must hit AUDIT-C's female threshold branch
    (`_score_audit_c`: female >= 5, male/unknown >= 6), never the
    male/unknown default this stage silently used before this fix. No live
    LLM/network calls — `SurveyAnswerLLM._ask` is monkeypatched, matching
    `TestRunF3StageLLMModeConstructsSurveyAnswerLLM`'s existing pattern.
    """

    @pytest.mark.asyncio
    async def test_female_persona_auto_derived_crosses_female_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import AsyncMock

        from tests.simulation import patient_llm as patient_llm_module
        from tests.simulation import survey_answer_llm as sal_module

        persona_dir = tmp_path / "personas"
        persona_dir.mkdir()
        (persona_dir / "VP-778_first_visit_mild.md").write_text(
            _FEMALE_AUDIT_C_PERSONA_MD, encoding="utf-8"
        )
        monkeypatch.setattr(patient_llm_module, "PERSONAS_DIR", persona_dir)

        original_init = sal_module.SurveyAnswerLLM.__init__

        def _patched_init(self, persona, api_key=None, base_url=None, model=None, scale_name=None):
            original_init(self, persona, api_key="k", model="m", scale_name=scale_name)

        monkeypatch.setattr(sal_module.SurveyAnswerLLM, "__init__", _patched_init)
        # Total = 2 + 2 + 1 = 5: crosses the FEMALE threshold (>=5) but would
        # NOT cross the male/unknown threshold (>=6) — a distinctive total
        # that proves the female branch, specifically, was exercised.
        monkeypatch.setattr(
            sal_module.SurveyAnswerLLM, "_ask", AsyncMock(side_effect=["2", "2", "1"])
        )

        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-778", recommended_questionnaire="AUDIT-C"
        )
        ctx = ct.ChainContext(
            persona_id="VP-778", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="llm",  # patient_sex=None (default) -> auto-derive from persona
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "patient_sex=female" in result.detail

        saved = json.loads(ctx.f3_survey_path.read_text(encoding="utf-8"))
        assert saved["responses"] == [2, 2, 1]
        assert saved["score_result"]["total_score"] == 5
        assert saved["score_result"]["severity"] == "hazardous_drinking"  # female threshold=5

    @pytest.mark.asyncio
    async def test_explicit_patient_sex_override_beats_female_persona(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The SAME female persona/responses as above, but with an explicit
        `ctx.patient_sex="unknown"` override — must use the male/unknown
        threshold (>=6) instead, proving the override truly takes
        precedence over persona-derivation, not just coexists with it."""
        from unittest.mock import AsyncMock

        from tests.simulation import patient_llm as patient_llm_module
        from tests.simulation import survey_answer_llm as sal_module

        persona_dir = tmp_path / "personas"
        persona_dir.mkdir()
        (persona_dir / "VP-778_first_visit_mild.md").write_text(
            _FEMALE_AUDIT_C_PERSONA_MD, encoding="utf-8"
        )
        monkeypatch.setattr(patient_llm_module, "PERSONAS_DIR", persona_dir)

        original_init = sal_module.SurveyAnswerLLM.__init__

        def _patched_init(self, persona, api_key=None, base_url=None, model=None, scale_name=None):
            original_init(self, persona, api_key="k", model="m", scale_name=scale_name)

        monkeypatch.setattr(sal_module.SurveyAnswerLLM, "__init__", _patched_init)
        monkeypatch.setattr(
            sal_module.SurveyAnswerLLM, "_ask", AsyncMock(side_effect=["2", "2", "1"])
        )

        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-778", recommended_questionnaire="AUDIT-C"
        )
        ctx = ct.ChainContext(
            persona_id="VP-778", max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, domain_inference_path=artifact_path,
            answer_mode="llm", patient_sex="unknown",
        )
        result = await ct.run_f3_stage(ctx)
        assert result.status == "pass"
        assert "patient_sex=unknown" in result.detail

        saved = json.loads(ctx.f3_survey_path.read_text(encoding="utf-8"))
        assert saved["score_result"]["total_score"] == 5
        assert saved["score_result"]["severity"] == "low_risk"  # male/unknown threshold=6, 5<6


class TestCliPatientSexFlag:
    """REV-041 Resolution 2."""

    def test_default_is_none(self) -> None:
        args = ct.build_arg_parser().parse_args([])
        assert args.patient_sex is None

    def test_override_female(self) -> None:
        args = ct.build_arg_parser().parse_args(["--patient-sex", "female"])
        assert args.patient_sex == "female"

    def test_invalid_choice_rejected(self) -> None:
        with pytest.raises(SystemExit):
            ct.build_arg_parser().parse_args(["--patient-sex", "bogus"])


class TestForcedModeLedgerCollisionSafety:
    """`PLAN-2026-W29-A` step 6 / `REV-038` Resolution 1: a forced run must
    NOT overwrite a natural run's ledger `"f3"` record for the same
    session — proven by running natural-then-forced on the same persona and
    showing both ledger records survive untouched."""

    @pytest.mark.asyncio
    async def test_natural_then_forced_same_persona_both_ledger_records_survive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conv_path = tmp_path / "VP-012" / "VP-012_20260101_000000_conversation.json"
        conv_path.parent.mkdir(parents=True, exist_ok=True)
        conv_path.write_text(
            json.dumps(
                {
                    "final_slots": [{"key": "chief_complaint", "value": "음주 문제"}],
                    "model": "stub", "prompt_version": "v3",
                }
            ),
            encoding="utf-8",
        )
        # F2 always recommends PHQ-9 in both runs — the SAME F1/F2 artifacts
        # are reused, mirroring REV-038's "Cell B reuses Cell A's F1/F2
        # artifacts" design intent.
        artifact_path = _write_domain_inference_artifact(
            tmp_path, persona_id="VP-012", recommended_questionnaire="PHQ-9"
        )

        async def _fake_run_f1_stage(ctx):
            ctx.conversation_path = conv_path
            return ct.StageResult("F1", "pass", "ok", artifacts={"conversation": conv_path})

        async def _fake_run_f2_stage(ctx):
            ctx.domain_inference_path = artifact_path
            return ct.StageResult(
                "F2", "pass", "ok", artifacts={"domain_inference": artifact_path}
            )

        monkeypatch.setattr(
            ct, "STAGE_REGISTRY",
            [
                ct.Stage("F1", True, _fake_run_f1_stage),
                ct.Stage("F2", True, _fake_run_f2_stage),
                ct.Stage("F3", True, ct.run_f3_stage),
            ],
        )

        # Run 1: natural — F2's own PHQ-9 recommendation is administered.
        args_natural = ct.build_arg_parser().parse_args(
            ["--persona", "VP-012", "--out", str(tmp_path), "--answer-mode", "expected"]
        )
        rc1 = await ct._main(args_natural)
        assert rc1 == 0

        ledger_path = ct._ledger_path("VP-012", tmp_path)
        entries_after_run1 = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(entries_after_run1) == 1
        assert entries_after_run1[0]["f3"]["scale_name"] == "PHQ-9"
        assert entries_after_run1[0]["f3"]["administration_mode"] == "natural"
        natural_snapshot = entries_after_run1[0]

        # Run 2: forced AUDIT-C — same persona, same (mocked) F1/F2
        # artifacts, same day (session_index/simulated_date collide with
        # run 1's entry exactly as REV-037/REV-038 flagged) — must still
        # NOT overwrite run 1's record.
        args_forced = ct.build_arg_parser().parse_args(
            [
                "--persona", "VP-012", "--out", str(tmp_path), "--answer-mode", "expected",
                "--force-questionnaire", "AUDIT-C",
            ]
        )
        rc2 = await ct._main(args_forced)
        assert rc2 == 0

        entries_after_run2 = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(entries_after_run2) == 2, (
            "the forced run must append a NEW ledger entry, never overwrite run 1's"
        )

        # Run 1's record survives byte-for-byte.
        assert entries_after_run2[0] == natural_snapshot
        assert entries_after_run2[0]["f3"]["scale_name"] == "PHQ-9"
        assert entries_after_run2[0]["f3"]["administration_mode"] == "natural"

        # Run 2's record is the new, distinct, self-describing forced entry.
        assert entries_after_run2[1]["f3"]["scale_name"] == "AUDIT-C"
        assert entries_after_run2[1]["f3"]["administration_mode"] == "forced"
        assert entries_after_run2[1]["f3"]["outcome"] == "administered"
        assert entries_after_run2[1]["f3"]["threshold_caveat"] is not None

        # Both share the same session_index/simulated_date collision REV-037
        # already disclosed as a pre-existing harness property — proving
        # the collision-safety guarantee is about the WRITE (append-only,
        # never in-place mutation), not about avoiding the key collision
        # itself.
        assert (
            entries_after_run2[0]["session_index"] == entries_after_run2[1]["session_index"]
        )
        assert (
            entries_after_run2[0]["simulated_date"] == entries_after_run2[1]["simulated_date"]
        )
