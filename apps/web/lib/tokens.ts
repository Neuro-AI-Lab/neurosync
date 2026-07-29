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

/**
 * CTRS(위기분류척도, Crisis Triage Rating Scale) 단계 표기.
 * 대시보드 환자 목록은 safety risk level을 위험성(Rating A) 기준 CTRS 단계로 환산해
 * 표기한다: critical→1(고위험) … RiskEvent 없음→5(안정). (앱 서버 `_RISK_TO_CTRS`와 동일)
 */
export type CtrsStage = 1 | 2 | 3 | 4 | 5;

export function ctrsFromLevel(level: RiskLevel | null | undefined): CtrsStage {
  switch (level) {
    case "critical":
      return 1;
    case "high":
      return 2;
    case "medium":
      return 3;
    case "low":
      return 4;
    default:
      return 5; // RiskEvent 없음 = 위험 신호 없음
  }
}

// 중증도 그라데이션: 1(고위험)로 갈수록 강한 위험색, 5(안정)로 갈수록 옅은 중립.
// 1은 solid red + 흰 글씨로 대비 확보(기존엔 배경 CSS 미생성으로 흰 배경에 안 보였음).
export const CTRS_META: Record<
  CtrsStage,
  { label: string; badge: { bg: string; border: string; text: string; dot: string } }
> = {
  1: {
    label: "고위험",
    badge: { bg: "bg-state-danger", border: "border-state-danger", text: "text-white", dot: "bg-white" },
  },
  2: {
    label: "위험",
    badge: { bg: "bg-danger-soft", border: "border-state-danger", text: "text-danger-ink", dot: "bg-state-danger" },
  },
  3: {
    label: "주의",
    badge: { bg: "bg-warn-soft", border: "border-warn-line", text: "text-warn", dot: "bg-warn" },
  },
  4: {
    label: "관찰",
    badge: { bg: "bg-surface", border: "border-border-strong", text: "text-ink2", dot: "bg-text-secondary" },
  },
  5: {
    label: "안정",
    badge: { bg: "bg-surface-elevated", border: "border-border", text: "text-text-secondary", dot: "bg-faint" },
  },
};
