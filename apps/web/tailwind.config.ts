import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Lo-fi tokens from screen-spec §0.8. Brand mapping decided later.
        surface: "#FFFFFF",
        "surface-elevated": "#F8FAFC",
        border: "#E2E8F0",
        "text-primary": "#0F172A",
        "text-secondary": "#64748B",
        "state-danger": "#DC2626",
        "state-warning": "#D97706",
        "state-success": "#059669",
        "state-info": "#2563EB",
      },
    },
  },
  plugins: [],
};

export default config;
