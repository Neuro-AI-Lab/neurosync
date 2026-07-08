"""DomainInferenceAgent (F2) — schema contract + agent runtime, mock-based only.

Covers PLAN-2026-W28-C C-4 offline item 1 (output schema incl. evidence>=1 and
candidates<=3) and the agent pin/runtime path (mirrors test_prompt_v3.py's
`TestAgentPinsAndRuntimeVersion` convention).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.adapters.base import LLMAdapter
from src.agents.domain_inference import PROMPT_VERSION, DomainInferenceAgent
from src.schemas.domain_inference import (
    DomainCandidate,
    DomainEvidence,
    DomainInferenceInput,
    DomainInferenceLLMResponse,
    RetrievedChunk,
    UtteranceTurn,
)


def _valid_evidence() -> DomainEvidence:
    return DomainEvidence(source_type="utterance", source_id="turn_1", quote="잠을 잘 못 자요")


class TestOutputSchemaContract:
    """C-4 offline #1 — evidence >= 1 per candidate, candidates <= 3."""

    def test_evidence_required_at_least_one(self) -> None:
        with pytest.raises(ValidationError):
            DomainCandidate(domain="sleep", confidence=0.5, evidence=[])

    def test_candidate_accepts_one_evidence(self) -> None:
        cand = DomainCandidate(domain="sleep", confidence=0.5, evidence=[_valid_evidence()])
        assert len(cand.evidence) == 1

    def test_domain_must_be_in_enum(self) -> None:
        with pytest.raises(ValidationError):
            DomainCandidate(
                domain="not_a_real_domain", confidence=0.5, evidence=[_valid_evidence()]
            )

    def test_max_three_domain_candidates(self) -> None:
        four = [
            DomainCandidate(domain=d, confidence=0.5, evidence=[_valid_evidence()])
            for d in ("anxiety", "depression", "sleep", "trauma")
        ]
        with pytest.raises(ValidationError):
            DomainInferenceLLMResponse(domain_candidates=four)

    def test_three_domain_candidates_ok(self) -> None:
        three = [
            DomainCandidate(domain=d, confidence=0.5, evidence=[_valid_evidence()])
            for d in ("anxiety", "depression", "sleep")
        ]
        resp = DomainInferenceLLMResponse(domain_candidates=three)
        assert len(resp.domain_candidates) == 3

    def test_confidence_bounded_0_to_1(self) -> None:
        with pytest.raises(ValidationError):
            DomainCandidate(domain="sleep", confidence=1.5, evidence=[_valid_evidence()])

    def test_department_domain_ref_optional(self) -> None:
        from src.schemas.domain_inference import DepartmentCandidate

        d = DepartmentCandidate(department="정신건강의학과", reason="수면 문제 지속")
        assert d.domain_ref is None


class TestDomainInferenceInput:
    def test_requires_core_fields(self) -> None:
        with pytest.raises(ValidationError):
            DomainInferenceInput(session_id="t")  # missing final_slots/session_ctrs/etc.

    def test_minimal_valid_input(self) -> None:
        inp = DomainInferenceInput(
            session_id="t",
            final_slots={"chief_complaint": "불안감과 수면 문제"},
            session_ctrs=5,
            crisis_triggered=False,
            is_first_visit=True,
        )
        assert inp.retrieval_mode == "llm_only"
        assert inp.retrieved_chunks == []

    def test_turns_and_chunks_roundtrip(self) -> None:
        inp = DomainInferenceInput(
            session_id="t",
            final_slots={"chief_complaint": "불안"},
            session_ctrs=5,
            crisis_triggered=False,
            is_first_visit=True,
            turns=[UtteranceTurn(turn=1, patient_message="잠을 잘 못 자요")],
            retrieved_chunks=[
                RetrievedChunk(chunk_id="case_card:1", source_type="case_card", text="불안 사례")
            ],
            retrieval_mode="rag",
        )
        assert inp.turns[0].turn == 1
        assert inp.retrieved_chunks[0].chunk_id == "case_card:1"


# ── Agent runtime (mocked router/adapter, no live LLM) ──────────────────


def _make_agent() -> DomainInferenceAgent:
    agent = DomainInferenceAgent.__new__(DomainInferenceAgent)
    agent._router = MagicMock()
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "domain inference 프롬프트"
    return agent


def _wire(agent: DomainInferenceAgent, content: str) -> AsyncMock:
    agent._router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    resp = MagicMock()
    resp.content = content
    resp.model = "test-model"
    resp.latency_ms = 1.0
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(return_value=resp)
    agent._router.get_adapter.return_value = adapter
    agent._router.record_success = MagicMock()
    agent._router.record_failure = MagicMock()
    return adapter


def _base_input(**overrides) -> DomainInferenceInput:
    fields = dict(
        session_id="t",
        final_slots={"chief_complaint": "불안감과 수면 문제"},
        session_ctrs=5,
        crisis_triggered=False,
        is_first_visit=True,
    )
    fields.update(overrides)
    return DomainInferenceInput(**fields)


class TestAgentRuntime:
    def test_prompt_version_pin(self) -> None:
        assert PROMPT_VERSION == "v1"

    @pytest.mark.asyncio
    async def test_run_parses_valid_llm_output(self) -> None:
        agent = _make_agent()
        _wire(
            agent,
            '{"domain_candidates": [{"domain": "sleep", "confidence": 0.6, '
            '"evidence": [{"source_type": "utterance", "source_id": "turn_0", '
            '"quote": "수면 문제"}]}], "department_candidates": [], '
            '"summary": "수면 문제 언급"}',
        )

        out = await agent.run(_base_input())

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "domain_inference", "v1"
        )
        assert out.prompt_version == "v1"
        assert len(out.domain_candidates) == 1
        assert out.domain_candidates[0].domain == "sleep"
        assert out.retrieval_meta.mode == "llm_only"

    @pytest.mark.asyncio
    async def test_run_reports_retrieval_meta_from_input(self) -> None:
        agent = _make_agent()
        _wire(agent, '{"domain_candidates": [], "department_candidates": [], "summary": ""}')

        out = await agent.run(_base_input(
            retrieved_chunks=[
                RetrievedChunk(chunk_id="qa:5", source_type="qa", text="Q/A 본문")
            ],
            retrieval_mode="rag",
            queries=["불안감과 수면 문제"],
        ))

        assert out.retrieval_meta.mode == "rag"
        assert out.retrieval_meta.chunks_returned == 1
        assert out.retrieval_meta.chunk_ids == ["qa:5"]

    @pytest.mark.asyncio
    async def test_run_degrades_gracefully_on_json_parse_failure(self) -> None:
        """No silent fabrication: unparsable output -> empty candidates, not a crash."""
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire(agent, "not json at all")

        out = await agent.run(_base_input())

        assert out.domain_candidates == []
        assert out.department_candidates == []
        assert "parse failure" in out.reason_summary.lower()

    @pytest.mark.asyncio
    async def test_run_degrades_gracefully_on_schema_validation_failure(self) -> None:
        """4 candidates (>3) or missing evidence must not crash the agent."""
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire(
            agent,
            '{"domain_candidates": [{"domain": "sleep", "confidence": 0.5, "evidence": []}]}',
        )

        out = await agent.run(_base_input())

        assert out.domain_candidates == []
        assert "validation failure" in out.reason_summary.lower()

    @pytest.mark.asyncio
    async def test_run_rejects_wrong_input_type(self) -> None:
        agent = _make_agent()
        with pytest.raises(TypeError):
            await agent.run(object())  # type: ignore[arg-type]
