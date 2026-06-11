/**
 * Design tokens — derived from screen-spec §0.8 (lo-fi palette).
 * Brand mapping replaces `info` later; everything else stays grayscale + semantic.
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

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radius = {
  sm: 4,
  md: 8,
  lg: 12,
  pill: 999,
} as const;

export const fontSize = {
  caption: 12,
  body: 14,
  bodyLg: 16,
  title: 20,
  display: 28,
} as const;
