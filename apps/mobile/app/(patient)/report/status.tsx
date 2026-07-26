/**
 * S-12 `/report/status` — patient-facing Handoff report status (FR-013/018).
 *
 * Reached via `router.replace` from `/intake/submit` after a 202 Accepted.
 * The report BODY is never shown to the patient (clinician-only); this screen
 * only surfaces generating / ready / failed + a progress estimate.
 *
 * Polling: every 3s, capped at 60s. Past the cap we show an "overdue" note and
 * let the patient go home (generation continues server-side).
 */

import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../../components/Button";
import { Check } from "../../../lib/icons";
import { APIException, getReportStatus, ReportPhase } from "../../../lib/api";
import { SURVEYS } from "../../../lib/surveys";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { SEVERITY_KO, useRecords } from "../../../state/records";
import { useSession } from "../../../state/session";

const POLL_INTERVAL_MS = 3000;
const POLL_CAP_MS = 60_000;

const REPORT_CONTENTS = [
  "주호소 및 현병력",
  "자가 설문 결과",
  "상태 변화 추이",
  "의료진 확인 필요 사항",
  "원문 근거 인용",
];

type UIState = ReportPhase | "overdue";

export default function ReportStatusScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{
    sessionId?: string;
    estimatedSeconds?: string;
  }>();
  const accessToken = useAuth((s) => s.accessToken);
  const storeSessionId = useSession((s) => s.sessionId);
  const resetSession = useSession((s) => s.reset);
  // 방금 완료한 문진 — 완료 화면에 점수 카드로 표시 (v3 FR-046 가드레일:
  // 표준 문진 점수는 환자 본인 응답 기반이라 노출 가능).
  const latestRecord = useRecords((s) => s.records[0]);

  const sessionId = params.sessionId ?? storeSessionId ?? null;
  const estimatedSeconds = Number(params.estimatedSeconds) || 30;

  const [uiState, setUiState] = useState<UIState>("generating");
  const [elapsedSec, setElapsedSec] = useState(0);
  const startedAt = useRef(Date.now());
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const tickTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTimers = useCallback(() => {
    if (pollTimer.current !== null) clearInterval(pollTimer.current);
    if (tickTimer.current !== null) clearInterval(tickTimer.current);
    pollTimer.current = null;
    tickTimer.current = null;
  }, []);

  const poll = useCallback(async () => {
    if (!accessToken || !sessionId) return;
    if (Date.now() - startedAt.current > POLL_CAP_MS) {
      stopTimers();
      setUiState((s) => (s === "ready" || s === "failed" ? s : "overdue"));
      return;
    }
    try {
      const res = await getReportStatus(accessToken, sessionId);
      if (res.status === "ready") {
        stopTimers();
        setUiState("ready");
      } else if (res.status === "failed") {
        stopTimers();
        setUiState("failed");
      }
    } catch (e) {
      // Transient errors keep polling; a hard auth failure stops.
      if (e instanceof APIException && e.status === 401) {
        stopTimers();
        setUiState("failed");
      }
    }
  }, [accessToken, sessionId, stopTimers]);

  const startPolling = useCallback(() => {
    startedAt.current = Date.now();
    setElapsedSec(0);
    setUiState("generating");
    stopTimers();
    void poll();
    pollTimer.current = setInterval(() => void poll(), POLL_INTERVAL_MS);
    tickTimer.current = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt.current) / 1000));
    }, 1000);
  }, [poll, stopTimers]);

  useEffect(() => {
    startPolling();
    return stopTimers;
  }, [startPolling, stopTimers]);

  const goHome = () => {
    resetSession();
    // Clear the whole intake chain (chat → survey → submit → report)
    // back to the tabs root so Back doesn't walk back into the questionnaire.
    if (router.canDismiss()) router.dismissAll();
    else router.replace("/(patient)/(tabs)/home");
  };

  const progress = Math.min(0.97, elapsedSec / estimatedSeconds);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={[
        styles.scroll,
        { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 32 },
      ]}
    >
      {uiState === "ready" ? (
        <View style={styles.center}>
          <View style={styles.checkSquare}>
            <Check size={26} color={colors.onInk} strokeWidth={2.4} />
          </View>
          <Text style={styles.title}>문진이 완료됐어요</Text>
          <Text style={styles.body}>
            리포트가 안전하게 보관됐어요.{"\n"}기록 탭에서 언제든 다시 볼 수 있어요.
          </Text>

          {latestRecord ? (
            <View style={styles.scoreCard}>
              <Text style={styles.scoreNum}>
                {latestRecord.totalScore}
                <Text style={styles.scoreMax}> /{latestRecord.maxScore}</Text>
              </Text>
              <Text style={styles.scoreLabel}>
                {SURVEYS[latestRecord.instrument].toolLabel} ·{" "}
                {SEVERITY_KO[latestRecord.severity] ?? latestRecord.severity}
              </Text>
            </View>
          ) : null}

          <View style={styles.readyActions}>
            <Button label="홈으로" onPress={goHome} />
            {latestRecord ? (
              <Button
                label="리포트 보기"
                variant="ghost"
                onPress={() => {
                  // 인트레이크 체인을 정리한 뒤 상세로 — 뒤로가기가 설문으로
                  // 되돌아가지 않도록 (goHome과 동일한 dismissAll 정책).
                  resetSession();
                  if (router.canDismiss()) router.dismissAll();
                  router.push({
                    pathname: "/(patient)/report/detail",
                    params: { recordId: latestRecord.id },
                  });
                }}
              />
            ) : null}
          </View>
        </View>
      ) : uiState === "failed" ? (
        <View style={styles.center}>
          <View style={[styles.checkSquare, styles.failSquare]}>
            <Text style={styles.failMark}>!</Text>
          </View>
          <Text style={styles.title}>리포트 생성에 실패했어요</Text>
          <Text style={styles.body}>
            잠시 후 다시 시도해 주세요. 입력하신 내용은 안전하게 보관됩니다.
          </Text>
          <View style={{ height: 16, alignSelf: "stretch" }} />
          <Button label="다시 시도" onPress={startPolling} />
          <View style={{ height: 8, alignSelf: "stretch" }} />
          <Button label="홈으로" variant="ghost" onPress={goHome} />
        </View>
      ) : (
        <View style={styles.generating}>
          <ActivityIndicator size="large" color={colors.ink} />
          <Text style={styles.title}>
            AI가 의료진 전달 리포트를{"\n"}만들고 있어요
          </Text>

          {uiState === "overdue" ? (
            <Text style={styles.body}>
              예상보다 오래 걸리고 있어요. 잠시 후 알림을 보내드릴게요. 지금 홈으로 돌아가셔도
              생성은 계속 진행돼요.
            </Text>
          ) : (
            <Text style={styles.body}>약 {estimatedSeconds}초 정도 걸려요.</Text>
          )}

          {uiState === "generating" ? (
            <View style={styles.progressRow}>
              <View style={styles.track}>
                <View style={[styles.fill, { width: `${Math.round(progress * 100)}%` }]} />
              </View>
              <Text style={styles.progressLabel}>
                {elapsedSec} / {estimatedSeconds}s
              </Text>
            </View>
          ) : null}

          <View style={styles.contentsCard}>
            <Text style={styles.contentsTitle}>리포트에 포함되는 내용</Text>
            {REPORT_CONTENTS.map((c) => (
              <View key={c} style={styles.contentRow}>
                <Check size={13} color={colors.ink} strokeWidth={2.4} />
                <Text style={styles.contentText}>{c}</Text>
              </View>
            ))}
          </View>

          <Text style={styles.fine}>본 리포트는 의료진 참고용이며, 진단이 아닙니다.</Text>

          {uiState === "overdue" ? <Button label="홈으로" variant="ghost" onPress={goHome} /> : null}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 24, gap: 16 },
  center: { gap: 10, alignItems: "center", paddingTop: 40 },
  generating: { gap: 20, alignItems: "center", paddingTop: 24 },
  checkSquare: {
    width: 52,
    height: 52,
    borderRadius: 15,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 6,
  },
  scoreCard: {
    alignSelf: "stretch",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    padding: 16,
    marginTop: 10,
  },
  scoreNum: {
    fontSize: 30,
    fontWeight: "500",
    color: colors.ink,
    letterSpacing: -0.9,
    fontVariant: ["tabular-nums"],
  },
  scoreMax: { fontSize: 13, color: colors.faint, fontWeight: "400" },
  scoreLabel: { fontSize: 11.5, color: colors.muted, marginTop: 4 },
  readyActions: { alignSelf: "stretch", gap: 8, marginTop: 12 },
  failSquare: { backgroundColor: colors.danger },
  failMark: { color: "#FFFFFF", fontSize: 30, fontWeight: "800", lineHeight: 34 },
  title: {
    fontSize: 22,
    fontWeight: "700",
    color: colors.ink,
    textAlign: "center",
    lineHeight: 28,
    letterSpacing: -0.4,
  },
  body: { fontSize: 14, color: colors.muted, lineHeight: 21, textAlign: "center" },
  progressRow: { width: "100%", gap: 6, alignItems: "center" },
  track: {
    width: "100%",
    height: 6,
    borderRadius: 999,
    backgroundColor: colors.fill,
    overflow: "hidden",
  },
  fill: { height: 6, borderRadius: 999, backgroundColor: colors.ink },
  progressLabel: { fontSize: 12, color: colors.muted, fontVariant: ["tabular-nums"] },
  contentsCard: {
    width: "100%",
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 18,
    gap: 10,
  },
  contentsTitle: { fontSize: 13.5, fontWeight: "600", color: colors.ink, marginBottom: 4 },
  contentRow: { flexDirection: "row", alignItems: "center", gap: 9 },
  contentText: { fontSize: 13, color: colors.ink2 },
  fine: { fontSize: 12, color: colors.muted, textAlign: "center" },
});
