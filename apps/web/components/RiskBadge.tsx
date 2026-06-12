import { riskColor, type RiskLevel } from "../lib/tokens";

const LABEL: Record<RiskLevel, string> = {
  low: "안전",
  medium: "주의",
  high: "위험",
  critical: "긴급",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  const c = riskColor[level];
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-xs font-semibold ${c.bg} ${c.border} ${c.text}`}
      aria-label={`위험 등급: ${LABEL[level]}`}
    >
      <span aria-hidden>●</span>
      {LABEL[level]}
    </span>
  );
}
