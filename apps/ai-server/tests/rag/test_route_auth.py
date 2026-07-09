"""POST /ai/rag/grounding — bearer-token auth (ADR-013, VAL-005, S3).

RETIRED ROUTE, CONVERTED TEST (ADR-017/REV-013, 2026-07-09): `rag_router` is no
longer mounted in `src.main.app` (RAG HTTP API permanently retired — in-process
only). `src.rag.route`/`src.rag.auth` are kept in the tree (retired-not-deleted,
REV-013 §2) so their auth contract stays covered — this file now mounts the
router into a STANDALONE throwaway FastAPI app (not `src.main.app`) to keep
exercising `require_rag_api_key`'s fail-closed default, the normal
401/403/200 bearer-token flow, and the explicit dev-mode bypass. A separate
class below asserts the retirement itself: `src.main.app` no longer serves
this route at all (404, not 503/401/403 — no live-mounted RAG HTTP surface).

FastAPI TestClient + mocked DB session/retrieve_grounding (no real DB).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.rag.route import router as rag_router

# Standalone app — mirrors how `src.main.app` mounted `rag_router` before the
# ADR-017/REV-013 retirement. `src.main.app` itself no longer includes this
# router (see TestRagRouteRetiredFromMainApp below).
_standalone_app = FastAPI()
_standalone_app.include_router(rag_router)
client = TestClient(_standalone_app)

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


class TestRagRouteRetiredFromMainApp:
    """ADR-017/REV-013 (2026-07-09): the running app has NO live-mounted,
    network-reachable RAG HTTP surface — gate intent, verified directly."""

    def test_main_app_does_not_serve_rag_grounding(self) -> None:
        from src.main import app as main_app

        main_client = TestClient(main_app)
        resp = main_client.post("/ai/rag/grounding", json={"utterance": "안녕하세요"})
        # 404 (route absent), never 503/401/403 (which would imply it's still
        # mounted-and-authed) and never 200 (which would imply unauthed leak).
        assert resp.status_code == 404

    def test_health_route_has_no_auth_requirement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.main import app as main_app

        monkeypatch.delenv("NS_RAG_API_KEY", raising=False)
        monkeypatch.delenv("NS_RAG_DEV_MODE", raising=False)
        resp = TestClient(main_app).get("/health")
        assert resp.status_code == 200
