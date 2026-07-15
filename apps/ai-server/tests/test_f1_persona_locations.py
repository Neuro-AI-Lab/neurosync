"""`PERSONA_LOCATIONS` + `--persona`/"Available:" help-text completeness —
PLAN-2026-W28-Q W6 (plan §9's "PERSONA_META and f1.py:1815 help text need
new-ID entries at implementation time"), the disclosed data-only f1.py
touch (non-behavioral).

Confirms VP-010/011/012 resolve through the SAME code path VP-001..004
already use (`PERSONA_LOCATIONS.get(persona_id)` at `f1.py`'s coordinate
resolution site) — no new branching, no new function.
"""

from __future__ import annotations

import inspect

from src.f1 import PERSONA_LOCATIONS, _run_simulation, main

ALL_SEVEN_PERSONAS = ("VP-001", "VP-002", "VP-003", "VP-004", "VP-010", "VP-011", "VP-012")
NEW_PERSONAS = ("VP-010", "VP-011", "VP-012")


class TestPersonaLocationsCompleteness:
    def test_all_seven_personas_have_a_location_entry(self) -> None:
        for persona_id in ALL_SEVEN_PERSONAS:
            assert persona_id in PERSONA_LOCATIONS, f"{persona_id} missing from PERSONA_LOCATIONS"

    def test_entries_are_lat_lng_float_tuples_mirroring_the_original_four(self) -> None:
        for persona_id in ALL_SEVEN_PERSONAS:
            lat, lng = PERSONA_LOCATIONS[persona_id]
            assert isinstance(lat, float)
            assert isinstance(lng, float)

    def test_new_persona_coordinates_are_within_seoul_bounding_box(self) -> None:
        """Sanity bound, not a precision claim (disclosed approximation,
        see the code comment) — catches a swapped lat/lng or a typo'd
        digit, not a geocoding-accuracy assertion."""
        # Rough Seoul metro bounding box.
        for persona_id in NEW_PERSONAS:
            lat, lng = PERSONA_LOCATIONS[persona_id]
            assert 37.4 <= lat <= 37.7
            assert 126.8 <= lng <= 127.2


class TestHelpTextMentionsNewPersonas:
    """Zero behavioral change: only the help-text strings and the
    PERSONA_LOCATIONS dict differ (verified independently by the caller
    via `git diff` on `f1.py`) — this test just locks in that the new IDs
    are actually discoverable via `--help` and the not-found message."""

    def test_persona_argument_help_lists_all_seven(self) -> None:
        source = inspect.getsource(main)
        assert '"--persona"' in source
        for persona_id in ALL_SEVEN_PERSONAS:
            assert persona_id in source

    def test_persona_not_found_message_lists_all_seven(self) -> None:
        source = inspect.getsource(_run_simulation)
        assert "Available:" in source
        for persona_id in ALL_SEVEN_PERSONAS:
            assert persona_id in source
