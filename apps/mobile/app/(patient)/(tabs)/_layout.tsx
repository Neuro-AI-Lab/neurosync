/**
 * Patient tab navigator (home / hospitals / settings) — screen-spec §S-04/11/13.
 *
 * A real Tabs navigator so each tab keeps its own history and switching between
 * them never touches the parent Stack. The intake flow, /emergency and /report
 * are pushed onto the parent (patient) Stack ABOVE these tabs, so the tab bar
 * correctly disappears during a flow and Back returns here.
 */

import { Tabs } from "expo-router";

import { Gear, Home, Hospital } from "../../../lib/icons";
import { colors } from "../../../lib/tokens";

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.faint,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.line,
          borderTopWidth: 1,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "500" },
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: "홈",
          tabBarIcon: ({ color }) => <Home size={22} color={color} strokeWidth={1.7} />,
        }}
      />
      <Tabs.Screen
        name="hospitals"
        options={{
          title: "병원",
          tabBarIcon: ({ color }) => <Hospital size={22} color={color} strokeWidth={1.7} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "설정",
          tabBarIcon: ({ color }) => <Gear size={22} color={color} strokeWidth={1.7} />,
        }}
      />
    </Tabs>
  );
}
