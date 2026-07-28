import { CTRS_META, ctrsFromLevel, type RiskLevel } from "../lib/tokens";

/**
 * 환자 목록용 CTRS(위기분류척도) 단계 배지 — `CTRS N · 라벨` 형식.
 * safety risk level을 위험성(Rating A) 기준 CTRS 단계로 환산해 표기하며,
 * RiskEvent가 없는 환자도 항상 `CTRS 5 · 안정`으로 표시한다(전원 단계 표기).
 */
export function CtrsBadge({ level }: { level: RiskLevel | null | undefined }) {
  const stage = ctrsFromLevel(level);
  const { label, badge } = CTRS_META[stage];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold tracking-tight ${badge.bg} ${badge.border} ${badge.text}`}
      aria-label={`CTRS ${stage}단계: ${label}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden />
      CTRS {stage} · {label}
    </span>
  );
}
