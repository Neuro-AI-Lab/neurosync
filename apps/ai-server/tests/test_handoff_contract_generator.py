"""Behavioral tests for structured handoff JSON and citation validation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from contracts.handoff import HandoffRequest

from src.adapters.base import LLMAdapter
from src.agents.handoff_contract_generator import (
    HandoffContractGenerator,
    HandoffContractValidationError,
    HandoffProviderError,
)
from src.schemas.common import ModelSelection
from src.services.handoff_contract_adapter import adapt_handoff_request

_MESSAGE_ID = "22222222-2222-4222-8222-222222222222"


def _request() -> HandoffRequest:
    return HandoffRequest.model_validate(
        {
            "session_id": "11111111-1111-4111-8111-111111111111",
            "messages": [
                {
                    "message_id": _MESSAGE_ID,
                    "role": "user",
                    "content": "잠들기 어렵고 식욕이 줄었어요.",
                }
            ],
        }
    )


def _draft_json(**evidence_override: str) -> str:
    evidence = {
        "field": "chief_complaint",
        "source_message_id": _MESSAGE_ID,
        "quote": "잠들기 어렵고 식욕이 줄었어요.",
    }
    evidence.update(evidence_override)
    return json.dumps(
        {
            "chief_complaint": "수면과 식욕 변화",
            "present_illness": "최근 수면과 식욕 변화를 보고함.",
            "symptoms": ["불면"],
            "onset": None,
            "recent_changes": None,
            "triggers": [],
            "sleep_appetite_activity": {
                "sleep": "잠들기 어려움",
                "appetite": "감소",
                "activity": None,
            },
            "psych_history": None,
            "medications": None,
            "documents_summary": [],
            "clinician_attention": [],
            "evidence": [evidence],
        },
        ensure_ascii=False,
    )


def _agent_with_outputs(outputs: list[str]) -> tuple[HandoffContractGenerator, AsyncMock]:
    agent = HandoffContractGenerator.__new__(HandoffContractGenerator)
    router = MagicMock()
    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(
        side_effect=[MagicMock(content=content, model="test-model") for content in outputs]
    )
    router.select_model.return_value = ModelSelection(
        adapter_name="test",
        model_id="test-model",
        supports_json_schema=True,
    )
    router.get_adapter.return_value = adapter
    agent._router = router
    prompt_loader = MagicMock()
    prompt_loader.load_system_prompt.return_value = "structured contract prompt"
    agent._prompt_loader = prompt_loader
    return agent, adapter.chat_timed


@pytest.mark.asyncio
async def test_invalid_json_retries_then_returns_valid_official_response() -> None:
    request = _request()
    agent, chat = _agent_with_outputs(["not json", _draft_json()])

    response = await agent.generate(request, adapt_handoff_request(request))

    assert response.chief_complaint == "수면과 식욕 변화"
    assert response.evidence[0].source_message_id == request.messages[0].message_id
    assert response.latency_ms >= 0
    assert chat.await_count == 2
    await_call = chat.await_args
    assert await_call is not None
    response_format = await_call.kwargs["response_format"]
    schema = response_format["json_schema"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    sleep_schema = schema["$defs"]["_SleepAppetiteActivityDraft"]
    assert set(sleep_schema["required"]) == set(sleep_schema["properties"])


@pytest.mark.parametrize(
    "invalid_output",
    [
        _draft_json(source_message_id="99999999-9999-4999-8999-999999999999"),
        _draft_json(quote="없는 원문"),
        _draft_json(quote="   "),
        _draft_json(field="unknown_field"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_citation_retries_twice_then_rejects(invalid_output: str) -> None:
    request = _request()
    agent, chat = _agent_with_outputs([invalid_output] * 3)

    with pytest.raises(HandoffContractValidationError):
        await agent.generate(request, adapt_handoff_request(request))

    assert chat.await_count == 3


@pytest.mark.asyncio
async def test_provider_failure_is_not_misreported_as_contract_rejection() -> None:
    request = _request()
    agent, chat = _agent_with_outputs([])
    chat.side_effect = RuntimeError("provider unavailable")

    with pytest.raises(HandoffProviderError):
        await agent.generate(request, adapt_handoff_request(request))

    assert chat.await_count == 1
