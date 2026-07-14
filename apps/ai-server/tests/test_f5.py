"""Unit tests for `src/f5.py` — the F5 hand-off report assembly engine.

`docs/ai/f5_quick_dev_plan.md`, `PLAN-2026-W29-E`, `ADR-037`. No live LLM/DB
call anywhere in this file (`f5.py` itself is zero-LLM by construction;
these tests build synthetic `HandoffReportInput`s directly — no F1-F4
pipeline is ever invoked). Fixture shapes are modeled on the real
`EXP-023` VP-001/VP-003 artifacts (per the HANDOFF brief) but constructed
inline here — this file has zero runtime dependency on `experiments/` or
`docs/ai/simulation_results/`.
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

import src.f5 as f5_module
from src.f5 import (
    ChartFilenames,
    DepartmentCandidateInput,
    DomainInferenceSnapshot,
    F3Administration,
    HandoffReportInput,
    SessionSnapshot,
    _rank_candidates,
    _relevant_gaps,
    _risk_elevated,
    assemble_handoff_report,
)
from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.longitudinal import CTRSSeriesPoint, LongitudinalAnalysisOutput, ScaleSeriesPoint
from src.services.f5_report import build_markdown_report

# ── Fixtures modeled on real VP-001/VP-003 EXP-023 shapes ──────────────


def _session(
    *,
    session_index: int = 11,
    simulated_date: str = "2027-01-12",
    session_ctrs: int | None = 4,
    crisis_triggered: bool = False,
    crisis_turn: int | None = None,
    risk_floor: int | None = None,
    probe_event_count: int = 0,
    final_slots: dict[str, str] | None = None,
) -> SessionSnapshot:
    return SessionSnapshot(
        session_id="f1_VP-TEST",
        persona_id="VP-TEST",
        persona_name="김테스트",
        session_index=session_index,
        simulated_date=simulated_date,
        model="solar-pro3-260323",
        final_slots=final_slots
        if final_slots is not None
        else {
            "chief_complaint": "잠을 잘 못 자는 것이 가장 신경 쓰임. 새벽에도 깨는 문제 지속",
            "history_of_present_illness": "3개월 전부터 지속된 수면 문제와 무기력감",
            "risk_assessment": "자살/자해 사고 탐색 질문에 부인",
        },
        session_ctrs=session_ctrs,
        crisis_triggered=crisis_triggered,
        crisis_turn=crisis_turn,
        risk_floor=risk_floor,
        probe_event_count=probe_event_count,
    )


def _f3(
    session_index: int,
    simulated_date: str,
    *,
    outcome: str = "administered",
    scale_name: str = "PHQ-9",
    total_score: int = 17,
    max_score: int = 27,
    severity: str = "moderately_severe",
    critical_item_positive: bool = False,
    safety_referral: bool = False,
    threshold_caveat: str | None = None,
    responses: tuple[int, ...] = (2, 2, 3, 3, 2, 2, 2, 1, 0),
) -> F3Administration:
    return F3Administration(
        session_index=session_index,
        simulated_date=simulated_date,
        outcome=outcome,
        scale_name=scale_name if outcome == "administered" else None,
        item_bank_version="v1",
        item_bank_provenance="v1, verbatim Pfizer PHQ-9",
        responses=responses if outcome == "administered" else (),
        total_score=total_score if outcome == "administered" else None,
        max_score=max_score if outcome == "administered" else None,
        severity=severity if outcome == "administered" else None,
        critical_item_positive=critical_item_positive if outcome == "administered" else None,
        safety_referral=safety_referral,
        threshold_caveat=threshold_caveat,
    )


def _apd(
    *,
    candidates: list[AIPredictedDiseaseCandidate] | None = None,
    mode: str = "rag_live",
) -> AIPredictedDiseaseOutput:
    return AIPredictedDiseaseOutput(
        candidates=candidates
        if candidates is not None
        else [
            AIPredictedDiseaseCandidate(
                disease="계절성 정동장애",
                similarity_score=0.485,
                source_id="case_card:1045",
                quote="q1",
            ),
            AIPredictedDiseaseCandidate(
                disease="월경전 불쾌장애",
                similarity_score=0.485,
                source_id="case_card:1045",
                quote="q1",
            ),
            AIPredictedDiseaseCandidate(
                disease="범불안장애", similarity_score=0.477, source_id="case_card:382", quote="q2"
            ),
        ],
        mode=mode,
        recommended_questionnaire="PHQ-9" if mode == "rag_live" else None,
        recommendation_caveat="PHQ-9 screens depressive-symptom burden only.",
    )


def _longitudinal(
    *,
    ctrs_points: list[CTRSSeriesPoint] | None = None,
    crisis_f3_gaps: list[str] | None = None,
    concordance_flag: str = "unknown",
) -> LongitudinalAnalysisOutput:
    return LongitudinalAnalysisOutput(
        vp_id="VP-TEST",
        n_sessions=3,
        ctrs_series=ctrs_points
        if ctrs_points is not None
        else [
            CTRSSeriesPoint(
                session_index=9, simulated_date="2026-11-12", session_ctrs=4, crisis_triggered=False
            ),
            CTRSSeriesPoint(
                session_index=11, simulated_date="2027-01-12", session_ctrs=2, crisis_triggered=True
            ),
        ],
        scale_series={
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=9,
                    simulated_date="2026-11-12",
                    scale_name="PHQ-9",
                    administered=True,
                    total_score=27,
                    max_score=27,
                    severity="severe",
                    critical_item_positive=True,
                )
            ]
        },
        overall_direction="worsened",
        concordance_flag=concordance_flag,  # type: ignore[arg-type]
        crisis_f3_gaps=crisis_f3_gaps if crisis_f3_gaps is not None else [],
    )


def _build_input(
    *,
    session: SessionSnapshot | None = None,
    current_session_f3: F3Administration | None = None,
    all_f3_administrations: tuple[F3Administration, ...] = (),
    ai_predicted_disease: AIPredictedDiseaseOutput | None = None,
    department_candidates: tuple[DepartmentCandidateInput, ...] = (),
    longitudinal: LongitudinalAnalysisOutput | None = None,
    narrative_enabled: bool = False,
) -> HandoffReportInput:
    return HandoffReportInput(
        vp_id="VP-TEST",
        session=session or _session(),
        current_session_f3=current_session_f3,
        all_f3_administrations=all_f3_administrations,
        domain_inference=DomainInferenceSnapshot(
            ai_predicted_disease=ai_predicted_disease
            if ai_predicted_disease is not None
            else _apd(),
            department_candidates=department_candidates,
        ),
        longitudinal=longitudinal or _longitudinal(),
        chart_filenames=ChartFilenames(),
        narrative_enabled=narrative_enabled,
    )


# ── Narrative descope (ADR-037 Decision 1) ─────────────────────────────


class TestNarrativeDescoped:
    def test_narrative_enabled_true_raises(self) -> None:
        inp = _build_input(narrative_enabled=True)
        with pytest.raises(ValueError, match="ADR-037"):
            assemble_handoff_report(inp)

    def test_narrative_enabled_false_default(self) -> None:
        out = assemble_handoff_report(_build_input())
        assert out.a8_narrative.narrative_enabled is False
        assert out.a8_narrative.text is None
        assert out.a8_narrative.absent_marker == "AI 종합 소견 미생성 (narrative disabled)"

    def test_module_never_imports_handoff_generator(self) -> None:
        """Import-statement-shaped check (not bare substring) — this
        module's own docstring legitimately DISCUSSES
        `src.agents.handoff_generator` in prose (documenting why it is
        never imported), so a naive substring check on the bare name would
        false-positive on that very prose (mirrors
        `test_f4_hpi_isolation.py::TestF4TypeLayerIsolation`'s discipline)."""
        source = inspect.getsource(f5_module)
        assert "from src.agents.handoff_generator" not in source
        assert "import src.agents.handoff_generator" not in source
        assert "from src.schemas.handoff import" not in source
        assert "import src.schemas.handoff" not in source
        assert "HandoffGeneratorAgent(" not in source
        assert "EvidenceVerifierAgent(" not in source

    def test_module_never_opens_files_or_reads_ledger(self) -> None:
        """REV-044 Criterion 6 (citation fixed from REV-022, ADR-037
        Decision 6): AST-level check (not source substring, since the
        module's own docstring legitimately discusses "open(" in prose
        documenting the invariant) — 0 `open(...)` CALL nodes anywhere in
        `src/f5.py`."""
        import ast

        tree = ast.parse(inspect.getsource(f5_module))
        open_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ]
        assert open_calls == []

        source = inspect.getsource(f5_module)
        assert "import src.continuous_test" not in source
        assert "from src.continuous_test" not in source
        assert "import json" not in source
        assert "import pathlib" not in source
        assert "from pathlib" not in source


# ── Absent-slot honesty (A1/A2/A4/A6/A5 never silently omitted) ────────


class TestAbsentSlotHonesty:
    def test_a1_a2_absent_when_slots_missing(self) -> None:
        session = _session(final_slots={})
        out = assemble_handoff_report(_build_input(session=session))
        assert out.a1_chief_complaint.present is False
        assert out.a1_chief_complaint.text is None
        assert out.a2_hpi.present is False

    def test_a0_header_derived_from_conversation_top_level_never_from_slot(self) -> None:
        """A0 (`encounter_metadata`) is never populated from a slot value —
        it is assembled deterministically from `SessionSnapshot`'s own
        top-level fields (design doc §2.2 A0 row)."""
        out = assemble_handoff_report(_build_input())
        assert out.a0_header.session_index == 11
        assert out.a0_header.persona_name == "김테스트"
        assert out.a0_header.chief_complaint_summary is not None

    def test_a4_mse_absent_by_default_rare_by_design(self) -> None:
        out = assemble_handoff_report(_build_input())
        assert out.a4_mental_status.present is False
        assert out.a4_mental_status.raw_text is None
        assert len(out.a4_mental_status.domain_checklist) == 11
        assert all(d.assessable is False for d in out.a4_mental_status.domain_checklist)

    def test_a4_mse_present_when_slot_populated(self) -> None:
        session = _session(final_slots={"mental_status_exam": "차분함, 눈맞춤 양호"})
        out = assemble_handoff_report(_build_input(session=session))
        assert out.a4_mental_status.present is True
        assert out.a4_mental_status.raw_text == "차분함, 눈맞춤 양호"

    def test_a5_absent_when_no_administrations(self) -> None:
        out = assemble_handoff_report(_build_input(all_f3_administrations=()))
        assert out.a5_questionnaires.present is False

    def test_a6_absent_when_experimental_unpopulated(self) -> None:
        out = assemble_handoff_report(
            _build_input(ai_predicted_disease=_apd(candidates=[], mode="experimental_unpopulated"))
        )
        assert out.a6_ai_predicted_disease.present is False
        assert out.a6_ai_predicted_disease.no_data_note is not None


# ── A3 종단 위험 신호 + staleness pointer (ADR-037 Decision 2) ─────────


class TestA3LongitudinalRiskSignal:
    def test_item9_positive_session_surfaced_regardless_of_being_latest(self) -> None:
        """Mirrors VP-001: item-9-positive sessions (S1/S3/S7) are NOT the
        latest session (S11) — A3 must still surface them."""
        session = _session(session_index=11, simulated_date="2027-01-12", session_ctrs=4)
        f3_s1 = _f3(
            1, "2026-08-01", critical_item_positive=True, safety_referral=True, total_score=22
        )
        f3_s11 = _f3(11, "2027-01-12", total_score=17)
        longitudinal = _longitudinal(
            ctrs_points=[
                CTRSSeriesPoint(
                    session_index=1,
                    simulated_date="2026-08-01",
                    session_ctrs=4,
                    crisis_triggered=False,
                ),
                CTRSSeriesPoint(
                    session_index=11,
                    simulated_date="2027-01-12",
                    session_ctrs=4,
                    crisis_triggered=False,
                ),
            ]
        )
        out = assemble_handoff_report(
            _build_input(
                session=session,
                current_session_f3=f3_s11,
                all_f3_administrations=(f3_s1, f3_s11),
                longitudinal=longitudinal,
            )
        )
        signals = out.a3_risk_safety.longitudinal_risk_signals
        assert len(signals) == 1
        assert signals[0].session_index == 1
        assert signals[0].safety_referral is True
        # session_ctrs=4 at session 1 is NOT elevated (>2, no crisis) -> discordant.
        assert "불일치" in signals[0].discordance_note

    def test_concordant_when_ctrs_also_elevated(self) -> None:
        f3_s1 = _f3(1, "2026-08-01", critical_item_positive=True, safety_referral=True)
        longitudinal = _longitudinal(
            ctrs_points=[
                CTRSSeriesPoint(
                    session_index=1,
                    simulated_date="2026-08-01",
                    session_ctrs=2,
                    crisis_triggered=True,
                )
            ]
        )
        out = assemble_handoff_report(
            _build_input(
                current_session_f3=None, all_f3_administrations=(f3_s1,), longitudinal=longitudinal
            )
        )
        signals = out.a3_risk_safety.longitudinal_risk_signals
        assert len(signals) == 1
        assert "일치" in signals[0].discordance_note
        assert "불일치" not in signals[0].discordance_note

    def test_no_signals_when_no_flagged_administration(self) -> None:
        f3 = _f3(1, "2026-08-01", critical_item_positive=False, safety_referral=False)
        out = assemble_handoff_report(_build_input(all_f3_administrations=(f3,)))
        assert out.a3_risk_safety.longitudinal_risk_signals == []

    def test_bug_043_safety_referral_only_administration_included_in_a3(self) -> None:
        """BUG-043 regression: `safety_referral=True` alone (item-9 negative,
        `critical_item_positive=False`) must independently be sufficient to
        surface an administration in A3's longitudinal risk signals — the
        `flagged` gate is an OR of the two fields, not a dependency on
        `critical_item_positive`. Prior to this test, no fixture anywhere in
        the F5 suite exercised `safety_referral=True` without also setting
        `critical_item_positive=True`, so a mutation collapsing the OR into
        `bool(admin.critical_item_positive)` alone survived the full suite."""
        f3_referral_only = _f3(
            1, "2026-08-01", critical_item_positive=False, safety_referral=True
        )
        out = assemble_handoff_report(
            _build_input(all_f3_administrations=(f3_referral_only,))
        )
        signals = out.a3_risk_safety.longitudinal_risk_signals
        assert len(signals) == 1
        assert signals[0].session_index == 1
        assert signals[0].safety_referral is True
        assert signals[0].critical_item_positive is False

        md = build_markdown_report(out)
        assert "2026-08-01" in md

    def test_staleness_pointer_vp003_worked_example(self) -> None:
        """VP-003 worked example (ADR-037 Decision 2): S11 current
        (active crisis, no F3), only-ever-administered PHQ-9 is S9
        (27/27, item-9 positive, safety_referral), ~2 months stale."""
        session = _session(
            session_index=11,
            simulated_date="2027-01-12",
            session_ctrs=2,
            crisis_triggered=True,
            risk_floor=3,
            probe_event_count=2,
        )
        f3_s9 = _f3(
            9,
            "2026-11-12",
            scale_name="PHQ-9",
            total_score=27,
            max_score=27,
            severity="severe",
            critical_item_positive=True,
            safety_referral=True,
            responses=(3,) * 9,
        )
        f3_s11 = _f3(11, "2027-01-12", outcome="no_questionnaire_indicated")
        out = assemble_handoff_report(
            _build_input(
                session=session,
                current_session_f3=f3_s11,
                all_f3_administrations=(f3_s9, f3_s11),
            )
        )
        sp = out.a3_risk_safety.staleness_pointer
        assert sp.applicable is True
        assert sp.latest_scored_session_index == 9
        assert sp.scale_name == "PHQ-9"
        assert sp.total_score == 27
        assert sp.safety_referral is True
        assert sp.sessions_stale == 2
        assert sp.days_stale == 61  # 2026-11-12 -> 2027-01-12
        assert "27" in sp.note and "9회차" in sp.note

    def test_staleness_pointer_not_applicable_when_current_session_administered(self) -> None:
        f3_s11 = _f3(11, "2027-01-12", total_score=17)
        out = assemble_handoff_report(
            _build_input(current_session_f3=f3_s11, all_f3_administrations=(f3_s11,))
        )
        sp = out.a3_risk_safety.staleness_pointer
        assert sp.applicable is False
        assert sp.latest_scored_session_index is None

    def test_staleness_pointer_no_prior_history(self) -> None:
        f3_s11 = _f3(11, "2027-01-12", outcome="no_questionnaire_indicated")
        out = assemble_handoff_report(
            _build_input(current_session_f3=f3_s11, all_f3_administrations=(f3_s11,))
        )
        sp = out.a3_risk_safety.staleness_pointer
        assert sp.applicable is True
        assert sp.latest_scored_session_index is None
        assert "없습니다" in sp.note

    def test_risk_elevated_helper(self) -> None:
        assert _risk_elevated(2, False) is True
        assert _risk_elevated(4, False) is False
        assert _risk_elevated(4, True) is True
        assert _risk_elevated(None, False) is False


# ── A5 latest-administered session (VP-003 S9-vs-S11 divergence) ──────


class TestA5LatestAdministered:
    def test_a5_uses_latest_administered_not_latest_conversation(self) -> None:
        session = _session(session_index=11, simulated_date="2027-01-12")
        f3_s9 = _f3(9, "2026-11-12", total_score=27, max_score=27, severity="severe")
        f3_s11 = _f3(11, "2027-01-12", outcome="no_questionnaire_indicated")
        out = assemble_handoff_report(
            _build_input(
                session=session,
                current_session_f3=f3_s11,
                all_f3_administrations=(f3_s9, f3_s11),
            )
        )
        a5 = out.a5_questionnaires
        assert a5.present is True
        assert a5.administering_session_index == 9
        assert a5.is_stale_relative_to_header is True

    def test_a5_gap_disclosure_includes_gap_acuity_framing(self) -> None:
        session = _session(session_index=11, simulated_date="2027-01-12")
        f3_s9 = _f3(9, "2026-11-12", total_score=27)
        f3_s11 = _f3(11, "2027-01-12", outcome="no_questionnaire_indicated")
        longitudinal = _longitudinal(
            crisis_f3_gaps=[
                "session 10 (2026-12-12): risk-elevated (crisis_triggered=True, "
                "session_ctrs=2) but NO scale was administered this session",
                "session 11 (2027-01-12): risk-elevated (crisis_triggered=True, "
                "session_ctrs=2) but NO scale was administered this session",
            ]
        )
        out = assemble_handoff_report(
            _build_input(
                session=session,
                current_session_f3=f3_s11,
                all_f3_administrations=(f3_s9, f3_s11),
                longitudinal=longitudinal,
            )
        )
        a5 = out.a5_questionnaires
        assert len(a5.gap_disclosure) == 2
        assert a5.gap_acuity_framing_note is not None

    def test_relevant_gaps_helper_filters_by_session_range(self) -> None:
        gaps = ["session 2 (x): ...", "session 9 (x): ...", "session 11 (x): ..."]
        assert _relevant_gaps(gaps, after_session_index=9, up_to_session_index=11) == [
            "session 11 (x): ..."
        ]
        assert _relevant_gaps(gaps, after_session_index=0, up_to_session_index=2) == [
            "session 2 (x): ..."
        ]

    def test_gad7_threshold_caveat_asymmetry_disclosed(self) -> None:
        f3 = _f3(
            1,
            "2026-01-01",
            scale_name="GAD-7",
            total_score=10,
            max_score=21,
            severity="moderate",
            threshold_caveat=None,
        )
        out = assemble_handoff_report(
            _build_input(current_session_f3=f3, all_f3_administrations=(f3,))
        )
        assert out.a5_questionnaires.threshold_caveat_asymmetry_note is not None

    def test_non_gad7_scale_has_no_asymmetry_note(self) -> None:
        f3 = _f3(1, "2026-01-01", scale_name="PHQ-9", total_score=10)
        out = assemble_handoff_report(
            _build_input(current_session_f3=f3, all_f3_administrations=(f3,))
        )
        assert out.a5_questionnaires.threshold_caveat_asymmetry_note is None

    def test_a5_non_validated_caveat_always_present(self) -> None:
        f3 = _f3(1, "2026-01-01")
        out = assemble_handoff_report(
            _build_input(current_session_f3=f3, all_f3_administrations=(f3,))
        )
        assert out.a5_questionnaires.non_validated_caveat


# ── A6 tie-handling (ADR-037 Decision 3, VP-001 S11 worked example) ────


class TestA6TieHandling:
    def test_vp001_tie_co_ranked(self) -> None:
        out = assemble_handoff_report(_build_input())
        ranked = {rc.candidate.disease: rc for rc in out.a6_ai_predicted_disease.candidates}
        assert ranked["계절성 정동장애"].rank == 1
        assert ranked["월경전 불쾌장애"].rank == 1
        assert ranked["계절성 정동장애"].co_ranked is True
        assert ranked["월경전 불쾌장애"].co_ranked is True
        assert ranked["계절성 정동장애"].tie_marker == "공동 1위"
        assert ranked["범불안장애"].rank == 3
        assert ranked["범불안장애"].co_ranked is False
        assert ranked["범불안장애"].tie_marker is None

    def test_no_tie_when_all_scores_distinct(self) -> None:
        candidates = [
            AIPredictedDiseaseCandidate(disease="A", similarity_score=0.9),
            AIPredictedDiseaseCandidate(disease="B", similarity_score=0.5),
            AIPredictedDiseaseCandidate(disease="C", similarity_score=0.1),
        ]
        ranked = _rank_candidates(candidates)
        assert [r.rank for r in ranked] == [1, 2, 3]
        assert all(not r.co_ranked for r in ranked)

    def test_similarity_score_field_name_never_relabeled(self) -> None:
        """REV-013 §4: no field/description anywhere in this module says
        'probability'/'확률'."""
        source = inspect.getsource(f5_module)
        assert "probability" not in source.lower()
        assert "확률" not in source


# ── Type-layer isolation (mirrors test_f4.py's own discipline) ────────


class TestSchemaValidation:
    def test_output_rejects_extra_fields(self) -> None:
        out = assemble_handoff_report(_build_input())
        dumped = out.model_dump()
        dumped["unexpected_field"] = "x"
        from src.schemas.handoff_report import HandoffReportOutput

        with pytest.raises(ValidationError):
            HandoffReportOutput.model_validate(dumped)

    def test_is_diagnostic_fixed_false(self) -> None:
        out = assemble_handoff_report(_build_input())
        assert out.is_diagnostic is False
