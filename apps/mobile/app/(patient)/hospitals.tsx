/**
 * S-11 `/hospitals` — Demo stub (full search is Phase 2, FR-012).
 * Tab-bar screen. Surfaces the 119 fallback for emergencies.
 */

import { Linking, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BottomTabBar } from "../../components/BottomTabBar";
import { Button } from "../../components/Button";
import { Hospital } from "../../lib/icons";
import { colors } from "../../lib/tokens";

export default function HospitalsScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Text style={[styles.largeTitle, { paddingTop: insets.top + 8 }]}>병원 찾기</Text>

      <View style={styles.body}>
        <View style={styles.iconBox}>
          <Hospital size={40} color={colors.muted} strokeWidth={1.5} />
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
  largeTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: colors.ink,
    letterSpacing: -0.9,
    paddingHorizontal: 20,
    paddingBottom: 6,
  },
  body: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    gap: 12,
  },
  iconBox: {
    width: 96,
    height: 96,
    borderRadius: 20,
    backgroundColor: colors.fill,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
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
  emergencyBlock: {
    marginTop: 32,
    width: "100%",
    gap: 10,
    alignItems: "stretch",
  },
  emergencyLabel: { fontSize: 13, color: colors.muted, textAlign: "center" },
});
