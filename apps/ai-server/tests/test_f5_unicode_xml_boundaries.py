from __future__ import annotations

import io
from xml.etree.ElementTree import fromstring

import pypdf
import pytest
from reportlab.platypus import Flowable

from src.f5 import assemble_handoff_report
from src.services.f5_fhir_safety import narrative_div
from src.services.f5_narrative_guard import contains_candidate_disease
from src.services.f5_report import build_pdf_report
from tests.test_f5 import build_test_input
from tests.test_f5_report import full_report_fixture


def test_exact_fullwidth_and_format_controls_match_candidate_disease() -> None:
    # Given
    diseases = ["PTSD"]

    # When
    results = [
        contains_candidate_disease(value, diseases)
        for value in ("PTSD", "ＰＴＳＤ", "P\u200bTSD")
    ]

    # Then
    assert results == [True, True, True]


def test_ascii_short_token_does_not_match_inside_word() -> None:
    # Given
    narrative = "The patient had insomnia."

    # When
    leaked = contains_candidate_disease(narrative, ["AD"])

    # Then
    assert leaked is False


def test_precomposed_diacritic_is_not_decomposed_for_comparison() -> None:
    # Given
    narrative = "caféine"

    # When
    leaked = contains_candidate_disease(narrative, ["cafeine"])

    # Then
    assert leaked is False


def test_clean_a8_narrative_text_is_preserved() -> None:
    # Given
    clean_text = "환자는 수면 문제를 자가보고함."

    # When
    report = assemble_handoff_report(
        build_test_input(narrative_enabled=True, narrative_text=clean_text)
    )

    # Then
    assert report.a8_narrative.text == clean_text


def test_valid_fhir_xhtml_is_escaped_without_changing_text() -> None:
    # Given
    text = '앞 <중간> & "뒤"'

    # When
    div = narrative_div(text)["div"]
    assert isinstance(div, str)
    parsed = fromstring(div)

    # Then
    assert parsed.text == text


def test_valid_pdf_is_created() -> None:
    # Given
    report = full_report_fixture()

    # When
    pdf = build_pdf_report(report, {})

    # Then
    assert pdf.startswith(b"%PDF")


@pytest.mark.parametrize(
    "attack",
    ["РΤЅD", "P\u0338TSD", "P\u0301TSD", "PҺSD", "PϛSD", "P\u034fTSD"],
)
def test_confusable_or_interstitial_mark_attack_matches_latin_disease(attack: str) -> None:
    # Given
    diseases = ["PTSD"]

    # When
    leaked = contains_candidate_disease(attack, diseases)

    # Then
    assert leaked is True


def test_interstitial_mark_attack_matches_korean_disease() -> None:
    # Given
    attack = "우\u0338울증"

    # When
    leaked = contains_candidate_disease(attack, ["우울증"])

    # Then
    assert leaked is True


@pytest.mark.parametrize(
    "clean_text",
    ["The patient reports sleep difficulty.", "환자는 수면 문제를 자가보고함."],
)
def test_clean_korean_and_english_do_not_match_ascii_candidate(clean_text: str) -> None:
    assert contains_candidate_disease(clean_text, ["PTSD"]) is False


@pytest.mark.parametrize("forbidden", ["\x00", "\ud800"])
def test_fhir_xhtml_replaces_each_xml_invalid_scalar(forbidden: str) -> None:
    # Given
    text = f"앞{forbidden}뒤"

    # When
    div = narrative_div(text)["div"]
    assert isinstance(div, str)
    parsed = fromstring(div)

    # Then
    assert parsed.text == "앞\ufffd뒤"
    assert forbidden not in div


def test_pdf_paragraph_replaces_nul_without_dropping_adjacent_text() -> None:
    # Given
    report = full_report_fixture(narrative_enabled=True, narrative_text="ALPHA\x00OMEGA")

    # When
    pdf = build_pdf_report(report, {})
    extracted = "".join(
        page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(pdf)).pages
    )

    # Then
    assert "\x00" not in extracted
    assert "ALPHA" in extracted
    assert "OMEGA" in extracted


def test_pdf_build_failure_closes_output_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    observed: dict[str, io.BytesIO] = {}

    class _FailingDocument:
        def __init__(self, target: io.BytesIO, **_kwargs: float) -> None:
            observed["target"] = target

        def build(self, _story: list[Flowable]) -> None:
            raise RuntimeError("simulated ReportLab build failure")

    monkeypatch.setattr("reportlab.platypus.SimpleDocTemplate", _FailingDocument)

    # When
    with pytest.raises(RuntimeError, match="simulated ReportLab build failure"):
        _ = build_pdf_report(full_report_fixture(), {})

    # Then
    assert observed["target"].closed is True
