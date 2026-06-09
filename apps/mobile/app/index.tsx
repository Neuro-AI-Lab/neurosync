import { CONTRACTS_VERSION } from "@neuro-sync/contracts";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

export default function Index() {
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        styles.container,
        { paddingTop: insets.top, paddingBottom: insets.bottom },
      ]}
    >
      <Text style={styles.title}>Neuro-Sync</Text>
      <Text style={styles.subtitle}>환자 사전 문진</Text>
      <Text style={styles.caption}>
        Phase 1a Day 1~2 bootstrap · contracts {CONTRACTS_VERSION}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 24,
    gap: 8,
  },
  title: {
    fontSize: 28,
    fontWeight: "600",
    color: "#0F172A",
  },
  subtitle: {
    fontSize: 16,
    color: "#64748B",
  },
  caption: {
    fontSize: 12,
    color: "#64748B",
    marginTop: 16,
  },
});
