"""Trend plotter tests — long-term clinical line charts with event markers.

Tests plot generation with realistic multi-visit VP data (6-12+ visits),
clinical events (medication changes, crises), edge cases, and output format.
"""

from __future__ import annotations

import base64

from src.services.trend_plotter import (
    ClinicalEvent,
    NamedSeriesPoint,
    TrendDataPoint,
    generate_domain_trend_plot,
    generate_similarity_trend_plot,
    generate_trend_plot,
    generate_trend_plot_base64,
)

# ── VP-002 이준호: 8 visits over 6 months, improving ─────────────────

VP002_LONGTERM = [
    TrendDataPoint(date="2026-04-01", phq9=14, gad7=8, ctrs=4, sentiment=-0.50),
    TrendDataPoint(date="2026-04-15", phq9=13, gad7=7, ctrs=4, sentiment=-0.45),
    TrendDataPoint(date="2026-05-06", phq9=12, gad7=6, ctrs=4, sentiment=-0.40),
    TrendDataPoint(date="2026-05-27", phq9=10, gad7=6, ctrs=4, sentiment=-0.25),
    TrendDataPoint(date="2026-06-17", phq9=8,  gad7=5, ctrs=5, sentiment=-0.10),
    TrendDataPoint(date="2026-07-08", phq9=7,  gad7=5, ctrs=5, sentiment=0.05),
    TrendDataPoint(date="2026-08-05", phq9=6,  gad7=4, ctrs=5, sentiment=0.15),
    TrendDataPoint(date="2026-09-02", phq9=5,  gad7=4, ctrs=5, sentiment=0.20),
]

VP002_EVENTS = [
    ClinicalEvent(date="2026-04-01", label="Escitalopram 10mg started", event_type="medication"),
    ClinicalEvent(date="2026-05-27", label="Dose maintained, sleep improving", event_type="other"),
    ClinicalEvent(date="2026-07-08", label="Social activities resumed", event_type="other"),
    ClinicalEvent(date="2026-09-02", label="Consider maintenance phase", event_type="other"),
]

# ── VP-004 최하은: 10 visits over 5 months, worsening ────────────────

VP004_LONGTERM = [
    TrendDataPoint(date="2026-02-10", phq9=10, gad7=8,  ctrs=4, sentiment=-0.20),
    TrendDataPoint(date="2026-03-03", phq9=12, gad7=9,  ctrs=4, sentiment=-0.25),
    TrendDataPoint(date="2026-03-17", phq9=14, gad7=10, ctrs=4, sentiment=-0.30),
    TrendDataPoint(date="2026-04-01", phq9=15, gad7=11, ctrs=4, sentiment=-0.40),
    TrendDataPoint(date="2026-04-14", phq9=14, gad7=10, ctrs=4, sentiment=-0.35),
    TrendDataPoint(date="2026-05-05", phq9=16, gad7=12, ctrs=3, sentiment=-0.50),
    TrendDataPoint(date="2026-05-10", phq9=18, gad7=14, ctrs=3, sentiment=-0.65),
    TrendDataPoint(date="2026-05-20", phq9=17, gad7=13, ctrs=3, sentiment=-0.60),
    TrendDataPoint(date="2026-06-17", phq9=19, gad7=15, ctrs=3, sentiment=-0.70),
    TrendDataPoint(date="2026-07-15", phq9=21, gad7=16, ctrs=3, sentiment=-0.80),
]

VP004_EVENTS = [
    ClinicalEvent(date="2026-03-17", label="Sertraline 50mg started", event_type="medication"),
    ClinicalEvent(date="2026-04-01", label="Severe nausea/vomiting", event_type="other"),
    ClinicalEvent(date="2026-04-14", label="Switch: Escitalopram 10mg", event_type="medication"),
    ClinicalEvent(date="2026-05-10", label="ER: Panic attack (119)", event_type="crisis"),
    ClinicalEvent(
        date="2026-05-20",
        label="Escitalopram 20mg + Alprazolam",
        event_type="medication",
    ),
    ClinicalEvent(date="2026-07-15", label="Referral: treatment resistance", event_type="other"),
]

# ── Short 2-visit for backward compat ────────────────────────────────

VP002_SHORT = [
    TrendDataPoint(date="2026-05-06", phq9=12, gad7=6, ctrs=4, sentiment=-0.4),
    TrendDataPoint(date="2026-06-25", phq9=7,  gad7=5, ctrs=5, sentiment=0.2),
]


class TestLongTermPlotGeneration:
    """Long-term (6+ visits) plot generation with clinical events."""

    def test_vp002_8visit_generates(self):
        result = generate_trend_plot(
            VP002_LONGTERM, patient_name="VP-002", events=VP002_EVENTS,
        )
        assert result is not None
        assert result.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(result.png_bytes) > 50_000  # substantial chart

    def test_vp004_10visit_generates(self):
        result = generate_trend_plot(
            VP004_LONGTERM, patient_name="VP-004", events=VP004_EVENTS,
        )
        assert result is not None
        assert len(result.png_bytes) > 50_000

    def test_vp002_longterm_larger_than_short(self):
        """8-visit plot should be more detailed than 2-visit."""
        long_r = generate_trend_plot(VP002_LONGTERM, events=VP002_EVENTS)
        short_r = generate_trend_plot(VP002_SHORT)
        assert long_r is not None and short_r is not None
        # Long-term chart has more data → generally larger file
        assert long_r.width_px >= short_r.width_px

    def test_events_dont_crash_without_data(self):
        """Events with no matching visit dates should still render."""
        data = [TrendDataPoint(date="2026-06-01", phq9=10)]
        events = [ClinicalEvent(date="2026-07-01", label="Future event", event_type="medication")]
        result = generate_trend_plot(data, events=events)
        assert result is not None

    def test_many_events_render(self):
        """12+ events should render without overlap crash."""
        data = VP004_LONGTERM
        events = VP004_EVENTS + [
            ClinicalEvent(date="2026-03-10", label="Blood test", event_type="other"),
            ClinicalEvent(date="2026-04-08", label="Therapy session 1", event_type="other"),
            ClinicalEvent(date="2026-04-22", label="Therapy session 2", event_type="other"),
            ClinicalEvent(date="2026-05-15", label="Family meeting", event_type="other"),
            ClinicalEvent(date="2026-06-01", label="Therapy session 5", event_type="other"),
            ClinicalEvent(date="2026-06-30", label="Insurance review", event_type="other"),
        ]
        result = generate_trend_plot(data, events=events)
        assert result is not None


class TestClinicalEventTypes:
    """Verify different event types are handled."""

    def test_medication_event(self):
        data = VP002_SHORT
        events = [ClinicalEvent(date="2026-05-06", label="SSRI started", event_type="medication")]
        result = generate_trend_plot(data, events=events)
        assert result is not None

    def test_crisis_event(self):
        data = VP002_SHORT
        events = [ClinicalEvent(date="2026-06-01", label="ER visit", event_type="crisis")]
        result = generate_trend_plot(data, events=events)
        assert result is not None

    def test_hospitalization_event(self):
        data = VP002_SHORT
        events = [ClinicalEvent(date="2026-06-01", label="Admitted", event_type="hospitalization")]
        result = generate_trend_plot(data, events=events)
        assert result is not None

    def test_custom_color_event(self):
        data = VP002_SHORT
        events = [
            ClinicalEvent(
                date="2026-06-01",
                label="Custom",
                event_type="other",
                color="#FF5722",
            )
        ]
        result = generate_trend_plot(data, events=events)
        assert result is not None


class TestBackwardCompatibility:
    """Existing short-timeline tests still pass."""

    def test_2visit_still_works(self):
        result = generate_trend_plot(VP002_SHORT)
        assert result is not None
        assert result.png_bytes[:4] == b"\x89PNG"

    def test_single_visit(self):
        data = [TrendDataPoint(date="2026-06-25", phq9=12, gad7=8, ctrs=4)]
        result = generate_trend_plot(data)
        assert result is not None

    def test_partial_data(self):
        data = [
            TrendDataPoint(date="2026-05-06", phq9=14),
            TrendDataPoint(date="2026-06-25", phq9=21),
        ]
        result = generate_trend_plot(data)
        assert result is not None

    def test_sentiment_only(self):
        data = [
            TrendDataPoint(date="2026-05-06", sentiment=-0.6),
            TrendDataPoint(date="2026-06-25", sentiment=-0.2),
        ]
        result = generate_trend_plot(data)
        assert result is not None

    def test_empty_returns_none(self):
        assert generate_trend_plot([]) is None

    def test_all_none_returns_none(self):
        assert generate_trend_plot([TrendDataPoint(date="2026-06-25")]) is None

    def test_base64_roundtrip(self):
        result = generate_trend_plot(VP002_SHORT)
        assert result is not None
        decoded = base64.b64decode(result.base64_str)
        assert decoded[:4] == b"\x89PNG"

    def test_base64_convenience(self):
        b64 = generate_trend_plot_base64(VP002_SHORT, "test")
        assert b64 is not None
        assert len(b64) > 100


# ── F4 quick-dev extensions (`_archive/plans/f4_quick_dev_plan.md` §5.2, wave 5) ──


class TestSlotFillPanel:
    """Chart 5 extension — `TrendDataPoint.slot_fill_count`."""

    def test_slot_fill_panel_renders(self):
        data = [
            TrendDataPoint(date="2026-01-01", phq9=13, slot_fill_count=4),
            TrendDataPoint(date="2026-01-08", phq9=10, slot_fill_count=6),
            TrendDataPoint(date="2026-01-15", phq9=8, slot_fill_count=8),
        ]
        result = generate_trend_plot(data)
        assert result is not None
        assert result.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_slot_fill_only_series_renders(self):
        data = [
            TrendDataPoint(date="2026-01-01", slot_fill_count=2),
            TrendDataPoint(date="2026-01-08", slot_fill_count=5),
        ]
        result = generate_trend_plot(data)
        assert result is not None

    def test_no_slot_fill_field_unaffected(self):
        """Backward compat: omitting slot_fill_count entirely (every
        pre-F4 caller) behaves exactly as before — no extra panel."""
        result = generate_trend_plot(VP002_SHORT)
        assert result is not None


class TestSimilarityAndDomainTrendCharts:
    """Charts 3-4 — new multi-series line-chart functions."""

    def test_similarity_trend_plot_renders_for_recurring_disease(self):
        points = [
            NamedSeriesPoint(date="2026-01-01", name="우울 삽화(우울증)", value=0.45),
            NamedSeriesPoint(date="2026-01-08", name="우울 삽화(우울증)", value=0.52),
            NamedSeriesPoint(date="2026-01-15", name="우울 삽화(우울증)", value=0.60),
            NamedSeriesPoint(date="2026-01-01", name="범불안장애", value=0.40),
        ]
        result = generate_similarity_trend_plot(points, patient_name="VP-001")
        assert result is not None
        assert result.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_similarity_trend_plot_none_when_nothing_recurs(self):
        points = [
            NamedSeriesPoint(date="2026-01-01", name="우울 삽화(우울증)", value=0.45),
            NamedSeriesPoint(date="2026-01-01", name="범불안장애", value=0.40),
        ]
        # Each disease appears in only 1 distinct session -> below
        # min_sessions=2 default -> nothing plottable -> None, not a crash.
        result = generate_similarity_trend_plot(points)
        assert result is None

    def test_domain_trend_plot_renders_for_recurring_domain(self):
        points = [
            NamedSeriesPoint(date="2026-01-01", name="anxiety", value=0.6),
            NamedSeriesPoint(date="2026-01-08", name="anxiety", value=0.7),
        ]
        result = generate_domain_trend_plot(points, patient_name="VP-001")
        assert result is not None

    def test_domain_trend_plot_empty_list_is_none(self):
        assert generate_domain_trend_plot([]) is None


# ── Small-multiples refactor (17-point spec) ─────────────────────────

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from src.services.trend_plotter import (  # noqa: E402
    MetricSpec,
    TrendPlotResult,
    _build_figure,
    _build_metric_specs,
    _prepare_metric_values,
    build_trend_chart_payload,
    summarize_change,
)


def _opts(**over):
    base = dict(
        connect_missing=False, missing_connection_style="dashed", x_axis_mode="date",
        annotation_mode="key_points", show_delta_annotations=False, ctrs_display_mode="step",
        slot_fill_max=8, audit_c_threshold=None, include_figure_title=False,
        include_patient_name=False, title="t", patient_name="p", figsize=(9, 8.5),
    )
    base.update(over)
    return base


class TestMissingValues:
    """Req 1: missing → numpy.nan, line breaks at gaps, no interpolation."""

    def test_missing_become_nan_full_length(self):
        dps = [TrendDataPoint("2026-01-01", phq9=22),
               TrendDataPoint("2026-02-01", phq9=None),
               TrendDataPoint("2026-03-01", phq9=None),
               TrendDataPoint("2026-04-01", phq9=18)]
        vals = _prepare_metric_values(dps, "phq9")
        assert len(vals) == 4
        assert vals[0] == 22 and vals[3] == 18
        assert np.isnan(vals[1]) and np.isnan(vals[2])

    def test_gap_breaks_line_no_solid_s1_s4(self):
        import matplotlib.pyplot as plt
        dps = [TrendDataPoint("2026-01-01", phq9=22),
               TrendDataPoint("2026-02-01", phq9=None),
               TrendDataPoint("2026-03-01", phq9=None),
               TrendDataPoint("2026-04-01", phq9=18)]
        fig, axes = _build_figure(dps, [], _opts())
        ydata = np.concatenate([ln.get_ydata() for ln in axes["phq9"].get_lines()
                                if len(ln.get_ydata()) == 4])
        assert np.isnan(ydata).any()  # nan segment → no continuous S1..S4 line
        plt.close(fig)

    def test_connect_missing_opt_adds_overlay(self):
        import matplotlib.pyplot as plt
        dps = [TrendDataPoint("2026-01-01", phq9=22),
               TrendDataPoint("2026-02-01", phq9=None),
               TrendDataPoint("2026-04-01", phq9=18)]
        off = _build_figure(dps, [], _opts(connect_missing=False))
        on = _build_figure(dps, [], _opts(connect_missing=True))
        assert len(on[1]["phq9"].get_lines()) > len(off[1]["phq9"].get_lines())
        plt.close(off[0])
        plt.close(on[0])


class TestCTRSPanel:
    """Req 5: step render, 1 at bottom / 5 at top, no invert."""

    def test_step_orientation_low_at_bottom(self):
        import matplotlib.pyplot as plt
        dps = [TrendDataPoint("2026-01-01", ctrs=3),
               TrendDataPoint("2026-02-01", ctrs=4),
               TrendDataPoint("2026-03-01", ctrs=4)]
        fig, axes = _build_figure(dps, [], _opts())
        ax = axes["ctrs"]
        lo, hi = ax.get_ylim()
        assert lo < hi and lo < 1 and hi > 5  # ascending, not inverted
        assert list(ax.get_yticks()) == [1, 2, 3, 4, 5]
        labels = [t.get_text() for t in ax.get_yticklabels()]
        assert labels[0].startswith("1") and "안정" in labels[-1]
        plt.close(fig)

    def test_ctrs_values_not_fabricated(self):
        dps = [TrendDataPoint("2026-01-01", ctrs=3),
               TrendDataPoint("2026-02-01", ctrs=None),
               TrendDataPoint("2026-03-01", ctrs=4)]
        vals = _prepare_metric_values(dps, "ctrs")
        assert vals[0] == 3 and np.isnan(vals[1]) and vals[2] == 4


class TestAuditCPanel:
    """Req 2: 2 points → compact; 3+ → line; no fabricated values."""

    def test_two_points_compact_no_fabrication(self):
        dps = [TrendDataPoint(f"2026-0{i + 1}-01") for i in range(6)]
        dps += [TrendDataPoint("2026-07-01", audit_c=11),
                TrendDataPoint("2026-08-01", audit_c=10)]
        specs = {s.key: s for s in _build_metric_specs(
            dps, slot_fill_max=8, audit_c_threshold=None)}
        assert specs["audit_c"].display_type == "compact"
        vals = _prepare_metric_values(dps, "audit_c")
        assert list(vals[~np.isnan(vals)]) == [11.0, 10.0]  # only the real values

    def test_three_points_line_mode(self):
        dps = [TrendDataPoint("2026-01-01", audit_c=8),
               TrendDataPoint("2026-02-01", audit_c=6),
               TrendDataPoint("2026-03-01", audit_c=4)]
        specs = {s.key: s for s in _build_metric_specs(
            dps, slot_fill_max=8, audit_c_threshold=None)}
        assert specs["audit_c"].display_type == "line"


class TestPanelPresence:
    """Req 17d,e: single measurement OK, absent metric → no panel."""

    def test_single_measurement_no_error(self):
        r = generate_trend_plot([TrendDataPoint("2026-01-01", phq9=15)])
        assert isinstance(r, TrendPlotResult) and len(r.png_bytes) > 0

    def test_absent_metric_has_no_panel(self):
        import matplotlib.pyplot as plt
        dps = [TrendDataPoint("2026-01-01", phq9=10),
               TrendDataPoint("2026-02-01", phq9=8)]
        fig, axes = _build_figure(dps, [], _opts())
        assert "phq9" in axes
        assert not ({"gad7", "ctrs", "audit_c"} & set(axes))
        plt.close(fig)


class TestOutputFormats:
    """Req 12: png / svg / both."""

    @pytest.mark.parametrize(("fmt", "has_png", "has_svg"), [
        ("png", True, False), ("svg", False, True), ("both", True, True)])
    def test_output_format(self, fmt, has_png, has_svg):
        dps = [TrendDataPoint("2026-01-01", phq9=20),
               TrendDataPoint("2026-02-01", phq9=12)]
        r = generate_trend_plot(dps, output_format=fmt)
        assert (len(r.png_bytes) > 0) is has_png
        assert (r.svg_bytes is not None and len(r.svg_bytes) > 0) is has_svg


class TestChartPayload:
    """Req 14: JSON-serializable, None preserved."""

    def test_payload_preserves_none(self):
        import json
        dps = [TrendDataPoint("2026-01-01", phq9=22, ctrs=3, sentiment=None, slot_fill_count=5),
               TrendDataPoint("2026-02-01", phq9=None, ctrs=None, audit_c=9)]
        evs = [ClinicalEvent("2026-01-15", "약물 시작", "medication")]
        payload = build_trend_chart_payload(dps, evs)
        s0, s1 = payload["sessions"]
        assert s0["phq9"] == 22 and s0["sentiment"] is None
        assert s1["phq9"] is None and s1["ctrs"] is None and s1["audit_c"] == 9
        assert payload["events"][0]["event_type"] == "medication"
        json.dumps(payload)  # serializable


class TestNewOutputBackCompat:
    """Req 16: new args/fields default; legacy fields present."""

    def test_old_positional_signature(self):
        dps = [TrendDataPoint("2026-01-01", phq9=20, ctrs=2),
               TrendDataPoint("2026-02-01", phq9=10, ctrs=4)]
        r = generate_trend_plot(dps, "홍길동", "종단 추이", None)
        assert isinstance(r, TrendPlotResult) and r.png_bytes and r.base64_str

    def test_datapoint_without_audit_c(self):
        assert TrendDataPoint("2026-01-01", phq9=10).audit_c is None

    def test_result_has_legacy_and_new_fields(self):
        r = generate_trend_plot([TrendDataPoint("2026-01-01", phq9=20),
                                 TrendDataPoint("2026-02-01", phq9=15)])
        for attr in ("png_bytes", "base64_str", "width_px", "height_px", "svg_bytes"):
            assert hasattr(r, attr)


class TestSummarizeChange:
    """Req 11: neutral within same band, direction across bands."""

    _SPEC = MetricSpec("phq9", "PHQ-9", 0, 27,
                       [(0, 4, "정상"), (5, 9, "경도"), (10, 14, "중등도"),
                        (15, 19, "중등–중증"), (20, 27, "중증")], "line", True)

    def test_same_band_is_neutral(self):
        dps = [TrendDataPoint("2026-01-01", phq9=21), TrendDataPoint("2026-02-01", phq9=20)]
        assert summarize_change(dps, "phq9", self._SPEC)["state"] == "neutral"

    def test_improved_across_bands(self):
        dps = [TrendDataPoint("2026-01-01", phq9=22), TrendDataPoint("2026-02-01", phq9=8)]
        s = summarize_change(dps, "phq9", self._SPEC)
        assert s["state"] == "improved" and s["delta"] == -14


class TestEventTimelineAndAxis:
    """Req 3, 8: dedicated event row; session x-axis mode."""

    def test_event_row_present(self):
        import matplotlib.pyplot as plt
        dps = [TrendDataPoint("2026-01-01", phq9=20), TrendDataPoint("2026-03-01", phq9=12)]
        evs = [ClinicalEvent("2026-01-15", "설트랄린 시작", "medication"),
               ClinicalEvent("2026-02-01", "위기 개입", "crisis"),
               ClinicalEvent("2026-02-20", "재평가", "assessment")]
        fig, axes = _build_figure(dps, evs, _opts())
        assert "_events" in axes
        plt.close(fig)

    def test_session_axis_mode(self):
        import matplotlib.pyplot as plt
        dps = [TrendDataPoint("2026-01-01", phq9=20), TrendDataPoint("2026-02-01", phq9=12)]
        fig, axes = _build_figure(dps, [], _opts(x_axis_mode="session"))
        labels = [t.get_text() for t in fig.axes[-1].get_xticklabels()]
        assert any(lbl.startswith("S") for lbl in labels)
        plt.close(fig)
