/**
 * v3 FR-046/047 — 리포트 상세 (S-12 미니 프리뷰, mock 선구현).
 *
 * 기록 피드에서 항목 탭으로 진입. 표준 문진 점수(환자 본인 응답 기반 — 노출
 * 가능, v3 원칙 1 가드레일)와 Handoff 리포트 미니 프리뷰를 보여준다.
 * AI 추정 질환명·도메인은 어디에도 표시하지 않는다.
 *
 * [전달하기] (FR-047): 실백엔드는 §6-B(보관→전달) 배포 전이므로 실모드에서는
 * 버튼을 비노출한다(PRD §3.2 이중 전달 방지 가드). MOCK 모드에서만 로컬 상태
 * 전이(보관→전달됨)로 플로우를 시연한다.
 */

import * as FileSystem from "expo-file-system/legacy";
import { router, useLocalSearchParams } from "expo-router";
import * as Sharing from "expo-sharing";
import { useEffect, useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../../components/Button";
import { NavBar } from "../../../components/NavBar";
import { TrendChart } from "../../../components/TrendChart";
import {
  APIException,
  deliverReport,
  getReportPdf,
  getReportSummary,
  getReportTrend,
  ReportSummary,
  ReportTrend,
} from "../../../lib/api";
import { MOCK } from "../../../lib/config";
import { SURVEYS } from "../../../lib/surveys";
import { colors } from "../../../lib/tokens";
import { useAuth } from "../../../state/auth";
import { SEVERITY_KO, STATUS_KO, useRecords } from "../../../state/records";
import { useSession } from "../../../state/session";

export default function ReportDetailScreen() {
  const insets = useSafeAreaInsets();
  const { recordId } = useLocalSearchParams<{ recordId?: string }>();
  const record = useRecords((s) => s.records.find((r) => r.id === recordId));
  const markDelivered = useRecords((s) => s.markDelivered);
  const accessToken = useAuth((s) => s.accessToken);
  const storeSessionId = useSession((s) => s.sessionId);
  // 세션 리셋 후에도 상세를 열 수 있도록, 레코드에 실린 sessionId를 우선 사용하고
  // 없으면 현재 세션 스토어 값으로 폴백한다.
  const effectiveSessionId = record?.sessionId ?? storeSessionId;

  // 점수 추이 (수정 7 · F4). 실 API에서 세션 id로 조회한다. mock 모드에서는
  // 가짜 추이를 띄우지 않는다 — 실데이터 연동(§6-A) 후에만 표시한다. 세션 id가
  // 없거나 실패하면 차트를 조용히 숨긴다.
  const [trend, setTrend] = useState<ReportTrend | null>(null);
  // F5 환자용 리포트 요약(자기보고 + 설문). ready 전이면 null.
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  useEffect(() => {
    let alive = true;
    if (MOCK) {
      getReportSummary("", "").then((s) => alive && setSummary(s));
      return () => {
        alive = false;
      };
    }
    if (!accessToken || !effectiveSessionId) return;
    getReportTrend(accessToken, effectiveSessionId)
      .then((t) => alive && setTrend(t))
      .catch(() => alive && setTrend(null));
    getReportSummary(accessToken, effectiveSessionId)
      .then((s) => alive && setSummary(s.ready ? s : null))
      .catch(() => alive && setSummary(null));
    return () => {
      alive = false;
    };
  }, [accessToken, effectiveSessionId]);

  // FR-047 · §6-B — 수동 전달. MOCK은 로컬 상태만 전이, 실모드는 서버에 전달 후
  // 로컬 반영. 실모드는 세션 id가 있어야 전달 대상이 특정된다.
  const [delivering, setDelivering] = useState(false);
  const onDeliver = async () => {
    if (!record) return;
    if (MOCK) {
      markDelivered(record.id);
      return;
    }
    if (!accessToken || !effectiveSessionId) return;
    setDelivering(true);
    try {
      await deliverReport(accessToken, effectiveSessionId);
      markDelivered(record.id);
    } catch (e) {
      Alert.alert(
        "전달하지 못했어요",
        e instanceof APIException ? e.body.message : "잠시 후 다시 시도해 주세요.",
      );
    } finally {
      setDelivering(false);
    }
  };

  // 최종 핸드오프 리포트 PDF 저장·공유. 서버에서 base64 PDF를 받아 임시 파일로
  // 쓰고 OS 공유 시트를 연다(저장/타 앱 전송). PDF 없으면 안내.
  const [savingPdf, setSavingPdf] = useState(false);
  const onSavePdf = async () => {
    if (!accessToken || !effectiveSessionId) return;
    setSavingPdf(true);
    try {
      const { filename, pdfBase64 } = await getReportPdf(accessToken, effectiveSessionId);
      const uri = FileSystem.cacheDirectory + filename;
      await FileSystem.writeAsStringAsync(uri, pdfBase64, {
        encoding: FileSystem.EncodingType.Base64,
      });
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(uri, {
          mimeType: "application/pdf",
          dialogTitle: "핸드오프 리포트 저장",
          UTI: "com.adobe.pdf",
        });
      } else {
        Alert.alert("저장 완료", `리포트를 저장했어요:\n${uri}`);
      }
    } catch (e) {
      Alert.alert(
        "PDF를 준비하지 못했어요",
        e instanceof APIException ? e.body.message : "잠시 후 다시 시도해 주세요.",
      );
    } finally {
      setSavingPdf(false);
    }
  };

  if (!record) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface }}>
        <NavBar title="리포트" backLabel="뒤로" onBack={() => router.back()} />
        <View style={styles.empty}>
          <Text style={styles.emptyText}>기록을 찾을 수 없어요.</Text>
        </View>
      </View>
    );
  }

  const d = new Date(record.completedAt);
  const dateLabel = `${d.getFullYear()} · ${String(d.getMonth() + 1).padStart(2, "0")} · ${String(
    d.getDate(),
  ).padStart(2, "0")}`;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <NavBar title="리포트" backLabel="뒤로" onBack={() => router.back()} />

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
      >
        <View style={styles.top}>
          <View>
            <Text style={styles.title}>사전 문진 리포트</Text>
            <Text style={styles.date}>{dateLabel}</Text>
          </View>
          <View style={styles.pill}>
            <View style={styles.pillDot} />
            <Text style={styles.pillText}>{STATUS_KO[record.status]}</Text>
          </View>
        </View>

        {/* 점수 — 환자 본인 응답 기반이라 노출 가능 (원칙 1 가드레일) */}
        <View style={styles.scoreCard}>
          <Text style={styles.scoreNum}>
            {record.totalScore}
            <Text style={styles.scoreMax}> /{record.maxScore}</Text>
          </Text>
          <Text style={styles.scoreLabel}>
            {SURVEYS[record.instrument].toolLabel} ·{" "}
            {SEVERITY_KO[record.severity] ?? record.severity}
          </Text>
        </View>

        {/* 점수 추이 차트 (수정 7 · F4 plot_data). 비교할 이전 방문이 있을 때만. */}
        {trend && trend.plotData.length >= 2 ? (
          <TrendChart points={trend.plotData} direction={trend.overallDirection} />
        ) : null}

        {/* Handoff 리포트 본문 (F5). 서버 요약(자기보고 + 설문)만 렌더한다 —
            AI 추정질환·신호강도 등 clinician 전용 정보는 서버가 제외한다. */}
        <View style={styles.report}>
          <View style={styles.reportHead}>
            <Text style={styles.reportHeadTitle}>Handoff 리포트</Text>
            <Text style={styles.reportHeadDate}>{dateLabel}</Text>
          </View>

          {summary ? (
            <>
              {(summary.selfReported ?? []).map((row) => (
                <View key={row.key} style={styles.rrow}>
                  <Text style={styles.rk}>{row.label}</Text>
                  <Text style={styles.rv}>{row.value}</Text>
                </View>
              ))}
              {(summary.questionnaires ?? []).length > 0 ? (
                <View style={styles.rrow}>
                  <Text style={styles.rk}>설문 결과</Text>
                  <View style={{ flex: 1 }}>
                    {(summary.questionnaires ?? []).map((q) => (
                      <Text key={q.scale} style={styles.rv}>
                        {q.scale} · {q.totalScore}점 · {q.severityLabel}
                      </Text>
                    ))}
                  </View>
                </View>
              ) : null}
              {summary.disclaimer ? (
                <View style={[styles.rrow, styles.rrowLast]}>
                  <Text style={styles.rv}>{summary.disclaimer}</Text>
                </View>
              ) : null}
            </>
          ) : (
            <View style={[styles.rrow, styles.rrowLast]}>
              <Text style={styles.rv}>리포트 본문을 불러오는 중이에요…</Text>
            </View>
          )}
        </View>

        <Text style={styles.fine}>
          본 리포트는 의료진 참고용이며, 진단이 아닙니다. 전달 전까지 의료진에게 공유되지 않아요.
        </Text>

        {/* 최종 핸드오프 리포트 PDF 저장·공유 */}
        {MOCK || effectiveSessionId ? (
          <Button
            label="리포트 PDF 저장·공유"
            variant="ghost"
            onPress={() => void onSavePdf()}
            loading={savingPdf}
          />
        ) : null}

        <View style={{ flex: 1 }} />

        {/* FR-047 · §6-B — 보관 중인 리포트를 [전달하기]. 실모드는 전달 대상
            세션 id가 있을 때만 노출(과거 이력 실연동은 §6-A 후속). */}
        {record.status === "stored" && (MOCK || effectiveSessionId) ? (
          <Button
            label="의료진에게 전달하기"
            onPress={() => void onDeliver()}
            loading={delivering}
          />
        ) : null}
        {record.status === "delivered" ? (
          <Text style={styles.deliveredNote}>의료진에게 전달됐어요. 진료 때 함께 확인해요.</Text>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, paddingTop: 8, gap: 14, flexGrow: 1 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyText: { fontSize: 14, color: colors.muted },
  top: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  title: { fontSize: 22, fontWeight: "700", color: colors.ink, letterSpacing: -0.5 },
  date: { fontSize: 12, color: colors.muted, marginTop: 4, fontVariant: ["tabular-nums"] },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: 999,
    paddingHorizontal: 11,
    paddingVertical: 5,
  },
  pillDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.ink },
  pillText: { fontSize: 11.5, color: colors.muted },
  scoreCard: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    padding: 16,
  },
  scoreNum: {
    fontSize: 30,
    fontWeight: "500",
    color: colors.ink,
    letterSpacing: -0.9,
    fontVariant: ["tabular-nums"],
  },
  scoreMax: { fontSize: 13, color: colors.faint, fontWeight: "400" },
  scoreLabel: { fontSize: 11.5, color: colors.muted, marginTop: 4 },
  report: { borderWidth: 1, borderColor: colors.line, borderRadius: 16, overflow: "hidden" },
  reportHead: {
    paddingHorizontal: 15,
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
  },
  reportHeadTitle: { fontSize: 13.5, fontWeight: "600", color: colors.ink },
  reportHeadDate: { fontSize: 10.5, color: colors.faint, fontVariant: ["tabular-nums"] },
  rrow: {
    paddingHorizontal: 15,
    paddingVertical: 11,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
  },
  rrowLast: { borderBottomWidth: 0 },
  rk: { fontSize: 11, fontWeight: "600", color: colors.muted },
  rv: { fontSize: 12.5, color: colors.ink, marginTop: 3, lineHeight: 18 },
  fine: { fontSize: 11.5, color: colors.muted, lineHeight: 16 },
  deliveredNote: { textAlign: "center", fontSize: 13, color: colors.muted, paddingVertical: 12 },
});
