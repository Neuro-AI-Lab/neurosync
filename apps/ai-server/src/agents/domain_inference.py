"""DomainInference agent — RAG 기반 정신건강 영역/진료과 후보 추론 (F2).

PLAN-2026-W28-C C-2/C-3: 2단계(Stage 1 코드 검색 + Stage 2 LLM 1회 호출) 중
이 클래스는 Stage 2만 담당한다. Stage 1(rag/retrieval.py 프리미티브 재사용,
DB 실패 시 mode=llm_only 강등)은 호출자(src/f2.py)의 책임이다 — 이 agent는
이미 검색된 chunk(있다면)를 ``DomainInferenceInput.retrieved_chunks``로 받는다.

위험 표현은 이 agent의 confidence 근거로 쓰이지 않는다(Safety 파이프라인
소관) — 프롬프트 절대 규칙 2. 코드 레벨 근거-화이트리스트는 별도
(``src.eval.f2_grounding``)가 담당하며, 이 파일은 LLM 호출/파싱만 한다.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.domain_inference import (
    DomainInferenceInput,
    DomainInferenceLLMResponse,
    DomainInferenceOutput,
    RetrievalMeta,
)

logger = logging.getLogger(__name__)

_PROMPT_AGENT_NAME = "domain_inference"
# PLAN-2026-W28-C — new agent, first version.
PROMPT_VERSION = "v1"

_LLM_FALLBACK_PROMPT = (
    "환자 슬롯/근거를 바탕으로 정신건강 영역 후보(최대 3개, evidence 필수)와 "
    "진료과 후보를 JSON으로만 출력하세요. 진단하지 않습니다."
)


def _build_user_content(inp: DomainInferenceInput) -> str:
    """Serialize F1(+F3) context and Stage-1 retrieval results for the LLM."""
    parts: list[str] = []

    parts.append("## 수집된 슬롯")
    if inp.final_slots:
        for k, v in inp.final_slots.items():
            if v:
                parts.append(f"- {k}: {v}")
    else:
        parts.append("- (수집된 슬롯 없음)")

    parts.append(f"\n## 방문 유형: {'초진' if inp.is_first_visit else '재진'}")

    parts.append("\n## 위험 정보 (참고용 — domain confidence의 근거로 사용 금지)")
    parts.append(f"- session_ctrs: {inp.session_ctrs}")
    parts.append(f"- crisis_triggered: {inp.crisis_triggered}")
    if inp.crisis_turn is not None:
        parts.append(f"- crisis_turn: {inp.crisis_turn}")

    if inp.scale_scores:
        parts.append("\n## 척도 점수")
        for s in inp.scale_scores:
            parts.append(f"- {s.scale_name}: {s.total_score} ({s.severity})")

    if inp.retrieved_chunks:
        parts.append("\n## 검색된 근거 청크 (source_type=rag_chunk, source_id=chunk_id)")
        for c in inp.retrieved_chunks:
            parts.append(f"- chunk_id={c.chunk_id} [{c.source_type}]: {c.text}")
    else:
        parts.append(
            "\n## 검색된 근거 청크: 없음 (mode=llm_only) — rag_chunk 근거를 인용할 수 없습니다."
        )

    if inp.turns:
        parts.append("\n## 환자 발화 (source_type=utterance, source_id=turn_{N})")
        for t in inp.turns:
            parts.append(f"- turn_id=turn_{t.turn}: {t.patient_message}")
    else:
        parts.append("\n## 환자 발화: 없음")

    if inp.prior_handoff:
        parts.append("\n## 이전 Handoff Report (참고용)")
        parts.append(inp.prior_handoff)

    return "\n".join(parts)


class DomainInferenceAgent(BaseAgent):
    """Stage 2: LLM이 domain/department 후보 + evidence를 생성한다."""

    def __init__(self, model_router: ModelRouter, prompt_loader: PromptLoader) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return _PROMPT_AGENT_NAME

    def _retrieval_meta(self, inp: DomainInferenceInput) -> RetrievalMeta:
        return RetrievalMeta(
            mode=inp.retrieval_mode,
            chunks_returned=len(inp.retrieved_chunks),
            chunk_ids=[c.chunk_id for c in inp.retrieved_chunks],
            queries=inp.queries or None,
        )

    @staticmethod
    def _parse(content: str) -> tuple[DomainInferenceLLMResponse | None, str]:
        """Parse+validate the LLM JSON. Never raises — returns (None, reason) on failure."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return None, f"LLM response JSON parse failure: {exc}"
        try:
            return DomainInferenceLLMResponse.model_validate(data), ""
        except ValidationError as exc:
            return None, f"LLM response schema validation failure: {exc.error_count()} error(s)"

    async def _call(
        self,
        messages: list[ChatMessage],
        adapter: LLMAdapter,
        model_id: str,
        response_format: dict[str, Any] | None,
    ) -> tuple[str, str, float]:
        """Return (raw_content, model_used, latency_ms). Raises on transport failure."""
        resp = await adapter.chat_timed(
            messages,
            model=model_id,
            temperature=0.2,
            max_tokens=1536,
            response_format=response_format,
        )
        return resp.content, resp.model, resp.latency_ms

    async def run(self, inp: AgentInput, **kwargs: Any) -> DomainInferenceOutput:
        """Stage 2 LLM call → parsed candidates. Never crashes: parse/transport
        failures degrade to an empty, clearly-labelled output (no silent
        fabrication of candidates)."""
        start = time.perf_counter()

        if not isinstance(inp, DomainInferenceInput):
            raise TypeError(f"Expected DomainInferenceInput, got {type(inp).__name__}")

        retrieval_meta = self._retrieval_meta(inp)

        try:
            system_prompt = self._prompt_loader.load_system_prompt(
                _PROMPT_AGENT_NAME, PROMPT_VERSION
            )
        except FileNotFoundError:
            logger.warning("domain_inference prompt not found, using fallback")
            system_prompt = _LLM_FALLBACK_PROMPT

        user_content = _build_user_content(inp)
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]

        selection = self._router.select_model(self.agent_name, require_json=True)
        adapter = self._router.get_adapter(selection.adapter_name)
        assert isinstance(adapter, LLMAdapter)
        response_format = (
            {"type": "json_object"}
            if selection.supports_json_schema or selection.supports_json_object
            else None
        )

        model_used = "none"
        raw_content = ""
        reason = ""
        try:
            raw_content, model_used, _ = await self._call(
                messages, adapter, selection.model_id, response_format
            )
            self._router.record_success(selection.adapter_name)
        except Exception as exc:
            logger.error("DomainInference LLM call failed on %s: %s", selection.adapter_name, exc)
            self._router.record_failure(selection.adapter_name, exc)

            fallback = self._router.get_fallback(
                self.agent_name, selection.adapter_name, str(exc)
            )
            if fallback is None:
                latency_ms = (time.perf_counter() - start) * 1000
                return DomainInferenceOutput(
                    model_used="none",
                    prompt_version=PROMPT_VERSION,
                    latency_ms=latency_ms,
                    reason_summary=f"LLM unavailable, no fallback: {exc}",
                    retrieval_meta=retrieval_meta,
                )
            try:
                fb_adapter = self._router.get_adapter(fallback.adapter_name)
                assert isinstance(fb_adapter, LLMAdapter)
                fb_format = (
                    {"type": "json_object"}
                    if fallback.supports_json_schema or fallback.supports_json_object
                    else None
                )
                raw_content, model_used, _ = await self._call(
                    messages, fb_adapter, fallback.model_id, fb_format
                )
                self._router.record_success(fallback.adapter_name)
            except Exception as fb_exc:
                logger.error("DomainInference fallback also failed: %s", fb_exc)
                latency_ms = (time.perf_counter() - start) * 1000
                return DomainInferenceOutput(
                    model_used="none",
                    prompt_version=PROMPT_VERSION,
                    latency_ms=latency_ms,
                    reason_summary=f"LLM unavailable (primary+fallback failed): {fb_exc}",
                    retrieval_meta=retrieval_meta,
                )

        parsed, reason = self._parse(raw_content)
        latency_ms = (time.perf_counter() - start) * 1000

        if parsed is None:
            logger.warning("DomainInference parse failure: %s", reason)
            return DomainInferenceOutput(
                model_used=model_used,
                prompt_version=PROMPT_VERSION,
                latency_ms=latency_ms,
                reason_summary=reason,
                retrieval_meta=retrieval_meta,
            )

        return DomainInferenceOutput(
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary="domain/department candidates generated",
            domain_candidates=parsed.domain_candidates,
            department_candidates=parsed.department_candidates,
            summary=parsed.summary,
            retrieval_meta=retrieval_meta,
            additional_questions=parsed.additional_questions,
        )
