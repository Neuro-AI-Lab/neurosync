"""Production route coverage for the closed A8 narrative activation gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.main import app
from tests.test_deployment_stateless_routes import _session_entry

client = TestClient(app)


def _sessions() -> list[dict]:
    return [
        _session_entry(
            1,
            "2026-01-01",
            session_id="s1",
            persona_id="vp999",
            persona_name="테스트환자",
            model="test-model",
        ),
        _session_entry(
            2,
            "2026-01-15",
            session_id="s2",
            persona_id="vp999",
            persona_name="테스트환자",
            model="test-model",
        ),
    ]


@pytest.mark.parametrize(
    ("narrative_enabled", "narrative_text", "expected_status"),
    [
        (True, None, 422),
        (True, "검토되지 않은 임상 서술", 422),
        (False, "비활성 요청에 남은 임상 서술", 422),
        (False, None, 200),
    ],
)
def test_narrative_activation_truth_table(
    narrative_enabled: bool,
    narrative_text: str | None,
    expected_status: int,
) -> None:
    response = client.post(
        "/ai/handoff/report",
        json={
            "vp_id": "vp999",
            "sessions": _sessions(),
            "narrative_enabled": narrative_enabled,
            "narrative_text": narrative_text,
            "include_pdf": False,
        },
    )

    assert response.status_code == expected_status, response.text
