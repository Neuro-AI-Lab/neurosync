import { router } from "expo-router";
import { useState } from "react";
import { Alert } from "react-native";

import { QuestionnaireForm } from "../../../components/QuestionnaireForm";
import { APIException, submitQuestionnaire } from "../../../lib/api";
import { useAuth } from "../../../state/auth";
import { useSession } from "../../../state/session";

// 한국어판 GAD-7 — 지난 2주간 불안 증상 빈도 (FR-007).
const GAD7_ITEMS = [
  "초조하거나 불안하거나 조마조마하게 느낌",
  "걱정하는 것을 멈추거나 조절할 수가 없음",
  "여러 가지 것들에 대해 걱정을 너무 많이 함",
  "편하게 있기가 어려움",
  "너무 안절부절못해서 가만히 있기가 힘듦",
  "쉽게 짜증이 나거나 화가 남",
  "마치 끔찍한 일이 생길 것처럼 두려움을 느낌",
];

export default function GAD7Screen() {
  const accessToken = useAuth((s) => s.accessToken);
  const sessionId = useSession((s) => s.sessionId);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (answers: number[]) => {
    if (!accessToken || !sessionId) return;
    setSubmitting(true);
    try {
      await submitQuestionnaire(accessToken, sessionId, "GAD7", answers);
      router.push("/(patient)/intake/submit");
    } catch (e) {
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("저장 실패", `잠시 후 다시 시도해 주세요 (코드: ${code})`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <QuestionnaireForm
      title="불안 척도 (GAD-7)"
      instruction="지난 2주 동안, 다음 문제들로 인해 얼마나 자주 불편을 느끼셨나요?"
      items={GAD7_ITEMS}
      progressLabel="문진 2 / 2"
      submitLabel="문진 마치기"
      submitting={submitting}
      onSubmit={onSubmit}
    />
  );
}
