import { StyleSheet, Text, View } from "react-native";

import { colors } from "../lib/tokens";

export type MessageBubbleProps = {
  role: "user" | "ai";
  content: string;
  safetyLevel?: string;
};

export function MessageBubble({ role, content, safetyLevel }: MessageBubbleProps) {
  const isUser = role === "user";
  const flagged = safetyLevel && safetyLevel !== "low";
  return (
    <View style={isUser ? styles.rowRight : styles.rowLeft}>
      <View
        style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAi]}
        accessibilityRole="text"
        accessibilityLabel={`${isUser ? "내 메시지" : "AI 메시지"}: ${content}`}
      >
        <Text style={[styles.content, { color: isUser ? colors.onInk : colors.ink }]}>
          {content}
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
