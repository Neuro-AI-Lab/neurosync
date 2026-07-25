"""PHI-safe HTTP boundary behavior for handoff PDF rendering failures."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import TypedDict

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.routes.handoff as handoff_route
from src.main import app
from src.schemas.handoff_report import HandoffReportOutput

_SECRET = "CLINICAL-SECRET-SENTINEL"


class _ClinicalSentinelError(RuntimeError):
    """Renderer failure carrying clinical-content text."""


class _SessionPayload(TypedDict):
    session_index: int
    simulated_date: str
    scenario_pack_id: str
    arc_mode: str
    final_slots: dict[str, str]
    session_ctrs: int
    turn_sentiment_polarities: list[float]
    session_id: str
    persona_id: str
    persona_name: str
    model: str


class _ReportPayload(TypedDict):
    vp_id: str
    sessions: list[_SessionPayload]
    include_charts: bool
    include_pdf: bool


def _payload() -> _ReportPayload:
    return {
        "vp_id": "vp999",
        "sessions": [
            {
                "session_index": 1,
                "simulated_date": "2026-01-01",
                "scenario_pack_id": "vp999",
                "arc_mode": "stable",
                "final_slots": {
                    "chief_complaint": "session 1 주호소",
                    "history_of_present_illness": "session 1 현병력",
                },
                "session_ctrs": 4,
                "turn_sentiment_polarities": [0.1, 0.2],
                "session_id": "s1",
                "persona_id": "vp999",
                "persona_name": "테스트환자",
                "model": "test-model",
            },
            {
                "session_index": 2,
                "simulated_date": "2026-01-15",
                "scenario_pack_id": "vp999",
                "arc_mode": "stable",
                "final_slots": {
                    "chief_complaint": "session 2 주호소",
                    "history_of_present_illness": "session 2 현병력",
                },
                "session_ctrs": 4,
                "turn_sentiment_polarities": [0.1, 0.2],
                "session_id": "s2",
                "persona_id": "vp999",
                "persona_name": "테스트환자",
                "model": "test-model",
            },
        ],
        "include_charts": False,
        "include_pdf": True,
    }


def _request() -> handoff_route.HandoffReportRequest:
    return handoff_route.HandoffReportRequest.model_validate(_payload())


report_payload = _payload
report_request = _request


def test_generic_pdf_failure_log_and_http_detail_are_phi_safe(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _raise_secret(_report: HandoffReportOutput, _chart_paths: dict[str, Path]) -> bytes:
        raise _ClinicalSentinelError(_SECRET)

    monkeypatch.setattr(handoff_route, "build_pdf_report", _raise_secret)
    caplog.set_level(logging.ERROR, logger=handoff_route.__name__)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/ai/handoff/report",
        json=_payload(),
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Handoff report PDF generation failed"}
    assert _SECRET not in response.text
    assert _SECRET not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert "pdf_status=failed" in caplog.text


@pytest.mark.asyncio
async def test_direct_route_pdf_failure_has_no_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_secret(_report: HandoffReportOutput, _chart_paths: dict[str, Path]) -> bytes:
        raise _ClinicalSentinelError(_SECRET)

    monkeypatch.setattr(handoff_route, "build_pdf_report", _raise_secret)

    with pytest.raises(HTTPException) as raised:
        await handoff_route.report(_request())

    failure = raised.value
    formatted = "".join(traceback.format_exception(failure))
    assert failure.__cause__ is None
    assert _SECRET not in formatted


def test_oversize_pdf_log_contains_metrics_but_no_caller_identifier(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    vp_sentinel = "CLINICAL-VP-SENTINEL"

    def _oversize_pdf(_report: HandoffReportOutput, _chart_paths: dict[str, Path]) -> bytes:
        return b"x" * (handoff_route._PDF_SIZE_GUARD_BYTES + 1)

    monkeypatch.setattr(handoff_route, "build_pdf_report", _oversize_pdf)
    payload = _payload()
    payload["vp_id"] = vp_sentinel
    caplog.set_level(logging.WARNING, logger=handoff_route.__name__)

    response = TestClient(app).post("/ai/handoff/report", json=payload)

    assert response.status_code == 200
    assert response.json()["pdf_base64"] is None
    assert response.json()["pdf_omitted_reason"] is not None
    assert vp_sentinel not in caplog.text
    assert "pdf_status=omitted" in caplog.text
    assert f"bytes={handoff_route._PDF_SIZE_GUARD_BYTES + 1}" in caplog.text
    assert f"limit={handoff_route._PDF_SIZE_GUARD_BYTES}" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit])
async def test_route_pdf_boundary_propagates_system_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[KeyboardInterrupt] | type[SystemExit],
) -> None:
    def _raise_system_exception(
        _report: HandoffReportOutput, _chart_paths: dict[str, Path]
    ) -> bytes:
        raise failure_type

    monkeypatch.setattr(handoff_route, "build_pdf_report", _raise_system_exception)

    with pytest.raises(failure_type):
        await handoff_route.report(_request())
