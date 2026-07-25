"use client";

import { useState } from "react";

import type { HandoffReport } from "../lib/api";

const Q_LABEL: Record<string, string> = { PHQ9: "우울 (PHQ-9)", GAD7: "불안 (GAD-7)" };
const SEV_LABEL: Record<string, string> = {
  minimal: "최소",
  mild: "경도",
  moderate: "중등도",
  moderately_severe: "중등도-중증",
  severe: "중증",
};
const RISK_LABEL: Record<string, string> = {
  low: "안전",
  medium: "주의",
  high: "위험",
  critical: "긴급",
};

/** FR-020 — Handoff 리포트를 EMR 붙여넣기용 구조화 평문으로. */
function toEmrText(report: HandoffReport, patientName: string): string {
  const L: string[] = [];
  L.push("[Neuro-Sync 사전 문진 리포트]");
  L.push(`환자: ${patientName}`);
  if (report.generatedAt) L.push(`생성: ${new Date(report.generatedAt).toLocaleString("ko-KR")}`);
  L.push("");

  if (report.questionnaires.length) {
    L.push("■ 표준 문진");
    for (const q of report.questionnaires) {
      L.push(`- ${Q_LABEL[q.type] ?? q.type}: ${q.totalScore}점 · ${SEV_LABEL[q.severity] ?? q.severity}`);
    }
    L.push("");
  }
  if (report.riskSignals.length) {
    L.push("■ 위험 신호");
    for (const r of report.riskSignals) {
      L.push(`- ${RISK_LABEL[r.level] ?? r.level}: ${r.category ?? "—"}`);
    }
    L.push("");
  }
  const n = report.narrative;
  if (n) {
    L.push("■ 요약");
    if (n.chief_complaint) L.push(`주호소: ${n.chief_complaint}`);
    if (n.present_illness) L.push(`현병력: ${n.present_illness}`);
    if (n.symptoms?.length) L.push(`주요 증상: ${n.symptoms.join(", ")}`);
    if (n.onset) L.push(`시작 시점: ${n.onset}`);
    if (n.recent_changes) L.push(`최근 변화: ${n.recent_changes}`);
    const saa = n.sleep_appetite_activity;
    const saaText = [
      saa?.sleep ? `수면 ${saa.sleep}` : null,
      saa?.appetite ? `식욕 ${saa.appetite}` : null,
      saa?.activity ? `활동 ${saa.activity}` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    if (saaText) L.push(`수면/식욕/활동: ${saaText}`);
    if (n.psych_history) L.push(`과거 정신건강 이력: ${n.psych_history}`);
    if (n.medications) L.push(`복용약: ${n.medications}`);
    if (n.clinician_attention?.length) L.push(`의료진 확인 필요: ${n.clinician_attention.join(", ")}`);
    if (n.evidence?.length) {
      L.push("");
      L.push("■ 원문 근거");
      for (const e of n.evidence) L.push(`- ${e.field}: "${e.quote}"`);
    }
  }
  L.push("");
  L.push("※ 본 리포트는 의료진 참고용이며 진단이 아닙니다.");
  return L.join("\n");
}

export function ReportActions({
  report,
  patientName,
}: {
  report: HandoffReport;
  patientName: string;
}) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(toEmrText(report, patientName));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="flex items-center gap-2 print:hidden">
      <button
        onClick={() => window.print()}
        className="rounded-lg border border-border-strong bg-surface px-3.5 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-ink"
      >
        인쇄 · PDF 저장
      </button>
      <button
        onClick={onCopy}
        className="rounded-lg bg-ink px-3.5 py-2 text-[13px] font-semibold text-white transition-opacity hover:opacity-90"
      >
        {copied ? "복사됨 ✓" : "EMR 복사"}
      </button>
    </div>
  );
}
