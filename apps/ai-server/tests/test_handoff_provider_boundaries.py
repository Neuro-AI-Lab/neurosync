"""Provider-boundary sanitization and BaseException propagation tests."""

from __future__ import annotations

import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import override

import pytest
from contracts.handoff import HandoffRequest
from fastapi.testclient import TestClient
from httpx import Client, Response

from src.adapters.base import ChatMessage, ChatResponse
from src.adapters.solar_pro3 import SolarPro3Adapter
from src.agents.handoff_contract_generator import (
    HandoffContractGenerator,
    HandoffProviderError,
)
from src.config import Settings
from src.main import app
from src.prompts.loader import PromptLoader
from src.routes.handoff import get_handoff_agent
from src.routing.model_router import ModelRouter
from src.services.handoff_contract_adapter import adapt_handoff_request

_ROOT = Path(__file__).parents[3]
_REGISTRY = Path(__file__).parents[1] / "src" / "routing" / "agent_model_registry.yaml"
_ADAPTER_NAMES = ("solar-pro3", "k-exaone", "ak-llm")
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


class _FailureAdapter(SolarPro3Adapter):
    _failure: BaseException

    def __init__(self, failure: BaseException) -> None:
        super().__init__(Settings(upstage_api_key="test-key"))
        self._failure = failure

    @override
    async def chat_timed(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: JsonValue,
    ) -> ChatResponse:
        _ = (messages, kwargs)
        raise self._failure


def _request() -> HandoffRequest:
    return HandoffRequest.model_validate(
        {
            "session_id": "11111111-1111-4111-8111-111111111111",
            "messages": [
                {
                    "message_id": "22222222-2222-4222-8222-222222222222",
                    "role": "user",
                    "content": "잠들기 어렵습니다.",
                }
            ],
        }
    )


def _agent(failures: tuple[BaseException, BaseException, BaseException]) -> tuple[
    HandoffContractGenerator,
    ModelRouter,
]:
    router = ModelRouter(_REGISTRY)
    router.register_adapters(
        {
            name: _FailureAdapter(failure)
            for name, failure in zip(_ADAPTER_NAMES, failures, strict=True)
        }
    )
    prompt_loader = PromptLoader(_ROOT / "docs" / "ai" / "prompts")
    return HandoffContractGenerator(router, prompt_loader), router


def _post(client: Client, payload: str) -> Response:
    return client.post(
        "/ai/handoff/generate",
        content=payload,
        headers={"content-type": "application/json"},
    )


@pytest.mark.parametrize("failure_type", [TypeError, AttributeError, IndexError])
@pytest.mark.asyncio
async def test_arbitrary_provider_exception_discards_trace_context(
    failure_type: type[Exception],
) -> None:
    sentinel = "phi-provider-context-sentinel"
    failures = (failure_type(sentinel), failure_type(sentinel), failure_type(sentinel))
    agent, _router = _agent(failures)
    request = _request()

    with pytest.raises(HandoffProviderError) as failure:
        _ = await agent.generate(request, adapt_handoff_request(request))

    formatted = "".join(traceback.format_exception(failure.value))
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
    assert sentinel not in formatted


@pytest.mark.asyncio
async def test_base_exception_propagates_without_failure_accounting() -> None:
    agent, router = _agent((KeyboardInterrupt(), RuntimeError(), RuntimeError()))
    request = _request()

    for _attempt in range(3):
        with pytest.raises(KeyboardInterrupt):
            _ = await agent.generate(request, adapt_handoff_request(request))

    assert router.select_model("handoff_generator", require_json=True).adapter_name == "solar-pro3"


@pytest.mark.asyncio
async def test_all_open_selection_discards_trace_context() -> None:
    sentinel = "all-circuits-open-sentinel"
    agent, router = _agent((RuntimeError(), RuntimeError(), RuntimeError()))
    for adapter_name in _ADAPTER_NAMES:
        for _attempt in range(3):
            _ = router.record_failure(adapter_name, HandoffProviderError())
    request = _request()

    with pytest.raises(HandoffProviderError) as failure:
        _ = await agent.generate(request, adapt_handoff_request(request))

    formatted = "".join(traceback.format_exception(failure.value))
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
    assert sentinel not in formatted


def test_route_redacts_arbitrary_provider_exception_from_body_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "phi-provider-context-sentinel"
    agent, _router = _agent(
        (TypeError(sentinel), AttributeError(sentinel), IndexError(sentinel))
    )
    app.dependency_overrides[get_handoff_agent] = lambda: agent
    try:
        response = _post(TestClient(app), _request().model_dump_json())
    finally:
        _ = app.dependency_overrides.pop(get_handoff_agent, None)

    assert response.status_code == 500
    assert response.json() == {"detail": "Handoff report generation failed"}
    assert sentinel not in response.text
    assert sentinel not in caplog.text
