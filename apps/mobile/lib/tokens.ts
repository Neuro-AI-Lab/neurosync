/**
 * Design tokens — monochrome system (white ground, ink text, red for danger only).
 * Interactive/primary = ink (near-black). Semantic color is reserved for
 * risk / emergency / destructive actions. Legacy keys are kept as aliases so
 * existing screens re-skin automatically.
 */

export const colors = {
  // ── ink / neutrals ──
  ink: "#121210",
  ink2: "#3B3B38",
  muted: "#8C8C86",
  faint: "#B3B3AD",
  surface: "#FFFFFF",
  surfaceElevated: "#F3F3F1",
  fill: "#F3F3F1",
  group: "#F1F1EF",
  line: "#ECECE8",
  lineStrong: "#D9D9D3",
  sep: "#E2E2DD",

  // ── interactive = ink ──
  accent: "#121210",
  accentSoft: "#F3F3F1",

  // ── semantic (danger reserved) ──
  danger: "#D93A31",
  dangerInk: "#C4302A",
  dangerSoft: "#FBEBE9",
  dangerLine: "#F1CDC8",
  warn: "#9A6A16",
  warnSoft: "#FBF0DA",
  onInk: "#FFFFFF",

  // ── legacy aliases (auto-remap old screens) ──
  textPrimary: "#121210",
  textSecondary: "#8C8C86",
  border: "#ECECE8",
  stateDanger: "#D93A31",
  stateWarning: "#9A6A16",
  stateSuccess: "#121210",
  stateInfo: "#121210",
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
  md: 10,
  lg: 14,
  xl: 18,
  pill: 999,
} as const;

export const fontSize = {
  micro: 11,
  caption: 12,
  body: 14,
  bodyLg: 16,
  lead: 17,
  title: 22,
  display: 28,
} as const;
