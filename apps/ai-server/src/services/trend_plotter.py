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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_FONT_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"


def _korean_font_candidates() -> list[str]:
    """Hangul-capable font files, bundled SHA-pinned assets first so charts
    render Korean labels on any host, then common system locations."""
    return [
        str(_FONT_ASSET_DIR / "NotoSansKR-Subset.ttf"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]

logger = logging.getLogger(__name__)


@dataclass
class ClinicalEvent:
    """A clinical event to mark on the timeline."""

    date: str                                          # ISO date
    label: str                                         # e.g. "Escitalopram 10mg started"
    event_type: str = "medication"  # medication | crisis | hospitalization | other
    color: str = ""                                    # auto-assigned if empty


@dataclass
class TrendDataPoint:
    """Single visit data point for trend plotting."""

    date: str                                          # ISO date string, e.g. "2026-04-14"
    phq9: int | None = None
    gad7: int | None = None
    ctrs: int | None = None
    sentiment: float | None = None
    label: str = ""                                    # e.g. "Visit 1", "F/U 3"
    # F4 quick-dev (`_archive/plans/f4_quick_dev_plan.md` §5.2 chart 5, wave 5):
    # 0..12 count of `QUESTIONABLE_SLOT_KEYS` filled this session. Smallest-
    # footprint extension — reuses `_draw_panel`/zones/axis code unchanged,
    # same shape as the `sentiment` panel above (`zones=[]`, fixed y-range).
    slot_fill_count: int | None = None


@dataclass
class TrendPlotResult:
    """Result of trend plot generation."""

    png_bytes: bytes
    base64_str: str
    width_px: int
    height_px: int


# ── Severity zone definitions (Korean labels — clinician-facing) ────

_PHQ9_ZONES = [
    (0, 4, "#E8F5E9", "최소"),
    (5, 9, "#FFF9C4", "경도"),
    (10, 14, "#FFE0B2", "중등도"),
    (15, 19, "#FFCCBC", "중등도-중증"),
    (20, 27, "#FFCDD2", "중증"),
]

_GAD7_ZONES = [
    (0, 4, "#E8F5E9", "최소"),
    (5, 9, "#FFF9C4", "경도"),
    (10, 14, "#FFE0B2", "중등도"),
    (15, 21, "#FFCDD2", "중증"),
]

_CTRS_ZONES = [
    (1, 1, "#FFCDD2", "최긴급"),
    (2, 2, "#FFCCBC", "고위험"),
    (3, 3, "#FFE0B2", "급성"),
    (4, 4, "#FFF9C4", "중등도"),
    (5, 5, "#E8F5E9", "안정"),
]

_EVENT_COLORS = {
    "medication": "#9C27B0",
    "crisis": "#D32F2F",
    "hospitalization": "#E65100",
    "other": "#607D8B",
}

# ── Clinician-readable font sizes at PDF embed scale ─────────────────
#
# BUG (user report, F5 hand-off PDF): chart captions/labels were too small
# to read once embedded. Root cause: `f5_report.build_pdf_report` embeds
# these PNGs at a fixed physical size (`reportlab.Image`, cm units) that is
# much smaller than the matplotlib figure's own physical size
# (`figsize` inches @ `dpi`) — the EFFECTIVE printed point size of any
# on-figure text is `original_fontsize_pt * (embed_width_in / figsize_
# width_in)`, independent of `dpi` (dpi only affects raster sharpness, not
# the physical/point size once reportlab is told an explicit target
# width/height).
#
# This module's `figsize` defaults were narrowed (14in/12in wide multi-
# panel + 12in/6in named-series -> 9in-wide for both, see
# `generate_trend_plot`/`_render_named_series_plot` defaults below) to
# line up with `f5_report.py`'s embed box (`width=17cm` — computed from
# A4 usable width 18cm minus a small margin buffer). That gives a SINGLE
# shared scale factor for every chart this module produces:
#
#     scale = 17cm / (9in * 2.54cm/in) = 17 / 22.86 ≈ 0.744
#
# Font constants below are chosen so `effective_pt = constant * scale`
# clears "≥10-11pt effective" for ticks/axis labels, higher for titles —
# e.g. _TICK_FONTSIZE=15 -> 15*0.744≈11.2pt effective; _TITLE_FONTSIZE=26
# -> 26*0.744≈19.3pt effective. If `f5_report.py`'s embed box width or
# this module's `figsize` width changes, recompute `scale` and re-derive
# these constants — they are NOT arbitrary.
_TITLE_FONTSIZE = 26      # figure suptitle
_PANEL_TITLE_FONTSIZE = 20   # per-panel title (left-aligned)
_AXIS_LABEL_FONTSIZE = 17   # y-axis label
_TICK_FONTSIZE = 15         # x/y tick labels
_LEGEND_FONTSIZE = 16       # named-series chart legend
_DATA_LABEL_FONTSIZE = 14   # on-line value annotations (dense charts: -1)
_DELTA_LABEL_FONTSIZE = 13  # delta-between-visits boxes (dense charts: -1)
_ZONE_LABEL_FONTSIZE = 11   # right-margin severity-zone labels (secondary)
_EVENT_TITLE_FONTSIZE = 16  # "임상 사건" row title
_EVENT_LABEL_FONTSIZE = 12  # per-event marker label
_CAPTION_FONTSIZE = 12      # on-figure low-confidence-cue caption


def generate_trend_plot(
    data_points: list[TrendDataPoint],
    patient_name: str = "",
    title: str = "종단 추이 보고서",
    events: list[ClinicalEvent] | None = None,
    figsize: tuple[float, float] = (9, 12),
    dpi: int = 150,
) -> TrendPlotResult | None:
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
) -> str | None:
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
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    # Korean font — bundled SHA-pinned assets first (portable: macOS/slim
    # containers have neither /usr/share path, which silently degraded every
    # Hangul label to missing glyphs), system fonts as fallback.
    for fpath in _korean_font_candidates():
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
    has_slot_fill = any(dp.slot_fill_count is not None for dp in data_points)

    # Each panel: (display_title_ko, values, zones, y_min, y_max, invert, kind).
    # `kind` drives display-agnostic logic (sentiment shading, delta-
    # improvement direction, y-axis label) that previously string-matched
    # the (now-Korean) `panel_title` — never couple logic to display text.
    panels: list[tuple] = []
    if has_phq9:
        panels.append(
            ("PHQ-9 (우울)", [dp.phq9 for dp in data_points], _PHQ9_ZONES, 0, 27, False, "phq9")
        )
    if has_gad7:
        panels.append(
            ("GAD-7 (불안)", [dp.gad7 for dp in data_points], _GAD7_ZONES, 0, 21, False, "gad7")
        )
    if has_ctrs:
        panels.append(
            (
                "위기 단계 (CTRS)",
                [dp.ctrs for dp in data_points],
                _CTRS_ZONES,
                1,
                5,
                True,
                "ctrs",
            )
        )
    if has_sentiment:
        panels.append(
            (
                "정서 극성 (감성 점수)",
                [dp.sentiment for dp in data_points],
                [],
                -1.0,
                1.0,
                False,
                "sentiment",
            )
        )
    if has_slot_fill:
        panels.append(
            (
                "문진 항목 충족도 (F4)",
                [dp.slot_fill_count for dp in data_points],
                [],
                0,
                12,
                False,
                "slot_fill",
            )
        )

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
        fontsize=_TITLE_FONTSIZE, fontweight="bold", y=0.98,
    )

    # Determine if dates are far enough apart for date formatting
    use_date_axis = len(dates) >= 2 and (max(dates) - min(dates)).days > 7
    many_points = len(data_points) > 5

    for idx, (panel_title, values, zones, y_min, y_max, invert, kind) in enumerate(panels):
        ax = axes[idx, 0]
        _draw_panel(
            ax, dates, values, zones, y_min, y_max, panel_title, kind,
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
    ax, dates, values, zones, y_min, y_max, panel_title, kind,
    invert, use_date_axis, many_points, events, event_dates,
):
    import matplotlib.dates as mdates
    import matplotlib.ticker as ticker

    x_vals = dates if use_date_axis else list(range(len(dates)))

    # Severity zones
    for zone_lo, zone_hi, color, zone_label in zones:
        ax.axhspan(zone_lo - 0.5, zone_hi + 0.5, alpha=0.2, color=color, zorder=0)
        # Zone labels on the right, vertically centered on the zone's own
        # DATA-coordinate band. BUG (pre-existing, exposed by this
        # mission's larger `_ZONE_LABEL_FONTSIZE`): `ax.get_yaxis_
        # transform()` keeps the y-component in DATA units (only x is
        # axes-fraction) — the old `/ (y_max if not isinstance(y_max,
        # float) else 1)` divisor was a leftover normalize-to-[0,1]
        # attempt that only canceled out for the float-y_max sentiment
        # panel (divisor=1, no zones there anyway); every int-y_max panel
        # (PHQ-9/GAD-7/CTRS, the only ones with non-empty `zones`) had
        # every zone label compressed into a sliver near data-y ~0-1,
        # overlapping unreadably once the font size increased. Fixed to
        # the zone's actual data-y center — matches `axhspan` above.
        ax.text(
            1.01, (zone_lo + zone_hi) / 2,
            zone_label, fontsize=_ZONE_LABEL_FONTSIZE, alpha=0.75, ha="left", va="center",
            transform=ax.get_yaxis_transform(),
        )

    # Sentiment special shading
    if kind == "sentiment":
        ax.axhline(y=0, color="gray", linestyle="--", alpha=0.4, linewidth=0.8)
        ax.axhspan(0, 1.0, alpha=0.06, color="#4CAF50")
        ax.axhspan(-1.0, 0, alpha=0.06, color="#F44336")

    # Plot line
    valid_pairs = [(x, v) for x, v in zip(x_vals, values, strict=False) if v is not None]
    if not valid_pairs:
        return
    vx, vy = zip(*valid_pairs, strict=False)

    ax.plot(
        vx, vy,
        marker="o", markersize=6 if many_points else 8, linewidth=2,
        color="#1565C0", markerfacecolor="#1565C0",
        markeredgecolor="white", markeredgewidth=1.2, zorder=5,
    )

    # Data labels — smart placement to avoid overlap on dense charts
    show_all_labels = len(vx) <= 8
    data_label_fontsize = _DATA_LABEL_FONTSIZE - 1 if many_points else _DATA_LABEL_FONTSIZE
    for i, (xi, yi) in enumerate(zip(vx, vy, strict=False)):
        if show_all_labels or i == 0 or i == len(vx) - 1 or i % 3 == 0:
            label = f"{yi}" if isinstance(yi, int) else f"{yi:.2f}"
            offset_y = 10 if not invert else -14
            ax.annotate(
                label, (xi, yi),
                textcoords="offset points", xytext=(0, offset_y),
                fontsize=data_label_fontsize,
                fontweight="bold", ha="center", color="#1565C0",
                zorder=15,
            )

    # Delta annotations — show between every pair if few points, every other if many
    step = 1 if len(vx) <= 6 else 2
    delta_label_fontsize = _DELTA_LABEL_FONTSIZE - 1 if many_points else _DELTA_LABEL_FONTSIZE
    for i in range(1, len(vx), step):
        delta = vy[i] - vy[i - 1]
        if delta == 0:
            continue

        is_improvement = (
            (kind in ("phq9", "gad7")) and delta < 0
        ) or (
            kind == "ctrs" and delta > 0
        ) or (
            kind == "sentiment" and delta > 0
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
            fontsize=delta_label_fontsize,
            fontweight="bold", color=color,
            ha="center", va="bottom",
            bbox=dict(
                boxstyle="round,pad=0.2", facecolor="white",
                edgecolor=color, alpha=0.85, linewidth=0.8,
            ),
            zorder=10,
        )

    # Event markers on this panel (vertical dashed lines)
    for ev, ed in zip(events, event_dates, strict=False):
        ev_x = ed if use_date_axis else _find_nearest_x(dates, ed, list(range(len(dates))))
        c = ev.color or _EVENT_COLORS.get(ev.event_type, "#607D8B")
        ax.axvline(x=ev_x, color=c, linestyle=":", alpha=0.5, linewidth=1, zorder=2)

    # Axis formatting
    ax.set_title(panel_title, fontsize=_PANEL_TITLE_FONTSIZE, fontweight="bold", loc="left", pad=8)

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
        ax.tick_params(axis="x", rotation=45, labelsize=_TICK_FONTSIZE)
    else:
        ax.set_xticks(list(range(len(dates))))
        ax.set_xticklabels(
            [d.strftime("%Y-%m-%d") for d in dates], fontsize=_TICK_FONTSIZE, rotation=45
        )
    ax.tick_params(axis="y", labelsize=_TICK_FONTSIZE)

    ax.set_ylabel("점수" if kind != "sentiment" else "극성", fontsize=_AXIS_LABEL_FONTSIZE)

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

    ax.set_title("임상 사건", fontsize=_EVENT_TITLE_FONTSIZE, fontweight="bold", loc="left", pad=4)

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
    for i, (ev, ed) in enumerate(zip(events, event_dates, strict=False)):
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
            fontsize=_EVENT_LABEL_FONTSIZE, color=c, fontweight="bold",
            ha="left", va="bottom" if y_pos > 0.5 else "top",
            bbox=dict(
                boxstyle="round,pad=0.15",
                facecolor="white",
                edgecolor=c,
                alpha=0.8,
                linewidth=0.6,
            ),
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
        ax.tick_params(axis="x", rotation=45, labelsize=_TICK_FONTSIZE)


def _find_nearest_x(dates, target, x_vals):
    """Find the x position nearest to a target date."""
    diffs = [abs((d - target).total_seconds()) for d in dates]
    idx = diffs.index(min(diffs))
    return x_vals[idx]


# ── F4 multi-series trend charts (`_archive/plans/f4_quick_dev_plan.md` §5.2
#    charts 3-4, wave 5) ────────────────────────────────────────────────
#
# Disease-similarity (chart 3) / domain-confidence (chart 4) are
# fundamentally N-series-per-date, unlike every panel above (1 value per
# date) — new functions rather than forcing them through `_draw_panel`.


@dataclass
class NamedSeriesPoint:
    """One (date, name, value) datum for a multi-series line chart — F2
    `disease_candidate_series`/`domain_candidate_series` points."""

    date: str
    name: str
    value: float


def generate_similarity_trend_plot(
    points: list[NamedSeriesPoint],
    patient_name: str = "",
    title: str = "질환 유사도 추이 (F4, 질환별)",
    min_sessions: int = 2,
    figsize: tuple[float, float] = (9, 5.5),
    dpi: int = 150,
) -> TrendPlotResult | None:
    """F4 chart 3: one line per disease name recurring in >= `min_sessions`
    distinct sessions. VAL-014 inherited (design doc §5.3 item 5 / CVR-020
    Finding 10, Rec 6): y-axis label reads "similarity score"(유사도 점수) —
    NEVER "probability"/"confidence"(확률/가능성/신뢰도) (REV-013 §4 binding
    rule) — and every line is rendered dashed + low-opacity with an
    on-chart caption, an ON-CHART low-confidence visual cue (not merely
    accompanying text)."""
    try:
        return _render_named_series_plot(
            points, patient_name, title, min_sessions, figsize, dpi,
            y_label="유사도 점수 (참고용, 확률 아님)",
            caption=(
                "VAL-014(미해결): F2 질환 후보 산출의 타당성이 아직 검증되지 않았습니다 — "
                "이 추이는 노이즈가 포함된 입력을 기반으로 계산되며, 임상적 추이 해석 "
                "용도로 사용할 수 없습니다."
            ),
        )
    except ImportError:
        logger.warning("matplotlib not installed — similarity trend plot skipped")
        return None
    except Exception as exc:
        logger.warning("Similarity trend plot generation failed: %s", exc)
        return None


def generate_domain_trend_plot(
    points: list[NamedSeriesPoint],
    patient_name: str = "",
    title: str = "진료과 후보 신뢰도 추이 (F4, 진료과별)",
    min_sessions: int = 2,
    figsize: tuple[float, float] = (9, 5.5),
    dpi: int = 150,
) -> TrendPlotResult | None:
    """F4 chart 4: one line per `DomainName` recurring in >= `min_sessions`
    distinct sessions. `confidence` is the schema's own field name — never
    relabeled "probability"(확률)."""
    try:
        return _render_named_series_plot(
            points, patient_name, title, min_sessions, figsize, dpi,
            y_label="신뢰도 (domain_candidates.confidence)",
            caption=None,
        )
    except ImportError:
        logger.warning("matplotlib not installed — domain trend plot skipped")
        return None
    except Exception as exc:
        logger.warning("Domain trend plot generation failed: %s", exc)
        return None


def _render_named_series_plot(
    points: list[NamedSeriesPoint],
    patient_name: str,
    title: str,
    min_sessions: int,
    figsize: tuple[float, float],
    dpi: int,
    *,
    y_label: str,
    caption: str | None,
) -> TrendPlotResult:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

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

    by_name: dict[str, list[tuple[datetime, float]]] = {}
    for p in points:
        by_name.setdefault(p.name, []).append((_parse_date(p.date), p.value))
    recurring = {
        name: sorted(vals, key=lambda t: t[0])
        for name, vals in by_name.items()
        if len({d for d, _ in vals}) >= min_sessions
    }
    if not recurring:
        raise ValueError("No name recurs in >= min_sessions distinct sessions — nothing to plot")

    fig, ax = plt.subplots(figsize=figsize)
    fig.suptitle(
        f"{title}\n{patient_name}" if patient_name else title,
        fontsize=_TITLE_FONTSIZE, fontweight="bold",
    )

    cmap = plt.get_cmap("tab10")
    for i, (name, vals) in enumerate(sorted(recurring.items())):
        xs = [d for d, _ in vals]
        ys = [v for _, v in vals]
        ax.plot(
            xs, ys, marker="o", markersize=5, linewidth=1.5, linestyle="--", alpha=0.55,
            color=cmap(i % 10), label=name,
        )

    ax.set_ylabel(y_label, fontsize=_AXIS_LABEL_FONTSIZE)
    ax.set_ylim(-0.05, 1.05)
    ax.grid(axis="y", alpha=0.2, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # Legend BELOW the axes, not "upper left" over the data (BUG, exposed
    # by this mission's larger `_LEGEND_FONTSIZE`: the old in-plot corner
    # legend grew large enough to cover most of the chart's own data —
    # unreadable in a different way than "too small"). `ncol` wraps long
    # Korean disease/domain-name lists into a few rows instead of one long
    # unreadable column.
    n_series = len(recurring)
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.30), fontsize=_LEGEND_FONTSIZE,
        framealpha=0.9, ncol=2 if n_series > 2 else 1,
    )
    ax.tick_params(axis="y", labelsize=_TICK_FONTSIZE)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.tick_params(axis="x", rotation=45, labelsize=_TICK_FONTSIZE)

    caption_text = (
        "점선·저채도 선 = 낮은 신뢰도 시각 신호. " + (caption or "")
    ).strip()
    fig.text(
        0.5, 0.02, caption_text, fontsize=_CAPTION_FONTSIZE, color="#B00020",
        ha="center", va="bottom", wrap=True,
    )

    # Explicit top/bottom margins (not `tight_layout`'s auto-fit) — the
    # legend now sits BELOW the axes (moved out of the plot area, see
    # above) and needs a reserved band sized to `figsize`, not whatever
    # `tight_layout` infers from the (empty at draw time) legend bbox.
    fig.subplots_adjust(top=0.78, bottom=0.40, left=0.13, right=0.97)

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
