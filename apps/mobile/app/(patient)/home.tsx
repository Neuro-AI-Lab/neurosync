import { router } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { EmergencyEntryButton } from "../../components/EmergencyEntryButton";
import { APIException, createSession } from "../../lib/api";
import { colors, fontSize, radius, spacing } from "../../lib/tokens";
import { useAuth } from "../../state/auth";
import { useSession } from "../../state/session";

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
  const logout = useAuth((s) => s.logout);
  const startSession = useSession((s) => s.start);
  const [starting, setStarting] = useState(false);

  const onStart = async () => {
    if (!accessToken) return;
    setStarting(true);
    try {
      const sess = await createSession(accessToken);
      startSession(sess.sessionId);
      router.push("/(patient)/intake/chat");
    } catch (e) {
      // PRD §4.5.2 — never proxy server message to UI (potential PII).
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("세션 시작 실패", `잠시 후 다시 시도해 주세요 (코드: ${code})`);
    } finally {
      setStarting(false);
    }
  };

  return (
    <ScrollView
      contentContainerStyle={[
        styles.scroll,
        { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.lg },
      ]}
      style={{ backgroundColor: colors.surface }}
    >
      <View style={styles.header}>
        <Text style={styles.greeting}>{greeting()}{user ? `, ${displayName(user.email)}님` : ""}</Text>
        <Text style={styles.subtitle}>오늘은 어떠신가요?</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>새 사전 문진 시작</Text>
        <Text style={styles.cardSubtitle}>약 15~20분 소요</Text>
        <Button label="문진 시작" onPress={onStart} loading={starting} />
      </View>

      <View style={styles.spacer} />

      <Text style={styles.sectionLabel}>지금 도움이 필요해요</Text>
      <EmergencyEntryButton onPress={() => router.push("/(patient)/emergency")} />

      <View style={styles.spacer} />

      <Button label="로그아웃" variant="secondary" onPress={logout} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
  },
  header: { gap: spacing.xs },
  greeting: { fontSize: fontSize.title, fontWeight: "600", color: colors.textPrimary },
  subtitle: { fontSize: fontSize.bodyLg, color: colors.textSecondary },
  card: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardTitle: { fontSize: fontSize.bodyLg, fontWeight: "600", color: colors.textPrimary },
  cardSubtitle: { fontSize: fontSize.body, color: colors.textSecondary, marginBottom: spacing.sm },
  sectionLabel: {
    fontSize: fontSize.body,
    fontWeight: "500",
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  spacer: { height: spacing.lg },
});
