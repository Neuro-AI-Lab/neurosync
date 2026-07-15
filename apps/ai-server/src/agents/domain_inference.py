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
import re
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
# PLAN-2026-W28-C — new agent, first version (v1 kept on disk, rollback policy).
# PLAN-2026-W28-E / ADR-014 (2026-07-08): v2 remediation — VAL-006/REV-008
# confirmed v1's rule 2 (위험≠도메인) fails live under prompt-only enforcement;
# v2 adds a code-enforcement disclosure + ISS-046 carve-out. The actual
# mechanical enforcement lives in src.eval.f2_grounding, not this pin.
PROMPT_VERSION = "v2"

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
        # BUG-016 (REV-010 finding 1): the literal string "chunk_id=" used to
        # sit directly adjacent to the id below, and the model sometimes
        # echoed that literal label into the source_id field it emitted
        # (e.g. "chunk_id=case_card:687"), which cost genuine evidence at
        # the exact-match lookup in src.eval.f2_grounding.check_evidence.
        # Defense in depth only — the deterministic fix is the code-level
        # normalization in check_evidence itself; this wording change just
        # removes the easy trigger.
        #
        # BUG-019 (EXP-007 root-cause hypothesis, 2026-07-09): the per-chunk
        # listing used to print `({c.source_type})` — the RetrievedChunk's DB
        # TABLE ORIGIN ("case_card"/"qa") — directly adjacent to chunk_id, in
        # the exact visual slot the output evidence[].source_type field
        # occupies (a DIFFERENT field with a different value domain,
        # Literal["rag_chunk", "utterance"]). The model sometimes echoed the
        # table-origin value into evidence[].source_type instead of the
        # required "rag_chunk" (offending values observed live: "qa",
        # "qa:1502", "qa:1537", "qa:532" — all qa-table chunks). Reworded so
        # the table-origin label no longer sits in that slot and is
        # explicitly named "origin"/DB 출처, not "source_type" — same
        # defense-in-depth-only status as BUG-016's wording fix; the
        # deterministic fix is the code-level coercion in `_parse` below.
        parts.append(
            "\n## 검색된 근거 청크 (evidence.source_type은 항상 고정값 rag_chunk — "
            "아래 괄호는 source_type이 아니라 DB 출처 테이블명, [ ] 안 값이 source_id)"
        )
        for c in inp.retrieved_chunks:
            parts.append(f"- [{c.chunk_id}] (DB 출처: {c.source_type}): {c.text}")
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


# BUG-019 (EXP-007 root-cause hypothesis, 2026-07-09): `RetrievedChunk.
# source_type` (DB table origin: "case_card"/"qa", `schemas/domain_
# inference.py:81`) and `DomainEvidence.source_type` (output enum
# Literal["rag_chunk", "utterance"], `:35`) share a field NAME across
# different value DOMAINS. EXP-007's captured `validation_errors` show the
# model intermittently echoes the table-origin value into the output field
# instead of the required "rag_chunk" — offending `input` values observed
# live: "qa" (bare table name), "qa:1502"/"qa:1537"/"qa:532" (the model went
# further and copied the whole source_id string). Every offending value
# observed is qa-table-sourced; case_card is included below on the same
# hypothesis (EXP-007's evidence does not rule it out, only that it was not
# observed this batch — REV-011 single-variable discipline: this coercion
# does not depend on which table, only on the known collision shape).
#
# NARROW BY DESIGN: matches only a source_type value that is exactly one of
# the two known DB table names, optionally suffixed with ":<digits>" (a
# copied source_id). Anything else (e.g. "garbage", "chunk", "rag") is left
# untouched and still fails Pydantic validation honestly — this coercion
# must not mask a genuinely malformed model output.
_SOURCE_TYPE_TABLE_ORIGIN_RE = re.compile(r"^(?:case_card|qa)(?::\d+)?$")


def _normalize_source_type_collision(data: Any) -> Any:
    """Coerce a known table-origin value in ``evidence[].source_type`` to
    ``"rag_chunk"`` (BUG-019), in place, before Pydantic ever validates it.

    Must run on the raw parsed JSON dict, before ``DomainInferenceLLMResponse.
    model_validate(data)`` — ``DomainEvidence.source_type`` is a Pydantic
    ``Literal``, so any correction has to happen pre-validation; there is no
    later hook that can fix an already-raised ``ValidationError`` (unlike
    BUG-016's ``source_id`` fix, which normalizes at grounding-check time in
    ``src.eval.f2_grounding`` because ``source_id`` is an unconstrained
    ``str`` there and the collision is only discovered post-parse).

    Only mutates a ``source_type`` value matching the known collision shape
    (``_SOURCE_TYPE_TABLE_ORIGIN_RE``) — a value that does not match (e.g.
    already-valid ``"rag_chunk"``/``"utterance"``, or genuinely malformed
    output such as ``"garbage"``) is left untouched, so validation still
    fails honestly on real defects. Tolerates a non-dict/non-list shape at
    any level (returns *data* unchanged for that branch) — malformed
    structure is Pydantic's job to reject, not this function's.
    """
    if not isinstance(data, dict):
        return data
    candidates = data.get("domain_candidates")
    if not isinstance(candidates, list):
        return data
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        evidence_list = candidate.get("evidence")
        if not isinstance(evidence_list, list):
            continue
        for evidence in evidence_list:
            if not isinstance(evidence, dict):
                continue
            source_type = evidence.get("source_type")
            if isinstance(source_type, str) and _SOURCE_TYPE_TABLE_ORIGIN_RE.match(
                source_type
            ):
                logger.info(
                    "DomainInference BUG-019 coercion: evidence.source_type "
                    "%r -> 'rag_chunk' (known DB table-origin collision, "
                    "source_id=%r)",
                    source_type, evidence.get("source_id"),
                )
                evidence["source_type"] = "rag_chunk"
    return data


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
    def _parse(
        content: str,
    ) -> tuple[DomainInferenceLLMResponse | None, str, list[dict[str, Any]] | None]:
        """Parse+validate the LLM JSON. Never raises — returns
        (parsed, reason, validation_errors) on failure.

        BUG-019 (2026-07-09): previously returned only `exc.error_count()` (a
        bare integer) in `reason` on a schema-validation failure, discarding
        `exc.errors()` — the field-level detail (which field failed, what
        value was received, which constraint was violated) — which made the
        root cause of a schema-validation failure undiagnosable from this
        pipeline's own logs/artifacts (EXP-006 RAG-arm batch, 3 failures,
        `error.md` BUG-019). `validation_errors` now carries that detail on
        the schema-validation branch; it is `None` on the JSON-parse-failure
        branch (no `ValidationError` was ever raised there — same gap class,
        `TestBug019JsonParseFailurePathAlsoDiscardsContent` precedent) and on
        success. The raw `content` string itself is not returned here — the
        caller (`run()`) already holds it in scope as `raw_content` from the
        `_call()` result, so it threads that directly into
        `DomainInferenceOutput.raw_response` rather than round-tripping it
        through this method's return value.

        BUG-019 root-cause fix (2026-07-09, EXP-007 diagnostic capture):
        before validation, `_normalize_source_type_collision` narrowly
        coerces a known `RetrievedChunk.source_type` (DB table origin,
        "case_card"/"qa", optionally suffixed ":<digits>") value the model
        sometimes echoes into `evidence[].source_type` back to the correct
        `"rag_chunk"`. This does not change `reason`/`validation_errors`'
        contract on a GENUINE validation failure — only the known collision
        shape is corrected; anything else still raises `ValidationError`
        and is reported exactly as before.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return None, f"LLM response JSON parse failure: {exc}", None
        # BUG-019: narrow, deterministic coercion of the known source_type
        # table-origin collision, BEFORE Pydantic validation — see
        # `_normalize_source_type_collision`'s own docstring for why this
        # must happen pre-validation and why it is scoped this narrowly.
        data = _normalize_source_type_collision(data)
        try:
            return DomainInferenceLLMResponse.model_validate(data), "", None
        except ValidationError as exc:
            return (
                None,
                f"LLM response schema validation failure: {exc.error_count()} error(s)",
                [dict(e) for e in exc.errors()],
            )

    async def _call(
        self,
        messages: list[ChatMessage],
        adapter: LLMAdapter,
        model_id: str,
        response_format: dict[str, Any] | None,
    ) -> tuple[str, str, float, str | None, dict[str, int] | None]:
        """Return (raw_content, model_used, latency_ms, finish_reason, usage).

        Raises on transport failure. BUG-017 phase A: `finish_reason`/`usage`
        (`ChatResponse.finish_reason`/`.usage`, `src/adapters/base.py`) used
        to be silently discarded here, which made the RAG-mode truncation
        hypothesis unfalsifiable from this project's own logs —
        `finish_reason == "length"` is the OpenAI-compatible API's own direct
        truncation signal. Now captured and threaded through by the caller
        for logging + persistence.

        BUG-017 phase B (2026-07-09): the diagnostic run confirmed the
        hypothesis directly — VP-003 RAG run
        (`docs/ai/simulation_results/VP-003/VP-003_20260709_110457_domain_
        inference.json`) returned `finish_reason="length"` with
        `usage.completion_tokens == 1536` (exactly the prior ceiling),
        `usage.prompt_tokens == 2665`. `max_tokens` raised from 1536 to
        4096 (global, both `llm_only`/`rag`) — see this dispatch's RESULT
        for the value/scope rationale. This is the only change BUG-017
        phase B makes; no retrieval/prompt-size change (that is a separate,
        held Track-3 item, REV-011 Issue 5).
        """
        resp = await adapter.chat_timed(
            messages,
            model=model_id,
            temperature=0.2,
            max_tokens=4096,
            response_format=response_format,
        )
        return resp.content, resp.model, resp.latency_ms, resp.finish_reason, resp.usage

    async def run(self, inp: AgentInput, **kwargs: Any) -> DomainInferenceOutput:
        """Stage 2 LLM call → parsed candidates. Never crashes: parse/transport
        failures degrade to an empty, clearly-labelled output (no silent
        fabrication of candidates)."""
        start = time.perf_counter()

        if not isinstance(inp, DomainInferenceInput):
            raise TypeError(f"Expected DomainInferenceInput, got {type(inp).__name__}")

        retrieval_meta = self._retrieval_meta(inp)

        # BUG-021: makes a degraded run machine-visible on this agent's own
        # output artifact, not just a WARNING log line — same pattern as
        # ClinicalSlotAgent/DialogueAgent/InputNormalizerAgent/
        # SafetyClassifierAgent. DomainInferenceAgent runs on every F2 call
        # (the W7 battery invokes it every time), so a silent degraded F2
        # prompt would invisibly corrupt validation results.
        prompts_degraded = False
        try:
            system_prompt = self._prompt_loader.load_system_prompt(
                _PROMPT_AGENT_NAME, PROMPT_VERSION
            )
        except FileNotFoundError:
            logger.warning("domain_inference prompt not found, using fallback")
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
        reason = ""
        finish_reason: str | None = None
        usage: dict[str, int] | None = None
        try:
            raw_content, model_used, _, finish_reason, usage = await self._call(
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
                    prompts_degraded=prompts_degraded,
                )
            try:
                fb_adapter = self._router.get_adapter(fallback.adapter_name)
                assert isinstance(fb_adapter, LLMAdapter)
                fb_format = (
                    {"type": "json_object"}
                    if fallback.supports_json_schema or fallback.supports_json_object
                    else None
                )
                raw_content, model_used, _, finish_reason, usage = await self._call(
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
                    prompts_degraded=prompts_degraded,
                )

        parsed, reason, validation_errors = self._parse(raw_content)
        latency_ms = (time.perf_counter() - start) * 1000

        # BUG-017 phase A: log finish_reason/usage on EVERY call outcome
        # (success and parse/schema failure alike) so a future RAG-mode
        # truncation hypothesis (finish_reason == "length") is falsifiable
        # from this project's own logs, not just inferred from a character
        # offset (REV-010 finding 2 / VAL-010 correlation note).
        if parsed is None:
            logger.warning(
                "DomainInference parse failure: %s (model=%s, finish_reason=%s, usage=%s)",
                reason, model_used, finish_reason, usage,
            )
            # BUG-019: persist the raw LLM response text AND (on a schema-
            # validation failure specifically) the field-level
            # ValidationError.errors() detail, on both failure branches
            # (JSON-parse and schema-validation alike, for symmetry) — the
            # gap that made this class of failure undiagnosable from this
            # pipeline's own artifacts. Mirrors finish_reason/usage's own
            # capture-on-every-failure-outcome discipline above.
            return DomainInferenceOutput(
                model_used=model_used,
                prompt_version=PROMPT_VERSION,
                latency_ms=latency_ms,
                reason_summary=reason,
                retrieval_meta=retrieval_meta,
                finish_reason=finish_reason,
                usage=usage,
                raw_response=raw_content,
                validation_errors=validation_errors,
                prompts_degraded=prompts_degraded,
            )

        logger.info(
            "DomainInference call ok — model=%s, finish_reason=%s, usage=%s",
            model_used, finish_reason, usage,
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
            finish_reason=finish_reason,
            usage=usage,
            prompts_degraded=prompts_degraded,
        )
