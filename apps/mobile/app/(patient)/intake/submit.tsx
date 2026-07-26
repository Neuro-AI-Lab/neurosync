import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button } from "../../../components/Button";
import { NavBar } from "../../../components/NavBar";
import { APIException, QuestionnaireResult, QuestionnaireType, submitSession } from "../../../lib/api";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { useRecords } from "../../../state/records";
import { useSession } from "../../../state/session";

// PRD §C 제출 전 안내 문구 (FR-010).
const NOTICE =
  "본 문진은 의료진의 진료를 돕기 위한 사전 정보 수집입니다. " +
  "AI는 진단이나 치료를 제공하지 않으며, 최종 판단은 의료진이 수행합니다.";

type Phase = "review" | "submitting";

export default function SubmitScreen() {
  const accessToken = useAuth((s) => s.accessToken);
  const sessionId = useSession((s) => s.sessionId);
  const addRecord = useRecords((s) => s.addFromResult);
  // survey에서 넘어온 문진 결과 — 기록에는 '제출하기'를 눌러 확정할 때만 추가한다
  // (보류하기는 기록을 남기지 않는다).
  const params = useLocalSearchParams<{ result?: string; instrument?: string }>();
  const [phase, setPhase] = useState<Phase>("review");

  // 보류 — 제출하지 않고 홈으로. 세션은 진행 중으로 남아 나중에 이어갈 수 있다.
  const onHold = () => {
    if (router.canDismiss()) router.dismissAll();
    else router.replace("/(patient)/(tabs)/home");
  };

  const onSubmit = async () => {
    if (!accessToken || !sessionId) return;
    setPhase("submitting");
    try {
      const accepted = await submitSession(accessToken, sessionId);
      // 제출 확정 시에만 기록에 남긴다 (보류하기는 미기록).
      if (params.result && params.instrument) {
        try {
          const result = JSON.parse(params.result) as QuestionnaireResult;
          // sessionId를 기록에 실어 리포트 상세에서 F4/F5(추이·요약)를 서버 조회
          // 할 수 있게 한다(세션 리셋 후에도). 여기 sessionId는 방금 submitSession에
          // 사용한 값과 동일 — 제출된 바로 그 세션이다.
          addRecord(result, params.instrument as QuestionnaireType, sessionId);
        } catch {
          // 파싱 실패는 기록 누락일 뿐, 제출 흐름은 계속한다.
        }
      }
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
        {/* v3 FR-047 — 보관 모델: 제출 = 리포트 생성·보관. 전달은 기록 화면에서
            환자가 직접 선택한다 (자동 전달 아님). */}
        <Text style={styles.body}>
          제출하면 문진 내용은 더 이상 수정할 수 없어요. 리포트는 보관되며, 의료진
          전달은 기록 화면에서 직접 선택할 수 있어요.
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
        <Button label="보류하기" variant="ghost" onPress={onHold} />
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
