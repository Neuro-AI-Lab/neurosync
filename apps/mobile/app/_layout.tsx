import { Stack, useRouter, useSegments } from "expo-router";
import { useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useAuth } from "../state/auth";

/**
 * 인증 가드 — 보호 영역((patient)) 안에서 세션이 만료·로그아웃돼 상태가
 * "anonymous"가 되면 로그인 화면으로 보낸다. index.tsx는 앱 진입 시에만
 * 라우팅하므로, 스택 깊숙이 있을 때 로그아웃되면 이 가드가 화면을 옮긴다.
 */
function useAuthGuard() {
  const status = useAuth((s) => s.status);
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous" && segments[0] === "(patient)") {
      router.replace("/(auth)/login");
    }
  }, [status, segments, router]);
}

export default function RootLayout() {
  const hydrate = useAuth((s) => s.hydrate);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  useAuthGuard();

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
