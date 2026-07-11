"""RagTriggerJudgeAgent (F2 Policy B, PLAN-2026-W28-Q W4) — schema contract +
agent runtime, mock-based only. Mirrors `test_domain_inference.py`'s
`TestAgentRuntime` convention. No live LLM call anywhere in this file.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.adapters.base import LLMAdapter
from src.agents.rag_trigger_judge import PROMPT_VERSION, RagTriggerJudgeAgent
from src.schemas.domain_inference import UtteranceTurn
from src.schemas.rag_trigger_judge import (
    RagTriggerJudgeInput,
    RagTriggerJudgeLLMResponse,
    RagTriggerJudgeOutput,
)


class TestRagTriggerJudgeInputSchema:
    def test_minimal_valid_input(self) -> None:
        inp = RagTriggerJudgeInput(session_id="t")
        assert inp.turns == []
        assert inp.final_slots == {}

    def test_turns_and_slots_roundtrip(self) -> None:
        inp = RagTriggerJudgeInput(
            session_id="t",
            turns=[UtteranceTurn(turn=0, patient_message="불안해요")],
            final_slots={"chief_complaint": "불안감"},
        )
        assert inp.turns[0].patient_message == "불안해요"
        assert inp.final_slots["chief_complaint"] == "불안감"

    def test_no_field_licenses_persona_or_retrieve_grounding(self) -> None:
        """Structural check mirroring the BUG-022 guard's own discipline —
        an omitted channel is automatically excluded, no deny-list needed."""
        fields = set(RagTriggerJudgeInput.model_fields)
        assert "persona_id" not in fields
        assert "persona_path" not in fields
        assert "session_insights" not in fields


class TestRagTriggerJudgeLLMResponseSchema:
    def test_retrieve_true_with_query(self) -> None:
        resp = RagTriggerJudgeLLMResponse(retrieve=True, query="불안감과 수면 문제")
        assert resp.retrieve is True
        assert resp.query == "불안감과 수면 문제"

    def test_retrieve_false_query_defaults_to_none(self) -> None:
        resp = RagTriggerJudgeLLMResponse(retrieve=False)
        assert resp.query is None

    def test_retrieve_is_required(self) -> None:
        with pytest.raises(ValidationError):
            RagTriggerJudgeLLMResponse(query="x")  # type: ignore[call-arg]


# ── Agent runtime (mocked router/adapter, no live LLM) ──────────────────


def _make_agent() -> RagTriggerJudgeAgent:
    agent = RagTriggerJudgeAgent.__new__(RagTriggerJudgeAgent)
    agent._router = MagicMock()
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "rag trigger judge 프롬프트"
    return agent


def _wire(agent: RagTriggerJudgeAgent, content: str) -> AsyncMock:
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


class TestAgentRuntime:
    def test_prompt_version_pin(self) -> None:
        assert PROMPT_VERSION == "v1"

    @pytest.mark.asyncio
    async def test_run_parses_valid_llm_output_retrieve_true(self) -> None:
        agent = _make_agent()
        _wire(agent, '{"retrieve": true, "query": "불안감과 수면 문제"}')

        out = await agent.run(RagTriggerJudgeInput(session_id="t"))

        agent._prompt_loader.load_system_prompt.assert_called_once_with(
            "rag_trigger_judge", "v1"
        )
        assert isinstance(out, RagTriggerJudgeOutput)
        assert out.retrieve is True
        assert out.query == "불안감과 수면 문제"
        assert out.prompts_degraded is False

    @pytest.mark.asyncio
    async def test_run_parses_valid_llm_output_retrieve_false(self) -> None:
        agent = _make_agent()
        _wire(agent, '{"retrieve": false, "query": null}')

        out = await agent.run(RagTriggerJudgeInput(session_id="t"))

        assert out.retrieve is False
        assert out.query is None

    @pytest.mark.asyncio
    async def test_run_degrades_gracefully_on_json_parse_failure(self) -> None:
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire(agent, "not json at all")

        out = await agent.run(RagTriggerJudgeInput(session_id="t"))

        assert out.retrieve is False
        assert out.query is None
        assert "parse failure" in out.reason_summary.lower()

    @pytest.mark.asyncio
    async def test_run_degrades_gracefully_on_schema_validation_failure(self) -> None:
        agent = _make_agent()
        agent._router.get_fallback.return_value = None
        _wire(agent, '{"query": "no retrieve key"}')  # missing required `retrieve`

        out = await agent.run(RagTriggerJudgeInput(session_id="t"))

        assert out.retrieve is False
        assert out.query is None
        assert "validation failure" in out.reason_summary.lower()

    @pytest.mark.asyncio
    async def test_run_rejects_wrong_input_type(self) -> None:
        agent = _make_agent()
        with pytest.raises(TypeError):
            await agent.run(object())  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_prompt_not_found_degrades_with_flag(self) -> None:
        agent = _make_agent()
        agent._prompt_loader.load_system_prompt.side_effect = FileNotFoundError()
        _wire(agent, '{"retrieve": false, "query": null}')

        out = await agent.run(RagTriggerJudgeInput(session_id="t"))

        assert out.prompts_degraded is True
        assert out.retrieve is False

    @pytest.mark.asyncio
    async def test_llm_unavailable_no_fallback_degrades_never_fabricates_query(self) -> None:
        agent = _make_agent()
        agent._router.select_model.return_value = MagicMock(
            adapter_name="test", model_id="test",
            supports_json_schema=False, supports_json_object=False,
        )
        adapter = AsyncMock(spec=LLMAdapter)
        adapter.chat_timed = AsyncMock(side_effect=RuntimeError("vendor down"))
        agent._router.get_adapter.return_value = adapter
        agent._router.record_success = MagicMock()
        agent._router.record_failure = MagicMock()
        agent._router.get_fallback.return_value = None

        out = await agent.run(RagTriggerJudgeInput(session_id="t"))

        assert out.retrieve is False
        assert out.query is None
        assert "unavailable" in out.reason_summary.lower()
