/**
 * Offline mock backend — lets the app run with NO API server / Postgres.
 *
 * Enabled when `MOCK` (lib/config.ts) is true (default in __DEV__, or set
 * EXPO_PUBLIC_MOCK=1 / =0 to force). Both the REST client (lib/api.ts) and the
 * chat WebSocket client (lib/ws.ts) route through here instead of the network.
 *
 * Everything is in-memory and deterministic enough to demo the full flow:
 *   login (any credentials) → home → start session → chat (simulated AI +
 *   progress + risk routing) → PHQ-9/GAD-7 → submit → emergency ack.
 */

import type {
  DeliverResult,
  OCRResult,
  QuestionnaireResult,
  ReportTrend,
  ReportSummary,
  ReportPdf,
  QuestionnaireType,
  RegisterInput,
  ReportStatusOut,
  RiskEventAck,
  SessionListItem,
  SessionOut,
  SubmitAccepted,
  TokenPair,
} from "./api";
import type { SafetyLevel, WSEvent } from "./ws";

// Monotonic id source — Math.random/Date are fine in app runtime, but a counter
// keeps ids readable in logs.
let seq = 0;
const id = (prefix: string): string => `${prefix}-${(++seq).toString(36)}-${Date.now().toString(36)}`;

const nowIso = (): string => new Date().toISOString();

// Simulated Handoff generation time (ms). Status flips to "ready" after this.
const MOCK_REPORT_GENERATE_MS = 8000;
const MOCK_REPORTS = new Map<string, { reportId: string; submittedAt: number }>();

const MOCK_TOKENS = (): TokenPair => ({
  userId: "mock-patient-001",
  role: "patient",
  accessToken: `mock-access.${seq}`,
  refreshToken: "mock-refresh",
  expiresIn: 3600,
});

// ────────── Risk classification (mirrors seed_demo crisis copy) ──────────

const CRISIS_RE = /살고\s*싶지\s*않|죽고\s*싶|자살|목숨|뛰어내리|사라지고\s*싶/;
const MEDIUM_RE = /우울|불안|힘들|괴로|불면|잠[을이]?\s*못|의욕이?\s*없|식욕/;

export function classifyRisk(content: string): SafetyLevel {
  if (CRISIS_RE.test(content)) return "critical";
  if (MEDIUM_RE.test(content)) return "medium";
  return "low";
}

// v3 FR-044 — 109 기준 (구 1393·1577-0199는 2024-01부터 통합).
export const MOCK_HOTLINES = [
  { name: "자살예방 통합번호", number: "109" },
  { name: "응급의료", number: "119" },
  { name: "경찰", number: "112" },
];

// ────────── REST mock ──────────

// 도구별 중증도 밴드 (v3 FR-040 — 4종. switch 누락 시 TS가 잡도록 exhaustive).
function severityFor(type: QuestionnaireType, score: number): string {
  switch (type) {
    case "PHQ9":
      if (score <= 4) return "minimal";
      if (score <= 9) return "mild";
      if (score <= 14) return "moderate";
      if (score <= 19) return "moderately_severe";
      return "severe";
    case "GAD7":
      if (score <= 4) return "minimal";
      if (score <= 9) return "mild";
      if (score <= 14) return "moderate";
      return "severe";
    case "AUDITC":
      // KNHANES 절사점 근사 (0-12) — 정식 채점은 서버 /ai/survey/score.
      if (score <= 3) return "minimal";
      if (score <= 7) return "mild";
      if (score <= 9) return "moderate";
      return "severe";
    case "PHQ4":
      // 표준 밴드: 0-2 정상, 3-5 경도, 6-8 중등도, 9-12 중증.
      if (score <= 2) return "minimal";
      if (score <= 5) return "mild";
      if (score <= 8) return "moderate";
      return "severe";
  }
}

const delay = <T>(value: T, ms = 250): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

export const mockApi = {
  register(_input: RegisterInput): Promise<TokenPair> {
    return delay(MOCK_TOKENS());
  },
  login(_email: string, _password: string): Promise<TokenPair> {
    // Accept ANY credentials in mock mode.
    return delay(MOCK_TOKENS());
  },
  updateProfileDemographics(): Promise<{ updated: string[] }> {
    return delay({ updated: [] }, 300);
  },
  refresh(): Promise<string | null> {
    return delay(`mock-access.${++seq}`);
  },
  createSession(): Promise<SessionOut> {
    return delay({ sessionId: id("mock-session"), status: "in_progress", createdAt: nowIso() });
  },
  submitQuestionnaire(
    type: QuestionnaireType,
    answers: number[],
  ): Promise<QuestionnaireResult> {
    const totalScore = answers.reduce((a, b) => a + (Number(b) || 0), 0);
    return delay({
      id: id("mock-q"),
      type,
      totalScore,
      severity: severityFor(type, totalScore),
      completedAt: nowIso(),
    });
  },
  inferDomainInstrument(): Promise<{ instrument: QuestionnaireType }> {
    // 오프라인 데모 시나리오는 우울(PHQ-9)로 고정한다.
    // 실제 라우팅은 서버가 F2 도메인 추정으로 결정한다 (v3 FR-039).
    return delay({ instrument: "PHQ9" as QuestionnaireType }, 1200);
  },
  parseDocument(): Promise<OCRResult> {
    // 오프라인 데모: 처방전 한 장을 인식한 것처럼 구조화 결과를 돌려준다.
    return delay(
      {
        documentType: "prescription",
        extractedSummary: {
          diagnoses: ["우울에피소드 (F32.1)"],
          medications: [
            { name: "에스시탈로프람", dose: "10mg", frequency: "1일 1회", route: "경구" },
            { name: "졸피뎀", dose: "10mg", frequency: "취침 전", route: "경구" },
          ],
          department: "정신건강의학과",
          dates: ["2026-06-18"],
          scaleScores: {},
        },
        lowConfidenceItems: [
          {
            blockId: "b-3",
            field: "medications[1].dose",
            value: "10mg",
            confidence: 0.62,
            severity: "verify",
            message: "확인 필요",
          },
        ],
        pageCount: 1,
        elementCount: 12,
      },
      1400,
    );
  },
  deliverReport(): Promise<DeliverResult> {
    return delay({ delivered: true, deliveredAt: nowIso() }, 400);
  },
  getReportTrend(): Promise<ReportTrend> {
    // 오프라인 데모: 3회 방문에 걸쳐 호전되는 추이(PHQ-9 18→14→9, GAD-7 15→11→7).
    // CTRS는 낮을수록 위험 — 2→3→3으로 위험도 완화. 실경로는 F4 plot_data 바인딩.
    return delay(
      {
        overallDirection: "improved",
        isFirstVisit: false,
        plotData: [
          {
            date: "2026-05-14",
            phq9: 18,
            gad7: 15,
            ctrsLevel: 2,
            sentimentPolarity: -0.42,
            events: ["첫 방문"],
          },
          {
            date: "2026-06-18",
            phq9: 14,
            gad7: 11,
            ctrsLevel: 3,
            sentimentPolarity: -0.18,
            events: [],
          },
          {
            date: "2026-07-19",
            phq9: 9,
            gad7: 7,
            ctrsLevel: 3,
            sentimentPolarity: 0.12,
            events: ["수면 호전"],
          },
        ],
      },
      600,
    );
  },
  submitSession(sessionId: string): Promise<SubmitAccepted> {
    const reportId = id("mock-report");
    // Record submit time so getReportStatus can simulate generating → ready.
    MOCK_REPORTS.set(sessionId, { reportId, submittedAt: Date.now() });
    return delay({
      sessionId,
      status: "report_generating",
      reportId,
      estimatedSeconds: MOCK_REPORT_GENERATE_MS / 1000,
    });
  },
  getReportStatus(sessionId: string): Promise<ReportStatusOut> {
    const rec = MOCK_REPORTS.get(sessionId);
    if (!rec) {
      // No submit recorded (e.g. app reloaded) — treat as already done.
      return delay({ status: "ready", reportId: null }, 120);
    }
    const elapsed = Date.now() - rec.submittedAt;
    const status = elapsed >= MOCK_REPORT_GENERATE_MS ? "ready" : "generating";
    return delay({ status, reportId: rec.reportId }, 120);
  },
  getReportSummary(): Promise<ReportSummary> {
    // 오프라인 데모: 자기보고 + 설문 결과 요약(환자 안전 뷰). 실경로는 F5 완료 후
    // /report/summary 바인딩.
    return delay({
      status: "ready",
      ready: true,
      generatedAt: nowIso(),
      selfReported: [
        { key: "chief_complaint", label: "주호소", value: "요즘 잠이 잘 안 오고 불안해요." },
        {
          key: "history_of_present_illness",
          label: "현병력",
          value: "몇 주 전부터 새벽에 자주 깨고 낮에 집중이 어렵다고 함.",
        },
      ],
      questionnaires: [
        { scale: "PHQ-9", totalScore: 14, severity: "moderate", severityLabel: "중등도" },
        { scale: "GAD-7", totalScore: 11, severity: "moderate", severityLabel: "중등도" },
      ],
      disclaimer:
        "이 요약은 자가보고와 설문을 정리한 자료로, 의학적 진단이 아닙니다. 정확한 평가는 의료진과 상담해 주세요.",
    });
  },
  getReportPdf(): Promise<ReportPdf> {
    // 오프라인 데모: 최소 유효 PDF 1페이지(base64). 실경로는 F5 editorial PDF.
    const MINI_PDF =
      "JVBERi0xLjQKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PgplbmRvYmoKMyAwIG9iago8PC9UeXBlL1BhZ2UvUGFyZW50IDIgMCBSL01lZGlhQm94WzAgMCA2MTIgNzkyXT4+CmVuZG9iagp4cmVmCjAgNAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTE1IDAwMDAwIG4gCnRyYWlsZXIKPDwvU2l6ZSA0L1Jvb3QgMSAwIFI+PgpzdGFydHhyZWYKMTkwCiUlRU9G";
    return delay({ filename: "handoff_report_demo.pdf", pdfBase64: MINI_PDF });
  },
  acknowledgeRiskEvent(
    riskEventId: string,
    aloneStatus: "alone" | "with_someone",
  ): Promise<RiskEventAck> {
    return delay({
      id: riskEventId,
      status: "acknowledged",
      aloneStatus,
      acknowledgedAt: nowIso(),
    });
  },
  // S09 records — not the demo's primary MOCK path (records.tsx keeps using
  // the `state/records.ts` local store when MOCK, per its own FR-045/046/047
  // seed), but kept lib-pattern-consistent so any other MOCK-mode caller of
  // `listSessions` gets a sane, self-contained response.
  listSessions(): Promise<SessionListItem[]> {
    return delay([
      {
        sessionId: id("mock-session"),
        status: "in_progress",
        createdAt: nowIso(),
        progressRatio: 0,
        hasReport: false,
      },
    ]);
  },
};

// ────────── Chat (WebSocket) mock ──────────

const AI_REPLIES = [
  "말씀해 주셔서 고마워요. 그 증상이 언제부터 시작됐는지 조금 더 알려주실 수 있을까요?",
  "그랬군요. 하루 중 특히 힘든 시간대가 있나요?",
  "이해했어요. 수면이나 식욕에는 어떤 변화가 있었나요?",
  "조금씩 정리가 되고 있어요. 일상생활(직장·학업·관계)에는 어떤 영향이 있었나요?",
  "충분히 들었어요. 마지막으로, 도움이 되었던 것이나 기대하는 점이 있다면 알려주세요.",
  "말씀해 주신 내용을 잘 정리했어요. 이제 표준 설문으로 넘어가 볼까요?",
];

export type MockEmit = (event: WSEvent) => void;

/**
 * Drives a simulated chat turn. The WS client calls this on sendMessage and
 * feeds emitted events back through its normal handler set.
 */
export function mockChatTurn(opts: {
  content: string;
  idempotencyKey: string;
  turnIndex: number;
  emit: MockEmit;
  schedule: (fn: () => void, ms: number) => void;
}): void {
  const { content, idempotencyKey, turnIndex, emit, schedule } = opts;
  const level = classifyRisk(content);
  const messageId = id("mock-msg");

  // 1) Echo ack for the user's message.
  schedule(() => {
    emit({
      type: "user:message:received",
      payload: { messageId, idempotencyKey, safetyLevel: level, latencyMs: 7 },
    });
  }, 150);

  // 2) Risk routing.
  if (level === "critical") {
    schedule(() => {
      emit({
        type: "risk:detected",
        payload: {
          level: "critical",
          category: "suicide",
          riskEventId: id("mock-risk"),
          triggerMessageId: messageId,
          routeTo: "/emergency",
          hotlines: MOCK_HOTLINES,
          reason: "위기 신호가 감지되었어요. 안전을 먼저 확인할게요.",
        },
      });
    }, 350);
    return; // On a crisis we hold the intake AI reply.
  }
  if (level === "medium") {
    schedule(() => {
      emit({
        type: "risk:detected",
        payload: {
          level: "medium",
          category: "distress",
          riskEventId: id("mock-risk"),
          triggerMessageId: messageId,
          routeTo: "/self_hotline",
          hotlines: MOCK_HOTLINES,
          reason: "힘든 마음이 느껴져요. 필요하면 도움을 받을 수 있어요.",
        },
      });
    }, 350);
  }

  // 3) AI reply + monotonic progress (~6 turns to reach 100%).
  const totalItems = AI_REPLIES.length;
  const ratio = Math.min(1, (turnIndex + 1) / totalItems);
  const content_ =
    AI_REPLIES[Math.min(turnIndex, AI_REPLIES.length - 1)] ??
    AI_REPLIES[AI_REPLIES.length - 1] ??
    "말씀 감사합니다.";
  schedule(() => {
    emit({
      type: "ai:complete",
      payload: {
        messageId: id("mock-ai"),
        content: content_,
        modelUsed: "mock-llm",
        progress: { collectedItems: [], totalItems, ratio },
      },
    });
  }, 700);
}
