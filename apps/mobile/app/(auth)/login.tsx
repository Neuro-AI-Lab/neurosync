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
import { APIException } from "../../lib/api";
import { Shield } from "../../lib/icons";
import { colors } from "../../lib/tokens";
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
      router.replace("/(patient)/(tabs)/home");
    } catch (e) {
      if (e instanceof APIException) {
        const code = e.body.code;
        if (code === "INVALID_CREDENTIALS")
          setError("이메일 또는 비밀번호가 일치하지 않아요");
        else if (code === "ROLE_MISMATCH")
          setError("본 앱은 환자 전용이에요. 의료진은 웹 대시보드를 이용해 주세요");
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
          { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 20 },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.head}>
          <Text style={styles.title}>로그인</Text>
          <Text style={styles.sub}>등록하신 이메일로 계속해요.</Text>
        </View>

        <Input
          label="이메일"
          placeholder="you@example.com"
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
          autoComplete="email"
          textContentType="emailAddress"
        />
        <Input
          label="비밀번호"
          placeholder="••••••••••"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="password"
          textContentType="password"
          error={error}
        />

        <View style={{ height: 8 }} />
        <Button label="로그인" onPress={onSubmit} loading={submitting} disabled={!email || !password} />

        <View style={styles.trust}>
          <Shield size={13} color={colors.muted} />
          <Text style={styles.trustText}>의료 정보는 암호화되어 안전하게 보관돼요</Text>
        </View>

        <Pressable
          style={styles.regRow}
          onPress={() => router.push("/(auth)/register")}
          accessibilityRole="button"
        >
          <Text style={styles.regText}>처음이신가요? </Text>
          <Text style={styles.regLink}>회원가입</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, gap: 14 },
  head: { marginBottom: 6, gap: 4 },
  title: { fontSize: 24, fontWeight: "700", color: colors.ink, letterSpacing: -0.6 },
  sub: { fontSize: 13.5, color: colors.muted },
  trust: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    marginTop: 4,
  },
  trustText: { fontSize: 11.5, color: colors.muted },
  regRow: { flexDirection: "row", justifyContent: "center", marginTop: 8 },
  regText: { fontSize: 14, color: colors.muted },
  regLink: { fontSize: 14, color: colors.ink, fontWeight: "600" },
});
