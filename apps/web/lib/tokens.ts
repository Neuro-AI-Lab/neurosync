/**
 * Design tokens — derived from screen-spec §0.8 (lo-fi palette).
 * Tailwind classes also reference these via tailwind.config.ts.
 */

export const colors = {
  textPrimary: "#0F172A",
  textSecondary: "#64748B",
  surface: "#FFFFFF",
  surfaceElevated: "#F8FAFC",
  border: "#E2E8F0",
  stateDanger: "#DC2626",
  stateWarning: "#D97706",
  stateSuccess: "#059669",
  stateInfo: "#2563EB",
} as const;

export const riskColor = {
  low: { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700" },
  medium: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700" },
  high: { bg: "bg-orange-50", border: "border-orange-200", text: "text-orange-700" },
  critical: { bg: "bg-red-50", border: "border-red-300", text: "text-red-700" },
} as const;

export type RiskLevel = keyof typeof riskColor;
