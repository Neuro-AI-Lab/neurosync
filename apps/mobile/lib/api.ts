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

import { API_BASE_URL } from "./config";
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

export type RegisterInput = {
  email: string;
  password: string;
  name: string;
  birthYear: number;
  gender: "male" | "female" | "other";
  phone: string;
  region: string;
  emergencyContact: string;
  consents: {
    tos: boolean;
    privacy: boolean;
    sensitive: boolean;
    riskNotification: boolean;
  };
};

export async function register(input: RegisterInput): Promise<TokenPair> {
  return request<TokenPair>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function login(
  email: string,
  password: string,
  role: "patient" | "clinician" | "org_admin" = "patient",
): Promise<TokenPair> {
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
  return request<SessionOut>("/api/v1/sessions", {
    method: "POST",
    token,
  });
}

// ────────── Questionnaires (FR-006/007) ──────────

export type QuestionnaireType = "PHQ9" | "GAD7";

export type QuestionnaireResult = {
  id: string;
  type: string;
  totalScore: number;
  severity: string;
  completedAt: string;
};

export async function submitQuestionnaire(
  token: string,
  sessionId: string,
  type: QuestionnaireType,
  answers: number[],
): Promise<QuestionnaireResult> {
  return request<QuestionnaireResult>(
    `/api/v1/sessions/${sessionId}/questionnaires`,
    {
      method: "POST",
      token,
      body: JSON.stringify({ type, answers }),
    },
  );
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
  return request<SubmitAccepted>(`/api/v1/sessions/${sessionId}/submit`, {
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
  return request<RiskEventAck>(`/api/v1/risk_events/${riskEventId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ aloneStatus }),
  });
}
