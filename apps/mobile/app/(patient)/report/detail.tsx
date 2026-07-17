/**
 * v3 FR-046/047 — 리포트 상세 (S-12 미니 프리뷰, mock 선구현).
 *
 * 기록 피드에서 항목 탭으로 진입. 표준 문진 점수(환자 본인 응답 기반 — 노출
 * 가능, v3 원칙 1 가드레일)와 Handoff 리포트 미니 프리뷰를 보여준다.
 * AI 추정 질환명·도메인은 어디에도 표시하지 않는다.
 *
 * [전달하기] (FR-047): 실백엔드는 §6-B(보관→전달) 배포 전이므로 실모드에서는
 * 버튼을 비노출한다(PRD §3.2 이중 전달 방지 가드). MOCK 모드에서만 로컬 상태
 * 전이(보관→전달됨)로 플로우를 시연한다.
 */

import { router, useLocalSearchParams } from "expo-router";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../../components/Button";
import { NavBar } from "../../../components/NavBar";
import { MOCK } from "../../../lib/config";
import { SURVEYS } from "../../../lib/surveys";
import { colors } from "../../../lib/tokens";
import { SEVERITY_KO, STATUS_KO, useRecords } from "../../../state/records";

export default function ReportDetailScreen() {
  const insets = useSafeAreaInsets();
  const { recordId } = useLocalSearchParams<{ recordId?: string }>();
  const record = useRecords((s) => s.records.find((r) => r.id === recordId));
  const markDelivered = useRecords((s) => s.markDelivered);

  if (!record) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface }}>
        <NavBar title="리포트" backLabel="뒤로" onBack={() => router.back()} />
        <View style={styles.empty}>
          <Text style={styles.emptyText}>기록을 찾을 수 없어요.</Text>
        </View>
      </View>
    );
  }

  const d = new Date(record.completedAt);
  const dateLabel = `${d.getFullYear()} · ${String(d.getMonth() + 1).padStart(2, "0")} · ${String(
    d.getDate(),
  ).padStart(2, "0")}`;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <NavBar title="리포트" backLabel="뒤로" onBack={() => router.back()} />

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
      >
        <View style={styles.top}>
          <View>
            <Text style={styles.title}>사전 문진 리포트</Text>
            <Text style={styles.date}>{dateLabel}</Text>
          </View>
          <View style={styles.pill}>
            <View style={styles.pillDot} />
            <Text style={styles.pillText}>{STATUS_KO[record.status]}</Text>
          </View>
        </View>

        {/* 점수 — 환자 본인 응답 기반이라 노출 가능 (원칙 1 가드레일) */}
        <View style={styles.scoreCard}>
          <Text style={styles.scoreNum}>
            {record.totalScore}
            <Text style={styles.scoreMax}> /{record.maxScore}</Text>
          </Text>
          <Text style={styles.scoreLabel}>
            {SURVEYS[record.instrument].toolLabel} ·{" "}
            {SEVERITY_KO[record.severity] ?? record.severity}
          </Text>
        </View>

        {/* Handoff 미니 프리뷰 — 예시 서사는 MOCK 전용. 실모드에서 실제 기록 위에
            가짜 임상 텍스트가 렌더되면 안 된다 (§6-A/B 배포 후 실데이터 바인딩). */}
        {MOCK ? (
          <View style={styles.report}>
            <View style={styles.reportHead}>
              <Text style={styles.reportHeadTitle}>Handoff 리포트</Text>
              <Text style={styles.reportHeadDate}>{dateLabel}</Text>
            </View>
            <View style={styles.rrow}>
              <Text style={styles.rk}>주호소</Text>
              <Text style={styles.rv}>한 달 넘게 지속되는 수면 곤란과 우울감</Text>
            </View>
            <View style={styles.rrow}>
              <Text style={styles.rk}>수면 · 식욕 · 활동</Text>
              <Text style={styles.rv}>입면까지 2~3시간, 식욕 저하, 활동량 감소</Text>
            </View>
            <View style={[styles.rrow, styles.rrowLast]}>
              <Text style={styles.rk}>위험 신호</Text>
              {record.riskFlag ? (
                <View style={styles.flag}>
                  <View style={styles.flagDot} />
                  <Text style={styles.flagText}>수동적 부정 사고 · 낮음</Text>
                </View>
              ) : (
                <Text style={styles.rv}>특이 소견 없음</Text>
              )}
            </View>
          </View>
        ) : (
          <View style={styles.report}>
            <View style={styles.reportHead}>
              <Text style={styles.reportHeadTitle}>Handoff 리포트</Text>
              <Text style={styles.reportHeadDate}>{dateLabel}</Text>
            </View>
            <View style={[styles.rrow, styles.rrowLast]}>
              <Text style={styles.rv}>리포트 본문은 정식 연동 후 여기에서 볼 수 있어요.</Text>
            </View>
          </View>
        )}

        <Text style={styles.fine}>
          본 리포트는 의료진 참고용이며, 진단이 아닙니다. 전달 전까지 의료진에게 공유되지 않아요.
        </Text>

        <View style={{ flex: 1 }} />

        {/* FR-047 — §6-B 배포 전 실모드 비노출 가드. MOCK에서만 전이 시연. */}
        {MOCK && record.status === "stored" ? (
          <Button label="의료진에게 전달하기" onPress={() => markDelivered(record.id)} />
        ) : null}
        {record.status === "delivered" ? (
          <Text style={styles.deliveredNote}>의료진에게 전달됐어요. 진료 때 함께 확인해요.</Text>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, paddingTop: 8, gap: 14, flexGrow: 1 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyText: { fontSize: 14, color: colors.muted },
  top: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  title: { fontSize: 22, fontWeight: "700", color: colors.ink, letterSpacing: -0.5 },
  date: { fontSize: 12, color: colors.muted, marginTop: 4, fontVariant: ["tabular-nums"] },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: 999,
    paddingHorizontal: 11,
    paddingVertical: 5,
  },
  pillDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.ink },
  pillText: { fontSize: 11.5, color: colors.muted },
  scoreCard: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    padding: 16,
  },
  scoreNum: {
    fontSize: 30,
    fontWeight: "500",
    color: colors.ink,
    letterSpacing: -0.9,
    fontVariant: ["tabular-nums"],
  },
  scoreMax: { fontSize: 13, color: colors.faint, fontWeight: "400" },
  scoreLabel: { fontSize: 11.5, color: colors.muted, marginTop: 4 },
  report: { borderWidth: 1, borderColor: colors.line, borderRadius: 16, overflow: "hidden" },
  reportHead: {
    paddingHorizontal: 15,
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
  },
  reportHeadTitle: { fontSize: 13.5, fontWeight: "600", color: colors.ink },
  reportHeadDate: { fontSize: 10.5, color: colors.faint, fontVariant: ["tabular-nums"] },
  rrow: {
    paddingHorizontal: 15,
    paddingVertical: 11,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
  },
  rrowLast: { borderBottomWidth: 0 },
  rk: {
    fontSize: 10.5,
    letterSpacing: 0.4,
    textTransform: "uppercase",
    color: colors.faint,
  },
  rv: { fontSize: 12.5, color: colors.ink, marginTop: 3, lineHeight: 18 },
  flag: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    marginTop: 4,
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: colors.dangerLine,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  flagDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.danger },
  flagText: { fontSize: 11.5, fontWeight: "600", color: colors.dangerInk },
  fine: { fontSize: 11.5, color: colors.muted, lineHeight: 16 },
  deliveredNote: { textAlign: "center", fontSize: 13, color: colors.muted, paddingVertical: 12 },
});
