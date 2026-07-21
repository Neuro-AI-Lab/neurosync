from __future__ import annotations

import json
import traceback
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from contracts.handoff import HandoffRequest
from fastapi.testclient import TestClient
from httpx import Response

from src.adapters.base import LLMAdapter
from src.agents.handoff_contract_generator import (
    HandoffContractGenerator,
    HandoffContractValidationError,
    HandoffProviderError,
)
from src.main import app
from src.routes.handoff import _get_handoff_agent
from src.schemas.common import ModelSelection
from src.services.handoff_contract_adapter import adapt_handoff_request

_MESSAGE_ID = "22222222-2222-4222-8222-222222222222"
_QUOTE = "잠들기 어렵고 식욕이 줄었어요."
_REQUIRED_TARGETS = (
    "chief_complaint",
    "present_illness",
    "symptoms[0]",
    "symptoms[1]",
    "onset",
    "recent_changes",
    "triggers[0]",
    "sleep_appetite_activity.sleep",
    "sleep_appetite_activity.appetite",
    "sleep_appetite_activity.activity",
    "psych_history",
    "medications",
    "clinician_attention[0]",
)


def _request() -> HandoffRequest:
    return HandoffRequest.model_validate(
        {
            "session_id": "11111111-1111-4111-8111-111111111111",
            "messages": [
                {"message_id": _MESSAGE_ID, "role": "user", "content": _QUOTE}
            ],
        }
    )


def _draft_json(
    evidence_fields: tuple[str, ...] = _REQUIRED_TARGETS,
    *,
    documents_summary: tuple[str, ...] = (),
    onset: str | None = "지난주",
) -> str:
    return json.dumps(
        {
            "chief_complaint": "수면 변화",
            "present_illness": "최근 수면 변화를 보고함.",
            "symptoms": ["불면", "식욕 저하"],
            "onset": onset,
            "recent_changes": "최근 악화",
            "triggers": ["업무 스트레스"],
            "sleep_appetite_activity": {
                "sleep": "잠들기 어려움",
                "appetite": "감소",
                "activity": "저하",
            },
            "psych_history": "과거 상담",
            "medications": "복용약 확인 필요",
            "documents_summary": list(documents_summary),
            "clinician_attention": ["자가보고 확인"],
            "evidence": [
                {
                    "field": field,
                    "source_message_id": _MESSAGE_ID,
                    "quote": _QUOTE,
                }
                for field in evidence_fields
            ],
        },
        ensure_ascii=False,
    )


def _selection(adapter_name: str, tier: str) -> ModelSelection:
    return ModelSelection(
        adapter_name=adapter_name,
        model_id=f"{adapter_name}-model",
        tier=tier,
        supports_json_schema=True,
    )


def _adapter(*outputs: str | RuntimeError) -> AsyncMock:
    adapter = AsyncMock(spec=LLMAdapter)
    responses = [
        output if isinstance(output, RuntimeError) else MagicMock(content=output)
        for output in outputs
    ]
    adapter.chat_timed = AsyncMock(side_effect=responses)
    return adapter


def _agent_with_tiers(
    primary: AsyncMock,
    secondary: AsyncMock,
    fallback: AsyncMock,
) -> tuple[HandoffContractGenerator, MagicMock]:
    selections = {
        "primary": _selection("primary", "primary"),
        "secondary": _selection("secondary", "secondary"),
        "fallback": _selection("fallback", "fallback"),
    }
    adapters = {"primary": primary, "secondary": secondary, "fallback": fallback}
    router = MagicMock()
    router.select_model.return_value = selections["primary"]
    router.get_fallback.side_effect = [selections["secondary"], selections["fallback"]]
    router.get_adapter.side_effect = adapters.__getitem__
    prompt_loader = MagicMock()
    prompt_loader.load_system_prompt.return_value = "structured contract prompt"
    return HandoffContractGenerator(router, prompt_loader), router


def _post_generate(agent: HandoffContractGenerator) -> Response:
    app.dependency_overrides[_get_handoff_agent] = lambda: agent
    try:
        return TestClient(app).post(
            "/ai/handoff/generate",
            json=_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(_get_handoff_agent, None)


@pytest.mark.parametrize(
    ("evidence_fields", "documents_summary"),
    [
        ((), ()),
        *[
            (tuple(field for field in _REQUIRED_TARGETS if field != missing), ())
            for missing in _REQUIRED_TARGETS
        ],
        ((*_REQUIRED_TARGETS, "evidence"), ()),
        ((*_REQUIRED_TARGETS, "sleep_appetite_activity"), ()),
        (_REQUIRED_TARGETS, ("문서 요약",)),
    ],
)
@pytest.mark.asyncio
async def test_generate_rejects_incomplete_or_invalid_leaf_grounding(
    evidence_fields: tuple[str, ...],
    documents_summary: tuple[str, ...],
) -> None:
    request = _request()
    invalid = _draft_json(evidence_fields, documents_summary=documents_summary)
    agent, router = _agent_with_tiers(
        _adapter(invalid), _adapter(invalid), _adapter(invalid)
    )

    with pytest.raises(HandoffContractValidationError):
        await agent.generate(request, adapt_handoff_request(request))

    assert [entry.args[0] for entry in router.record_failure.call_args_list] == [
        "primary",
        "secondary",
        "fallback",
    ]
    router.record_success.assert_not_called()


@pytest.mark.asyncio
async def test_generate_rejects_citation_to_empty_response_target() -> None:
    request = _request()
    invalid = _draft_json(onset=None)
    agent, _router = _agent_with_tiers(
        _adapter(invalid), _adapter(invalid), _adapter(invalid)
    )

    with pytest.raises(HandoffContractValidationError):
        await agent.generate(request, adapt_handoff_request(request))


@pytest.mark.asyncio
async def test_generate_advances_to_valid_secondary_after_invalid_primary() -> None:
    request = _request()
    primary = _adapter(_draft_json(()))
    secondary = _adapter(_draft_json())
    fallback = _adapter(_draft_json())
    agent, router = _agent_with_tiers(primary, secondary, fallback)

    response = await agent.generate(request, adapt_handoff_request(request))

    assert response.chief_complaint == "수면 변화"
    assert primary.chat_timed.await_count == 1
    assert secondary.chat_timed.await_count == 1
    assert fallback.chat_timed.await_count == 0
    assert router.record_failure.call_args_list == [
        call("primary", HandoffContractValidationError())
    ]
    router.record_success.assert_called_once_with("secondary")


@pytest.mark.asyncio
async def test_generate_returns_provider_failure_after_all_three_tiers_fail() -> None:
    request = _request()
    sentinel = "provider-secret-sentinel"
    agent, router = _agent_with_tiers(
        _adapter(RuntimeError(sentinel)),
        _adapter(RuntimeError(sentinel)),
        _adapter(RuntimeError(sentinel)),
    )

    with pytest.raises(HandoffProviderError) as failure:
        await agent.generate(request, adapt_handoff_request(request))

    formatted = "".join(traceback.format_exception(failure.value))
    assert failure.value.__cause__ is None
    assert sentinel not in formatted
    assert [entry.args[0] for entry in router.record_failure.call_args_list] == [
        "primary",
        "secondary",
        "fallback",
    ]
    router.record_success.assert_not_called()


def test_route_returns_generic_422_after_three_invalid_tiers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "clinical-secret-sentinel"
    invalid = _draft_json((), onset=sentinel)
    agent, _router = _agent_with_tiers(
        _adapter(invalid), _adapter(invalid), _adapter(invalid)
    )

    response = _post_generate(agent)

    assert response.status_code == 422
    assert response.json() == {"detail": "Handoff response validation failed"}
    assert sentinel not in response.text
    assert sentinel not in caplog.text


def test_route_returns_generic_500_after_three_provider_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "provider-secret-sentinel"
    agent, _router = _agent_with_tiers(
        _adapter(RuntimeError(sentinel)),
        _adapter(RuntimeError(sentinel)),
        _adapter(RuntimeError(sentinel)),
    )

    response = _post_generate(agent)

    assert response.status_code == 500
    assert response.json() == {"detail": "Handoff report generation failed"}
    assert sentinel not in response.text
    assert sentinel not in caplog.text
