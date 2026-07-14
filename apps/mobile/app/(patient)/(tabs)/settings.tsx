/**
 * S-13 `/settings` — demo scope: profile (read-only), consent toggles,
 * re-view onboarding, logout. Tab-bar screen.
 *
 * iOS grouped inset lists on a grouped ground; consent edit (FR-026/034) and
 * profile edit (FR-002) hit APIs that aren't in the demo yet, so those are
 * local-only / stubbed with an explicit notice. Logout is the one destructive
 * (red) row.
 */

import { router } from "expo-router";
import { ReactNode, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ChevronRight } from "../../../lib/icons";
import { APIException, setVoiceConsent } from "../../../lib/api";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";

const APP_VERSION = "뉴로싱크 v0.1.0";

function displayName(email: string | undefined): string {
  if (!email) return "환자";
  const idx = email.indexOf("@");
  return idx > 0 ? email.slice(0, idx) : email;
}

function GList({ children }: { children: ReactNode }) {
  return <View style={styles.glist}>{children}</View>;
}

function GRow({
  label,
  sub,
  onPress,
  right,
  danger,
  first,
}: {
  label: string;
  sub?: string;
  onPress?: () => void;
  right?: ReactNode;
  danger?: boolean;
  first?: boolean;
}) {
  return (
    <Pressable
      style={[styles.grow, !first && styles.growDivider]}
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <View style={{ flex: 1 }}>
        <Text style={[styles.growLabel, danger && { color: colors.danger }]}>{label}</Text>
        {sub ? <Text style={styles.growSub}>{sub}</Text> : null}
      </View>
      {right ?? (onPress ? <ChevronRight size={14} color={colors.faint} /> : null)}
    </Pressable>
  );
}

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const user = useAuth((s) => s.user);
  const accessToken = useAuth((s) => s.accessToken);
  const logout = useAuth((s) => s.logout);

  // risk_notify edit API is Phase 2; voice consent (FR-034) has a real endpoint.
  const [riskNotify, setRiskNotify] = useState(true);
  const [voiceInput, setVoiceInput] = useState(false);
  const [voiceSaving, setVoiceSaving] = useState(false);

  const onVoiceToggle = async (next: boolean) => {
    setVoiceInput(next); // optimistic
    if (!accessToken) return;
    setVoiceSaving(true);
    try {
      await setVoiceConsent(accessToken, next);
    } catch (e) {
      setVoiceInput(!next); // revert on failure
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      Alert.alert("저장 실패", `잠시 후 다시 시도해 주세요 (코드: ${code})`);
    } finally {
      setVoiceSaving(false);
    }
  };

  const stub = (what: string) => Alert.alert(what, "이 기능은 정식 버전에서 제공됩니다.");

  const confirmLogout = () => {
    Alert.alert("로그아웃", "로그아웃하시겠어요?", [
      { text: "취소", style: "cancel" },
      { text: "로그아웃", style: "destructive", onPress: () => void logout() },
    ]);
  };

  const initial = displayName(user?.email).charAt(0);

  return (
    <View style={{ flex: 1, backgroundColor: colors.group }}>
      <Text style={[styles.largeTitle, { paddingTop: insets.top + 8 }]}>설정</Text>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scroll}>
        <GList>
          <Pressable
            style={styles.profile}
            onPress={() => stub("프로필 수정")}
            accessibilityRole="button"
          >
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{initial}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.profileName}>{displayName(user?.email)}님</Text>
              <Text style={styles.profileEmail}>{user?.email ?? "—"}</Text>
            </View>
            <ChevronRight size={14} color={colors.faint} />
          </Pressable>
        </GList>

        <Text style={styles.glabel}>개인정보 및 동의</Text>
        <GList>
          <GRow
            first
            label="위험 통보 동의"
            right={<Switch value={riskNotify} onValueChange={setRiskNotify} trackColor={{ true: colors.ink, false: colors.lineStrong }} />}
          />
          <GRow
            label="음성 입력 사용 (민감정보)"
            right={
              <Switch
                value={voiceInput}
                onValueChange={onVoiceToggle}
                disabled={voiceSaving}
                trackColor={{ true: colors.ink, false: colors.lineStrong }}
              />
            }
          />
          <GRow label="약관 · 개인정보 처리방침" onPress={() => stub("약관 보기")} />
        </GList>
        <Text style={styles.gfoot}>음성 동의를 끄면 마이크 입력이 꺼져요.</Text>

        <Text style={styles.glabel}>앱</Text>
        <GList>
          <GRow first label="온보딩 다시 보기" onPress={() => router.push("/(auth)/onboarding")} />
          <GRow label="안전 도움말 (1393 · 119)" onPress={() => router.push("/(patient)/emergency")} />
        </GList>

        <View style={{ height: 8 }} />
        <GList>
          <GRow first label="로그아웃" danger onPress={confirmLogout} />
        </GList>

        <Text style={styles.version}>{APP_VERSION}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  largeTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: colors.ink,
    letterSpacing: -0.9,
    paddingHorizontal: 20,
    paddingBottom: 6,
  },
  scroll: { paddingHorizontal: 16, paddingTop: 6, paddingBottom: 20 },
  glist: {
    backgroundColor: colors.surface,
    borderRadius: 13,
    overflow: "hidden",
  },
  profile: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12 },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontSize: 14, fontWeight: "600", color: colors.onInk },
  profileName: { fontSize: 14.5, fontWeight: "600", color: colors.ink },
  profileEmail: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  grow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    minHeight: 44,
    paddingHorizontal: 15,
    paddingVertical: 8,
  },
  growDivider: { borderTopWidth: 1, borderTopColor: colors.sep },
  growLabel: { fontSize: 14.5, color: colors.ink },
  growSub: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  glabel: {
    fontSize: 11.5,
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    paddingHorizontal: 15,
    paddingTop: 18,
    paddingBottom: 6,
    fontWeight: "500",
  },
  gfoot: { fontSize: 11, color: colors.muted, paddingHorizontal: 15, paddingTop: 6, lineHeight: 15 },
  version: {
    fontSize: 10,
    color: colors.faint,
    textAlign: "center",
    marginTop: 24,
    letterSpacing: 0.5,
    fontVariant: ["tabular-nums"],
  },
});
