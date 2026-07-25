from __future__ import annotations

from datetime import datetime


class InvalidGeneratedAtError(ValueError):
    __slots__: tuple[str, ...] = ("value",)

    value: str

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__("generated_at must be a valid timezone-aware ISO timestamp")


def parse_aware_iso_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidGeneratedAtError(value) from exc
    if parsed.utcoffset() is None:
        raise InvalidGeneratedAtError(value)
    return value
