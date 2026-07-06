"""T1-F1-VER-008: SentimentAnalyzer session-level route test."""

import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

class TestSentimentSessionRoute:
    def test_empty_session(self):
        resp = client.post("/ai/sentiment/session", json={
            "session_id": "test",
            "per_utterance_results": [],
            "conversation_history": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["signal_strength"] == "none"
        assert data["dominant_emotions"] == []

    def test_session_with_results(self):
        results = [
            {"turn_index": 1, "emotions": [{"label": "anxiety", "intensity": 0.7}], "polarity": -0.5, "arousal": "high", "evidence_phrase": "불안해요", "risk_signal": False, "model_used": "test", "prompt_version": "v1", "latency_ms": 0, "reason_summary": "test"},
            {"turn_index": 2, "emotions": [{"label": "sadness", "intensity": 0.6}], "polarity": -0.6, "arousal": "medium", "evidence_phrase": "슬퍼요", "risk_signal": False, "model_used": "test", "prompt_version": "v1", "latency_ms": 0, "reason_summary": "test"},
            {"turn_index": 3, "emotions": [{"label": "anxiety", "intensity": 0.8}], "polarity": -0.7, "arousal": "high", "evidence_phrase": "너무 불안해요", "risk_signal": False, "model_used": "test", "prompt_version": "v1", "latency_ms": 0, "reason_summary": "test"},
        ]
        resp = client.post("/ai/sentiment/session", json={
            "session_id": "test",
            "per_utterance_results": results,
            "conversation_history": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "anxiety" in data["dominant_emotions"]
        assert data["signal_strength"] in ("moderate", "strong")
        assert len(data["polarity_trajectory"]) == 3
        assert len(data["per_utterance_tags"]) == 3
