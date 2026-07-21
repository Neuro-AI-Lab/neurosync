from __future__ import annotations

from collections.abc import Set
from typing import assert_never
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


def narrative_div(text: str) -> JsonObject:
    return {
        "status": "generated",
        "div": f"<div xmlns='http://www.w3.org/1999/xhtml'>{xml_escape(text)}</div>",
    }


def _walk_fhir_json(
    value: JsonValue,
    path: str,
    full_urls: Set[str | None],
    violations: list[str],
) -> None:
    if isinstance(value, dict):
        reference = value.get("reference")
        if (
            isinstance(reference, str)
            and reference.startswith("urn:uuid:")
            and reference not in full_urls
        ):
            violations.append(f"unresolved reference: {reference}")
        div = value.get("div")
        if isinstance(div, str):
            try:
                _ = ElementTree.fromstring(div)
            except ElementTree.ParseError as error:
                violations.append(
                    f"{path}: Narrative.div is not well-formed XHTML ({error})"
                )
        for key, child in value.items():
            if child is None:
                violations.append(f"{path}.{key}: null values are forbidden in FHIR JSON")
            else:
                _walk_fhir_json(child, f"{path}.{key}", full_urls, violations)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_fhir_json(child, f"{path}[{index}]", full_urls, violations)
        return
    match value:
        case None:
            return
        case str() | int() | float():
            return
        case _:
            assert_never(value)


def fhir_structure_violations(
    bundle: JsonObject,
    full_urls: Set[str | None],
) -> list[str]:
    violations: list[str] = []
    _walk_fhir_json(bundle, "bundle", full_urls, violations)
    return violations
