from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def _normalized_for_comparison(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Cf"
    )


def _contains_disease(normalized_text: str, disease: str) -> bool:
    normalized_disease = _normalized_for_comparison(disease).strip()
    if not normalized_disease:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_disease)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def contains_candidate_disease(text: str, diseases: Iterable[str]) -> bool:
    normalized_text = _normalized_for_comparison(text)
    return any(_contains_disease(normalized_text, disease) for disease in diseases)
