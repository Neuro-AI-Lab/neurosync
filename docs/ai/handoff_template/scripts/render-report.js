/* ============================================================
   render-report.js — JSON → HTML 바인딩 (8-page Editorial Clinical Handoff)
   최종 사용자용: 개발자 기술정보(모델명·세션ID·함수/변수명·파일명 등)는
   데이터에 없거나 렌더하지 않는다.
   ============================================================ */

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));
function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}. ${p(d.getMonth() + 1)}. ${p(d.getDate())}`;
}
const pad2 = (n) => String(n).padStart(2, "0");

/* 표준 임상 척도 정의 (데이터 아닌 코드에 고정) — 게이지·근거 표시용 */
const SCALES = {
  phq9:   { min: 0, max: 27, basis: "9개 문항 합산 · 각 0–3점",
            bands: [[0,4,"정상",0],[5,9,"경도",1],[10,14,"중등도",2],[15,19,"중등–중증",3],[20,27,"중증",4]] },
  safety: { min: 1, max: 5, basis: "위기 단계 척도 · 1(위험)–5(안정)",
            bands: [[1,1,"최긴급",4],[2,2,"고위험",3],[3,3,"급성",2],[4,4,"경도 우려",1],[5,5,"안정",0]] },
  auditc: { min: 0, max: 12, basis: "3개 문항 합산 · 각 0–4점",
            bands: [[0,3,"저위험",0],[4,7,"위험",2],[8,12,"고위험",4]] },
};
const CLAY_A = [0.02, 0.07, 0.12, 0.18, 0.24];
function gauge(m) {
  const S = SCALES[m.key];
  if (!S || m.value == null) return "";
  const span = S.max - S.min + 1;
  const segs = S.bands.map(([f, t, , tone]) =>
    `<span class="seg" style="flex:${t - f + 1}; background:rgba(166,70,47,${CLAY_A[tone]})"></span>`).join("");
  const left = ((m.value - S.min + 0.5) / span) * 100;
  return `<div class="m-scale">
    <div class="m-scale-bar">${segs}<span class="m-marker" style="left:${left.toFixed(1)}%"></span></div>
    <div class="m-scale-ticks"><span>${S.min}</span><span>${S.max}</span></div>
    <div class="m-basis">${esc(S.basis)} · <span class="cur">현재 ${esc(m.value)}점</span></div>
  </div>`;
}

/* ── Page 1 · Executive Handoff ─────────────────────────── */
function renderPage1(d) {
  const { report, patient, period, latestSession, summary, metrics } = d;
  $("#p1-eyebrow").textContent = "임상 인계 보고서";
  $("#p1-title").textContent = report.title;
  $("#p1-rid").textContent = report.id;
  $("#p1-meta").innerHTML = [
    ["환자", `${esc(patient.maskedName)} · ${esc(patient.id)} · ${esc(patient.ageSex)}`],
    ["최신 세션", `${esc(latestSession.number)}회차 · ${fmtDate(latestSession.date)}`],
    ["보고 기간", `${esc(period.days)}일 · ${esc(period.sessions)}세션`],
    ["생성일", fmtDate(report.generatedAt)],
  ].map(([k, v]) => `<div class="meta-item"><span class="k">${k}</span><span class="v">${v}</span></div>`).join("");
  $("#p1-lead").textContent = summary.lead;

  const chg = (m) => m.change == null ? "" :
    `<span class="m-change ${esc(m.direction || "")}">${m.change === 0 ? "→" : m.change > 0 ? "▲" : "▼"} ${Math.abs(m.change)}
      <span class="prev">이전 ${esc(m.previous)}</span></span>`;
  // 보고 기간(followUp)은 상단 메타로 충분 — 큰 지표는 임상 지표만(위계 구분)
  const labelKo = { "SAFETY LEVEL": "위기 단계", "FOLLOW-UP": "보고 기간" };
  $("#p1-metrics").innerHTML = metrics.filter((m) => m.key !== "followUp").map((m) => {
    const unit = m.unit ? `<span class="m-unit">${esc(m.unit)}</span>` : (m.max ? `<span class="m-unit">/ ${esc(m.max)}</span>` : "");
    return `<div class="metric keep-together"><div class="m-label">${esc(labelKo[m.label] || m.label)}</div>
      <div class="m-sub">${esc(m.sub || "")}</div><div class="m-value num">${esc(m.value)}${unit}</div>
      <div class="m-state">${esc(m.state || "")}</div>${chg(m)}${gauge(m)}</div>`;
  }).join("");

  $("#p1-observations").innerHTML = (summary.observations || []).slice(0, 4).map((o, i) =>
    `<li class="keep-together"><span class="idx num">${pad2(i + 1)}</span>
      <span class="otext">${esc(o.text)}</span><span class="osrc">${o.session ? "S" + esc(o.session) : ""}</span></li>`).join("");
  $("#p1-focus").innerHTML = (summary.handoffFocus || []).slice(0, 4).map((f, i) =>
    `<li class="keep-together"><span class="idx num">${pad2(i + 1)}</span>
      <div class="fcontent"><span class="otext">${esc(f.text)}</span>
      ${f.priority ? `<span class="prio ${esc(f.priority)}">${esc(f.priority)}</span>` : ""}</div></li>`).join("");
  $("#p1-disclaimer").textContent = d.disclaimer;
}

/* ── Page 2 · Risk & Safety ─────────────────────────────── */
function renderRisk(d) {
  const r = d.riskSafety;
  if (!r) { $("#page-2").hidden = true; return; }
  const c = r.current;
  $("#p2-current").innerHTML = `
    <div class="rc-assess">${esc(c.assessment)} — 위기 단계(CTRS) ${esc(c.ctrs)}/${esc(c.ctrsMax)} · ${esc(c.ctrsLabel)}</div>
    ${c.quote ? `<p class="rc-quote">“${esc(c.quote)}”</p>` : ""}
    <div class="risk-lines">
      <div class="rl"><span class="rk">자살사고 문항</span><span class="rv">${esc(c.item9)}</span></div>
      <div class="rl"><span class="rk">안전 의뢰</span><span class="rv">${esc(c.referral)}</span></div>
      <div class="rl"><span class="rk">문진 최신성</span><span class="rv">${esc(c.surveyStatus)}</span></div>
    </div>`;
  $("#p2-flags").innerHTML = (r.flags || []).map((f) =>
    `<div class="risk-flag ${esc(f.level)}"><span class="fdot"></span><span>${esc(f.text)}</span></div>`).join("");
  $("#p2-traj").innerHTML = (r.trajectory || []).map((t) =>
    `<div class="tl-item keep-together"><div class="tl-when"><span class="tl-date">${esc(t.date)}</span>
      <span class="tl-sess">Session ${esc(t.session)}</span></div>
      <div class="tl-body"><div class="tl-change">${esc(t.note)}</div></div></div>`).join("");
}

/* ── Page 3 · Patient Narrative ─────────────────────────── */
function renderNarrative(d) {
  const n = d.narrative || {};
  $("#p3-concern").textContent = n.presentingConcern || "";
  $("#p3-hpi").textContent = n.hpi || "";
  $("#p3-mse").textContent = n.mse || "";
  const q = n.quote;
  $("#p3-quote").innerHTML = q ? `<div class="cq-eyebrow">환자 진술</div>
    <p class="cq-text">“${esc(q.text)}”</p><div class="cq-attr">Session ${esc(q.session)} · ${esc(q.attribution || "")}</div>` : "";
  $("#p3-rail").innerHTML = (n.annotations || []).map((a) =>
    `<div class="rail-item"><span class="rk">${esc(a.label)}</span><span class="rv">${esc(a.value)}</span>
      ${a.source ? `<span class="rsrc">${esc(a.source)}</span>` : ""}</div>`).join("");
}

/* ── Page 4 · Clinical Summary & Surveys ────────────────── */
function renderClinical(d) {
  const cs = d.clinicalSummary || {};
  // 문진 스냅샷 표(p4-note/p4-slots)는 본문에서 제거됨(슬롯 전체 이력이 대체). 요소가
  // 있을 때만 채운다.
  const noteEl = $("#p4-note");
  if (noteEl) noteEl.textContent = cs.note || "";
  const slotEl = $("#p4-slots");
  if (slotEl) slotEl.innerHTML = (cs.slots || []).map((s) =>
    `<div class="slot-row keep-together"><span class="sl-k">${esc(s.label)}</span>
      <span class="sl-v">${esc(s.latest)}</span>
      <span class="sl-meta"><span class="sl-src">${esc(s.source)}</span>
      ${s.changes ? `<span class="sl-chg">변경 ${esc(s.changes)}회</span>` : ""}</span></div>`).join("");

  const p = (d.surveys || {}).phq9;
  if (p) {
    $("#p4-survey-head").innerHTML = `
      <span class="sv-score num">${esc(p.score)}<span class="sv-max"> / ${esc(p.max)}</span></span>
      <span class="sv-sev">${esc(p.name)} · ${esc(p.severity)} 범위</span>
      <span class="sv-when">${esc(p.session)}회차 · ${fmtDate(p.date)} · ${esc(p.mode)}</span>`;
    $("#p4-phq").innerHTML = (p.items || []).map((it) => {
      const dots = [0, 1, 2].map((i) => `<span class="pi-dot ${i < it.score ? "on" : ""}"></span>`).join("");
      return `<div class="phq-item ${it.no === 9 ? "crit" : ""}">
        <span class="pi-label"><span class="pi-no num">${esc(it.no)}</span>${esc(it.label)}</span>
        <span class="pi-bar">${dots}<span class="pi-num">${esc(it.score)}</span></span></div>`;
    }).join("");
    const ac = (d.surveys || {}).auditc;
    const acStr = ac ? "AUDIT-C(음주): " + ac.points.map((x) => `${x.s}회차 ${x.score}/${ac.max}`).join(" → ") + ` · ${esc(ac.severity)}` : "";
    $("#p4-auditc").textContent = `${p.item9Note} · ${p.scaleNote}` + (acStr ? `　|　${acStr}` : "");
  }
}

/* ── Page 5 · Longitudinal Course ───────────────────────── */
function renderLongitudinal(d) {
  $("#p5-timeline").innerHTML = (d.timeline || []).slice(0, 6).map((t) =>
    `<div class="tl-item keep-together"><div class="tl-when"><span class="tl-date">${esc(t.date)}</span>
      <span class="tl-sess">Session ${esc(t.session)}</span></div>
      <div class="tl-body"><div class="tl-change">${esc(t.change)}</div>
      ${t.scale ? `<span class="tl-scale">${esc(t.scale)}</span>` : ""}</div></div>`).join("");

  // 초진·최신(thenNow) 블록 제거 — baseline/latest 는 척도 변화 요약과 차트 첫/끝
  // 마커에 이미 담겨 중복이므로 렌더하지 않는다.

  const sc = d.scaleChanges;
  if (sc) {
    $("#p5-overall").textContent = sc.overall ? `· 전체 ${sc.overall}` : "";
    const dirCls = (x) => x === "개선" ? "improved" : x === "악화" ? "worsened" : "unchanged";
    const ep = (e) => `<span class="sc-val">${esc(e.v)}</span><span class="sc-when">${esc(e.s)}회차${e.d ? ` · ${esc(e.d)}` : ""}</span>`;
    $("#p5-scale").innerHTML = (sc.rows || []).map((r) => {
      let line;
      if (Array.isArray(r.steps) && r.steps.length) {
        // 변화 지점마다 나열(초기값 + 값이 바뀐 회차). 변화 없으면 단일값 + '변화 없음'.
        const chain = r.steps.map(ep).join('<span class="sc-arrow">→</span>');
        const suffix = (r.nChanges === 0)
          ? '<span class="sc-note">전 기간 변화 없음</span>'
          : (r.latest && r.latest.s !== r.steps[r.steps.length - 1].s
              ? `<div class="sc-note">최신 ${esc(r.latest.s)}회차 ${esc(r.latest.v)} 유지</div>` : "");
        line = `<div class="sc-line">${chain}</div>${suffix}`;
      } else if (r.from && r.to) {                       // 구 스키마 호환
        line = `<div class="sc-line">${ep(r.from)}<span class="sc-arrow">→</span>${ep(r.to)}</div>`;
      } else {
        line = `<div class="sc-line">${esc(r.detail || "")}</div>`;
      }
      return `<div class="scale-row">
        <div class="sc-head"><span class="sc-m">${esc(r.metric)}</span>
          <span class="sc-d ${dirCls(r.direction)}">초기 대비 ${esc(r.direction)}</span></div>
        ${line}</div>`;
    }).join("");
    $("#p5-scale-notes").innerHTML = (sc.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
  }
}

/* ── Page 6 · Data Editorial ────────────────────────────── */
function renderData(d) {
  const fig = (d.figures || [])[0];
  if (!fig) return;                         // 차트 없으면 종단 섹션의 차트 영역만 비움
  $("#p6-interp").textContent = fig.interpretation || "";
  // 현재/기준/변화(cbc) 카드 제거 — 척도 변화 요약과 중복.
  $("#p6-figure").innerHTML = `
    <img src="${esc(fig.image)}" alt="${esc(fig.caption || "종단 차트")}" />
    <div class="fig-note"><span class="axkey">축 값</span> PHQ-9 세로축 0(정상)–27(중증), 음영은 중증도 구간(위로 갈수록 중증) · 위기 단계(CTRS) 세로축 1(위험)–5(안정)</div>
    <figcaption><span class="fig-id">${esc(fig.id)}</span>${esc(fig.caption || "")}<span class="fig-src">${esc(fig.source || "")}</span></figcaption>`;

  const f2 = (d.figures || []).find((f) => f.slot === "secondary");
  if (f2) $("#p6-figure2").innerHTML = `
    <img src="${esc(f2.image || "assets/fig02_sentiment_slotfill.png")}" alt="보조 종단 지표" />
    <div class="fig-note"><span class="axkey">축 값</span> 정서 극성 −1(부정)·0(중립)·+1(긍정) · 문진 항목 충족도 0–8(수집·확인된 핵심 문진 항목 수, 8이면 정보 완비)</div>
    <figcaption><span class="fig-id">${esc(f2.id)}</span>${esc(f2.caption || "")}</figcaption>`;
}

/* ── Page 7 · Handoff Actions + Care Routing + Provenance ── */
// 가이드라인 §4: 영문 업무 메타데이터(PRIORITY/STATUS/OWNER/SOURCE) 대신 한글.
// STATUS(OPEN/CLOSED)는 업무관리 시스템 미연동이므로 제거.
const PRIO_KO = { HIGH: "우선 확인", MEDIUM: "확인 권장", LOW: "경과 관찰",
                  high: "우선 확인", medium: "확인 권장", low: "경과 관찰" };
function renderActions(d) {
  $("#p7-actions").innerHTML = (d.actionItems || []).slice(0, 5).map((a) => {
    const prio = a.priority ? (PRIO_KO[a.priority] || esc(a.priority)) : "";
    return `<div class="action-item keep-together"><span class="ai-no num">${pad2(a.no)}</span>
      <div><div class="ai-text">${esc(a.text)}</div><div class="ai-meta">
        ${prio ? `<span class="m"><span class="mv ${esc(a.priority)}">${esc(prio)}</span></span>` : ""}
        ${a.owner ? `<span class="m"><span class="mk">담당</span><span class="mv">${esc(a.owner)}</span></span>` : ""}
        ${a.source ? `<span class="m"><span class="mk">근거</span><span class="mv">${esc(a.source)}</span></span>` : ""}
      </div></div></div>`;
  }).join("");

  const cr = d.careRouting || {};
  $("#p7-routing").innerHTML = (cr.recommendedDepartments || []).map((x) =>
    `<div class="care-row"><span class="cr-dept">${esc(x.name)}</span><span class="cr-reason">${esc(x.reason)}</span></div>`).join("");
  $("#p7-questionnaire").textContent = cr.recommendedQuestionnaire ? `추천 설문 · ${cr.recommendedQuestionnaire}` : "";
  $("#p7-medication").textContent = cr.medicationNote ? `약물 정보 · ${cr.medicationNote}` : "";

  const pv = d.provenance || {};
  $("#p7-prov").innerHTML = [
    ["Report ID", pv.reportId], ["보고 기간", pv.period], ["최신 평가일", pv.latestAssessment],
    ["생성일", pv.generatedAt], ["데이터 출처", pv.dataSource],
  ].filter(([, v]) => v).map(([k, v]) => `<div><span class="am-k">${k}</span> · ${esc(v)}</div>`).join("");
}

/* ── Page 8 · Appendix ──────────────────────────────────── */
function renderAppendix(d) {
  const a = d.appendix;
  if (!a) { $("#page-8").hidden = true; $("#page-9").hidden = true; return; }

  // FIG.03 차트 제거 — 아래 유사도 순위(최신 스냅샷)와 같은 F2 데이터라 중복.
  const f3 = (d.figures || []).find((f) => f.slot === "appendix");
  const rk = f3 && f3.ranking;
  $("#p8-ranking").innerHTML = rk ? `
    <div class="ar-title">질환 유사도 순위 (${esc(rk.asOf)} 기준 · 참고·비진단)</div>
    ${rk.items.map((x) => `<div class="ar-row"><span class="ar-rank">${esc(x.rank)}</span>
      <span class="ar-name">${esc(x.name)}</span><span class="ar-score num">${esc(x.score)}</span></div>`).join("")}
    ${rk.others ? `<div class="ar-others">기타 후보 · ${esc(rk.others)}</div>` : ""}` : "";

  // 위험 관련 발화는 '위험·안전 평가' 섹션에 이미 인용되므로 부록 전문 인용에서 제외.
  $("#p8-quotes").innerHTML = (a.quotes || [])
    .filter((q) => !/위험|자살|자해/.test(q.label || ""))
    .map((q) => `<div class="apx-quote"><span class="aq-k">${esc(q.label)}</span><span class="aq-t">“${esc(q.text)}”</span></div>`).join("");
  $("#p8-source").textContent = a.surveySource || "";
  // 세션→일자 매핑(부록 이력에 날짜 표기용). 이력 point 에 d 가 없으면 hero 차트
  // 계열(ctrs·phq9)의 세션-날짜에서 보완한다.
  const heroFig = (d.figures || []).find((f) => !f.slot || f.slot === "hero") || (d.figures || [])[0] || {};
  const sdate = {};
  for (const key of ["ctrs", "phq9"])
    for (const pt of (((heroFig.series || {})[key] || {}).points || []))
      if (pt.d && !(pt.s in sdate)) sdate[pt.s] = pt.d;
  // 슬롯별 전체 이력: 실제로 값이 변한 슬롯만(불변 슬롯은 본문/요약과 중복). 각 회차에 일자 표기.
  $("#p9-hist").innerHTML = (a.slotHistory || [])
    .filter((h) => new Set((h.points || []).map((p) => p.text)).size > 1)
    .map((h) =>
      `<div class="ah-slot">${esc(h.slot)}</div>` +
      h.points.map((p) => {
        const dd = p.d || sdate[p.s];
        return `<div class="ah-step"><span class="ah-s">S${esc(p.s)}${dd ? ` · ${esc(fmtDate(dd))}` : ""}</span><span>${esc(p.text)}</span></div>`;
      }).join("")
    ).join("");

  // 빈 블록(라벨만 남는 것) 자동 숨김 — 가이드라인 §10.1.
  // 예: 설문 미시행 → '문항별 응답' 빈칸, F2 llm_only → 'AI 참고 지표' 순위 없음.
  const hideEmpty = (sel, wrap) => {
    const el = $(sel);
    if (el && !el.innerHTML.trim()) { const c = el.closest(wrap); if (c) c.hidden = true; }
  };
  hideEmpty("#p4-phq", ".section");      // 시행 설문 — 문항별 응답
  hideEmpty("#p8-ranking", ".section");  // AI 참고 지표 (비진단)
  hideEmpty("#p8-quotes", ".col-7");     // 전문 인용
  hideEmpty("#p8-source", ".col-5");     // 문항 출처
  hideEmpty("#p9-hist", ".block");       // 슬롯별 전체 변화 이력
}

/* 러닝 헤더/푸터(@page 마진박스)를 리포트 데이터로 동적 주입.
   Chrome은 @page 안에서 string()을 지원하지 않으므로 JS가 리터럴 규칙을 삽입한다. */
function injectRunningHeader(d) {
  const t = String(d.report.title || "").replace(/"/g, "");
  const id = String(d.report.id || "").replace(/"/g, "");
  const st = document.createElement("style");
  st.textContent = `@page {
    @top-left { content: "NeuroSync"; font-size: 7.5pt; letter-spacing: 0.12em; color: #6E7881; }
    @top-right { content: "${t} · ${id}"; font-size: 7.5pt; color: #6E7881; }
  }`;
  document.head.appendChild(st);
}

async function main() {
  const p = new URLSearchParams(location.search).get("p");
  const path = p ? `./data/report-${p}.json` : "./data/sample-report.json";
  const d = await (await fetch(path)).json();
  document.title = `${d.report.title} — ${d.patient.id}`;
  injectRunningHeader(d);
  document.querySelectorAll(".footer-doc").forEach((e) => { e.textContent = `NeuroSync · ${d.report.id}`; });
  document.querySelectorAll(".rh-doc").forEach((e) => { e.textContent = `${d.report.title} · ${d.report.id}`; });
  renderPage1(d); renderRisk(d); renderNarrative(d); renderClinical(d);
  renderLongitudinal(d); renderData(d); renderActions(d); renderAppendix(d);
  document.body.dataset.rendered = "1";
}
main().catch((e) => { console.error(e); document.body.dataset.error = String(e); });
