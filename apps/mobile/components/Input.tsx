import { StyleSheet, Text, TextInput, TextInputProps, View } from "react-native";

import { colors, fontSize, radius, spacing } from "../lib/tokens";

export type InputProps = TextInputProps & {
  label?: string;
  error?: string | null;
};

export function Input({ label, error, style, ...rest }: InputProps) {
  return (
    <View style={styles.wrap}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={colors.textSecondary}
        accessibilityLabel={label}
        {...rest}
        style={[
          styles.input,
          { borderColor: error ? colors.stateDanger : colors.border },
          style,
        ]}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  label: {
    fontSize: fontSize.body,
    fontWeight: "500",
    color: colors.textPrimary,
  },
  input: {
    minHeight: 48,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    fontSize: fontSize.bodyLg,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  error: {
    fontSize: fontSize.caption,
    color: colors.stateDanger,
  },
});
