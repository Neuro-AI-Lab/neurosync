import Link from "next/link";

import type { SessionSummary } from "../lib/api";
import { RiskBadge } from "./RiskBadge";

const statusLabel: Record<string, string> = {
  in_progress: "진행 중",
  submitted: "제출됨",
  report_ready: "리포트 준비됨",
  closed: "종료됨",
};

export function SessionCard({
  patientId,
  session,
}: {
  patientId: string;
  session: SessionSummary;
}) {
  return (
    <Link
      href={`/dashboard/patients/${patientId}/sessions/${session.id}`}
      className="group block bg-surface border border-border rounded-xl p-4 transition-colors hover:border-border-strong"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <p className="font-semibold tracking-tight text-text-primary">
            {statusLabel[session.status] ?? session.status}
          </p>
          <p className="text-[13px] text-text-secondary tabular-nums">
            시작 {new Date(session.createdAt).toLocaleString("ko-KR")}
          </p>
          {session.submittedAt ? (
            <p className="text-[13px] text-text-secondary tabular-nums">
              제출 {new Date(session.submittedAt).toLocaleString("ko-KR")}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {session.latestRisk ? <RiskBadge level={session.latestRisk.level} /> : null}
          {session.riskEventCount > 0 ? (
            <span className="text-xs text-text-secondary tabular-nums">
              위험 {session.riskEventCount}건
            </span>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
