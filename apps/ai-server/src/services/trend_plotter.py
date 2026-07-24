"""Longitudinal trend plotter — editorial small-multiples for handoff reports.

Renders PHQ-9 / GAD-7 / AUDIT-C / CTRS + secondary indicators (sentiment,
questionnaire completeness) as vertically-aligned small multiples on a
shared time axis, tuned for embedding in an A4 clinical hand-off PDF.

Design principles (clinician-facing, editorial):
- Missing sessions are held as ``numpy.nan`` — never forward-filled or
  interpolated; the trend line breaks at a gap unless ``connect_missing``.
- Clinical panels (PHQ-9/AUDIT-C/CTRS) sit above lower-hierarchy secondary
  indicators (sentiment sparkline, completion strip).
- CTRS is an ordinal 1–5 stage (1 위험 … 5 안정, low at bottom) — never a
  smooth line by default.
- Restrained teal/neutral palette; red reserved for real risk/worsening.
- No figure title / patient-name by default (the PDF body carries those).

Public API (backward-compatible): ``generate_trend_plot``,
``generate_trend_plot_base64``, ``generate_similarity_trend_plot``,
``generate_domain_trend_plot``; ``TrendPlotResult.png_bytes`` /
``.base64_str`` retained. New args/fields all have defaults.
No clinical-diagnostic logic and no interpolation is introduced.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Data models ─────────────────────────────────────────────────────

@dataclass
class ClinicalEvent:
    """A clinical event to mark on the shared timeline."""

    date: str                                          # ISO date
    label: str
    # medication | crisis | hospitalization | assessment | life_event | other
    event_type: str = "medication"
    color: str = ""                                    # auto if empty


@dataclass
class TrendDataPoint:
    """Single session data point. New fields keep back-compat defaults."""

    date: str                                          # ISO date string
    phq9: int | None = None
    gad7: int | None = None
    ctrs: int | None = None
    audit_c: int | None = None                         # 0–12 (new; back-compat)
    sentiment: float | None = None
    label: str = ""
    slot_fill_count: int | None = None


@dataclass
class TrendPlotResult:
    """Result of trend plot generation. ``svg_bytes`` added (back-compat)."""

    png_bytes: bytes
    base64_str: str
    width_px: int
    height_px: int
    svg_bytes: bytes | None = None


@dataclass
class MetricSpec:
    """Declarative spec for one metric panel — replaces the old panel tuple.
    Logic keys off ``key``/spec, never the display ``title``."""

    key: str
    title: str
    y_min: float
    y_max: float
    zones: list = field(default_factory=list)
    display_type: str = "line"     # line | step | points | sparkline | strip | compact
    lower_is_better: bool | None = None
    integer_ticks: bool = True
    show_in_main: bool = True
    y_tick_labels: dict | None = None   # {value: label} for ordinal axes


@dataclass
class NamedSeriesPoint:
    """One (date, name, value) datum for a multi-series line chart."""

    date: str
    name: str
    value: float


# ── Palette (report teal / neutral; red = real risk only) ───────────

PRIMARY = "#174F4C"
SECONDARY = "#687572"
GRID = "#DCE2E0"
TEXT = "#27302E"
MUTED = "#7A8582"
HIGH_RISK = "#A44A3F"
WARNING = "#A97823"

# Low-chroma severity bands (name → fill). alpha applied at draw.
_PHQ9_ZONES = [
    (0, 4, "정상"), (5, 9, "경도"), (10, 14, "중등도"),
    (15, 19, "중등–중증"), (20, 27, "중증"),
]
_GAD7_ZONES = [
    (0, 4, "정상"), (5, 9, "경도"), (10, 14, "중등도"), (15, 21, "중증"),
]
# clay alpha per band index (subtle → stronger toward severe)
_ZONE_ALPHA = [0.0, 0.045, 0.075, 0.11, 0.15]

_CTRS_TICK_LABELS = {1: "1 최긴급", 2: "2 고위험", 3: "3 급성", 4: "4 준안정", 5: "5 안정"}

_EVENT_MARKER = {
    "medication": "o", "crisis": "X", "hospitalization": "s",
    "assessment": "^", "life_event": "D", "other": ".",
}
_EVENT_COLORS = {
    "medication": PRIMARY, "crisis": HIGH_RISK, "hospitalization": WARNING,
    "assessment": SECONDARY, "life_event": SECONDARY, "other": MUTED,
}

# Font sizes (effective ≈ constant * embed-scale ~0.74 at 17cm/9in).
_FS_PANEL_TITLE = 12
_FS_AXIS = 9.5
_FS_TICK = 9
_FS_DATA = 9
_FS_ZONE = 7.5
_FS_EVENT = 8.5
_FS_CAPTION = 8
_FS_FIGTITLE = 15


def _fonts():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt
    for fp in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
               "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
        try:
            fm.fontManager.addfont(fp)
            plt.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False


def _parse_date(s: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.now()


# ── Metric spec + value preparation ─────────────────────────────────

def _build_metric_specs(
    data_points: list[TrendDataPoint], *, slot_fill_max: int, audit_c_threshold: int | None,
) -> list[MetricSpec]:
    """Specs for metrics that actually have >=1 measured value, in report order:
    PHQ-9, GAD-7, AUDIT-C, CTRS, sentiment(secondary), completion(secondary)."""
    def present(key):
        return any(getattr(dp, key) is not None for dp in data_points)

    specs: list[MetricSpec] = []
    if present("phq9"):
        specs.append(MetricSpec("phq9", "PHQ-9 (우울)", 0, 27, _PHQ9_ZONES, "line", True))
    if present("gad7"):
        specs.append(MetricSpec("gad7", "GAD-7 (불안)", 0, 21, _GAD7_ZONES, "line", True))
    if present("audit_c"):
        n = sum(1 for dp in data_points if dp.audit_c is not None)
        specs.append(MetricSpec(
            "audit_c", "AUDIT-C (음주)", 0, 12, [], "line" if n >= 3 else "compact", True))
    if present("ctrs"):
        specs.append(MetricSpec(
            "ctrs", "위기 단계 (CTRS)", 1, 5, [], "step", None,
            y_tick_labels=_CTRS_TICK_LABELS))
    if present("sentiment"):
        specs.append(MetricSpec(
            "sentiment", "정서 극성 · 보조 지표 · 임상 척도 아님", -1.0, 1.0, [],
            "sparkline", None, integer_ticks=False, show_in_main=False))
    if present("slot_fill_count"):
        specs.append(MetricSpec(
            "slot_fill_count", "문진 항목 충족도 · 데이터 수집 완성도(임상 상태 아님)",
            0, slot_fill_max, [], "strip", None, show_in_main=False))
    return specs


def _prepare_metric_values(data_points: list[TrendDataPoint], key: str):
    """Full per-session array with numpy.nan for missing (no fill/interp)."""
    import numpy as np
    out = []
    for dp in data_points:
        v = getattr(dp, key)
        out.append(np.nan if v is None else float(v))
    return np.array(out, dtype=float)


def summarize_change(data_points: list[TrendDataPoint], key: str, spec: MetricSpec) -> dict | None:
    """Baseline→latest numeric change + neutral/clinical category note.
    No diagnosis — 'category' is the severity-band name from the spec."""
    vals = [getattr(dp, key) for dp in data_points if getattr(dp, key) is not None]
    if not vals:
        return None
    fv, lv = vals[0], vals[-1]
    delta = lv - fv

    def band(v):
        return next((z[2] for z in spec.zones if z[0] <= v <= z[1]), None)

    fb, lb = band(fv), band(lv)
    if delta == 0 or (spec.zones and fb == lb):
        state = "neutral"           # same band / no change → clinically ambiguous
    elif spec.lower_is_better is None:
        state = "changed"
    else:
        improved = (delta < 0) == spec.lower_is_better
        state = "improved" if improved else "worsened"
    return {"baseline": fv, "latest": lv, "delta": delta,
            "baseline_category": fb, "latest_category": lb, "state": state}


# ── Public API ──────────────────────────────────────────────────────

def generate_trend_plot(
    data_points: list[TrendDataPoint],
    patient_name: str = "",
    title: str = "종단 추이 보고서",
    events: list[ClinicalEvent] | None = None,
    figsize: tuple[float, float] = (9, 8.5),
    dpi: int = 180,
    *,
    connect_missing: bool = False,
    missing_connection_style: str = "dashed",
    x_axis_mode: str = "date",              # "date" | "session"
    annotation_mode: str = "key_points",    # "none" | "key_points" | "all"
    show_delta_annotations: bool = False,
    ctrs_display_mode: str = "step",        # "step" | "points"
    slot_fill_max: int = 8,
    audit_c_threshold: int | None = None,
    include_figure_title: bool = False,
    include_patient_name: bool = False,
    output_format: str = "png",             # "png" | "svg" | "both"
    x_tick_labels: list[str] | None = None,  # session-mode: label each position (e.g. dates)
) -> TrendPlotResult | None:
    """Generate the small-multiples longitudinal chart. See module docstring.

    ``x_tick_labels`` (session mode only): per-session bottom-axis labels — use
    real dates so unevenly-spaced sessions render at equal positions yet still
    carry their date, avoiding date-axis crowding when early visits cluster."""
    try:
        opts = dict(
            connect_missing=connect_missing, missing_connection_style=missing_connection_style,
            x_axis_mode=x_axis_mode, annotation_mode=annotation_mode,
            show_delta_annotations=show_delta_annotations, ctrs_display_mode=ctrs_display_mode,
            slot_fill_max=slot_fill_max, audit_c_threshold=audit_c_threshold,
            include_figure_title=include_figure_title, include_patient_name=include_patient_name,
            title=title, patient_name=patient_name, figsize=figsize, x_tick_labels=x_tick_labels,
        )
        import matplotlib.pyplot as plt
        fig, _axes = _build_figure(data_points, events or [], opts)
        if fig is None:
            return None
        png, svg = _save_figure(fig, dpi, output_format)
        plt.close(fig)
        return TrendPlotResult(
            png_bytes=png or b"",
            base64_str=base64.b64encode(png).decode("ascii") if png else "",
            width_px=int(figsize[0] * dpi), height_px=int(figsize[1] * dpi),
            svg_bytes=svg,
        )
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
    """Convenience wrapper returning just the base64 PNG string."""
    result = generate_trend_plot(data_points, patient_name, events=events)
    return result.base64_str if result else None


def build_trend_chart_payload(
    data_points: list[TrendDataPoint], events: list[ClinicalEvent] | None = None,
) -> dict:
    """JSON-serializable payload for future dynamic (ECharts/Vega-Lite) charts.
    ``None`` values are preserved verbatim; no rendering/interaction here."""
    return {
        "sessions": [
            {
                "date": dp.date, "label": dp.label or f"S{i + 1}",
                "phq9": dp.phq9, "gad7": dp.gad7, "audit_c": dp.audit_c,
                "ctrs": dp.ctrs, "sentiment": dp.sentiment,
                "slot_fill_count": dp.slot_fill_count,
            }
            for i, dp in enumerate(data_points)
        ],
        "events": [
            {"date": e.date, "label": e.label, "event_type": e.event_type}
            for e in (events or [])
        ],
    }


# ── Figure assembly ─────────────────────────────────────────────────

_PANEL_H = {"line": 1.6, "compact": 1.2, "step": 1.55, "sparkline": 0.85, "strip": 0.8}


def _build_figure(data_points: list[TrendDataPoint], events: list[ClinicalEvent], opts: dict):
    """Returns (fig, axes_map{key:ax}). axes_map used by tests. None if no data."""
    import matplotlib.pyplot as plt
    import numpy as np  # noqa: F401 (used by helpers)
    _fonts()

    if len(data_points) < 1:
        raise ValueError("Need at least 1 data point")
    specs = _build_metric_specs(
        data_points, slot_fill_max=opts["slot_fill_max"],
        audit_c_threshold=opts["audit_c_threshold"])
    has_events = len(events) > 0
    if not specs and not has_events:
        raise ValueError("No plottable data")

    # x positions
    dates = [_parse_date(dp.date) for dp in data_points]
    session_mode = opts["x_axis_mode"] == "session"
    x = list(range(len(data_points))) if session_mode else dates
    ev_x = [_event_x(e, dates, x, session_mode) for e in events]

    # panel layout
    heights = [_PANEL_H.get(s.display_type, 2.0) for s in specs]
    if has_events:
        heights.append(1.25)
    total_h = sum(heights) + 0.6
    width = opts["figsize"][0]
    fig, axl = plt.subplots(
        len(heights), 1, figsize=(width, total_h), squeeze=False, sharex=True,
        gridspec_kw={"height_ratios": heights})
    axes = [row[0] for row in axl]
    fig.patch.set_alpha(0)

    if opts["include_figure_title"] or opts["include_patient_name"]:
        t = opts["title"] if opts["include_figure_title"] else ""
        if opts["include_patient_name"] and opts["patient_name"]:
            t = f"{t}\n{opts['patient_name']}".strip()
        if t:
            fig.suptitle(t, fontsize=_FS_FIGTITLE, fontweight="bold", color=TEXT, y=0.995)

    axes_map: dict = {}
    for ax, spec in zip(axes, specs, strict=False):
        ax.set_facecolor("none")
        axes_map[spec.key] = ax
        if spec.display_type in ("line",):
            _draw_clinical_line_panel(ax, x, data_points, spec, events, ev_x, opts)
        elif spec.display_type == "compact":
            _draw_audit_c_panel(ax, x, data_points, spec, events, ev_x, opts)
        elif spec.display_type == "step":
            _draw_ctrs_panel(ax, x, data_points, spec, events, ev_x, opts)
        elif spec.display_type == "sparkline":
            _draw_sentiment_sparkline(ax, x, data_points, spec, ev_x)
        elif spec.display_type == "strip":
            _draw_completion_strip(ax, x, data_points, spec, opts["slot_fill_max"])

    if has_events:
        ev_ax = axes[-1]
        axes_map["_events"] = ev_ax
        _draw_event_timeline(ev_ax, x, events, ev_x)

    _format_shared_x_axis(axes, x, dates, session_mode, opts.get("x_tick_labels"))
    top = 0.93 if opts["include_figure_title"] else 0.965
    fig.subplots_adjust(left=0.11, right=0.9, top=top, bottom=0.07, hspace=0.32)
    return fig, axes_map


def _event_x(e: ClinicalEvent, dates, x, session_mode):
    ed = _parse_date(e.date)
    if not session_mode:
        return ed
    diffs = [abs((d - ed).total_seconds()) for d in dates]
    return x[diffs.index(min(diffs))] if diffs else 0


def _event_guides(ax, ev_x):
    """Faint vertical guide at each event date, aligned across every panel."""
    for ex in ev_x:
        ax.axvline(x=ex, color=SECONDARY, linestyle=(0, (2, 3)), alpha=0.18,
                   linewidth=0.8, zorder=1)


def _panel_frame(ax, spec):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
        ax.spines[s].set_linewidth(0.8)
    ax.grid(axis="y", color=GRID, linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=_FS_TICK, colors=TEXT, length=0)
    ax.set_title(spec.title, fontsize=_FS_PANEL_TITLE, fontweight="bold",
                 color=TEXT, loc="left", pad=6)


def _annot_indices(vals, mode):
    """Sessions to label: first, latest, and clinical extremum (key_points)."""
    import numpy as np
    idx = [i for i, v in enumerate(vals) if not np.isnan(v)]
    if not idx or mode == "none":
        return set()
    if mode == "all":
        return set(idx)
    keep = {idx[0], idx[-1]}
    ext = max(idx, key=lambda i: vals[i])   # highest (worst for symptom scales)
    keep.add(ext)
    return keep


def _draw_clinical_line_panel(ax, x, data_points, spec, events, ev_x, opts):
    import numpy as np
    vals = _prepare_metric_values(data_points, spec.key)
    # severity bands (low-chroma)
    for i, (lo, hi, _name) in enumerate(spec.zones):
        a = _ZONE_ALPHA[i] if i < len(_ZONE_ALPHA) else 0.15
        if a:
            ax.axhspan(lo - 0.5, hi + 0.5, color=HIGH_RISK, alpha=a, lw=0, zorder=0)
        ax.text(1.012, (lo + hi) / 2, _name, transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=_FS_ZONE, color=MUTED, clip_on=False)
    _event_guides(ax, ev_x)

    # 마커는 실측 세션에만. 선 처리는 세 가지:
    #  - connect_missing=False        → 결측에서 선이 끊김(값을 지어내지 않음, 기본)
    #  - connect_missing + style solid → 실측점끼리 하나의 추세선으로 연결(미측정은 관통)
    #  - connect_missing + style dashed/dotted → 끊긴 실선 + 결측 구간만 점선 브리지
    meas = [i for i in range(len(x)) if not np.isnan(vals[i])]
    if opts["connect_missing"]:
        xv = [x[i] for i in meas]
        yv = [vals[i] for i in meas]
        style = opts["missing_connection_style"]
        if style in ("solid", "line"):
            ax.plot(xv, yv, color=PRIMARY, linewidth=1.8, zorder=4)
        else:
            ax.plot(x, vals, color=PRIMARY, linewidth=1.8, zorder=4)
            ls = {"dashed": (0, (4, 2)), "dotted": (0, (1, 2))}.get(style, (0, (4, 2)))
            ax.plot(xv, yv, color=PRIMARY, linewidth=1.0, linestyle=ls, alpha=0.55, zorder=3)
    else:
        ax.plot(x, vals, color=PRIMARY, linewidth=1.8, zorder=4)

    # markers only on measured points; latest emphasized
    meas = [i for i in range(len(x)) if not np.isnan(vals[i])]
    for j, i in enumerate(meas):
        last = (j == len(meas) - 1)
        ax.plot(x[i], vals[i], marker="o", ms=6 if last else 4.5,
                mfc=PRIMARY, mec="white", mew=0.9, color=PRIMARY, zorder=6)

    # key-point value labels + neutral colouring within same band
    summ = summarize_change(data_points, spec.key, spec)
    for i in _annot_indices(vals, opts["annotation_mode"]):
        ax.annotate(f"{int(vals[i])}", (x[i], vals[i]), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=_FS_DATA, fontweight="bold",
                    color=PRIMARY, zorder=8)
    if opts["show_delta_annotations"] and summ and summ["delta"] != 0:
        col = {"improved": PRIMARY, "worsened": HIGH_RISK}.get(summ["state"], SECONDARY)
        ax.annotate(f"{summ['delta']:+d}", (x[meas[-1]], vals[meas[-1]]),
                    textcoords="offset points", xytext=(0, -14), ha="center",
                    fontsize=_FS_DATA, color=col, zorder=8)

    ax.set_ylim(spec.y_min - 1, spec.y_max + 1)
    ax.set_ylabel("점수", fontsize=_FS_AXIS, color=TEXT)
    _panel_frame(ax, spec)


def _draw_audit_c_panel(ax, x, data_points, spec, events, ev_x, opts):
    """<=2 measured points → compact two-point comparison (no long line)."""
    import numpy as np
    vals = _prepare_metric_values(data_points, spec.key)
    meas = [i for i in range(len(x)) if not np.isnan(vals[i])]
    _event_guides(ax, ev_x)
    xv = [x[i] for i in meas]
    yv = [vals[i] for i in meas]
    if len(meas) >= 2:
        ax.plot(xv, yv, color=PRIMARY, linewidth=1.4, linestyle=(0, (5, 2)),
                marker="o", ms=6, mfc=PRIMARY, mec="white", mew=0.9, zorder=5)
    elif meas:
        ax.plot(xv, yv, marker="o", ms=6, mfc=PRIMARY, mec="white", mew=0.9, color=PRIMARY)
    for i in meas:
        ax.annotate(f"{int(vals[i])}", (x[i], vals[i]), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=_FS_DATA, fontweight="bold",
                    color=PRIMARY, zorder=8)
    thr = opts["audit_c_threshold"]
    if thr is not None:
        ax.axhline(y=thr, color=WARNING, linestyle=(0, (2, 2)), alpha=0.6, linewidth=0.9)
        ax.text(1.012, thr, f"기준 {thr}", transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=_FS_ZONE, color=WARNING, clip_on=False)
    ax.set_ylim(spec.y_min - 0.5, spec.y_max + 0.5)
    ax.set_ylabel("점수", fontsize=_FS_AXIS, color=TEXT)
    _panel_frame(ax, spec)


def _draw_ctrs_panel(ax, x, data_points, spec, events, ev_x, opts):
    """Ordinal 1–5, 1 at bottom / 5 at top (NO invert). step or points."""
    import numpy as np
    vals = _prepare_metric_values(data_points, spec.key)
    _event_guides(ax, ev_x)
    if opts["ctrs_display_mode"] == "points":
        meas = [i for i in range(len(x)) if not np.isnan(vals[i])]
        ax.plot([x[i] for i in meas], [vals[i] for i in meas], linestyle="None",
                marker="s", ms=5.5, mfc="white", mec=PRIMARY, mew=1.4, zorder=5)
    else:
        ax.step(x, vals, where="post", color=PRIMARY, linewidth=1.6, zorder=4)
        meas = [i for i in range(len(x)) if not np.isnan(vals[i])]
        ax.plot([x[i] for i in meas], [vals[i] for i in meas], linestyle="None",
                marker="s", ms=4.5, mfc="white", mec=PRIMARY, mew=1.2, zorder=6)
    meas = [i for i in range(len(x)) if not np.isnan(vals[i])]
    for j, i in enumerate(meas):
        if j == 0 or j == len(meas) - 1:
            ax.annotate(f"{int(vals[i])}", (x[i], vals[i]), textcoords="offset points",
                        xytext=(0, 7), ha="center", fontsize=_FS_DATA, fontweight="bold",
                        color=PRIMARY, zorder=8)
    ax.set_ylim(spec.y_min - 0.5, spec.y_max + 0.5)   # 1 bottom … 5 top (no invert)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels([spec.y_tick_labels.get(v, str(v)) for v in [1, 2, 3, 4, 5]])
    ax.set_ylabel("단계", fontsize=_FS_AXIS, color=TEXT)
    _panel_frame(ax, spec)


def _draw_sentiment_sparkline(ax, x, data_points, spec, ev_x):
    import numpy as np
    vals = _prepare_metric_values(data_points, spec.key)
    ax.axhline(y=0, color=MUTED, linestyle=(0, (3, 3)), alpha=0.5, linewidth=0.8)
    ax.plot(x, vals, color=SECONDARY, linewidth=1.3, zorder=4)
    meas = [i for i in range(len(x)) if not np.isnan(vals[i])]
    for i in meas:
        ax.plot(x[i], vals[i], marker="o", ms=3, mfc=SECONDARY, mec="white",
                mew=0.6, color=SECONDARY)
    # label min + latest only
    if meas:
        lo = min(meas, key=lambda i: vals[i])
        for i in {lo, meas[-1]}:
            ax.annotate(f"{vals[i]:.2f}", (x[i], vals[i]), textcoords="offset points",
                        xytext=(0, 6), ha="center", fontsize=_FS_ZONE, color=SECONDARY)
    ax.set_ylim(-1.05, 1.05)
    ax.set_yticks([-1, 0, 1])
    ax.set_ylabel("극성", fontsize=_FS_AXIS, color=MUTED)
    _panel_frame(ax, spec)
    ax.title.set_color(MUTED)          # lower visual hierarchy
    ax.title.set_fontweight("normal")


def _draw_completion_strip(ax, x, data_points, spec, slot_fill_max):
    """Per-session completeness bars (filled/max) — a 데이터 수집 완성도 status
    ribbon aligned to the shared time axis, not a clinical line graph."""
    width = 6.0 if x and isinstance(x[0], datetime) else 0.5  # days | session units
    xs, fracs, labels = [], [], []
    for xi, dp in zip(x, data_points, strict=False):
        if dp.slot_fill_count is None:
            continue
        xs.append(xi)
        fracs.append(max(0.0, min(1.0, dp.slot_fill_count / slot_fill_max)) if slot_fill_max else 0)
        labels.append((xi, dp.slot_fill_count))
    if xs:
        # faint full-height track + filled portion (bar handles date x natively)
        ax.bar(xs, [1] * len(xs), width=width, color=GRID, alpha=0.55, zorder=1, align="center")
        ax.bar(xs, fracs, width=width, color=PRIMARY, alpha=0.85, zorder=2, align="center")
        for xi, v in labels:
            ax.annotate(f"{v}/{slot_fill_max}", (xi, 1.0), textcoords="offset points",
                        xytext=(0, 3), ha="center", va="bottom", fontsize=_FS_ZONE, color=SECONDARY)
    ax.set_ylim(0, 1.35)
    ax.set_yticks([])
    ax.set_ylabel("", fontsize=_FS_AXIS)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_title(spec.title, fontsize=_FS_PANEL_TITLE, fontweight="normal", color=MUTED,
                 loc="left", pad=6)


def _draw_event_timeline(ax, x, events, ev_x):
    """Bottom row: detailed event labels (only here), marker by type,
    2–3 stacked heights to reduce overlap, wrapped labels."""
    import textwrap
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_title("주요 사건", fontsize=_FS_PANEL_TITLE, fontweight="bold", color=TEXT,
                 loc="left", pad=6)
    heights = [0.68, 0.40, 0.12]
    order = sorted(range(len(events)), key=lambda i: ev_x[i])  # ev_x is homogeneous (dates | ints)
    for rank, i in enumerate(order):
        e = events[i]
        c = e.color or _EVENT_COLORS.get(e.event_type, MUTED)
        m = _EVENT_MARKER.get(e.event_type, ".")
        y = heights[rank % len(heights)]
        ax.plot(ev_x[i], y, marker=m, markersize=8, color=c, zorder=6,
                linestyle="None", mec="white", mew=0.6)
        ax.annotate("\n".join(textwrap.wrap(e.label, 16)), (ev_x[i], y),
                    textcoords="offset points", xytext=(6, 0), va="center",
                    fontsize=_FS_EVENT, color=TEXT, zorder=7)


def _format_shared_x_axis(axes, x, dates, session_mode, x_tick_labels=None):
    """Date labels on the bottom axis only; upper panels hide x labels.
    In session mode, ``x_tick_labels`` (if given) replaces the default S# labels
    — pass real dates for equal-spaced-but-dated x positioning."""
    import matplotlib.dates as mdates
    bottom = axes[-1]
    if session_mode:
        bottom.set_xticks(list(range(len(dates))))
        if x_tick_labels and len(x_tick_labels) == len(dates):
            rot = 30 if max((len(s) for s in x_tick_labels), default=0) > 4 else 0
            bottom.set_xticklabels(x_tick_labels, fontsize=_FS_TICK,
                                   rotation=rot, ha="right" if rot else "center")
        else:
            bottom.set_xticklabels([f"S{i + 1}" for i in range(len(dates))], fontsize=_FS_TICK)
    else:
        span = (max(dates) - min(dates)).days if len(dates) >= 2 else 0
        loc = mdates.MonthLocator() if span > 120 else mdates.AutoDateLocator()
        bottom.xaxis.set_major_locator(loc)
        bottom.xaxis.set_major_formatter(mdates.DateFormatter("%y.%m"))
        for lbl in bottom.get_xticklabels():
            lbl.set_fontsize(_FS_TICK)
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)


def _save_figure(fig, dpi: int, output_format: str):
    """Return (png_bytes|None, svg_bytes|None) per output_format."""
    png = svg = None
    if output_format in ("png", "both"):
        b = io.BytesIO()
        fig.savefig(b, format="png", dpi=dpi, bbox_inches="tight", transparent=True)
        png = b.getvalue()
    if output_format in ("svg", "both"):
        b = io.BytesIO()
        fig.savefig(b, format="svg", bbox_inches="tight", transparent=True)
        svg = b.getvalue()
    return png, svg


# ── Named-series charts (disease similarity / domain fit) ────────────

def generate_similarity_trend_plot(
    points: list[NamedSeriesPoint],
    patient_name: str = "",
    title: str = "질환 유사도 추이 (질환별)",
    min_sessions: int = 2,
    figsize: tuple[float, float] = (9, 5.0),
    dpi: int = 180,
    *,
    include_figure_title: bool = False,
    include_patient_name: bool = False,
) -> TrendPlotResult | None:
    """One dashed low-opacity line per disease (>= min_sessions). Similarity
    is a REFERENCE signal — never labeled probability/confidence."""
    try:
        return _render_named_series_plot(
            points, patient_name, title, min_sessions, figsize, dpi,
            y_label="유사도 (참고용 · 확률 아님)",
            caption=("참고용 신호입니다 — F2 후보 산출의 임상 타당성은 검증되지 않았으며 "
                     "확률·가능성·진단이 아닙니다."),
            include_figure_title=include_figure_title, include_patient_name=include_patient_name)
    except ImportError:
        logger.warning("matplotlib not installed — similarity trend plot skipped")
        return None
    except Exception as exc:
        logger.warning("Similarity trend plot generation failed: %s", exc)
        return None


def generate_domain_trend_plot(
    points: list[NamedSeriesPoint],
    patient_name: str = "",
    title: str = "진료과 후보 적합도 추이 (진료과별)",
    min_sessions: int = 2,
    figsize: tuple[float, float] = (9, 5.0),
    dpi: int = 180,
    *,
    include_figure_title: bool = False,
    include_patient_name: bool = False,
) -> TrendPlotResult | None:
    """One dashed line per department. Axis reads user-facing '적합도' —
    never the internal 'domain_candidates.confidence' variable name."""
    try:
        return _render_named_series_plot(
            points, patient_name, title, min_sessions, figsize, dpi,
            y_label="적합도 (참고용)",
            caption="참고용 신호입니다 — 값이 높을수록 관련성이 높습니다. 진단이 아닙니다.",
            include_figure_title=include_figure_title, include_patient_name=include_patient_name)
    except ImportError:
        logger.warning("matplotlib not installed — domain trend plot skipped")
        return None
    except Exception as exc:
        logger.warning("Domain trend plot generation failed: %s", exc)
        return None


_SERIES_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
_SERIES_LINESTYLES = [(0, (4, 2)), (0, (1, 2)), (0, (5, 1, 1, 1)), (0, (3, 1, 1, 1, 1, 1))]
_SERIES_COLORS = [PRIMARY, SECONDARY, WARNING, "#3E6E88", "#7A8582", "#9B6A4A"]


def _render_named_series_plot(
    points, patient_name, title, min_sessions, figsize, dpi, *,
    y_label, caption, include_figure_title, include_patient_name,
) -> TrendPlotResult:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    _fonts()

    by_name: dict[str, list[tuple[datetime, float]]] = {}
    for p in points:
        by_name.setdefault(p.name, []).append((_parse_date(p.date), p.value))
    recurring = {n: sorted(v, key=lambda t: t[0]) for n, v in by_name.items()
                 if len({d for d, _ in v}) >= min_sessions}
    if not recurring:
        raise ValueError("No name recurs in >= min_sessions distinct sessions")

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_alpha(0)
    if include_figure_title:
        t = title + (f"\n{patient_name}" if include_patient_name and patient_name else "")
        fig.suptitle(t, fontsize=_FS_FIGTITLE, fontweight="bold", color=TEXT)

    for i, (name, vals) in enumerate(sorted(recurring.items())):
        ax.plot([d for d, _ in vals], [v for _, v in vals],
                marker=_SERIES_MARKERS[i % len(_SERIES_MARKERS)], markersize=4.5,
                linewidth=1.3, linestyle=_SERIES_LINESTYLES[i % len(_SERIES_LINESTYLES)],
                alpha=0.85, color=_SERIES_COLORS[i % len(_SERIES_COLORS)],
                mfc="white", mew=0.9, label=name)

    ax.set_ylabel(y_label, fontsize=_FS_AXIS, color=TEXT)
    ax.set_ylim(-0.03, 1.03)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=_FS_TICK, colors=TEXT, length=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y.%m"))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), fontsize=_FS_CAPTION,
              frameon=False, ncol=min(3, len(recurring)), labelcolor=TEXT)
    if caption:
        fig.text(0.5, 0.005, caption, fontsize=_FS_CAPTION, color=SECONDARY,
                 ha="center", va="bottom", wrap=True)
    fig.subplots_adjust(top=0.9, bottom=0.30, left=0.12, right=0.97)

    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=dpi, bbox_inches="tight", transparent=True)
    plt.close(fig)
    png = b.getvalue()
    return TrendPlotResult(
        png_bytes=png, base64_str=base64.b64encode(png).decode("ascii"),
        width_px=int(figsize[0] * dpi), height_px=int(figsize[1] * dpi))
