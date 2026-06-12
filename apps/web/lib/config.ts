/**
 * Server-side configuration.
 *
 * Production deployments MUST set `API_BASE_URL` to an https:// URL.
 * The TLS guard runs lazily on the first request (not at module load), so
 * `next build` doesn't need the production URL.
 */

export const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

/** Cookie names for the clinician session (httpOnly server-side). */
export const ACCESS_COOKIE = "ns_access";
export const REFRESH_COOKIE = "ns_refresh";
export const USER_COOKIE = "ns_user";

let tlsChecked = false;

/** Call before every outbound fetch — cheap and fail-fast at runtime. */
export function assertProductionTLS(): void {
  if (tlsChecked) return;
  if (process.env.NODE_ENV !== "production") {
    tlsChecked = true;
    return;
  }
  if (!API_BASE_URL.startsWith("https://")) {
    throw new Error(
      "[neuro-sync/web] Production deployments require API_BASE_URL to start with https://",
    );
  }
  tlsChecked = true;
}
