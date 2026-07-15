import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius } from "../lib/tokens";

export type ButtonVariant = "primary" | "tinted" | "ghost" | "quiet" | "danger";

export type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  /** Optional trailing glyph node (e.g. an arrow icon). */
  trailing?: React.ReactNode;
};

export function Button({
  label,
  onPress,
  variant = "primary",
  disabled,
  loading,
  trailing,
}: ButtonProps) {
  const isDisabled = disabled || loading;
  const v = VARIANTS[variant];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: isDisabled }}
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        v.container,
        variant === "quiet" && styles.quiet,
        { opacity: isDisabled ? 0.4 : pressed ? 0.85 : 1 },
      ]}
    >
      <View style={styles.row}>
        {loading ? (
          <ActivityIndicator size="small" color={v.fg} />
        ) : (
          <>
            <Text style={[styles.label, { color: v.fg }, variant === "quiet" && styles.quietLabel]}>
              {label}
            </Text>
            {trailing}
          </>
        )}
      </View>
    </Pressable>
  );
}

const VARIANTS: Record<ButtonVariant, { container: object; fg: string }> = {
  primary: { container: { backgroundColor: colors.ink }, fg: colors.onInk },
  tinted: { container: { backgroundColor: colors.fill }, fg: colors.ink },
  ghost: {
    container: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.lineStrong },
    fg: colors.ink,
  },
  quiet: { container: { backgroundColor: "transparent" }, fg: colors.muted },
  danger: { container: { backgroundColor: colors.danger }, fg: "#FFFFFF" },
};

const styles = StyleSheet.create({
  base: {
    height: 52,
    paddingHorizontal: 20,
    borderRadius: radius.lg,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "transparent",
  },
  quiet: { height: 44 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  label: {
    fontSize: 15.5,
    fontWeight: "600",
    letterSpacing: -0.1,
  },
  quietLabel: { fontSize: 14.5, fontWeight: "500" },
});
