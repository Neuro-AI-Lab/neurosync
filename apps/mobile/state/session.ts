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

  start: (sessionId: string) => void;
  addUserMessage: (msg: LocalMessage) => void;
  addAiMessage: (msg: LocalMessage) => void;
  markAcked: (idempotencyKey: string, messageId: string, safetyLevel: SafetyLevel) => void;
  setRisk: (risk: RiskEvent) => void;
  clearRisk: () => void;
  setProgress: (ratio: number) => void;
  reset: () => void;
};

export const useSession = create<SessionState>((set) => ({
  sessionId: null,
  messages: [],
  lastRisk: null,
  progress: 0,

  start: (sessionId) => set({ sessionId, messages: [], lastRisk: null, progress: 0 }),
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
  reset: () => set({ sessionId: null, messages: [], lastRisk: null, progress: 0 }),
}));
