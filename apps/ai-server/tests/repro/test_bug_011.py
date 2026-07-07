"""BUG-011 repro: `F1Pipeline.run_session`'s turn-0 crisis early-return never
substitutes `CRISIS_RESPONSE` into the logged/patient-facing `agent_response`.

Discovered during qa's PLAN-2026-W28-B final gate (rollback verification for
ADR-012), independently confirmed against the live EXP-003 artifacts (see
`error.md` BUG-011). This repro isolates the defect at the code level, with
no live LLM call: `f1_testkit.py`'s `StubSafetyAgent` deterministically
returns a CTRS<=2 (crisis) classification for the very first patient message,
exactly the shape safety_classifier v3 produced for SM-04a/SM-04b/SM-08b in
EXP-003 (turn0 `crisis_protocol_activated=true`).

Root cause: `src/f1.py`'s turn-0 special-case branch (~lines 546-573) builds
`F1TurnLog(agent_response=greeting, ...)` before ever checking `turn0_crisis`,
then early-returns at the `if turn0_crisis:` block without reassigning
`agent_response = CRISIS_RESPONSE` the way the main per-turn loop does at
line ~731 (`if crisis: agent_response = CRISIS_RESPONSE`). The turn-0 log is
never revisited after that early return.

Distinct from VAL-001 (`f1.py` `_has_plan_disclosure()` clause-splitting,
open in `error.md`) -- that defect corrupts which turns get classified as
crisis; this defect corrupts the crisis-response *text* after a crisis has
already been correctly (or incorrectly) classified, and only for turn 0.
"""

from __future__ import annotations

import pytest

from src.f1 import CRISIS_RESPONSE
from tests.f1_testkit import StubSafetyAgent, make_patient_fn, make_pipeline

_U_CRISIS_FIRST_MESSAGE = "지금 당장 죽고 싶어요. 방법도 정해뒀어요."
_U_FOLLOWUP = "그냥 잠을 잘 못 자요."  # never reached if session ends at turn 0


def _turn0_crisis_pipeline():
    safety = StubSafetyAgent({_U_CRISIS_FIRST_MESSAGE: (2, ["suicidal_ideation"])})
    return make_pipeline(safety=safety)


@pytest.mark.asyncio
async def test_turn0_crisis_is_classified_correctly():
    """Sanity: the classification/session-control side of turn-0 crisis is
    correct -- this repro isolates the response-text bug specifically, not a
    classification bug (that is VAL-001/EXP-003's territory)."""
    pipeline = _turn0_crisis_pipeline()
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_CRISIS_FIRST_MESSAGE, _U_FOLLOWUP]),
        session_id="t-bug011-classify",
        max_turns=5,
    )

    assert result.crisis_triggered is True
    assert result.crisis_turn == 0
    assert result.total_turns == 0
    assert len(result.turns) == 1
    assert result.turns[0].safety_crisis is True


@pytest.mark.asyncio
async def test_turn0_crisis_response_text_is_not_substituted_bug():
    """BUG-011: turn-0 `agent_response` stays the session-opening greeting
    instead of `CRISIS_RESPONSE`, even though the turn is correctly flagged
    as a crisis. This test currently PASSES because it documents the bug
    (asserts the defective behavior) -- flip both asserts once BUG-011 is
    fixed, matching the `test_bug_007.py`/`test_bug_008.py` convention of
    repro tests that pass pre-fix and must be inverted post-fix.
    """
    pipeline = _turn0_crisis_pipeline()
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_CRISIS_FIRST_MESSAGE, _U_FOLLOWUP]),
        session_id="t-bug011-text",
        max_turns=5,
    )

    turn0 = result.turns[0]
    # Bug: the crisis hotline text never reaches the turn-0 log.
    assert turn0.agent_response != CRISIS_RESPONSE
    assert "109" not in turn0.agent_response
    assert "119" not in turn0.agent_response
    # It is left at the fixed session-opening greeting instead.
    assert turn0.agent_response.startswith("안녕하세요! 저는 정신건강 사전문진을")


@pytest.mark.asyncio
async def test_turn1_plus_crisis_response_text_is_substituted_correctly():
    """Contrast case: the main per-turn loop (turn>=1) DOES substitute
    CRISIS_RESPONSE correctly -- confirms the bug is specific to the turn-0
    early-return branch, not the crisis-response mechanism in general
    (matches SM-01's live turn4 behavior in EXP-002/EXP-003, where
    `crisis_response_contains_any` passes)."""
    safety = StubSafetyAgent({
        "괜찮아요, 그냥 힘든 하루였어요.": (5, []),
        _U_CRISIS_FIRST_MESSAGE: (2, ["suicidal_ideation"]),
    })
    pipeline = make_pipeline(safety=safety)
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(
            ["괜찮아요, 그냥 힘든 하루였어요.", _U_CRISIS_FIRST_MESSAGE]
        ),
        session_id="t-bug011-contrast",
        max_turns=5,
    )

    assert result.crisis_triggered is True
    assert result.crisis_turn is not None
    assert result.crisis_turn >= 1  # i.e. NOT the turn-0 early-return path
    crisis_turn_log = next(t for t in result.turns if t.turn == result.crisis_turn)
    assert crisis_turn_log.agent_response == CRISIS_RESPONSE
    assert "109" in crisis_turn_log.agent_response
