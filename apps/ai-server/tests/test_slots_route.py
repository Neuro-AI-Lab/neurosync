"""ISS-042: POST /ai/slots/extract success-path regression test.

The route's result log referenced `result.safety_flag`, a field removed from
ClinicalSlotOutput (safety judgment is SafetyClassifier's role, not the slot
extractor's). The AttributeError sat OUTSIDE the route's try/except, so a
fully successful extraction still returned HTTP 500.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.main import app
from src.routes.slots import _get_slot_agent
from src.schemas.clinical_slot import ClinicalSlotOutput

client = TestClient(app)


def _make_slot_output() -> ClinicalSlotOutput:
    return ClinicalSlotOutput(
        model_used="test",
        prompt_version="v1",
        latency_ms=5.0,
        reason_summary="test",
        extracted_slots={"chief_complaint": "불안"},
        filled_slots=["chief_complaint"],
        missing_slots=["history_of_present_illness"],
        essential_filled=["chief_complaint"],
        essential_missing=["risk_assessment"],
        slot_coverage=1 / 12,
    )


class TestSlotExtractRoute:
    def test_extract_success_returns_200(self) -> None:
        """A successful agent run must produce HTTP 200, not a post-hoc 500."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=_make_slot_output())
        app.dependency_overrides[_get_slot_agent] = lambda: mock_agent
        try:
            resp = client.post(
                "/ai/slots/extract",
                json={
                    "session_id": "iss042",
                    "conversation_history": [
                        {"role": "user", "content": "요즘 불안해요"}
                    ],
                    "current_slots": {},
                },
            )
        finally:
            app.dependency_overrides.pop(_get_slot_agent, None)

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["filled_slots"] == ["chief_complaint"]
        assert data["essential_missing"] == ["risk_assessment"]
        assert "safety_flag" not in data  # role separation: no safety field here

    def test_extract_agent_failure_returns_500(self) -> None:
        """Agent exceptions are still translated into a clean HTTP 500."""
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))
        app.dependency_overrides[_get_slot_agent] = lambda: mock_agent
        try:
            resp = client.post(
                "/ai/slots/extract",
                json={"session_id": "iss042-fail", "conversation_history": []},
            )
        finally:
            app.dependency_overrides.pop(_get_slot_agent, None)

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Slot extraction failed"
