"""v3 FR-039 — RAG top1 도메인 → 문진 도구 라우팅.

ai-server `/ai/domain/infer`(F2 Stage 2)를 호출하고, **도구 ID 하나만** 돌려준다.

NFR(v3-2) 질환명 비노출을 코드 구조로 강제한다:
- 이 모듈 밖으로 나가는 값은 `PHQ9 | GAD7 | AUDITC | PHQ4` 뿐이다.
- 도메인 문자열(depression/anxiety/…)은 여기서만 존재하고 응답·로그에 남기지 않는다.
  (로그에도 병명 대신 도구 ID를 남긴다.)

라우팅 실패는 예외가 아니라 폴백이다 — 대화를 끝낸 환자를 막을 수 없다.
어떤 실패(타임아웃/5xx/후보 없음/저신뢰)든 FALLBACK_INSTRUMENT로 진행한다.
"""

from __future__ import annotations

import logging
import uuid

from contracts.domain import DomainInferRequest, UtteranceTurn

from src.services.ai_client import AIClient

logger = logging.getLogger(__name__)

# 모듈 내부 전용 — 도메인 키를 밖으로 내보내지 않는다 (PRD v3 §4.1).
_DOMAIN_TO_INSTRUMENT: dict[str, str] = {
    "depression": "PHQ9",
    "anxiety": "GAD7",
    "alcohol": "AUDITC",
}

# 미결 #4 — 후보 없음·저신뢰 시 기본 문진. 정책 확정 시 이 상수만 바꾼다.
FALLBACK_INSTRUMENT = "PHQ4"

# 이 미만이면 저신뢰로 보고 폴백한다.
MIN_CONFIDENCE = 0.35


async def infer_instrument(
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    turns: list[tuple[int, str]],
    clinical_slots: dict[str, str] | None = None,
    crisis_triggered: bool = False,
) -> str:
    """top1 도메인에 해당하는 문진 도구 ID를 반환한다.

    Args:
        turns: [(turn_no, patient_message)] — 근거 소스. llm_only 모드에서는
            이것이 유일한 근거이므로 비어 있으면 곧장 폴백한다.

    Returns:
        "PHQ9" | "GAD7" | "AUDITC" | "PHQ4" — 절대 예외를 던지지 않는다.
    """
    if not turns:
        logger.info("domain routing: no utterances, using fallback (session=%s)", session_id)
        return FALLBACK_INSTRUMENT

    # "라우팅은 실패하지 않는다" — 요청 조립(중첩 슬롯값 등으로 ValidationError
    # 가능)부터 호출까지 통째로 감싸고, 어떤 예외든 폴백으로 떨어뜨린다.
    try:
        payload = DomainInferRequest(
            session_id=str(session_id),
            # final_slots는 dict[str,str] 계약 — 비문자열 값은 문자열화해 검증 실패를 막는다.
            final_slots={str(k): str(v) for k, v in (clinical_slots or {}).items()},
            crisis_triggered=crisis_triggered,
            turns=[UtteranceTurn(turn=n, patient_message=m) for n, m in turns],
            # Stage 1(RAG 검색)은 플랫폼이 수행하지 않는다 — 근거는 환자 발화뿐.
            retrieval_mode="llm_only",
        )
        result = await ai_client.domain_infer(payload)
    except Exception as exc:  # noqa: BLE001 — 라우팅은 어떤 실패에서도 폴백한다
        logger.warning("domain routing fell back (session=%s): %s", session_id, exc)
        return FALLBACK_INSTRUMENT

    candidates = [c for c in result.domain_candidates if c.confidence >= MIN_CONFIDENCE]
    if not candidates:
        logger.info(
            "domain routing: no candidate above %.2f, using fallback (session=%s)",
            MIN_CONFIDENCE,
            session_id,
        )
        return FALLBACK_INSTRUMENT

    top = max(candidates, key=lambda c: c.confidence)
    instrument = _DOMAIN_TO_INSTRUMENT.get(top.domain)
    if instrument is None:
        # trauma/sleep/psychosis/substance/other — 전용 척도가 아직 없다.
        logger.info(
            "domain routing: top1 has no mapped instrument, using fallback (session=%s)",
            session_id,
        )
        return FALLBACK_INSTRUMENT

    # 로그에도 병명을 남기지 않는다 (NFR v3-2).
    logger.info(
        "domain routing: session=%s instrument=%s confidence=%.2f",
        session_id,
        instrument,
        top.confidence,
    )
    return instrument
