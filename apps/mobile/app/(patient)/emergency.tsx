import * as Clipboard from "expo-clipboard";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, BackHandler, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { acknowledgeRiskEvent, APIException } from "../../lib/api";
import { Phone } from "../../lib/icons";
import { colors } from "../../lib/tokens";
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
 * Red is reserved for exactly this screen: the alert card, the phone tiles,
 * the numbers — everything else stays monochrome.
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
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("저장이 지연되고 있어요", `잠시 후 자동으로 다시 시도돼요 (코드: ${code})`);
    } finally {
      setAcking(false);
    }
  };

  // v3 FR-044 — 핫라인 109 기준 (구 1393·1577-0199는 2024-01부터 109로 통합).
  // 서버 payload가 109 기준으로 갱신될 때까지(미결 #5) 구번호를 정규화한다 —
  // 갱신 후에는 no-op. 위기 화면에 폐지 번호가 노출되는 일이 없도록 보장.
  const LEGACY_TO_109: Record<string, true> = { "1393": true, "1577-0199": true, "15770199": true };
  const CANONICAL_HOTLINES = [
    { name: "자살예방 통합번호", number: "109" },
    { name: "응급의료", number: "119" },
    { name: "경찰", number: "112" },
  ];
  const normalized = (risk?.hotlines ?? CANONICAL_HOTLINES).map((h) =>
    LEGACY_TO_109[h.number.replace(/[^0-9-]/g, "")]
      ? { name: "자살예방 통합번호", number: "109" }
      : h,
  );
  // 정규화로 생긴 중복(1393·1577-0199 → 109) 제거.
  const hotlines = normalized.filter(
    (h, i) => normalized.findIndex((x) => x.number === h.number) === i,
  );

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
        Alert.alert("전화 연결이 어려워요", `${name} ${number}로 직접 걸어 주세요.`, [
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
        ]);
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
      router.replace("/(patient)/(tabs)/home");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.alert, { marginTop: insets.top + 8 }]}>
        <View style={styles.eyebrowRow}>
          <View style={styles.pulse} />
          <Text style={styles.eyebrow}>지금, 안전 확인이 필요해요</Text>
        </View>
        <Text style={styles.alertTitle}>당신의 안전이 가장 중요해요</Text>
        <Text style={styles.alertSub}>혼자 감당하지 않으셔도 돼요. 아래로 바로 연결돼요.</Text>
      </View>

      <ScrollView contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 24 }]}>
        {hotlines.map((h) => (
          <Pressable
            key={h.number}
            onPress={() => dial(h.name, h.number)}
            accessibilityRole="button"
            accessibilityLabel={`${h.name} ${h.number} 전화 걸기`}
            style={styles.hot}
          >
            <View style={styles.hotIcon}>
              <Phone size={19} color="#FFFFFF" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.hotNumber}>{h.number}</Text>
              <Text style={styles.hotName}>{h.name}</Text>
            </View>
            <Text style={styles.hotCta}>전화</Text>
          </Pressable>
        ))}

        {/* FR-011/022 — patient self-report routes to risk_events.alone_status. */}
        <Text style={styles.qline}>지금 혼자 계신가요?</Text>
        <View style={styles.etwo}>
          {(["alone", "with_someone"] as const).map((v) => (
            <Pressable
              key={v}
              onPress={() => acknowledge(v)}
              disabled={acking}
              accessibilityRole="button"
              accessibilityState={{ selected: alone === v }}
              style={[styles.eBtn, alone === v && styles.eBtnSel]}
            >
              <Text style={[styles.eBtnText, alone === v && styles.eBtnTextSel]}>
                {v === "alone" ? "혼자 있어요" : "함께 있어요"}
              </Text>
            </Pressable>
          ))}
        </View>
        {alone !== null ? (
          <Text style={styles.ackHint}>
            {alone === "alone"
              ? "혼자 계시는군요. 위 번호로 꼭 연락해 주세요."
              : "곁에 누군가 있어 다행이에요. 함께 도움을 요청해 주세요."}
          </Text>
        ) : null}

        <View style={{ height: 8 }} />
        <Pressable onPress={exit} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.exit}>안전한 곳에 있어요 · 닫기</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  alert: {
    marginHorizontal: 20,
    borderWidth: 1,
    borderColor: colors.dangerLine,
    backgroundColor: colors.dangerSoft,
    borderRadius: 16,
    padding: 16,
  },
  eyebrowRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  pulse: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.danger },
  eyebrow: { color: colors.dangerInk, fontSize: 11, fontWeight: "700", letterSpacing: 0.3 },
  alertTitle: { marginTop: 10, fontSize: 20, fontWeight: "700", color: colors.ink, letterSpacing: -0.4, lineHeight: 26 },
  alertSub: { marginTop: 6, fontSize: 12.5, color: colors.ink2 },
  body: { padding: 20, gap: 10 },
  hot: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    paddingHorizontal: 15,
    paddingVertical: 14,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
  },
  hotIcon: {
    width: 44,
    height: 44,
    borderRadius: 13,
    backgroundColor: colors.danger,
    alignItems: "center",
    justifyContent: "center",
  },
  hotNumber: { fontSize: 21, fontWeight: "600", color: colors.dangerInk, fontVariant: ["tabular-nums"], lineHeight: 24 },
  hotName: { fontSize: 12, color: colors.muted, marginTop: 3 },
  hotCta: {
    fontSize: 13,
    fontWeight: "600",
    color: colors.dangerInk,
    borderWidth: 1,
    borderColor: colors.dangerLine,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 7,
    overflow: "hidden",
  },
  qline: { fontSize: 14, fontWeight: "600", color: colors.ink, textAlign: "center", marginTop: 8 },
  etwo: { flexDirection: "row", gap: 9 },
  eBtn: {
    flex: 1,
    height: 48,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  eBtnSel: { borderColor: colors.ink, borderWidth: 1.5 },
  eBtnText: { fontSize: 13.5, color: colors.ink },
  eBtnTextSel: { fontWeight: "600" },
  ackHint: { fontSize: 13, color: colors.muted, textAlign: "center", marginTop: 4 },
  exit: { textAlign: "center", color: colors.muted, fontSize: 13, fontWeight: "500", paddingVertical: 6 },
});
