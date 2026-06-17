/**
 * S-13 `/settings` — demo scope: profile (read-only), consent toggles,
 * re-view onboarding, logout. Tab-bar screen.
 *
 * Consent edit (FR-026/034) and profile edit (FR-002) hit APIs that aren't in
 * the demo yet, so those are local-only / stubbed with an explicit notice.
 */

import { router } from "expo-router";
import { ReactNode, useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BottomTabBar } from "../../components/BottomTabBar";
import { APIException, setVoiceConsent } from "../../lib/api";
import { colors, fontSize, radius, spacing } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

const APP_VERSION = "v0.1.0 (Demo)";

function displayName(email: string | undefined): string {
  if (!email) return "환자";
  const idx = email.indexOf("@");
  return idx > 0 ? email.slice(0, idx) : email;
}

function Row({
  label,
  onPress,
  right,
  danger,
}: {
  label: string;
  onPress?: () => void;
  right?: ReactNode;
  danger?: boolean;
}) {
  return (
    <Pressable
      style={styles.row}
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Text style={[styles.rowLabel, danger && { color: colors.stateDanger }]}>{label}</Text>
      {right ?? (onPress ? <Text style={styles.chevron}>›</Text> : null)}
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

  const stub = (what: string) =>
    Alert.alert(what, "이 기능은 정식 버전에서 제공됩니다.");

  const confirmLogout = () => {
    Alert.alert("로그아웃", "로그아웃하시겠어요?", [
      { text: "취소", style: "cancel" },
      { text: "로그아웃", style: "destructive", onPress: () => void logout() },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.title}>설정</Text>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg }}
      >
        <View style={styles.profileCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{displayName(user?.email).charAt(0)}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.profileName}>{displayName(user?.email)}님</Text>
            <Text style={styles.profileEmail}>{user?.email ?? "—"}</Text>
          </View>
          <Pressable onPress={() => stub("프로필 수정")} accessibilityRole="button">
            <Text style={styles.editLink}>수정</Text>
          </Pressable>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>개인정보 및 동의</Text>
          <Row
            label="위험 통보 동의"
            right={
              <Switch
                value={riskNotify}
                onValueChange={setRiskNotify}
                trackColor={{ true: colors.stateInfo }}
              />
            }
          />
          <Row
            label="음성 입력 사용 (음성은 민감정보)"
            right={
              <Switch
                value={voiceInput}
                onValueChange={onVoiceToggle}
                disabled={voiceSaving}
                trackColor={{ true: colors.stateInfo }}
              />
            }
          />
          <Row label="약관 · 개인정보 처리방침" onPress={() => stub("약관 보기")} />
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>앱</Text>
          <Row label="온보딩 다시 보기" onPress={() => router.push("/(auth)/onboarding")} />
          <Row
            label="안전 도움말 (1393 · 119)"
            onPress={() => router.push("/(patient)/emergency")}
          />
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionLabel}>계정</Text>
          <Row label="로그아웃" onPress={confirmLogout} danger />
          <Row label="회원 탈퇴 (정식 버전)" onPress={() => stub("회원 탈퇴")} />
        </View>

        <Text style={styles.version}>{APP_VERSION}</Text>
      </ScrollView>

      <BottomTabBar active="settings" />
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { fontSize: fontSize.title, fontWeight: "700", color: colors.textPrimary },
  profileCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surfaceElevated,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontSize: fontSize.title, fontWeight: "700", color: colors.textPrimary },
  profileName: { fontSize: fontSize.bodyLg, fontWeight: "600", color: colors.textPrimary },
  profileEmail: { fontSize: fontSize.body, color: colors.textSecondary, marginTop: 2 },
  editLink: { fontSize: fontSize.body, color: colors.stateInfo, fontWeight: "600" },
  section: { gap: 2 },
  sectionLabel: {
    fontSize: fontSize.caption,
    fontWeight: "700",
    color: colors.textSecondary,
    marginBottom: spacing.xs,
    paddingHorizontal: spacing.xs,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 52,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowLabel: { fontSize: fontSize.bodyLg, color: colors.textPrimary },
  chevron: { fontSize: fontSize.title, color: colors.textSecondary },
  version: {
    fontSize: fontSize.caption,
    color: colors.textSecondary,
    textAlign: "center",
    marginTop: spacing.md,
  },
});
