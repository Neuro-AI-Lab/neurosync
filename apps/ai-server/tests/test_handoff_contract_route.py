"""Official shared-contract coverage for ``POST /ai/handoff/generate``."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from contracts.handoff import Citation, HandoffRequest, HandoffResponse, SleepAppetiteActivity
from fastapi.testclient import TestClient

from src.agents.handoff_contract_generator import (
    HandoffContractValidationError,
    HandoffProviderError,
)
from src.main import app
from src.routes.handoff import _get_handoff_agent
from src.schemas.handoff import HandoffInput, HandoffOutput

_SESSION_ID = "11111111-1111-4111-8111-111111111111"
_USER_MESSAGE_ID = "22222222-2222-4222-8222-222222222222"
_AI_MESSAGE_ID = "33333333-3333-4333-8333-333333333333"
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _official_payload() -> dict[str, JsonValue]:
    return {
        "session_id": _SESSION_ID,
        "messages": [
            {
                "message_id": _USER_MESSAGE_ID,
                "role": "user",
                "content": "잠들기 어렵고 식욕이 줄었어요.",
            },
            {
                "message_id": _AI_MESSAGE_ID,
                "role": "assistant",
                "content": "언제부터 그러셨나요?",
            },
            {
                "message_id": "44444444-4444-4444-8444-444444444444",
                "role": "system",
                "content": "",
            },
        ],
        "questionnaires": [
            {"type": "PHQ9", "total_score": 11, "severity": "moderate"},
            {"type": "GAD7", "total_score": 4, "severity": "minimal"},
        ],
        "doc_texts": ["처방 문서 원문", "두 번째 문서"],
        "risk_signals": [
            {
                "level": "high",
                "category": "self-harm",
                "source_message_id": _USER_MESSAGE_ID,
            },
            {"level": "vendor-specific", "category": None, "source_message_id": None},
        ],
    }


def _official_response() -> HandoffResponse:
    return HandoffResponse(
        chief_complaint="수면과 식욕 변화",
        present_illness="최근 잠들기 어렵고 식욕이 줄었다고 보고함.",
        symptoms=["불면", "식욕 저하"],
        onset=None,
        recent_changes="식욕 감소",
        triggers=[],
        sleep_appetite_activity=SleepAppetiteActivity(
            sleep="잠들기 어려움", appetite="감소"
        ),
        psych_history=None,
        medications=None,
        documents_summary=["처방 문서 원문", "두 번째 문서"],
        clinician_attention=["자가보고 내용 확인"],
        evidence=[
            Citation(
                field="chief_complaint",
                source_message_id=UUID(_USER_MESSAGE_ID),
                quote="잠들기 어렵고 식욕이 줄었어요.",
            )
        ],
        latency_ms=7,
    )


class RecordingGenerator:
    """Test double that supports both the removed and official generator seams."""

    def __init__(self) -> None:
        self.request: HandoffRequest | HandoffInput | None = None
        self.adapted: HandoffInput | None = None

    async def generate(
        self,
        request: HandoffRequest,
        adapted: HandoffInput,
    ) -> HandoffResponse:
        self.request = request
        self.adapted = adapted
        return _official_response()

    async def run(self, body: HandoffInput) -> HandoffOutput:
        self.request = body
        return HandoffOutput(
            report_markdown="# legacy",
            latency_ms=1,
            model_used="test",
            prompt_version="test",
            reason_summary="legacy route",
        )


@pytest.fixture
def official_client() -> Iterator[tuple[TestClient, RecordingGenerator]]:
    generator = RecordingGenerator()
    app.dependency_overrides[_get_handoff_agent] = lambda: generator
    try:
        yield TestClient(app), generator
    finally:
        app.dependency_overrides.pop(_get_handoff_agent, None)


def test_generate_round_trips_official_contract_losslessly(
    official_client: tuple[TestClient, RecordingGenerator],
) -> None:
    client, generator = official_client

    response = client.post("/ai/handoff/generate", json=_official_payload())

    assert response.status_code == 200, response.text
    assert HandoffResponse.model_validate(response.json()) == _official_response()
    assert generator.request is not None
    assert generator.request.session_id == UUID(_SESSION_ID)
    assert generator.adapted is not None
    assert generator.adapted.session_id == _SESSION_ID
    assert generator.adapted.conversation_history == [
        {
            "message_id": _USER_MESSAGE_ID,
            "role": "user",
            "content": "잠들기 어렵고 식욕이 줄었어요.",
        },
        {
            "message_id": _AI_MESSAGE_ID,
            "role": "assistant",
            "content": "언제부터 그러셨나요?",
        },
        {
            "message_id": "44444444-4444-4444-8444-444444444444",
            "role": "system",
            "content": "",
        },
    ]
    assert [score.model_dump() for score in generator.adapted.scale_scores] == [
        {"scale_name": "PHQ9", "total_score": 11, "severity": "moderate"},
        {"scale_name": "GAD7", "total_score": 4, "severity": "minimal"},
    ]
    assert generator.adapted.ocr_documents == [
        {"document_id": "doc-1", "content": "처방 문서 원문"},
        {"document_id": "doc-2", "content": "두 번째 문서"},
    ]
    assert [event.model_dump() for event in generator.adapted.risk_events] == [
        {
            "risk_level": "high",
            "level": "high",
            "category": "self-harm",
            "source_message_id": _USER_MESSAGE_ID,
        },
        {"level": "vendor-specific"},
    ]
    assert "report_markdown" not in response.json()


def test_generate_openapi_uses_only_official_models() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    operation = schema["paths"]["/ai/handoff/generate"]["post"]

    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/HandoffRequest"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/HandoffResponse")


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_detail"),
    [
        (
            HandoffContractValidationError(),
            422,
            "Handoff response validation failed",
        ),
        (HandoffProviderError(), 500, "Handoff report generation failed"),
    ],
)
def test_generate_returns_generic_errors(
    failure: HandoffContractValidationError | HandoffProviderError,
    expected_status: int,
    expected_detail: str,
) -> None:
    generator = RecordingGenerator()
    generator.generate = AsyncMock(side_effect=failure)
    app.dependency_overrides[_get_handoff_agent] = lambda: generator
    try:
        response = TestClient(app).post("/ai/handoff/generate", json=_official_payload())
    finally:
        app.dependency_overrides.pop(_get_handoff_agent, None)

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
