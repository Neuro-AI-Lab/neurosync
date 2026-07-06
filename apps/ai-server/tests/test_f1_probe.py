"""T1-F1-DEV-022/023: graduated safety probe state machine (mocked agents).

Covers: trigger (CTRS 3 + SI/self-harm), stage progression, lexical
belt-and-braces escalation, safety-CTRS escalation, de-escalation with a
grounded risk_assessment composed from the actual exchange, soft-safety note,
and turn-0 trigger handling.
"""

from __future__ import annotations

import pytest

from src.f1 import CRISIS_RESPONSE, _has_plan_disclosure
from tests.f1_testkit import (
    StubDialogueAgent,
    StubSafetyAgent,
    StubSlotAgent,
    make_patient_fn,
    make_pipeline,
)

_U_BENIGN = "요즘 잠을 잘 못 자요."
_U_SI = "요즘 자꾸 죽고 싶다는 생각이 들어요."
_U_FREQ = "거의 매일 그런 생각이 들어요."
_U_PLAN_DENIAL = "그런 계획 같은 건 없어요. 그렇게까지 하지는 않을 거예요."
_U_PLAN_REVEAL = "사실 방법도 정해뒀어요. 준비까지 했어요."
_U_CRISIS = "이제 정말 오늘 끝낼 거예요."


def _probe_pipeline(extra_safety: dict | None = None):
    mapping = {
        _U_BENIGN: (4, []),
        _U_SI: (3, ["suicidal_ideation"]),
        _U_FREQ: (3, ["suicidal_ideation"]),
        _U_PLAN_DENIAL: (4, []),
        _U_PLAN_REVEAL: (3, ["suicidal_ideation"]),
        _U_CRISIS: (2, ["suicidal_ideation"]),
    }
    mapping.update(extra_safety or {})
    safety = StubSafetyAgent(mapping)
    dialogue = StubDialogueAgent()
    slots = StubSlotAgent()
    return make_pipeline(safety, dialogue, slots), dialogue


@pytest.mark.asyncio
async def test_probe_trigger_and_deescalation():
    """CTRS3+SI → probe → frequency → plan denied → grounded risk, continue."""
    pipeline, dialogue = _probe_pipeline()
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(
            [_U_BENIGN, _U_SI, _U_FREQ, _U_PLAN_DENIAL, "그냥 버티고 있어요."]
        ),
        session_id="t",
        max_turns=5,
    )

    assert result.crisis_triggered is False
    assert result.risk_floor == 3
    types = [e["type"] for e in result.probe_events]
    assert types[:3] == ["trigger", "progress", "deescalation"]

    # risk_assessment composed from the ACTUAL exchange, not a template
    slot_map = {s["key"]: s["value"] for s in result.final_slots}
    assert "risk_assessment" in slot_map
    assert _U_SI[:20] in slot_map["risk_assessment"]          # trigger utterance
    assert "부인" in slot_map["risk_assessment"]               # denial recorded
    assert _U_PLAN_DENIAL[:15] in slot_map["risk_assessment"]  # patient's own words

    # probe instructions injected on the two probe turns, then withdrawn
    probes = dialogue.probe_instructions
    # dialogue calls: turn1 (normal), turn2 (probe freq), turn3 (probe plan), turn4 (normal)
    assert probes[0] is None
    assert probes[1] is not None and "자주" in probes[1]
    assert probes[2] is not None and "계획" in probes[2]
    assert probes[3] is None

    # soft-safety note (109 안내) appended to the de-escalation turn's response
    deesc_turn = next(e["turn"] for e in result.probe_events if e["type"] == "deescalation")
    turn_log = next(t for t in result.turns if t.turn == deesc_turn)
    assert "109" in turn_log.agent_response
    assert turn_log.safety_crisis is False  # non-terminating

    # session CTRS latched at 3 via the probe turns (includes turn 0)
    assert result.session_ctrs == 3


@pytest.mark.asyncio
async def test_probe_lexical_escalation():
    """Plan/means disclosure in a probe answer escalates even at CTRS 3."""
    pipeline, _ = _probe_pipeline()
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_BENIGN, _U_SI, _U_FREQ, _U_PLAN_REVEAL]),
        session_id="t",
        max_turns=6,
    )

    assert result.crisis_triggered is True
    types = [e["type"] for e in result.probe_events]
    assert "escalation" in types
    crisis_turn_log = next(t for t in result.turns if t.turn == result.crisis_turn)
    assert crisis_turn_log.agent_response == CRISIS_RESPONSE
    assert "109" in CRISIS_RESPONSE and "119" in CRISIS_RESPONSE
    # session ended at the crisis turn
    assert result.turns[-1].turn == result.crisis_turn


@pytest.mark.asyncio
async def test_probe_escalation_via_safety_ctrs():
    """A probe answer classified CTRS <= 2 by safety goes through standard crisis."""
    pipeline, _ = _probe_pipeline()
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_BENIGN, _U_SI, _U_FREQ, _U_CRISIS]),
        session_id="t",
        max_turns=6,
    )

    assert result.crisis_triggered is True
    types = [e["type"] for e in result.probe_events]
    assert "trigger" in types
    crisis_turn_log = next(t for t in result.turns if t.turn == result.crisis_turn)
    assert crisis_turn_log.agent_response == CRISIS_RESPONSE


@pytest.mark.asyncio
async def test_probe_trigger_at_turn_zero():
    """CTRS3+SI on the very first message enters probe mode without crashing
    on the duplicate turn-1 processing of the same message."""
    pipeline, dialogue = _probe_pipeline()
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_SI, _U_FREQ, _U_PLAN_DENIAL, "네..."]),
        session_id="t",
        max_turns=4,
    )

    assert result.probe_events[0]["type"] == "trigger"
    assert result.probe_events[0]["turn"] == 0
    assert result.risk_floor == 3
    # first dialogue call (turn 1) already carries the probe instruction
    assert dialogue.probe_instructions[0] is not None
    # de-escalation happened after the plan denial
    assert any(e["type"] == "deescalation" for e in result.probe_events)
    assert result.crisis_triggered is False


@pytest.mark.asyncio
async def test_probe_denial_at_frequency_stage_does_not_deescalate():
    """De-escalation requires reaching the plan/means stage (per DR-002)."""
    freq_denial = "아니요, 그런 생각은 잘 안 들어요."
    pipeline, dialogue = _probe_pipeline(extra_safety={freq_denial: (4, [])})
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(
            [_U_BENIGN, _U_SI, freq_denial, _U_PLAN_DENIAL, "네..."]
        ),
        session_id="t",
        max_turns=5,
    )

    types = [e["type"] for e in result.probe_events]
    # frequency-stage denial → progress (not deescalation), then plan denial → deescalation
    assert types[:3] == ["trigger", "progress", "deescalation"]
    deesc = next(e for e in result.probe_events if e["type"] == "deescalation")
    assert deesc["stage"] == "plan"


@pytest.mark.asyncio
async def test_extractor_risk_value_discarded_during_probe():
    """Even mid-probe, extractor-supplied risk_assessment is discarded."""
    slots = StubSlotAgent(
        lambda inp, n: {"risk_assessment": "자살/자해 사고 명시적 부인"}
    )
    safety = StubSafetyAgent({
        _U_BENIGN: (4, []),
        _U_SI: (3, ["suicidal_ideation"]),
        _U_FREQ: (3, ["suicidal_ideation"]),
        _U_PLAN_DENIAL: (4, []),
    })
    pipeline = make_pipeline(safety, StubDialogueAgent(), slots)
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_BENIGN, _U_SI, _U_FREQ, _U_PLAN_DENIAL]),
        session_id="t",
        max_turns=4,
    )

    # every turn that ran extraction discarded the fabricated risk value
    discard_turns = [t for t in result.turns if "risk_assessment" in t.slot_discards]
    assert discard_turns, "extractor risk value must be discarded, not merged"
    # the only accepted risk value is the probe-composed one
    slot_map = {s["key"]: s["value"] for s in result.final_slots}
    assert "부인" in slot_map["risk_assessment"]
    assert _U_SI[:20] in slot_map["risk_assessment"]
    assert slot_map["risk_assessment"] != "자살/자해 사고 명시적 부인"


# ── ISS-043: clause-local negation veto for plan disclosure ──────────

_U_PLAN_MIXED = "계획을 세워뒀어요. 근데 아직 실행은 않았어요"


class TestIss043PlanDisclosure:
    def test_disclosure_with_trailing_negation_is_disclosure(self):
        """Exact ISS-043 phrase: the patient HAS a plan — a negation in a
        LATER clause must not veto the affirmative disclosure clause."""
        assert _has_plan_disclosure(_U_PLAN_MIXED) is True

    def test_disclosure_after_negated_clause_is_disclosure(self):
        assert _has_plan_disclosure("계획은 없는데 방법은 생각해봤어요") is True
        assert _has_plan_disclosure("사실 방법도 정해뒀어요. 준비까지 했어요.") is True

    def test_legitimate_denials_do_not_escalate(self):
        assert _has_plan_disclosure("계획 같은 건 없어요") is False
        assert _has_plan_disclosure("아니요, 계획은 없어요") is False
        assert _has_plan_disclosure(
            "그런 계획 같은 건 없어요. 그렇게까지 하지는 않을 거예요."
        ) is False
        assert _has_plan_disclosure("유서 같은 건 쓴 적 없어요") is False


@pytest.mark.asyncio
async def test_iss043_mixed_plan_negation_escalates_not_deescalates():
    """Pipeline-level ISS-043 regression: the mixed answer must escalate to
    crisis; risk_assessment must NOT be written as '계획/의도 부인'."""
    pipeline, _ = _probe_pipeline(
        extra_safety={_U_PLAN_MIXED: (3, ["suicidal_ideation"])}
    )
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn([_U_SI, _U_FREQ, _U_PLAN_MIXED]),
        session_id="t",
        max_turns=6,
    )

    assert result.crisis_triggered is True
    types = [e["type"] for e in result.probe_events]
    assert "escalation" in types
    assert "deescalation" not in types
    esc = next(e for e in result.probe_events if e["type"] == "escalation")
    assert esc["stage"] == "plan"
    # no fabricated denial label anywhere
    slot_map = {s["key"]: s["value"] for s in result.final_slots}
    assert "부인" not in slot_map.get("risk_assessment", "")
    crisis_log = next(t for t in result.turns if t.turn == result.crisis_turn)
    assert crisis_log.agent_response == CRISIS_RESPONSE


# ── QA finding 8: probe cooldown ─────────────────────────────────────

_U_CONCLUDE_SI = "계획은 없어요, 그냥 죽고 싶은 생각만 들어요"


@pytest.mark.asyncio
async def test_probe_no_retrigger_on_concluding_turn():
    """The answer that concludes a probe (de-escalation) may itself score
    CTRS3+SI — it must NOT immediately restart a new probe."""
    pipeline, _ = _probe_pipeline(
        extra_safety={_U_CONCLUDE_SI: (3, ["suicidal_ideation"])}
    )
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(
            [_U_SI, _U_FREQ, _U_CONCLUDE_SI, "네, 감사합니다."]
        ),
        session_id="t",
        max_turns=4,
    )

    triggers = [e for e in result.probe_events if e["type"] == "trigger"]
    deescalations = [e for e in result.probe_events if e["type"] == "deescalation"]
    assert len(triggers) == 1, f"cooldown violated: {result.probe_events}"
    assert len(deescalations) == 1
    assert result.crisis_triggered is False
    slot_map = {s["key"]: s["value"] for s in result.final_slots}
    assert "risk_assessment" in slot_map  # still grounded from the exchange


@pytest.mark.asyncio
async def test_probe_retrigger_cap_two_per_session():
    """A NEW SI episode in a later turn may re-trigger once (2 triggers max);
    a third episode is suppressed."""
    u1 = "요즘 기분이 가라앉아요"
    si2 = "요즘은 사라지고 싶은 마음도 들어요"
    freq2 = "그런 생각은 가끔 들긴 해요"
    denial2 = "아니요, 계획이나 방법 같은 건 없어요"
    si3 = "다 끝내버리고 싶은 기분이에요"
    pipeline, _ = _probe_pipeline(extra_safety={
        u1: (4, []),
        si2: (3, ["suicidal_ideation"]),
        freq2: (3, ["suicidal_ideation"]),
        denial2: (4, []),
        si3: (3, ["suicidal_ideation"]),
    })
    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(
            [u1, _U_SI, _U_FREQ, _U_PLAN_DENIAL, si2, freq2, denial2, si3, "네."]
        ),
        session_id="t",
        max_turns=9,
    )

    triggers = [e for e in result.probe_events if e["type"] == "trigger"]
    deescalations = [e for e in result.probe_events if e["type"] == "deescalation"]
    assert len(triggers) == 2, f"expected 2 triggers, got: {triggers}"
    assert len(deescalations) == 2
    assert result.crisis_triggered is False
    assert result.risk_floor == 3
