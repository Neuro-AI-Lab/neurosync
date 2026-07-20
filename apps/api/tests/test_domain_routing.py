"""v3 FR-039 — top1 도메인 → 문진 도구 라우팅.

핵심 불변조건 두 가지를 고정한다:
1. 라우팅은 절대 실패하지 않는다 (어떤 오류든 폴백 문진으로).
2. 응답에 질환/도메인 문자열이 새지 않는다 — 반환 타입이 도구 ID뿐 (NFR v3-2).
"""

from __future__ import annotations

import uuid

import pytest
from contracts.domain import DomainCandidate, DomainEvidence, DomainInferResponse

from src.services.ai_client import AIClientError
from src.services.domain_routing import (
    FALLBACK_INSTRUMENT,
    MIN_CONFIDENCE,
    infer_instrument,
)

SESSION = uuid.uuid4()
TURNS = [(1, "요즘 한 달 넘게 잠을 잘 못 자요."), (2, "아침엔 아무 의욕이 없어요.")]


class _FakeClient:
    """domain_infer만 흉내내는 최소 스텁."""

    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list = []

    async def domain_infer(self, payload):
        self.calls.append(payload)
        if self._error is not None:
            raise self._error
        return self._result


def _candidate(domain: str, confidence: float) -> DomainCandidate:
    return DomainCandidate(
        domain=domain,
        confidence=confidence,
        evidence=[DomainEvidence(source_type="utterance", source_id="turn_1", quote="…")],
    )


def _response(*candidates: DomainCandidate) -> DomainInferResponse:
    return DomainInferResponse(domain_candidates=list(candidates))


# ────────── 정상 라우팅 ──────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("domain", "expected"),
    [("depression", "PHQ9"), ("anxiety", "GAD7"), ("alcohol", "AUDITC")],
)
async def test_maps_top_domain_to_instrument(domain: str, expected: str) -> None:
    client = _FakeClient(result=_response(_candidate(domain, 0.9)))
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    assert got == expected


@pytest.mark.asyncio
async def test_picks_highest_confidence_candidate() -> None:
    client = _FakeClient(
        result=_response(_candidate("anxiety", 0.4), _candidate("depression", 0.85))
    )
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    assert got == "PHQ9"


# ────────── 폴백: 라우팅은 실패하지 않는다 ──────────


@pytest.mark.asyncio
async def test_ai_server_error_falls_back() -> None:
    client = _FakeClient(error=AIClientError("boom"))
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    assert got == FALLBACK_INSTRUMENT


@pytest.mark.asyncio
async def test_no_candidates_falls_back() -> None:
    client = _FakeClient(result=_response())
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    assert got == FALLBACK_INSTRUMENT


@pytest.mark.asyncio
async def test_low_confidence_falls_back() -> None:
    client = _FakeClient(result=_response(_candidate("depression", MIN_CONFIDENCE - 0.01)))
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    assert got == FALLBACK_INSTRUMENT


@pytest.mark.asyncio
async def test_unmapped_domain_falls_back() -> None:
    """trauma/sleep/psychosis 등은 전용 척도가 아직 없다."""
    client = _FakeClient(result=_response(_candidate("trauma", 0.95)))
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    assert got == FALLBACK_INSTRUMENT


@pytest.mark.asyncio
async def test_no_utterances_skips_call_entirely() -> None:
    """근거가 없으면 LLM을 부르지 않고 곧장 폴백 — 불필요한 지연 방지."""
    client = _FakeClient(result=_response(_candidate("depression", 0.9)))
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=[])
    assert got == FALLBACK_INSTRUMENT
    assert client.calls == []


# ────────── 계약: 도메인 문자열 비노출 ──────────


@pytest.mark.asyncio
async def test_returns_only_instrument_id() -> None:
    """반환값은 도구 ID 문자열뿐이어야 한다 (NFR v3-2)."""
    client = _FakeClient(result=_response(_candidate("depression", 0.9)))
    got = await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    assert got in {"PHQ9", "GAD7", "AUDITC", "PHQ4"}
    assert "depression" not in got


@pytest.mark.asyncio
async def test_sends_llm_only_mode_and_utterances() -> None:
    """플랫폼은 Stage 1 검색을 하지 않으므로 llm_only + 발화 근거로 호출한다."""
    client = _FakeClient(result=_response(_candidate("depression", 0.9)))
    await infer_instrument(ai_client=client, session_id=SESSION, turns=TURNS)
    sent = client.calls[0]
    assert sent.retrieval_mode == "llm_only"
    assert [t.turn for t in sent.turns] == [1, 2]
