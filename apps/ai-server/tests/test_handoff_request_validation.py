"""Non-leaking handoff request-boundary validation tests."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from contracts.handoff import HandoffRequest, HandoffResponse
from fastapi.testclient import TestClient
from httpx import Client, Response
from pydantic import ValidationError

from src.main import app
from src.routes.handoff import get_handoff_agent
from src.schemas.handoff import HandoffInput

_SESSION_ID = "11111111-1111-4111-8111-111111111111"
_MESSAGE_ID = "22222222-2222-4222-8222-222222222222"


class _FailIfCalledGenerator:
    calls: int = 0

    async def generate(
        self,
        request: HandoffRequest,
        adapted: HandoffInput,
    ) -> HandoffResponse:
        self.calls += 1
        raise AssertionError((request.session_id, adapted.session_id))


@pytest.fixture
def boundary_client() -> Iterator[tuple[TestClient, _FailIfCalledGenerator]]:
    generator = _FailIfCalledGenerator()
    app.dependency_overrides[get_handoff_agent] = lambda: generator
    try:
        yield TestClient(app), generator
    finally:
        _ = app.dependency_overrides.pop(get_handoff_agent, None)


def _payload(content: str) -> dict[str, str | list[dict[str, str]]]:
    return {
        "session_id": _SESSION_ID,
        "messages": [
            {"message_id": _MESSAGE_ID, "role": "user", "content": content}
        ],
    }


def _post(client: Client, payload: dict[str, str | list[dict[str, str]]]) -> Response:
    return client.post(
        "/ai/handoff/generate",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


def test_missing_field_is_generic_and_does_not_reach_provider(
    boundary_client: tuple[TestClient, _FailIfCalledGenerator],
) -> None:
    client, generator = boundary_client
    sentinel = "phi-missing-field-sentinel"
    payload = _payload(sentinel)
    del payload["session_id"]

    response = _post(client, payload)

    assert response.status_code == 422
    assert response.json() == {"detail": "Handoff request validation failed"}
    assert sentinel not in response.text
    assert generator.calls == 0


def test_duplicate_ids_are_generic_and_do_not_reach_provider(
    boundary_client: tuple[TestClient, _FailIfCalledGenerator],
) -> None:
    client, generator = boundary_client
    sentinel = "phi-duplicate-message-sentinel"
    payload = _payload(sentinel)
    messages = payload["messages"]
    assert isinstance(messages, list)
    messages.append(
        {"message_id": _MESSAGE_ID, "role": "assistant", "content": "duplicate"}
    )

    response = _post(client, payload)

    assert response.status_code == 422
    assert response.json() == {"detail": "Handoff request validation failed"}
    assert sentinel not in response.text
    assert generator.calls == 0


def test_contract_locates_duplicate_ids_at_messages_field() -> None:
    payload = _payload("first")
    messages = payload["messages"]
    assert isinstance(messages, list)
    messages.append(
        {"message_id": _MESSAGE_ID, "role": "assistant", "content": "second"}
    )

    with pytest.raises(ValidationError) as failure:
        _ = HandoffRequest.model_validate(payload)

    [error] = failure.value.errors()
    assert error["loc"] == ("messages",)
    assert error["type"] == "duplicate_message_ids"
