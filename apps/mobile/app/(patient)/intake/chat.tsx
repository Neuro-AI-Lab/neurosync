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

import { MessageBubble } from "../../../components/MessageBubble";
import { NavBar } from "../../../components/NavBar";
import { PushToTalk } from "../../../components/PushToTalk";
import { RiskConfirmModal } from "../../../components/RiskConfirm";
import { inferTopSurvey } from "../../../lib/domain";
import { ArrowUp } from "../../../lib/icons";
import { SafetyLevel, SessionChatClient, WSEvent, WSStatus } from "../../../lib/ws";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { LocalMessage, useSession } from "../../../state/session";

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
  const [mediumBanner, setMediumBanner] = useState<string | null>(null);
  // v3 FR-042 — 강제 전환 대신 확인 창. FR-041 — 도메인 추정 '분석 중' 상태.
  const [riskConfirm, setRiskConfirm] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const clientRef = useRef<SessionChatClient | null>(null);
  const listRef = useRef<FlatList<LocalMessage>>(null);

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
        const { level } = event.payload;
        setRisk(event.payload);
        if (level === "high" || level === "critical") {
          // v3 FR-042 — 강제 전환 금지. 강한 햅틱 + 확인 창(모달)에서
          // [도움 받기] 선택 시에만 /emergency 진입.
          void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
          setRiskConfirm(true);
        } else if (level === "medium") {
          // 인라인 배너만 (Screen Spec §S-05 medium 정책)
          setMediumBanner("안전 확인이 필요해요. 도움이 필요하면 알려주세요.");
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
  const progressPct = Math.round(progress * 100);
  const questionnaireReady = progress >= 0.7;

  // v3 FR-039/041 — 대화 종료 → '분석 중' → top1 문진 1종으로 바로 진입.
  // 추정 결과(도구 ID)는 라우팅에만 쓰고 화면·상태에 남기지 않는다 (NFR v3-2).
  const goSurvey = async () => {
    if (analyzing) return;
    setAnalyzing(true);
    try {
      const instrument = await inferTopSurvey(initialAccessToken, sessionId);
      router.push({
        pathname: "/(patient)/intake/survey",
        params: { instrument },
      });
    } finally {
      setAnalyzing(false);
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

      <View style={styles.cprog}>
        <View style={styles.cprogRow}>
          <Text style={styles.cprogLabel}>수집 진행률</Text>
          <Text style={styles.cprogPct}>
            {questionnaireReady ? `문진 준비됨 · ${progressPct}%` : `${progressPct}%`}
          </Text>
        </View>
        <View
          style={styles.track}
          accessibilityRole="progressbar"
          accessibilityValue={{ min: 0, max: 100, now: progressPct }}
        >
          <View style={[styles.fill, { width: `${progressPct}%` }]} />
        </View>
      </View>

      {statusLabel ? <Text style={styles.statusText}>{statusLabel}</Text> : null}
      {mediumBanner ? (
        <View style={styles.banner} accessibilityLiveRegion="polite">
          <Text style={styles.bannerText}>{mediumBanner}</Text>
          <Pressable onPress={() => router.push("/(patient)/emergency")}>
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
      />

      <View style={[styles.inbar, { paddingBottom: Math.max(insets.bottom, 8) }]}>
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
  cprog: { paddingHorizontal: 16, paddingBottom: 8 },
  cprogRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 6 },
  cprogLabel: { fontSize: 11, color: colors.muted },
  cprogPct: { fontSize: 11.5, color: colors.ink, fontWeight: "500" },
  track: { height: 4, borderRadius: 999, backgroundColor: colors.fill, overflow: "hidden" },
  fill: { height: 4, borderRadius: 999, backgroundColor: colors.ink },
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
  list: { flex: 1 },
  listContent: { paddingHorizontal: 16, paddingVertical: 8 },
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
