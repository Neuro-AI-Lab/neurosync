"""ISS-021 hardening for the local legacy handoff-agent input.

Security review finding: ``HandoffInput.risk_events`` accepted arbitrary
strings, and ``_event_risk()`` used unicode-wide ``str.isdigit()`` + a broad
``except ValueError`` — so a unicode-confusable CTRS label such as ``"①"``
(intent: CTRS 1 = 초응급/critical) was silently floored to ``medium`` in the
clinician-facing output. ``RiskEvent`` protects the local model boundary;
``POST /ai/handoff/generate`` uses the separate shared ``HandoffRiskSignal``
contract.

Kept intact: a present-but-UNLABELLED event (no severity keys at all) still
floors to medium (issue #21 semantics).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.handoff_generator import _detect_risk_level
from src.schemas.common import RiskLevel
from src.schemas.handoff import HandoffInput, JsonScalar, RiskEvent


def _make_input(risk_events: list[dict[str, JsonScalar]]) -> HandoffInput:
    return HandoffInput.model_validate({"session_id": "s", "risk_events": list(risk_events)})


class TestSchemaValidation:
    """Local HandoffInput/RiskEvent validation and normalization semantics."""

    @pytest.mark.parametrize("label", ["①", "١", "9", "0", "abc"])
    def test_invalid_ctrs_raises(self, label: str):
        with pytest.raises(ValidationError):
            _make_input([{"ctrs_level": label}])

    def test_unknown_risk_level_raises(self):
        with pytest.raises(ValidationError):
            _make_input([{"risk_level": "severe"}])

    def test_explicit_null_severity_raises(self):
        with pytest.raises(ValidationError):
            _make_input([{"ctrs_level": None}])
        with pytest.raises(ValidationError):
            _make_input([{"risk_level": None}])

    def test_valid_labels_normalized(self):
        inp = _make_input([{"risk_level": "  CRITICAL ", "ctrs_level": " 1 "}])
        evt = inp.risk_events[0]
        assert evt.risk_level == "critical"
        assert evt.ctrs_level == "1"

    def test_integer_ctrs_coerced(self):
        inp = _make_input([{"ctrs_level": 2}])
        assert inp.risk_events[0].ctrs_level == "2"

    def test_extra_keys_preserved(self):
        # Sibling fix #20 sends {"crisis": "True"} alongside the severity keys.
        inp = _make_input([{"risk_level": "high", "ctrs_level": "2", "crisis": "True"}])
        dumped = inp.risk_events[0].model_dump()
        assert dumped["crisis"] == "True"

    def test_unlabelled_event_still_accepted(self):
        # No severity keys at all → allowed; floors to medium downstream (#21).
        inp = _make_input([{"note": "observed distress"}])
        assert inp.risk_events[0].risk_level is None

    def test_oversized_risk_events_raises(self):
        with pytest.raises(ValidationError):
            _make_input([{"risk_level": "low"}] * 101)


class TestDetectRiskLevelWithValidatedEvents:
    """_detect_risk_level must handle RiskEvent instances like dicts."""

    def test_max_across_riskevent_instances(self):
        events = [
            RiskEvent(risk_level="low"),
            RiskEvent(ctrs_level="1"),  # → critical via CTRS_TO_RISK
        ]
        assert _detect_risk_level(events) == RiskLevel.critical

    def test_unlabelled_riskevent_floors_to_medium(self):
        assert _detect_risk_level([RiskEvent()]) == RiskLevel.medium

    def test_dict_path_non_ascii_digit_floors_to_medium(self):
        # Internal dict path: non-ASCII digits never parse as CTRS (defense in depth).
        assert _detect_risk_level([{"ctrs_level": "١"}]) == RiskLevel.medium


class TestRiskEventOpenApiSchema:
    """codex P2: the request schema (/openapi.json) must ADVERTISE the severity
    constraints the validators enforce (enum + non-null), while still allowing
    field omission — else generated clients submit schema-legal payloads and
    get surprise HTTP 422s."""

    def test_schema_encodes_enum_nonnull_and_optional(self):
        schema = RiskEvent.model_json_schema()
        assert schema.get("required", []) == [], "severity fields must be omittable"
        expected = {
            "risk_level": {"none", "low", "medium", "high", "critical"},
            "ctrs_level": {"1", "2", "3", "4", "5"},
        }
        for field, labels in expected.items():
            prop = schema["properties"][field]
            assert prop.get("type") == "string", f"{field} must be a non-nullable string: {prop}"
            assert "anyOf" not in prop, f"{field} must not expose a nullable union: {prop}"
            assert "null" not in repr(prop), f"{field} must not advertise null: {prop}"
            assert "default" not in prop, f"{field} must not advertise a null default: {prop}"
            assert set(prop["enum"]) == labels, f"{field} enum must match validators: {prop}"

    def test_riskevent_schema_matches_validators(self):
        from src.schemas.handoff import _VALID_CTRS_LABELS, _VALID_RISK_LABELS

        schema = RiskEvent.model_json_schema()
        assert set(schema["properties"]["risk_level"]["enum"]) == set(_VALID_RISK_LABELS)
        assert set(schema["properties"]["ctrs_level"]["enum"]) == set(_VALID_CTRS_LABELS)


class TestRiskEventSerializationRoundTrip:
    """codex P2: an unlabeled event must round-trip via standard model_dump() —
    absent severity serializes as OMITTED, never `null` (which the validators
    would then reject), so a valid HandoffInput can be cached/retried/forwarded."""

    def test_unlabeled_event_dumps_without_null_and_revalidates(self):
        dumped = RiskEvent().model_dump()
        assert "risk_level" not in dumped and "ctrs_level" not in dumped
        RiskEvent.model_validate(dumped)  # must not raise

    def test_nested_unlabeled_event_dump_revalidates(self):
        dumped = HandoffInput(session_id="s", risk_events=[RiskEvent()]).model_dump()
        assert dumped["risk_events"] == [{}]
        assert HandoffInput.model_validate(dumped).risk_events == [RiskEvent()]

    def test_labeled_event_dumps_value_and_revalidates(self):
        dumped = RiskEvent(risk_level="high", ctrs_level="2").model_dump()
        assert dumped["risk_level"] == "high" and dumped["ctrs_level"] == "2"
        rt = RiskEvent.model_validate(dumped)
        assert rt.risk_level == "high" and rt.ctrs_level == "2"

    def test_extra_keys_preserved_through_serializer(self):
        event = RiskEvent.model_validate({"crisis": True})
        assert event.model_dump() == {"crisis": True}
