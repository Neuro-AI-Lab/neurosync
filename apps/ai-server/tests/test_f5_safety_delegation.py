from __future__ import annotations

from pathlib import Path

import pytest

import src.agents.handoff_generator as handoff_generator
import src.continuous_test as continuous_test
import src.f5 as f5
import src.services.f5_report as f5_report
from src.schemas.ai_predicted_disease import (
    AIPredictedDiseaseCandidate,
    AIPredictedDiseaseOutput,
)
from src.schemas.common import RiskLevel
from src.schemas.handoff_report import ChiefComplaintSection
from tests.test_f5 import _build_input
from tests.test_f5_report import _full_report, _minimal_report


def test_f5_narrative_guard_is_delegated(monkeypatch: pytest.MonkeyPatch) -> None:
    disease = AIPredictedDiseaseOutput(
        candidates=[
            AIPredictedDiseaseCandidate(
                disease="PTSD",
                similarity_score=0.5,
                source_id="case_card:1",
                quote="q",
            )
        ],
        mode="rag_live",
    )
    monkeypatch.setattr(
        f5,
        "contains_candidate_disease",
        lambda _text, _diseases: True,
        raising=False,
    )

    report = f5.assemble_handoff_report(
        _build_input(
            ai_predicted_disease=disease,
            narrative_enabled=True,
            narrative_text="질환명이 없는 임상 요약",
        )
    )

    assert report.a8_narrative.narrative_enabled is False


def test_markdown_chart_guard_is_delegated(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _full_report()
    report.b_longitudinal.chart_filenames.scales_ctrs_sentiment = "safe.png"
    monkeypatch.setattr(
        f5_report,
        "is_safe_chart_filename",
        lambda _filename: False,
        raising=False,
    )

    markdown = f5_report.build_markdown_report(report)

    assert "![scales_ctrs_sentiment](safe.png)" not in markdown


def test_pdf_chunking_is_delegated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        f5_report,
        "pdf_line_chunks",
        lambda _text, _max_lines: [["delegated"]],
        raising=False,
    )

    assert f5_report._pdf_line_chunks("original", 1) == [["delegated"]]


def test_fhir_safety_walk_is_delegated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        f5_report,
        "fhir_structure_violations",
        lambda _bundle, _full_urls: ["delegated violation"],
        raising=False,
    )

    violations = f5_report.validate_fhir_bundle(
        f5_report.build_fhir_bundle(_minimal_report())
    )

    assert "delegated violation" in violations


def test_handoff_risk_detection_is_delegated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        handoff_generator,
        "detect_risk_level",
        lambda _events: RiskLevel.critical,
        raising=False,
    )

    assert handoff_generator._detect_risk_level([]) is RiskLevel.critical


def test_chain_exit_status_is_delegated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        continuous_test,
        "stage_return_code",
        lambda _results: 17,
        raising=False,
    )

    assert continuous_test._chain_return_code([]) == 17


def test_contract_typing_marker_exists() -> None:
    marker = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "shared-contracts"
        / "python"
        / "src"
        / "contracts"
        / "py.typed"
    )

    assert marker.is_file()


def test_report_sanitizers_preserve_scalar_string_coercion() -> None:
    report = _full_report()
    report.a1_chief_complaint = ChiefComplaintSection(present=True, text=None)

    markdown = f5_report.build_markdown_report(report)

    assert f5_report._md_cell(None) == "None"
    assert f5_report._pdf_raw(None) == "None"
    assert "**주호소**: None" in markdown


def test_plain_dict_integer_risk_values_preserve_legacy_coercion() -> None:
    assert handoff_generator._detect_risk_level([{"ctrs_level": 1}]) is RiskLevel.critical
    assert handoff_generator._detect_risk_level([{"risk_level": 1}]) is RiskLevel.medium
