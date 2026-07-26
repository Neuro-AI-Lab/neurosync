/**
 * 문항 주입형 공통 문진 폼 (v3 FR-040) — 한 문항 집중 방식.
 *
 * SurveyDef(문항·선택지·위험 문항 index)를 주입받아 PHQ-9/GAD-7/AUDIT-C/PHQ-4를
 * 동일 컴포넌트로 렌더한다. 헤더에는 도구명만 표시하고(질환명 금지, v3 원칙 1),
 * "AI 추정은 참고용" 고지를 서브텍스트로 둔다.
 *
 * 진행 표시(문항 번호 + 진행 바)는 매핑된 설문지 안의 실제 문항 인덱스
 * (index+1 / items.length, 예: "문항 3/9") 기준 — 고정 문진 단계 수(과거
 * "문진 1/1")는 매핑형 설문 전달 구조와 불일치해 폐지.
 *
 * FR-043: riskItemIndex 문항에 양성(>0) 응답 시 인라인 위험 확인 카드를 띄운다.
 * 응답 값은 그대로 유지(점수 계산 보존), 설문은 중단되지 않는다.
 * [도움 받기] → /emergency · [괜찮아요] → 다음 문항.
 */

import { router } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { SurveyDef } from "../lib/surveys";
import { colors } from "../lib/tokens";
import { Button } from "./Button";
import { NavBar } from "./NavBar";
import { RiskConfirmCard } from "./RiskConfirm";

type Props = {
  def: SurveyDef;
  submitLabel: string;
  submitting: boolean;
  onSubmit: (answers: number[]) => void;
};

export function QuestionnaireForm({
  def,
  submitLabel,
  submitting,
  onSubmit,
}: Props) {
  const { items } = def;
  const [answers, setAnswers] = useState<(number | null)[]>(() => items.map(() => null));
  const [index, setIndex] = useState(0);
  const [riskCard, setRiskCard] = useState(false);

  const answeredCount = useMemo(() => answers.filter((a) => a !== null).length, [answers]);
  const allAnswered = answeredCount === items.length;
  const isLast = index === items.length - 1;
  const current = answers[index] ?? null;
  const item = items[index];
  const options = item?.options ?? def.defaultOptions;

  const select = (value: number) => {
    setAnswers((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
    // FR-043 — 위험 문항 양성 응답 시 확인 카드. 값은 이미 저장됨(중단 없음).
    if (index === def.riskItemIndex) {
      setRiskCard(value > 0);
    }
  };

  const goPrev = () => {
    setRiskCard(false);
    if (index > 0) setIndex(index - 1);
    else router.back();
  };

  const advance = () => {
    setRiskCard(false);
    if (!isLast) setIndex(index + 1);
  };

  const onPrimary = () => {
    if (isLast) {
      if (allAnswered) onSubmit(answers as number[]);
      return;
    }
    if (current !== null) advance();
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <NavBar title={def.toolLabel} backLabel={index > 0 ? "이전" : "그만"} onBack={goPrev} />

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.disclaimer}>AI 추정은 참고용이에요. 진단은 의료진이 합니다.</Text>

        <View style={styles.qtop}>
          <Text style={styles.eyebrow}>{def.timeframe}</Text>
          <Text style={styles.score}>
            문항 {index + 1} / {items.length}
          </Text>
        </View>
        <View style={styles.qtrack}>
          <View style={[styles.qfill, { width: `${((index + 1) / items.length) * 100}%` }]} />
        </View>

        <Text style={styles.qq}>{def.instruction}</Text>
        <Text style={styles.qt}>{item?.text}</Text>

        <View style={styles.likert}>
          {options.map((opt) => {
            const selected = current === opt.value;
            return (
              <Pressable
                key={opt.value}
                onPress={() => select(opt.value)}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                accessibilityLabel={`${index + 1}번 문항 ${opt.label}`}
                style={[styles.opt, selected && styles.optSel]}
              >
                <View style={[styles.rad, selected && styles.radSel]} />
                <Text style={[styles.optLabel, selected && styles.optLabelSel]}>{opt.label}</Text>
              </Pressable>
            );
          })}
        </View>

        {riskCard ? (
          <View style={{ marginTop: 12 }}>
            <RiskConfirmCard
              onHelp={() => {
                // 설문 상태는 스택에 유지 — 응급에서 [안전해요]로 복귀 가능.
                setRiskCard(false);
                router.push("/(patient)/emergency");
              }}
              onDismiss={advance}
              dismissLabel={isLast ? "괜찮아요, 계속할게요" : "괜찮아요, 다음 문항으로"}
            />
          </View>
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        {/* 카드 노출 중에는 카드의 선택으로만 진행 (FR-043 확인 후 진행 원칙) */}
        {!riskCard ? (
          <Button
            label={isLast ? submitLabel : "다음 문항"}
            onPress={onPrimary}
            loading={submitting}
            disabled={current === null || (isLast && !allAnswered)}
          />
        ) : null}
        <Text style={styles.qcount}>답을 고르면 자동으로 저장돼요</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 20, paddingTop: 4, paddingBottom: 24, gap: 4 },
  disclaimer: { fontSize: 11.5, color: colors.muted, marginBottom: 8 },
  qtop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  eyebrow: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  score: { fontSize: 13, color: colors.ink, fontWeight: "500", fontVariant: ["tabular-nums"] },
  qtrack: {
    height: 4,
    borderRadius: 999,
    backgroundColor: colors.fill,
    overflow: "hidden",
    marginTop: 8,
    marginBottom: 2,
  },
  qfill: { height: 4, borderRadius: 999, backgroundColor: colors.ink },
  qq: { fontSize: 12.5, color: colors.muted, marginTop: 12 },
  qt: {
    fontSize: 19,
    fontWeight: "600",
    color: colors.ink,
    letterSpacing: -0.4,
    lineHeight: 26,
    marginTop: 6,
    marginBottom: 12,
  },
  likert: { gap: 9 },
  opt: {
    flexDirection: "row",
    alignItems: "center",
    gap: 13,
    minHeight: 54,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  optSel: { borderColor: colors.ink, borderWidth: 1.5 },
  rad: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: colors.lineStrong,
  },
  radSel: {
    borderColor: colors.ink,
    backgroundColor: colors.ink,
    borderWidth: 6,
  },
  optLabel: { fontSize: 14.5, color: colors.ink, flex: 1 },
  optLabelSel: { fontWeight: "600" },
  footer: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 20,
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.surface,
  },
  qcount: { textAlign: "center", fontSize: 11, color: colors.faint },
});
