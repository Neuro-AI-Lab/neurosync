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

  start: (sessionId: string) => void;
  addUserMessage: (msg: LocalMessage) => void;
  markAcked: (idempotencyKey: string, messageId: string, safetyLevel: SafetyLevel) => void;
  setRisk: (risk: RiskEvent) => void;
  clearRisk: () => void;
  reset: () => void;
};

export const useSession = create<SessionState>((set) => ({
  sessionId: null,
  messages: [],
  lastRisk: null,

  start: (sessionId) => set({ sessionId, messages: [], lastRisk: null }),
  addUserMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  markAcked: (idempotencyKey, messageId, safetyLevel) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === idempotencyKey ? { ...m, messageId, safetyLevel } : m,
      ),
    })),
  setRisk: (risk) => set({ lastRisk: risk }),
  clearRisk: () => set({ lastRisk: null }),
  reset: () => set({ sessionId: null, messages: [], lastRisk: null }),
}));
