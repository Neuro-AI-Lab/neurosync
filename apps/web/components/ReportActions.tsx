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
  // BUG-066 fix (see HandoffReportView.tsx): `HandoffNarrative` mirrors
  // ai-server's real `report_markdown`-primary shape — the previous
  // chief_complaint/present_illness/... fields here were never actually
  // produced by ai-server. Mirror the same fields HandoffReportView renders.
  const n = report.narrative;
  if (n) {
    L.push("■ 요약");
    L.push(n.report_markdown);
    if (n.missing_slots?.length) {
      L.push("");
      L.push(`누락된 항목: ${n.missing_slots.join(", ")}`);
    }
    if (n.evidence_packets?.length) {
      L.push("");
      L.push("■ 원문 근거");
      for (const e of n.evidence_packets) {
        L.push(`- ${e.source_type} (${e.source_ref}): ${e.content_summary}`);
      }
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
