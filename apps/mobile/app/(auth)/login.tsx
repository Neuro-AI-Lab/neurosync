import { Link, router } from "expo-router";
import { useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { APIException } from "../../lib/api";
import { colors, fontSize, spacing } from "../../lib/tokens";
import { useAuth } from "../../state/auth";

export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const login = useAuth((s) => s.login);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    if (!email || !password) {
      setError("이메일과 비밀번호를 입력해 주세요");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.replace("/(patient)/home");
    } catch (e) {
      if (e instanceof APIException) {
        const code = e.body.code;
        if (code === "INVALID_CREDENTIALS")
          setError("이메일 또는 비밀번호가 일치하지 않아요");
        else if (code === "ROLE_MISMATCH")
          setError("본 앱은 환자 전용이에요. 의료진은 웹 대시보드를 이용해 주세요");
        // PRD §4.5.2: never render raw server message (potential PII).
        else setError(`잠시 후 다시 시도해 주세요 (코드: ${code})`);
      } else {
        Alert.alert("연결 오류", "인터넷 연결이 불안정해요. 잠시 후 다시 시도해 주세요.");
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
          { paddingTop: insets.top + spacing.xxl, paddingBottom: insets.bottom + spacing.lg },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.title}>Neuro-Sync</Text>
        <Text style={styles.subtitle}>환자 로그인</Text>

        <Input
          label="이메일"
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
          autoComplete="email"
          textContentType="emailAddress"
        />
        <Input
          label="비밀번호"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="password"
          textContentType="password"
          passwordRules="minlength: 12; required: lower; required: upper; required: digit; required: special;"
          error={error}
        />

        <Button
          label="로그인"
          onPress={onSubmit}
          loading={submitting}
          disabled={!email || !password}
        />

        <View style={styles.footer}>
          <Text style={styles.footerText}>회원이 아니신가요? </Text>
          <Link href="/(auth)/register" style={styles.link}>
            가입하기
          </Link>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
  },
  title: {
    fontSize: fontSize.display,
    fontWeight: "600",
    color: colors.textPrimary,
  },
  subtitle: {
    fontSize: fontSize.bodyLg,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  footer: {
    flexDirection: "row",
    justifyContent: "center",
    marginTop: spacing.md,
  },
  footerText: {
    fontSize: fontSize.body,
    color: colors.textSecondary,
  },
  link: {
    fontSize: fontSize.body,
    color: colors.stateInfo,
    fontWeight: "600",
  },
});
