import { router } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { NavBar } from "./NavBar";
import { Button } from "./Button";
import { colors } from "../lib/tokens";

/** 0-3 Likert scale shared by PHQ-9 / GAD-7 (DSM standard). */
export const LIKERT_OPTIONS = [
  { value: 0, label: "전혀 아니다" },
  { value: 1, label: "며칠 동안" },
  { value: 2, label: "일주일 이상" },
  { value: 3, label: "거의 매일" },
] as const;

type Props = {
  title: string;
  instruction: string;
  items: string[];
  progressLabel: string;
  submitLabel: string;
  submitting: boolean;
  onSubmit: (answers: number[]) => void;
};

/**
 * One-question-at-a-time standard-scale form (screen-spec §S-06). Focused single
 * item, big radio options, auto-saved locally as you go; advances via 다음 문항 and
 * submits the full array on the last item.
 */
export function QuestionnaireForm({
  title,
  instruction,
  items,
  progressLabel,
  submitLabel,
  submitting,
  onSubmit,
}: Props) {
  const [answers, setAnswers] = useState<(number | null)[]>(() => items.map(() => null));
  const [index, setIndex] = useState(0);

  const answeredCount = useMemo(() => answers.filter((a) => a !== null).length, [answers]);
  const allAnswered = answeredCount === items.length;
  const isLast = index === items.length - 1;
  const current = answers[index];

  const select = (value: number) => {
    setAnswers((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
  };

  const goPrev = () => {
    if (index > 0) setIndex(index - 1);
    else router.back();
  };

  const onPrimary = () => {
    if (isLast) {
      if (allAnswered) onSubmit(answers as number[]);
      return;
    }
    if (current !== null) setIndex(index + 1);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <NavBar title={title} backLabel={index > 0 ? "이전" : "그만"} onBack={goPrev} />

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.qtop}>
          <Text style={styles.eyebrow}>{progressLabel}</Text>
          <Text style={styles.score}>
            {index + 1} / {items.length}
          </Text>
        </View>
        <View style={styles.qtrack}>
          <View style={[styles.qfill, { width: `${((index + 1) / items.length) * 100}%` }]} />
        </View>

        <Text style={styles.qq}>{instruction}</Text>
        <Text style={styles.qt}>{items[index]}</Text>

        <View style={styles.likert}>
          {LIKERT_OPTIONS.map((opt) => {
            const selected = current === opt.value;
            return (
              <Pressable
                key={opt.value}
                onPress={() => select(opt.value)}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                accessibilityLabel={`${index + 1}번 문항 ${opt.label}`}
                style={[styles.opt, selected && styles.optSel]}
              >
                <View style={[styles.rad, selected && styles.radSel]} />
                <Text style={[styles.optLabel, selected && styles.optLabelSel]}>{opt.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <Button
          label={isLast ? submitLabel : "다음 문항"}
          onPress={onPrimary}
          loading={submitting}
          disabled={current === null || (isLast && !allAnswered)}
        />
        <Text style={styles.qcount}>답을 고르면 자동으로 저장돼요</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, paddingTop: 4, paddingBottom: 24, gap: 4 },
  qtop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  eyebrow: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  score: { fontSize: 13, color: colors.ink, fontWeight: "500", fontVariant: ["tabular-nums"] },
  qtrack: {
    height: 4,
    borderRadius: 999,
    backgroundColor: colors.fill,
    overflow: "hidden",
    marginTop: 8,
    marginBottom: 2,
  },
  qfill: { height: 4, borderRadius: 999, backgroundColor: colors.ink },
  qq: { fontSize: 12.5, color: colors.muted, marginTop: 12 },
  qt: {
    fontSize: 19,
    fontWeight: "600",
    color: colors.ink,
    letterSpacing: -0.4,
    lineHeight: 26,
    marginTop: 6,
    marginBottom: 12,
  },
  likert: { gap: 9 },
  opt: {
    flexDirection: "row",
    alignItems: "center",
    gap: 13,
    minHeight: 54,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  optSel: { borderColor: colors.ink, borderWidth: 1.5 },
  rad: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: colors.lineStrong,
  },
  radSel: {
    borderColor: colors.ink,
    backgroundColor: colors.ink,
    borderWidth: 6,
  },
  optLabel: { fontSize: 14.5, color: colors.ink },
  optLabelSel: { fontWeight: "600" },
  footer: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 20,
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
  },
  qcount: { textAlign: "center", fontSize: 11, color: colors.faint },
});
