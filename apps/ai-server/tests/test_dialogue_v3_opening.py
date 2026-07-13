"""Dialogue v3 (PLAN-2026-W28-Q W2): autonomous turn-0 greeting + continuity
phrasing.

Covers `DialogueAgent._build_opening_context` / the continuity hint in
`_build_slot_context`, plus an `F1Pipeline` integration check that turn 0
now calls `DialogueAgent` (never a hardcoded f-string greeting) and threads
is_revisit/carry content through `session_state` only (AVC-02) — mirrors
the plan's greeting-v3 validation checks #2 (no premature clinical/slot
content) and #5 (revisit-awareness, carry-channel-licensed content only).
"""

from __future__ import annotations

import pytest

from src.agents.dialogue import DialogueAgent
from src.f1 import _compose_carry_content
from tests.f1_testkit import (
    StubDialogueAgent,
    StubSafetyAgent,
    StubSlotAgent,
    make_patient_fn,
    make_pipeline,
)


class TestBuildOpeningContext:
    def test_first_visit_has_no_prior_session_language(self) -> None:
        ctx = DialogueAgent._build_opening_context({"opening_turn": True, "is_revisit": False})
        assert "이전에 상담한 적이 있습니다" not in ctx
        assert "첫 인사" in ctx

    def test_forbids_slot_machinery_and_clinical_jargon_at_turn0(self) -> None:
        """Greeting-v3 validation check #2: no premature clinical content /
        slot-machinery language."""
        ctx = DialogueAgent._build_opening_context({"opening_turn": True, "is_revisit": False})
        assert "임상적 내용을 언급하지 마세요" in ctx
        assert "내부 시스템 용어를 언급하지 마세요" in ctx

    def test_revisit_may_reference_fact_via_carry_summary(self) -> None:
        ctx = DialogueAgent._build_opening_context({
            "opening_turn": True,
            "is_revisit": True,
            "carry_summary": "지난번에 '수면 문제' 문제로 상담하셨습니다.",
        })
        assert "이전에 상담한 적이 있습니다" in ctx
        assert "수면 문제" in ctx

    def test_revisit_never_carries_raw_risk_narrative(self) -> None:
        """AVC-02: may reference the FACT of a prior session, never raw
        risk narration — carry_summary itself (built by
        F1Pipeline._summarize_prior_handoff) never contains risk/CTRS text,
        and the static instruction explicitly forbids speculating beyond
        it."""
        ctx = DialogueAgent._build_opening_context({
            "opening_turn": True,
            "is_revisit": True,
            "carry_summary": "지난번 상담 내용을 확인했습니다.",
        })
        assert "추측하거나" in ctx
        assert "위기 프로토콜" not in ctx
        assert "CTRS" not in ctx

    def test_revisit_prior_missing_slots_are_key_names_only(self) -> None:
        ctx = DialogueAgent._build_opening_context({
            "opening_turn": True,
            "is_revisit": True,
            "prior_missing_slots": ["family_history", "substance_use_history"],
        })
        assert "family_history" in ctx
        assert "substance_use_history" in ctx


class TestSlotContextRoutesToOpeningContext:
    def test_opening_turn_flag_bypasses_round_robin_context(self) -> None:
        agent = DialogueAgent.__new__(DialogueAgent)
        ctx = agent._build_slot_context(
            filled_slots={"chief_complaint": "불면"},
            session_state={"opening_turn": True, "is_revisit": False},
            conversation_history=None,
        )
        assert "세션 시작" in ctx
        assert "이미 수집 완료" not in ctx  # round-robin-only section


class TestContinuityPhrasingHint:
    def test_target_in_prior_missing_slots_gets_continuity_hint(self) -> None:
        agent = DialogueAgent.__new__(DialogueAgent)
        ctx = agent._build_slot_context(
            filled_slots={},
            session_state={"prior_missing_slots": ["chief_complaint"]},
            conversation_history=None,
        )
        assert "연속성 안내" in ctx

    def test_no_session_state_has_no_continuity_hint(self) -> None:
        agent = DialogueAgent.__new__(DialogueAgent)
        ctx = agent._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=None,
        )
        assert "연속성 안내" not in ctx

    def test_target_not_in_prior_missing_slots_has_no_hint(self) -> None:
        agent = DialogueAgent.__new__(DialogueAgent)
        ctx = agent._build_slot_context(
            filled_slots={"chief_complaint": "불면"},
            session_state={"prior_missing_slots": ["family_history"]},
            conversation_history=None,
        )
        # target this turn is NOT chief_complaint (already filled) — assert
        # the hint only appears when the computed target is actually in the
        # prior_missing_slots set (family_history here), never unconditionally.
        assert "연속성" not in ctx or "family_history" in ctx


@pytest.mark.asyncio
async def test_f1_turn0_calls_dialogue_agent_not_hardcoded_greeting():
    """v3: DialogueAgent IS called at turn 0 with session_state carrying
    opening_turn/is_revisit — never a hardcoded f-string greeting."""
    dialogue = StubDialogueAgent()
    pipeline = make_pipeline(StubSafetyAgent(), dialogue, StubSlotAgent())

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(["그냥 잠을 잘 못 자요."]),
        session_id="t-v3-opening",
        max_turns=2,
    )

    assert len(dialogue.calls) >= 1
    opening_call = dialogue.calls[0]
    assert opening_call.session_state is not None
    assert opening_call.session_state.get("opening_turn") is True
    assert opening_call.session_state.get("is_revisit") is False
    # Repro-metadata captured from the turn-0 call (PLAN-2026-W28-Q W2).
    assert result.model == "stub"
    assert result.prompt_version == "v1"


@pytest.mark.asyncio
async def test_f1_turn0_revisit_carries_narrowed_content_only():
    """Integration check: the revisit carry channel reaching DialogueAgent's
    session_state is the SAME narrowed content persisted on F1Result — no
    raw risk_assessment prose anywhere in the path."""
    dialogue = StubDialogueAgent()
    pipeline = make_pipeline(StubSafetyAgent(), dialogue, StubSlotAgent())

    prior_slots = {"chief_complaint": "불면", "risk_assessment": "자살 사고 부인"}
    missing = ["family_history"]
    carry = _compose_carry_content(prior_slots, missing)

    result = await pipeline.run_session(
        patient_input_fn=make_patient_fn(["그냥 잠을 잘 못 자요."]),
        session_id="t-v3-revisit",
        max_turns=2,
        is_revisit=True,
        prior_handoff=carry,
        prior_slots=prior_slots,
        prior_missing_slots=missing,
        prior_session_index=1,
    )

    opening_call = dialogue.calls[0]
    assert opening_call.session_state["is_revisit"] is True
    assert "carry_summary" in opening_call.session_state
    assert "자살" not in opening_call.session_state["carry_summary"]
    assert opening_call.session_state["prior_missing_slots"] == missing

    # Persisted for F2 wiring (f2.py's prior_handoff hardcoded-None fix).
    assert result.prior_handoff == carry
    assert result.is_revisit is True
    assert "자살" not in (result.prior_handoff or "")
