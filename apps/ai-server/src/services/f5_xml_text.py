from __future__ import annotations

from typing import Final

_REPLACEMENT_CHARACTER: Final = "\ufffd"


def is_xml_10_character(character: str) -> bool:
    code_point = ord(character)
    return (
        character in "\t\n\r"
        or 0x20 <= code_point <= 0xD7FF
        or 0xE000 <= code_point <= 0xFFFD
        or 0x10000 <= code_point <= 0x10FFFF
    )


def sanitize_xml_10(text: str) -> str:
    """Replace each XML 1.0-invalid scalar one-for-one with U+FFFD."""
    return "".join(
        character if is_xml_10_character(character) else _REPLACEMENT_CHARACTER
        for character in text
    )
