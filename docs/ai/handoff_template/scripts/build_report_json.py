#!/usr/bin/env python3
"""페르소나 아티팩트(temporal.json + handoff.md) → Editorial Handoff report JSON.

사용: python build_report_json.py <VP-XXX>
  simulation_results/<VP>/*_temporal.json + *_handoff.md 를 읽어
  data/report-<VP>.json 을 생성한다. 개발자 정보(모델명/세션ID/함수/변수명/
  파일명/confidence)는 제외한다. 결측 필드는 넣지 않아 템플릿이 숨긴다.

이 스크립트는 템플릿 견고성 검증용 하네스이며, 최종 F5/DB 바인딩의 참고 구현이다.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT.parent / "simulation_results"   # docs/ai/simulation_results

PHQ_BANDS = [{"lo":0,"hi":4,"name":"정상"},{"lo":5,"hi":9,"name":"경도"},
             {"lo":10,"hi":14,"name":"중등도"},{"lo":15,"hi":19,"name":"중등–중증"},{"lo":20,"hi":27,"name":"중증"}]
PHQ_ITEM_LABELS = ["흥미·즐거움 저하","우울·절망감","수면 문제","피로·기력 저하","식욕 문제",
                   "자기 부정적 감정","집중 곤란","정신운동 지연/초조","자해·자살 사고"]
CTRS_LABEL = {1:"최긴급",2:"고위험",3:"급성 우려",4:"경도 우려 · 준안정",5:"안정"}

def phq_sev(v):
    for b in PHQ_BANDS:
        if b["lo"] <= v <= b["hi"]: return b["name"]
    return ""

def mask(name):
    name = name.strip()
    if len(name) <= 1: return name
    if len(name) == 2: return name[0] + "○"
    return name[0] + "○"*(len(name)-2) + name[-1]

def sect(md, header):
    """## header 이후 다음 ## 전까지."""
    m = re.search(r'(?m)^#{2,3}\s*'+re.escape(header)+r'\s*$', md)
    if not m: return ""
    start = m.end()
    nxt = re.search(r'(?m)^#{2,3}\s+', md[start:])
    return md[start:start+(nxt.start() if nxt else len(md))].strip()

def clip(s, n=90):
    """단어 경계에서 자르고 말줄임(중간 잘림 방지)."""
    s = str(s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n]; sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.6 else cut).rstrip() + "…"

def main():
    vp = sys.argv[1]
    d = SIM / vp
    # 세션 수가 가장 많은 run(정본 다세션 아크)을 선택 — 짧은 데모 실행이 원본 리포트를
    # 덮어쓰지 않도록. handoff.md 는 같은 날짜(run)의 것 중 최신으로 매칭해 정합성 유지.
    temps = sorted(d.glob("*_temporal.json"))
    def _nsess(p):
        try:
            return int(json.loads(p.read_text(encoding="utf-8")).get("n_sessions", 0))
        except Exception:
            return 0
    mx = max((_nsess(p) for p in temps), default=0)
    tj = [p for p in temps if _nsess(p) == mx][-1]      # 최다 세션 아크 중 최신 run
    datep = "_".join(tj.name.split("_")[:2])            # 예: VP-001_20260715
    hs = sorted(d.glob(f"{datep}_*_handoff.md")) or sorted(d.glob("*_handoff.md"))
    mdf = hs[-1]
    T = json.loads(tj.read_text(encoding="utf-8"))
    md = mdf.read_text(encoding="utf-8")
    num = vp.split("-")[1]

    sdate = {p["session_index"]: p["simulated_date"] for p in T.get("ctrs_series", [])}
    def dt(s): return sdate.get(s, "")

    # ── patient ──
    m = re.search(r'환자:\s*([^\(]+)\(', md)
    name = m.group(1).strip() if m else vp
    latest = max(sdate) if sdate else T.get("n_sessions", 0)
    R = {
      "report": {"id": f"HR-2027-{num.zfill(4)}", "eyebrow": "CLINICAL HANDOFF", "reportNo": f"REPORT {num.zfill(3)}",
                 "title": "종단 문진 인계 보고서", "generatedAt": dt(latest)+"T00:00:00+09:00", "status": "FINAL"},
      "patient": {"id": vp, "displayName": name, "maskedName": mask(name), "ageSex": ""},
      "period": {"sessions": T.get("n_sessions"), "days": T.get("session_span_days"),
                 "firstDate": dt(min(sdate)) if sdate else "", "latestDate": dt(latest)},
      "latestSession": {"number": latest, "date": dt(latest), "mode": "자연 대화형"},
      "disclaimer": "본 보고서는 자가보고(AI 대화형 문진) 기반 비공식 문서이며 공식 의무기록·의학적 진단이 아닙니다. 최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다.",
    }

    # ── scales & metrics ──
    scales = T.get("scale_series", {})
    def series_pts(name):
        return [{"s":p["session_index"],"d":p["simulated_date"],"v":p["total_score"]}
                for p in scales.get(name, []) if p.get("total_score") is not None]
    phqp = series_pts("PHQ-9"); audp = series_pts("AUDIT-C")
    ctrsp = [{"s":p["session_index"],"d":p["simulated_date"],"v":p["session_ctrs"]}
             for p in T.get("ctrs_series", []) if p.get("session_ctrs") is not None]
    metrics = []
    def metric(key,label,sub,pts,mx,sev_fn,better_low):
        if not pts: return
        v=pts[-1]["v"]; prev=pts[-2]["v"] if len(pts)>1 else None
        mo={"key":key,"label":label,"sub":sub,"value":v,"max":mx,"state":sev_fn(v)}
        if prev is not None:
            ch=v-prev; mo["previous"]=prev; mo["change"]=ch
            mo["direction"]="improved" if ((ch<0)==better_low and ch!=0) else ("worsened" if ch!=0 else "")
        metrics.append(mo)
    metric("phq9","PHQ-9","우울 선별",phqp,27,phq_sev,True)
    metric("safety","SAFETY LEVEL","위기 단계 (CTRS)",ctrsp,5,lambda v:CTRS_LABEL.get(v,""),False)
    metrics.append({"key":"followUp","label":"FOLLOW-UP","sub":"보고 기간","value":T.get("session_span_days"),"unit":"일","state":f"{T.get('n_sessions')}세션"})
    metric("auditc","AUDIT-C","음주 선별",audp,12,lambda v:"고위험 음주" if v>=8 else "중등도",True)
    # PHQ가 temporal에 없으면 handoff 설문에서 단일값 보충
    if not phqp:
        ms=re.search(r'PHQ-9\s+(\d+)/(\d+)\s*\(([^)]+)\)', md)
        if ms: metrics.insert(0,{"key":"phq9","label":"PHQ-9","sub":"우울 선별(직전 시행)","value":int(ms.group(1)),"max":int(ms.group(2)),"state":ms.group(3)})
    R["metrics"]=metrics[:4]

    # ── figures ──
    figs=[]
    hero={"id":"FIG. 01","interpretation":"","current":"","baseline":"","caption":"PHQ-9·위기 단계(CTRS) 추이.","source":f"출처 · 종단 자가보고 문진 ({T.get('n_sessions')}세션).","image":f"assets/fig01_{vp}.png","series":{}}
    if phqp: hero["series"]["phq9"]={"label":"PHQ-9","axis":"left","min":0,"max":27,"bands":PHQ_BANDS,"points":phqp,"labelPoints":[phqp[0]["s"],phqp[-1]["s"]]}
    if ctrsp: hero["series"]["ctrs"]={"label":"위기 단계 (CTRS)","axis":"right","min":1,"max":5,"points":ctrsp,"labelPoints":[ctrsp[0]["s"]]}
    if phqp or ctrsp:
        cur=[]; base=[]
        if phqp: cur.append(f"PHQ-9 {phqp[-1]['v']}"); base.append(f"PHQ-9 {phqp[0]['v']}")
        if ctrsp: cur.append(f"위기 {ctrsp[-1]['v']}"); base.append(f"위기 {ctrsp[0]['v']}")
        hero["current"]=" · ".join(cur); hero["baseline"]=" · ".join(base)
        hero["interpretation"]=f"보고 기간 동안 위기 단계·우울 지표의 종단 변화. 전체 방향: {kdir(T.get('overall_direction'))}."
        figs.append(hero)
    # secondary
    sent=[{"s":p["session_index"],"v":round(p.get("mean_polarity") or 0,2)} for p in T.get("sentiment_series",[]) if p.get("mean_polarity") is not None]
    slot=[{"s":p["session_index"],"v":p.get("filled_count")} for p in T.get("slot_fill_series",[]) if p.get("filled_count") is not None]
    if sent or slot:
        figs.append({"id":"FIG. 02","slot":"secondary","caption":"정서 극성·문진 충족도 추이 (보조).","image":f"assets/fig02_{vp}.png",
                     "series":{"sentiment":{"min":-1,"max":1,"points":sent},"slotfill":{"min":0,"max":8,"points":slot}}})
    # appendix disease/domain
    def topN(series_key, val_key, n=3):
        rows={}
        for p in T.get(series_key,[]):
            rows.setdefault(p[val_key], []).append({"s":p["session_index"],"v":round(p.get("similarity_score",p.get("confidence",0)),3)})
        # 최신 값 기준 정렬
        ranked=sorted(rows.items(), key=lambda kv:-kv[1][-1]["v"])
        return [{"name":k,"points":v} for k,v in ranked[:n]]
    dis=topN("disease_candidate_series","disease")
    if dis:
        # FIG.03 은 질환 유사도만 렌더(진료과 적합도는 스케일이 달라 제외). 질환
        # 유사도 데이터가 없으면 image 를 두지 않아 render-report.js 가 도형을 숨긴다.
        appf={"id":"FIG. 03","slot":"appendix","caption":"질환 유사도 추이 (AI 참고·비진단).",
              "note":"유사도는 참고용 신호일 뿐 확률·가능성·진단이 아니며, 임상 판단을 대체하지 않는다.","image":f"assets/fig03_{vp}.png",
              "series":{"disease":{"min":0,"max":0.6,"lines":dis}}}
        # 랭킹(최신 세션)
        latest_dis=sorted([(p["disease"],p["similarity_score"]) for p in T.get("disease_candidate_series",[]) if p["session_index"]==max((x["session_index"] for x in T.get("disease_candidate_series",[])), default=0)], key=lambda x:-x[1])
        if latest_dis:
            items=[{"rank":f"{i+1}위","name":k,"score":round(v,3)} for i,(k,v) in enumerate(latest_dis[:3])]
            appf["ranking"]={"asOf":f"{latest}회차 · {dt(latest)}","items":items,
                             "others":" · ".join(f"{k} {round(v,3)}" for k,v in latest_dis[3:5])}
        figs.append(appf)
    R["figures"]=figs

    # ── scaleChanges: 변화 지점마다 추이(steps) + 초기 대비 최종 판정(값 기준) ──
    # 방향은 F4 종단 verdict(전체 궤적)가 아니라 '초기값 vs 최신값'으로 계산한다
    # (3→3 인데 악화/개선으로 뜨던 불일치 제거). LOWER_BETTER: 값이 낮을수록 개선.
    LOWER_BETTER = {"scale_total_PHQ-9": True, "scale_total_AUDIT-C": True,
                    "session_ctrs": False, "sentiment": False, "slot_fill_count": False}
    def _verdict(dimkey, first_v, last_v):
        if first_v == last_v:
            return "유지"
        lower_better = LOWER_BETTER.get(dimkey, True)
        improved = (last_v < first_v) if lower_better else (last_v > first_v)
        return "개선" if improved else "악화"
    def _change_steps(pts):
        # 첫 점 + 값이 바뀐 지점만 (연속 동일값은 접음). 마지막 실측 회차는 latest 로 별도.
        steps = [pts[0]]
        for p in pts[1:]:
            if p["v"] != steps[-1]["v"]:
                steps.append(p)
        return steps
    def srow(metric, dimkey, pts, vfmt):
        if not pts:
            return None
        first_v, last_v = pts[0]["v"], pts[-1]["v"]
        steps = _change_steps(pts)
        return {"metric": metric,
                "direction": _verdict(dimkey, first_v, last_v),
                "steps": [{"s": p["s"], "d": p.get("d") or dt(p["s"]), "v": vfmt(p["v"])} for p in steps],
                "latest": {"s": pts[-1]["s"], "d": pts[-1].get("d") or dt(pts[-1]["s"]), "v": vfmt(last_v)},
                "nChanges": len(steps) - 1}
    fnum = lambda v: f"{v:.2f}" if isinstance(v, float) else f"{v}"
    rows = [r for r in [
        srow("PHQ-9 (우울)", "scale_total_PHQ-9", phqp, lambda v: f"{v}점"),
        srow("AUDIT-C (음주)", "scale_total_AUDIT-C", audp, lambda v: f"{v}점"),
        srow("위기 단계 (CTRS)", "session_ctrs", ctrsp, lambda v: f"{v}"),
        srow("정서 극성 (감성)", "sentiment", sent, fnum),
        srow("문진 항목 충족도", "slot_fill_count", slot, lambda v: f"{v}"),
    ] if r]
    kconc = {"concordant": "일치", "discordant": "불일치", "unknown": "판정 보류"}
    R["scaleChanges"] = {"overall": kdir(T.get("overall_direction")), "rows": rows,
        "notes": [f"종단 추세 일관성(설문·위기단계·정서): {kconc.get(T.get('concordance_flag'), '—')}"]}

    # ── narrative ──
    nar=sect(md,"주호소 및 현병력")
    cc=re.search(r'\*\*주호소\*\*:\s*(.+)', nar); hpi=re.search(r'\*\*현병력\*\*:\s*(.+)', nar)
    R["narrative"]={"presentingConcern":cc.group(1).strip() if cc else "","hpi":hpi.group(1).strip() if hpi else "",
                    "mse":sect(md,"정신상태검사 (MSE)").split("\n")[0] if sect(md,"정신상태검사 (MSE)") else "",
                    "annotations":[]}

    # ── risk ──
    risk=sect(md,"위험/안전 평가")
    para=risk.split("\n")[0]
    ctrsm=re.search(r'CTRS\)?\s*(\d)/5\s*[—-]\s*([^\.]+)', para)
    qm=re.search(r'발화:\s*"([^"]+)"', para)
    R["riskSafety"]={"current":{"session":latest,"date":dt(latest),
        "ctrs":int(ctrsm.group(1)) if ctrsm else None,"ctrsMax":5,"ctrsLabel":(ctrsm.group(2).strip() if ctrsm else ""),
        "assessment":re.split(r'[—\-]\s*환자 발화', para)[0].strip()[:120],
        "quote":qm.group(1) if qm else "", "item9":"","referral":"","surveyStatus":""},
        "flags":[],"trajectory":[]}
    for line in md.splitlines():
        lm=re.match(r'>?\s*-?\s*위험 플래그:\s*(.+)', line) or re.match(r'>?\s*-?\s*주요 우려:\s*(.+)', line)
        if lm: R["riskSafety"]["flags"].append({"level":"attention" if ("양성" in lm.group(1) or "위기" in lm.group(1) or "불일치" in lm.group(1)) else "info","text":lm.group(1).strip()})

    # ── slot table + history ──
    def parse_rows(block):
        out=[]
        for row in re.findall(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|', block, re.M):
            k=row[0].strip()
            if k in ("슬롯","---") or k.startswith("-"): continue
            out.append((k,row[1].strip(),row[2].strip()))
        return out
    summ=sect(md,"전체 세션 요약")
    hist_block = md.split("슬롯별 전체 변화 이력")[-1].split("## 각주")[0] if "슬롯별 전체 변화 이력" in md else ""
    # history parse
    hist=[]
    for hh in ["주호소","현병력","음주·흡연·물질사용","위험평가","개인사/사회력","가족력"]:
        mm=re.search(r'(?m)^\*\*'+re.escape(hh)+r'\*\*\s*\n(.+)', hist_block)
        if not mm:
            mm=re.search(re.escape(hh)+r'\n(S\d+:.+)', hist_block)
        if mm:
            pts=[{"s":int(a),"d":dt(int(a)),"text":b.strip()} for a,b in re.findall(r"S(\d+):\s*'(.*?)'(?=\s*→\s*S\d+:|\s*$)", mm.group(1))]
            if pts: hist.append({"slot":hh.replace("·흡연",""),"points":pts})
    def full_latest(label):
        for h in hist:
            if h["slot"].startswith(label[:2]): return h["points"][-1]["text"]
        return None
    slots=[]
    for k,latest_v,src in parse_rows(summ):
        v=latest_v
        if "참조" in v or "…" in v:
            fl=full_latest(k)
            if fl: v=fl
        if v in ("미수집","-",""): continue
        chm=re.search(r'(\d+)회 변화', src if src else "")
        slots.append({"label":k,"latest":v,"source":(src.split("·")[0].strip() if src else "").replace("/", " · "),"changes":0})
    R["clinicalSummary"]={"note":"아래 값은 AI 대화형 문진(F1)에서 환자가 자가보고한 내용이며, 임상의의 직접 평가나 검증된 척도 시행이 아니다.","slots":slots}

    # risk trajectory from history 위험평가
    for h in hist:
        if h["slot"]=="위험평가":
            R["riskSafety"]["trajectory"]=[{"session":p["s"],"date":dt(p["s"]),"note":clip(p["text"],72)} for p in h["points"][:6]]

    # ── surveys ──
    surv=sect(md,"시행된 설문")
    # `**PHQ-9 23/27 (중증)** — 2회차` 처럼 굵게(**) 감싼 형식도 허용(닫는 ** 소비)
    sm=re.search(r'PHQ-9\s+(\d+)/(\d+)\s*\(([^)]+)\)\*{0,2}\s*[—\-–]\s*(\d+)\s*회차', surv)
    resp=re.search(r'응답:\s*([\d,]+)', surv)
    if sm and resp:
        scores=[int(x) for x in resp.group(1).split(",")]
        R["surveys"]={"phq9":{"name":"PHQ-9","score":int(sm.group(1)),"max":int(sm.group(2)),"severity":sm.group(3),
            "session":int(sm.group(4)),"date":dt(int(sm.group(4))),"mode":"자연 대화형",
            "item9Note":f"자살사고 문항(9번) {'양성' if len(scores)>8 and scores[8]>0 else '음성'} · {scores[8] if len(scores)>8 else 0}점",
            "scaleNote":"응답 척도 0(전혀 아님)–3(거의 매일)",
            "items":[{"no":i+1,"label":PHQ_ITEM_LABELS[i],"score":s} for i,s in enumerate(scores)]},
            "note":"AI가 진행한 대화형 문진 결과이며, 검증된 임상 설문의 정식 시행이 아니다."}

    # ── care routing ──
    care=sect(md,"권장 진료과 및 후속 조치")
    depts=[{"name":a.strip(),"reason":b.strip()} for a,b in re.findall(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', care, re.M) if a.strip() not in ("진료과","---") and not a.strip().startswith("-")]
    qm2=re.search(r'추천 설문:\s*([^\n]+)', care)
    R["careRouting"]={"recommendedDepartments":depts,
        "recommendedQuestionnaire":(re.sub(r'\s*[—-]\s*PHQ-9 screens.*','',qm2.group(1)).strip() if qm2 else ""),
        "medicationNote":"구조화된 약물 정보 항목 없음 (병력 서술 내 언급만 확인)"}

    # ── action items (from handoff focus / care) ──
    R["actionItems"]=[{"no":i+1,"text":clip(dp["reason"],90),"priority":"HIGH" if i==0 else "MEDIUM","owner":dp["name"],"status":"OPEN","source":f"{latest}회차"} for i,dp in enumerate(depts[:4])]

    # ── appendix ──
    apx=sect(md,"상세 부록")
    quotes=[{"label":a.strip(),"text":b.strip()} for a,b in re.findall(r'\*\*\d+\.\s*([^\*]+?)\*\*\s*\n+([^\n]+)', apx)]
    R["appendix"]={"quotes":quotes[:4],"slotHistory":hist,"surveySource":"PHQ-9 공식 한국어판 (Pfizer / phqscreeners.com)"}

    # ── summary (executive) ──
    obs=[]
    ks=sect(md,"") # not used
    R["summary"]={"lead":(R["narrative"]["hpi"] or R["narrative"]["presentingConcern"] or "")[:380],
        "observations":[{"text":clip(f["text"],80)} for f in R["riskSafety"]["flags"][:2]] + ([{"text":clip(R["clinicalSummary"]["slots"][0]["latest"],64)}] if slots else []),
        "handoffFocus":[{"text":clip(a["text"],72),"priority":a["priority"]} for a in R["actionItems"][:4]]}

    R["provenance"]={"reportId":R["report"]["id"],"period":f"{R['period']['firstDate']} – {R['period']['latestDate']} · {T.get('n_sessions')}세션 · {T.get('session_span_days')}일",
        "latestAssessment":dt(latest),"generatedAt":dt(latest),"dataSource":"자가보고(AI 대화형 문진) 종단 기록"}

    out=ROOT/"data"/f"report-{vp}.json"
    out.write_text(json.dumps(R, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"wrote {out}  (metrics {len(R['metrics'])}, slots {len(slots)}, hist {len(hist)}, figs {len(figs)})")

def kdir(x): return {"improved":"개선","worsened":"악화","unchanged":"변화 없음","unknown":"판정 보류"}.get(x,x or "")

if __name__ == "__main__":
    main()
