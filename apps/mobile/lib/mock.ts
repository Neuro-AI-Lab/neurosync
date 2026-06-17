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
  QuestionnaireResult,
  QuestionnaireType,
  RegisterInput,
  ReportStatusOut,
  RiskEventAck,
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

export const MOCK_HOTLINES = [
  { name: "자살예방 상담전화", number: "1393" },
  { name: "정신건강 상담전화", number: "1577-0199" },
];

// ────────── REST mock ──────────

function severityFor(type: QuestionnaireType, score: number): string {
  if (type === "PHQ9") {
    if (score <= 4) return "minimal";
    if (score <= 9) return "mild";
    if (score <= 14) return "moderate";
    if (score <= 19) return "moderately_severe";
    return "severe";
  }
  // GAD7
  if (score <= 4) return "minimal";
  if (score <= 9) return "mild";
  if (score <= 14) return "moderate";
  return "severe";
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
