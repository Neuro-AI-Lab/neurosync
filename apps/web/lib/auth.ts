/**
 * Server-side auth helpers — cookie set/clear plus a `requireSession()` guard
 * for protected route handlers.
 */

import "server-only";

import { cookies } from "next/headers";

import { ACCESS_COOKIE, REFRESH_COOKIE, TLS_EXEMPT, USER_COOKIE } from "./config";

export type SessionUser = {
  userId: string;
  role: "clinician" | "org_admin";
  email: string;
};

const COMMON_COOKIE_OPTS = {
  httpOnly: true,
  // `Secure` requires the browser's own connection to this app be https.
  // Under the closed-network DGX demo exemption (API_TLS_EXEMPT=1, see
  // lib/config.ts) the web frontend itself is served over plain http, so a
  // `Secure` cookie would never round-trip back and login would silently
  // fail to persist — same underlying no-TLS condition as the API guard.
  secure: process.env.NODE_ENV === "production" && !TLS_EXEMPT,
  sameSite: "lax",
  path: "/",
} as const;

export async function setSessionCookies(args: {
  accessToken: string;
  refreshToken: string;
  user: SessionUser;
  expiresInSec: number;
}): Promise<void> {
  const store = await cookies();
  store.set(ACCESS_COOKIE, args.accessToken, {
    ...COMMON_COOKIE_OPTS,
    maxAge: args.expiresInSec,
  });
  store.set(REFRESH_COOKIE, args.refreshToken, {
    ...COMMON_COOKIE_OPTS,
    maxAge: 60 * 60 * 24 * 7, // 7d
  });
  store.set(USER_COOKIE, JSON.stringify(args.user), {
    ...COMMON_COOKIE_OPTS,
    httpOnly: false, // readable client-side for header chrome
    maxAge: 60 * 60 * 24 * 7,
  });
}

export async function clearSessionCookies(): Promise<void> {
  const store = await cookies();
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE, USER_COOKIE]) {
    store.set(name, "", { ...COMMON_COOKIE_OPTS, maxAge: 0 });
  }
}

export async function getSessionUser(): Promise<SessionUser | null> {
  const store = await cookies();
  const raw = store.get(USER_COOKIE);
  if (!raw?.value) return null;
  try {
    return JSON.parse(raw.value) as SessionUser;
  } catch {
    return null;
  }
}
