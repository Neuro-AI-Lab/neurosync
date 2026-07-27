/**
 * v3 FR-048 — OCR 결과 확인 화면.
 *
 * 대화에서 첨부한 처방전/진단서를 업로드→인식하고, 추출 결과를 카드로 보여준다.
 * 저신뢰 항목("확인 필요")은 빨간 배지로 표시한다. [확인 완료]를 누르면 확정 요약을
 * 대화로 흘려보내(FR-048) F1이 인지·응답하고 conversation_history(→리포트)에 남는다.
 */

import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../../components/Button";
import { NavBar } from "../../../components/NavBar";
import { APIException, OCRResult, parseDocument } from "../../../lib/api";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { useSession } from "../../../state/session";

const DOC_LABEL: Record<string, string> = {
  prescription: "처방전",
  diagnosis: "진단서",
  medical_record: "진료기록",
  consultation: "상담기록",
  lab_result: "검사결과",
  unknown: "문서",
};

/**
 * 확정된 OCR 요약을 대화용 한국어 한 문장으로 조립한다(FR-048). 사용자 말풍선으로
 * 전송돼 F1이 복용약/진단을 인지하고 후속 질문에 활용한다. 추출값이 전혀 없으면
 * null → 주입을 건너뛴다(빈 첨부 안내 방지).
 */
function buildInjection(r: OCRResult): string | null {
  const s = r.extractedSummary;
  const docLabel = DOC_LABEL[r.documentType] ?? "문서";
  const parts: string[] = [];
  if (s.diagnoses.length > 0) parts.push(`진단은 ${s.diagnoses.join(", ")}`);
  if (s.medications.length > 0) {
    const meds = s.medications
      .map((m) => [m.name, m.dose, m.frequency].filter(Boolean).join(" "))
      .filter(Boolean)
      .join(", ");
    if (meds) parts.push(`처방약은 ${meds}`);
  }
  if (s.department) parts.push(`진료과는 ${s.department}`);
  if (parts.length === 0) return null;
  return `${docLabel}을 첨부했어요. ${parts.join(", ")}예요.`;
}

type Phase = "loading" | "ready" | "error";

export default function OcrConfirmScreen() {
  const insets = useSafeAreaInsets();
  const { uri, name, mime } = useLocalSearchParams<{ uri: string; name: string; mime: string }>();
  const accessToken = useAuth((s) => s.accessToken);
  const sessionId = useSession((s) => s.sessionId);
  const setPendingInjection = useSession((s) => s.setPendingInjection);

  const [phase, setPhase] = useState<Phase>("loading");
  const [result, setResult] = useState<OCRResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!accessToken || !sessionId || !uri) {
        setPhase("error");
        setErrorMsg("세션 정보를 찾을 수 없어요.");
        return;
      }
      try {
        const r = await parseDocument(accessToken, sessionId, {
          uri,
          name: name ?? "document.jpg",
          mime: mime ?? "image/jpeg",
        });
        if (!alive) return;
        setResult(r);
        setPhase("ready");
      } catch (e) {
        if (!alive) return;
        setErrorMsg(
          e instanceof APIException ? e.body.message : "문서 인식에 실패했어요.",
        );
        setPhase("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [accessToken, sessionId, uri, name, mime]);

  // 저신뢰 필드 빠른 조회용 (field 문자열 매칭).
  const flagged = new Set((result?.lowConfidenceItems ?? []).map((i) => i.field));
  const isFlagged = (field: string) => flagged.has(field);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <NavBar title="문서 확인" backLabel="취소" onBack={() => router.back()} />

      {phase === "loading" ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.ink} />
          <Text style={styles.centerText}>문서를 인식하고 있어요…</Text>
        </View>
      ) : null}

      {phase === "error" ? (
        <View style={styles.center}>
          <Text style={styles.errTitle}>인식에 실패했어요</Text>
          <Text style={styles.errText}>{errorMsg}</Text>
          <View style={{ height: 12 }} />
          <Button label="대화로 돌아가기" variant="ghost" onPress={() => router.back()} />
        </View>
      ) : null}

      {phase === "ready" && result ? (
        <>
          <ScrollView
            style={{ flex: 1 }}
            contentContainerStyle={styles.scroll}
            showsVerticalScrollIndicator={false}
          >
            <View style={styles.head}>
              <Text style={styles.docType}>
                {DOC_LABEL[result.documentType] ?? "문서"}로 인식했어요
              </Text>
              <Text style={styles.headSub}>
                내용을 확인해 주세요. 빨간 표시는 인식이 불확실한 항목이에요.
              </Text>
            </View>

            {result.lowConfidenceItems.length > 0 ? (
              <View style={styles.warnBanner}>
                <View style={styles.warnDot} />
                <Text style={styles.warnText}>
                  확인이 필요한 항목 {result.lowConfidenceItems.length}개가 있어요.
                </Text>
              </View>
            ) : null}

            {/* 진단명 */}
            {result.extractedSummary.diagnoses.length > 0 ? (
              <Section title="진단명">
                {result.extractedSummary.diagnoses.map((d, i) => (
                  <Row key={i} value={d} flag={isFlagged(`diagnoses[${i}]`)} />
                ))}
              </Section>
            ) : null}

            {/* 약물 */}
            {result.extractedSummary.medications.length > 0 ? (
              <Section title="처방 약물">
                {result.extractedSummary.medications.map((m, i) => (
                  <Row
                    key={i}
                    value={[m.name, m.dose, m.frequency].filter(Boolean).join(" · ")}
                    flag={isFlagged(`medications[${i}].dose`) || isFlagged(`medications[${i}]`)}
                  />
                ))}
              </Section>
            ) : null}

            {/* 진료과 · 날짜 */}
            {result.extractedSummary.department ? (
              <Section title="진료과">
                <Row value={result.extractedSummary.department} flag={isFlagged("department")} />
              </Section>
            ) : null}
            {result.extractedSummary.dates.length > 0 ? (
              <Section title="날짜">
                {result.extractedSummary.dates.map((d, i) => (
                  <Row key={i} value={d} flag={isFlagged(`dates[${i}]`)} />
                ))}
              </Section>
            ) : null}

            <Text style={styles.fine}>
              확인한 내용은 대화에 반영되고 사전 문진 리포트에 참고 자료로 담겨요.
            </Text>
          </ScrollView>

          <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 16) }]}>
            <Button
              label="확인 완료"
              onPress={() => {
                const summary = buildInjection(result);
                if (summary) setPendingInjection(summary);
                router.back();
              }}
            />
          </View>
        </>
      ) : null}
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.card}>{children}</View>
    </View>
  );
}

function Row({ value, flag }: { value: string; flag?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowValue}>{value}</Text>
      {flag ? (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>확인 필요</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 10, padding: 32 },
  centerText: { fontSize: 13, color: colors.muted },
  errTitle: { fontSize: 17, fontWeight: "700", color: colors.ink },
  errText: { fontSize: 13.5, color: colors.muted, textAlign: "center", lineHeight: 20 },
  scroll: { padding: 20, gap: 16 },
  head: { gap: 6 },
  docType: { fontSize: 22, fontWeight: "700", color: colors.ink, letterSpacing: -0.5 },
  headSub: { fontSize: 13.5, color: colors.muted, lineHeight: 20 },
  warnBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    padding: 13,
    borderRadius: 12,
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: colors.dangerLine,
  },
  warnDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.danger },
  warnText: { fontSize: 13, color: colors.dangerInk, fontWeight: "500" },
  section: { gap: 8 },
  sectionTitle: {
    fontSize: 11.5,
    fontWeight: "600",
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    paddingLeft: 2,
  },
  card: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    overflow: "hidden",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    paddingHorizontal: 15,
    paddingVertical: 13,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.line,
  },
  rowValue: { flex: 1, fontSize: 14.5, color: colors.ink, lineHeight: 20 },
  badge: {
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 4,
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: colors.dangerLine,
  },
  badgeText: { fontSize: 11, fontWeight: "600", color: colors.dangerInk },
  fine: { fontSize: 11.5, color: colors.faint, lineHeight: 16, marginTop: 4 },
  footer: {
    paddingHorizontal: 20,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
  },
});
