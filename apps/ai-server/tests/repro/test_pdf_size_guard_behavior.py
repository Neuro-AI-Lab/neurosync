"""QA gap-fill: `POST /ai/handoff/report`'s ~10MB PDF response-size guard
(`docs/ai/deployment_integration_plan.md` R1, `src/routes/handoff.py::
_PDF_SIZE_GUARD_BYTES`) had no test exercising the actual over-limit branch
before this file — `tests/test_deployment_stateless_routes.py::
TestHandoffReportRoute` only covers the normal (under-guard) PDF-included
and PDF-excluded paths. This test drives the omission branch directly by
monkeypatching `build_pdf_report` to return an oversized payload, so the
`pdf_base64=None` / `pdf_omitted_reason` set / `report_markdown`+`fhir_bundle`
still-populated contract is actually verified, not just asserted correct by
reading the code.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def _session_entry(session_index: int, simulated_date: str, **overrides) -> dict:
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
        "session_ctrs": 4,
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
    entry.update(overrides)
    return entry


class TestPdfSizeGuardOmissionBranch:
    def test_oversized_pdf_is_omitted_with_reason(self, monkeypatch) -> None:
        import src.routes.handoff as handoff_route

        # Force the guard threshold low (1 byte) so a real, tiny PDF built by
        # the real `build_pdf_report` trips the SAME comparison the route
        # uses in production against a real 10MB threshold — exercises the
        # actual branch, not a mocked PDF byte string.
        monkeypatch.setattr(handoff_route, "_PDF_SIZE_GUARD_BYTES", 1)

        sessions = [
            _session_entry(
                1, "2026-01-01",
                session_id="s1", persona_id="vp999", persona_name="테스트환자",
                model="test-model",
            ),
            _session_entry(
                2, "2026-01-15",
                session_id="s2", persona_id="vp999", persona_name="테스트환자",
                model="test-model",
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
        assert data["pdf_base64"] is None
        assert data["pdf_omitted_reason"] is not None
        assert "byte response size guard" in data["pdf_omitted_reason"]
        # Non-PDF sections are unaffected by the omission.
        assert "F5 인계 요약 보고서" in data["report_markdown"]
        assert data["fhir_bundle"]["resourceType"] == "Bundle"

    def test_under_guard_pdf_is_included(self, monkeypatch) -> None:
        import src.routes.handoff as handoff_route

        # Sanity control: an absurdly high threshold never omits.
        monkeypatch.setattr(handoff_route, "_PDF_SIZE_GUARD_BYTES", 10 * 1024 * 1024)

        sessions = [
            _session_entry(
                1, "2026-01-01",
                session_id="s1", persona_id="vp999", persona_name="테스트환자",
                model="test-model",
            ),
            _session_entry(
                2, "2026-01-15",
                session_id="s2", persona_id="vp999", persona_name="테스트환자",
                model="test-model",
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
