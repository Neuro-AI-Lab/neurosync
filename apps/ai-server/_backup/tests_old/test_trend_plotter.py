"""Trend plotter tests — long-term clinical line charts with event markers.

Tests plot generation with realistic multi-visit VP data (6-12+ visits),
clinical events (medication changes, crises), edge cases, and output format.
"""

from __future__ import annotations

import base64

import pytest

from src.services.trend_plotter import (
    ClinicalEvent,
    TrendDataPoint,
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
    ClinicalEvent(date="2026-05-20", label="Escitalopram 20mg + Alprazolam", event_type="medication"),
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
        events = [ClinicalEvent(date="2026-06-01", label="Custom", event_type="other", color="#FF5722")]
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
