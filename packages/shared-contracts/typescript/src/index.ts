/**
 * Neuro-Sync shared contracts (TypeScript).
 *
 * Platform API → mobile/web 응답 타입 단일 소스.
 * 본 골격은 Phase 1a Day 1~2 부트스트랩에 한정.
 * 실제 타입은 PRD §5.1 API 명세 구현 시점에 채운다.
 */

export const CONTRACTS_VERSION = "0.1.0" as const;

// Placeholder so the module isn't empty for `tsc --noEmit`.
export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
};
