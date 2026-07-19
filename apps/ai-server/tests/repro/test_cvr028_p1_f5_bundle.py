"""CVR-028/CVR-030 P1 fix bundle — F5 renderer regression tests.

Covers three items from the total-validation P1 fix bundle:
  3. VP-010 risk-label mislabel (CVR-028 Finding 4) — a stale "표현 있음"
     categorical prefix that the SAME quoted text contradicts (an explicit
     denial) must relabel to "자살사고 부인(탐색 완료)".
  4. Near-ceiling caveat coverage (CVR-028) — the over-endorsement caveat
     now also fires within 1 point of max (e.g. 26/27), and a flat
     near-ceiling delta (26->26) must never render "worsened".
  5. VP-002 headline-body consistency (CVR-028 Finding 7) — the SBAR
     headline's "주요 우려" line must never read "특이 우려 사항 없음" while
     `overall_direction=worsened`.
"""

from __future__ import annotations

import src.f4 as f4_module
import src.f5 as f5_module
from src.f5 import (
    ChartFilenames,
    DomainInferenceSnapshot,
    HandoffReportInput,
    SessionSlotSnapshot,
    SessionSnapshot,
    _relabel_risk_assessment_text,
    assemble_handoff_report,
)
from src.schemas.longitudinal import LongitudinalAnalysisOutput, ScaleSeriesPoint
from src.services.f5_report import _key_concerns

# ── Finding 3 / CVR-028 Finding 4: risk-label mislabel ─────────────────

_SI_EXPRESSED_DENIAL_TEXT = (
    '자살/자해 사고 표현 있음 — 환자 발화: "아니요, 그런 건 전혀 없어요. '
    '정신과 가본 적도 없고, 상담 같은 건 처음이에요."; 탐색 질문에 대한 환자 응답: "음..."'
)

_SI_EXPRESSED_GENUINE_TEXT = (
    '자살/자해 사고 표현 있음 — 환자 발화: "가끔 그냥 사라지고 싶다는 생각이 들어요."; '
    '구체적 계획/의도 부인 — 환자 발화: "아니요, 계획은 없어요."'
)


class TestRelabelRiskAssessmentText:
    def test_denial_quote_relabels_to_denial_marker(self) -> None:
        out = _relabel_risk_assessment_text(_SI_EXPRESSED_DENIAL_TEXT)
        assert out is not None
        assert out.startswith("자살사고 부인(탐색 완료)")
        assert "표현 있음" not in out.split("—")[0]

    def test_genuine_expression_quote_left_unchanged(self) -> None:
        """A quote that is NOT a denial must keep the original label —
        this function never suppresses a genuine SI-positive signal."""
        out = _relabel_risk_assessment_text(_SI_EXPRESSED_GENUINE_TEXT)
        assert out == _SI_EXPRESSED_GENUINE_TEXT

    def test_none_passthrough(self) -> None:
        assert _relabel_risk_assessment_text(None) is None

    def test_text_without_label_prefix_untouched(self) -> None:
        text = "환자가 최근 불면을 호소함."
        assert _relabel_risk_assessment_text(text) == text

    def test_label_prefix_but_no_quote_untouched(self) -> None:
        text = "자살/자해 사고 표현 있음 — 기록 누락"
        assert _relabel_risk_assessment_text(text) == text

    def test_quoted_content_preserved_verbatim(self) -> None:
        """The underlying quote is never altered, only the label."""
        out = _relabel_risk_assessment_text(_SI_EXPRESSED_DENIAL_TEXT)
        assert '아니요, 그런 건 전혀 없어요' in out
        assert '탐색 질문에 대한 환자 응답: "음..."' in out


def _session(final_slots: dict[str, str]) -> SessionSnapshot:
    return SessionSnapshot(
        session_id="f1_VP-010",
        persona_id="VP-010",
        persona_name="테스트",
        session_index=10,
        simulated_date="2027-01-14",
        model="solar-pro3-260323",
        final_slots=final_slots,
        session_ctrs=4,
        crisis_triggered=False,
        crisis_turn=None,
        risk_floor=None,
        probe_event_count=0,
    )


def _minimal_input(final_slots: dict[str, str], all_sessions=()) -> HandoffReportInput:
    return HandoffReportInput(
        vp_id="VP-010",
        session=_session(final_slots),
        current_session_f3=None,
        all_f3_administrations=(),
        domain_inference=DomainInferenceSnapshot(ai_predicted_disease=None),
        longitudinal=LongitudinalAnalysisOutput(
            vp_id="VP-010", n_sessions=1, overall_direction="unchanged",
        ),
        chart_filenames=ChartFilenames(),
        all_sessions=all_sessions,
    )


class TestA3RiskAssessmentRelabelIntegration:
    def test_a3_risk_assessment_text_relabeled(self) -> None:
        inp = _minimal_input({"risk_assessment": _SI_EXPRESSED_DENIAL_TEXT})
        out = assemble_handoff_report(inp)
        assert out.a3_risk_safety.risk_assessment_text.startswith("자살사고 부인(탐색 완료)")

    def test_a3_risk_assessment_present_unaffected(self) -> None:
        inp = _minimal_input({"risk_assessment": _SI_EXPRESSED_DENIAL_TEXT})
        out = assemble_handoff_report(inp)
        assert out.a3_risk_safety.risk_assessment_present is True


class TestSlotOverviewRiskAssessmentRelabel:
    def test_slot_overview_latest_value_relabeled(self) -> None:
        sessions = (
            SessionSlotSnapshot(3, "2026-08-01", {"risk_assessment": _SI_EXPRESSED_DENIAL_TEXT}),
        )
        inp = _minimal_input({}, all_sessions=sessions)
        out = assemble_handoff_report(inp)
        row = next(r for r in out.slot_overview.rows if r.key == "risk_assessment")
        assert row.latest_value.startswith("자살사고 부인(탐색 완료)")

    def test_slot_overview_change_history_relabeled(self) -> None:
        earlier_denial = "자살/자해 사고 탐색 질문에 부인"
        sessions = (
            SessionSlotSnapshot(1, "2026-06-01", {"risk_assessment": earlier_denial}),
            SessionSlotSnapshot(3, "2026-08-01", {"risk_assessment": _SI_EXPRESSED_DENIAL_TEXT}),
        )
        inp = _minimal_input({}, all_sessions=sessions)
        out = assemble_handoff_report(inp)
        row = next(r for r in out.slot_overview.rows if r.key == "risk_assessment")
        assert any("자살사고 부인(탐색 완료)" in h for h in row.change_history_full)

    def test_other_slot_keys_never_relabeled(self) -> None:
        """The relabel is scoped to risk_assessment only — a chief_complaint
        value that happens to contain the same literal prefix string must
        never be touched (guards against an overreaching implementation)."""
        sessions = (
            SessionSlotSnapshot(
                1, "2026-06-01", {"chief_complaint": _SI_EXPRESSED_DENIAL_TEXT}
            ),
        )
        inp = _minimal_input({}, all_sessions=sessions)
        out = assemble_handoff_report(inp)
        row = next(r for r in out.slot_overview.rows if r.key == "chief_complaint")
        assert row.latest_value.startswith("자살/자해 사고 표현 있음")


# ── Item 4: near-ceiling caveat + flat-delta trend fix ──────────────────


class TestNearCeilingCaveat:
    def test_exact_ceiling_still_triggers(self) -> None:
        assert f5_module._ceiling_caveat(27, 27) is not None

    def test_one_point_below_ceiling_now_triggers(self) -> None:
        assert f5_module._ceiling_caveat(26, 27) is not None

    def test_two_points_below_ceiling_does_not_trigger(self) -> None:
        assert f5_module._ceiling_caveat(25, 27) is None

    def test_none_inputs_still_none(self) -> None:
        assert f5_module._ceiling_caveat(None, 27) is None
        assert f5_module._ceiling_caveat(26, None) is None


class TestNearCeilingFlatOverride:
    def test_flat_at_max_forces_unchanged(self) -> None:
        direction, note = f4_module._near_ceiling_flat_override(
            "worsened", [(1, 27.0), (2, 26.0), (3, 27.0)], 27
        )
        assert direction == "unchanged"
        assert note is not None

    def test_flat_one_below_max_forces_unchanged(self) -> None:
        direction, note = f4_module._near_ceiling_flat_override(
            "worsened", [(1, 26.0), (2, 25.0), (3, 26.0)], 27
        )
        assert direction == "unchanged"
        assert note is not None

    def test_flat_not_near_ceiling_untouched(self) -> None:
        direction, note = f4_module._near_ceiling_flat_override(
            "worsened", [(1, 10.0), (2, 15.0), (3, 10.0)], 27
        )
        assert direction == "worsened"
        assert note is None

    def test_non_flat_delta_untouched_even_near_ceiling(self) -> None:
        direction, note = f4_module._near_ceiling_flat_override(
            "worsened", [(1, 27.0), (2, 20.0)], 27
        )
        assert direction == "worsened"
        assert note is None

    def test_already_unchanged_is_a_noop(self) -> None:
        direction, note = f4_module._near_ceiling_flat_override(
            "unchanged", [(1, 27.0), (2, 27.0)], 27
        )
        assert direction == "unchanged"
        assert note is None

    def test_missing_max_score_is_a_noop(self) -> None:
        direction, note = f4_module._near_ceiling_flat_override(
            "worsened", [(1, 27.0), (2, 26.0), (3, 27.0)], None
        )
        assert direction == "worsened"
        assert note is None


class TestScaleTrendVerdictNearCeilingIntegration:
    def test_flat_26_to_26_never_worsened(self) -> None:
        """The CVR-028-cited defect shape: flat first-vs-last at 26 (near
        PHQ-9's own 27-point ceiling) with an asymmetric mid-series wobble
        that would otherwise produce a nonzero slope (and thus a
        'worsened' direction via `_first_last_slope_trend`'s slope-
        fallback) must render 'unchanged' instead."""
        points = [
            ScaleSeriesPoint(
                session_index=i, simulated_date=f"2026-0{i}-01", scale_name="PHQ-9",
                administered=True, total_score=score, max_score=27, severity="severe",
            )
            for i, score in enumerate([26, 25, 27, 26], start=1)
        ]
        # Sanity: without the override, this series' slope-fallback would
        # have produced a non-"unchanged" direction (proves the test
        # fixture actually exercises the override, not a vacuous case).
        comparable = [(p.session_index, float(p.total_score)) for p in points]
        pre_override_direction, _ = f4_module._first_last_slope_trend(
            comparable, higher_is_better=False, label="PHQ-9"
        )
        assert pre_override_direction != "unchanged"

        verdict = f4_module._scale_trend_verdict("PHQ-9", points)
        assert verdict.direction == "unchanged"
        assert any("NEAR-CEILING" in e for e in verdict.evidence)

    def test_flat_not_near_ceiling_unaffected_by_override(self) -> None:
        """A flat-delta series NOT near ceiling keeps its pre-existing
        slope-fallback behavior (this fix's scope is near-ceiling only)."""
        points = [
            ScaleSeriesPoint(
                session_index=i, simulated_date=f"2026-0{i}-01", scale_name="PHQ-9",
                administered=True, total_score=score, max_score=27, severity="moderate",
            )
            for i, score in enumerate([10, 15, 10], start=1)
        ]
        verdict = f4_module._scale_trend_verdict("PHQ-9", points)
        # slope over (10,15,10) is 0 (symmetric) -> unchanged anyway here,
        # but no NEAR-CEILING override note should be present.
        assert not any("NEAR-CEILING" in e for e in verdict.evidence)


# ── Item 5: VP-002 headline-body consistency ────────────────────────────


class _FakeRiskSafety:
    longitudinal_risk_signals: list = []
    risk_assessment_present = False


class _FakeQuestionnaire:
    present = False
    ceiling_caveat = None


class TestKeyConcernsHeadlineConsistency:
    def test_worsened_direction_forces_honest_line(self) -> None:
        lon = LongitudinalAnalysisOutput(
            vp_id="VP-002", n_sessions=10, overall_direction="worsened",
        )
        concerns = _key_concerns(_FakeRiskSafety(), _FakeQuestionnaire(), lon)
        assert "특이 우려 사항 없음" not in concerns
        assert any("추세 판정 혼재" in c for c in concerns)

    def test_non_worsened_direction_keeps_no_concerns_default(self) -> None:
        lon = LongitudinalAnalysisOutput(
            vp_id="VP-001", n_sessions=10, overall_direction="improved",
        )
        concerns = _key_concerns(_FakeRiskSafety(), _FakeQuestionnaire(), lon)
        assert concerns == ["특이 우려 사항 없음"]

    def test_unknown_direction_keeps_no_concerns_default(self) -> None:
        lon = LongitudinalAnalysisOutput(
            vp_id="VP-003", n_sessions=1, overall_direction="unknown",
        )
        concerns = _key_concerns(_FakeRiskSafety(), _FakeQuestionnaire(), lon)
        assert concerns == ["특이 우려 사항 없음"]
