import { riskBadge, type RiskLevel } from "../lib/tokens";

const LABEL: Record<RiskLevel, string> = {
  low: "안전",
  medium: "주의",
  high: "위험",
  critical: "긴급",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  const c = riskBadge[level];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold tracking-tight ${c.bg} ${c.border} ${c.text}`}
      aria-label={`위험 등급: ${LABEL[level]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} aria-hidden />
      {LABEL[level]}
    </span>
  );
}
