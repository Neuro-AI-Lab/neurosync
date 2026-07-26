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
from dataclasses import dataclass

import httpx
from contracts.domain import DomainInferRequest, UtteranceTurn

from src.services.ai_client import AIClient

logger = logging.getLogger(__name__)

# 모듈 내부 전용 — 도메인 키를 밖으로 내보내지 않는다 (PRD v3 §4.1).
_DOMAIN_TO_INSTRUMENT: dict[str, str] = {
    "depression": "PHQ9",
    "anxiety": "GAD7",
    "alcohol": "AUDITC",
    # ADR-046 #2 / contract4 fix: mirrors ai-server's canonical
    # DOMAIN_TO_SCALE["panic"] == "GAD-7" (rag/questionnaire_mapping.py) —
    # anxiety-family precedent (DSM-5: Panic Disorder is an anxiety
    # disorder); see also golden_labels_f1f2.md VP-004's panic->anxiety
    # mapping. Without this entry a "panic" top1 candidate silently fell
    # to FALLBACK_INSTRUMENT below instead of routing to GAD7.
    "panic": "GAD7",
    # PLAN-2026-W30-INTEG P3-1(b) / CVR-049 register #3: mirrors ai-server's
    # canonical DOMAIN_TO_SCALE["substance"] == "AUDIT-C"
    # (rag/questionnaire_mapping.py:349). Without this entry a "substance"
    # top1 candidate silently fell to FALLBACK_INSTRUMENT (PHQ4) instead of
    # routing to AUDITC — same class of gap as the panic fix above.
    "substance": "AUDITC",
}

# 미결 #4 — 후보 없음·저신뢰 시 기본 문진. 정책 확정 시 이 상수만 바꾼다.
FALLBACK_INSTRUMENT = "PHQ4"

# 이 미만이면 저신뢰로 보고 폴백한다.
MIN_CONFIDENCE = 0.35

# PLAN-2026-W30-INTEG P3-0 (clinical-validator caveat-design consult) / P3-1(c):
# proxy-scale caveats for routings where the administered instrument is not a
# native scale for the inferred domain. Keyed by domain (module-internal only
# — never returned bare; always attached to the `InstrumentRouting.caveat`
# alongside the instrument ID, never the domain key itself). Verbatim wording
# from the consult; do not paraphrase.
_PROXY_CAVEATS: dict[str, str] = {
    "panic": (
        "GAD-7은 범불안(generalized anxiety) 척도로, panic 특이 증상(발작 빈도, "
        "상황성/자발성 구분, 죽을 것 같은 공포·비현실감, 광장공포 회피)을 직접 "
        "반영하지 않습니다. 이 결과는 panic 중증도의 proxy로만 해석하고, 점수와 "
        "무관하게 임상의 확인이 필요합니다."
    ),
    "substance": (
        "AUDIT-C는 알코올(음주) 소비·빈도 전용 스크리너입니다. 이 세션의 substance "
        "후보가 알코올이 아닌 물질(예: 각성제·아편유사제·대마 등)을 포함하는 경우, "
        "AUDIT-C 문항은 해당 물질 사용을 전혀 묻지 않으므로 이 결과가 실제 물질사용 "
        "양상을 반영하지 못할 수 있습니다. 알코올 특이적 스크리닝 결과로만 해석하고, "
        "비알코올 물질 사용 여부는 별도의 임상 확인이 필요합니다."
    ),
}


@dataclass(frozen=True)
class InstrumentRouting:
    """CVR-049 finding 2 "infer_instrument marker" direction — carries the
    resolved instrument PLUS, when the routing is a proxy (panic->GAD7,
    substance->AUDITC), the clinician/audit-facing caveat text.

    `caveat` is `None` for native routings (depression/anxiety/alcohol) and
    for the FALLBACK_INSTRUMENT path — never populated for a routing that
    is not an actual proxy. This struct itself carries no domain KEY (only
    instrument + prose caveat), so returning it does not regress the "only
    PHQ9|GAD7|AUDITC|PHQ4 leave this module" invariant for the *bare*
    `infer_instrument` API, which remains a thin wrapper returning only
    `.instrument` unchanged.
    """

    instrument: str
    caveat: str | None = None


async def _resolve_routing(
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    turns: list[tuple[int, str]],
    clinical_slots: dict[str, str] | None = None,
    crisis_triggered: bool = False,
) -> InstrumentRouting:
    """top1 도메인에 해당하는 문진 도구 + (proxy인 경우) caveat를 반환한다.

    Args:
        turns: [(turn_no, patient_message)] — 근거 소스. llm_only 모드에서는
            이것이 유일한 근거이므로 비어 있으면 곧장 폴백한다.

    Returns:
        `InstrumentRouting` — 절대 예외를 던지지 않는다.
    """
    if not turns:
        logger.info("domain routing: no utterances, using fallback (session=%s)", session_id)
        return InstrumentRouting(instrument=FALLBACK_INSTRUMENT)

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
        # BUG-091 권고 #3: "예산 초과(timeout)"와 그 외 전송/스키마 오류를 로그에서
        # 구분한다 — AIClientError는 `raise ... from exc`로 원인을 보존하므로
        # `__cause__`가 httpx.TimeoutException이면 timeout, 아니면 error다.
        # (여기서는 여전히 둘 다 동일하게 FALLBACK_INSTRUMENT로 떨어진다 — 이건
        # 관측성만 개선하는 것이지 폴백 동작 자체는 바뀌지 않는다.)
        reason = "timeout" if isinstance(exc.__cause__, httpx.TimeoutException) else "error"
        logger.warning(
            "domain routing fell back (session=%s, reason=%s): %s", session_id, reason, exc
        )
        return InstrumentRouting(instrument=FALLBACK_INSTRUMENT)

    candidates = [c for c in result.domain_candidates if c.confidence >= MIN_CONFIDENCE]
    if not candidates:
        logger.info(
            "domain routing: no candidate above %.2f, using fallback (session=%s)",
            MIN_CONFIDENCE,
            session_id,
        )
        return InstrumentRouting(instrument=FALLBACK_INSTRUMENT)

    top = max(candidates, key=lambda c: c.confidence)
    instrument = _DOMAIN_TO_INSTRUMENT.get(top.domain)
    if instrument is None:
        # trauma/sleep/psychosis/other — 전용 척도가 아직 없다.
        logger.info(
            "domain routing: top1 has no mapped instrument, using fallback (session=%s)",
            session_id,
        )
        return InstrumentRouting(instrument=FALLBACK_INSTRUMENT)

    # 로그에도 병명을 남기지 않는다 (NFR v3-2) — instrument ID만 남긴다.
    logger.info(
        "domain routing: session=%s instrument=%s confidence=%.2f",
        session_id,
        instrument,
        top.confidence,
    )
    return InstrumentRouting(instrument=instrument, caveat=_PROXY_CAVEATS.get(top.domain))


async def infer_instrument(
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    turns: list[tuple[int, str]],
    clinical_slots: dict[str, str] | None = None,
    crisis_triggered: bool = False,
) -> str:
    """top1 도메인에 해당하는 문진 도구 ID를 반환한다 (bare-string API, 하위호환 불변).

    Returns:
        "PHQ9" | "GAD7" | "AUDITC" | "PHQ4" — 절대 예외를 던지지 않는다.
    """
    routing = await _resolve_routing(
        ai_client=ai_client,
        session_id=session_id,
        turns=turns,
        clinical_slots=clinical_slots,
        crisis_triggered=crisis_triggered,
    )
    return routing.instrument


async def infer_instrument_with_caveat(
    *,
    ai_client: AIClient,
    session_id: uuid.UUID,
    turns: list[tuple[int, str]],
    clinical_slots: dict[str, str] | None = None,
    crisis_triggered: bool = False,
) -> InstrumentRouting:
    """PLAN-2026-W30-INTEG P3-1(c) — `infer_instrument`와 동일 로직이나 proxy
    caveat(clinician/audit-facing)도 함께 반환한다. `/ai/survey/plan` 배선
    (F3 plan 채널)에서만 쓰인다 — 환자 응답 경로(`infer_instrument`)는 여전히
    bare instrument 문자열만 쓴다."""
    return await _resolve_routing(
        ai_client=ai_client,
        session_id=session_id,
        turns=turns,
        clinical_slots=clinical_slots,
        crisis_triggered=crisis_triggered,
    )
