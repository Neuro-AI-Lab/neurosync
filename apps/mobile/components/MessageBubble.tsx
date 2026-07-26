import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors } from "../lib/tokens";

export type MessageBubbleProps = {
  role: "user" | "ai";
  content: string;
  safetyLevel?: string;
  /** 최신 AI 메시지 도착 시 한 글자씩 드러낸다(스트리밍처럼 보이는 타자기 효과). */
  animate?: boolean;
  /** 리빌 완료 콜백 — 부모가 1회성 처리(스크롤 재진입 시 재실행 방지)에 쓴다. */
  onRevealed?: () => void;
};

const TYPE_MS_PER_CHAR = 18;

/** animate가 켜진 첫 마운트에서만 content를 한 글자씩 공개. 이후엔 전체 표시. */
function useTypewriter(content: string, animate: boolean, onDone?: () => void): string {
  const [shown, setShown] = useState(animate ? "" : content);
  const ran = useRef(false);
  useEffect(() => {
    if (!animate || ran.current) {
      setShown(content);
      return;
    }
    ran.current = true;
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setShown(content.slice(0, i));
      if (i >= content.length) {
        clearInterval(id);
        onDone?.();
      }
    }, TYPE_MS_PER_CHAR);
    return () => clearInterval(id);
    // onDone 은 매 렌더 새 함수일 수 있으나 재실행되면 안 되므로 deps에서 제외.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, animate]);
  return shown;
}

export function MessageBubble({
  role,
  content,
  safetyLevel,
  animate = false,
  onRevealed,
}: MessageBubbleProps) {
  const isUser = role === "user";
  const flagged = safetyLevel && safetyLevel !== "low";
  // 사용자 메시지는 즉시, AI 최신 메시지는 타자기 효과.
  const shown = useTypewriter(content, animate && !isUser, onRevealed);
  return (
    <View style={isUser ? styles.rowRight : styles.rowLeft}>
      <View
        style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAi]}
        accessibilityRole="text"
        accessibilityLabel={`${isUser ? "내 메시지" : "AI 메시지"}: ${content}`}
      >
        <Text style={[styles.content, { color: isUser ? colors.onInk : colors.ink }]}>
          {shown}
        </Text>
      </View>
      {flagged ? <Text style={styles.meta}>안전 확인 · {safetyLevel}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  rowLeft: { alignItems: "flex-start", marginVertical: 4 },
  rowRight: { alignItems: "flex-end", marginVertical: 4 },
  bubble: {
    maxWidth: "82%",
    borderRadius: 18,
    paddingHorizontal: 13,
    paddingVertical: 10,
  },
  bubbleUser: {
    backgroundColor: colors.ink,
    borderBottomRightRadius: 5,
  },
  bubbleAi: {
    backgroundColor: colors.fill,
    borderBottomLeftRadius: 5,
  },
  content: {
    fontSize: 14,
    lineHeight: 20,
  },
  meta: {
    fontSize: 10.5,
    color: colors.faint,
    marginTop: 3,
    marginHorizontal: 3,
  },
});
