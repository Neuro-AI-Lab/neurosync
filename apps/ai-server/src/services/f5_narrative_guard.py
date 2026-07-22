from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_GREEK_OR_CYRILLIC_PREFIXES = ("GREEK", "CYRILLIC")


def _is_letter_or_number(character: str) -> bool:
    return unicodedata.category(character)[0] in {"L", "N"}


def _without_interstitial_marks(text: str) -> str:
    kept: list[str] = []
    index = 0
    while index < len(text):
        if unicodedata.category(text[index])[0] != "M":
            kept.append(text[index])
            index += 1
            continue
        end = index + 1
        while end < len(text) and unicodedata.category(text[end])[0] == "M":
            end += 1
        if not (
            index > 0
            and end < len(text)
            and _is_letter_or_number(text[index - 1])
            and _is_letter_or_number(text[end])
        ):
            kept.extend(text[index:end])
        index = end
    return "".join(kept)


def _normalized_for_comparison(text: str) -> str:
    without_interstitial_marks = _without_interstitial_marks(text)
    normalized = unicodedata.normalize("NFKC", without_interstitial_marks)
    return "".join(
        character
        for character in normalized.casefold()
        if unicodedata.category(character) != "Cf"
    )


def _has_greek_or_cyrillic(text: str) -> bool:
    return any(
        unicodedata.name(character, "").startswith(_GREEK_OR_CYRILLIC_PREFIXES)
        for character in text
    )


def _is_ascii_candidate(text: str) -> bool:
    return text.isascii() and any(character.isalnum() for character in text)


def _contains_disease(normalized_text: str, disease: str) -> bool:
    normalized_disease = _normalized_for_comparison(disease).strip()
    if not normalized_disease:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_disease)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def contains_candidate_disease(text: str, diseases: Iterable[str]) -> bool:
    normalized_text = _normalized_for_comparison(text)
    has_confusable_script = _has_greek_or_cyrillic(normalized_text)
    for disease in diseases:
        normalized_disease = _normalized_for_comparison(disease).strip()
        if has_confusable_script and _is_ascii_candidate(normalized_disease):
            return True
        if _contains_disease(normalized_text, normalized_disease):
            return True
    return False
