"""Handoff report format converters: Markdown → JSON, Markdown → PDF.

Both renderers are optional and additive — the markdown output is the
primary format and these converters produce alternative representations.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Section parsing ─────────────────────────────────────────────────

# Matches "## 섹션 N. Title" or "## N. Title"
_SECTION_RE = re.compile(
    r"^##\s+(?:섹션\s+)?(\d+)\.\s*(.+)$",
    re.MULTILINE,
)

# 12 section titles (Korean)
_SECTION_TITLES: dict[int, str] = {
    1: "환자 기본 정보",
    2: "평가 일시 및 환경",
    3: "주호소 및 현병력",
    4: "주요 증상",
    5: "CTRS 기반 위험도 평가",
    6: "구조화 척도 결과",
    7: "과거 병력 및 현재 약물",
    8: "업로드 문서 요약",
    9: "종단적 상태 변화",
    10: "추가 정보 필요 사항",
    11: "추천 진료과 및 사유",
    12: "근거 레지스트리",
}


def markdown_to_json(
    report_markdown: str,
    evidence_packets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a 12-section markdown handoff report into structured JSON.

    Returns a dict with:
      - sections: list of {number, title, content} dicts
      - section_count: number of sections found
      - complete: True if all 12 sections present
      - evidence_packets: pass-through from input
    """
    sections: list[dict[str, Any]] = []

    # Find all section headers and their positions
    matches = list(_SECTION_RE.finditer(report_markdown))

    for i, match in enumerate(matches):
        section_num = int(match.group(1))
        section_title = match.group(2).strip()

        # Content is between this header and the next (or end of string)
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(report_markdown)
        content = report_markdown[content_start:content_end].strip()

        sections.append({
            "number": section_num,
            "title": section_title,
            "content": content,
        })

    found_numbers = {s["number"] for s in sections}
    missing = [n for n in range(1, 13) if n not in found_numbers]

    return {
        "sections": sections,
        "section_count": len(sections),
        "complete": len(missing) == 0,
        "missing_sections": missing,
        "evidence_packets": evidence_packets or [],
    }


def markdown_to_pdf(report_markdown: str) -> Optional[bytes]:
    """Convert a handoff report markdown to PDF bytes.

    Uses reportlab if available. Returns None if reportlab is not installed
    or PDF generation fails.
    """
    try:
        return _generate_pdf(report_markdown)
    except ImportError:
        logger.warning("reportlab not installed — PDF generation skipped")
        return None
    except Exception as exc:
        logger.warning("PDF generation failed: %s", exc)
        return None


def markdown_to_pdf_base64(report_markdown: str) -> Optional[str]:
    """Convert markdown to base64-encoded PDF string."""
    pdf_bytes = markdown_to_pdf(report_markdown)
    if pdf_bytes is None:
        return None
    return base64.b64encode(pdf_bytes).decode("ascii")


# ── PDF generation (reportlab) ──────────────────────────────────────


def _generate_pdf(report_markdown: str) -> bytes:
    """Internal PDF generator using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    # Try to use a Korean-capable font; fallback to default
    heading_style = ParagraphStyle(
        "HandoffHeading",
        parent=styles["Heading2"],
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "HandoffBody",
        parent=styles["Normal"],
        spaceAfter=12,
        leading=14,
    )

    story: list[Any] = []

    # Title
    story.append(Paragraph("Handoff Report", styles["Title"]))
    story.append(Spacer(1, 12))

    # Parse sections
    parsed = markdown_to_json(report_markdown)
    for section in parsed["sections"]:
        # Section heading
        heading_text = f"Section {section['number']}. {section['title']}"
        story.append(Paragraph(heading_text, heading_style))

        # Section content — escape XML-special chars for reportlab
        content = (
            section["content"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        # Split by double newlines for paragraphs
        for para in content.split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para.replace("\n", "<br/>"), body_style))

        story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()
