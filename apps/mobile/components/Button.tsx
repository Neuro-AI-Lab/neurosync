import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, fontSize, radius, spacing } from "../lib/tokens";

export type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  loading?: boolean;
};

export function Button({
  label,
  onPress,
  variant = "primary",
  disabled,
  loading,
}: ButtonProps) {
  const palette =
    variant === "danger"
      ? { bg: colors.stateDanger, fg: "#FFFFFF" }
      : variant === "secondary"
      ? { bg: colors.surfaceElevated, fg: colors.textPrimary }
      : { bg: colors.stateInfo, fg: "#FFFFFF" };

  const isDisabled = disabled || loading;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: isDisabled }}
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        { backgroundColor: palette.bg, opacity: isDisabled ? 0.5 : pressed ? 0.8 : 1 },
      ]}
    >
      <View style={styles.row}>
        {loading ? (
          <ActivityIndicator size="small" color={palette.fg} />
        ) : (
          <Text style={[styles.label, { color: palette.fg }]}>{label}</Text>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 48,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    justifyContent: "center",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  label: {
    fontSize: fontSize.bodyLg,
    fontWeight: "600",
  },
});
