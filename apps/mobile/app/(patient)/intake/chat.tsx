import * as Crypto from "expo-crypto";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
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
import { SafetyLevel, SessionChatClient, WSEvent, WSStatus } from "../../../lib/ws";
import { colors, fontSize, radius, spacing } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { LocalMessage, useSession } from "../../../state/session";

export default function ChatScreen() {
  const insets = useSafeAreaInsets();
  // Pull token ONCE via a ref so a future refresh doesn't tear down the WS.
  const initialAccessToken = useAuth((s) => s.accessToken);
  const refreshAccessToken = useAuth((s) => s.refreshAccessToken);
  const sessionId = useSession((s) => s.sessionId);
  const messages = useSession((s) => s.messages);
  const addUserMessage = useSession((s) => s.addUserMessage);
  const markAcked = useSession((s) => s.markAcked);
  const setRisk = useSession((s) => s.setRisk);
  const clearRisk = useSession((s) => s.clearRisk);

  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<WSStatus>("idle");
  const [mediumBanner, setMediumBanner] = useState<string | null>(null);
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
      } else if (event.type === "risk:detected") {
        const { level } = event.payload;
        setRisk(event.payload);
        if (level === "high" || level === "critical") {
          // PRD §A 보수적 탐지 — 강한 햅틱 + 응급 전환.
          void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
          router.push("/(patient)/emergency");
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
  }, [sessionId, initialAccessToken, markAcked, setRisk, clearRisk, refreshAccessToken]);

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
      case "open":
        return "연결됨";
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

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 24}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} accessibilityRole="button">
          <Text style={styles.back}>← 그만하기</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Pressable
          onPress={() => router.push("/(patient)/intake/phq9")}
          accessibilityRole="button"
          accessibilityLabel="표준 문진으로 이동"
          hitSlop={8}
        >
          <Text style={styles.next}>설문 →</Text>
        </Pressable>
        <View
          style={[
            styles.statusDot,
            { backgroundColor: status === "open" ? colors.stateSuccess : colors.stateWarning },
          ]}
        />
      </View>
      {statusLabel ? <Text style={styles.statusText}>{statusLabel}</Text> : null}
      {mediumBanner ? (
        <View style={styles.banner} accessibilityLiveRegion="polite">
          <Text style={styles.bannerText}>{mediumBanner}</Text>
          <Pressable onPress={() => router.push("/(patient)/emergency")}>
            <Text style={styles.bannerLink}>도움 받기 →</Text>
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
        ListEmptyComponent={
          <Text style={styles.empty}>오늘은 어떤 점이 가장 힘드신가요?</Text>
        }
      />

      <View style={[styles.inputBar, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="메시지를 입력해 주세요"
          placeholderTextColor={colors.textSecondary}
          style={styles.input}
          multiline
          maxLength={4000}
        />
        <Pressable
          onPress={onSend}
          accessibilityRole="button"
          accessibilityLabel="메시지 보내기"
          style={({ pressed }) => [
            styles.sendBtn,
            { opacity: draft.trim() && status === "open" ? (pressed ? 0.7 : 1) : 0.4 },
          ]}
          disabled={!draft.trim() || status !== "open"}
        >
          <Text style={styles.sendBtnText}>↑</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const sentenceColor = (level: SafetyLevel | undefined) => {
  // Reserved for future colorization. Type re-exported so consumers stay typed.
  return level;
};
void sentenceColor;

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    gap: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  back: { fontSize: fontSize.bodyLg, color: colors.textPrimary, fontWeight: "500" },
  next: { fontSize: fontSize.bodyLg, color: colors.stateInfo, fontWeight: "600", marginRight: spacing.sm },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  statusText: {
    fontSize: fontSize.caption,
    color: colors.textSecondary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  banner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#FEF3C7",
    borderColor: colors.stateWarning,
    borderWidth: 1,
    marginHorizontal: spacing.md,
    marginVertical: spacing.xs,
    padding: spacing.sm,
    borderRadius: radius.md,
    gap: spacing.sm,
  },
  bannerText: { color: colors.textPrimary, flex: 1, fontSize: fontSize.body },
  bannerLink: { color: colors.stateWarning, fontWeight: "600", fontSize: fontSize.body },
  list: { flex: 1 },
  empty: {
    textAlign: "center",
    color: colors.textSecondary,
    fontSize: fontSize.bodyLg,
    padding: spacing.xl,
  },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: fontSize.bodyLg,
    color: colors.textPrimary,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.stateInfo,
    alignItems: "center",
    justifyContent: "center",
  },
  sendBtnText: { color: colors.surface, fontSize: fontSize.title, fontWeight: "700" },
});
