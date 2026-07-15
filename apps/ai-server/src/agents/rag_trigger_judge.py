"""RagTriggerJudge agent — Policy-B LLM-judged RAG trigger (F2, PLAN-2026-W28-Q W4).

`docs/ai/validation_plan_f1f2_continuous.md` §3 Policy-B row: a single small
LLM call, inserted before `run_stage1()` (`src.rag_trigger.decide_policy_b`
is the call site), that decides whether F2's Stage-1 retrieval should fire
this run and, if so, composes the query text to search with. Output is
code-parsed only — `{"retrieve": bool, "query": str|null}` — never free
text.

Licensed input (plan §6 allowlist, Policy-B judge row): session transcript
+ slot state. NOT licensed: persona paths, `retrieve_grounding()` (BUG-022
lineage) — `RagTriggerJudgeInput` (`src.schemas.rag_trigger_judge`) has no
field for either, and the standing BUG-022 guard test
(`tests/repro/test_bug_022.py`) asserts this mechanically. `risk_assessment`
is hard-excluded as a query source (REV-022 Issue 10) by the CALLER
(`decide_policy_b`) before this agent ever runs — belt-and-braces with the
prompt's own instruction, per this project's code-enforce-not-prompt-only
precedent (ADR-014).

Whatever query this agent composes still passes through
`src.rag_trigger.apply_risk_lexicon_filter` — the SAME single choke point
Policy A's fallback queries pass through — before it ever reaches Stage 1.
That filter, not this agent's own prompt discipline, is this project's
actual enforcement mechanism for the residual risk-content channel
(REV-022 Issues 9/10).
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
from src.schemas.rag_trigger_judge import (
    RagTriggerJudgeInput,
    RagTriggerJudgeLLMResponse,
    RagTriggerJudgeOutput,
)

logger = logging.getLogger(__name__)

_PROMPT_AGENT_NAME = "rag_trigger_judge"
# W4 — new agent, first version.
PROMPT_VERSION = "v1"

_LLM_FALLBACK_PROMPT = (
    "세션 대화와 슬롯 상태를 보고 RAG 검색이 필요한지 판단해 JSON으로만 출력하세요: "
    '{"retrieve": true|false, "query": "<질의 또는 null>"}. '
    "위험/자살/자해 관련 표현은 절대 query에 포함하지 않습니다."
)


def _build_user_content(inp: RagTriggerJudgeInput) -> str:
    """Serialize slot state + session transcript for the judge LLM."""
    parts: list[str] = []

    parts.append("## 현재 슬롯 상태")
    if inp.final_slots:
        for k, v in inp.final_slots.items():
            if v:
                parts.append(f"- {k}: {v}")
    else:
        parts.append("- (수집된 슬롯 없음)")

    parts.append("\n## 세션 대화 (환자 발화)")
    if inp.turns:
        for t in inp.turns:
            parts.append(f"- turn_{t.turn}: {t.patient_message}")
    else:
        parts.append("- (발화 없음)")

    return "\n".join(parts)


class RagTriggerJudgeAgent(BaseAgent):
    """Policy-B trigger decision — single small LLM call, code-parsed output."""

    def __init__(self, model_router: ModelRouter, prompt_loader: PromptLoader) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return _PROMPT_AGENT_NAME

    @staticmethod
    def _parse(content: str) -> tuple[RagTriggerJudgeLLMResponse | None, str]:
        """Parse+validate the LLM JSON. Never raises — returns (parsed, reason)."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return None, f"LLM response JSON parse failure: {exc}"
        try:
            return RagTriggerJudgeLLMResponse.model_validate(data), ""
        except ValidationError as exc:
            return None, f"LLM response schema validation failure: {exc.error_count()} error(s)"

    async def _call(
        self,
        messages: list[ChatMessage],
        adapter: LLMAdapter,
        model_id: str,
        response_format: dict[str, Any] | None,
    ) -> tuple[str, str, float]:
        """Return (raw_content, model_used, latency_ms). Raises on transport failure.

        Low `max_tokens` (this agent's whole output is a two-field JSON
        object) and `temperature=0.0` — a trigger DECISION benefits from
        maximal determinism (this project's judge-stability floor, plan §5
        Gate 0.5, checks the `retrieve` boolean for unanimity across
        identical-input repeats).
        """
        resp = await adapter.chat_timed(
            messages, model=model_id, temperature=0.0, max_tokens=256,
            response_format=response_format,
        )
        return resp.content, resp.model, resp.latency_ms

    async def run(self, inp: AgentInput, **kwargs: Any) -> RagTriggerJudgeOutput:
        """Slot state + transcript -> {retrieve, query}. Never crashes: parse/
        transport failures degrade to retrieve=False, query=None (no silent
        fabrication of a query the judge never actually composed)."""
        start = time.perf_counter()

        if not isinstance(inp, RagTriggerJudgeInput):
            raise TypeError(f"Expected RagTriggerJudgeInput, got {type(inp).__name__}")

        prompts_degraded = False
        try:
            system_prompt = self._prompt_loader.load_system_prompt(
                _PROMPT_AGENT_NAME, PROMPT_VERSION
            )
        except FileNotFoundError:
            logger.warning("rag_trigger_judge prompt not found, using fallback")
            system_prompt = _LLM_FALLBACK_PROMPT
            prompts_degraded = True

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
        try:
            raw_content, model_used, _ = await self._call(
                messages, adapter, selection.model_id, response_format
            )
            self._router.record_success(selection.adapter_name)
        except Exception as exc:
            logger.error(
                "RagTriggerJudge LLM call failed on %s: %s", selection.adapter_name, exc
            )
            self._router.record_failure(selection.adapter_name, exc)

            fallback = self._router.get_fallback(
                self.agent_name, selection.adapter_name, str(exc)
            )
            if fallback is None:
                latency_ms = (time.perf_counter() - start) * 1000
                # No-fallback, safe default: retrieve=False — never
                # fabricate a query when the judge itself is unavailable
                # (mirrors DomainInferenceAgent's "degrade, never fabricate"
                # discipline).
                return RagTriggerJudgeOutput(
                    model_used="none", prompt_version=PROMPT_VERSION, latency_ms=latency_ms,
                    reason_summary=f"LLM unavailable, no fallback: {exc}",
                    retrieve=False, query=None, prompts_degraded=prompts_degraded,
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
                logger.error("RagTriggerJudge fallback also failed: %s", fb_exc)
                latency_ms = (time.perf_counter() - start) * 1000
                return RagTriggerJudgeOutput(
                    model_used="none", prompt_version=PROMPT_VERSION, latency_ms=latency_ms,
                    reason_summary=f"LLM unavailable (primary+fallback failed): {fb_exc}",
                    retrieve=False, query=None, prompts_degraded=prompts_degraded,
                )

        parsed, reason = self._parse(raw_content)
        latency_ms = (time.perf_counter() - start) * 1000

        if parsed is None:
            logger.warning("RagTriggerJudge parse failure: %s (model=%s)", reason, model_used)
            return RagTriggerJudgeOutput(
                model_used=model_used, prompt_version=PROMPT_VERSION, latency_ms=latency_ms,
                reason_summary=reason, retrieve=False, query=None,
                prompts_degraded=prompts_degraded,
            )

        logger.info(
            "RagTriggerJudge call ok — model=%s, retrieve=%s", model_used, parsed.retrieve
        )
        return RagTriggerJudgeOutput(
            model_used=model_used, prompt_version=PROMPT_VERSION, latency_ms=latency_ms,
            reason_summary="retrieve/query decision generated",
            retrieve=parsed.retrieve, query=parsed.query, prompts_degraded=prompts_degraded,
        )
