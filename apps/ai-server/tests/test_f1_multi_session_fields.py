"""PLAN-2026-W28-Q W2: multi-session production fields on `F1Result`/
`conversation.json` — `session_index`, `simulated_date`, `is_revisit`,
repro-metadata (`model`, `prompt_version`), `prior_handoff`, and
`carried_slot_provenance` (REV-022 Issue 7: slots that bypassed
`evaluate_slot_grounding` this session must be distinguishable from
freshly-grounded ones).
"""

from __future__ import annotations

import re

import pytest

from tests.f1_testkit import (
    StubDialogueAgent,
    StubSafetyAgent,
    StubSlotAgent,
    make_patient_fn,
    make_pipeline,
)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.mark.asyncio
async def test_defaults_first_visit_session_index_1_today_date():
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), StubSlotAgent())
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(["그냥 잠을 잘 못 자요."]),
        session_id="t-fields-default",
        max_turns=2,
    )
    assert result.session_index == 1
    assert result.is_revisit is False
    assert result.prior_handoff is None
    assert _ISO_DATE_RE.match(result.simulated_date)
    assert result.carried_slot_provenance == {}


@pytest.mark.asyncio
async def test_explicit_session_index_and_simulated_date_are_persisted():
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), StubSlotAgent())
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(["그냥 잠을 잘 못 자요."]),
        session_id="t-fields-explicit",
        max_turns=2,
        session_index=3,
        simulated_date="2026-08-15",
    )
    assert result.session_index == 3
    assert result.simulated_date == "2026-08-15"


@pytest.mark.asyncio
async def test_carried_slot_never_regrounded_gets_provenance_tag():
    """A prior slot that is never re-extracted this session stays tagged as
    carried — never mistaken for freshly-grounded (REV-022 Issue 7)."""
    slots = StubSlotAgent(lambda inp, n: {})  # extractor never returns anything
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), slots)
    prior = {"chief_complaint": "지난 세션 주호소"}

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(["그냥 그래요."]),
        session_id="t-fields-carried",
        max_turns=2,
        is_revisit=True,
        prior_slots=prior,
        prior_session_index=2,
    )

    assert result.carried_slot_provenance.get("chief_complaint") == "carried_from_session_2"


@pytest.mark.asyncio
async def test_carried_slot_reground_this_session_loses_provenance_tag():
    """Once the grounding filter accepts a FRESH value for a carried key,
    it must no longer be tagged as carried (even if the text is
    identical) — the tag reflects re-grounding, not text equality."""
    fresh_value = "오늘도 그 얘기예요"
    slots = StubSlotAgent(
        lambda inp, n: {"chief_complaint": fresh_value} if n == 1 else {}
    )
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), slots)
    prior = {"chief_complaint": "지난 세션 주호소"}

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([fresh_value, "그냥 그래요."]),
        session_id="t-fields-reground",
        max_turns=2,
        is_revisit=True,
        prior_slots=prior,
        prior_session_index=1,
    )

    assert "chief_complaint" not in result.carried_slot_provenance


@pytest.mark.asyncio
async def test_no_prior_session_index_uses_generic_provenance_tag():
    slots = StubSlotAgent(lambda inp, n: {})
    pipeline = make_pipeline(StubSafetyAgent(), StubDialogueAgent(), slots)
    prior = {"chief_complaint": "지난 세션 주호소"}

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(["그냥 그래요."]),
        session_id="t-fields-generic-tag",
        max_turns=2,
        is_revisit=True,
        prior_slots=prior,
        # prior_session_index intentionally omitted
    )

    assert result.carried_slot_provenance.get("chief_complaint") == "carried_from_prior_session"
