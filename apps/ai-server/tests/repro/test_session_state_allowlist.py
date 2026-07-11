"""`session_state` inner-content mechanical allowlist (REV-024 ruling 3,
qa W2 flag) — standing regression guard, BUG-022-guard style.

`DialogueInput.session_state: dict[str, Any]` is field-level guarded
already (`tests/repro/test_bug_022.py` — the field itself is in
`APPROVED_FIELDS`, so a *new top-level field* cannot smuggle content past
that guard) but its VALUE was, until this fix, unconstrained — the same
class of blind spot BUG-022 itself was: an already-licensed conduit whose
CONTENTS are unchecked. Direct read of every `session_state` construction
site in `f1.py` (`discussion.md` REV-024 ruling 3) shows the actual key
space `src.f1.F1Pipeline` uses is small and fully enumerable:

  - `f1.py` ~1068-1075 (`opening_session_state`, turn 0): a subset of
    ``{opening_turn, is_revisit, carry_summary, prior_missing_slots}``.
  - `f1.py` ~1493-1512 (`session_state`, every other turn): a subset of
    ``{probe_instruction, prior_missing_slots}``.

Union across both call sites is exactly the 5 keys pinned below.

**No schema-level production guard was added — deliberately, not by
omission.** A `DialogueInput.session_state` `field_validator` allowlisting
these 5 keys was attempted first and reverted: `DialogueInput` is shared by
a SECOND, independent, currently-live production producer —
`src.routes.chat`'s `OrchestratorAgent` flow (`src/routes/chat.py:130-136`,
registered in `src/main.py`) — which passes `SessionState.model_dump()`, a
disjoint ~14-key shape (`session_id, patient_id, current_stage,
safety_status, slot_data, filled_slots, missing_essential_slots,
slot_coverage, conversation_history, stage_history, turn_count,
is_first_visit, scale_scores, error_log`, `src/schemas/orchestrator.py:
57-78`). A schema-level allowlist keyed to `f1.py`'s shape rejected that
second producer's legitimate payload outright — caught by running the
FULL suite before this fix landed, not merely this module's own tests:
`tests/test_chat_orchestrator_integration.py::
test_dialogue_input_has_session_state_field` failed with a
`pydantic.ValidationError` against the reverted validator. REV-024's own
"session_state inner keys... fully enumerable" claim is correct SCOPED TO
`f1.py`; it does not extend to the schema field itself, which is
genuinely polymorphic across two independent callers. Per this dispatch's
own brief ("if no clean production home exists, the standing test over
construction sites + a composed-payload assertion is acceptable"), the
guard below is CALLER-scoped (`f1.py`'s own construction sites), not
schema-scoped — mirroring `test_bug_022.py`'s own precedent exactly (that
file's `APPROVED_FIELDS`/`BUG_022_FORBIDDEN_FIELDS` also live in the TEST
file, not in the schema module).

Two independent assertion styles below, both caller-scoped:

1. Composed-payload assertions (`TestComposedPayloadShapesAreAllowlisted`):
   every distinct dict SHAPE `f1.py`'s source explicitly builds (read
   directly off the two construction sites) is checked against the
   allowlist as a plain dict comparison — no schema/validator involved,
   this is the "composed-payload assertion" the brief's fallback names.
2. Construction-site integration coverage
   (`TestConstructionSitesEndToEnd`): real `F1Pipeline.run_session` runs
   (via `tests.f1_testkit`'s stub agents, no LLM) through every scenario
   that reaches a distinct `session_state` shape — first-visit opening,
   revisit opening (carry_summary + prior_missing_slots), probe-mode
   turns, the mandatory SI-screen turn, and a revisit continuity turn
   (prior_missing_slots only) — sweeping EVERY captured
   `DialogueInput.session_state` across the whole session against the
   allowlist. This exercises `f1.py`'s actual dict-building code, not a
   hand-copied fixture, so a future edit that adds a new key at either
   site is caught automatically rather than requiring this file to be
   remembered and updated in lockstep.
"""

from __future__ import annotations

import pytest

from tests.f1_testkit import (
    StubDialogueAgent,
    StubSafetyAgent,
    StubSlotAgent,
    make_patient_fn,
    make_pipeline,
)

# Caller-scoped allowlist for `src.f1.F1Pipeline`'s own `session_state`
# construction sites ONLY (not a `DialogueInput` schema-wide constraint —
# see this module's docstring for why). Union of both traced call sites
# (`f1.py` ~1068-1075, ~1493-1512).
APPROVED_SESSION_STATE_KEYS: frozenset[str] = frozenset(
    {"opening_turn", "is_revisit", "carry_summary", "prior_missing_slots", "probe_instruction"}
)

_U_BENIGN = "요즘 잠을 잘 못 자요."
_U_SI = "요즘 자꾸 죽고 싶다는 생각이 들어요."
_U_FREQ = "거의 매일 그런 생각이 들어요."
_U_PLAN_DENIAL = "그런 계획 같은 건 없어요. 그렇게까지 하지는 않을 거예요."


def _assert_every_call_is_allowlisted(dialogue: StubDialogueAgent) -> None:
    """Sweep ALL captured `DialogueInput` calls (not a single spot-check) —
    the mechanical proof that every construction site this session
    actually exercised stayed inside the allowlist."""
    assert dialogue.calls, "fixture must exercise at least one dialogue call"
    for i, call in enumerate(dialogue.calls):
        state = call.session_state
        if state is None:
            continue
        leaked = set(state) - APPROVED_SESSION_STATE_KEYS
        assert not leaked, f"call[{i}] session_state carries unapproved key(s): {leaked}"


class TestApprovedSessionStateKeysPin:
    """Guards the guard (mirrors test_bug_022.py's own forbidden-fields pin)."""

    def test_exactly_the_five_traced_keys(self) -> None:
        assert APPROVED_SESSION_STATE_KEYS == {
            "opening_turn",
            "is_revisit",
            "carry_summary",
            "prior_missing_slots",
            "probe_instruction",
        }


class TestComposedPayloadShapesAreAllowlisted:
    """Composed-payload assertions — every distinct shape `f1.py`'s source
    builds, checked directly against the allowlist (no schema/validator
    involved, per this dispatch's brief fallback)."""

    def test_turn0_first_visit_shape(self) -> None:
        payload = {"opening_turn": True, "is_revisit": False}
        assert set(payload) <= APPROVED_SESSION_STATE_KEYS

    def test_turn0_revisit_with_carry_and_missing_slots_shape(self) -> None:
        payload = {
            "opening_turn": True,
            "is_revisit": True,
            "carry_summary": "지난번 요약",
            "prior_missing_slots": ["family_history"],
        }
        assert set(payload) <= APPROVED_SESSION_STATE_KEYS

    def test_probe_instruction_shape(self) -> None:
        payload = {"probe_instruction": "안전 확인 질문"}
        assert set(payload) <= APPROVED_SESSION_STATE_KEYS

    def test_prior_missing_slots_only_shape(self) -> None:
        payload = {"prior_missing_slots": ["substance_use_history"]}
        assert set(payload) <= APPROVED_SESSION_STATE_KEYS

    def test_a_hypothetical_drifted_key_would_be_caught(self) -> None:
        """Guards the guard's own sensitivity: an unapproved key must fail
        this assertion style, not just the schema (which no longer
        enforces this at all — see module docstring)."""
        payload = {"opening_turn": True, "risk_assessment": "자살 사고 있음"}
        assert not (set(payload) <= APPROVED_SESSION_STATE_KEYS)


class TestConstructionSitesEndToEnd:
    """Real `F1Pipeline.run_session` runs, every distinct `session_state`
    shape `f1.py` is known to build."""

    @pytest.mark.asyncio
    async def test_first_visit_turn0_opening(self) -> None:
        dialogue = StubDialogueAgent()
        pipeline = make_pipeline(StubSafetyAgent(), dialogue, StubSlotAgent())
        await pipeline.run_session(
            patient_input_fn=make_patient_fn([_U_BENIGN, "네."]),
            session_id="t-fv", max_turns=2,
        )
        _assert_every_call_is_allowlisted(dialogue)

    @pytest.mark.asyncio
    async def test_revisit_turn0_opening_with_carry_and_missing_slots(self) -> None:
        dialogue = StubDialogueAgent()
        pipeline = make_pipeline(StubSafetyAgent(), dialogue, StubSlotAgent())
        await pipeline.run_session(
            patient_input_fn=make_patient_fn([_U_BENIGN, "네."]),
            session_id="t-rv", max_turns=2,
            is_revisit=True,
            prior_handoff="- chief_complaint: 불면",
            prior_slots={"chief_complaint": "불면"},
            prior_missing_slots=["family_history"],
            prior_session_index=1,
        )
        _assert_every_call_is_allowlisted(dialogue)

    @pytest.mark.asyncio
    async def test_probe_mode_trigger_and_deescalation(self) -> None:
        safety = StubSafetyAgent({
            _U_BENIGN: (4, []),
            _U_SI: (3, ["suicidal_ideation"]),
            _U_FREQ: (3, ["suicidal_ideation"]),
            _U_PLAN_DENIAL: (4, []),
        })
        dialogue = StubDialogueAgent()
        pipeline = make_pipeline(safety, dialogue, StubSlotAgent())
        await pipeline.run_session(
            patient_input_fn=make_patient_fn(
                [_U_BENIGN, _U_SI, _U_FREQ, _U_PLAN_DENIAL, "그냥 버티고 있어요."]
            ),
            session_id="t-probe", max_turns=5,
        )
        # at least one probe-mode call actually happened (fixture sanity)
        assert any(p is not None for p in dialogue.probe_instructions)
        _assert_every_call_is_allowlisted(dialogue)

    @pytest.mark.asyncio
    async def test_mandatory_si_screen_forced_turn(self) -> None:
        """All other slots grounded at turn 0 -> forced SI screen
        (`_SI_SCREEN_INSTRUCTION`) -> same `probe_instruction`-only shape.
        Fixture mirrors `test_f1_termination_gate.py::
        test_session_cannot_end_until_risk_grounded` (verbatim-substring
        grounding filter requires exact fixture text)."""
        u_full = (
            "석 달 전부터 잠을 못 자요. 불면이 제일 힘들어요. 정신과 진료는 처음이에요. "
            "당뇨 약을 먹고 있어요. 혼자 살아요. 가족 중에 우울증을 앓은 사람은 없어요. "
            "술은 주말에 한두 잔 마셔요."
        )
        extracted = {
            "chief_complaint": "잠을 못 자요. 불면이 제일 힘들어요",
            "history_of_present_illness": "석 달 전부터 잠을 못 자요",
            "past_psychiatric_history": "정신과 진료는 처음",
            "medical_history": "당뇨 약을 먹고 있어요",
            "personal_social_history": "혼자 살아요",
            "family_history": "가족 중에 우울증을 앓은 사람은 없어요",
            "substance_use_history": "술은 주말에 한두 잔 마셔요",
            "risk_assessment": "자살/자해 사고 명시적 부인",
        }
        slots = StubSlotAgent(lambda inp, n: dict(extracted) if n == 1 else {})
        dialogue = StubDialogueAgent()
        pipeline = make_pipeline(StubSafetyAgent(), dialogue, slots)
        await pipeline.run_session(
            patient_input_fn=make_patient_fn(
                [u_full, "아니요, 그런 생각은 전혀 없어요.", "네, 감사합니다."]
            ),
            session_id="t-si-screen", max_turns=8,
        )
        assert any(p is not None for p in dialogue.probe_instructions)
        _assert_every_call_is_allowlisted(dialogue)

    @pytest.mark.asyncio
    async def test_revisit_continuity_turn_prior_missing_slots_only(self) -> None:
        """Non-probe, non-opening turn with `prior_missing_slots` set —
        `session_state == {"prior_missing_slots": [...]}` (no carry_summary,
        no opening_turn key at this call site)."""
        dialogue = StubDialogueAgent()
        pipeline = make_pipeline(StubSafetyAgent(), dialogue, StubSlotAgent())
        await pipeline.run_session(
            patient_input_fn=make_patient_fn([_U_BENIGN, "그냥 그래요.", "네."]),
            session_id="t-continuity", max_turns=3,
            is_revisit=True,
            prior_missing_slots=["family_history", "substance_use_history"],
        )
        _assert_every_call_is_allowlisted(dialogue)
        # sanity: the continuity shape was actually exercised at least once
        # past turn 0 (turn-0's own opening_turn shape also legitimately
        # carries prior_missing_slots — this checks a LATER, non-opening
        # call also carried it without opening_turn/carry_summary).
        later_calls = [
            c for c in dialogue.calls
            if not (c.session_state or {}).get("opening_turn")
        ]
        assert any(
            (c.session_state or {}).get("prior_missing_slots") for c in later_calls
        )
