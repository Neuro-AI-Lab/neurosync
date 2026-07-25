import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { APIException } from "../../lib/api";
import { colors } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

/**
 * S-03 register — 2단계: 계정 + 필수 프로필. 약관 동의는 1단계(/consent)에서
 * 이미 받아 params로 넘어온다(민감정보는 수집 전 동의, PIPA). 인적사항(선택)은
 * 3단계(/profile-setup). 가입 성공 시 profile-setup으로 이동한다.
 */
export default function RegisterScreen() {
  const insets = useSafeAreaInsets();
  const register = useAuth((s) => s.register);

  // 1단계 동의 결과(params). 필수 3종이 없으면 동의 화면으로 되돌린다.
  const p = useLocalSearchParams<{
    tos?: string;
    privacy?: string;
    sensitive?: string;
    risk?: string;
    voice?: string;
  }>();
  const consents = {
    tos: p.tos === "1",
    privacy: p.privacy === "1",
    sensitive: p.sensitive === "1",
    riskNotification: p.risk === "1",
    voice: p.voice === "1",
  };
  useEffect(() => {
    if (!(consents.tos && consents.privacy && consents.sensitive)) {
      router.replace("/(auth)/consent");
    }
    // 최초 마운트 시 params 검증만. consents는 params 파생이라 안정적.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [birthYear, setBirthYear] = useState("");
  const [phone, setPhone] = useState("");
  const [emergency, setEmergency] = useState("");
  const [region, setRegion] = useState("서울 강남구");
  const [gender, setGender] = useState<"male" | "female" | "other">("male");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isFilled = (s: string) => s.trim().length > 0;
  const canSubmit =
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
        consents,
      });
      // 가입 완료 → 2단계 인적사항(선택) 화면으로. 홈이 아니다.
      router.replace("/(auth)/profile-setup");
    } catch (e) {
      if (e instanceof APIException) {
        const c = e.body.code;
        if (c === "WEAK_PASSWORD") setError("비밀번호 정책: 12자 이상 + 대/소문자 + 숫자 + 특수문자");
        else if (c === "EMAIL_EXISTS") setError("이미 가입된 이메일이에요");
        else if (c === "CONSENT_REQUIRED") setError("필수 동의를 확인해 주세요");
        else if (c === "INVALID_INPUT") setError("입력 내용을 다시 확인해 주세요");
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
          { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.head}>
          <Text style={styles.step}>회원가입 · 2/3</Text>
          <Text style={styles.title}>계정 · 기본 정보</Text>
          <Text style={styles.sub}>진료 연계에 필요한 최소한의 정보만 받아요.</Text>
        </View>

        <Input label="이메일" placeholder="you@example.com" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
        <Input label="비밀번호 (12자 이상)" placeholder="••••••••••" value={password} onChangeText={setPassword} secureTextEntry />
        <Input label="이름" value={name} onChangeText={setName} />
        <Input label="출생연도" placeholder="예: 1995" value={birthYear} onChangeText={setBirthYear} keyboardType="number-pad" />
        <Input label="연락처" placeholder="010-0000-0000" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
        <Input label="비상 연락처" placeholder="010-0000-0000" value={emergency} onChangeText={setEmergency} keyboardType="phone-pad" />
        <Input label="거주 지역" value={region} onChangeText={setRegion} />

        <View style={styles.genderWrap}>
          <Text style={styles.fieldLabel}>성별</Text>
          <View style={styles.chipRow}>
            {(["female", "male", "other"] as const).map((g) => {
              const on = gender === g;
              return (
                <Pressable
                  key={g}
                  onPress={() => setGender(g)}
                  style={[styles.chip, on && styles.chipOn]}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: on }}
                >
                  <Text style={[styles.chipText, on && styles.chipTextOn]}>
                    {g === "female" ? "여성" : g === "male" ? "남성" : "그 외"}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        {error ? (
          <View style={styles.errBox}>
            <Text style={styles.errText}>{error}</Text>
          </View>
        ) : null}

        <View style={{ height: 4 }} />
        <Button label="가입하고 계속" onPress={onSubmit} loading={submitting} disabled={!canSubmit} />

        <Pressable
          style={styles.footer}
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/(auth)/login"))}
          accessibilityRole="button"
        >
          <Text style={styles.footerText}>← 약관 동의로 돌아가기</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, gap: 12 },
  head: { marginBottom: 4, gap: 4 },
  step: { fontSize: 11.5, fontWeight: "600", color: colors.muted, letterSpacing: 0.3 },
  title: { fontSize: 24, fontWeight: "700", color: colors.ink, letterSpacing: -0.6 },
  sub: { fontSize: 13, color: colors.muted },
  fieldLabel: { fontSize: 12.5, fontWeight: "500", color: colors.muted, paddingLeft: 2 },
  genderWrap: { gap: 6 },
  chipRow: { flexDirection: "row", gap: 8 },
  chip: {
    flex: 1,
    height: 44,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  chipOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  chipText: { fontSize: 14, color: colors.ink },
  chipTextOn: { color: colors.onInk, fontWeight: "600" },
  errBox: {
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: colors.dangerLine,
    borderRadius: 12,
    padding: 12,
  },
  errText: { fontSize: 13, color: colors.dangerInk },
  footer: { flexDirection: "row", justifyContent: "center", marginTop: 10 },
  footerText: { fontSize: 14, color: colors.muted },
});
