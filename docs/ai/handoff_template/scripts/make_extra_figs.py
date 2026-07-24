#!/usr/bin/env python3
"""보조 종단 차트 렌더러 — FIG.02(정서·충족도), FIG.03(AI 참고: 유사도·적합도).

data/sample-report.json 의 figures[1]/figures[2] 를 읽어 스펙에 맞춘 작은
보조 Figure PNG를 생성한다. 세션→날짜 매핑은 figures[0].series.ctrs 에서
재사용한다. 차트 안에 제목·환자ID·파일명·변수명은 넣지 않는다.
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
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample-report.json"
ASSETS = ROOT / "assets"

PRIMARY = "#17494E"
GRID = "#E6E7E3"
INK = "#17211F"
FAINT = "#9AA0A0"
# 절제된 다계열 팔레트 (teal → muted)
PALETTE = ["#17494E", "#7FA7A6", "#B98A5E"]

for fp in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]:
    try:
        fm.fontManager.addfont(fp)
        plt.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False


def _clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID); ax.spines[s].set_linewidth(0.8)
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
    ax.tick_params(labelsize=7, colors=INK, length=0)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y.%m"))


def main():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    figs = doc["figures"]
    # 세션→날짜
    sdate = {p["s"]: datetime.strptime(p["d"], "%Y-%m-%d")
             for p in figs[0]["series"]["ctrs"]["points"]}
    xy = lambda pts: ([sdate[p["s"]] for p in pts], [p["v"] for p in pts])

    # ── FIG.02 : 정서 극성 + 문진 충족도 ──
    f2 = next(f for f in figs if f.get("slot") == "secondary")["series"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.1, 2.05), dpi=200)
    fig.patch.set_alpha(0)
    sx, sy = xy(f2["sentiment"]["points"])
    a1.axhline(0, color=FAINT, lw=0.7, ls=(0, (3, 3)))
    a1.plot(sx, sy, color=PRIMARY, lw=1.6, marker="o", ms=3.5, mec="white", mew=0.7)
    a1.set_ylim(-1, 1); a1.set_ylabel("정서 극성", fontsize=8, color=INK)
    fx, fy = xy(f2["slotfill"]["points"])
    a2.plot(fx, fy, color=PRIMARY, lw=1.6, marker="o", ms=3.5, mec="white", mew=0.7)
    a2.set_ylim(0, 8); a2.set_ylabel("문진 충족도", fontsize=8, color=INK)
    for a in (a1, a2):
        a.set_facecolor("none"); _clean(a)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.16, wspace=0.18)
    fig.savefig(ASSETS / "fig02_sentiment_slotfill.png", transparent=True, dpi=200)
    plt.close(fig)

    # ── FIG.03 : 질환 유사도 + 진료과 적합도 (AI 참고·비진단) ──
    f3 = next(f for f in figs if f.get("slot") == "appendix")["series"]
    fig, (b1, b2) = plt.subplots(1, 2, figsize=(7.1, 2.5), dpi=200)
    fig.patch.set_alpha(0)

    def draw_multi(ax, block, ymax):
        for i, ln in enumerate(block["lines"]):
            x, y = xy(ln["points"])
            ax.plot(x, y, color=PALETTE[i % len(PALETTE)], lw=1.3,
                    ls=(0, (4, 2)), marker="o", ms=2.8, mfc="white",
                    mec=PALETTE[i % len(PALETTE)], mew=0.9)
        ax.set_ylim(0, ymax)
        ax.set_facecolor("none"); _clean(ax)
        handles = [Line2D([0], [0], color=PALETTE[i % len(PALETTE)], lw=1.3,
                          ls=(0, (4, 2)), marker="o", ms=2.8, mfc="white",
                          label=ln["name"]) for i, ln in enumerate(block["lines"])]
        ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.14),
                  ncol=len(handles), frameon=False, fontsize=6.4, handlelength=2,
                  columnspacing=1.2, labelcolor=INK)

    draw_multi(b1, f3["disease"], f3["disease"]["max"])
    b1.set_ylabel("질환 유사도", fontsize=8, color=INK)
    draw_multi(b2, f3["domain"], f3["domain"]["max"])
    b2.set_ylabel("진료과 적합도", fontsize=8, color=INK)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.28, wspace=0.18)
    fig.savefig(ASSETS / "fig03_ai_reference.png", transparent=True, dpi=200)
    plt.close(fig)
    print("wrote fig02, fig03")


if __name__ == "__main__":
    main()
