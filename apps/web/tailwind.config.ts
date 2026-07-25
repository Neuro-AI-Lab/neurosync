import type { Config } from "tailwindcss";

/**
 * 모노크롬 디자인 시스템 — 모바일 앱(lib/tokens.ts)과 동일 언어.
 * 흰 바탕 · ink 텍스트 · 색은 위험(danger)과 경고(warn)에만. 나머지는 무채색.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── 바탕 / 표면 ──
        canvas: "#FAFAF9", // 페이지 바탕(살짝 웜 뉴트럴) — 흰 카드가 떠 보이게
        surface: "#FFFFFF", // 카드 표면
        "surface-elevated": "#F3F3F1", // 미묘한 채움(코드블록·칩)
        group: "#F1F1EF",
        // ── 선 ──
        border: "#ECECE8",
        "border-strong": "#D9D9D3",
        sep: "#E2E2DD",
        // ── ink / 무채색 텍스트 ──
        "text-primary": "#121210",
        ink: "#121210",
        ink2: "#3B3B38",
        "text-secondary": "#8C8C86",
        faint: "#B3B3AD",
        // ── 위험(danger) ──
        "state-danger": "#D93A31",
        "danger-ink": "#C4302A",
        "danger-soft": "#FBEBE9",
        "danger-line": "#F1CDC8",
        // ── 경고(warn) ──
        "state-warning": "#9A6A16",
        warn: "#9A6A16",
        "warn-soft": "#FBF0DA",
        "warn-line": "#EBD9A8",
        // ── 링크·성공: 모노크롬이라 ink로 수렴 ──
        "state-success": "#121210",
        "state-info": "#121210",
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "Pretendard Variable",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Apple SD Gothic Neo"',
          '"Malgun Gothic"',
          '"Noto Sans KR"',
          "system-ui",
          "sans-serif",
        ],
      },
      borderRadius: {
        xl: "0.875rem", // 14px — 모바일 카드 라운드
        "2xl": "1rem", // 16px
      },
    },
  },
  plugins: [],
};

export default config;
