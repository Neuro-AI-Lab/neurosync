/**
 * RAG top1 문진 라우팅 (v3 FR-039/041).
 *
 * 대화 종료 시 도메인 추정을 백그라운드로 호출하고 top1 도메인에 해당하는
 * 문진 도구 ID만 반환한다. 질환/도메인 문자열은 이 모듈 밖으로 내보내지
 * 않는다 — 화면·상태·로그에 병명이 잔류하지 않도록 구조적으로 차단
 * (NFR v3-2, v3 원칙 1).
 *
 * ⚠️ 플랫폼 프록시(§6-A, 미결 #1)가 아직 없어 실제 `/ai/domain/infer` 호출은
 * 비활성 상태다. `DOMAIN_INFER_ENABLED`를 켜기 전까지는 목(mock) 추정으로
 * UI/로딩/폴백 흐름을 검증한다 — PRD §7 선구현 전략.
 */

import { QuestionnaireType } from "./api";
import { API_BASE_URL } from "./config";

/**
 * 폴백 문진 (미결 #4 확정 전 잠정값 — PRD §3.1).
 * 도구 확정(PHQ-4 한국어판 검증 포함) 시 이 상수만 교체한다.
 * §6-D(type 확장) 배포 전에는 서버가 PHQ4 저장을 거부하므로, 데모 컨틴전시
 * (§10)에서는 "PHQ9"로 임시 전환할 수 있다.
 */
export const FALLBACK_SURVEY: QuestionnaireType = "PHQ4";

/** '분석 중' 대기 상한 — NFR(v3-3). 초과 시 폴백 문진으로 진행. */
export const INFER_TIMEOUT_MS = 5_000;

/** §6-A 프록시 배포 후 true로 전환 (미결 #1). */
const DOMAIN_INFER_ENABLED = false;

/** 도메인 → 문진 매핑 (PRD §4.1). 모듈 내부 전용 — 외부로 도메인 키를 노출하지 않는다. */
const DOMAIN_TO_SURVEY: Record<string, QuestionnaireType> = {
  depression: "PHQ9",
  anxiety: "GAD7",
  alcohol: "AUDITC",
};

/** 프록시 배포 전 목 추정 — 데모 기본 시나리오(우울 → PHQ-9)로 라우팅. */
async function mockInfer(): Promise<QuestionnaireType> {
  // '분석 중' 로딩이 실제처럼 보이도록 짧은 지연을 둔다 (FR-041).
  await new Promise((resolve) => setTimeout(resolve, 1_800));
  return "PHQ9";
}

/**
 * top1 문진 도구를 결정한다. 어떤 실패(5xx/타임아웃/저신뢰/미배포)에서도
 * throw 하지 않고 FALLBACK_SURVEY를 반환한다 — 라우팅은 항상 성공해야 한다.
 */
export async function inferTopSurvey(
  token: string | null,
  sessionId: string | null,
): Promise<QuestionnaireType> {
  if (!DOMAIN_INFER_ENABLED || !token || !sessionId) {
    return mockInfer();
  }

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), INFER_TIMEOUT_MS);
    // §6-A 프록시 경로(제안): POST /api/v1/sessions/:id/domain/infer
    // 프록시 계약 확정 시 lib/api.ts의 request()로 이관한다.
    const res = await fetch(`${API_BASE_URL}/api/v1/sessions/${sessionId}/domain/infer`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return FALLBACK_SURVEY;
    const body = (await res.json()) as { top1?: string };
    // 저신뢰/후보 없음 → 서버가 top1을 비워 보냄 → 폴백.
    return (body.top1 && DOMAIN_TO_SURVEY[body.top1]) || FALLBACK_SURVEY;
  } catch {
    return FALLBACK_SURVEY;
  }
}
