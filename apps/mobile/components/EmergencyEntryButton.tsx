import { Pressable, StyleSheet, Text, View } from "react-native";

import { Phone } from "../lib/icons";
import { colors } from "../lib/tokens";

export type EmergencyEntryButtonProps = {
  onPress: () => void;
  label?: string;
};

/**
 * Always-visible escape hatch to /emergency. PRD §A — 위험 신호는 보수적으로 탐지.
 * Even if the AI hasn't classified anything risky, the patient can reach
 * help with one tap. Soft-red fill (danger affinity, not an alarming display).
 */
export function EmergencyEntryButton({
  onPress,
  label = "지금 도움이 필요해요 · 24시간",
}: EmergencyEntryButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.btn, { opacity: pressed ? 0.8 : 1 }]}
    >
      <View style={styles.row}>
        <Phone size={16} color={colors.dangerInk} strokeWidth={1.9} />
        <Text style={styles.label}>{label}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    height: 46,
    borderRadius: 14,
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: colors.dangerLine,
    alignItems: "center",
    justifyContent: "center",
  },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  label: {
    fontSize: 13.5,
    fontWeight: "600",
    color: colors.dangerInk,
  },
});
