import * as Clipboard from "expo-clipboard";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useEffect } from "react";
import { Alert, BackHandler, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing } from "../../lib/tokens";
import { useSession } from "../../state/session";

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

        {/* Phase 1b: PATCH /risk_events/:id { aloneStatus, acknowledgedAt }.
            Disabled here so the patient is not misled by no-op buttons. */}
        <Text style={styles.questionMuted}>지금 혼자 계신가요?</Text>
        <View style={styles.row}>
          <View style={[styles.answer, styles.answerDisabled]}>
            <Text style={styles.answerTextMuted}>곧 지원돼요</Text>
          </View>
        </View>

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
  questionMuted: {
    fontSize: fontSize.bodyLg,
    fontWeight: "600",
    color: colors.textSecondary,
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
  },
  answerDisabled: { backgroundColor: colors.surfaceElevated },
  answerTextMuted: { fontSize: fontSize.body, color: colors.textSecondary },
  exit: {
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  exitText: { fontSize: fontSize.bodyLg, color: colors.textSecondary, fontWeight: "600" },
});
