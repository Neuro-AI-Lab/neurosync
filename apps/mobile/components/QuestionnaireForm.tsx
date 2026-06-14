import { useMemo, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, radius, spacing } from "../lib/tokens";
import { Button } from "./Button";

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

export function QuestionnaireForm({
  title,
  instruction,
  items,
  progressLabel,
  submitLabel,
  submitting,
  onSubmit,
}: Props) {
  const insets = useSafeAreaInsets();
  const [answers, setAnswers] = useState<(number | null)[]>(
    () => items.map(() => null),
  );

  const answeredCount = useMemo(
    () => answers.filter((a) => a !== null).length,
    [answers],
  );
  const allAnswered = answeredCount === items.length;

  const select = (itemIndex: number, value: number) => {
    setAnswers((prev) => {
      const next = [...prev];
      next[itemIndex] = value;
      return next;
    });
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={[
        styles.scroll,
        { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl },
      ]}
    >
      <Text style={styles.progress}>{progressLabel}</Text>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.instruction}>{instruction}</Text>

      {items.map((item, i) => (
        <View key={i} style={styles.itemCard}>
          <Text style={styles.itemText}>
            {i + 1}. {item}
          </Text>
          <View style={styles.options}>
            {LIKERT_OPTIONS.map((opt) => {
              const selected = answers[i] === opt.value;
              return (
                <Pressable
                  key={opt.value}
                  onPress={() => select(i, opt.value)}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  accessibilityLabel={`${i + 1}번 문항 ${opt.label}`}
                  style={[styles.option, selected && styles.optionSelected]}
                >
                  <Text
                    style={[
                      styles.optionLabel,
                      selected && styles.optionLabelSelected,
                    ]}
                  >
                    {opt.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ))}

      <Text style={styles.counter}>
        {answeredCount} / {items.length} 응답함
      </Text>
      <Button
        label={submitLabel}
        onPress={() => allAnswered && onSubmit(answers as number[])}
        loading={submitting}
        disabled={!allAnswered || submitting}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: spacing.lg, gap: spacing.md },
  progress: { fontSize: fontSize.caption, color: colors.textSecondary, fontWeight: "600" },
  title: { fontSize: fontSize.title, fontWeight: "700", color: colors.textPrimary },
  instruction: {
    fontSize: fontSize.body,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  itemCard: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.sm,
  },
  itemText: { fontSize: fontSize.bodyLg, color: colors.textPrimary, fontWeight: "500" },
  options: { flexDirection: "row", gap: spacing.xs },
  option: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    alignItems: "center",
    backgroundColor: colors.surface,
  },
  optionSelected: {
    borderColor: colors.stateInfo,
    backgroundColor: "#EFF6FF",
  },
  optionLabel: {
    fontSize: fontSize.caption,
    color: colors.textSecondary,
    textAlign: "center",
  },
  optionLabelSelected: { color: colors.stateInfo, fontWeight: "700" },
  counter: {
    fontSize: fontSize.caption,
    color: colors.textSecondary,
    textAlign: "center",
    marginTop: spacing.sm,
  },
});
