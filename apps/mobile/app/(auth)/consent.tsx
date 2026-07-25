/**
 * S-03a `/consent` — 회원가입 1단계: 약관 동의 (v3, 동의 먼저).
 *
 * 민감정보(건강정보)는 PIPA상 '수집·이용 전 동의'가 원칙이라, 개인정보 입력보다
 * 먼저 동의를 받는다. 동의 상태는 라우트 params로 다음 단계(register)에 전달한다.
 * 흐름: consent → register(계정·프로필) → profile-setup(인적사항, 선택).
 */

import { router } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { Check, ChevronRight } from "../../lib/icons";
import { colors } from "../../lib/tokens";

export default function ConsentScreen() {
  const insets = useSafeAreaInsets();

  const [tos, setTos] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [sensitive, setSensitive] = useState(false);
  // PRD §4.5.2 + FR-026 — risk_notification은 PIPA상 옵트인.
  const [riskNotification, setRiskNotification] = useState(false);
  // FR-034 — 음성(STT)은 민감(생체) 정보라 별도 옵트인, 기본 off.
  const [voiceConsent, setVoiceConsent] = useState(false);

  const allOn = tos && privacy && sensitive && riskNotification && voiceConsent;
  const setAll = (v: boolean) => {
    setTos(v);
    setPrivacy(v);
    setSensitive(v);
    setRiskNotification(v);
    setVoiceConsent(v);
  };

  const canProceed = tos && privacy && sensitive;

  const onNext = () => {
    router.push({
      pathname: "/(auth)/register",
      params: {
        tos: tos ? "1" : "0",
        privacy: privacy ? "1" : "0",
        sensitive: sensitive ? "1" : "0",
        risk: riskNotification ? "1" : "0",
        voice: voiceConsent ? "1" : "0",
      },
    });
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 16 },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.head}>
          <Text style={styles.step}>회원가입 · 1/3</Text>
          <Text style={styles.title}>약관 동의</Text>
          <Text style={styles.sub}>
            건강 정보를 다루기 때문에, 개인정보를 입력하기 전에 먼저 동의를 받아요.
          </Text>
        </View>

        <Pressable
          style={styles.agreeAll}
          onPress={() => setAll(!allOn)}
          accessibilityRole="checkbox"
          accessibilityState={{ checked: allOn }}
        >
          <Checkbox on={allOn} size={26} />
          <View style={{ flex: 1 }}>
            <Text style={styles.agreeAllTitle}>전체 동의합니다</Text>
            <Text style={styles.agreeAllSub}>필수·선택 항목을 모두 포함해요</Text>
          </View>
        </Pressable>

        <View style={styles.clist}>
          <ConsentRow label="서비스 이용약관" required on={tos} onToggle={() => setTos(!tos)} />
          <ConsentRow label="개인정보 처리방침" required on={privacy} onToggle={() => setPrivacy(!privacy)} />
          <ConsentRow label="민감정보(의료) 수집·이용" required on={sensitive} onToggle={() => setSensitive(!sensitive)} />
          <ConsentRow label="위험 감지 시 비상 연락" on={riskNotification} onToggle={() => setRiskNotification(!riskNotification)} />
          <ConsentRow label="음성 입력(STT) 사용" on={voiceConsent} onToggle={() => setVoiceConsent(!voiceConsent)} />
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        <Button label="동의하고 계속" onPress={onNext} disabled={!canProceed} />
        <Pressable
          style={styles.loginLink}
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/(auth)/login"))}
          accessibilityRole="button"
        >
          <Text style={styles.loginText}>이미 회원이신가요? </Text>
          <Text style={styles.loginStrong}>로그인</Text>
        </Pressable>
      </View>
    </View>
  );
}

function Checkbox({ on, size = 24 }: { on: boolean; size?: number }) {
  return (
    <View
      style={[
        styles.check,
        { width: size, height: size, borderRadius: size / 2 },
        on && styles.checkOn,
      ]}
    >
      {on ? <Check size={size - 10} color={colors.onInk} /> : null}
    </View>
  );
}

function ConsentRow({
  label,
  required,
  on,
  onToggle,
}: {
  label: string;
  required?: boolean;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <Pressable
      style={styles.citem}
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: on }}
    >
      <Checkbox on={on} />
      <Text style={styles.citemLabel} numberOfLines={1}>
        {label}
      </Text>
      <Text style={[styles.citemTag, required && styles.citemTagReq]}>
        {required ? "필수" : "선택"}
      </Text>
      <ChevronRight size={13} color={colors.faint} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, gap: 14 },
  head: { marginBottom: 4, gap: 4 },
  step: { fontSize: 11.5, fontWeight: "600", color: colors.muted, letterSpacing: 0.3 },
  title: { fontSize: 24, fontWeight: "700", color: colors.ink, letterSpacing: -0.6 },
  sub: { fontSize: 13, color: colors.muted, lineHeight: 19 },
  agreeAll: {
    flexDirection: "row",
    alignItems: "center",
    gap: 13,
    padding: 15,
    borderWidth: 1.5,
    borderColor: colors.ink,
    borderRadius: 14,
  },
  agreeAllTitle: { fontSize: 15, fontWeight: "600", color: colors.ink },
  agreeAllSub: { fontSize: 11.5, color: colors.muted, marginTop: 2 },
  clist: { paddingHorizontal: 4 },
  citem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    height: 50,
    paddingHorizontal: 6,
    borderBottomWidth: 1,
    borderBottomColor: colors.sep,
  },
  citemLabel: { flex: 1, fontSize: 14, color: colors.ink },
  citemTag: { fontSize: 11, color: colors.muted },
  citemTagReq: { color: colors.ink2, fontWeight: "500" },
  check: {
    borderWidth: 2,
    borderColor: colors.lineStrong,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  checkOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  footer: {
    paddingHorizontal: 20,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
    gap: 4,
  },
  loginLink: { flexDirection: "row", justifyContent: "center", marginTop: 6 },
  loginText: { fontSize: 14, color: colors.muted },
  loginStrong: { fontSize: 14, color: colors.ink, fontWeight: "600" },
});
