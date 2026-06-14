import { router } from "expo-router";
import { useState } from "react";
import { Alert } from "react-native";

import { QuestionnaireForm } from "../../../components/QuestionnaireForm";
import { APIException, submitQuestionnaire } from "../../../lib/api";
import { useAuth } from "../../../state/auth";
import { useSession } from "../../../state/session";

// 한국어판 PHQ-9 — 지난 2주간 우울 증상 빈도 (FR-006).
const PHQ9_ITEMS = [
  "매사에 흥미나 즐거움이 거의 없음",
  "기분이 가라앉거나, 우울하거나, 희망이 없다고 느낌",
  "잠들기 어렵거나 자주 깸, 또는 잠을 너무 많이 잠",
  "피곤하다고 느끼거나 기력이 저하됨",
  "식욕이 줄거나 너무 많이 먹음",
  "내 자신이 실패자라고 느끼거나 가족을 실망시켰다고 느낌",
  "신문이나 TV 보기 등 일에 집중하기 어려움",
  "다른 사람이 알아챌 정도로 말과 행동이 느려짐, 또는 너무 안절부절못함",
  "차라리 죽는 것이 낫겠다고 생각하거나 자해할 생각을 함",
];

export default function PHQ9Screen() {
  const accessToken = useAuth((s) => s.accessToken);
  const sessionId = useSession((s) => s.sessionId);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (answers: number[]) => {
    if (!accessToken || !sessionId) return;
    setSubmitting(true);
    try {
      await submitQuestionnaire(accessToken, sessionId, "PHQ9", answers);
      router.push("/(patient)/intake/gad7");
    } catch (e) {
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("저장 실패", `잠시 후 다시 시도해 주세요 (코드: ${code})`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <QuestionnaireForm
      title="우울 척도 (PHQ-9)"
      instruction="지난 2주 동안, 다음 문제들로 인해 얼마나 자주 불편을 느끼셨나요?"
      items={PHQ9_ITEMS}
      progressLabel="문진 1 / 2"
      submitLabel="다음 (불안 척도)"
      submitting={submitting}
      onSubmit={onSubmit}
    />
  );
}
