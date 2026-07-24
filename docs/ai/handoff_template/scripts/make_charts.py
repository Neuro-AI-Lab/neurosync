#!/usr/bin/env python3
"""템플릿 차트 렌더러 (정식) — apps/ai-server 의 리팩터된 ``trend_plotter.py`` 가
직접 FIG.01/02/03 을 렌더한다(스타일·결측·CTRS 방향 등 신 코드 반영).

구 matplotlib 자체 구현은 ``make_charts_legacy_matplotlib.py.bak`` 로 보관.
차트 스타일의 단일 진실 소스는 이제 ``trend_plotter.py`` 이며, 이 스크립트는
report JSON 계열을 ``TrendDataPoint`` 로 옮겨 그 엔진을 호출하는 얇은 어댑터다.

- FIG.01 (hero)      : PHQ-9 / GAD-7 / AUDIT-C / CTRS 임상 패널 (존재분만)
- FIG.02 (secondary) : 정서 극성 sparkline + 문진 충족도 막대(보조 지표)
- FIG.03 (appendix)  : 질환 유사도 명명 계열(참고용 · 비진단)

출력 경로는 report JSON 의 각 figure `image` 필드(및 render-report.js 의 fallback)
를 그대로 따른다 — JSON 수정 없이 기존 슬롯에 신 코드 산출물을 꽂는다.

사용: python make_charts.py [report.json]   (생략 시 data/sample-report.json)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]                       # handoff_template/
REPO = ROOT.parents[2]                                           # neurosync/
_TP = REPO / "apps" / "ai-server" / "src" / "services" / "trend_plotter.py"

# 신 코드(trend_plotter.py)를 패키지 import 부작용 없이 파일에서 직접 로드
_spec = importlib.util.spec_from_file_location("trend_plotter", _TP)
tp = importlib.util.module_from_spec(_spec)
sys.modules["trend_plotter"] = tp        # dataclass needs the module registered
_spec.loader.exec_module(tp)


def _session_dates(fig_hero: dict) -> dict[int, str]:
    """세션 번호 → ISO 날짜. ctrs 우선, 없으면 phq9(둘 다 `d` 보유)."""
    sdate: dict[int, str] = {}
    for key in ("ctrs", "phq9", "gad7", "auditc", "audit_c"):
        for p in fig_hero.get("series", {}).get(key, {}).get("points", []):
            if "d" in p and p["s"] not in sdate:
                sdate[p["s"]] = p["d"]
    return sdate


def _val_by_session(series: dict, key: str) -> dict[int, float]:
    return {p["s"]: p["v"] for p in series.get(key, {}).get("points", [])}


def _build_points(hero: dict, sec: dict | None, sdate: dict[int, str], keys: dict):
    """세션 합집합으로 TrendDataPoint 배열 생성 — 미측정 세션은 None(→nan gap)."""
    hs, ss = hero.get("series", {}), (sec or {}).get("series", {})
    vals = {
        "phq9": _val_by_session(hs, "phq9"),
        "gad7": _val_by_session(hs, "gad7"),
        "audit_c": {**_val_by_session(hs, "auditc"), **_val_by_session(hs, "audit_c")},
        "ctrs": _val_by_session(hs, "ctrs"),
        "sentiment": _val_by_session(ss, "sentiment"),
        "slot_fill": _val_by_session(ss, "slotfill"),
    }
    sessions = sorted({s for m in vals.values() for s in m} | set(sdate))
    pts = []
    for s in sessions:
        d = sdate.get(s)
        if d is None:
            continue                                             # 날짜 없는 세션은 축에 못 얹음
        pts.append(tp.TrendDataPoint(
            date=d,
            phq9=_i(vals["phq9"].get(s)) if "phq9" in keys else None,
            gad7=_i(vals["gad7"].get(s)) if "gad7" in keys else None,
            audit_c=_i(vals["audit_c"].get(s)) if "audit_c" in keys else None,
            ctrs=_i(vals["ctrs"].get(s)) if "ctrs" in keys else None,
            sentiment=vals["sentiment"].get(s) if "sentiment" in keys else None,
            slot_fill_count=_i(vals["slot_fill"].get(s)) if "slot_fill" in keys else None,
        ))
    return pts


def _i(v):
    return None if v is None else int(round(v))


def _named_points(block: dict, sdate: dict[int, str]):
    out = []
    for ln in (block or {}).get("lines", []):
        for p in ln.get("points", []):
            d = p.get("d") or sdate.get(p.get("s"))
            if d is not None:
                out.append(tp.NamedSeriesPoint(date=d, name=ln.get("name", "?"), value=p["v"]))
    return out


def _resolve(fig: dict | None, fallback: str) -> Path:
    img = (fig or {}).get("image") or fallback
    return (ROOT / img)


def main(report_path: str):
    import json
    doc = json.loads(Path(report_path).read_text(encoding="utf-8"))
    figs = doc.get("figures", [])
    hero = next((f for f in figs if f.get("slot") in (None, "hero")), figs[0] if figs else {})
    sec = next((f for f in figs if f.get("slot") == "secondary"), None)
    app = next((f for f in figs if f.get("slot") == "appendix"), None)
    sdate = _session_dates(hero)
    (ROOT / "assets").mkdir(exist_ok=True)

    # FIG.01 — 임상 패널 (PHQ-9/GAD-7/AUDIT-C/CTRS 중 존재분)
    clinical = _build_points(hero, None, sdate, {"phq9", "gad7", "audit_c", "ctrs"})
    # 세션은 등간격으로 배치하고 눈금은 실제 날짜(m/d)로 라벨 — 초기 주간 세션이 날짜축
    # 에서 몰려 겹치던 문제를 없애면서 날짜 정보는 유지(FIG.01·02 x축 정렬). 라벨은 실제
    # 전달 포인트에서 파생해 정렬을 보장한다.
    xlabels = [p.date[5:].replace("-", "/") for p in clinical]
    # 실측 세션에만 마커, 미측정 세션은 관통해 실측점끼리 이어 그린다(추세선).
    r1 = tp.generate_trend_plot(clinical, figsize=(9.4, 8.0), dpi=200,
                                x_axis_mode="session", x_tick_labels=xlabels,
                                connect_missing=True, missing_connection_style="solid")
    if r1:
        _resolve(hero, "assets/fig01.png").write_bytes(r1.png_bytes)

    # FIG.02 — 보조 지표 (정서 sparkline + 충족도 막대)
    secondary = _build_points(hero, sec, sdate, {"sentiment", "slot_fill"})
    r2 = tp.generate_trend_plot(secondary, figsize=(9.4, 4.0), dpi=200,
                                x_axis_mode="session", x_tick_labels=xlabels,
                                slot_fill_max=(sec or {}).get("series", {})
                                .get("slotfill", {}).get("max", 8))
    if r2:
        _resolve(sec, "assets/fig02_sentiment_slotfill.png").write_bytes(r2.png_bytes)

    # FIG.03 — 질환 유사도 명명 계열만 (스케일이 다른 진료과 적합도는 제외; 캡션 일치)
    if app:
        dis = _named_points(app.get("series", {}).get("disease"), sdate)
        r3 = tp.generate_similarity_trend_plot(dis, min_sessions=1, figsize=(7.1, 2.6), dpi=200) \
            if dis else None
        if r3:
            _resolve(app, "assets/fig03_ai_reference.png").write_bytes(r3.png_bytes)

    print(f"charts(trend_plotter) done for {report_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "sample-report.json"))
