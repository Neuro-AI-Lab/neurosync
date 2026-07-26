import * as Crypto from "expo-crypto";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AttachButton } from "../../../components/AttachButton";
import { Button } from "../../../components/Button";
import { MessageBubble } from "../../../components/MessageBubble";
import { NavBar } from "../../../components/NavBar";
import { PushToTalk } from "../../../components/PushToTalk";
import { RiskConfirmModal } from "../../../components/RiskConfirm";
import type { QuestionnaireType } from "../../../lib/api";
import { inferTopSurvey } from "../../../lib/domain";
import { ArrowUp } from "../../../lib/icons";
import { SafetyLevel, SessionChatClient, WSEvent, WSStatus } from "../../../lib/ws";
import { colors, radius } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { LocalMessage, useSession } from "../../../state/session";

// BUG-086/090 (apps/ai-server/src/agents/orchestrator.py::_HANDOFF_ACK_MESSAGE)
// stage-1 closing ack literal, mirrored client-side ONLY to detect the closing
// bubble and drive the post-closing "증상 확인" progress UI below it — never
// duplicated as UI copy. If the server-side literal changes, this must too.
const HANDOFF_ACK_MESSAGE = "네 알겠습니다. 답변 주신 내용을 토대로 증상 확인 중입니다.";

// 사용자 지시(2026-07-25, 마무리 멘트 재설계 2단계) stage-2 bubble, shared by
// the auto-prefetch flow and the manual 설문 nav-button fallback so the copy
// never drifts between the two call sites.
const SURVEY_STAGE2_MESSAGE =
  "증상 확인이 완료되었습니다. 보다 정확한 상태 확인을 위해 자가 설문을 진행하겠습니다. " +
  "해당 설문 결과는 의료진 면담에 활용되므로 솔직하게 답변해주시면 감사하겠습니다.";

// Simulated-gauge time constant (ms) — purely cosmetic pacing for the
// real-time-looking gauge while `inferTopSurvey` (background prefetch, capped
// at INFER_TIMEOUT_MS = 75s, never throws) is in flight. The gauge asymptotes
// toward 92% so it never looks "done" before the real answer lands, then
// snaps to 100% the instant the prefetch resolves (success OR fallback).
// BUG-091 (2026-07-26): the real `/ai/domain/infer` latency observed live is
// 20.2s-30.6s (server budget now 60s) — a 2500ms time constant would sit
// pinned at the 92% cap for the bulk of that wait, looking frozen. 9000ms
// keeps the curve visibly climbing across the observed 20-30s range
// (~82%-89% at t=20s/30s) while still reaching the cap by the time the
// 60s server budget could plausibly be hit.
const SURVEY_GAUGE_TIME_CONSTANT_MS = 9000;
const SURVEY_GAUGE_CAP = 0.92;
const SURVEY_GAUGE_TICK_MS = 120;

export default function ChatScreen() {
  const insets = useSafeAreaInsets();
  // Pull token ONCE via a ref so a future refresh doesn't tear down the WS.
  const initialAccessToken = useAuth((s) => s.accessToken);
  const refreshAccessToken = useAuth((s) => s.refreshAccessToken);
  const sessionId = useSession((s) => s.sessionId);
  const messages = useSession((s) => s.messages);
  const progress = useSession((s) => s.progress);
  const addUserMessage = useSession((s) => s.addUserMessage);
  const addAiMessage = useSession((s) => s.addAiMessage);
  const markAcked = useSession((s) => s.markAcked);
  const setRisk = useSession((s) => s.setRisk);
  const setProgress = useSession((s) => s.setProgress);
  const clearRisk = useSession((s) => s.clearRisk);

  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<WSStatus>("idle");
  // CVR-052 gap 1 fix: `neutral: true` for the classifier-unavailable reason
  // (technical failure, not a clinical signal) — suppresses the risk-toned
  // banner color, per CVR-052 finding 2/recommendation 1.
  const [mediumBanner, setMediumBanner] = useState<{ text: string; neutral: boolean } | null>(
    null,
  );
  const lastRisk = useSession((s) => s.lastRisk);
  // v3 FR-042 — 강제 전환 대신 확인 창. FR-041 — 도메인 추정 '분석 중' 상태.
  const [riskConfirm, setRiskConfirm] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const clientRef = useRef<SessionChatClient | null>(null);
  const listRef = useRef<FlatList<LocalMessage>>(null);
  // 분석 중 화면 이탈(Android back 등) 시 늦은 router.push를 막는다.
  const mountedRef = useRef(true);

  // 종료 멘트(HANDOFF_ACK_MESSAGE) 이하 "증상 확인" 진행률 게이지 + CTA 상태.
  const [surveyStageShown, setSurveyStageShown] = useState(false);
  const [surveyProgress, setSurveyProgress] = useState(0);
  const [surveyCtaReady, setSurveyCtaReady] = useState(false);
  // 백그라운드 prefetch 결과 재사용(중복 inferTopSurvey 호출/중복 2단계 버블 방지).
  const surveyInstrumentRef = useRef<QuestionnaireType | null>(null);
  const surveyPrefetchStartedRef = useRef(false);
  const surveyGaugeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (surveyGaugeTimerRef.current) clearInterval(surveyGaugeTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!sessionId || !initialAccessToken) return;

    const client = new SessionChatClient(
      sessionId,
      initialAccessToken,
      // Server says token expired — try REST refresh.
      async () => refreshAccessToken(),
    );
    clientRef.current = client;
    const offStatus = client.onStatus(setStatus);
    const offEvent = client.on((event: WSEvent) => {
      if (event.type === "user:message:received") {
        const ack = event.payload;
        if (ack.idempotencyKey) {
          markAcked(ack.idempotencyKey, ack.messageId, ack.safetyLevel);
        }
      } else if (event.type === "ai:complete") {
        const { messageId, content, progress: p } = event.payload;
        addAiMessage({ id: messageId, role: "ai", content, sentAt: Date.now() });
        setProgress(p.ratio);
      } else if (event.type === "risk:detected") {
        const { level, reason } = event.payload;
        setRisk(event.payload);
        if (level === "high" || level === "critical") {
          // v3 FR-042 — 강제 전환 금지. 강한 햅틱 + 확인 창(모달)에서
          // [도움 받기] 선택 시에만 /emergency 진입.
          void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
          setRiskConfirm(true);
        } else if (level === "medium") {
          // 인라인 배너만 (Screen Spec §S-05 medium 정책). CVR-052 gap 1 fix:
          // `reason === "classifier_unavailable"`(안전 분류기 다운, level은
          // 항상 MEDIUM 하드코딩— services/safety.py::handle_unavailable_
          // classifier)는 실제 위험 판정이 아니라 기술적 장애다. 동일한
          // 위험-톤 문구를 재사용하면 환자가 두 상황을 구분할 수 없다는
          // CVR-052 finding 2 — 별도의, 위험-톤이 아닌 안내 문구로 분기.
          setMediumBanner(
            reason === "classifier_unavailable"
              ? {
                  text: "일시적으로 확인이 지연되고 있어요. 잠시 후 다시 시도해 주세요.",
                  neutral: true,
                }
              : { text: "안전 확인이 필요해요. 도움이 필요하면 알려주세요.", neutral: false },
          );
        }
      } else if (event.type === "auth:error") {
        Alert.alert("연결 오류", "로그인이 만료되었어요. 다시 로그인해 주세요.");
      } else if (event.type === "error") {
        const safeCode = ["FRAME_DECODE_FAILED", "FRAME_INVALID", "FRAME_UNEXPECTED"].includes(
          event.payload.code,
        )
          ? "통신 오류"
          : "오류";
        Alert.alert("메시지 오류", `${safeCode} (${event.payload.code})`);
      }
    });
    client.connect();
    return () => {
      offStatus();
      offEvent();
      client.close();
      clientRef.current = null;
      // C-10: avoid stale modal state if user navigates away mid-event.
      clearRisk();
    };
  }, [
    sessionId,
    initialAccessToken,
    markAcked,
    addAiMessage,
    setRisk,
    setProgress,
    clearRisk,
    refreshAccessToken,
  ]);

  // PRD §5.5 flow — surface the questionnaire step once intake is ~70% done.
  // 사용자 판정(2026-07-25): 환자 화면에는 슬롯 수집율(progress_ratio)을
  // 수치·진행바로 노출하지 않는다 — `questionnaireReady`는 임계값 도달 여부만
  // 내부적으로 판단해 "설문" 내비 버튼 강조에 쓰고, 비율 자체는 표시하지 않는다.
  const questionnaireReady = progress >= 0.7;

  // 사용자 확정 UX 스펙(오늘): 종료 멘트(HANDOFF_ACK_MESSAGE) 도착 시 그 버블
  // 아래에 "증상 확인" 진행률을 실시간으로 보여주고, 완료되면 "설문으로
  // 넘어가기" CTA를 노출한다. 진행률은 실제 작업(설문 구성 API prefetch)과
  // 동기화한다 — 애니메이션은 예상 소요 기준 시각적 페이싱일 뿐, 완결은
  // 항상 실제 응답 도착(성공/폴백 불문, inferTopSurvey는 throw하지 않음)에서
  // 온다. `messages`를 감시해 재마운트(앱 리로드/화면 재진입) 시에도 이미
  // 종료 멘트/2단계 버블이 남아있으면 중복 호출·중복 버블 없이 같은
  // 상태(진행 중 vs CTA-ready)로 복원한다.
  useEffect(() => {
    if (surveyPrefetchStartedRef.current) return;
    const hasClosingAck = messages.some(
      (m) => m.role === "ai" && m.content === HANDOFF_ACK_MESSAGE,
    );
    if (!hasClosingAck) return;
    surveyPrefetchStartedRef.current = true;
    setSurveyStageShown(true);

    const hasStage2 = messages.some((m) => m.role === "ai" && m.content === SURVEY_STAGE2_MESSAGE);
    if (hasStage2) {
      // Remounted after the prefetch had already completed in a prior mount.
      setSurveyProgress(1);
      setSurveyCtaReady(true);
      return;
    }

    const startedAt = Date.now();
    surveyGaugeTimerRef.current = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      const eased =
        SURVEY_GAUGE_CAP * (1 - Math.exp(-elapsed / SURVEY_GAUGE_TIME_CONSTANT_MS));
      setSurveyProgress((prev) => Math.max(prev, eased));
    }, SURVEY_GAUGE_TICK_MS);

    void inferTopSurvey(initialAccessToken, sessionId).then((instrument) => {
      if (surveyGaugeTimerRef.current) {
        clearInterval(surveyGaugeTimerRef.current);
        surveyGaugeTimerRef.current = null;
      }
      if (!mountedRef.current) return;
      surveyInstrumentRef.current = instrument;
      setSurveyProgress(1);
      addAiMessage({
        id: Crypto.randomUUID(),
        role: "ai",
        content: SURVEY_STAGE2_MESSAGE,
        sentAt: Date.now(),
      });
      setSurveyCtaReady(true);
    });
    // messages is the trigger source (watched for the closing-ack literal);
    // the effect body is idempotent via surveyPrefetchStartedRef, so it is
    // intentionally not re-run on every other dependency's identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // v3 FR-039/041 — 대화 종료 → '분석 중' → top1 문진 1종으로 바로 진입.
  // 추정 결과(도구 ID)는 라우팅에만 쓰고 화면·상태에 남기지 않는다 (NFR v3-2).
  // 사용자 지시(2026-07-25, 마무리 멘트 재설계 2단계): domain/infer 성공 후
  // (= "증상 확인"이 완료된 시점) 설문 전환 전 마무리 멘트를 채팅 말풍선으로
  // 보여준 뒤 설문으로 이동한다. inferTopSurvey는 절대 throw하지 않으므로
  // (BUG-091: 75초 상한 초과/오류는 FALLBACK_SURVEY로 흡수) 이 멘트는 실패
  // 여부와 무관하게 항상 표시된다.
  const goSurvey = async () => {
    if (analyzing) return;
    // 백그라운드 prefetch가 이미 끝난 경우(종료 멘트 이후 CTA 경로) 재호출
    // 없이 즉시 진입 — 2단계 버블은 prefetch 완료 시 이미 추가돼 있다.
    if (surveyInstrumentRef.current) {
      router.push({
        pathname: "/(patient)/intake/survey",
        params: { instrument: surveyInstrumentRef.current },
      });
      return;
    }
    setAnalyzing(true);
    try {
      const instrument = await inferTopSurvey(initialAccessToken, sessionId);
      if (!mountedRef.current) return; // 이탈 후 늦은 내비게이션 방지
      addAiMessage({
        id: Crypto.randomUUID(),
        role: "ai",
        content: SURVEY_STAGE2_MESSAGE,
        sentAt: Date.now(),
      });
      router.push({
        pathname: "/(patient)/intake/survey",
        params: { instrument },
      });
    } finally {
      if (mountedRef.current) setAnalyzing(false);
    }
  };

  const onSend = () => {
    const content = draft.trim();
    if (!content || !clientRef.current) return;
    if (status !== "open") return;
    // Insert AFTER we confirm the socket is ready, to avoid orphan optimistic bubbles.
    const idempotencyKey = Crypto.randomUUID();
    const sent = clientRef.current.sendMessage({ content, idempotencyKey });
    if (!sent) return;
    addUserMessage({
      id: idempotencyKey,
      role: "user",
      content,
      sentAt: Date.now(),
    });
    setDraft("");
    setMediumBanner(null);
  };

  const statusLabel = useMemo<string>(() => {
    switch (status) {
      case "connecting":
        return "연결 중…";
      case "closing":
      case "closed":
        return "연결이 끊겼어요. 자동으로 다시 연결해요";
      case "auth_failed":
        return "로그인이 만료되었어요";
      case "exhausted":
        return "다시 연결할 수 없어요. 잠시 후 다시 시도해 주세요";
      default:
        return "";
    }
  }, [status]);

  const canSend = !!draft.trim() && status === "open";

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 24}
    >
      <NavBar
        backLabel="그만하기"
        onBack={() => router.back()}
        title="사전 문진"
        liveDot={status === "open"}
        right={
          <Pressable
            onPress={() => void goSurvey()}
            accessibilityRole="button"
            accessibilityLabel="표준 문진으로 이동"
            hitSlop={8}
            disabled={analyzing}
          >
            <Text style={[styles.navAct, questionnaireReady && styles.navActReady]}>설문</Text>
          </Pressable>
        }
      />

      {/* 사용자 판정(2026-07-25): 슬롯 수집율(progress_ratio) 수치·진행바를
          환자 화면에서 제거 — 이전에는 여기 수집 진행률 라벨/퍼센트/진행바
          (styles.cprog/cprogRow/cprogLabel/cprogPct/track/fill)가 있었다.
          progress 자체(setProgress)는 백엔드·설문 라우팅 판단(questionnaireReady)에
          계속 쓰이며, 화면 표시만 제거한다. */}

      {statusLabel ? <Text style={styles.statusText}>{statusLabel}</Text> : null}
      {mediumBanner ? (
        <View
          style={[styles.banner, mediumBanner.neutral && styles.bannerNeutral]}
          accessibilityLiveRegion="polite"
        >
          <Text style={styles.bannerText}>{mediumBanner.text}</Text>
          <Pressable
            onPress={() =>
              // CVR-052 gap 3 fix: consume the backend-computed, consent-
              // gated `routeTo` (`/emergency` vs `/self_hotline`,
              // `services/safety.py::_payload_for`) instead of the pre-fix
              // unconditional hardcoded push — restores the consent-
              // respecting distinction CVR-052 finding 4 found was inert.
              // No dedicated `/self_hotline` screen exists in the mobile app
              // (verified this pass) — per the "no major frontend rewrite"
              // constraint, `/self_hotline` reuses the one real destination
              // (`emergency.tsx`) with a `mode` param it now reads (CVR-052
              // gap 2/3 combined fix, see that screen) rather than adding a
              // new route file.
              router.push({
                pathname: "/(patient)/emergency",
                params: {
                  reason: lastRisk?.reason ?? "",
                  mode: lastRisk?.routeTo === "/self_hotline" ? "self_hotline" : "emergency",
                },
              })
            }
          >
            <Text style={styles.bannerLink}>도움 받기</Text>
          </Pressable>
        </View>
      ) : null}

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => (
          <MessageBubble role={item.role} content={item.content} safetyLevel={item.safetyLevel} />
        )}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        style={styles.list}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          <Text style={styles.empty}>오늘은 어떤 점이 가장 힘드신가요?{"\n"}편하게 말씀해 주세요.</Text>
        }
        ListFooterComponent={
          // 사용자 확정 UX 스펙: 종료 멘트 버블 아래 실시간 "증상 확인" 진행률
          // → 완료 시 "설문으로 넘어가기" CTA. 슬롯/내부 용어는 노출하지 않는다.
          surveyStageShown ? (
            <View style={styles.surveyStage}>
              {!surveyCtaReady ? (
                <View accessibilityLiveRegion="polite">
                  <View style={styles.surveyTrack}>
                    <View
                      style={[
                        styles.surveyFill,
                        { width: `${Math.round(surveyProgress * 100)}%` },
                      ]}
                    />
                  </View>
                  <Text style={styles.surveyLabel}>
                    증상 확인 중… {Math.round(surveyProgress * 100)}%
                  </Text>
                </View>
              ) : (
                <Button
                  label="설문으로 넘어가기"
                  onPress={() => void goSurvey()}
                  variant="primary"
                  disabled={analyzing}
                  loading={analyzing}
                />
              )}
            </View>
          ) : null
        }
      />

      <View style={[styles.inbar, { paddingBottom: Math.max(insets.bottom, 8) }]}>
        <AttachButton
          disabled={status !== "open"}
          onPick={(doc) =>
            // FR-048 — 촬영/선택 후 OCR 확인 화면으로. 인식·확정은 거기서.
            router.push({
              pathname: "/(patient)/intake/ocr-confirm",
              params: { uri: doc.uri, name: doc.name, mime: doc.mime },
            })
          }
        />
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="메시지를 입력해 주세요"
          placeholderTextColor={colors.faint}
          style={styles.tf}
          multiline
          maxLength={4000}
        />
        <PushToTalk
          token={initialAccessToken}
          sessionId={sessionId}
          disabled={status !== "open"}
          onTranscript={(text) =>
            // FR-035 — fill the input; the patient edits + sends explicitly.
            setDraft((prev) => (prev.trim() ? `${prev.trim()} ${text}` : text))
          }
          onNotice={(_reason, message) => Alert.alert("음성 입력", message)}
        />
        <Pressable
          onPress={onSend}
          accessibilityRole="button"
          accessibilityLabel="메시지 보내기"
          style={({ pressed }) => [
            styles.send,
            { opacity: canSend ? (pressed ? 0.7 : 1) : 0.35 },
          ]}
          disabled={!canSend}
        >
          <ArrowUp size={17} color={colors.onInk} />
        </Pressable>
      </View>

      {/* v3 FR-042 — 위험 확인 창 (모달). 명시적 선택 후에만 응급 진입. */}
      <RiskConfirmModal
        visible={riskConfirm}
        onHelp={() => {
          setRiskConfirm(false);
          router.push("/(patient)/emergency");
        }}
        onDismiss={() => setRiskConfirm(false)}
      />

      {/* v3 FR-041 — '분석 중' 로딩 (상한은 inferTopSurvey가 보장). */}
      {analyzing ? (
        <View style={styles.analyzing} accessibilityLiveRegion="polite">
          <ActivityIndicator size="large" color={colors.ink} />
          <Text style={styles.analyzingTitle}>이야기를 정리하고 있어요</Text>
          <Text style={styles.analyzingSub}>곧 알맞은 문진으로 이어드릴게요</Text>
        </View>
      ) : null}
    </KeyboardAvoidingView>
  );
}

const sentenceColor = (level: SafetyLevel | undefined) => {
  // Reserved for future colorization. Type re-exported so consumers stay typed.
  return level;
};
void sentenceColor;

const styles = StyleSheet.create({
  navAct: { fontSize: 14, color: colors.muted, fontWeight: "600", paddingHorizontal: 6 },
  navActReady: { color: colors.ink },
  statusText: { fontSize: 12, color: colors.muted, paddingHorizontal: 16, paddingVertical: 4 },
  banner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.warnSoft,
    borderColor: "rgba(154,106,22,0.28)",
    borderWidth: 1,
    marginHorizontal: 16,
    marginBottom: 6,
    paddingVertical: 10,
    paddingHorizontal: 13,
    borderRadius: 12,
    gap: 9,
  },
  bannerText: { color: colors.ink, flex: 1, fontSize: 12, lineHeight: 16 },
  bannerLink: { color: colors.warn, fontWeight: "600", fontSize: 12 },
  // CVR-052 gap 1 fix: neutral (non-risk-toned) styling for the
  // classifier-unavailable banner — a technical-failure notice should not
  // look identical to a genuine risk detection (finding 2).
  bannerNeutral: {
    backgroundColor: colors.fill,
    borderColor: colors.lineStrong,
  },
  list: { flex: 1 },
  listContent: { paddingHorizontal: 16, paddingVertical: 8 },
  surveyStage: { paddingHorizontal: 4, paddingTop: 4, paddingBottom: 12, gap: 8 },
  surveyTrack: {
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.fill,
    overflow: "hidden",
  },
  surveyFill: {
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
  },
  surveyLabel: { fontSize: 12, color: colors.muted },
  empty: {
    textAlign: "center",
    color: colors.muted,
    fontSize: 15,
    lineHeight: 22,
    paddingVertical: 40,
    paddingHorizontal: 24,
  },
  inbar: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: 12,
    paddingTop: 8,
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
  },
  tf: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    paddingHorizontal: 14,
    paddingVertical: 9,
    fontSize: 14,
    color: colors.ink,
  },
  send: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  analyzing: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(255,255,255,0.96)",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  analyzingTitle: {
    marginTop: 12,
    fontSize: 18,
    fontWeight: "700",
    color: colors.ink,
    letterSpacing: -0.4,
  },
  analyzingSub: { fontSize: 13, color: colors.muted },
});
