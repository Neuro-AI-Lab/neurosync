import { Stack } from "expo-router";
import { useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useAuth } from "../state/auth";

export default function RootLayout() {
  const hydrate = useAuth((s) => s.hydrate);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  // 로그아웃/만료 리다이렉트는 (patient)/_layout 의 선언형 Redirect가 담당한다
  // (anonymous → /(auth)/login). 여기 중복 가드를 두지 않는다.

  return (
    <SafeAreaProvider>
      <Stack
        screenOptions={{
          headerShown: false,
        }}
      />
      <StatusBar style="auto" />
    </SafeAreaProvider>
  );
}
