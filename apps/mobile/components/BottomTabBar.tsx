/**
 * Patient bottom tab bar (home / hospitals / settings) — screen-spec §S-04/11/13.
 *
 * Presentational: the patient area is a Stack, so this bar switches between the
 * three top-level tabs with router.replace (no back-stacking between tabs).
 * The intake flow, /emergency and /report keep no tab bar by simply not
 * rendering it.
 */

import { Href, router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, fontSize, spacing } from "../lib/tokens";

export type TabKey = "home" | "hospitals" | "settings";

const TABS: { key: TabKey; label: string; glyph: string; href: Href }[] = [
  { key: "home", label: "홈", glyph: "🏠", href: "/(patient)/home" },
  { key: "hospitals", label: "병원", glyph: "🏥", href: "/(patient)/hospitals" },
  { key: "settings", label: "설정", glyph: "⚙️", href: "/(patient)/settings" },
];

export function BottomTabBar({ active }: { active: TabKey }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
      {TABS.map((tab) => {
        const isActive = tab.key === active;
        return (
          <Pressable
            key={tab.key}
            style={styles.tab}
            accessibilityRole="tab"
            accessibilityState={{ selected: isActive }}
            accessibilityLabel={tab.label}
            onPress={() => {
              if (!isActive) router.replace(tab.href);
            }}
          >
            <Text style={[styles.glyph, { opacity: isActive ? 1 : 0.45 }]}>{tab.glyph}</Text>
            <Text style={[styles.label, isActive ? styles.labelActive : styles.labelIdle]}>
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
    paddingTop: spacing.sm,
  },
  tab: { flex: 1, alignItems: "center", gap: 2 },
  glyph: { fontSize: 20 },
  label: { fontSize: fontSize.caption, fontWeight: "600" },
  labelActive: { color: colors.textPrimary },
  labelIdle: { color: colors.textSecondary },
});
