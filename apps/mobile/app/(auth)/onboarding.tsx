/**
 * S-01 `/onboarding` — 4-step value-first intro (guest, no auth).
 *
 * Shown only on first-ever launch (index.tsx routes here when
 * seenOnboarding === false). Skip or finishing the last step persists the flag
 * and replaces to /login. Monotone per screen-spec §0.8 — grayscale + the
 * danger accent reserved for the safety step.
 */

import { router } from "expo-router";
import { useRef, useState } from "react";
import {
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { colors, fontSize, radius, spacing } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

type Step = {
  glyph: string;
  headline: string;
  sub: string;
  bullets?: string[];
  danger?: boolean;
};

const STEPS: Step[] = [
  {
    glyph: "🗓️",
    headline: "초진 대기 6개월,\n변화가 기록되지 않습니다.",
    sub: "본 앱은 진료 전 사전 문진을 AI와 함께 준비하도록 돕습니다.",
  },
  {
    glyph: "⏱️",
    headline: "40분 진료, 20분은\n과거력 청취에 소진됩니다.",
    sub: "미리 정리해 두면 의사가 핵심을 빠르게 파악합니다.",
  },
  {
    glyph: "🆘",
    headline: "위기 순간에는\n즉시 연결됩니다.",
    sub: "언제든 도움을 받을 수 있어요.",
    bullets: ["자살예방 상담전화 1393", "응급의료 119", "정신건강 상담 1577-0199"],
    danger: true,
  },
  {
    glyph: "🩺",
    headline: "본 앱은 진단·치료를\n제공하지 않습니다.",
    sub: "AI는 환자의 정보를 구조화하고 요약합니다. 최종 판단은 의료진이 합니다.",
  },
];

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const completeOnboarding = useAuth((s) => s.completeOnboarding);
  const authStatus = useAuth((s) => s.status);
  const scrollRef = useRef<ScrollView>(null);
  const [index, setIndex] = useState(0);

  const isLast = index === STEPS.length - 1;

  const finish = async () => {
    await completeOnboarding();
    // Re-viewed from Settings while logged in → return to the app, not login.
    if (authStatus === "authenticated") {
      router.replace("/(patient)/home");
    } else {
      router.replace("/(auth)/login");
    }
  };

  const onNext = () => {
    if (isLast) {
      void finish();
      return;
    }
    scrollRef.current?.scrollTo({ x: (index + 1) * width, animated: true });
    setIndex(index + 1);
  };

  const onScrollEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const next = Math.round(e.nativeEvent.contentOffset.x / width);
    if (next !== index) setIndex(next);
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.topBar}>
        <Pressable
          onPress={() => void finish()}
          accessibilityRole="button"
          accessibilityLabel="건너뛰기"
          hitSlop={10}
        >
          <Text style={styles.skip}>건너뛰기</Text>
        </Pressable>
      </View>

      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={onScrollEnd}
        style={{ flex: 1 }}
      >
        {STEPS.map((step) => (
          <View key={step.headline} style={[styles.page, { width }]}>
            <View
              style={[
                styles.illustration,
                step.danger && { borderColor: colors.stateDanger, borderWidth: 1 },
              ]}
              accessibilityElementsHidden
            >
              <Text style={styles.glyph}>{step.glyph}</Text>
            </View>
            <Text style={styles.headline}>{step.headline}</Text>
            <Text style={styles.sub}>{step.sub}</Text>
            {step.bullets ? (
              <View style={styles.bullets}>
                {step.bullets.map((b) => (
                  <View key={b} style={styles.bulletRow}>
                    <View style={styles.bulletDot} />
                    <Text style={styles.bulletText}>{b}</Text>
                  </View>
                ))}
              </View>
            ) : null}
          </View>
        ))}
      </ScrollView>

      <View style={styles.dots} accessibilityRole="progressbar">
        {STEPS.map((_, i) => (
          <View
            key={i}
            style={[styles.dot, i === index ? styles.dotActive : styles.dotIdle]}
          />
        ))}
      </View>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Button label={isLast ? "시작하기" : "다음"} onPress={onNext} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  topBar: {
    height: 44,
    flexDirection: "row",
    justifyContent: "flex-end",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
  },
  skip: { fontSize: fontSize.body, color: colors.textSecondary, fontWeight: "500" },
  page: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    gap: spacing.lg,
  },
  illustration: {
    width: 180,
    height: 180,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.md,
  },
  glyph: { fontSize: 72 },
  headline: {
    fontSize: fontSize.display,
    fontWeight: "700",
    color: colors.textPrimary,
    textAlign: "center",
    lineHeight: 36,
    letterSpacing: -0.5,
  },
  sub: {
    fontSize: fontSize.bodyLg,
    color: colors.textSecondary,
    textAlign: "center",
    lineHeight: 24,
  },
  bullets: { gap: spacing.sm, marginTop: spacing.xs },
  bulletRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  bulletDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.stateDanger,
  },
  bulletText: { fontSize: fontSize.body, color: colors.textPrimary, fontWeight: "500" },
  dots: {
    flexDirection: "row",
    justifyContent: "center",
    gap: spacing.sm,
    paddingVertical: spacing.lg,
  },
  dot: { height: 8, borderRadius: 4 },
  dotActive: { width: 24, backgroundColor: colors.textPrimary },
  dotIdle: { width: 8, backgroundColor: colors.border },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
});
