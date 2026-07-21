"""Circuit-health behavior for official handoff generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from contracts.handoff import HandoffRequest

from src.agents.handoff_contract_generator import (
    HandoffContractGenerator,
    HandoffContractValidationError,
    HandoffProviderError,
)
from src.routing.fallback_policy import FallbackPolicy
from src.routing.model_router import ModelRouter
from src.services.handoff_contract_adapter import adapt_handoff_request

_REGISTRY = Path(__file__).parents[1] / "src" / "routing" / "agent_model_registry.yaml"
_ADAPTERS = ("solar-pro3", "k-exaone", "ak-llm")


def _router() -> ModelRouter:
    return ModelRouter(_REGISTRY)


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


def test_three_contract_failures_make_next_request_skip_primary() -> None:
    router = _router()
    for _attempt in range(3):
        _ = router.record_failure("solar-pro3", HandoffContractValidationError())

    selection = router.select_model("handoff_generator", require_json=True)

    assert selection.adapter_name == "k-exaone"


def test_success_resets_only_the_matching_adapter() -> None:
    router = _router()
    for _attempt in range(2):
        _ = router.record_failure("solar-pro3", HandoffProviderError())
        _ = router.record_failure("k-exaone", HandoffProviderError())

    router.record_success("k-exaone")
    _ = router.record_failure("solar-pro3", HandoffProviderError())
    selection = router.select_model("handoff_generator", require_json=True)

    assert selection.adapter_name == "k-exaone"


@pytest.mark.asyncio
async def test_all_open_circuits_raise_content_free_provider_error() -> None:
    router = _router()
    for adapter_name in _ADAPTERS:
        for _attempt in range(3):
            _ = router.record_failure(adapter_name, HandoffProviderError())
    agent = HandoffContractGenerator(router, MagicMock())
    request = _request()

    with pytest.raises(HandoffProviderError) as failure:
        _ = await agent.generate(request, adapt_handoff_request(request))

    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None


def test_unknown_policy_failure_does_not_open_adapter_circuit() -> None:
    policy = FallbackPolicy(threshold=1)

    assert policy.should_fallback("primary", TypeError("programming defect"))
    assert not policy.is_circuit_open("primary")


def test_handoff_failure_opens_adapter_circuit_at_threshold() -> None:
    policy = FallbackPolicy(threshold=1)

    assert policy.should_fallback("primary", HandoffContractValidationError())
    assert policy.is_circuit_open("primary")
