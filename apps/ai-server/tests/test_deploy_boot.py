"""Deployment smoke suite — app boot, route surface, agent registry wiring.

ADR-041 T4 (user directive, 2026-07-20): the legacy test suite (582 files)
was archived to `_archive/legacy_code/tests_legacy_20260720/tests/` for a
later deployment-focused refactor. This is the START of that refactor — a
minimal, credential-independent smoke suite that CI (no `.env`) can run.

Every check here uses dummy/monkeypatched env values (PR #67 lesson: CI has
no real API keys) — nothing hits a network or LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
AI_SERVER_ROOT = Path(__file__).resolve().parents[1]

# Registry key -> (module path, class name). Every key in
# src/routing/agent_model_registry.yaml must appear here.
_AGENT_MAP: dict[str, tuple[str, str]] = {
    "stt_agent": ("src.agents.stt", "STTAgent"),
    "ocr_agent": ("src.agents.ocr", "OCRAgent"),
    "safety_classifier": ("src.agents.safety_classifier", "SafetyClassifierAgent"),
    "dialogue": ("src.agents.dialogue", "DialogueAgent"),
    "clinical_slot": ("src.agents.clinical_slot", "ClinicalSlotAgent"),
    "input_normalizer": ("src.agents.input_normalizer", "InputNormalizerAgent"),
    "orchestrator": ("src.agents.orchestrator", "OrchestratorAgent"),
    "handoff_generator": ("src.agents.handoff_generator", "HandoffGeneratorAgent"),
    "evidence_verifier": ("src.agents.evidence_verifier", "EvidenceVerifierAgent"),
    "sentiment_analyzer": ("src.agents.sentiment_analyzer", "SentimentAnalyzerAgent"),
    "domain_inference": ("src.agents.domain_inference", "DomainInferenceAgent"),
}

# Expected mounted route surface (main.py's app.include_router list) —
# ADR-041 T2 retired the entire `nearby` router; it must never reappear here.
_EXPECTED_ROUTES: set[tuple[str, str]] = {
    ("GET", "/health"),
    ("POST", "/ai/safety/classify"),
    ("POST", "/ai/handoff/generate"),
    ("POST", "/ai/handoff/report"),
    ("POST", "/ai/chat/respond"),
    ("POST", "/ai/slots/extract"),
    ("POST", "/ai/survey/score"),
    ("POST", "/ai/survey/plan"),
    ("POST", "/ai/sentiment/utterance"),
    ("POST", "/ai/sentiment/session"),
    ("POST", "/ai/temporal/analyze"),
    ("POST", "/ai/ocr/parse"),
    ("POST", "/ai/stt/transcribe"),
    ("POST", "/ai/domain/infer"),
    ("POST", "/ai/phr/context"),
}


def test_app_imports_and_boots() -> None:
    from src.main import app

    assert app.title == "Neuro-Sync AI Server"


def test_route_surface_matches_expected_no_nearby() -> None:
    from src.main import app

    actual: set[tuple[str, str]] = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not methods:
            continue
        if path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            continue
        for m in methods:
            if m == "HEAD":
                continue
            actual.add((m, path))

    assert actual == _EXPECTED_ROUTES, (
        f"missing: {_EXPECTED_ROUTES - actual}, unexpected: {actual - _EXPECTED_ROUTES}"
    )
    assert not any("nearby" in path for _, path in actual), (
        "ADR-041 T2: nearby router must not be mounted"
    )


def test_health_endpoint() -> None:
    from src.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "neuro-sync-ai-server"


def test_registry_covers_exactly_the_mapped_agents() -> None:
    registry_path = AI_SERVER_ROOT / "src" / "routing" / "agent_model_registry.yaml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry_keys = set(data["agents"])
    assert registry_keys == set(_AGENT_MAP), (
        f"registry/test map drift — missing: {registry_keys - set(_AGENT_MAP)}, "
        f"stale: {set(_AGENT_MAP) - registry_keys}"
    )


@pytest.mark.parametrize("registry_key", list(_AGENT_MAP))
def test_registry_key_maps_to_importable_agent_with_matching_name(registry_key: str) -> None:
    module_path, class_name = _AGENT_MAP[registry_key]
    import importlib

    module = importlib.import_module(module_path)
    agent_cls = getattr(module, class_name)
    # agent_name is a property independent of constructor args (some
    # agents require a live ModelRouter/PromptLoader) — __new__ avoids
    # invoking __init__ while still exercising the real property.
    instance = agent_cls.__new__(agent_cls)
    assert instance.agent_name == registry_key


def test_adapters_construct_with_dummy_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """No network/LLM call happens at adapter construction — only client
    objects are built. Dummy values prove the constructors are credential-
    format-independent (CI has no real keys)."""
    monkeypatch.setenv("UPSTAGE_API_KEY", "dummy-upstage")
    monkeypatch.setenv("LG_K_EXAONE_API_KEY", "dummy-exaone")
    monkeypatch.setenv("LG_K_EXAONE_ENDPOINT_ID", "dummy-endpoint")
    monkeypatch.setenv("SKT_A_X_API_KEY", "dummy-skt")
    monkeypatch.setenv("HIRA_SERVICE_KEY", "dummy-hira")

    from src.adapters.ak_llm import AkLlmAdapter
    from src.adapters.hira_drug_efficacy import HiraDrugEfficacyAdapter
    from src.adapters.k_exaone import KExaoneAdapter
    from src.adapters.skt_ak_stt import SktAkSttAdapter
    from src.adapters.solar_document_parse import SolarDocumentParseAdapter
    from src.adapters.solar_pro3 import SolarPro3Adapter
    from src.config import Settings

    settings = Settings()
    assert settings.upstage_api_key == "dummy-upstage"

    for adapter_cls in (
        SolarPro3Adapter,
        KExaoneAdapter,
        AkLlmAdapter,
        SktAkSttAdapter,
        SolarDocumentParseAdapter,
        HiraDrugEfficacyAdapter,
    ):
        instance = adapter_cls(settings)
        assert instance.adapter_name
