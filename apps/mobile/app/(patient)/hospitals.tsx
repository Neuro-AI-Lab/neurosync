/**
 * S-11 `/hospitals` — Demo stub (full search is Phase 2, FR-012).
 * Tab-bar screen. Surfaces the 119 fallback for emergencies.
 */

import { Linking, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BottomTabBar } from "../../components/BottomTabBar";
import { Button } from "../../components/Button";
import { colors, fontSize, radius, spacing } from "../../lib/tokens";

export default function HospitalsScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.title}>병원 찾기</Text>
      </View>

      <View style={styles.body}>
        <View style={styles.iconBox}>
          <Text style={styles.icon}>🏥</Text>
        </View>
        <Text style={styles.lead}>가까운 정신건강의학과를{"\n"}찾을 수 있어요.</Text>
        <Text style={styles.note}>이 기능은 정식 버전에서 제공됩니다.</Text>

        <View style={styles.emergencyBlock}>
          <Text style={styles.emergencyLabel}>응급 상황이라면</Text>
          <Button label="119 전화 걸기" variant="danger" onPress={() => Linking.openURL("tel:119")} />
        </View>
      </View>

      <BottomTabBar active="hospitals" />
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { fontSize: fontSize.title, fontWeight: "700", color: colors.textPrimary },
  body: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    gap: spacing.md,
  },
  iconBox: {
    width: 120,
    height: 120,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  icon: { fontSize: 52 },
  lead: {
    fontSize: fontSize.bodyLg,
    color: colors.textPrimary,
    textAlign: "center",
    lineHeight: 24,
    fontWeight: "600",
  },
  note: { fontSize: fontSize.body, color: colors.textSecondary, textAlign: "center" },
  emergencyBlock: {
    marginTop: spacing.xl,
    width: "100%",
    gap: spacing.sm,
    alignItems: "stretch",
  },
  emergencyLabel: { fontSize: fontSize.body, color: colors.textSecondary, textAlign: "center" },
});
