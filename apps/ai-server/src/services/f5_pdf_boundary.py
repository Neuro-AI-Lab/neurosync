"""Typed failure boundary around the external ReportLab PDF renderer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from src.schemas.handoff_report import HandoffReportOutput

type PdfRenderer = Callable[[HandoffReportOutput, dict[str, Path]], bytes]


@dataclass(frozen=True, slots=True)
class PdfRendered:
    content: bytes


@dataclass(frozen=True, slots=True)
class PdfRenderFailed:
    """Renderer failed without retaining exception or clinical content."""


type PdfRenderResult = PdfRendered | PdfRenderFailed

# ReportLab can surface multiple Exception subclasses from its rendering stack.
# This is the sole catch-all policy boundary; BaseException subclasses propagate.
_RENDERER_FAILURES: Final[tuple[type[Exception], ...]] = (Exception,)


def render_pdf(
    renderer: PdfRenderer,
    report: HandoffReportOutput,
    chart_paths: dict[str, Path],
) -> PdfRenderResult:
    """Render a PDF without carrying renderer exception data across the boundary."""
    try:
        return PdfRendered(content=renderer(report, chart_paths))
    except _RENDERER_FAILURES:
        return PdfRenderFailed()
