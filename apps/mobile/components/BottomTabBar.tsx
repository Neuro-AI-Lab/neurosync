/**
 * Patient bottom tab bar (home / hospitals / settings) — screen-spec §S-04/11/13.
 *
 * Presentational: the patient area is a Stack, so this bar switches between the
 * three top-level tabs with router.replace (no back-stacking between tabs).
 * Line icons (react-native-svg) keep the monochrome language; the active tab is
 * ink, idle tabs faint.
 */

import { Href, router } from "expo-router";
import { ComponentType } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Gear, Home, Hospital, IconProps } from "../lib/icons";
import { colors } from "../lib/tokens";

export type TabKey = "home" | "hospitals" | "settings";

const TABS: { key: TabKey; label: string; Icon: ComponentType<IconProps>; href: Href }[] = [
  { key: "home", label: "홈", Icon: Home, href: "/(patient)/home" },
  { key: "hospitals", label: "병원", Icon: Hospital, href: "/(patient)/hospitals" },
  { key: "settings", label: "설정", Icon: Gear, href: "/(patient)/settings" },
];

export function BottomTabBar({ active }: { active: TabKey }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 8) }]}>
      {TABS.map((tab) => {
        const isActive = tab.key === active;
        const tint = isActive ? colors.ink : colors.faint;
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
            <tab.Icon size={22} color={tint} strokeWidth={1.7} />
            <Text style={[styles.label, { color: tint }]}>{tab.label}</Text>
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
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
    paddingTop: 8,
  },
  tab: { flex: 1, alignItems: "center", gap: 3 },
  label: { fontSize: 10, fontWeight: "500" },
});
