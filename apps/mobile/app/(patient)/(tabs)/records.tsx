/**
 * v3 FR-045/046 — 지난 기록·리포트 (S-14 연속 스크롤 피드, mock 선구현).
 *
 * 월 헤더 + 날짜 칩 + 점수·상태 배지 피드. 실데이터(F4 추이 차트 포함)는
 * §6-A 프록시 배포 후 바인딩하고, 그 전까지는 로컬 기록 스토어(MOCK 시드 +
 * 이번 세션에서 완료한 문진)로 화면 계약을 검증한다.
 * 항목 탭 → 리포트 상세(/report/detail).
 */

import { router } from "expo-router";
import { SectionList, StyleSheet, Text, View } from "react-native";
import { Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ChevronRight } from "../../../lib/icons";
import { colors } from "../../../lib/tokens";
import { IntakeRecord, SEVERITY_KO, STATUS_KO, useRecords } from "../../../state/records";

const DOW = ["일", "월", "화", "수", "목", "금", "토"];

function groupByMonth(records: IntakeRecord[]) {
  const sorted = [...records].sort((a, b) => b.completedAt - a.completedAt);
  const sections: { title: string; data: IntakeRecord[] }[] = [];
  for (const rec of sorted) {
    const d = new Date(rec.completedAt);
    const title = `${d.getFullYear()}년 ${d.getMonth() + 1}월`;
    const last = sections[sections.length - 1];
    if (last && last.title === title) last.data.push(rec);
    else sections.push({ title, data: [rec] });
  }
  return sections;
}

function badgeStyle(rec: IntakeRecord) {
  if (rec.riskFlag) return { box: styles.stRisk, text: styles.stRiskText, label: "위험" };
  switch (rec.status) {
    case "reviewed":
      return { box: styles.stReviewed, text: styles.stReviewedText, label: STATUS_KO.reviewed };
    case "delivered":
      return { box: styles.stDelivered, text: styles.stDeliveredText, label: STATUS_KO.delivered };
    default:
      return { box: styles.stStored, text: styles.stStoredText, label: STATUS_KO.stored };
  }
}

export default function RecordsScreen() {
  const insets = useSafeAreaInsets();
  const records = useRecords((s) => s.records);
  const sections = groupByMonth(records);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Text style={[styles.largeTitle, { paddingTop: insets.top + 8 }]}>기록</Text>

      {records.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>아직 기록이 없어요</Text>
          <Text style={styles.emptySub}>첫 사전 문진을 완료하면 여기에 쌓여요.</Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.id}
          stickySectionHeadersEnabled={false}
          contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 24 }}
          renderSectionHeader={({ section }) => (
            <Text style={styles.mhead}>{section.title}</Text>
          )}
          renderItem={({ item }) => {
            const d = new Date(item.completedAt);
            const badge = badgeStyle(item);
            return (
              <Pressable
                style={({ pressed }) => [styles.entry, { opacity: pressed ? 0.7 : 1 }]}
                accessibilityRole="button"
                accessibilityLabel={`${d.getMonth() + 1}월 ${d.getDate()}일 ${item.instrument} 기록 열기`}
                onPress={() =>
                  router.push({
                    pathname: "/(patient)/report/detail",
                    params: { recordId: item.id },
                  })
                }
              >
                <View style={styles.day}>
                  <Text style={styles.dayNum}>{String(d.getDate()).padStart(2, "0")}</Text>
                  <Text style={styles.dayDow}>{DOW[d.getDay()]}</Text>
                </View>
                <View style={styles.mid}>
                  <Text style={styles.midTitle} numberOfLines={1}>
                    {item.instrument === "PHQ9" ? "PHQ-9" : item.instrument === "GAD7" ? "GAD-7" : item.instrument === "AUDITC" ? "AUDIT-C" : "PHQ-4"}{" "}
                    {item.totalScore}
                    <Text style={styles.midMax}> /{item.maxScore}</Text>
                  </Text>
                  <Text style={styles.midSub}>
                    사전 문진 · {SEVERITY_KO[item.severity] ?? item.severity}
                  </Text>
                </View>
                <View style={[styles.stat, badge.box]}>
                  <Text style={[styles.statText, badge.text]}>{badge.label}</Text>
                </View>
                <ChevronRight size={14} color={colors.faint} />
              </Pressable>
            );
          }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  largeTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: colors.ink,
    letterSpacing: -0.9,
    paddingHorizontal: 20,
    paddingBottom: 6,
  },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: 6, paddingBottom: 60 },
  emptyTitle: { fontSize: 16, fontWeight: "600", color: colors.ink },
  emptySub: { fontSize: 13, color: colors.muted },
  mhead: {
    fontSize: 12,
    fontWeight: "600",
    color: colors.muted,
    paddingTop: 15,
    paddingBottom: 7,
    letterSpacing: 0.1,
  },
  entry: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    paddingVertical: 13,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
  day: { width: 34, alignItems: "center" },
  dayNum: {
    fontSize: 19,
    fontWeight: "500",
    color: colors.ink,
    letterSpacing: -0.5,
    fontVariant: ["tabular-nums"],
    lineHeight: 22,
  },
  dayDow: { fontSize: 10, color: colors.faint, marginTop: 2 },
  mid: { flex: 1, minWidth: 0 },
  midTitle: { fontSize: 14, fontWeight: "600", color: colors.ink },
  midMax: { fontSize: 12, color: colors.faint, fontWeight: "400" },
  midSub: { fontSize: 11.5, color: colors.muted, marginTop: 3 },
  stat: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 },
  statText: { fontSize: 11, fontWeight: "600" },
  stStored: { backgroundColor: colors.fill },
  stStoredText: { color: colors.ink2 },
  stDelivered: { backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.lineStrong },
  stDeliveredText: { color: colors.ink },
  stReviewed: { backgroundColor: colors.ink },
  stReviewedText: { color: colors.onInk },
  stRisk: { backgroundColor: colors.dangerSoft, borderWidth: 1, borderColor: colors.dangerLine },
  stRiskText: { color: colors.dangerInk },
});
