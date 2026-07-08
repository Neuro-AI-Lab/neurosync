"""POST /ai/rag/grounding — bearer-token auth (ADR-013, VAL-005, S3).

FastAPI TestClient + mocked DB session/retrieve_grounding (no real DB).
Confirms the fail-closed default (unconfigured -> 503, not open), the normal
401/403/200 bearer-token flow, the explicit dev-mode bypass, and that every
OTHER router is unaffected (ADR-013: "other routes unaffected").
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

_CANNED_GROUNDING = {
    "similar_cases": [], "knowledge": [], "mentioned_symptoms": [],
    "follow_up": None, "my_past": [],
}


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _stub_db(monkeypatch: pytest.MonkeyPatch) -> None:
    # route.py calls get_sessionmaker()/retrieve_grounding() as plain module
    # attributes, not FastAPI Depends() params — patch the names it imported.
    monkeypatch.setattr("src.rag.route.get_sessionmaker", lambda: (lambda: _FakeSession()))
    monkeypatch.setattr(
        "src.rag.route.retrieve_grounding", AsyncMock(return_value=dict(_CANNED_GROUNDING))
    )


class TestRagAuthFailClosedDefault:
    def test_unconfigured_key_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NS_RAG_API_KEY", raising=False)
        monkeypatch.delenv("NS_RAG_DEV_MODE", raising=False)
        _stub_db(monkeypatch)

        resp = client.post("/ai/rag/grounding", json={"utterance": "안녕하세요"})
        assert resp.status_code == 503

    def test_configured_key_missing_header_returns_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NS_RAG_API_KEY", "secret-key")
        monkeypatch.delenv("NS_RAG_DEV_MODE", raising=False)
        _stub_db(monkeypatch)

        resp = client.post("/ai/rag/grounding", json={"utterance": "안녕하세요"})
        assert resp.status_code == 401

    def test_configured_key_wrong_header_returns_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NS_RAG_API_KEY", "secret-key")
        monkeypatch.delenv("NS_RAG_DEV_MODE", raising=False)
        _stub_db(monkeypatch)

        resp = client.post(
            "/ai/rag/grounding",
            json={"utterance": "안녕하세요"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 403

    def test_configured_key_correct_header_returns_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NS_RAG_API_KEY", "secret-key")
        monkeypatch.delenv("NS_RAG_DEV_MODE", raising=False)
        _stub_db(monkeypatch)

        resp = client.post(
            "/ai/rag/grounding",
            json={"utterance": "안녕하세요"},
            headers={"Authorization": "Bearer secret-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["similar_cases"] == []

    def test_dev_mode_bypasses_auth_even_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NS_RAG_API_KEY", raising=False)
        monkeypatch.setenv("NS_RAG_DEV_MODE", "1")
        _stub_db(monkeypatch)

        resp = client.post("/ai/rag/grounding", json={"utterance": "안녕하세요"})
        assert resp.status_code == 200

    def test_malformed_authorization_header_returns_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NS_RAG_API_KEY", "secret-key")
        monkeypatch.delenv("NS_RAG_DEV_MODE", raising=False)
        _stub_db(monkeypatch)

        resp = client.post(
            "/ai/rag/grounding",
            json={"utterance": "안녕하세요"},
            headers={"Authorization": "secret-key"},  # missing "Bearer " prefix
        )
        assert resp.status_code == 401


class TestOtherRoutersUnaffectedByRagAuth:
    """ADR-013: auth is wired onto the rag router ONLY."""

    def test_health_route_has_no_auth_requirement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NS_RAG_API_KEY", raising=False)
        monkeypatch.delenv("NS_RAG_DEV_MODE", raising=False)
        resp = client.get("/health")
        assert resp.status_code == 200
