/**
 * S-08 `/intake/documents` — Demo stub (full upload + OCR is Phase 2,
 * FR-008/009/028). Sits in the intake flow between GAD-7 and submit; documents
 * are optional, so the only action is to continue.
 */

import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../../components/Button";
import { colors, fontSize, radius, spacing } from "../../../lib/tokens";

export default function DocumentsScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.back}>←</Text>
        </Pressable>
        <Text style={styles.headerTitle}>사전 문진</Text>
        <View style={{ width: 24 }} />
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: "85%" }]} />
      </View>

      <View style={styles.body}>
        <View style={styles.iconBox}>
          <Text style={styles.icon}>📄</Text>
        </View>
        <Text style={styles.lead}>타 병원 진단서·처방전을{"\n"}업로드할 수 있어요.</Text>
        <Text style={styles.note}>이 기능은 정식 버전에서 제공됩니다.</Text>
        <Text style={styles.note}>문서가 없어도 진행할 수 있어요.</Text>
      </View>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Button label="건너뛰고 다음으로" onPress={() => router.push("/(patient)/intake/submit")} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
  },
  back: { fontSize: fontSize.title, color: colors.textPrimary, fontWeight: "600" },
  headerTitle: { fontSize: fontSize.bodyLg, fontWeight: "600", color: colors.textPrimary },
  track: {
    height: 6,
    backgroundColor: colors.surfaceElevated,
    marginHorizontal: spacing.md,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  fill: { height: 6, borderRadius: radius.pill, backgroundColor: colors.stateInfo },
  body: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    gap: spacing.sm,
  },
  iconBox: {
    width: 120,
    height: 120,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceElevated,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.md,
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
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
});
