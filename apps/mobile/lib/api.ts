/**
 * REST client wrapper — apps/api.
 *
 * Surfaces Phase 1a Auth + Sessions endpoints with structured errors.
 *
 * Token lifecycle:
 * - On 401 we try refresh once using the refresh token from SecureStore.
 * - If refresh succeeds, the new access token is persisted and the original
 *   request is replayed exactly once.
 * - If refresh fails (or there is no refresh token), `clearAll()` runs to
 *   purge any orphan state and the original 401 is re-thrown.
 */

import { API_BASE_URL, MOCK } from "./config";
import { mockApi } from "./mock";
import * as Store from "./secure-store";

export type APIError = {
  code: string;
  message: string;
  details?: unknown[];
};

export class APIException extends Error {
  status: number;
  body: APIError;
  constructor(status: number, body: APIError) {
    super(body.message ?? "API error");
    this.status = status;
    this.body = body;
  }
}

type Envelope<T> = { success: true; data: T } | { success: false; error: APIError };

export type TokenPair = {
  userId: string;
  role: "patient";
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
};

type RequestInitWithToken = RequestInit & { token?: string };

async function rawRequest<T>(
  path: string,
  init: RequestInitWithToken,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.token) headers.Authorization = `Bearer ${init.token}`;

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  let body: Envelope<T> | null = null;
  try {
    body = (await resp.json()) as Envelope<T>;
  } catch {
    body = null;
  }

  if (!resp.ok) {
    const err: APIError =
      body && body.success === false
        ? body.error
        : { code: "HTTP_ERROR", message: `HTTP ${resp.status}` };
    throw new APIException(resp.status, err);
  }

  if (!body || body.success === false) {
    const err: APIError =
      body && body.success === false
        ? body.error
        : { code: "INVALID_RESPONSE", message: "Server returned non-envelope JSON" };
    throw new APIException(resp.status, err);
  }
  return body.data;
}

let refreshInFlight: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  // Coalesce concurrent refresh attempts so we don't double-spend the refresh
  // token if multiple in-flight requests all 401 at once.
  if (refreshInFlight !== null) return refreshInFlight;
  refreshInFlight = (async () => {
    if (MOCK) {
      const fresh = await mockApi.refresh();
      if (fresh) await Store.saveAccessToken(fresh);
      refreshInFlight = null;
      return fresh;
    }
    const refresh = await Store.getRefreshToken();
    if (!refresh) return null;
    try {
      const { accessToken } = await rawRequest<{
        accessToken: string;
        expiresIn: number;
      }>("/api/v1/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refreshToken: refresh }),
      });
      await Store.saveAccessToken(accessToken);
      return accessToken;
    } catch {
      // Orphan refresh tokens are a reuse hazard — purge the partial state.
      await Store.clearAll();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function request<T>(
  path: string,
  init: RequestInitWithToken,
): Promise<T> {
  try {
    return await rawRequest<T>(path, init);
  } catch (exc) {
    if (
      exc instanceof APIException &&
      exc.status === 401 &&
      // /auth/login and /auth/refresh themselves must not loop — only retry
      // endpoints that needed a bearer to begin with.
      init.token !== undefined
    ) {
      const fresh = await tryRefresh();
      if (fresh !== null) {
        return await rawRequest<T>(path, { ...init, token: fresh });
      }
    }
    throw exc;
  }
}

// ────────── Auth ──────────

// v3 수정 1 — 확장 인적사항 코드 유니온 (백엔드 schemas/auth.py와 일치).
export type MaritalStatus = "single" | "married" | "divorced" | "bereaved" | "separated" | "other";
export type HouseholdType = "alone" | "spouse" | "parents" | "children" | "relatives" | "other";
export type EducationLevel = "middle_or_below" | "high_school" | "college" | "graduate" | "other";
export type EmploymentStatus =
  | "employed"
  | "self_employed"
  | "unemployed"
  | "student"
  | "retired"
  | "homemaker"
  | "other";
export type IncomeLevel = "low" | "mid_low" | "mid" | "mid_high" | "high" | "prefer_not";
export type Religion =
  | "none"
  | "protestant"
  | "catholic"
  | "buddhist"
  | "won"
  | "other"
  | "prefer_not";

export type RegisterInput = {
  email: string;
  password: string;
  name: string;
  birthYear: number;
  gender: "male" | "female" | "other";
  phone: string;
  region: string;
  emergencyContact: string;
  // 확장 인적사항 — 모두 선택. 미입력 시 생략(백엔드 default None).
  maritalStatus?: MaritalStatus;
  householdType?: HouseholdType;
  educationLevel?: EducationLevel;
  occupation?: string;
  employmentStatus?: EmploymentStatus;
  incomeLevel?: IncomeLevel;
  religion?: Religion;
  consents: {
    tos: boolean;
    privacy: boolean;
    sensitive: boolean;
    riskNotification: boolean;
    voice?: boolean;
  };
};

export async function register(input: RegisterInput): Promise<TokenPair> {
  if (MOCK) return mockApi.register(input);
  return request<TokenPair>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// v3 수정 1 — 가입 후 인적사항(선택) 저장. 보낸 필드만 갱신된다.
export type ProfileDemographics = {
  maritalStatus?: MaritalStatus;
  householdType?: HouseholdType;
  educationLevel?: EducationLevel;
  occupation?: string;
  employmentStatus?: EmploymentStatus;
  incomeLevel?: IncomeLevel;
  religion?: Religion;
};

export async function updateProfileDemographics(
  token: string,
  fields: ProfileDemographics,
): Promise<{ updated: string[] }> {
  if (MOCK) return mockApi.updateProfileDemographics();
  return request<{ updated: string[] }>("/api/v1/auth/me/profile", {
    method: "PATCH",
    token,
    body: JSON.stringify(fields),
  });
}

export async function login(
  email: string,
  password: string,
  role: "patient" | "clinician" | "org_admin" = "patient",
): Promise<TokenPair> {
  if (MOCK) return mockApi.login(email, password);
  return request<TokenPair>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
  });
}

export async function refreshAccessTokenOnce(): Promise<string | null> {
  return tryRefresh();
}

// ────────── Sessions ──────────

export type SessionOut = {
  sessionId: string;
  status: string;
  createdAt: string;
};

export async function createSession(token: string): Promise<SessionOut> {
  if (MOCK) return mockApi.createSession();
  return request<SessionOut>("/api/v1/sessions", {
    method: "POST",
    token,
  });
}

// ────────── Questionnaires (FR-006/007 · v3 FR-040) ──────────

// v3 FR-040 — 문항 주입형 문진 4종. AUDITC/PHQ4의 서버 저장은
// questionnaire_results type 확장(§6-D, 미결 #7) 배포 후 수용된다.
export type QuestionnaireType = "PHQ9" | "GAD7" | "AUDITC" | "PHQ4";

export type QuestionnaireResult = {
  id: string;
  type: string;
  totalScore: number;
  severity: string;
  completedAt: string;
  /** v3 FR-043 — PHQ-9 9번 양성. 서버 채점기 판정을 그대로 쓴다. */
  criticalItemPositive?: boolean;
};

export async function submitQuestionnaire(
  token: string,
  sessionId: string,
  type: QuestionnaireType,
  answers: number[],
): Promise<QuestionnaireResult> {
  if (MOCK) return mockApi.submitQuestionnaire(type, answers);
  return request<QuestionnaireResult>(
    `/api/v1/sessions/${sessionId}/questionnaires`,
    {
      method: "POST",
      token,
      body: JSON.stringify({ type, answers }),
    },
  );
}

// ────────── Domain routing (v3 FR-039, §6-A 프록시) ──────────

/**
 * 대화 종료 후 진행할 문진 도구 1종을 서버가 정해준다.
 *
 * 응답에는 도구 ID만 담긴다 — 추정된 질환/도메인 문자열은 서버가 내려보내지
 * 않는다 (v3 원칙 1 / NFR v3-2). 클라이언트가 병명을 화면에 띄울 방법 자체가
 * 없도록 계약이 설계돼 있다.
 */
export async function inferDomainInstrument(
  token: string,
  sessionId: string,
): Promise<{ instrument: QuestionnaireType }> {
  if (MOCK) return mockApi.inferDomainInstrument();
  return request<{ instrument: QuestionnaireType }>(
    `/api/v1/sessions/${sessionId}/domain/infer`,
    { method: "POST", token },
  );
}

// ────────── OCR 문서 첨부 (v3 FR-048) ──────────

export type OCRMedication = {
  name: string;
  dose?: string | null;
  frequency?: string | null;
  route?: string | null;
  confidence?: number;
};

export type OCRSummary = {
  diagnoses: string[];
  diagnosisCodes?: string[];
  medications: OCRMedication[];
  department?: string | null;
  dates: string[];
  scaleScores?: Record<string, number>;
  patientName?: string | null;
  patientAge?: string | null;
  patientGender?: string | null;
};

export type OCRLowConfidenceItem = {
  blockId: string;
  field: string;
  value: string;
  confidence: number;
  severity: "info" | "verify" | "retry";
  message: string;
};

export type OCRResult = {
  documentType: string;
  extractedSummary: OCRSummary;
  lowConfidenceItems: OCRLowConfidenceItem[];
  pageCount: number;
  elementCount: number;
};

export type DocumentUpload = { uri: string; name: string; mime: string };

/**
 * 처방전/진단서 이미지를 업로드해 OCR 구조화 결과를 받는다 (multipart).
 * 확정 반영은 사용자가 확인 화면에서 [확인 완료]를 눌러야 이뤄진다 (FR-048).
 */
export async function parseDocument(
  token: string,
  sessionId: string,
  file: DocumentUpload,
  documentTypeHint = "unknown",
): Promise<OCRResult> {
  if (MOCK) return mockApi.parseDocument();

  const form = new FormData();
  // RN FormData file part: { uri, name, type }.
  form.append(
    "document",
    { uri: file.uri, name: file.name, type: file.mime } as unknown as Blob,
  );
  form.append("document_type_hint", documentTypeHint);

  const resp = await fetch(
    `${API_BASE_URL}/api/v1/sessions/${sessionId}/documents/ocr`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form, // Content-Type은 fetch가 boundary와 함께 설정
    },
  );
  let body: Envelope<OCRResult> | null = null;
  try {
    body = (await resp.json()) as Envelope<OCRResult>;
  } catch {
    body = null;
  }
  if (!resp.ok || !body || body.success === false) {
    const err: APIError =
      body && body.success === false
        ? body.error
        : { code: "NETWORK", message: "문서 인식에 실패했어요." };
    throw new APIException(resp.status, err);
  }
  return body.data;
}

// ────────── Submit (FR-010) ──────────

export type SubmitAccepted = {
  sessionId: string;
  status: string;
  reportId: string;
  estimatedSeconds: number;
};

export async function submitSession(
  token: string,
  sessionId: string,
): Promise<SubmitAccepted> {
  if (MOCK) return mockApi.submitSession(sessionId);
  return request<SubmitAccepted>(`/api/v1/sessions/${sessionId}/submit`, {
    method: "POST",
    token,
  });
}

// ────────── Report status (FR-013/018) ──────────

export type ReportPhase = "generating" | "ready" | "failed";

export type ReportStatusOut = {
  status: ReportPhase;
  reportId: string | null;
};

/**
 * Patient-facing report status — STATUS ONLY (the report body stays
 * clinician-only per screen-spec §S-12). The patient screen polls this.
 */
export async function getReportStatus(
  token: string,
  sessionId: string,
): Promise<ReportStatusOut> {
  if (MOCK) return mockApi.getReportStatus(sessionId);
  return request<ReportStatusOut>(`/api/v1/sessions/${sessionId}/report/status`, {
    method: "GET",
    token,
  });
}

// ────────── 점수 추이 (F4 종단 추론 · 리포트 차트) ──────────

export type TrendDirection = "improved" | "worsened" | "unchanged" | "unknown";

export type TrendPoint = {
  date: string;
  phq9: number | null;
  gad7: number | null;
  /** CTRS 위험 단계 1~5 — **숫자가 낮을수록 위험**(1=최고위험). */
  ctrsLevel: number | null;
  sentimentPolarity: number | null;
  events: string[];
};

export type ReportTrend = {
  overallDirection: TrendDirection;
  plotData: TrendPoint[];
  isFirstVisit: boolean;
};

/**
 * 리포트 점수 추이 (핸드오프 문서 수정 7). 이번 세션과 직전 방문의 표준 척도
 * 점수를 비교한 F4 plot_data를 차트에 바인딩한다. 환자 본인 응답 기반 점수만
 * 시각화하며 AI 추정 도메인은 표시하지 않는다(NFR v3-2).
 */
export async function getReportTrend(
  token: string,
  sessionId: string,
): Promise<ReportTrend> {
  if (MOCK) return mockApi.getReportTrend();
  return request<ReportTrend>(`/api/v1/sessions/${sessionId}/report/trend`, {
    method: "GET",
    token,
  });
}

// ────────── 리포트 수동 전달 (FR-047 · §6-B) ──────────

export type DeliverResult = { delivered: boolean; deliveredAt: string };

/**
 * 보관 중인 리포트를 의료진에게 전달한다(핸드오프 수정 7 · §6-B). 전달 전까지
 * 리포트는 환자만 열람하며, 이 호출로 delivered_at이 채워져야 의료진 웹에 노출된다.
 * 멱등 — 이미 전달됐으면 기존 전달 시각을 그대로 돌려준다.
 */
export async function deliverReport(
  token: string,
  sessionId: string,
): Promise<DeliverResult> {
  if (MOCK) return mockApi.deliverReport();
  return request<DeliverResult>(`/api/v1/sessions/${sessionId}/report/deliver`, {
    method: "POST",
    token,
  });
}

// ────────── Risk event acknowledgement (FR-011/022) ──────────

export type RiskEventAck = {
  id: string;
  status: string;
  aloneStatus: string | null;
  acknowledgedAt: string | null;
};

export async function acknowledgeRiskEvent(
  token: string,
  riskEventId: string,
  aloneStatus: "alone" | "with_someone",
): Promise<RiskEventAck> {
  if (MOCK) return mockApi.acknowledgeRiskEvent(riskEventId, aloneStatus);
  return request<RiskEventAck>(`/api/v1/risk_events/${riskEventId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ aloneStatus }),
  });
}

// ────────── Voice consent (FR-034) ──────────

export type VoiceConsent = {
  voice: boolean;
  consentSnapshotId: string;
};

/** Toggle voice (STT) consent post-signup. Appends a new consent snapshot. */
export async function setVoiceConsent(
  token: string,
  voice: boolean,
): Promise<VoiceConsent> {
  if (MOCK) return { voice, consentSnapshotId: "mock-consent" };
  return request<VoiceConsent>("/api/v1/consent/voice", {
    method: "POST",
    token,
    body: JSON.stringify({ voice }),
  });
}

// ────────── STT transcribe (FR-033) ──────────

export type STTResult = {
  transcriptionId: string;
  text: string;
  confidence: number;
  vendor: string;
  durationMs: number;
  latencyMs: number;
  audioRecordingId: string;
};

export type STTUpload = {
  uri: string;
  encoding?: "pcm16" | "opus";
  sampleRateHz?: number;
  prevContext?: string;
};

/**
 * Upload a Push-to-Talk audio clip for transcription (multipart).
 * Returns text only — the caller fills the input box; nothing is auto-sent
 * (FR-035). Throws APIException on 403 (consent) / 422 (low confidence) / 503.
 */
export async function transcribeAudio(
  token: string,
  sessionId: string,
  clip: STTUpload,
): Promise<STTResult> {
  if (MOCK) {
    return {
      transcriptionId: "mock-stt",
      text: "요즘 잠을 잘 못 자고 불안한 느낌이 들어요",
      confidence: 0.93,
      vendor: "mock",
      durationMs: 4200,
      latencyMs: 120,
      audioRecordingId: "mock-audio",
    };
  }

  const ext = clip.encoding === "opus" ? "ogg" : "wav";
  const mime = clip.encoding === "opus" ? "audio/ogg" : "audio/wav";
  const form = new FormData();
  // RN FormData file part: { uri, name, type }.
  form.append("audio", { uri: clip.uri, name: `clip.${ext}`, type: mime } as unknown as Blob);
  form.append("sessionId", sessionId);
  form.append("encoding", clip.encoding ?? "pcm16");
  form.append("sampleRateHz", String(clip.sampleRateHz ?? 16000));
  if (clip.prevContext) form.append("prevContext", clip.prevContext);

  // Do NOT set Content-Type — fetch adds the multipart boundary itself.
  const resp = await fetch(`${API_BASE_URL}/api/v1/stt/transcribe`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  let body: Envelope<STTResult> | null = null;
  try {
    body = (await resp.json()) as Envelope<STTResult>;
  } catch {
    body = null;
  }
  if (!resp.ok || !body || body.success === false) {
    const err: APIError =
      body && body.success === false
        ? body.error
        : { code: "HTTP_ERROR", message: `HTTP ${resp.status}` };
    throw new APIException(resp.status, err);
  }
  return body.data;
}
