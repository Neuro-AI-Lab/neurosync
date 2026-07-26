/**
 * AI 응답 대기 중 "입력 중…" 인디케이터 — AI 말풍선 안에서 점 3개가 순차로
 * 통통 튀는 애니메이션. 실제 응답(ai:complete)이 오기 전까지만 표시한다.
 */

import { useEffect, useRef } from "react";
import { Animated, StyleSheet, View } from "react-native";

import { colors } from "../lib/tokens";

function Dot({ delay }: { delay: number }) {
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(v, { toValue: 1, duration: 300, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: 300, useNativeDriver: true }),
        Animated.delay(600 - delay),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [v, delay]);
  const translateY = v.interpolate({ inputRange: [0, 1], outputRange: [0, -4] });
  const opacity = v.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] });
  return <Animated.View style={[styles.dot, { opacity, transform: [{ translateY }] }]} />;
}

export function TypingIndicator() {
  return (
    <View style={styles.rowLeft} accessibilityRole="text" accessibilityLabel="AI가 입력 중이에요">
      <View style={styles.bubble}>
        <Dot delay={0} />
        <Dot delay={150} />
        <Dot delay={300} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  rowLeft: { alignItems: "flex-start", marginVertical: 4 },
  bubble: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    backgroundColor: colors.fill,
    borderRadius: 18,
    borderBottomLeftRadius: 5,
    paddingHorizontal: 15,
    paddingVertical: 13,
  },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.muted },
});
