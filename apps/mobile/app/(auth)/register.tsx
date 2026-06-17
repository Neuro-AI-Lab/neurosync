import { Link, router } from "expo-router";
import { useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { APIException } from "../../lib/api";
import { colors, fontSize, spacing } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

/**
 * Single-screen register — screen-spec §S-03 compresses 3 steps into one for
 * the Phase 1a demo. Production version restores the stepper.
 */
export default function RegisterScreen() {
  const insets = useSafeAreaInsets();
  const register = useAuth((s) => s.register);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [birthYear, setBirthYear] = useState("");
  const [phone, setPhone] = useState("");
  const [emergency, setEmergency] = useState("");
  const [region, setRegion] = useState("서울 강남구");
  const [gender, setGender] = useState<"male" | "female" | "other">("male");

  const [tos, setTos] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [sensitive, setSensitive] = useState(false);
  // PRD §4.5.2 + FR-026 — risk_notification is OPT-IN per PIPA doctrine.
  // Default = false; toggling off is itself a consent decision.
  const [riskNotification, setRiskNotification] = useState(false);
  // FR-034 — voice (STT) is sensitive (biometric); separate opt-in, default off.
  const [voiceConsent, setVoiceConsent] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isFilled = (s: string) => s.trim().length > 0;
  const canSubmit =
    tos &&
    privacy &&
    sensitive &&
    isFilled(email) &&
    isFilled(password) &&
    isFilled(name) &&
    isFilled(birthYear) &&
    isFilled(phone) &&
    isFilled(emergency);

  const onSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await register({
        email: email.trim(),
        password,
        name: name.trim(),
        birthYear: Number(birthYear),
        gender,
        phone: phone.trim(),
        region: region.trim(),
        emergencyContact: emergency.trim(),
        consents: { tos, privacy, sensitive, riskNotification, voice: voiceConsent },
      });
      router.replace("/(patient)/home");
    } catch (e) {
      if (e instanceof APIException) {
        const c = e.body.code;
        if (c === "WEAK_PASSWORD") setError("비밀번호 정책: 12자 이상 + 대/소문자 + 숫자 + 특수문자");
        else if (c === "EMAIL_EXISTS") setError("이미 가입된 이메일이에요");
        else if (c === "CONSENT_REQUIRED") setError("필수 동의를 확인해 주세요");
        else if (c === "INVALID_INPUT") setError("입력 내용을 다시 확인해 주세요");
        // PRD §4.5.2: 서버 응답 message는 잠재 PII 포함 가능 — 코드만 노출
        else setError(`잠시 후 다시 시도해 주세요 (코드: ${c})`);
      } else {
        Alert.alert("연결 오류", "인터넷 연결이 불안정해요");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.lg },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.title}>회원가입</Text>

        <Input label="이메일" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
        <Input label="비밀번호 (12자 이상)" value={password} onChangeText={setPassword} secureTextEntry />
        <Input label="이름" value={name} onChangeText={setName} />
        <Input label="출생연도 (예: 1995)" value={birthYear} onChangeText={setBirthYear} keyboardType="number-pad" />
        <Input label="연락처 (010-...)" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
        <Input label="비상 연락처 (010-...)" value={emergency} onChangeText={setEmergency} keyboardType="phone-pad" />
        <Input label="거주 지역" value={region} onChangeText={setRegion} />

        <Text style={styles.sectionLabel}>성별</Text>
        <View style={styles.row}>
          {(["female", "male", "other"] as const).map((g) => (
            <Pressable
              key={g}
              onPress={() => setGender(g)}
              style={[styles.chip, gender === g && styles.chipActive]}
              accessibilityRole="radio"
              accessibilityState={{ selected: gender === g }}
            >
              <Text style={[styles.chipText, gender === g && styles.chipTextActive]}>
                {g === "female" ? "여성" : g === "male" ? "남성" : "그 외"}
              </Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.sectionLabel}>동의</Text>
        <Toggle label="[필수] 서비스 이용약관" value={tos} onChange={setTos} />
        <Toggle label="[필수] 개인정보 처리방침" value={privacy} onChange={setPrivacy} />
        <Toggle label="[필수] 민감정보(의료) 수집" value={sensitive} onChange={setSensitive} />
        <Toggle
          label="[선택] 위험 신호 감지 시 비상 연락처에 안내 (옵트아웃 시 본인에게만 표시)"
          value={riskNotification}
          onChange={setRiskNotification}
        />
        <Toggle
          label="[선택] 음성 입력(STT) 사용 — 음성은 민감정보로 별도 동의 (설정에서 변경 가능)"
          value={voiceConsent}
          onChange={setVoiceConsent}
        />

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Button label="가입 완료" onPress={onSubmit} loading={submitting} disabled={!canSubmit} />

        <View style={styles.footer}>
          <Text style={styles.footerText}>이미 회원이신가요? </Text>
          <Link href="/(auth)/login" style={styles.link}>
            로그인
          </Link>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <Pressable
      onPress={() => onChange(!value)}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: value }}
      style={styles.toggle}
    >
      <Text style={[styles.toggleBox, value && styles.toggleBoxOn]}>{value ? "✓" : ""}</Text>
      <Text style={styles.toggleLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: spacing.lg, gap: spacing.md },
  title: { fontSize: fontSize.display, fontWeight: "600", color: colors.textPrimary, marginBottom: spacing.sm },
  sectionLabel: { fontSize: fontSize.body, fontWeight: "500", color: colors.textPrimary, marginTop: spacing.md },
  row: { flexDirection: "row", gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
  },
  chipActive: { backgroundColor: colors.textPrimary, borderColor: colors.textPrimary },
  chipText: { fontSize: fontSize.body, color: colors.textPrimary },
  chipTextActive: { color: colors.surface, fontWeight: "600" },
  toggle: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs },
  toggleBox: {
    width: 24,
    height: 24,
    textAlign: "center",
    lineHeight: 24,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.surface,
    backgroundColor: colors.surface,
    overflow: "hidden",
  },
  toggleBoxOn: { backgroundColor: colors.textPrimary, borderColor: colors.textPrimary, color: colors.surface },
  toggleLabel: { fontSize: fontSize.body, color: colors.textPrimary, flex: 1 },
  error: {
    fontSize: fontSize.body,
    color: colors.stateDanger,
    backgroundColor: "#FEF2F2",
    padding: spacing.sm,
    borderRadius: 8,
  },
  footer: { flexDirection: "row", justifyContent: "center", marginTop: spacing.md },
  footerText: { fontSize: fontSize.body, color: colors.textSecondary },
  link: { fontSize: fontSize.body, color: colors.stateInfo, fontWeight: "600" },
});
