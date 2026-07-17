/**
 * 문항 주입형 표준 문진 정의 (v3 FR-040).
 *
 * 화면에는 질환명이 아니라 도구명(PHQ-9 등)만 노출한다 — v3 원칙 1
 * (AI 추정 질환명·신호 강도 비노출). 채점은 서버(/ai/survey/score)가 담당하고
 * 클라이언트는 응답 배열만 제출한다.
 *
 * AUDITC/PHQ4 저장은 questionnaire_results type 확장(§6-D, 미결 #7) 배포 후
 * 서버에서 수용된다 — 그 전에는 PHQ9/GAD7만 실제 제출 가능.
 */

import { QuestionnaireType } from "./api";

export type SurveyOption = { value: number; label: string };

export type SurveyItem = {
  text: string;
  /** 문항별 선택지가 다른 도구(AUDIT-C)용. 없으면 defaultOptions 사용. */
  options?: SurveyOption[];
};

export type SurveyDef = {
  id: QuestionnaireType;
  /** 화면 헤더 — 도구명만 (질환명 금지). */
  toolLabel: string;
  /** 기준 기간 안내 (qtop eyebrow). */
  timeframe: string;
  instruction: string;
  defaultOptions: SurveyOption[];
  items: SurveyItem[];
  /** FR-043 — 양성(>0) 응답 시 위험 확인 카드를 띄울 문항 index. */
  riskItemIndex?: number;
};

/** 0-3 Likert — PHQ-9 / GAD-7 / PHQ-4 공통 (DSM 표준). */
const LIKERT_0_3: SurveyOption[] = [
  { value: 0, label: "전혀 아니다" },
  { value: 1, label: "며칠 동안" },
  { value: 2, label: "일주일 이상" },
  { value: 3, label: "거의 매일" },
];

const PHQ9: SurveyDef = {
  id: "PHQ9",
  toolLabel: "PHQ-9",
  timeframe: "지난 2주 기준",
  instruction: "얼마나 자주 이런 문제로 불편을 느끼셨나요?",
  defaultOptions: LIKERT_0_3,
  items: [
    { text: "매사에 흥미나 즐거움이 거의 없음" },
    { text: "기분이 가라앉거나, 우울하거나, 희망이 없다고 느낌" },
    { text: "잠들기 어렵거나 자주 깸, 또는 잠을 너무 많이 잠" },
    { text: "피곤하다고 느끼거나 기력이 저하됨" },
    { text: "식욕이 줄거나 너무 많이 먹음" },
    { text: "내 자신이 실패자라고 느끼거나 가족을 실망시켰다고 느낌" },
    { text: "신문이나 TV 보기 등 일에 집중하기 어려움" },
    { text: "다른 사람이 알아챌 정도로 말과 행동이 느려짐, 또는 너무 안절부절못함" },
    { text: "차라리 죽는 것이 낫겠다고 생각하거나 자해할 생각을 함" },
  ],
  riskItemIndex: 8, // 9번 문항 (FR-043)
};

const GAD7: SurveyDef = {
  id: "GAD7",
  toolLabel: "GAD-7",
  timeframe: "지난 2주 기준",
  instruction: "얼마나 자주 이런 문제로 불편을 느끼셨나요?",
  defaultOptions: LIKERT_0_3,
  items: [
    { text: "초조하거나 불안하거나 조마조마하게 느낀다" },
    { text: "걱정하는 것을 멈추거나 조절할 수가 없다" },
    { text: "여러 가지 것들에 대해 걱정을 너무 많이 한다" },
    { text: "편하게 있기가 어렵다" },
    { text: "너무 안절부절못해서 가만히 있기가 힘들다" },
    { text: "쉽게 짜증이 나거나 쉽게 성을 내게 된다" },
    { text: "마치 끔찍한 일이 생길 것처럼 두렵게 느껴진다" },
  ],
};

// AUDIT-C — 한국어 v2 문항 (KNHANES 임계값, 채점은 서버 /ai/survey/score)
const AUDITC: SurveyDef = {
  id: "AUDITC",
  toolLabel: "AUDIT-C",
  timeframe: "지난 1년 기준",
  instruction: "평소 음주 습관에 가장 가까운 것을 골라 주세요.",
  defaultOptions: LIKERT_0_3, // 사용 안 함 — 전 문항 개별 options
  items: [
    {
      text: "술을 얼마나 자주 마십니까?",
      options: [
        { value: 0, label: "전혀 마시지 않는다" },
        { value: 1, label: "월 1회 이하" },
        { value: 2, label: "월 2~4회" },
        { value: 3, label: "주 2~3회" },
        { value: 4, label: "주 4회 이상" },
      ],
    },
    {
      text: "술을 마시는 날은 보통 몇 잔을 마십니까?",
      options: [
        { value: 0, label: "1~2잔" },
        { value: 1, label: "3~4잔" },
        { value: 2, label: "5~6잔" },
        { value: 3, label: "7~9잔" },
        { value: 4, label: "10잔 이상" },
      ],
    },
    {
      text: "한 번의 술자리에서 6잔 이상(여성 5잔) 마시는 경우는 얼마나 자주 있습니까?",
      options: [
        { value: 0, label: "전혀 없다" },
        { value: 1, label: "월 1회 미만" },
        { value: 2, label: "월 1회 정도" },
        { value: 3, label: "주 1회 정도" },
        { value: 4, label: "거의 매일" },
      ],
    },
  ],
};

// PHQ-4 — 초간이 스크리닝 (PHQ-2 + GAD-2). 폴백 잠정 도구 (미결 #4).
const PHQ4: SurveyDef = {
  id: "PHQ4",
  toolLabel: "PHQ-4",
  timeframe: "지난 2주 기준",
  instruction: "얼마나 자주 이런 문제로 불편을 느끼셨나요?",
  defaultOptions: LIKERT_0_3,
  items: [
    { text: "초조하거나 불안하거나 조마조마하게 느낀다" },
    { text: "걱정하는 것을 멈추거나 조절할 수가 없다" },
    { text: "매사에 흥미나 즐거움이 거의 없음" },
    { text: "기분이 가라앉거나, 우울하거나, 희망이 없다고 느낌" },
  ],
};

export const SURVEYS: Record<QuestionnaireType, SurveyDef> = {
  PHQ9,
  GAD7,
  AUDITC,
  PHQ4,
};

/** 도구 총점 상한 — 문항 정의에서 파생 (별도 상수로 중복 관리하지 않는다). */
export function surveyMaxScore(def: SurveyDef): number {
  return def.items.reduce(
    (sum, item) =>
      sum + Math.max(...(item.options ?? def.defaultOptions).map((o) => o.value)),
    0,
  );
}
