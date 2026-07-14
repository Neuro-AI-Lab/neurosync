import { router } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button } from "../../../components/Button";
import { NavBar } from "../../../components/NavBar";
import { APIException, submitSession } from "../../../lib/api";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { useSession } from "../../../state/session";

// PRD §C 제출 전 안내 문구 (FR-010).
const NOTICE =
  "본 문진은 의료진의 진료를 돕기 위한 사전 정보 수집입니다. " +
  "AI는 진단이나 치료를 제공하지 않으며, 최종 판단은 의료진이 수행합니다.";

type Phase = "review" | "submitting";

export default function SubmitScreen() {
  const accessToken = useAuth((s) => s.accessToken);
  const sessionId = useSession((s) => s.sessionId);
  const [phase, setPhase] = useState<Phase>("review");

  const onSubmit = async () => {
    if (!accessToken || !sessionId) return;
    setPhase("submitting");
    try {
      const accepted = await submitSession(accessToken, sessionId);
      // FR-018 — generation runs out-of-band; hand off to the status screen
      // which polls. Replace so back doesn't return to the submit confirm.
      router.replace({
        pathname: "/(patient)/report/status",
        params: {
          sessionId: accepted.sessionId,
          estimatedSeconds: String(accepted.estimatedSeconds),
        },
      });
    } catch (e) {
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("제출 실패", `잠시 후 다시 시도해 주세요 (코드: ${code})`);
      setPhase("review");
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <NavBar title="제출 확인" backLabel="이전" onBack={() => router.back()} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>문진을 제출할까요?</Text>
        <Text style={styles.body}>
          제출하면 입력하신 내용은 의료진에게 전달되며, 이후에는 수정할 수 없어요.
        </Text>
        <View style={styles.noticeCard}>
          <Text style={styles.noticeText}>{NOTICE}</Text>
        </View>
        <View style={{ height: 8 }} />
        <Button
          label="제출하기"
          onPress={onSubmit}
          loading={phase === "submitting"}
          disabled={phase === "submitting"}
        />
        <Button label="더 작성하기" variant="ghost" onPress={() => router.back()} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 32, gap: 14 },
  title: { fontSize: 24, fontWeight: "700", color: colors.ink, letterSpacing: -0.6 },
  body: { fontSize: 14, color: colors.muted, lineHeight: 21 },
  noticeCard: {
    backgroundColor: colors.fill,
    borderRadius: 14,
    padding: 16,
  },
  noticeText: { fontSize: 13, color: colors.ink2, lineHeight: 20 },
});
