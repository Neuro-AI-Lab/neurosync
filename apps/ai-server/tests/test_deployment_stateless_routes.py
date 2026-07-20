"""Route contract tests for the stateless deployment-integration endpoints
(`docs/ai/deployment_integration_plan.md` R1/R3): `POST /ai/temporal/analyze`,
`POST /ai/handoff/report`, `POST /ai/survey/plan`.

All three routes wrap PURE, zero-LLM engines (`src.f3`/`src.f4`/`src.f5`) —
no mocking is needed (mirrors `tests/test_survey_route.py`'s own
no-LLM-dependency discipline for `/ai/survey/score`); these tests exercise
the real conversion path (`src.services.stateless_longitudinal`) end-to-end
on synthetic session-series payloads via `TestClient`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.main import app

client = TestClient(app)


def _session_entry(
    session_index: int,
    simulated_date: str,
    *,
    phq9_total: int | None = None,
    session_ctrs: int = 4,
    **overrides,
) -> dict:
    """One synthetic ledger-entry-shaped session — mirrors
    `contracts.longitudinal.LongitudinalSessionEntry`."""
    entry = {
        "session_index": session_index,
        "simulated_date": simulated_date,
        "scenario_pack_id": "vp999",
        "arc_mode": "stable",
        "final_slots": {
            "chief_complaint": f"session {session_index} 주호소",
            "history_of_present_illness": f"session {session_index} 현병력",
        },
        "missing_slots": [],
        "session_ctrs": session_ctrs,
        "crisis_triggered": False,
        "crisis_turn": None,
        "probe_events": [],
        "risk_floor": None,
        "turn_sentiment_polarities": [0.1, 0.2],
        "turn_risk_signal_count": 0,
        "session_sentiment_summary": None,
        "domain_candidates": [],
        "ai_predicted_disease": None,
        "f3": None,
    }
    if phq9_total is not None:
        entry["f3"] = {
            "outcome": "administered",
            "scale_name": "PHQ-9",
            "item_bank_version": "v1",
            "item_bank_provenance": "test-fixture",
            "responses": [1] * 8 + [0],
            "total_score": phq9_total,
            "max_score": 27,
            "severity": "mild" if phq9_total < 10 else "moderate",
            "safety_referral": False,
            "administration_mode": "natural",
            "critical_item_positive": False,
        }
    entry.update(overrides)
    return entry


class TestTemporalAnalyzeRoute:
    def test_two_session_series(self):
        sessions = [
            _session_entry(1, "2026-01-01", phq9_total=18),
            _session_entry(2, "2026-01-15", phq9_total=10),
        ]
        resp = client.post(
            "/ai/temporal/analyze", json={"vp_id": "vp999", "sessions": sessions}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["vp_id"] == "vp999"
        assert data["n_sessions"] == 2
        assert data["overall_direction"] in ("improved", "worsened", "unchanged", "unknown")
        assert "PHQ-9" in data["scale_series"]

    def test_empty_sessions_422(self):
        resp = client.post("/ai/temporal/analyze", json={"vp_id": "vp999", "sessions": []})
        assert resp.status_code == 422

    def test_out_of_order_sessions_are_sorted(self):
        sessions = [
            _session_entry(2, "2026-01-15", phq9_total=10),
            _session_entry(1, "2026-01-01", phq9_total=18),
        ]
        resp = client.post(
            "/ai/temporal/analyze", json={"vp_id": "vp999", "sessions": sessions}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["n_sessions"] == 2


class TestHandoffReportRoute:
    def test_two_session_report_markdown_and_fhir(self):
        sessions = [
            _session_entry(
                1, "2026-01-01", phq9_total=18,
                session_id="s1", persona_id="vp999", persona_name="테스트환자", model="test-model",
            ),
            _session_entry(
                2, "2026-01-15", phq9_total=10,
                session_id="s2", persona_id="vp999", persona_name="테스트환자", model="test-model",
            ),
        ]
        resp = client.post(
            "/ai/handoff/report",
            json={
                "vp_id": "vp999",
                "sessions": sessions,
                "include_charts": False,
                "include_pdf": False,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["vp_id"] == "vp999"
        assert "F5 인계 요약 보고서" in data["report_markdown"]
        assert data["fhir_bundle"]["resourceType"] == "Bundle"
        assert data["fhir_bundle"]["type"] == "document"
        assert data["pdf_base64"] is None
        assert data["chart_pngs_base64"] == {}

    def test_pdf_included_when_requested(self):
        sessions = [
            _session_entry(
                1, "2026-01-01", phq9_total=18,
                session_id="s1", persona_id="vp999", persona_name="테스트환자", model="test-model",
            ),
            _session_entry(
                2, "2026-01-15", phq9_total=10,
                session_id="s2", persona_id="vp999", persona_name="테스트환자", model="test-model",
            ),
        ]
        resp = client.post(
            "/ai/handoff/report",
            json={
                "vp_id": "vp999",
                "sessions": sessions,
                "include_charts": False,
                "include_pdf": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["pdf_base64"] is not None
        assert data["pdf_omitted_reason"] is None
        import base64
        pdf_bytes = base64.b64decode(data["pdf_base64"])
        assert pdf_bytes[:4] == b"%PDF"

    def test_single_session_422(self):
        sessions = [_session_entry(1, "2026-01-01", phq9_total=18)]
        resp = client.post(
            "/ai/handoff/report", json={"vp_id": "vp999", "sessions": sessions}
        )
        assert resp.status_code == 422


class TestPromptsBaseDirDockerDefaultResolutionOrder:
    """G1 (`docs/ai/deployment_integration_plan.md`) — the Dockerfile bakes
    `ENV PROMPTS_BASE_DIR=/app/prompts` as the IN-CONTAINER default; a host
    `.env`/explicit env var value must still win over it (env > default,
    `src.config.Settings`'s own pydantic-settings precedence: explicit env
    var > `.env` file > field default). `tests/repro/test_bug_021_prompts_
    base_dir.py` already covers `resolve_prompts_base_dir`'s CLI-anchoring
    behavior exhaustively — this test targets the OTHER consumer,
    `Settings.resolve_prompts_dir()` (`src/dependencies.py::get_prompt_
    loader`'s own call), which the Docker image's ENV default actually
    feeds."""

    def test_explicit_env_var_overrides_dockerfile_style_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulates the Dockerfile's own baked-in container default.
        monkeypatch.setenv("PROMPTS_BASE_DIR", "/app/prompts")
        assert Settings().resolve_prompts_dir() == Path("/app/prompts")

        # An operator-supplied host override (docker-compose env passthrough,
        # or a host-run .env) still wins — same env var, later value.
        monkeypatch.setenv("PROMPTS_BASE_DIR", "/custom/prompts/dir")
        assert Settings().resolve_prompts_dir() == Path("/custom/prompts/dir")

    def test_unset_falls_back_to_field_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PROMPTS_BASE_DIR", raising=False)
        # Isolate from this repo's own apps/ai-server/.env (env_file="​.env")
        # so this assertion checks the FIELD default specifically, not
        # whatever the live .env happens to carry today.
        monkeypatch.chdir("/tmp")
        assert Settings().resolve_prompts_dir() == Path("docs/ai/prompts")


class TestSurveyPlanRoute:
    def test_natural_recommendation(self):
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": "PHQ-9",
                "recommendation_caveat": None,
                "crisis_triggered": False,
                "session_ctrs": 4,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scale"] == "PHQ-9"
        assert data["administration_mode"] == "natural"
        assert len(data["items"]) == 9
        assert data["si_supplement"] is False

    def test_safety_net_no_recommendation_high_acuity(self):
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": None,
                "crisis_triggered": True,
                "session_ctrs": 2,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scale"] == "PHQ-9"
        assert data["administration_mode"] == "safety_net"

    def test_si_supplement_plan_on_crisis_non_phq9(self):
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": "AUDIT-C",
                "crisis_triggered": True,
                "session_ctrs": 4,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scale"] == "AUDIT-C"
        assert data["administration_mode"] == "si_supplement-plan"
        assert data["si_supplement"] is True
        assert data["si_supplement_item"] is not None
        assert data["si_supplement_item"]["index"] == 9

    def test_no_questionnaire_indicated(self):
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": None,
                "crisis_triggered": False,
                "session_ctrs": 5,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scale"] is None
        assert data["administration_mode"] is None
        assert data["not_administrable_reason"] is not None

    # ── CVR-031 remediation ──────────────────────────────────────────

    def test_phq9_item9_marked_is_si_item(self):
        """Finding 1: same-call actionability — PHQ-9 item 9 (index=9) is
        flagged in `items`, nothing else is."""
        resp = client.post(
            "/ai/survey/plan",
            json={"recommended_questionnaire": "PHQ-9", "crisis_triggered": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        si_items = [item for item in data["items"] if item["is_si_item"]]
        assert len(si_items) == 1
        assert si_items[0]["index"] == 9
        assert data["si_positive_action_ko"] is not None
        assert "109" in data["si_positive_action_ko"]
        assert "119" in data["si_positive_action_ko"]
        assert data["si_positive_threshold"] == 1

    def test_si_supplement_item_marked_is_si_item(self):
        """Finding 1: the CVR-030 standalone SI-supplement item is also
        flagged, and drives si_positive_action_ko for a non-PHQ-9 scale."""
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": "AUDIT-C",
                "crisis_triggered": True,
                "session_ctrs": 4,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["si_supplement_item"]["is_si_item"] is True
        assert all(not item["is_si_item"] for item in data["items"])
        assert data["si_positive_action_ko"] is not None

    def test_no_si_item_no_action_text(self):
        """A GAD-7-only natural plan carries no SI item — no action text."""
        resp = client.post(
            "/ai/survey/plan",
            json={"recommended_questionnaire": "GAD-7", "crisis_triggered": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert all(not item["is_si_item"] for item in data["items"])
        assert data["si_supplement_item"] is None
        assert data["si_positive_action_ko"] is None

    def test_recommendation_caveat_echoed(self):
        """Finding 3: recommendation_caveat survives to the response."""
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": "PHQ-9",
                "recommendation_caveat": "PHQ-9's mania/hypomania blind spot",
                "crisis_triggered": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["recommendation_caveat"] == "PHQ-9's mania/hypomania blind spot"

    def test_recommendation_caveat_echoed_on_not_administrable(self):
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": None,
                "recommendation_caveat": "carried caveat",
                "crisis_triggered": False,
                "session_ctrs": 5,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["recommendation_caveat"] == "carried caveat"

    def test_duplicate_administration_flagged(self):
        """Finding 4: same scale already administered this session -> flag,
        no behavior block (still returns the full plan)."""
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": "PHQ-9",
                "crisis_triggered": False,
                "administered_scale": "PHQ-9",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["duplicate_administration"] is True
        assert data["scale"] == "PHQ-9"
        assert len(data["items"]) == 9

    def test_duplicate_administration_false_when_different_scale(self):
        resp = client.post(
            "/ai/survey/plan",
            json={
                "recommended_questionnaire": "PHQ-9",
                "crisis_triggered": False,
                "administered_scale": "GAD-7",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["duplicate_administration"] is False

    def test_refusal_guidance_present_when_administrable(self):
        """Finding 5: deterministic refusal/no-response guidance."""
        resp = client.post(
            "/ai/survey/plan",
            json={"recommended_questionnaire": "PHQ-9", "crisis_triggered": False},
        )
        assert resp.status_code == 200, resp.text
        assert "강요" in resp.json()["refusal_guidance_ko"]
