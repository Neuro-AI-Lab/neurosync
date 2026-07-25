/**
 * v3 FR-045/046 — 지난 기록·리포트 (S-14 연속 스크롤 피드).
 *
 * MOCK=1: 기존 로컬 기록 스토어(`state/records.ts` — 문진 점수·중증도까지
 * 포함한 풍부한 목업 피드)를 그대로 유지한다. 상세 화면(`/report/detail`)도
 * 이 스토어 하나만 바라보므로 함께 유지된다.
 *
 * MOCK=0: `GET /api/v1/sessions`(본인 세션 목록 — id/status/createdAt/
 * progress/리포트 유무) 실호출로 교체한다. 서버가 내려주는 필드가 세션
 * 요약뿐(문진 점수·중증도는 없음)이라 렌더링은 목업 피드보다 얇다 — 문진
 * 결과 상세(`/report/detail`)는 여전히 `state/records.ts` 스토어만 바라보는
 * mock 전용 화면이라(§6-B 배포 전) 실모드 행은 상세로 연결하지 않는다.
 */

import { router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { listSessions, SessionListItem } from "../../../lib/api";
import { MOCK } from "../../../lib/config";
import { ChevronRight } from "../../../lib/icons";
import { SURVEYS } from "../../../lib/surveys";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { IntakeRecord, SEVERITY_KO, STATUS_KO, useRecords } from "../../../state/records";

const DOW = ["일", "월", "화", "수", "목", "금", "토"];

const SESSION_STATUS_KO: Record<string, string> = {
  in_progress: "진행중",
  submitted: "제출됨",
  report_ready: "리포트 준비완료",
  closed: "종료",
};

function groupByMonth<T extends { completedAt: number }>(records: T[]) {
  const sorted = [...records].sort((a, b) => b.completedAt - a.completedAt);
  const sections: { title: string; data: T[] }[] = [];
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

  return MOCK ? <MockRecordsScreen insets={insets} /> : <LiveRecordsScreen insets={insets} />;
}

// ────────── MOCK mode (unchanged) ──────────

function MockRecordsScreen({ insets }: { insets: { top: number } }) {
  const records = useRecords((s) => s.records);
  const sections = useMemo(() => groupByMonth(records), [records]);

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
          renderItem={({ item }) => <MockRow item={item} />}
        />
      )}
    </View>
  );
}

function MockRow({ item }: { item: IntakeRecord }) {
  const d = new Date(item.completedAt);
  const badge = badgeStyle(item);
  return (
    <Pressable
      style={({ pressed }: { pressed: boolean }) => [styles.entry, { opacity: pressed ? 0.7 : 1 }]}
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
          {SURVEYS[item.instrument].toolLabel} {item.totalScore}
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
}

// ────────── LIVE mode — GET /api/v1/sessions ──────────

function LiveRecordsScreen({ insets }: { insets: { top: number } }) {
  const accessToken = useAuth((s) => s.accessToken);
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!accessToken) return;
      if (!opts?.silent) setLoading(true);
      setError(null);
      try {
        const data = await listSessions(accessToken);
        setSessions(data);
      } catch {
        setError("기록을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [accessToken],
  );

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    load({ silent: true });
  }, [load]);

  const withEpoch = useMemo(
    () => sessions.map((s) => ({ ...s, completedAt: Date.parse(s.createdAt) || 0 })),
    [sessions],
  );
  const sections = useMemo(() => groupByMonth(withEpoch), [withEpoch]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Text style={[styles.largeTitle, { paddingTop: insets.top + 8 }]}>기록</Text>

      {loading ? (
        <View style={styles.empty}>
          <ActivityIndicator color={colors.muted} />
        </View>
      ) : error ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>불러오지 못했어요</Text>
          <Text style={styles.emptySub}>{error}</Text>
        </View>
      ) : sessions.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>아직 기록이 없어요</Text>
          <Text style={styles.emptySub}>첫 사전 문진을 완료하면 여기에 쌓여요.</Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.sessionId}
          stickySectionHeadersEnabled={false}
          contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 24 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          renderSectionHeader={({ section }) => (
            <Text style={styles.mhead}>{section.title}</Text>
          )}
          renderItem={({ item }) => <LiveRow item={item} />}
        />
      )}
    </View>
  );
}

function LiveRow({ item }: { item: SessionListItem & { completedAt: number } }) {
  const d = new Date(item.completedAt);
  const percent = Math.round(item.progressRatio * 100);
  return (
    <View style={styles.entry}>
      <View style={styles.day}>
        <Text style={styles.dayNum}>{String(d.getDate()).padStart(2, "0")}</Text>
        <Text style={styles.dayDow}>{DOW[d.getDay()]}</Text>
      </View>
      <View style={styles.mid}>
        <Text style={styles.midTitle} numberOfLines={1}>
          {SESSION_STATUS_KO[item.status] ?? item.status}
        </Text>
        <Text style={styles.midSub}>진행률 {percent}%</Text>
      </View>
      <View style={[styles.stat, item.hasReport ? styles.stReviewed : styles.stStored]}>
        <Text style={[styles.statText, item.hasReport ? styles.stReviewedText : styles.stStoredText]}>
          {item.hasReport ? "리포트 있음" : "리포트 없음"}
        </Text>
      </View>
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
  emptySub: { fontSize: 13, color: colors.muted, textAlign: "center", paddingHorizontal: 32 },
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
