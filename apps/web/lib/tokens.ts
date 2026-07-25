/**
 * Design tokens — 모바일 앱(apps/mobile/lib/tokens.ts)과 동일한 모노크롬 시스템.
 * 색은 위험(danger)·경고(warn)에만. 나머지는 무채색. Tailwind 클래스는
 * tailwind.config.ts의 토큰을 참조한다.
 */

export const colors = {
  textPrimary: "#121210",
  ink2: "#3B3B38",
  textSecondary: "#8C8C86",
  faint: "#B3B3AD",
  canvas: "#FAFAF9",
  surface: "#FFFFFF",
  surfaceElevated: "#F3F3F1",
  border: "#ECECE8",
  borderStrong: "#D9D9D3",
  stateDanger: "#D93A31",
  dangerInk: "#C4302A",
  stateWarning: "#9A6A16",
  // 링크·성공은 모노크롬이라 ink로 수렴
  stateSuccess: "#121210",
  stateInfo: "#121210",
} as const;

/**
 * 위험도 → 표면(카드 배경·테두리·텍스트). 카드 위에 본문이 얹히므로 항상 soft.
 * 규율: low=무채색, medium=warn, high/critical=danger. 강조는 배지가 담당.
 */
export const riskColor = {
  low: { bg: "bg-surface-elevated", border: "border-border", text: "text-text-secondary" },
  medium: { bg: "bg-warn-soft", border: "border-warn-line", text: "text-warn" },
  high: { bg: "bg-danger-soft", border: "border-danger-line", text: "text-danger-ink" },
  critical: { bg: "bg-danger-soft", border: "border-state-danger", text: "text-danger-ink" },
} as const;

/**
 * 위험도 → 배지(pill). 표면보다 강하게. critical만 solid red로 시선을 끈다.
 */
export const riskBadge = {
  low: { bg: "bg-surface", border: "border-border-strong", text: "text-text-secondary", dot: "bg-faint" },
  medium: { bg: "bg-warn-soft", border: "border-warn-line", text: "text-warn", dot: "bg-warn" },
  high: { bg: "bg-danger-soft", border: "border-danger-line", text: "text-danger-ink", dot: "bg-state-danger" },
  critical: { bg: "bg-state-danger", border: "border-state-danger", text: "text-white", dot: "bg-white" },
} as const;

export type RiskLevel = keyof typeof riskColor;
