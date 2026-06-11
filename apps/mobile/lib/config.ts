/**
 * Runtime configuration — resolves API base URLs by platform.
 *
 * Order of resolution:
 * 1. EXPO_PUBLIC_API_BASE_URL / WS_BASE_URL env vars (Expo bundles `EXPO_PUBLIC_*`)
 * 2. iOS simulator → http://localhost:8000
 * 3. Android emulator → http://10.0.2.2:8000 (loopback to host)
 * 4. Fallback → http://localhost:8000
 *
 * Override on a physical device by exporting EXPO_PUBLIC_API_BASE_URL before
 * `expo start --dev-client`.
 *
 * SECURITY (PRD §4.5.2 TLS 1.3 강제):
 * - In production (`__DEV__ === false`) the URLs MUST be `https://` and `wss://`.
 * - We throw at module-load time so a misconfigured release build fails fast
 *   instead of silently sending plaintext over the wire.
 */

import { Platform } from "react-native";

function platformLocalhost(port: number): string {
  if (Platform.OS === "android") {
    return `http://10.0.2.2:${port}`;
  }
  return `http://localhost:${port}`;
}

function envOr(envKey: string, fallback: string): string {
  // EXPO_PUBLIC_* env vars are inlined into the bundle at build time
  const v = (process.env as Record<string, string | undefined>)[envKey];
  return v && v.length > 0 ? v : fallback;
}

export const API_BASE_URL = envOr(
  "EXPO_PUBLIC_API_BASE_URL",
  platformLocalhost(8000),
);

export const WS_BASE_URL = envOr(
  "EXPO_PUBLIC_WS_BASE_URL",
  platformLocalhost(8000).replace(/^http/, "ws"),
);

if (!__DEV__) {
  if (!API_BASE_URL.startsWith("https://")) {
    throw new Error(
      "[neuro-sync] Production builds require EXPO_PUBLIC_API_BASE_URL to start with https://",
    );
  }
  if (!WS_BASE_URL.startsWith("wss://")) {
    throw new Error(
      "[neuro-sync] Production builds require EXPO_PUBLIC_WS_BASE_URL to start with wss://",
    );
  }
}
