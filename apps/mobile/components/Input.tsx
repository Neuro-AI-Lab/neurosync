import { useState } from "react";
import { StyleSheet, Text, TextInput, TextInputProps, View } from "react-native";

import { colors } from "../lib/tokens";

export type InputProps = TextInputProps & {
  label?: string;
  error?: string | null;
};

export function Input({ label, error, style, onFocus, onBlur, ...rest }: InputProps) {
  const [focused, setFocused] = useState(false);
  const borderColor = error ? colors.danger : focused ? colors.ink : colors.lineStrong;

  return (
    <View style={styles.wrap}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={colors.faint}
        accessibilityLabel={label}
        {...rest}
        onFocus={(e) => {
          setFocused(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          onBlur?.(e);
        }}
        style={[styles.input, { borderColor }, style]}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  label: {
    fontSize: 12.5,
    fontWeight: "500",
    color: colors.muted,
    paddingLeft: 2,
  },
  input: {
    height: 50,
    borderRadius: 13,
    borderWidth: 1,
    paddingHorizontal: 15,
    fontSize: 15,
    color: colors.ink,
    backgroundColor: colors.surface,
  },
  error: {
    fontSize: 12,
    color: colors.danger,
    paddingLeft: 2,
  },
});
