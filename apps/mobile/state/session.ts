/**
 * Active session Zustand store.
 * Tracks the current session id, in-flight messages, last received safety
 * event, and idempotency keys we've assigned to outgoing messages.
 */

import { create } from "zustand";

import type { SafetyLevel } from "../lib/ws";

export type LocalMessage = {
  /** Stable UI key — client-generated idempotency key (UUID v4). */
  id: string;
  /** Server-issued message id, filled when the ack arrives. */
  messageId?: string;
  role: "user" | "ai";
  content: string;
  sentAt: number;
  safetyLevel?: SafetyLevel;
};

export type RiskEvent = {
  level: SafetyLevel;
  category: string;
  riskEventId: string;
  triggerMessageId: string;
  routeTo: "/emergency" | "/self_hotline";
  hotlines: Array<{ name: string; number: string }>;
  reason: string;
};

export type SessionState = {
  sessionId: string | null;
  messages: LocalMessage[];
  lastRisk: RiskEvent | null;
  /** Intake completeness 0..1 (FR-004), reported by the AI via ai:complete. */
  progress: number;
  /**
   * FR-048 — OCR 확인 화면([확인 완료])이 대화로 흘려보낼 요약 텍스트.
   * ocr-confirm 화면은 WS 클라이언트가 없어 직접 전송할 수 없으므로, 여기에
   * 큐잉하고 chat 화면이 소켓 open 시점에 사용자 메시지로 전송한다(전송 후 clear).
   */
  pendingInjection: string | null;

  start: (sessionId: string) => void;
  addUserMessage: (msg: LocalMessage) => void;
  addAiMessage: (msg: LocalMessage) => void;
  markAcked: (idempotencyKey: string, messageId: string, safetyLevel: SafetyLevel) => void;
  setRisk: (risk: RiskEvent) => void;
  clearRisk: () => void;
  setProgress: (ratio: number) => void;
  setPendingInjection: (text: string) => void;
  clearPendingInjection: () => void;
  reset: () => void;
};

export const useSession = create<SessionState>((set) => ({
  sessionId: null,
  messages: [],
  lastRisk: null,
  progress: 0,
  pendingInjection: null,

  start: (sessionId) =>
    set({ sessionId, messages: [], lastRisk: null, progress: 0, pendingInjection: null }),
  addUserMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  addAiMessage: (msg) =>
    set((s) =>
      // Guard against a replayed ai:complete adding the same bubble twice.
      s.messages.some((m) => m.id === msg.id)
        ? s
        : { messages: [...s.messages, msg] },
    ),
  markAcked: (idempotencyKey, messageId, safetyLevel) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === idempotencyKey ? { ...m, messageId, safetyLevel } : m,
      ),
    })),
  setRisk: (risk) => set({ lastRisk: risk }),
  clearRisk: () => set({ lastRisk: null }),
  // Progress is monotonic — never let a late/replayed frame walk it backwards.
  setProgress: (ratio) => set((s) => ({ progress: Math.max(s.progress, ratio) })),
  setPendingInjection: (text) => set({ pendingInjection: text }),
  clearPendingInjection: () => set({ pendingInjection: null }),
  reset: () =>
    set({ sessionId: null, messages: [], lastRisk: null, progress: 0, pendingInjection: null }),
}));
