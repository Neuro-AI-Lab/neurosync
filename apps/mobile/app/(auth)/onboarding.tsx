/**
 * S-01 `/onboarding` — 4-step value-first intro (guest, no auth).
 *
 * Shown only on first-ever launch (index.tsx routes here when
 * seenOnboarding === false). Skip or finishing the last step persists the flag
 * and replaces to /login. Monochrome — calm concentric mark, ink type; the
 * danger accent appears only on the safety step's hotline dots.
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
import { ArrowRight, ConcentricMark } from "../../lib/icons";
import { colors } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

type Step = {
  key: string;
  headline: string;
  sub: string;
  bullets?: string[];
  danger?: boolean;
};

const STEPS: Step[] = [
  {
    key: "wait",
    headline: "진료 전,\n마음을 차분히\n정리해요",
    sub: "대화하듯 증상을 남기면, 의료진이 5분 안에 읽는 리포트로 정리해 드려요.",
  },
  {
    key: "time",
    headline: "40분 진료,\n핵심에 더 오래\n머무를 수 있게",
    sub: "미리 정리해 두면 과거력 청취 시간이 줄고, 의사가 핵심을 빠르게 파악해요.",
  },
  {
    key: "safety",
    headline: "위기의 순간에는\n즉시 연결돼요",
    sub: "언제든 도움을 받을 수 있어요.",
    // v3 FR-044 — 109 기준 (구 1393·1577-0199 통합)
    bullets: ["자살예방 통합번호 109", "응급의료 119", "경찰 112"],
    danger: true,
  },
  {
    key: "scope",
    headline: "진단·치료는\n의료진의 몫이에요",
    sub: "AI는 환자의 정보를 구조화하고 요약할 뿐, 최종 판단은 의료진이 합니다.",
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
    if (authStatus === "authenticated") {
      router.replace("/(patient)/(tabs)/home");
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
          <View key={step.key} style={[styles.page, { width }]}>
            <View style={styles.mark} accessibilityElementsHidden>
              <ConcentricMark size={76} />
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
          <View key={i} style={[styles.dot, i === index ? styles.dotActive : styles.dotIdle]} />
        ))}
      </View>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        <Button
          label={isLast ? "시작하기" : "다음"}
          onPress={onNext}
          trailing={<ArrowRight size={16} color={colors.onInk} />}
        />
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
    paddingHorizontal: 20,
  },
  skip: { fontSize: 14.5, color: colors.muted, fontWeight: "500" },
  page: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 36,
  },
  mark: { marginBottom: 28 },
  headline: {
    fontSize: 27,
    fontWeight: "700",
    color: colors.ink,
    textAlign: "center",
    lineHeight: 33,
    letterSpacing: -0.8,
  },
  sub: {
    fontSize: 14,
    color: colors.muted,
    textAlign: "center",
    lineHeight: 21,
    marginTop: 14,
    maxWidth: 260,
  },
  bullets: { gap: 8, marginTop: 22, alignSelf: "stretch", paddingHorizontal: 20 },
  bulletRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  bulletDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.danger },
  bulletText: { fontSize: 14, color: colors.ink2, fontWeight: "500" },
  dots: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 20,
  },
  dot: { height: 4, borderRadius: 9 },
  dotActive: { width: 22, backgroundColor: colors.ink },
  dotIdle: { width: 4, backgroundColor: colors.lineStrong },
  footer: { paddingHorizontal: 20, paddingTop: 4 },
});
