import { Redirect, Stack } from "expo-router";

import { useAuth } from "../../state/auth";

export default function PatientLayout() {
  const status = useAuth((s) => s.status);
  if (status === "hydrating") return null;
  if (status === "anonymous") return <Redirect href="/(auth)/login" />;
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        animation: "default",
      }}
    >
      <Stack.Screen
        name="emergency"
        options={{
          presentation: "modal",
          gestureEnabled: false,
          animation: "slide_from_bottom",
        }}
      />
    </Stack>
  );
}
