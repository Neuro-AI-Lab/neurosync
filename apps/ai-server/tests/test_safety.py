"""Unit + HTTP tests for /ai/safety/classify."""

from __future__ import annotations

import pytest
from contracts.safety import RiskCategory, RiskLevel
from fastapi.testclient import TestClient

from src.main import app
from src.safety.classifier import classify

client = TestClient(app)


# ────────── classifier unit ──────────


@pytest.mark.parametrize(
    "text,expected_level,expected_category",
    [
        ("그냥 살고 싶지 않아요", RiskLevel.CRITICAL, RiskCategory.SUICIDE),
        ("자살하고 싶다는 생각이 자주 들어요", RiskLevel.CRITICAL, RiskCategory.SUICIDE),
        ("어제 자해를 했어요", RiskLevel.HIGH, RiskCategory.SELF_HARM),
        ("누군가를 죽이고 싶어요", RiskLevel.HIGH, RiskCategory.OTHER_HARM),
        ("더 이상 못 견디겠어요", RiskLevel.MEDIUM, RiskCategory.ACUTE_DISTRESS),
        ("오늘은 비가 와서 우산을 챙겼어요", RiskLevel.LOW, RiskCategory.NONE),
    ],
)
def test_classifier_returns_expected_level(text, expected_level, expected_category):
    result = classify(text)
    assert result.level == expected_level
    assert result.category == expected_category
    assert result.latency_ms >= 0
    assert 0.0 <= result.evidence.confidence <= 1.0


def test_classifier_longest_match_wins():
    # "자살하고 싶" (critical, conf 0.97) should beat any shorter prefix
    result = classify("이제 자살하고 싶어요")
    assert result.level == RiskLevel.CRITICAL
    assert "자살하고 싶" in result.evidence.matched_keywords


def test_classifier_clean_text_uses_llm_stub():
    result = classify("최근 잠을 잘 잤습니다")
    assert result.level == RiskLevel.LOW
    assert result.evidence.classifier == "llm-stub-v0"
    assert result.evidence.matched_keywords == []


# ────────── HTTP layer ──────────


def test_safety_classify_endpoint_critical():
    response = client.post(
        "/ai/safety/classify",
        json={"message": "그냥 죽고 싶어요", "prev_context": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["level"] == "critical"
    assert body["category"] == "suicide"
    assert body["evidence"]["classifier"] == "keyword-v1"


def test_safety_classify_endpoint_low():
    response = client.post(
        "/ai/safety/classify",
        json={"message": "오늘 점심 메뉴를 추천해 주세요", "prev_context": []},
    )
    assert response.status_code == 200
    assert response.json()["level"] == "low"


def test_safety_classify_validation_error_on_empty_message():
    response = client.post(
        "/ai/safety/classify",
        json={"message": "", "prev_context": []},
    )
    assert response.status_code == 422


def test_safety_classify_rejects_unknown_field():
    """extra='forbid' (set on the shared contract) must reject extras."""
    response = client.post(
        "/ai/safety/classify",
        json={"message": "hi", "prev_context": [], "role": "admin"},
    )
    assert response.status_code == 422
