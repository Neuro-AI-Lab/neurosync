import { Redirect } from "expo-router";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { colors } from "../lib/tokens";
import { useAuth } from "../state/auth";

export default function Index() {
  const status = useAuth((s) => s.status);
  const seenOnboarding = useAuth((s) => s.seenOnboarding);

  if (status === "hydrating") {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.stateInfo} />
      </View>
    );
  }
  if (status === "authenticated") {
    return <Redirect href="/(patient)/home" />;
  }
  // First-ever launch (anonymous + never seen intro) → onboarding.
  if (seenOnboarding === false) {
    return <Redirect href="/(auth)/onboarding" />;
  }
  return <Redirect href="/(auth)/login" />;
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
});
