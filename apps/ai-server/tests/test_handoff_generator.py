"""Issue #21: _detect_risk_level must return the MAX severity across events.

The placeholder heuristic returned RiskLevel.medium for any non-empty
risk_events list, so a patient with a critical/high safety event was reported
with risk_level=medium in the structured handoff output — under-prioritising an
emergency.
"""

from __future__ import annotations

from src.agents.handoff_generator import _detect_risk_level
from src.schemas.common import RiskLevel


def test_critical_event_maps_to_critical() -> None:
    assert _detect_risk_level([{"risk_level": "critical", "ctrs_level": "1"}]) == RiskLevel.critical


def test_high_event_maps_to_high() -> None:
    assert _detect_risk_level([{"risk_level": "high", "ctrs_level": "2"}]) == RiskLevel.high


def test_ctrs_only_maps_via_ctrs_to_risk() -> None:
    # No explicit risk_level; CTRS 1 (초응급) must map to critical.
    assert _detect_risk_level([{"ctrs_level": "1"}]) == RiskLevel.critical


def test_max_across_mixed_events() -> None:
    events = [{"risk_level": "low"}, {"risk_level": "high"}, {"risk_level": "medium"}]
    assert _detect_risk_level(events) == RiskLevel.high


def test_contradictory_labels_take_max_not_explicit() -> None:
    # Issue #21: "parse each event's risk_level and/or map ctrs_level via
    # CTRS_TO_RISK, and return the max" — a contradictory pair must never
    # resolve DOWNWARD (fail-closed for clinician-facing triage metadata).
    assert _detect_risk_level([{"risk_level": "none", "ctrs_level": "1"}]) == RiskLevel.critical
    assert _detect_risk_level([{"risk_level": "low", "ctrs_level": "2"}]) == RiskLevel.high


def test_consistent_pair_unchanged_by_max_rule() -> None:
    assert _detect_risk_level([{"risk_level": "high", "ctrs_level": "3"}]) == RiskLevel.high


def test_empty_is_none() -> None:
    assert _detect_risk_level([]) == RiskLevel.none


def test_unlabeled_present_event_is_at_least_medium() -> None:
    # A present-but-unlabelled event keeps the prior "at least medium" floor.
    assert _detect_risk_level([{"foo": "bar"}]) == RiskLevel.medium
