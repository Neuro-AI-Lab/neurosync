import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { EmergencyEntryButton } from "../../../components/EmergencyEntryButton";
import { ArrowRight, Chat, ChevronRight, Doc } from "../../../lib/icons";
import { APIException, createSession } from "../../../lib/api";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { STATUS_KO, useRecords } from "../../../state/records";
import { useSession } from "../../../state/session";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "좋은 아침이에요";
  if (h < 18) return "안녕하세요";
  if (h < 22) return "오늘 하루 어떠셨어요?";
  return "늦은 시간까지 수고하셨어요";
}

function displayName(email: string): string {
  const idx = email.indexOf("@");
  return idx > 0 ? email.slice(0, idx) : email;
}

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const accessToken = useAuth((s) => s.accessToken);
  const user = useAuth((s) => s.user);
  const startSession = useSession((s) => s.start);
  const activeSessionId = useSession((s) => s.sessionId);
  // v3 FR-045 — 지난 기록·리포트 통합 카드 (mock: 로컬 기록 스토어 기반).
  const latestRecord = useRecords((s) => s.records[0]);
  const [starting, setStarting] = useState(false);

  const onStart = async () => {
    if (!accessToken) return;
    setStarting(true);
    try {
      const sess = await createSession(accessToken);
      startSession(sess.sessionId);
      router.push("/(patient)/intake/chat");
    } catch (e) {
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("세션 시작 실패", `잠시 후 다시 시도해 주세요 (코드: ${code})`);
    } finally {
      setStarting(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top + 12 }]}
      >
        <View style={styles.greet}>
          <Text style={styles.greetHi}>{greeting()}</Text>
          <Text style={styles.greetName}>
            {user ? `${displayName(user.email)}님` : "환자님"}
          </Text>
        </View>

        <Pressable
          style={({ pressed }) => [styles.startCard, { opacity: pressed ? 0.9 : 1 }]}
          onPress={onStart}
          disabled={starting}
          accessibilityRole="button"
          accessibilityLabel="새 사전 문진 시작"
        >
          <View style={styles.startTop}>
            <View style={styles.startIco}>
              <Chat size={20} color={colors.ink} />
            </View>
            <Text style={styles.startTime}>약 15분</Text>
          </View>
          <Text style={styles.startTitle}>
            {activeSessionId ? "사전 문진 새로 시작" : "새 사전 문진 시작"}
          </Text>
          <Text style={styles.startDesc}>대화하고, 표준 문진에 답하면 준비 끝이에요.</Text>
          <View style={styles.startCta}>
            {starting ? (
              <ActivityIndicator size="small" color={colors.onInk} />
            ) : (
              <>
                <Text style={styles.startCtaText}>시작하기</Text>
                <ArrowRight size={15} color={colors.onInk} />
              </>
            )}
          </View>
        </Pressable>

        {activeSessionId ? (
          <Pressable
            style={styles.lastRow}
            accessibilityRole="button"
            accessibilityLabel="진행 중인 문진 이어서 진행"
            onPress={() => router.push("/(patient)/intake/chat")}
          >
            <View style={styles.lastIco}>
              <Doc size={17} color={colors.muted} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.lastTitle}>진행 중인 사전 문진</Text>
              <Text style={styles.lastSub}>이어서 진행할 수 있어요</Text>
            </View>
            <ChevronRight size={15} color={colors.faint} />
          </Pressable>
        ) : null}

        {latestRecord ? (
          <Pressable
            style={styles.lastRow}
            accessibilityRole="button"
            accessibilityLabel="지난 기록·리포트 보기"
            onPress={() => router.push("/(patient)/(tabs)/records")}
          >
            <View style={styles.lastIco}>
              <Doc size={17} color={colors.muted} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.lastTitle}>지난 리포트</Text>
              <Text style={styles.lastSub}>
                {new Date(latestRecord.completedAt).getMonth() + 1}월{" "}
                {new Date(latestRecord.completedAt).getDate()}일 ·{" "}
                {latestRecord.status === "reviewed"
                  ? STATUS_KO.reviewed
                  : latestRecord.status === "delivered"
                    ? STATUS_KO.delivered
                    : STATUS_KO.stored}
              </Text>
            </View>
            <ChevronRight size={15} color={colors.faint} />
          </Pressable>
        ) : null}

        <View style={{ flex: 1 }} />

        <EmergencyEntryButton onPress={() => router.push("/(patient)/emergency")} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: 20,
    paddingBottom: 20,
    gap: 14,
    flexGrow: 1,
  },
  greet: { paddingTop: 6 },
  greetHi: { fontSize: 14, color: colors.muted },
  greetName: { fontSize: 25, fontWeight: "700", color: colors.ink, letterSpacing: -0.7, marginTop: 2 },
  startCard: {
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: 20,
    padding: 20,
    backgroundColor: colors.surface,
  },
  startTop: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  startIco: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: colors.fill,
    alignItems: "center",
    justifyContent: "center",
  },
  startTime: { fontSize: 12, color: colors.muted },
  startTitle: { fontSize: 19, fontWeight: "700", color: colors.ink, letterSpacing: -0.4, marginTop: 16 },
  startDesc: { fontSize: 12.5, color: colors.muted, marginTop: 5 },
  startCta: {
    marginTop: 16,
    height: 46,
    borderRadius: 13,
    backgroundColor: colors.ink,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
  },
  startCtaText: { color: colors.onInk, fontWeight: "600", fontSize: 14.5 },
  lastRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 15,
  },
  lastIco: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: colors.fill,
    alignItems: "center",
    justifyContent: "center",
  },
  lastTitle: { fontSize: 13.5, fontWeight: "600", color: colors.ink },
  lastSub: { fontSize: 11.5, color: colors.muted, marginTop: 2 },
});
