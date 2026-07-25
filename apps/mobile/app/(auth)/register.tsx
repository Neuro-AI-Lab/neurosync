import { router } from "expo-router";
import { useState } from "react";
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
import {
  APIException,
  EducationLevel,
  EmploymentStatus,
  HouseholdType,
  IncomeLevel,
  MaritalStatus,
  Religion,
} from "../../lib/api";
import {
  EDUCATION_OPTIONS,
  EMPLOYMENT_OPTIONS,
  HOUSEHOLD_OPTIONS,
  INCOME_OPTIONS,
  MARITAL_OPTIONS,
  Option,
  RELIGION_OPTIONS,
} from "../../lib/demographics";
import { Check, ChevronRight } from "../../lib/icons";
import { colors } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

/**
 * Single-screen register — screen-spec §S-03 compresses profile + consent into
 * one for the Phase 1a demo. Consent is presented as the iOS "전체 동의" box over
 * a grouped checkbox list (필수 / 선택), matching the design mock.
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

  // v3 수정 1 — 확장 인적사항 (모두 선택, 기본 미선택).
  const [marital, setMarital] = useState<MaritalStatus | null>(null);
  const [household, setHousehold] = useState<HouseholdType | null>(null);
  const [education, setEducation] = useState<EducationLevel | null>(null);
  const [occupation, setOccupation] = useState("");
  const [employment, setEmployment] = useState<EmploymentStatus | null>(null);
  const [income, setIncome] = useState<IncomeLevel | null>(null);
  const [religion, setReligion] = useState<Religion | null>(null);

  const [tos, setTos] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [sensitive, setSensitive] = useState(false);
  // PRD §4.5.2 + FR-026 — risk_notification is OPT-IN per PIPA doctrine.
  const [riskNotification, setRiskNotification] = useState(false);
  // FR-034 — voice (STT) is sensitive (biometric); separate opt-in, default off.
  const [voiceConsent, setVoiceConsent] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allOn = tos && privacy && sensitive && riskNotification && voiceConsent;
  const setAll = (v: boolean) => {
    setTos(v);
    setPrivacy(v);
    setSensitive(v);
    setRiskNotification(v);
    setVoiceConsent(v);
  };

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
        // 확장 인적사항 — 선택한 것만 전송(null/빈값은 생략).
        ...(marital ? { maritalStatus: marital } : {}),
        ...(household ? { householdType: household } : {}),
        ...(education ? { educationLevel: education } : {}),
        ...(occupation.trim() ? { occupation: occupation.trim() } : {}),
        ...(employment ? { employmentStatus: employment } : {}),
        ...(income ? { incomeLevel: income } : {}),
        ...(religion ? { religion } : {}),
        consents: { tos, privacy, sensitive, riskNotification, voice: voiceConsent },
      });
      router.replace("/(patient)/(tabs)/home");
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
          <Text style={styles.title}>회원가입</Text>
          <Text style={styles.sub}>민감한 의료 정보를 다루기에 항목을 나눴어요.</Text>
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

        {/* v3 수정 1 — 확장 인적사항 (선택). 진료 맥락 파악에 쓰이며 미입력 가능. */}
        <Text style={styles.sectionLabel}>추가 인적사항 (선택)</Text>
        <Text style={styles.sectionHint}>
          진료 맥락 파악에 도움이 돼요. 입력하지 않아도 가입할 수 있어요.
        </Text>
        <ChipSelect label="혼인 상태" options={MARITAL_OPTIONS} value={marital} onChange={setMarital} />
        <ChipSelect label="동거 형태" options={HOUSEHOLD_OPTIONS} value={household} onChange={setHousehold} />
        <ChipSelect label="학력" options={EDUCATION_OPTIONS} value={education} onChange={setEducation} />
        <Input label="직업 (선택)" placeholder="예: 회사원" value={occupation} onChangeText={setOccupation} />
        <ChipSelect label="고용 상태" options={EMPLOYMENT_OPTIONS} value={employment} onChange={setEmployment} />
        <ChipSelect label="소득 수준 (민감·선택)" options={INCOME_OPTIONS} value={income} onChange={setIncome} />
        <ChipSelect label="종교 (민감·선택)" options={RELIGION_OPTIONS} value={religion} onChange={setReligion} />

        {/* Consent — 전체 동의 + grouped checkbox list */}
        <Text style={styles.sectionLabel}>약관 동의</Text>
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

        {error ? (
          <View style={styles.errBox}>
            <Text style={styles.errText}>{error}</Text>
          </View>
        ) : null}

        <View style={{ height: 4 }} />
        <Button label="동의하고 계속" onPress={onSubmit} loading={submitting} disabled={!canSubmit} />

        <Pressable
          style={styles.footer}
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/(auth)/login"))}
          accessibilityRole="button"
        >
          <Text style={styles.footerText}>이미 회원이신가요? </Text>
          <Text style={styles.footerLink}>로그인</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function ChipSelect<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Option<T>[];
  value: T | null;
  onChange: (v: T | null) => void;
}) {
  return (
    <View style={styles.selectWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.wrapChips}>
        {options.map((opt) => {
          const on = value === opt.code;
          return (
            <Pressable
              key={opt.code}
              // 다시 누르면 선택 해제 — 선택 항목이므로 되돌릴 수 있어야 한다.
              onPress={() => onChange(on ? null : opt.code)}
              style={[styles.wchip, on && styles.chipOn]}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
            >
              <Text style={[styles.wchipText, on && styles.chipTextOn]}>{opt.label}</Text>
            </Pressable>
          );
        })}
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
  scroll: { paddingHorizontal: 20, gap: 12 },
  head: { marginBottom: 4, gap: 4 },
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
  sectionLabel: { fontSize: 12.5, fontWeight: "600", color: colors.muted, marginTop: 12, paddingLeft: 2 },
  sectionHint: { fontSize: 11.5, color: colors.faint, paddingLeft: 2, marginTop: -6, lineHeight: 16 },
  selectWrap: { gap: 7 },
  wrapChips: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  wchip: {
    paddingHorizontal: 13,
    height: 38,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  wchipText: { fontSize: 13.5, color: colors.ink },
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
  footerLink: { fontSize: 14, color: colors.ink, fontWeight: "600" },
});
