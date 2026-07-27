/**
 * Server-side configuration.
 *
 * Production deployments MUST set `API_BASE_URL` to an https:// URL.
 * The TLS guard runs lazily on the first request (not at module load), so
 * `next build` doesn't need the production URL.
 *
 * Closed-network demo exception: set `API_TLS_EXEMPT=1` to allow a plain
 * http:// API_BASE_URL under NODE_ENV=production. This exists solely for the
 * DGX compose deployment (infra/deploy/docker-compose.dgx.yml), which runs
 * on an isolated demo network with no public exposure and no TLS
 * termination in front of it — never set this for an internet-reachable
 * deployment. Default is unset (fail-fast preserved).
 */

export const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

/** Cookie names for the clinician session (httpOnly server-side). */
export const ACCESS_COOKIE = "ns_access";
export const REFRESH_COOKIE = "ns_refresh";
export const USER_COOKIE = "ns_user";

/**
 * True only when the operator has explicitly opted into the closed-network
 * TLS exemption. Also read by lib/auth.ts to decide whether session cookies
 * require the `Secure` attribute — on the same closed-network demo, the web
 * frontend itself is served over plain http, so a `Secure` cookie would
 * never be sent back by the browser and login would silently fail to
 * persist. Both exemptions are gated by the same variable because they are
 * the same underlying condition (no TLS anywhere on this deployment), not
 * two independent risks.
 */
export const TLS_EXEMPT = process.env.API_TLS_EXEMPT === "1";

let tlsChecked = false;

/** Call before every outbound fetch — cheap and fail-fast at runtime. */
export function assertProductionTLS(): void {
  if (tlsChecked) return;
  if (process.env.NODE_ENV !== "production") {
    tlsChecked = true;
    return;
  }
  if (TLS_EXEMPT) {
    tlsChecked = true;
    return;
  }
  if (!API_BASE_URL.startsWith("https://")) {
    throw new Error(
      "[neuro-sync/web] Production deployments require API_BASE_URL to start with https://" +
        " (set API_TLS_EXEMPT=1 only for the closed-network DGX demo)",
    );
  }
  tlsChecked = true;
}
