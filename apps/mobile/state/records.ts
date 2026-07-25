/**
 * 지난 기록·리포트 로컬 스토어 (v3 FR-045/046/047 — mock 선구현).
 *
 * F4 종단 추이 / 리포트 이력 API는 플랫폼 프록시(§6-A)·수동 전달(§6-B)가
 * 배포되어야 실데이터로 바뀐다. 그 전까지 이 스토어가 화면 계약(피드·상태
 * 배지·상세)을 검증한다: 완료된 문진은 세션 리셋과 무관하게 여기 누적되고,
 * MOCK 모드에서는 과거 이력 시드가 채워진다.
 *
 * 상태 배지 (PRD v3 §4.2): 보관(미전달) → 전달됨 → 검토 완료.
 */

import { create } from "zustand";

import { QuestionnaireResult, QuestionnaireType } from "../lib/api";
import { SURVEYS, surveyMaxScore } from "../lib/surveys";

export type RecordStatus = "stored" | "delivered" | "reviewed";

export type IntakeRecord = {
  id: string;
  /** epoch ms */
  completedAt: number;
  instrument: QuestionnaireType;
  totalScore: number;
  maxScore: number;
  severity: string;
  status: RecordStatus;
  /** 위험 신호 플래그 (mock — 실데이터는 risk_events 조인) */
  riskFlag?: boolean;
};

export const SEVERITY_KO: Record<string, string> = {
  minimal: "정상 범위",
  mild: "경도",
  moderate: "중등도",
  moderately_severe: "중등도-중증",
  severe: "중증",
};

export const STATUS_KO: Record<RecordStatus, string> = {
  stored: "보관",
  delivered: "전달됨",
  reviewed: "검토 완료",
};

// 기록은 실제로 완료한 문진(addFromResult)만 누적한다. 예전에는 mock 모드에서
// 디자인 목업용 가짜 이력(seed-1..4)을 채웠으나, 실사용/시연 시 가짜 데이터가
// 섞여 혼란스러워 제거했다 — 빈 상태로 시작한다.

type RecordsState = {
  records: IntakeRecord[];
  /** 문진 제출 결과를 이력에 추가 (survey.tsx에서 호출). */
  addFromResult: (result: QuestionnaireResult, instrument: QuestionnaireType) => void;
  /** FR-047 mock — [전달하기]. 실모드는 §6-B 배포 전 버튼 자체를 비노출. */
  markDelivered: (id: string) => void;
};

export const useRecords = create<RecordsState>((set) => ({
  records: [],
  addFromResult: (result, instrument) =>
    set((s) => ({
      records: [
        {
          id: result.id,
          // 서버 completedAt 우선 — 클라이언트 시계와의 불일치 방지.
          completedAt: Date.parse(result.completedAt) || Date.now(),
          instrument,
          totalScore: result.totalScore,
          maxScore: surveyMaxScore(SURVEYS[instrument]),
          severity: result.severity,
          status: "stored" as const,
          // v3 FR-043 — 위험 플래그는 서버 채점기 판정을 따른다.
          // (설문 중 인라인 확인 카드는 응답 즉시 떠야 하므로 별도로
          //  클라이언트가 riskItemIndex로 판단한다 — 역할이 다르다.)
          riskFlag: result.criticalItemPositive === true,
        },
        ...s.records,
      ],
    })),
  markDelivered: (id) =>
    set((s) => ({
      records: s.records.map((r) =>
        r.id === id && r.status === "stored" ? { ...r, status: "delivered" as const } : r,
      ),
    })),
}));
