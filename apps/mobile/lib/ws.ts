/**
 * Session chat WebSocket client.
 *
 * Implements the PRD §5.1 C-7 handshake:
 * - Connect via plain ws://… (no token in URL / no Sec-WebSocket-Protocol token)
 * - Send `auth:connect` initial frame within 5s
 * - Wait for `auth:connected` before sending user messages
 *
 * Hardenings (Phase 1a Day 8+):
 * - Client-side 5s `auth:connect` timer — if the server never replies,
 *   we close 1008 instead of getting stuck in `connecting`.
 * - `auth:refresh_required` → caller-provided `onTokenRefreshRequired`
 *   hook mints a new access token (REST refresh) and replies with
 *   `auth:refresh`. If the refresh fails the socket closes.
 * - Reconnect: exponential backoff 500ms→30s with `maxAttempts=10`.
 *   No retry when the last close was an auth failure we couldn't recover.
 *
 * Mobile path note: React Native's WebSocket does not let callers set the
 * `Origin` header. The server's mobile origin policy (PRD §5.1 line 577
 * Origin whitelist) currently treats absent Origin from `expo` user-agent
 * as mobile-allowed. Documented so a future server hardening doesn't
 * silently break the mobile client.
 */

import { WS_BASE_URL } from "./config";

export type SafetyLevel = "low" | "medium" | "high" | "critical";

export type WSEvent =
  | { type: "auth:connected"; payload: { sessionId: string } }
  | { type: "auth:error"; payload: { code: string } }
  | { type: "auth:refresh_required"; payload: { graceMs?: number } }
  | {
      type: "risk:detected";
      payload: {
        level: SafetyLevel;
        category: string;
        triggerMessageId: string;
        routeTo: "/emergency" | "/self_hotline";
        hotlines: Array<{ name: string; number: string }>;
        reason: string;
      };
    }
  | {
      type: "user:message:received";
      payload: {
        messageId: string;
        idempotencyKey?: string;
        safetyLevel: SafetyLevel;
        latencyMs: number;
      };
    }
  | { type: "error"; payload: { code: string; details?: unknown[] } };

export type WSStatus =
  | "idle"
  | "connecting"
  | "open"
  | "closing"
  | "closed"
  | "auth_failed"
  | "exhausted";

export type SendMessageInput = {
  content: string;
  inputModality?: "text" | "voice";
  idempotencyKey: string;
};

type Handler = (event: WSEvent) => void;
type StatusListener = (status: WSStatus) => void;

const MAX_BACKOFF_MS = 30_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const AUTH_HANDSHAKE_TIMEOUT_MS = 5_000;

export class SessionChatClient {
  private socket: WebSocket | null = null;
  private status: WSStatus = "idle";
  private handlers: Set<Handler> = new Set();
  private statusListeners: Set<StatusListener> = new Set();
  private backoffMs = 500;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private authTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;
  private authed = false;
  private attempts = 0;
  private accessToken: string;

  /**
   * onTokenRefreshRequired: server sent `auth:refresh_required`. The caller
   * runs the REST `/auth/refresh` flow and resolves with a fresh access
   * token, OR returns null if refresh fails. Returning null causes a
   * graceful close — the UI should then redirect to login.
   */
  constructor(
    private readonly sessionId: string,
    initialAccessToken: string,
    private readonly onTokenRefreshRequired?: () => Promise<string | null>,
  ) {
    this.accessToken = initialAccessToken;
  }

  /** Hot-swap the token without tearing down the socket. */
  setAccessToken(token: string): void {
    this.accessToken = token;
  }

  on(handler: Handler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => {
      this.statusListeners.delete(listener);
    };
  }

  private setStatus(next: WSStatus): void {
    this.status = next;
    for (const l of this.statusListeners) l(next);
  }

  connect(): void {
    if (this.status === "connecting" || this.status === "open") return;
    if (this.status === "exhausted" || this.status === "auth_failed") return;
    this.intentionalClose = false;
    this.setStatus("connecting");
    this.authed = false;

    const url = `${WS_BASE_URL}/api/v1/sessions/${encodeURIComponent(this.sessionId)}/chat`;
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          type: "auth:connect",
          payload: { accessToken: this.accessToken },
        }),
      );
      this.clearAuthTimer();
      this.authTimer = setTimeout(() => {
        if (!this.authed && this.socket !== null) {
          try {
            this.socket.close(1008, "AUTH_TIMEOUT");
          } catch {
            // ignore
          }
        }
      }, AUTH_HANDSHAKE_TIMEOUT_MS);
    };

    socket.onmessage = (evt) => {
      let data: WSEvent | null = null;
      try {
        data = JSON.parse(evt.data as string) as WSEvent;
      } catch {
        return;
      }
      if (data === null) return;

      if (data.type === "auth:connected") {
        this.authed = true;
        this.backoffMs = 500;
        this.attempts = 0;
        this.clearAuthTimer();
        this.setStatus("open");
      } else if (data.type === "auth:refresh_required") {
        void this.handleRefreshRequired();
      } else if (data.type === "auth:error") {
        // Auth failure — don't reconnect with the same token.
        this.intentionalClose = true;
        this.setStatus("auth_failed");
      }
      for (const h of this.handlers) h(data);
    };

    socket.onerror = () => {
      // onclose will fire next; handle reconnect there.
    };

    socket.onclose = () => {
      this.clearAuthTimer();
      this.socket = null;
      const wasAuthed = this.authed;
      this.authed = false;
      if (this.intentionalClose) {
        if (this.status !== "auth_failed") this.setStatus("closed");
        return;
      }
      this.setStatus("closed");
      if (!wasAuthed) return;
      if (this.attempts >= MAX_RECONNECT_ATTEMPTS) {
        this.setStatus("exhausted");
        return;
      }
      this.scheduleReconnect();
    };
  }

  private async handleRefreshRequired(): Promise<void> {
    if (!this.onTokenRefreshRequired || !this.socket) return;
    try {
      const fresh = await this.onTokenRefreshRequired();
      if (fresh === null) {
        try {
          this.socket?.close(1008, "REFRESH_FAILED");
        } catch {
          // ignore
        }
        this.setStatus("auth_failed");
        return;
      }
      this.accessToken = fresh;
      this.socket?.send(
        JSON.stringify({
          type: "auth:refresh",
          payload: { accessToken: fresh },
        }),
      );
    } catch {
      try {
        this.socket?.close(1008, "REFRESH_FAILED");
      } catch {
        // ignore
      }
      this.setStatus("auth_failed");
    }
  }

  private clearAuthTimer(): void {
    if (this.authTimer !== null) {
      clearTimeout(this.authTimer);
      this.authTimer = null;
    }
  }

  private scheduleReconnect(): void {
    this.attempts += 1;
    const delay = this.backoffMs;
    this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  sendMessage(input: SendMessageInput): boolean {
    if (this.socket === null || this.status !== "open" || !this.authed) {
      return false;
    }
    this.socket.send(
      JSON.stringify({
        type: "user:message",
        payload: {
          content: input.content,
          inputModality: input.inputModality ?? "text",
          idempotencyKey: input.idempotencyKey,
        },
      }),
    );
    return true;
  }

  close(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearAuthTimer();
    if (this.socket !== null) {
      this.setStatus("closing");
      this.socket.close();
      this.socket = null;
    } else {
      this.setStatus("closed");
    }
  }
}
