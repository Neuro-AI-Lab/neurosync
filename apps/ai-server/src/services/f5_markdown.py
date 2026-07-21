from __future__ import annotations

import html
import re
from typing import Final

_MARKDOWN_PUNCTUATION_RE: Final = re.compile(r"([\\`*_{}\[\]()#+\-.!|~=])")
_SAFE_CHART_FILENAME_RE: Final = re.compile(r"[A-Za-z0-9._-]+\Z")


def _literal(text: str, *, preserve_lines: bool) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    laid_out = normalized if preserve_lines else " ".join(normalized.split())
    html_safe = html.escape(laid_out, quote=False)
    return _MARKDOWN_PUNCTUATION_RE.sub(r"\\\1", html_safe)


def inline_literal(text: str) -> str:
    return _literal(text, preserve_lines=False)


def table_cell_literal(text: str) -> str:
    return _literal(text, preserve_lines=False)


def block_literal(text: str) -> str:
    return _literal(text, preserve_lines=True)


def plain_text(text: str) -> str:
    return text


def is_safe_chart_filename(filename: str) -> bool:
    return filename not in {".", ".."} and _SAFE_CHART_FILENAME_RE.fullmatch(filename) is not None
