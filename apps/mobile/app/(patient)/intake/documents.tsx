/**
 * S-08 `/intake/documents` — Demo stub (full upload + OCR is Phase 2,
 * FR-008/009/028). Sits in the intake flow between GAD-7 and submit; documents
 * are optional, so the only action is to continue.
 */

import { router } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../../components/Button";
import { NavBar } from "../../../components/NavBar";
import { Doc } from "../../../lib/icons";
import { colors } from "../../../lib/tokens";

export default function DocumentsScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <NavBar title="사전 문진" backLabel="이전" onBack={() => router.back()} />
      <View style={styles.track}>
        <View style={[styles.fill, { width: "85%" }]} />
      </View>

      <View style={styles.body}>
        <View style={styles.iconBox}>
          <Doc size={40} color={colors.muted} strokeWidth={1.5} />
        </View>
        <Text style={styles.lead}>타 병원 진단서·처방전을{"\n"}업로드할 수 있어요.</Text>
        <Text style={styles.note}>이 기능은 정식 버전에서 제공됩니다.</Text>
        <Text style={styles.note}>문서가 없어도 진행할 수 있어요.</Text>
      </View>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        <Button label="건너뛰고 다음으로" onPress={() => router.push("/(patient)/intake/submit")} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: 4,
    backgroundColor: colors.fill,
    marginHorizontal: 16,
    borderRadius: 999,
    overflow: "hidden",
  },
  fill: { height: 4, borderRadius: 999, backgroundColor: colors.ink },
  body: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    gap: 8,
  },
  iconBox: {
    width: 96,
    height: 96,
    borderRadius: 20,
    backgroundColor: colors.fill,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  lead: {
    fontSize: 17,
    color: colors.ink,
    textAlign: "center",
    lineHeight: 24,
    fontWeight: "600",
    letterSpacing: -0.3,
  },
  note: { fontSize: 13, color: colors.muted, textAlign: "center" },
  footer: { paddingHorizontal: 20, paddingTop: 8 },
});
