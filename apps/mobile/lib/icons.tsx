/**
 * Stroke line-icons (react-native-svg) — the monochrome design leans on thin,
 * consistent 1.7–2.2px strokes rather than colored emoji. Every icon inherits
 * `color` (defaults to ink) so it re-tints per context (ink / muted / danger).
 */

import Svg, { Circle, Path, Rect } from "react-native-svg";

import { colors } from "./tokens";

export type IconProps = {
  size?: number;
  color?: string;
  strokeWidth?: number;
};

function base(size: number) {
  return { width: size, height: size, viewBox: "0 0 24 24" } as const;
}

export function ChevronLeft({ size = 20, color = colors.ink, strokeWidth = 2.2 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M15 4 7 12l8 8" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function ChevronRight({ size = 20, color = colors.faint, strokeWidth = 2.2 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M9 18l6-6-6-6" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function ArrowRight({ size = 20, color = colors.ink, strokeWidth = 2.2 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M5 12h14M13 6l6 6-6 6" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function ArrowUp({ size = 20, color = colors.ink, strokeWidth = 2.1 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M12 19V5M6 11l6-6 6 6" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function Mic({ size = 20, color = colors.ink, strokeWidth = 1.8 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Rect x="9" y="2" width="6" height="12" rx="3" stroke={color} strokeWidth={strokeWidth} />
      <Path d="M5 11a7 7 0 0 0 14 0M12 18v3" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function Stop({ size = 16, color = "#FFFFFF" }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Rect x="6" y="6" width="12" height="12" rx="2.5" fill={color} />
    </Svg>
  );
}

export function Phone({ size = 20, color = colors.ink, strokeWidth = 1.9 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path
        d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function Home({ size = 21, color = colors.ink, strokeWidth = 1.7 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M3 10.5 12 3l9 7.5" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M5 9.5V21h14V9.5" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function Records({ size = 21, color = colors.ink, strokeWidth = 1.7 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path
        d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function Gear({ size = 21, color = colors.ink, strokeWidth = 1.7 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Circle cx="12" cy="12" r="3.2" stroke={color} strokeWidth={strokeWidth} />
      <Path
        d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 1.2-2.9H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 5 7"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function Check({ size = 16, color = "#FFFFFF", strokeWidth = 3 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M20 6 9 17l-5-5" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function Shield({ size = 13, color = colors.muted, strokeWidth = 1.9 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Rect x="4" y="10" width="16" height="10" rx="2" stroke={color} strokeWidth={strokeWidth} />
      <Path d="M8 10V7a4 4 0 0 1 8 0v3" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function Doc({ size = 17, color = colors.muted, strokeWidth = 1.7 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M14 2v6h6M9 13h6M9 17h4" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function Hospital({ size = 21, color = colors.ink, strokeWidth = 1.7 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path d="M4 21V6a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v15" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M2 21h20" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
      <Path d="M12 8v5M9.5 10.5h5" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
    </Svg>
  );
}

export function Chat({ size = 20, color = colors.ink, strokeWidth = 1.7 }: IconProps) {
  return (
    <Svg {...base(size)} fill="none">
      <Path
        d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.8-.9L3 20l1.1-4.1A8.4 8.4 0 1 1 21 11.5Z"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

/** Onboarding mark — three concentric rings + a filled center (calm, clinical). */
export function ConcentricMark({ size = 76 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 76 76" fill="none">
      <Circle cx="38" cy="38" r="35" stroke={colors.lineStrong} />
      <Circle cx="38" cy="38" r="23" stroke={colors.lineStrong} />
      <Circle cx="38" cy="38" r="11.5" stroke={colors.ink} strokeWidth={1.4} />
      <Circle cx="38" cy="38" r="3.5" fill={colors.ink} />
    </Svg>
  );
}
