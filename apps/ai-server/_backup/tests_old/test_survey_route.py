"""T1-F3-DEV-004: Survey scoring HTTP route tests."""

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


class TestSurveyScoreRoute:
    """POST /ai/survey/score — rule-based, no LLM."""

    def test_phq9_valid(self):
        resp = client.post("/ai/survey/score", json={
            "scale_name": "PHQ-9",
            "responses": [1, 1, 1, 1, 1, 1, 1, 1, 0],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["scale_name"] == "PHQ-9"
        assert data["total_score"] == 8
        assert data["severity"] == "mild"
        assert data["critical_item_positive"] is False

    def test_phq9_q9_positive(self):
        resp = client.post("/ai/survey/score", json={
            "scale_name": "PHQ-9",
            "responses": [0, 0, 0, 0, 0, 0, 0, 0, 2],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["critical_item_positive"] is True
        assert data["recommended_action"] == "safety_referral"

    def test_gad7_valid(self):
        resp = client.post("/ai/survey/score", json={
            "scale_name": "GAD-7",
            "responses": [2, 2, 2, 2, 2, 2, 2],
        })
        assert resp.status_code == 200
        assert resp.json()["total_score"] == 14
        assert resp.json()["severity"] == "moderate"

    def test_audit_c_female(self):
        resp = client.post("/ai/survey/score", json={
            "scale_name": "AUDIT-C",
            "responses": [1, 1, 1],
            "patient_sex": "female",
        })
        assert resp.status_code == 200
        assert resp.json()["severity"] == "hazardous_drinking"

    def test_invalid_scale(self):
        resp = client.post("/ai/survey/score", json={
            "scale_name": "INVALID",
            "responses": [1, 2, 3],
        })
        assert resp.status_code == 422

    def test_wrong_item_count(self):
        resp = client.post("/ai/survey/score", json={
            "scale_name": "PHQ-9",
            "responses": [1, 2],
        })
        assert resp.status_code == 422

    def test_out_of_range(self):
        resp = client.post("/ai/survey/score", json={
            "scale_name": "PHQ-9",
            "responses": [0, 0, 0, 0, 0, 0, 0, 0, 5],
        })
        assert resp.status_code == 422
