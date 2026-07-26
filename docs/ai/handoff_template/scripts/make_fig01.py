#!/usr/bin/env python3
"""FIG.01 — PHQ-9 · 위기단계(CTRS) 상하 분리 2패널 차트.

이중 축에 겹치지 않고, 범위·방향이 다른 두 지표를 상하로 정렬된 별도 패널로
표현한다(레퍼런스: IBM data-viz). 차트 안에 제목/환자ID/파일명 없음 — 제목·설명·
출처는 HTML 캡션이 담당. data/sample-report.json figures[0].series 를 읽는다.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample-report.json"
OUT = ROOT / "assets" / "fig01_phq9_safety.png"
PRIMARY, COMPARE, INK, FAINT, CLAY, GRID = "#17494E", "#59636A", "#17211F", "#9AA0A0", "#A6462F", "#E9EAE6"
for fp in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
    try:
        fm.fontManager.addfont(fp); plt.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name(); break
    except Exception: pass
plt.rcParams["axes.unicode_minus"] = False
_d = lambda s: datetime.strptime(s, "%Y-%m-%d")

def _axis(ax, last=False):
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(GRID); ax.spines[s].set_linewidth(0.8)
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
    ax.tick_params(labelsize=7.5, colors=INK, length=0)
    if last:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y.%m"))
    else:
        ax.tick_params(labelbottom=False)

def main():
    s = json.loads(DATA.read_text(encoding="utf-8"))["figures"][0]["series"]
    phq, ctrs = s["phq9"], s["ctrs"]
    dmin = min(_d(p["d"]) for p in phq["points"] + ctrs["points"])
    dmax = max(_d(p["d"]) for p in phq["points"] + ctrs["points"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.1, 3.7), dpi=200, sharex=True,
                                   gridspec_kw={"height_ratios": [1.25, 1]})
    fig.patch.set_alpha(0)
    for ax in (ax1, ax2): ax.set_facecolor("none"); ax.set_xlim(dmin, dmax)

    def endpoints(pts, lp):
        """시작·끝은 항상, 지정 지점(dip 등) 추가 — 값 라벨용 세션집합."""
        ss = {pts[0]["s"], pts[-1]["s"]} | set(lp or [])
        return ss

    # ── 상단: PHQ-9 (severity 밴드 + 우측 구간 라벨) ──
    for i, b in enumerate(phq["bands"]):
        a = {0:0,1:.03,2:.055,3:.085,4:.12}.get(i, 0)
        if a: ax1.axhspan(b["lo"]-.5, b["hi"]+.5, color=CLAY, alpha=a, lw=0, zorder=0)
        # 중증도 구간 라벨을 우측 여백에 직접 표기 (캡션 없이 즉시 해석)
        ax1.text(1.012, (b["lo"]+b["hi"])/2, b["name"], transform=ax1.get_yaxis_transform(),
                 ha="left", va="center", fontsize=6, color=FAINT, clip_on=False)
    px = [_d(p["d"]) for p in phq["points"]]; py = [p["v"] for p in phq["points"]]
    ax1.plot(px, py, color=PRIMARY, lw=1.9, marker="o", ms=4.5, mfc=PRIMARY, mec="white", mew=0.8, zorder=5)
    ax1.set_ylim(phq["min"], phq["max"]); ax1.set_ylabel("PHQ-9 (우울)", fontsize=8, color=INK)
    lp1 = endpoints(phq["points"], phq.get("labelPoints"))
    for p in phq["points"]:
        if p["s"] in lp1:
            ax1.annotate(str(p["v"]), (_d(p["d"]), p["v"]), textcoords="offset points", xytext=(0, 7),
                         ha="center", fontsize=7.5, color=PRIMARY, fontweight="bold")
    _axis(ax1)

    # ── 하단: 위기 단계 CTRS (gray, 안정↑/위험↓ 방향 표기) ──
    cx = [_d(p["d"]) for p in ctrs["points"]]; cy = [p["v"] for p in ctrs["points"]]
    ax2.plot(cx, cy, color=COMPARE, lw=1.7, marker="s", ms=3.8, mfc="white", mec=COMPARE, mew=1.2, zorder=5)
    ax2.set_ylim(ctrs["min"]-.4, ctrs["max"]+.4); ax2.set_ylabel("위기 단계 (CTRS)", fontsize=8, color=INK)
    ax2.text(1.012, ctrs["max"], "안정", transform=ax2.get_yaxis_transform(), ha="left", va="center", fontsize=6, color=FAINT, clip_on=False)
    ax2.text(1.012, ctrs["min"], "위험", transform=ax2.get_yaxis_transform(), ha="left", va="center", fontsize=6, color=FAINT, clip_on=False)
    lp2 = endpoints(ctrs["points"], ctrs.get("labelPoints"))
    for p in ctrs["points"]:
        if p["s"] in lp2:
            ax2.annotate(str(p["v"]), (_d(p["d"]), p["v"]), textcoords="offset points", xytext=(0, 7),
                         ha="center", fontsize=7.5, color=COMPARE, fontweight="bold")
    _axis(ax2, last=True)

    fig.subplots_adjust(left=0.1, right=0.9, top=0.97, bottom=0.11, hspace=0.16)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, transparent=True, dpi=200); plt.close(fig)
    print("wrote", OUT)

if __name__ == "__main__":
    main()
