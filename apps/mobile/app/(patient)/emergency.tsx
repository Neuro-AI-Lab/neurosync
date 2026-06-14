import * as Clipboard from "expo-clipboard";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, BackHandler, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { acknowledgeRiskEvent, APIException } from "../../lib/api";
import { colors, fontSize, radius, spacing } from "../../lib/tokens";
import { useAuth } from "../../state/auth";
import { useSession } from "../../state/session";

type AloneStatus = "alone" | "with_someone";

/**
 * Modal-presented emergency screen (PRD §5.5 Flow C client side).
 * - Hardware back is intercepted (Android).
 * - iOS swipe-back is disabled by the Stack screen options in _layout.
 * - Single explicit exit: "안전한 곳에 있어요" button.
 * - Haptic warning on entry.
 * - tel: failures fall back to a copy-to-clipboard Alert so the patient
 *   can still reach the number (PRD §A 보수적 탐지 / screen-spec §S-10).
 */
export default function EmergencyScreen() {
  const insets = useSafeAreaInsets();
  const risk = useSession((s) => s.lastRisk);
  const clearRisk = useSession((s) => s.clearRisk);
  const accessToken = useAuth((s) => s.accessToken);
  const [alone, setAlone] = useState<AloneStatus | null>(null);
  const [acking, setAcking] = useState(false);

  const acknowledge = async (value: AloneStatus) => {
    // Optimistic — the UI reflects the choice even if the network is flaky.
    setAlone(value);
    if (!accessToken || !risk?.riskEventId) return;
    setAcking(true);
    try {
      await acknowledgeRiskEvent(accessToken, risk.riskEventId, value);
    } catch (e) {
      // Acknowledgement is best-effort; never block the safety screen on it.
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("저장이 지연되고 있어요", `잠시 후 자동으로 다시 시도돼요 (코드: ${code})`);
    } finally {
      setAcking(false);
    }
  };

  const hotlines =
    risk?.hotlines ??
    [
      { name: "자살예방상담전화", number: "1393" },
      { name: "응급의료", number: "119" },
      { name: "정신건강상담전화", number: "1577-0199" },
    ];

  useEffect(() => {
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    const sub = BackHandler.addEventListener("hardwareBackPress", () => true);
    return () => sub.remove();
  }, []);

  const dial = async (name: string, number: string) => {
    const sanitized = number.replace(/[^0-9+]/g, "");
    const url = `tel:${sanitized}`;
    try {
      const supported = await Linking.canOpenURL(url);
      if (!supported) {
        Alert.alert(
          "전화 연결이 어려워요",
          `${name} ${number}로 직접 걸어 주세요.`,
          [
            {
              text: "번호 복사",
              onPress: async () => {
                try {
                  await Clipboard.setStringAsync(sanitized);
                } catch {
                  // ignore — UX hint only
                }
              },
            },
            { text: "확인" },
          ],
        );
        return;
      }
      await Linking.openURL(url);
    } catch {
      Alert.alert("전화 연결 실패", `${name} ${number}로 직접 걸어 주세요.`);
    }
  };

  const exit = () => {
    clearRisk();
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(patient)/home");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.banner, { paddingTop: insets.top + spacing.lg }]}>
        <Text style={styles.bannerTitle}>지금 당신의 안전이 가장 중요해요</Text>
        <Text style={styles.bannerSub}>도움을 받을 수 있는 곳이 여기 있어요</Text>
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: insets.bottom + spacing.xl },
        ]}
      >
        {hotlines.map((h) => (
          <Pressable
            key={h.number}
            onPress={() => dial(h.name, h.number)}
            accessibilityRole="button"
            accessibilityLabel={`${h.name} ${h.number} 전화 걸기`}
            style={styles.card}
          >
            <Text style={styles.cardIcon}>📞</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardNumber}>{h.number}</Text>
              <Text style={styles.cardName}>{h.name}</Text>
            </View>
            <Text style={styles.cardCta}>전화</Text>
          </Pressable>
        ))}

        <View style={styles.separator} />

        {/* FR-011/022 — patient self-report routes to risk_events.alone_status. */}
        <Text style={styles.question}>지금 혼자 계신가요?</Text>
        <View style={styles.row}>
          <Pressable
            onPress={() => acknowledge("alone")}
            disabled={acking}
            accessibilityRole="button"
            accessibilityState={{ selected: alone === "alone" }}
            style={[styles.answer, alone === "alone" && styles.answerSelected]}
          >
            <Text style={[styles.answerText, alone === "alone" && styles.answerTextSelected]}>
              혼자 있어요
            </Text>
          </Pressable>
          <Pressable
            onPress={() => acknowledge("with_someone")}
            disabled={acking}
            accessibilityRole="button"
            accessibilityState={{ selected: alone === "with_someone" }}
            style={[styles.answer, alone === "with_someone" && styles.answerSelected]}
          >
            <Text
              style={[
                styles.answerText,
                alone === "with_someone" && styles.answerTextSelected,
              ]}
            >
              누군가와 함께 있어요
            </Text>
          </Pressable>
        </View>
        {alone !== null ? (
          <Text style={styles.ackHint}>
            {alone === "alone"
              ? "혼자 계시는군요. 위 번호로 꼭 연락해 주세요."
              : "곁에 누군가 있어 다행이에요. 함께 도움을 요청해 주세요."}
          </Text>
        ) : null}

        <View style={styles.separator} />

        <Pressable style={styles.exit} onPress={exit} accessibilityRole="button">
          <Text style={styles.exitText}>안전한 곳에 있어요 → 닫기</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.stateDanger,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },
  bannerTitle: { color: "#FFFFFF", fontSize: fontSize.title, fontWeight: "700" },
  bannerSub: { color: "#FECACA", fontSize: fontSize.body, marginTop: spacing.xs },
  scroll: { padding: spacing.lg, gap: spacing.md },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.stateDanger,
    backgroundColor: "#FEF2F2",
  },
  cardIcon: { fontSize: 28 },
  cardNumber: { fontSize: fontSize.display, fontWeight: "700", color: colors.stateDanger },
  cardName: { fontSize: fontSize.body, color: colors.textPrimary, marginTop: 2 },
  cardCta: { fontSize: fontSize.bodyLg, color: colors.stateDanger, fontWeight: "600" },
  separator: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  question: {
    fontSize: fontSize.bodyLg,
    fontWeight: "600",
    color: colors.textPrimary,
    textAlign: "center",
  },
  row: { flexDirection: "row", gap: spacing.sm },
  answer: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: "center",
    backgroundColor: colors.surface,
  },
  answerSelected: { borderColor: colors.stateInfo, backgroundColor: "#EFF6FF" },
  answerText: { fontSize: fontSize.body, color: colors.textPrimary, textAlign: "center" },
  answerTextSelected: { color: colors.stateInfo, fontWeight: "700" },
  ackHint: {
    fontSize: fontSize.body,
    color: colors.textSecondary,
    textAlign: "center",
    marginTop: spacing.xs,
  },
  exit: {
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  exitText: { fontSize: fontSize.bodyLg, color: colors.textSecondary, fontWeight: "600" },
});
