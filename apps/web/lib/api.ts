/**
 * Server-only REST client for the clinician dashboard.
 * Forwards the access token from the httpOnly cookie as a Bearer header.
 */

import "server-only";

import { cookies } from "next/headers";

import { ACCESS_COOKIE, API_BASE_URL, assertProductionTLS } from "./config";

export type APIError = { code: string; message: string; details?: unknown[] };

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

async function fetchAPI<T>(
  path: string,
  init: RequestInit & { withAuth?: boolean } = {},
): Promise<T> {
  assertProductionTLS();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  if (init.withAuth ?? true) {
    const store = await cookies();
    const access = store.get(ACCESS_COOKIE);
    if (access?.value) {
      headers.set("Authorization", `Bearer ${access.value}`);
    }
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
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

// ────────── Auth ──────────

export type TokenPair = {
  userId: string;
  role: "clinician" | "org_admin";
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
};

export async function loginClinician(
  email: string,
  password: string,
  role: "clinician" | "org_admin",
): Promise<TokenPair> {
  return fetchAPI<TokenPair>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
    withAuth: false,
  });
}

// ────────── Clinician dashboard ──────────

export type RiskBadge = {
  level: "low" | "medium" | "high" | "critical";
  category: string | null;
  detectedAt: string;
};

export type PatientListItem = {
  userId: string;
  email: string;
  name: string;
  birthYear: number;
  isMinor: boolean;
  latestSessionId: string | null;
  latestSessionStatus: string | null;
  latestSessionAt: string | null;
  latestRisk: RiskBadge | null;
  riskEventCount: number;
};

export type ConsentOut = {
  tos: boolean;
  privacy: boolean;
  sensitive: boolean;
  riskNotification: boolean;
  collectedAt: string;
};

export type SessionSummary = {
  id: string;
  status: string;
  createdAt: string;
  submittedAt: string | null;
  riskEventCount: number;
  latestRisk: RiskBadge | null;
};

export type PatientDetail = {
  userId: string;
  email: string;
  name: string;
  birthYear: number;
  isMinor: boolean;
  gender: string | null;
  phone: string | null;
  region: string | null;
  emergencyContact: string | null;
  consent: ConsentOut | null;
  sessions: SessionSummary[];
};

export type MessageOut = {
  id: string;
  role: "user" | "ai" | "system";
  content: string;
  inputModality: "text" | "voice";
  createdAt: string;
};

export type RiskEventOut = {
  id: string;
  level: "low" | "medium" | "high" | "critical";
  category: string | null;
  status: string;
  legalBasis: string | null;
  triggerMessageId: string | null;
  aiEvidence: Record<string, unknown> | null;
  detectedAt: string;
};

export type SessionDetail = {
  id: string;
  patientId: string;
  status: string;
  createdAt: string;
  submittedAt: string | null;
  messages: MessageOut[];
  riskEvents: RiskEventOut[];
};

export async function listPatients(): Promise<PatientListItem[]> {
  return fetchAPI<PatientListItem[]>("/api/v1/clinician/patients");
}

export async function getPatient(id: string): Promise<PatientDetail> {
  return fetchAPI<PatientDetail>(`/api/v1/clinician/patients/${id}`);
}

export async function getSession(id: string): Promise<SessionDetail> {
  return fetchAPI<SessionDetail>(`/api/v1/clinician/sessions/${id}`);
}

// ────────── Handoff report (FR-017/018) ──────────

export type QuestionnaireScore = {
  type: string;
  totalScore: number;
  severity: string;
};

export type ReportRiskSignal = {
  level: "low" | "medium" | "high" | "critical";
  category: string | null;
  triggerMessageId: string | null;
};

export type ReportPatient = {
  id: string;
  name: string;
  birthYear: number;
  gender: string | null;
};

export type Citation = {
  field: string;
  source_message_id: string;
  quote: string;
};

export type HandoffNarrative = {
  chief_complaint: string;
  present_illness: string;
  symptoms: string[];
  onset: string | null;
  recent_changes: string | null;
  triggers: string[];
  sleep_appetite_activity: {
    sleep: string | null;
    appetite: string | null;
    activity: string | null;
  };
  psych_history: string | null;
  medications: string | null;
  documents_summary: string[];
  clinician_attention: string[];
  evidence: Citation[];
};

export type HandoffReport = {
  reportId: string;
  sessionId: string;
  status: "generating" | "ready" | "failed";
  generatedAt: string | null;
  failureReason: string | null;
  patient: ReportPatient | null;
  questionnaires: QuestionnaireScore[];
  riskSignals: ReportRiskSignal[];
  narrative: HandoffNarrative | null;
};

/** Returns null when the session has no report row yet (404). */
export async function getReport(sessionId: string): Promise<HandoffReport | null> {
  try {
    return await fetchAPI<HandoffReport>(`/api/v1/sessions/${sessionId}/report`);
  } catch (e) {
    if (e instanceof APIException && e.status === 404) return null;
    throw e;
  }
}
