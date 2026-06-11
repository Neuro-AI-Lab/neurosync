import { Pressable, StyleSheet, Text } from "react-native";

import { colors, fontSize, radius, spacing } from "../lib/tokens";

export type EmergencyEntryButtonProps = {
  onPress: () => void;
  label?: string;
};

/**
 * Always-visible escape hatch to /emergency. PRD §A — 위험 신호는 보수적으로 탐지.
 * Even if the AI hasn't classified anything risky, the patient can reach
 * help with one tap.
 */
export function EmergencyEntryButton({
  onPress,
  label = "지금 도움이 필요해요",
}: EmergencyEntryButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [
        styles.btn,
        { opacity: pressed ? 0.8 : 1 },
      ]}
    >
      <Text style={styles.label}>⚠️  {label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    borderRadius: radius.md,
    backgroundColor: "#FEE2E2", // light red — danger affinity without alarming display
    borderWidth: 1,
    borderColor: colors.stateDanger,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
  },
  label: {
    fontSize: fontSize.bodyLg,
    fontWeight: "600",
    color: colors.stateDanger,
  },
});
