import Link from "next/link";

import type { PatientListItem as PatientListItemT } from "../lib/api";
import { RiskBadge } from "./RiskBadge";

function relative(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const ago = Date.now() - t;
  const min = Math.round(ago / 60000);
  if (min < 1) return "방금 전";
  if (min < 60) return `${min}분 전`;
  if (min < 60 * 24) return `${Math.round(min / 60)}시간 전`;
  return `${Math.round(min / 60 / 24)}일 전`;
}

export function PatientListItem({ item }: { item: PatientListItemT }) {
  return (
    <Link
      href={`/dashboard/patients/${item.userId}`}
      className="block bg-surface border border-border rounded-lg p-4 hover:bg-surface-elevated transition-colors"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-text-primary truncate">
              {item.name}
            </span>
            {item.isMinor ? (
              <span className="text-xs text-state-warning border border-amber-200 rounded px-1.5">
                만 14세 미만
              </span>
            ) : null}
          </div>
          <p className="text-sm text-text-secondary truncate">{item.email}</p>
          <p className="text-xs text-text-secondary">
            {item.birthYear}년생 · 마지막 활동 {relative(item.latestSessionAt)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {item.latestRisk ? <RiskBadge level={item.latestRisk.level} /> : null}
          {item.riskEventCount > 0 ? (
            <span className="text-xs text-text-secondary">
              위험 이벤트 {item.riskEventCount}건
            </span>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
