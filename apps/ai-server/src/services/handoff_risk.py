from __future__ import annotations

from collections.abc import Sequence
from typing import Final, assert_never

from src.schemas.common import CTRS_TO_RISK, CTRSLevel, RiskLevel
from src.schemas.handoff import RiskEvent

type JsonScalar = str | int | float | bool | None
type RiskEventData = dict[str, JsonScalar]
type RiskEventInput = RiskEvent | RiskEventData

_RISK_ORDER: Final = {
    RiskLevel.none: 0,
    RiskLevel.low: 1,
    RiskLevel.medium: 2,
    RiskLevel.high: 3,
    RiskLevel.critical: 4,
}
_RISK_BY_VALUE: Final = {risk.value: risk for risk in RiskLevel}


def risk_event_text(event: RiskEventInput) -> str:
    match event:
        case RiskEvent():
            view = event.model_dump(exclude_none=True)
            return str(view or event)
        case dict():
            return str(event)
        case _:
            assert_never(event)


def _risk_labels(event: RiskEventInput) -> tuple[str, str]:
    match event:
        case RiskEvent(risk_level=risk_level, ctrs_level=ctrs_level):
            return risk_level or "", ctrs_level or ""
        case dict():
            return str(event.get("risk_level", "")), str(event.get("ctrs_level", ""))
        case _:
            assert_never(event)


def _event_risk(event: RiskEventInput) -> RiskLevel:
    risk_label, ctrs_label = _risk_labels(event)
    candidates: list[RiskLevel] = []
    normalized_risk = risk_label.strip().lower()
    explicit_risk = _RISK_BY_VALUE.get(normalized_risk)
    if explicit_risk is not None:
        candidates.append(explicit_risk)
    normalized_ctrs = ctrs_label.strip()
    if normalized_ctrs.isascii() and normalized_ctrs.isdigit():
        try:
            ctrs_risk = CTRS_TO_RISK.get(CTRSLevel(int(normalized_ctrs)))
        except ValueError:
            ctrs_risk = None
        if ctrs_risk is not None:
            candidates.append(ctrs_risk)
    if not candidates:
        return RiskLevel.medium
    return max(candidates, key=_RISK_ORDER.__getitem__)


def detect_risk_level(events: Sequence[RiskEventInput]) -> RiskLevel:
    if not events:
        return RiskLevel.none
    return max((_event_risk(event) for event in events), key=_RISK_ORDER.__getitem__)
