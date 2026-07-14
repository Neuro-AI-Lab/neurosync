/**
 * iOS-style navigation bar — back affordance on the left, centered title,
 * optional right-hand action. Kept presentational; screens pass handlers.
 */

import { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ChevronLeft } from "../lib/icons";
import { colors } from "../lib/tokens";

export type NavBarProps = {
  title?: string;
  /** Text shown next to the back chevron (e.g. "뒤로", "그만하기"). */
  backLabel?: string;
  onBack?: () => void;
  /** A live dot rendered before the title (chat "연결됨" indicator). */
  liveDot?: boolean;
  right?: ReactNode;
};

export function NavBar({ title, backLabel, onBack, liveDot, right }: NavBarProps) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.wrap, { paddingTop: insets.top + 4 }]}>
      <View style={styles.side}>
        {onBack ? (
          <Pressable onPress={onBack} accessibilityRole="button" hitSlop={8} style={styles.back}>
            <ChevronLeft size={19} color={colors.ink} />
            {backLabel ? <Text style={styles.backLabel}>{backLabel}</Text> : null}
          </Pressable>
        ) : null}
      </View>

      <View style={styles.center}>
        {liveDot ? <View style={styles.dot} /> : null}
        {title ? (
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
        ) : null}
      </View>

      <View style={[styles.side, styles.sideRight]}>{right}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    minHeight: 44,
    paddingHorizontal: 12,
    paddingBottom: 6,
  },
  side: { width: 96, flexDirection: "row", alignItems: "center" },
  sideRight: { justifyContent: "flex-end" },
  back: { flexDirection: "row", alignItems: "center", gap: 1 },
  backLabel: { fontSize: 15, color: colors.ink, fontWeight: "400" },
  center: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.ink },
  title: { fontSize: 15, fontWeight: "600", color: colors.ink },
});
