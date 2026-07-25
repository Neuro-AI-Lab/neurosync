"""Regression test for BUG-075 (fixed this pass).

Pre-fix: `services/chat.py::respond` derived the progress bar exclusively
from `result.progress` (`ChatResponse.progress`) — a field ai-server's real
`DialogueOutput` never populates (see BUG-075's own reproduction: `grep -rln
progress apps/ai-server/src/` finds no populate call in `routes/chat.py`).
Every real call therefore had `result.progress is None`, freezing
`progress_ratio`/`collected_items` at their DB defaults forever regardless
of turn count.

Fix (this pass, option (b) from BUG-075's own fix direction): derive
progress directly from the round-tripped `session_state` dict every
`ChatResponse` already carries (ai-server's own `SessionState.
model_dump()` shape — `slot_coverage`/`filled_slots` keys are always
present, computed server-side every turn) via the new
`_progress_fields_from_session_state` helper — no ai-server change
required, single source of truth (never a second, independently-computed
ratio).

No DB/AIClient/httpx call in this module — `_progress_fields_from_session_
state` is a pure function; a mocked `ChatResponse.progress=None` shape is
constructed inline (a plain dict `session_state`, exactly what apps/api
actually receives on the wire) to prove the derivation no longer depends
on `.progress` at all.
"""

from __future__ import annotations

from src.services.chat import _INTAKE_TOTAL_ITEMS, _progress_fields_from_session_state


def test_progress_derived_from_session_state_slot_coverage_and_filled_slots():
    """Mirrors a real ai-server `ChatResponse` where `.progress` is `None`
    (the structural BUG-075 shape) but `.session_state` carries the real
    `slot_coverage`/`filled_slots` — the fix's whole point."""
    session_state = {
        "slot_coverage": 0.42,
        "filled_slots": ["chief_complaint", "risk_assessment"],
        # Other SessionState keys are present on the real wire but
        # irrelevant to progress derivation — included to prove the
        # helper reads only the two keys it needs, not the whole shape.
        "turn_count": 5,
        "dialogue_target_slot": "family_history",
    }

    ratio, collected_items = _progress_fields_from_session_state(session_state)

    assert ratio == 0.42
    assert collected_items == ["chief_complaint", "risk_assessment"]


def test_progress_is_none_none_when_session_state_absent():
    """First turn (or any error path with no session_state yet) — the
    caller must keep the session's LAST-KNOWN values, never fabricate 0."""
    assert _progress_fields_from_session_state(None) == (None, None)
    assert _progress_fields_from_session_state({}) == (None, None)


def test_progress_ignores_malformed_shapes_defensively():
    assert _progress_fields_from_session_state(
        {"slot_coverage": "not-a-number", "filled_slots": "not-a-list"}
    ) == (None, None)


def test_intake_total_items_matches_ai_server_patient_fillable_denominator():
    """BUG-075: `total_items` must match the SAME denominator ai-server's
    own `slot_coverage` ratio is computed over (`PATIENT_FILLABLE_SLOTS`,
    7 of 12 canonical slots) — not the old hardcoded `13`, which produced
    a ratio/fraction mismatch (dashboard-trust risk, same class as the
    VP-010 `slot_coverage` vs `grounded_coverage` split noted elsewhere)."""
    assert _INTAKE_TOTAL_ITEMS == 7
