from __future__ import annotations

import io
import logging
import traceback
from pathlib import Path
from xml.etree.ElementTree import fromstring

import pypdf
import pytest
from fastapi import HTTPException

import src.routes.handoff as handoff_route
import src.services.f5_report as f5_report
from src.schemas.handoff_report import HandoffReportOutput
from src.services.f5_fhir_safety import (
    InvalidFhirBundleError,
    JsonObject,
    narrative_div,
)
from src.services.f5_report import (
    build_markdown_report,
    build_pdf_report,
    save_f5_result,
)
from src.services.f5_xml_text import sanitize_xml_10
from tests.test_f5_report import full_report_fixture, minimal_report_fixture
from tests.test_handoff_report_pdf_failure import report_request


@pytest.mark.parametrize(
    ("forbidden", "expected"),
    [
        ("\x00", "\ufffd"),
        ("\x08", "\ufffd"),
        ("\x0b", "\ufffd"),
        ("\x0c", "\ufffd"),
        ("\x1f", "\ufffd"),
        ("\ud800", "\ufffd"),
        ("\udfff", "\ufffd"),
        ("\ufffe", "\ufffd"),
        ("\uffff", "\ufffd"),
        ("\t", "\t"),
        ("\n", "\n"),
        ("\r", "\r"),
        ("\ufffd", "\ufffd"),
    ],
)
def test_xml_10_scalar_filter_is_one_for_one(forbidden: str, expected: str) -> None:
    assert sanitize_xml_10(f"A{forbidden}B") == f"A{expected}B"


@pytest.mark.parametrize("forbidden", ["\x00", "\x08", "\x1f", "\ud800", "\ufffe"])
def test_fhir_narrative_is_parseable_and_preserves_surrounding_text(forbidden: str) -> None:
    div = narrative_div(f"ALPHA{forbidden}OMEGA")["div"]
    assert isinstance(div, str)

    parsed = fromstring(div)

    assert parsed.text == "ALPHA\ufffdOMEGA"
    assert forbidden not in div


@pytest.mark.parametrize("forbidden", ["\x00", "\ud800"])
def test_pdf_replaces_invalid_scalar_without_dropping_neighbors(forbidden: str) -> None:
    report = full_report_fixture(
        narrative_enabled=True,
        narrative_text=f"ALPHA{forbidden}OMEGA",
    )

    pdf = build_pdf_report(report, {})
    extracted = "".join(
        page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(pdf)).pages
    )

    assert forbidden not in extracted
    assert "ALPHA" in extracted
    assert "OMEGA" in extracted


def test_markdown_keeps_original_invalid_scalar_bytes() -> None:
    report = full_report_fixture(narrative_enabled=True, narrative_text="ALPHA\x00OMEGA")

    markdown = build_markdown_report(report)

    assert "ALPHA\x00OMEGA" in markdown


def test_persistence_rejects_malformed_fhir_before_creating_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinical_sentinel = "CLINICAL-FHIR-SENTINEL"

    def _malformed(_report: HandoffReportOutput) -> JsonObject:
        return {"resourceType": "Bundle", "type": "document", "entry": clinical_sentinel}

    monkeypatch.setattr(f5_report, "build_fhir_bundle", _malformed)

    with pytest.raises(InvalidFhirBundleError) as raised:
        _ = save_f5_result(minimal_report_fixture(), tmp_path, vp_id="CLINICAL-VP-SENTINEL")

    assert raised.value.violation_count > 0
    assert "CLINICAL-VP-SENTINEL" not in str(raised.value)
    assert clinical_sentinel not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert list(tmp_path.iterdir()) == []


def test_persistence_sanitizes_arbitrary_validator_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clinical_sentinel = "CLINICAL-VALIDATOR-SENTINEL"

    def _raise_validator_error(_bundle: JsonObject) -> list[str]:
        raise RuntimeError(clinical_sentinel)

    monkeypatch.setattr(f5_report, "validate_fhir_bundle", _raise_validator_error)

    with pytest.raises(InvalidFhirBundleError) as raised:
        _ = save_f5_result(minimal_report_fixture(), tmp_path)

    error = raised.value
    assert error.violation_count == 1
    assert error.__cause__ is None
    assert error.__context__ is None
    assert clinical_sentinel not in "".join(traceback.format_exception(error))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit])
def test_persistence_validator_propagates_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[KeyboardInterrupt] | type[SystemExit],
) -> None:
    def _interrupt(_bundle: JsonObject) -> list[str]:
        raise failure_type

    monkeypatch.setattr(f5_report, "validate_fhir_bundle", _interrupt)

    with pytest.raises(failure_type):
        _ = save_f5_result(minimal_report_fixture(), tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_route_sanitizes_arbitrary_validator_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clinical_sentinel = "CLINICAL-FHIR-SENTINEL"

    def _raise_validator_error(_bundle: JsonObject) -> list[str]:
        raise RuntimeError(clinical_sentinel)

    monkeypatch.setattr(handoff_route, "validate_fhir_bundle", _raise_validator_error)
    caplog.set_level(logging.ERROR, logger=handoff_route.__name__)

    with pytest.raises(HTTPException) as raised:
        _ = await handoff_route.report(report_request())

    error = raised.value
    assert error.status_code == 500
    assert error.detail == "Handoff report FHIR validation failed"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert clinical_sentinel not in "".join(traceback.format_exception(error))
    assert clinical_sentinel not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert "violation_count=" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit])
async def test_route_validator_propagates_base_exception(
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[KeyboardInterrupt] | type[SystemExit],
) -> None:
    def _interrupt(_bundle: JsonObject) -> list[str]:
        raise failure_type

    monkeypatch.setattr(handoff_route, "validate_fhir_bundle", _interrupt)

    with pytest.raises(failure_type):
        _ = await handoff_route.report(report_request())
