/**
 * S-03b `/profile-setup` — 가입 직후 인적사항(선택) 입력 (v3 수정 1).
 *
 * 회원가입 폼이 과해서 계정·동의 단계와 분리했다. 여기서는 사회인구학적 항목만
 * 받고, 모두 선택이라 [건너뛰기]로 넘어갈 수 있다. 저장은 PATCH /auth/me/profile.
 * 이 화면에 도달한 시점엔 이미 로그인(accessToken) 상태다.
 */

import { router } from "expo-router";
import { useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { ChipSelect } from "../../components/ChipSelect";
import { Input } from "../../components/Input";
import {
  APIException,
  EducationLevel,
  EmploymentStatus,
  HouseholdType,
  IncomeLevel,
  MaritalStatus,
  ProfileDemographics,
  Religion,
  updateProfileDemographics,
} from "../../lib/api";
import {
  EDUCATION_OPTIONS,
  EMPLOYMENT_OPTIONS,
  HOUSEHOLD_OPTIONS,
  INCOME_OPTIONS,
  MARITAL_OPTIONS,
  RELIGION_OPTIONS,
} from "../../lib/demographics";
import { colors } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

const HOME = "/(patient)/(tabs)/home";

export default function ProfileSetupScreen() {
  const insets = useSafeAreaInsets();
  const accessToken = useAuth((s) => s.accessToken);

  const [marital, setMarital] = useState<MaritalStatus | null>(null);
  const [household, setHousehold] = useState<HouseholdType | null>(null);
  const [education, setEducation] = useState<EducationLevel | null>(null);
  const [occupation, setOccupation] = useState("");
  const [employment, setEmployment] = useState<EmploymentStatus | null>(null);
  const [income, setIncome] = useState<IncomeLevel | null>(null);
  const [religion, setReligion] = useState<Religion | null>(null);
  const [saving, setSaving] = useState(false);

  const goHome = () => router.replace(HOME);

  const onSave = async () => {
    const fields: ProfileDemographics = {
      ...(marital ? { maritalStatus: marital } : {}),
      ...(household ? { householdType: household } : {}),
      ...(education ? { educationLevel: education } : {}),
      ...(occupation.trim() ? { occupation: occupation.trim() } : {}),
      ...(employment ? { employmentStatus: employment } : {}),
      ...(income ? { incomeLevel: income } : {}),
      ...(religion ? { religion } : {}),
    };
    // 아무것도 선택 안 했으면 서버 호출 없이 홈으로.
    if (Object.keys(fields).length === 0 || !accessToken) {
      goHome();
      return;
    }
    setSaving(true);
    try {
      await updateProfileDemographics(accessToken, fields);
      goHome();
    } catch (e) {
      Alert.alert(
        "저장하지 못했어요",
        e instanceof APIException ? e.body.message : "잠시 후 다시 시도하거나 건너뛸 수 있어요.",
      );
    } finally {
      setSaving(false);
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
          <Text style={styles.step}>가입 완료 · 2/2</Text>
          <Text style={styles.title}>인적사항</Text>
          <Text style={styles.sub}>
            진료 맥락 파악에 도움이 돼요. 모두 선택 항목이라 건너뛸 수 있어요.
          </Text>
        </View>

        <ChipSelect label="혼인 상태" options={MARITAL_OPTIONS} value={marital} onChange={setMarital} />
        <ChipSelect label="동거 형태" options={HOUSEHOLD_OPTIONS} value={household} onChange={setHousehold} />
        <ChipSelect label="학력" options={EDUCATION_OPTIONS} value={education} onChange={setEducation} />
        <Input label="직업 (선택)" placeholder="예: 회사원" value={occupation} onChangeText={setOccupation} />
        <ChipSelect label="고용 상태" options={EMPLOYMENT_OPTIONS} value={employment} onChange={setEmployment} />
        <ChipSelect label="소득 수준 (민감·선택)" options={INCOME_OPTIONS} value={income} onChange={setIncome} />
        <ChipSelect label="종교 (민감·선택)" options={RELIGION_OPTIONS} value={religion} onChange={setReligion} />

        <View style={{ height: 8 }} />
        <Button label="완료" onPress={() => void onSave()} loading={saving} />
        <Button label="건너뛰기" variant="ghost" onPress={goHome} disabled={saving} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, gap: 14 },
  head: { marginBottom: 4, gap: 4 },
  step: { fontSize: 11.5, fontWeight: "600", color: colors.muted, letterSpacing: 0.3 },
  title: { fontSize: 24, fontWeight: "700", color: colors.ink, letterSpacing: -0.6 },
  sub: { fontSize: 13, color: colors.muted, lineHeight: 19 },
});
