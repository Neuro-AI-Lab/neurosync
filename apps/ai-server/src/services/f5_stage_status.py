from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class StageStatus(Protocol):
    name: str
    status: str


def stage_return_code(results: Sequence[StageStatus]) -> int:
    if any(result.status == "fail" for result in results):
        return 1
    if any(result.name == "F5" and result.status == "warn" for result in results):
        return 2
    return 0
