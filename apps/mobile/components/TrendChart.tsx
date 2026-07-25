/**
 * 점수 추이 차트 (핸드오프 문서 수정 7 · F4 종단 추론).
 *
 * 여러 방문에 걸친 표준 척도 점수(PHQ-9·GAD-7)를 monotone 라인으로 그린다.
 * 색은 위험(빨강)에만 쓰는 디자인 규칙에 따라, 두 지표는 **실선(PHQ-9) vs
 * 점선(GAD-7) + 채운 점 vs 빈 점**으로 구분한다. 점수는 높을수록 중증이라
 * 선이 아래로 내려가면 호전이다.
 *
 * CTRS는 위험 단계(1~5)이며 **숫자가 낮을수록 위험**(1=최고위험)이라, 오해를
 * 막기 위해 라인에 섞지 않고 하단에 단계 배지 + "낮을수록 위험" 캡션으로 둔다.
 *
 * v3 원칙 1(NFR v3-2): 환자 본인 응답 기반 척도 점수만 시각화한다. AI 추정
 * 도메인·질환명은 표시하지 않는다.
 */

import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Line, Polyline, Text as SvgText } from "react-native-svg";

import type { TrendDirection, TrendPoint } from "../lib/api";
import { colors } from "../lib/tokens";

const CHART_H = 128;
const PAD_T = 12;
const PAD_B = 22; // 날짜 라벨 공간
const PAD_X = 14;
const Y_MAX = 27; // PHQ-9 최고점 기준 공통 상한 (GAD-7 21도 수용).

const DIRECTION_KO: Record<TrendDirection, string> = {
  improved: "호전 추세",
  worsened: "악화 추세",
  unchanged: "유지",
  unknown: "추이 정보 부족",
};

function mmdd(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

function xAt(i: number, n: number, w: number): number {
  if (n <= 1) return w / 2;
  return PAD_X + (i * (w - PAD_X * 2)) / (n - 1);
}

function yAt(score: number, h: number): number {
  const plot = h - PAD_T - PAD_B;
  return PAD_T + plot * (1 - Math.min(score, Y_MAX) / Y_MAX);
}

function polyline(
  points: TrendPoint[],
  pick: (p: TrendPoint) => number | null,
  w: number,
  h: number,
): { line: string; dots: { x: number; y: number }[] } {
  const dots: { x: number; y: number }[] = [];
  const coords: string[] = [];
  points.forEach((p, i) => {
    const v = pick(p);
    if (v == null) return;
    const x = xAt(i, points.length, w);
    const y = yAt(v, h);
    coords.push(`${x},${y}`);
    dots.push({ x, y });
  });
  return { line: coords.join(" "), dots };
}

export function TrendChart({
  points,
  direction,
}: {
  points: TrendPoint[];
  direction: TrendDirection;
}) {
  const [w, setW] = useState(0);

  if (points.length < 2) {
    return (
      <View style={styles.wrap}>
        <Text style={styles.emptyText}>
          비교할 이전 방문 기록이 아직 없어요. 다음 방문부터 추이를 볼 수 있어요.
        </Text>
      </View>
    );
  }

  const phq = polyline(points, (p) => p.phq9, w, CHART_H);
  const gad = polyline(points, (p) => p.gad7, w, CHART_H);
  const hasCtrs = points.some((p) => p.ctrsLevel != null);

  return (
    <View style={styles.wrap}>
      <View style={styles.head}>
        <Text style={styles.title}>점수 추이</Text>
        <View style={styles.dirPill}>
          <Text style={styles.dirText}>{DIRECTION_KO[direction]}</Text>
        </View>
      </View>

      <View style={styles.plot} onLayout={(e) => setW(e.nativeEvent.layout.width)}>
        {w > 0 ? (
          <Svg width={w} height={CHART_H}>
            {/* 기준선 (상·하) */}
            <Line
              x1={PAD_X}
              y1={PAD_T}
              x2={w - PAD_X}
              y2={PAD_T}
              stroke={colors.line}
              strokeWidth={1}
            />
            <Line
              x1={PAD_X}
              y1={CHART_H - PAD_B}
              x2={w - PAD_X}
              y2={CHART_H - PAD_B}
              stroke={colors.line}
              strokeWidth={1}
            />

            {/* GAD-7 — 점선 + 빈 점 */}
            <Polyline
              points={gad.line}
              fill="none"
              stroke={colors.muted}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              strokeLinejoin="round"
            />
            {gad.dots.map((d, i) => (
              <Circle
                key={`g${i}`}
                cx={d.x}
                cy={d.y}
                r={3.5}
                fill={colors.surface}
                stroke={colors.muted}
                strokeWidth={1.5}
              />
            ))}

            {/* PHQ-9 — 실선 + 채운 점 */}
            <Polyline
              points={phq.line}
              fill="none"
              stroke={colors.ink}
              strokeWidth={2}
              strokeLinejoin="round"
            />
            {phq.dots.map((d, i) => (
              <Circle key={`p${i}`} cx={d.x} cy={d.y} r={3.5} fill={colors.ink} />
            ))}

            {/* 날짜 라벨 */}
            {points.map((p, i) => (
              <SvgText
                key={`x${i}`}
                x={xAt(i, points.length, w)}
                y={CHART_H - 6}
                fontSize={9.5}
                fill={colors.faint}
                textAnchor="middle"
              >
                {mmdd(p.date)}
              </SvgText>
            ))}
          </Svg>
        ) : null}
      </View>

      {/* 범례 */}
      <View style={styles.legend}>
        <View style={styles.legendItem}>
          <View style={styles.solidLine} />
          <Text style={styles.legendText}>PHQ-9 (우울)</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={styles.dashRow}>
            <View style={styles.dash} />
            <View style={styles.dash} />
            <View style={styles.dash} />
          </View>
          <Text style={styles.legendText}>GAD-7 (불안)</Text>
        </View>
        <Text style={styles.axisHint}>점수 낮을수록 호전</Text>
      </View>

      {/* CTRS — 낮을수록 위험이라 별도 표기 */}
      {hasCtrs ? (
        <View style={styles.ctrsRow}>
          <Text style={styles.ctrsLabel}>CTRS 위험단계</Text>
          <View style={styles.ctrsCells}>
            {points.map((p, i) => (
              <View key={`c${i}`} style={styles.ctrsCell}>
                <View
                  style={[
                    styles.ctrsBadge,
                    p.ctrsLevel != null && p.ctrsLevel <= 2 ? styles.ctrsBadgeDanger : null,
                  ]}
                >
                  <Text
                    style={[
                      styles.ctrsNum,
                      p.ctrsLevel != null && p.ctrsLevel <= 2 ? styles.ctrsNumDanger : null,
                    ]}
                  >
                    {p.ctrsLevel ?? "–"}
                  </Text>
                </View>
              </View>
            ))}
          </View>
          <Text style={styles.ctrsHint}>숫자 낮을수록 위험</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    padding: 14,
    gap: 10,
  },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { fontSize: 13.5, fontWeight: "600", color: colors.ink },
  dirPill: {
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  dirText: { fontSize: 11, color: colors.muted, fontWeight: "500" },
  plot: { height: CHART_H, width: "100%" },
  emptyText: { fontSize: 12.5, color: colors.muted, lineHeight: 18 },
  legend: { flexDirection: "row", alignItems: "center", gap: 14, flexWrap: "wrap" },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendText: { fontSize: 11, color: colors.muted },
  solidLine: { width: 16, height: 2, borderRadius: 1, backgroundColor: colors.ink },
  dashRow: { flexDirection: "row", alignItems: "center", gap: 2, width: 16 },
  dash: { width: 4, height: 2, borderRadius: 1, backgroundColor: colors.muted },
  axisHint: { fontSize: 10.5, color: colors.faint, marginLeft: "auto" },
  ctrsRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.line,
    paddingTop: 10,
  },
  ctrsLabel: { fontSize: 11, color: colors.muted, fontWeight: "500" },
  ctrsCells: { flex: 1, flexDirection: "row", justifyContent: "space-around" },
  ctrsCell: { alignItems: "center" },
  ctrsBadge: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    alignItems: "center",
    justifyContent: "center",
  },
  ctrsBadgeDanger: { borderColor: colors.dangerLine, backgroundColor: colors.dangerSoft },
  ctrsNum: {
    fontSize: 11.5,
    fontWeight: "600",
    color: colors.ink,
    fontVariant: ["tabular-nums"],
  },
  ctrsNumDanger: { color: colors.dangerInk },
  ctrsHint: { fontSize: 10, color: colors.faint },
});
