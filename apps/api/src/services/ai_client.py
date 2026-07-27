"""httpx-based client for apps/ai-server.

PRD §0.3 — Platform calls AI server over internal HTTP. mTLS comes in Phase 4.
Timeouts mirror PRD §4.1 SLA budgets (with a small safety margin).

모든 호출은 `_post`를 거친다 — 전송 오류(httpx)뿐 아니라 **응답 파싱/스키마
검증 실패(JSON decode, pydantic ValidationError)까지** AIClientError로 감싼다.
이게 빠지면 ai-server가 잘못된 200을 줄 때 예외가 호출자의 `except AIClientError`를
빠져나가 환자에게 500이 나간다(REV: PR#74 C1). 채점·라우팅의 폴백 보장은 이
래핑에 의존한다.
"""

from __future__ import annotations

from typing import TypeVar

import httpx
from contracts.chat import ChatRequest, ChatResponse
from contracts.domain import DomainInferRequest, DomainInferResponse
from contracts.handoff import HandoffRequest, HandoffResponse
from contracts.longitudinal import HandoffReportRequest, HandoffReportResponse
from contracts.nearby import NearbyHospitalsResponse
from contracts.ocr import OCRParseResponse
from contracts.safety import SafetyRequest, SafetyResponse
from contracts.slots import SlotsExtractRequest, SlotsExtractResponse
from contracts.stt import STTRequest, STTResponse
from contracts.survey import SurveyScoreRequest, SurveyScoreResponse
from contracts.survey_plan import SurveyPlanRequest, SurveyPlanResponse
from contracts.temporal import TemporalSummarizeRequest, TemporalSummarizeResponse
from pydantic import BaseModel, ValidationError

from src.core.config import Settings, get_settings

_TModel = TypeVar("_TModel", bound=BaseModel)


class AIClientError(RuntimeError):
    """Wraps any failure talking to apps/ai-server — transport OR response
    parsing/validation. Callers catch this to trigger their fallback."""


class AIClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=2.0)
        self._owned = client is None

    async def _post(
        self,
        path: str,
        model: type[_TModel],
        payload: BaseModel,
        *,
        timeout: float | None = None,
    ) -> _TModel:
        """POST + parse, with EVERYTHING inside one try.

        `resp.json()` raises json.JSONDecodeError (a ValueError) on a non-JSON
        body; `model_validate` raises pydantic ValidationError on schema drift.
        Both — not just httpx errors — must become AIClientError so callers can
        fall back instead of 500-ing.
        """
        url = f"{self._settings.ai_server_url}{path}"
        kwargs: dict = {"json": payload.model_dump(mode="json")}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            resp = await self._client.post(url, **kwargs)
            resp.raise_for_status()
            return model.model_validate(resp.json())
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            raise AIClientError(f"{path} failed: {exc}") from exc

    async def safety_classify(self, payload: SafetyRequest) -> SafetyResponse:
        """POST /ai/safety/classify.

        BUG-062 fix (EXP-031 fix_wave_design.md step 4, retiring the interim
        hand-built adapter that used to live here): `SafetyRequest`/
        `SafetyResponse` are now field-identical to ai-server's real
        `SafetyInput`/`SafetyOutput` wire shape, so this is the same generic
        `_post` path every other endpoint uses — no more manual dict-building
        or response re-mapping. The category-priority reduction that used to
        happen here (`_SAFETY_CATEGORY_MAP`/`_SAFETY_CATEGORY_PRIORITY`) now
        lives in `services/safety.py::to_safety_assessment` (domain-layer
        translation, single-sourced with the CVR-051 orchestrator-crisis
        category map — see that module).
        """
        return await self._post(
            "/ai/safety/classify",
            SafetyResponse,
            payload,
            timeout=self._settings.ai_safety_timeout_seconds,
        )

    async def chat_respond(self, payload: ChatRequest) -> ChatResponse:
        """POST /ai/chat/respond. Non-streaming dialogue turn; its own timeout
        (the full reply may take a few seconds, independent of the safety budget)."""
        return await self._post(
            "/ai/chat/respond",
            ChatResponse,
            payload,
            timeout=self._settings.ai_chat_timeout_seconds,
        )

    async def stt_transcribe(self, payload: STTRequest) -> STTResponse:
        """POST /ai/stt/transcribe. PRD §4.1 SLA < 2,000ms; the AI server runs
        its own vendor fallback chain within this budget."""
        return await self._post(
            "/ai/stt/transcribe",
            STTResponse,
            payload,
            timeout=self._settings.ai_stt_timeout_seconds,
        )

    async def handoff_generate(self, payload: HandoffRequest) -> HandoffResponse:
        """POST /ai/handoff/generate. Generation budget is generous (PRD §4.1
        p95 < 30s) so this call uses its own longer timeout."""
        return await self._post(
            "/ai/handoff/generate",
            HandoffResponse,
            payload,
            timeout=self._settings.ai_handoff_timeout_seconds,
        )

    async def handoff_report(
        self, payload: HandoffReportRequest
    ) -> HandoffReportResponse:
        """POST /ai/handoff/report. 결정론적(LLM 없음) F4+F5 통합 리포트 —
        12섹션 markdown + HL7 FHIR + editorial PDF + F4 차트. PDF/차트 렌더가
        있어 handoff_generate와 동일한 넉넉한 예산을 쓴다."""
        return await self._post(
            "/ai/handoff/report",
            HandoffReportResponse,
            payload,
            timeout=self._settings.ai_handoff_timeout_seconds,
        )

    # ── v3 추가 (PRD_frontend_v3 §6-A) ──────────────────────────────────

    async def survey_score(self, payload: SurveyScoreRequest) -> SurveyScoreResponse:
        """POST /ai/survey/score. 결정론적 채점(LLM 없음) — 빠른 기본 타임아웃."""
        return await self._post("/ai/survey/score", SurveyScoreResponse, payload)

    async def survey_plan(self, payload: SurveyPlanRequest) -> SurveyPlanResponse:
        """POST /ai/survey/plan. F3 문진 시행 계획 — 결정론적(LLM 없음),
        `survey_score`와 같은 기본 타임아웃(PLAN-2026-W30-INTEG P3-1(a))."""
        return await self._post("/ai/survey/plan", SurveyPlanResponse, payload)

    async def domain_infer(self, payload: DomainInferRequest) -> DomainInferResponse:
        """POST /ai/domain/infer. LLM 호출이라 chat과 비슷한 예산(60s)을 쓴다.

        BUG-091 (2026-07-26): 구 4.5s 예산은 실측 20.2s-30.6s latency를
        전혀 커버하지 못해 2/2 실세션이 예산 초과로 폴백했다(모바일 구
        NFR v3-3 "5초 상한"도 같은 계열의 잘못된 전제). 이 예산을 넘기거나
        오류가 나면 호출자(`domain_routing._resolve_routing`)가 폴백
        문진(PHQ4)으로 진행한다 — 라우팅은 예외를 던지지 않는다.
        """
        return await self._post(
            "/ai/domain/infer",
            DomainInferResponse,
            payload,
            timeout=self._settings.ai_domain_timeout_seconds,
        )

    async def nearby_hospitals(
        self, *, lat: float, lng: float, radius_km: float = 5.0, num_of_rows: int = 30
    ) -> NearbyHospitalsResponse:
        """GET /ai/nearby/hospitals (FR-049). 데이터 조회만 — 지도 렌더는 플랫폼.

        _post는 POST 전용이라 GET은 여기서 직접 보낸다(ocr_parse와 동일 예외 처리).
        HIRA 키 미설정 등으로 502가 나면 호출자가 빈 지도로 폴백한다.
        """
        url = f"{self._settings.ai_server_url}/ai/nearby/hospitals"
        try:
            resp = await self._client.get(
                url,
                params={
                    "lat": lat,
                    "lng": lng,
                    "radius_km": radius_km,
                    "num_of_rows": num_of_rows,
                },
                timeout=self._settings.ai_nearby_timeout_seconds,
            )
            resp.raise_for_status()
            return NearbyHospitalsResponse.model_validate(resp.json())
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            raise AIClientError(f"/ai/nearby/hospitals failed: {exc}") from exc

    async def temporal_summarize(
        self, payload: TemporalSummarizeRequest
    ) -> TemporalSummarizeResponse:
        """F4 종단 추론 — 직전/이번 방문 척도 비교 + plot_data (리포트 추이 차트)."""
        return await self._post(
            "/ai/temporal/summarize",
            TemporalSummarizeResponse,
            payload,
            timeout=self._settings.ai_temporal_timeout_seconds,
        )

    async def slots_extract(self, payload: SlotsExtractRequest) -> SlotsExtractResponse:
        """POST /ai/slots/extract. 대화 배경 작업 — 실패해도 대화를 막지 않는다."""
        return await self._post(
            "/ai/slots/extract",
            SlotsExtractResponse,
            payload,
            timeout=self._settings.ai_slots_timeout_seconds,
        )

    async def ocr_parse(
        self,
        *,
        document: bytes,
        filename: str,
        content_type: str,
        session_id: str,
        patient_id: str,
        document_type_hint: str = "unknown",
    ) -> OCRParseResponse:
        """POST /ai/ocr/parse (multipart). 처방전/진단서 파싱 (FR-048).

        _post는 JSON 전용이라 여기선 직접 multipart를 보낸다. 다른 메서드와
        동일하게 전송/파싱 실패를 통째로 AIClientError로 감싼다(PR#74 C1 원칙).
        """
        url = f"{self._settings.ai_server_url}/ai/ocr/parse"
        files = {"document": (filename, document, content_type)}
        data = {
            "session_id": session_id,
            "patient_id": patient_id,
            "document_type_hint": document_type_hint,
        }
        try:
            resp = await self._client.post(
                url, files=files, data=data, timeout=self._settings.ai_ocr_timeout_seconds
            )
            resp.raise_for_status()
            return OCRParseResponse.model_validate(resp.json())
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            raise AIClientError(f"/ai/ocr/parse failed: {exc}") from exc

    async def aclose(self) -> None:
        if self._owned:
            await self._client.aclose()


_singleton: AIClient | None = None


def get_ai_client() -> AIClient:
    """FastAPI dependency — reuses one connection pool across requests."""
    global _singleton
    if _singleton is None:
        _singleton = AIClient()
    return _singleton
