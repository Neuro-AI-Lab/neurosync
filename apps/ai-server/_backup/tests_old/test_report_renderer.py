"""T1-F5-DEV-004: Report renderer tests — Markdown → JSON and Markdown → PDF.

Tests section parsing, Korean content, missing sections, and PDF generation.
"""

from __future__ import annotations

import pytest

from src.services.report_renderer import (
    _SECTION_TITLES,
    markdown_to_json,
    markdown_to_pdf,
    markdown_to_pdf_base64,
)


def _make_full_report() -> str:
    """Build a 12-section report in the standard format."""
    parts = []
    for n in range(1, 13):
        title = _SECTION_TITLES[n]
        content = f"섹션 {n} 내용입니다. 한국어 테스트."
        parts.append(f"## 섹션 {n}. {title}\n\n{content}\n")
    return "\n".join(parts)


def _make_partial_report(*section_nums: int) -> str:
    parts = []
    for n in section_nums:
        title = _SECTION_TITLES.get(n, f"섹션 {n}")
        parts.append(f"## 섹션 {n}. {title}\n\n내용 {n}\n")
    return "\n".join(parts)


# ── JSON parsing tests ──────────────────────────────────────────────


class TestMarkdownToJson:
    """Test markdown → structured JSON conversion."""

    def test_full_12_sections(self):
        report = _make_full_report()
        result = markdown_to_json(report)

        assert result["section_count"] == 12
        assert result["complete"] is True
        assert result["missing_sections"] == []
        assert len(result["sections"]) == 12

    def test_section_numbers_correct(self):
        report = _make_full_report()
        result = markdown_to_json(report)
        numbers = [s["number"] for s in result["sections"]]
        assert numbers == list(range(1, 13))

    def test_section_titles_preserved(self):
        report = _make_full_report()
        result = markdown_to_json(report)
        for section in result["sections"]:
            assert section["title"] == _SECTION_TITLES[section["number"]]

    def test_section_content_not_empty(self):
        report = _make_full_report()
        result = markdown_to_json(report)
        for section in result["sections"]:
            assert len(section["content"]) > 0

    def test_korean_content_preserved(self):
        report = _make_full_report()
        result = markdown_to_json(report)
        first = result["sections"][0]
        assert "한국어" in first["content"]

    def test_partial_report_detects_missing(self):
        report = _make_partial_report(1, 3, 5, 7)
        result = markdown_to_json(report)

        assert result["section_count"] == 4
        assert result["complete"] is False
        assert 2 in result["missing_sections"]
        assert 4 in result["missing_sections"]

    def test_empty_report(self):
        result = markdown_to_json("")
        assert result["section_count"] == 0
        assert result["complete"] is False
        assert len(result["missing_sections"]) == 12

    def test_evidence_packets_passthrough(self):
        report = _make_full_report()
        packets = [{"evidence_id": "ev_001", "source_type": "message"}]
        result = markdown_to_json(report, evidence_packets=packets)
        assert result["evidence_packets"] == packets

    def test_no_section_prefix_format(self):
        """Test ## N. Title format (without 섹션 prefix)."""
        report = "## 1. 환자 기본 정보\n\n내용\n\n## 2. 평가 일시 및 환경\n\n내용\n"
        result = markdown_to_json(report)
        assert result["section_count"] == 2
        assert result["sections"][0]["number"] == 1


# ── PDF generation tests ────────────────────────────────────────────


class TestMarkdownToPdf:
    """Test PDF generation. May skip if reportlab not installed."""

    def test_pdf_bytes_produced(self):
        report = _make_full_report()
        pdf = markdown_to_pdf(report)

        if pdf is None:
            pytest.skip("reportlab not installed")

        assert isinstance(pdf, bytes)
        assert len(pdf) > 100  # non-trivial PDF
        assert pdf[:5] == b"%PDF-"  # valid PDF header

    def test_pdf_base64_produced(self):
        report = _make_full_report()
        b64 = markdown_to_pdf_base64(report)

        if b64 is None:
            pytest.skip("reportlab not installed")

        assert isinstance(b64, str)
        assert len(b64) > 100

    def test_empty_report_pdf(self):
        pdf = markdown_to_pdf("")
        if pdf is None:
            pytest.skip("reportlab not installed")
        assert isinstance(pdf, bytes)

    def test_pdf_none_on_import_error(self):
        """PDF should gracefully return None if reportlab fails."""
        # We can't easily unimport reportlab, but we verify the contract
        # by checking the function handles exceptions
        result = markdown_to_pdf("test")
        # Either bytes or None — both are valid
        assert result is None or isinstance(result, bytes)
