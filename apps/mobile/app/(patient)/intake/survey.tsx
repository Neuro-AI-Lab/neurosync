/**
 * v3 FR-040 — 문항 주입형 단일 문진 화면.
 *
 * `/intake/chat`의 도메인 추정(FR-039)이 결정한 도구를 `instrument` 파라미터로
 * 받아 렌더한다. 고정 순차(phq9 → gad7)를 대체하며 진행 표기는 매핑된 설문지의
 * 실제 문항 인덱스 기준(예: "문항 3/9") — QuestionnaireForm이 내부에서 계산.
 * 제출 후 바로 최종 제출 확인(/intake/submit)으로 간다 — 사전 문진 단계의
 * 문서 업로드는 폐지(v3, OCR은 FR-048에서 대화 중 첨부로 이동).
 */

import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert } from "react-native";

import { QuestionnaireForm } from "../../../components/QuestionnaireForm";
import { APIException, QuestionnaireType, submitQuestionnaire } from "../../../lib/api";
import { FALLBACK_SURVEY } from "../../../lib/domain";
import { SURVEYS } from "../../../lib/surveys";
import { useAuth } from "../../../state/auth";
import { useRecords } from "../../../state/records";
import { useSession } from "../../../state/session";

export default function SurveyScreen() {
  const params = useLocalSearchParams<{ instrument?: string }>();
  const accessToken = useAuth((s) => s.accessToken);
  const sessionId = useSession((s) => s.sessionId);
  const addRecord = useRecords((s) => s.addFromResult);
  const [submitting, setSubmitting] = useState(false);

  // 알 수 없는/누락된 instrument는 폴백 문진으로 — 라우팅은 항상 성공 (FR-039).
  const instrument =
    params.instrument && params.instrument in SURVEYS
      ? (params.instrument as QuestionnaireType)
      : FALLBACK_SURVEY;
  const def = SURVEYS[instrument];

  const onSubmit = async (answers: number[]) => {
    if (!accessToken || !sessionId) return;
    setSubmitting(true);
    try {
      const result = await submitQuestionnaire(accessToken, sessionId, def.id, answers);
      // 기록·리포트 화면(FR-045/046)용 로컬 이력 — 세션 리셋과 무관하게 유지.
      // sessionId를 실어 리포트 상세에서 F4/F5(추이·요약)를 서버 조회한다.
      addRecord(result, def.id, sessionId);
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
      def={def}
      submitLabel="제출하기"
      submitting={submitting}
      onSubmit={onSubmit}
    />
  );
}
