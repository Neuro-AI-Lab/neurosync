/**
 * RAG top1 문진 라우팅 (v3 FR-039/041).
 *
 * 대화 종료 시 플랫폼 프록시(`POST /sessions/:id/domain/infer`)를 호출하고
 * **문진 도구 ID 하나만** 받는다. 질환/도메인 문자열은 서버가 애초에 내려주지
 * 않으므로, 클라이언트 상태·화면·로그에 병명이 잔류할 방법이 없다 (NFR v3-2).
 *
 * 라우팅은 실패하지 않는다. 어떤 오류(타임아웃/5xx/네트워크)든 FALLBACK_SURVEY로
 * 진행한다 — 대화를 끝낸 환자를 막을 수 없다. 서버도 같은 원칙으로 폴백하므로
 * 이 클라이언트 폴백은 네트워크 단절 대비 2차 방어선이다.
 */

import { inferDomainInstrument, QuestionnaireType } from "./api";

/**
 * 폴백 문진 (미결 #4 확정 전 잠정값 — PRD v3 §3.1).
 * 서버 `services/domain_routing.FALLBACK_INSTRUMENT`와 같은 값이어야 한다.
 */
export const FALLBACK_SURVEY: QuestionnaireType = "PHQ4";

/**
 * '분석 중' 대기 상한. 초과 시 폴백 문진(FALLBACK_SURVEY)으로 진행 — 절대 throw
 * 하지 않는다는 원칙은 그대로다.
 *
 * BUG-091 (2026-07-26): 구 NFR(v3-3) "5초 상한" 전제가 서버 실측(20.2s-30.6s
 * live) 대비 완전히 틀렸음이 드러나 폐기됐다. 서버 `ai_domain_timeout_seconds`
 * 가 60s로 올라갔으므로, 서버 판정(진짜 top1 라우팅 vs 서버측 폴백)이 클라
 * 폴백보다 항상 먼저 나오도록 이 값은 서버 예산보다 커야 한다 — 75s
 * (서버 60s + 15s 왕복/처리 여유). 대기 UX는 `chat.tsx`의 증상확인 게이지가
 * 흡수한다(FR-041 2단계).
 */
export const INFER_TIMEOUT_MS = 75_000;

const VALID: readonly QuestionnaireType[] = ["PHQ9", "GAD7", "AUDITC", "PHQ4"];

/** 상한 시간 안에 끝나지 않으면 폴백으로 떨어뜨린다. */
function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(fallback), ms);
    p.then((v) => {
      clearTimeout(timer);
      resolve(v);
    }).catch(() => {
      clearTimeout(timer);
      resolve(fallback);
    });
  });
}

/**
 * top1 문진 도구를 결정한다. 절대 throw 하지 않는다.
 */
export async function inferTopSurvey(
  token: string | null,
  sessionId: string | null,
): Promise<QuestionnaireType> {
  if (!token || !sessionId) return FALLBACK_SURVEY;

  const result = await withTimeout(
    inferDomainInstrument(token, sessionId).then((r) => r.instrument),
    INFER_TIMEOUT_MS,
    FALLBACK_SURVEY,
  );

  // 서버가 알 수 없는 값을 주더라도 화면이 깨지지 않게 방어한다.
  return VALID.includes(result) ? result : FALLBACK_SURVEY;
}
