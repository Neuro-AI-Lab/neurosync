from __future__ import annotations

from typing import Final

DEFAULT_PDF_PARAGRAPH_MAX_LINES: Final = 40


def collapse_blank_runs(text: str) -> list[str]:
    collapsed: list[str] = []
    for line in text.split("\n"):
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)
    return collapsed


def pdf_line_chunks(
    text: str,
    max_lines: int = DEFAULT_PDF_PARAGRAPH_MAX_LINES,
) -> list[list[str]]:
    lines = collapse_blank_runs(text)
    if len(lines) <= max_lines:
        return [lines]
    return [lines[index : index + max_lines] for index in range(0, len(lines), max_lines)]
