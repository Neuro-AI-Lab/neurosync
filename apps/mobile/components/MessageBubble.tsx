import { StyleSheet, Text, View } from "react-native";

import { colors, fontSize, radius, spacing } from "../lib/tokens";

export type MessageBubbleProps = {
  role: "user" | "ai";
  content: string;
  safetyLevel?: string;
};

export function MessageBubble({ role, content, safetyLevel }: MessageBubbleProps) {
  const isUser = role === "user";
  return (
    <View style={[styles.row, isUser ? styles.rowRight : styles.rowLeft]}>
      <View
        style={[
          styles.bubble,
          isUser ? styles.bubbleUser : styles.bubbleAi,
        ]}
        accessibilityRole="text"
        accessibilityLabel={`${isUser ? "내 메시지" : "AI 메시지"}: ${content}`}
      >
        <Text
          style={[
            styles.content,
            { color: isUser ? "#FFFFFF" : colors.textPrimary },
          ]}
        >
          {content}
        </Text>
        {safetyLevel && safetyLevel !== "low" ? (
          <Text style={styles.meta}>
            safety: {safetyLevel}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    paddingHorizontal: spacing.md,
    marginVertical: spacing.xs,
  },
  rowLeft: { justifyContent: "flex-start" },
  rowRight: { justifyContent: "flex-end" },
  bubble: {
    maxWidth: "80%",
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: 2,
  },
  bubbleUser: {
    backgroundColor: colors.stateInfo,
    borderBottomRightRadius: 2,
  },
  bubbleAi: {
    backgroundColor: colors.surfaceElevated,
    borderBottomLeftRadius: 2,
    borderWidth: 1,
    borderColor: colors.border,
  },
  content: {
    fontSize: fontSize.bodyLg,
  },
  meta: {
    fontSize: fontSize.caption,
    color: colors.textSecondary,
  },
});
