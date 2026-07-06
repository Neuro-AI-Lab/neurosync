"""Longitudinal trend plotter — clinical line charts for handoff reports.

Produces a multi-panel figure tracking PHQ-9, GAD-7, CTRS, and sentiment
polarity across an extended treatment timeline (6-12+ visits over months).

Features:
- Date-based X axis with proper time spacing
- Severity zone shading (color-coded risk bands)
- Delta annotations between consecutive visits
- Clinical event markers (medication changes, crisis events, hospitalizations)
- Phase annotations (treatment phases separated by vertical lines)
- Supports 1 to 20+ data points

Output: PNG bytes (or base64) for embedding in PDF/JSON handoff reports.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClinicalEvent:
    """A clinical event to mark on the timeline."""

    date: str                                          # ISO date
    label: str                                         # e.g. "Escitalopram 10mg started"
    event_type: str = "medication"                     # medication | crisis | hospitalization | other
    color: str = ""                                    # auto-assigned if empty


@dataclass
class TrendDataPoint:
    """Single visit data point for trend plotting."""

    date: str                                          # ISO date string, e.g. "2026-04-14"
    phq9: Optional[int] = None
    gad7: Optional[int] = None
    ctrs: Optional[int] = None
    sentiment: Optional[float] = None
    label: str = ""                                    # e.g. "Visit 1", "F/U 3"


@dataclass
class TrendPlotResult:
    """Result of trend plot generation."""

    png_bytes: bytes
    base64_str: str
    width_px: int
    height_px: int


# ── Severity zone definitions ──────────────────────────────────────

_PHQ9_ZONES = [
    (0, 4, "#E8F5E9", "Minimal"),
    (5, 9, "#FFF9C4", "Mild"),
    (10, 14, "#FFE0B2", "Moderate"),
    (15, 19, "#FFCCBC", "Mod. Severe"),
    (20, 27, "#FFCDD2", "Severe"),
]

_GAD7_ZONES = [
    (0, 4, "#E8F5E9", "Minimal"),
    (5, 9, "#FFF9C4", "Mild"),
    (10, 14, "#FFE0B2", "Moderate"),
    (15, 21, "#FFCDD2", "Severe"),
]

_CTRS_ZONES = [
    (1, 1, "#FFCDD2", "Emergency"),
    (2, 2, "#FFCCBC", "High Risk"),
    (3, 3, "#FFE0B2", "Acute"),
    (4, 4, "#FFF9C4", "Moderate"),
    (5, 5, "#E8F5E9", "Stable"),
]

_EVENT_COLORS = {
    "medication": "#9C27B0",
    "crisis": "#D32F2F",
    "hospitalization": "#E65100",
    "other": "#607D8B",
}


def generate_trend_plot(
    data_points: list[TrendDataPoint],
    patient_name: str = "",
    title: str = "Longitudinal Trend Report",
    events: list[ClinicalEvent] | None = None,
    figsize: tuple[float, float] = (14, 12),
    dpi: int = 150,
) -> Optional[TrendPlotResult]:
    """Generate a multi-panel longitudinal trend chart.

    Args:
        data_points: Visit data points in chronological order (2-20+).
        patient_name: Patient name/ID for the title.
        title: Figure title.
        events: Clinical events (med changes, crises) to mark on timeline.
        figsize: Figure size in inches.
        dpi: Resolution.

    Returns:
        TrendPlotResult or None on failure.
    """
    try:
        return _render_plot(data_points, patient_name, title, events or [], figsize, dpi)
    except ImportError:
        logger.warning("matplotlib not installed — trend plot skipped")
        return None
    except Exception as exc:
        logger.warning("Trend plot generation failed: %s", exc)
        return None


def generate_trend_plot_base64(
    data_points: list[TrendDataPoint],
    patient_name: str = "",
    events: list[ClinicalEvent] | None = None,
) -> Optional[str]:
    """Convenience wrapper returning just the base64 string."""
    result = generate_trend_plot(data_points, patient_name, events=events)
    return result.base64_str if result else None


# ── Internal rendering ─────────────────────────────────────────────

def _parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.now()


def _render_plot(
    data_points: list[TrendDataPoint],
    patient_name: str,
    title: str,
    events: list[ClinicalEvent],
    figsize: tuple[float, float],
    dpi: int,
) -> TrendPlotResult:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.ticker as ticker
    import matplotlib.font_manager as fm

    # Korean font
    for fpath in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]:
        try:
            fm.fontManager.addfont(fpath)
            plt.rcParams["font.family"] = fm.FontProperties(fname=fpath).get_name()
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

    if len(data_points) < 1:
        raise ValueError("Need at least 1 data point")

    # Parse dates for proper time-based X axis
    dates = [_parse_date(dp.date) for dp in data_points]
    event_dates = [_parse_date(e.date) for e in events]

    # Determine panels
    has_phq9 = any(dp.phq9 is not None for dp in data_points)
    has_gad7 = any(dp.gad7 is not None for dp in data_points)
    has_ctrs = any(dp.ctrs is not None for dp in data_points)
    has_sentiment = any(dp.sentiment is not None for dp in data_points)

    panels: list[tuple] = []
    if has_phq9:
        panels.append(("PHQ-9 (Depression)", [dp.phq9 for dp in data_points], _PHQ9_ZONES, 0, 27, False))
    if has_gad7:
        panels.append(("GAD-7 (Anxiety)", [dp.gad7 for dp in data_points], _GAD7_ZONES, 0, 21, False))
    if has_ctrs:
        panels.append(("CTRS (Crisis Triage)", [dp.ctrs for dp in data_points], _CTRS_ZONES, 1, 5, True))
    if has_sentiment:
        panels.append(("Sentiment Polarity", [dp.sentiment for dp in data_points], [], -1.0, 1.0, False))

    if not panels:
        raise ValueError("No plottable data")

    n_panels = len(panels)
    # Add extra row for event timeline if events exist
    has_event_row = len(events) > 0
    n_rows = n_panels + (1 if has_event_row else 0)

    height_ratios = [3] * n_panels + ([1] if has_event_row else [])
    fig, axes = plt.subplots(
        n_rows, 1, figsize=figsize, squeeze=False,
        gridspec_kw={"height_ratios": height_ratios},
    )

    fig.suptitle(
        f"{title}\n{patient_name}" if patient_name else title,
        fontsize=14, fontweight="bold", y=0.98,
    )

    # Determine if dates are far enough apart for date formatting
    use_date_axis = len(dates) >= 2 and (max(dates) - min(dates)).days > 7
    many_points = len(data_points) > 5

    for idx, (panel_title, values, zones, y_min, y_max, invert) in enumerate(panels):
        ax = axes[idx, 0]
        _draw_panel(
            ax, dates, values, zones, y_min, y_max, panel_title,
            invert, use_date_axis, many_points, events, event_dates,
        )

    # Event timeline row
    if has_event_row:
        _draw_event_timeline(axes[n_panels, 0], dates, events, event_dates, use_date_axis)

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    png_bytes = buf.getvalue()

    return TrendPlotResult(
        png_bytes=png_bytes,
        base64_str=base64.b64encode(png_bytes).decode("ascii"),
        width_px=int(figsize[0] * dpi),
        height_px=int(figsize[1] * dpi),
    )


def _draw_panel(
    ax, dates, values, zones, y_min, y_max, panel_title,
    invert, use_date_axis, many_points, events, event_dates,
):
    import matplotlib.dates as mdates
    import matplotlib.ticker as ticker

    x_vals = dates if use_date_axis else list(range(len(dates)))

    # Severity zones
    for zone_lo, zone_hi, color, zone_label in zones:
        ax.axhspan(zone_lo - 0.5, zone_hi + 0.5, alpha=0.2, color=color, zorder=0)
        # Zone labels on the right
        ax.text(
            1.01, (zone_lo + zone_hi) / (2 * (y_max if not isinstance(y_max, float) else 1)),
            zone_label, fontsize=7, alpha=0.5, ha="left", va="center",
            transform=ax.get_yaxis_transform(),
        )

    # Sentiment special shading
    if panel_title == "Sentiment Polarity":
        ax.axhline(y=0, color="gray", linestyle="--", alpha=0.4, linewidth=0.8)
        ax.axhspan(0, 1.0, alpha=0.06, color="#4CAF50")
        ax.axhspan(-1.0, 0, alpha=0.06, color="#F44336")

    # Plot line
    valid_pairs = [(x, v) for x, v in zip(x_vals, values) if v is not None]
    if not valid_pairs:
        return
    vx, vy = zip(*valid_pairs)

    ax.plot(
        vx, vy,
        marker="o", markersize=6 if many_points else 8, linewidth=2,
        color="#1565C0", markerfacecolor="#1565C0",
        markeredgecolor="white", markeredgewidth=1.2, zorder=5,
    )

    # Data labels — smart placement to avoid overlap on dense charts
    show_all_labels = len(vx) <= 8
    for i, (xi, yi) in enumerate(zip(vx, vy)):
        if show_all_labels or i == 0 or i == len(vx) - 1 or i % 3 == 0:
            label = f"{yi}" if isinstance(yi, int) else f"{yi:.2f}"
            offset_y = 10 if not invert else -14
            ax.annotate(
                label, (xi, yi),
                textcoords="offset points", xytext=(0, offset_y),
                fontsize=8 if many_points else 9,
                fontweight="bold", ha="center", color="#1565C0",
                zorder=15,
            )

    # Delta annotations — show between every pair if few points, every other if many
    step = 1 if len(vx) <= 6 else 2
    for i in range(1, len(vx), step):
        delta = vy[i] - vy[i - 1]
        if delta == 0:
            continue

        is_improvement = (
            (panel_title.startswith("PHQ") or panel_title.startswith("GAD")) and delta < 0
        ) or (
            panel_title.startswith("CTRS") and delta > 0
        ) or (
            panel_title.startswith("Sentiment") and delta > 0
        )
        color = "#2E7D32" if is_improvement else "#C62828"

        if isinstance(delta, float):
            delta_str = f"{delta:+.2f}"
        else:
            delta_str = f"{delta:+d}"

        arrow = "\u2193" if is_improvement else "\u2191"

        # Position delta box at midpoint
        if use_date_axis:
            mid_x = vx[i - 1] + (vx[i] - vx[i - 1]) / 2
        else:
            mid_x = (vx[i - 1] + vx[i]) / 2
        mid_y = (vy[i - 1] + vy[i]) / 2

        ax.annotate(
            f"{arrow}{delta_str}",
            (mid_x, mid_y),
            fontsize=8 if many_points else 9,
            fontweight="bold", color=color,
            ha="center", va="bottom",
            bbox=dict(
                boxstyle="round,pad=0.2", facecolor="white",
                edgecolor=color, alpha=0.85, linewidth=0.8,
            ),
            zorder=10,
        )

    # Event markers on this panel (vertical dashed lines)
    for ev, ed in zip(events, event_dates):
        ev_x = ed if use_date_axis else _find_nearest_x(dates, ed, list(range(len(dates))))
        c = ev.color or _EVENT_COLORS.get(ev.event_type, "#607D8B")
        ax.axvline(x=ev_x, color=c, linestyle=":", alpha=0.5, linewidth=1, zorder=2)

    # Axis formatting
    ax.set_title(panel_title, fontsize=11, fontweight="bold", loc="left", pad=8)

    if use_date_axis:
        span_days = (max(dates) - min(dates)).days
        if span_days > 180:
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        elif span_days > 60:
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        else:
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.tick_params(axis="x", rotation=45, labelsize=7)
    else:
        ax.set_xticks(list(range(len(dates))))
        ax.set_xticklabels([d.strftime("%Y-%m-%d") for d in dates], fontsize=7, rotation=45)

    ax.set_ylabel("Score" if "Sentiment" not in panel_title else "Polarity", fontsize=9)

    if isinstance(y_min, float):
        ax.set_ylim(y_min - 0.1, y_max + 0.1)
    else:
        ax.set_ylim(y_min - 1, y_max + 1)

    ax.grid(axis="y", alpha=0.2, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if invert:
        ax.invert_yaxis()
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))


def _draw_event_timeline(ax, dates, events, event_dates, use_date_axis):
    """Draw the clinical event timeline row at the bottom."""
    import matplotlib.dates as mdates

    ax.set_title("Clinical Events", fontsize=10, fontweight="bold", loc="left", pad=4)

    if use_date_axis:
        ax.set_xlim(min(dates), max(dates))
    else:
        ax.set_xlim(-0.5, len(dates) - 0.5)

    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    # Draw events as colored markers with labels
    y_positions = [0.7, 0.4, 0.7, 0.4]  # Alternate heights to reduce overlap
    for i, (ev, ed) in enumerate(zip(events, event_dates)):
        c = ev.color or _EVENT_COLORS.get(ev.event_type, "#607D8B")
        x_pos = ed if use_date_axis else _find_nearest_x(dates, ed, list(range(len(dates))))
        y_pos = y_positions[i % len(y_positions)]

        # Marker symbol by type
        marker = {"medication": "D", "crisis": "X", "hospitalization": "s", "other": "o"}.get(
            ev.event_type, "o"
        )
        ax.plot(x_pos, y_pos, marker=marker, markersize=10, color=c, zorder=5)

        ax.annotate(
            ev.label, (x_pos, y_pos),
            textcoords="offset points",
            xytext=(5, 8 if y_pos > 0.5 else -14),
            fontsize=7, color=c, fontweight="bold",
            ha="left", va="bottom" if y_pos > 0.5 else "top",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor=c, alpha=0.8, linewidth=0.6),
            zorder=10,
        )

    if use_date_axis:
        span_days = (max(dates) - min(dates)).days
        if span_days > 180:
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        else:
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.tick_params(axis="x", rotation=45, labelsize=7)


def _find_nearest_x(dates, target, x_vals):
    """Find the x position nearest to a target date."""
    diffs = [abs((d - target).total_seconds()) for d in dates]
    idx = diffs.index(min(diffs))
    return x_vals[idx]
