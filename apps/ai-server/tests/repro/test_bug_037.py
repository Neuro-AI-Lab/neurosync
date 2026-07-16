"""BUG-037 regression tests — DialogueAgent output-isolation guard.

Design: `_archive/plans/fix_design_exhaustion_bug037.md` §2. Filed: `error.md`
BUG-037 (root cause: `f1.py` Step 1b composes `risk_assessment` clinical-
note text BEFORE the Step 3 dialogue call; `_build_slot_context` renders it
into the SAME turn's prompt; the model echoed it verbatim — all 3 pre-
existing guard branches were structurally blind).

Fixtures are derived verbatim from the two calibration artifacts BUG-037
and its CVR-012 F2 bridge note cite:
  - `docs/ai/simulation_results/VP-001/VP-001_20260712_141413_
    conversation.json` turn 9 — `agent_response == slot_updates[
    "risk_assessment"] == cumulative_slots["risk_assessment"]`, byte-
    identical (the confirmed BUG-037 hit).
  - `docs/ai/simulation_results/VP-010/VP-010_20260712_141728_
    conversation.json` turn 7 — `agent_response` is a verbatim echo of the
    patient's own denial utterance (CVR-012 F2, a second, structurally
    distinct broken-generation at the same SI-screen-result pivot).

Mirrors the mock-adapter idiom already established in
`tests/repro/test_bug_030_iter2.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents import dialogue as dialogue_module
from src.agents.dialogue import DialogueAgent
from src.f1 import F1TurnLog
from src.schemas.dialogue import DialogueInput, DialogueOutput

# VP-001_20260712_141413 turn 9 (BUG-037's confirmed shipped hit) — verbatim.
_RISK_ASSESSMENT_LEAK = (
    '자살/자해 사고 탐색 질문에 부인 — 환자 발화: "아, 그런 생각은 없어요. 그냥 '
    '좀 힘들고, 무기력한 정도지 그 정도는 아니에요."'
)
_PATIENT_DENIAL_VP001 = (
    "아, 그런 생각은 없어요. 그냥 좀 힘들고, 무기력한 정도지 그 정도는 아니에요."
)
_PROPER_REPLY_VP001 = (
    "그렇다면 다행이에요. 최근에 다른 신체 질환으로 진단받으신 적이 있으신가요?"
)

# VP-010_20260712_141728 turn 7 (CVR-012 F2's cited patient-echo channel).
_PATIENT_DENIAL_VP010 = (
    "아니요, 그런 건 전혀 없어요. 진짜로요. 그런 생각은 전혀 안 들어요."
)
_PROPER_REPLY_VP010 = (
    "그렇다면 다행이에요. 이전에 정신건강의학과 진료를 받으신 적이 있으신가요?"
)


def _agent() -> DialogueAgent:
    return DialogueAgent.__new__(DialogueAgent)


def _wire_adapter_with_responses(agent: object, contents: list[str]) -> AsyncMock:
    """Mirrors `test_bug_030_iter2.py::_wire_adapter_with_responses`."""
    router = MagicMock()
    agent._router = router  # type: ignore[attr-defined]

    def _resp(content: str) -> MagicMock:
        resp = MagicMock()
        resp.content = content
        resp.model = "test-model"
        resp.latency_ms = 1.0
        return resp

    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(side_effect=[_resp(c) for c in contents])
    router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
        supports_json_schema=False, supports_json_object=False,
    )
    router.get_adapter.return_value = adapter
    router.record_success = MagicMock()
    return adapter


def _run_agent(contents: list[str]) -> tuple[DialogueAgent, AsyncMock]:
    agent = _agent()
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "BASE_PROMPT"
    adapter = _wire_adapter_with_responses(agent, contents)
    return agent, adapter


def _json_response(text: str) -> str:
    import json

    return json.dumps({"assistant_response": text}, ensure_ascii=False)


class TestOutputIsolationViolationPureFunction:
    """Design §2 — priority order and containment/equality/min-length
    semantics of `_output_isolation_violation` in isolation."""

    def test_this_turn_value_detected_by_equality(self) -> None:
        violation = DialogueAgent._output_isolation_violation(
            _RISK_ASSESSMENT_LEAK,
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            patient_message=_PATIENT_DENIAL_VP001,
        )
        assert violation == "this_turn"

    def test_prior_turn_value_detected_when_not_this_turn(self) -> None:
        old_value = "이전 턴에 기록된 아주 긴 임상 노트 문구입니다 예시 텍스트"
        violation = DialogueAgent._output_isolation_violation(
            old_value,
            filled_slots={"chief_complaint": old_value},
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            patient_message="괜찮아요.",
        )
        assert violation == "prior_turn"

    def test_this_turn_takes_priority_over_prior_turn_and_patient_echo(self) -> None:
        """A single candidate that matches ALL THREE sources simultaneously
        must report `this_turn` — the highest-priority reason."""
        violation = DialogueAgent._output_isolation_violation(
            _RISK_ASSESSMENT_LEAK,
            filled_slots={
                "risk_assessment": _RISK_ASSESSMENT_LEAK,
                "chief_complaint": _RISK_ASSESSMENT_LEAK,
            },
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            patient_message=_RISK_ASSESSMENT_LEAK,
        )
        assert violation == "this_turn"

    def test_patient_echo_detected_verbatim(self) -> None:
        violation = DialogueAgent._output_isolation_violation(
            _PATIENT_DENIAL_VP010,
            filled_slots={},
            slot_updates_this_turn=None,
            patient_message=_PATIENT_DENIAL_VP010,
        )
        assert violation == "patient_echo"

    def test_no_match_returns_none(self) -> None:
        violation = DialogueAgent._output_isolation_violation(
            "그렇다면 다행이에요. 잠은 잘 주무시나요?",
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            slot_updates_this_turn=None,
            patient_message=_PATIENT_DENIAL_VP001,
        )
        assert violation is None

    def test_short_slot_value_below_min_length_not_flagged(self) -> None:
        """Guards against coincidental short-string collisions — a 2-char
        slot value like "없음" must not flag an otherwise-fine response
        that happens to contain it."""
        violation = DialogueAgent._output_isolation_violation(
            "특별한 증상은 없음 확인했습니다. 다른 부분은 어떠신가요?",
            filled_slots={"substance_use_history": "없음"},
            slot_updates_this_turn=None,
            patient_message="네",
        )
        assert violation is None

    def test_containment_not_just_equality(self) -> None:
        """A partial echo embedded in a longer response is also caught."""
        embedded = f"음, {_RISK_ASSESSMENT_LEAK} 다른 것도 여쭤볼게요."
        violation = DialogueAgent._output_isolation_violation(
            embedded,
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            patient_message="",
        )
        assert violation == "this_turn"

    def test_empty_response_returns_none(self) -> None:
        assert DialogueAgent._output_isolation_violation(
            "", filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            slot_updates_this_turn=None, patient_message="",
        ) is None

    def test_none_slot_updates_this_turn_falls_back_to_filled_slots(self) -> None:
        """routes/chat.py never threads `slot_updates_this_turn` — the
        guard must still catch a `filled_slots`-level leak."""
        violation = DialogueAgent._output_isolation_violation(
            _RISK_ASSESSMENT_LEAK,
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            slot_updates_this_turn=None,
            patient_message="",
        )
        assert violation == "prior_turn"


class TestBug037ShapeBlockedAndRegenerated:
    """The confirmed BUG-037 hit (VP-001_20260712_141413 turn 9) at
    run()-level: the draft ships the same-turn `risk_assessment` clinical-
    note text verbatim; the guard must block it and regenerate."""

    @pytest.mark.asyncio
    async def test_leak_triggers_retry_and_ships_regenerated_reply(self) -> None:
        agent, adapter = _run_agent([
            _json_response(_RISK_ASSESSMENT_LEAK),
            _json_response(_PROPER_REPLY_VP001),
        ])
        out = await agent.run(DialogueInput(
            session_id="t",
            user_message=_PATIENT_DENIAL_VP001,
            conversation_history=[],
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            safety_result=None,
            session_state=None,
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
        ))
        assert adapter.chat_timed.call_count == 2
        assert out.retry_count == 1
        assert out.retry_reasons == ["output_isolation_this_turn"]
        assert out.fall_through is False
        assert out.output_isolation_fallback is False
        assert out.assistant_response == _PROPER_REPLY_VP001
        assert out.assistant_response != _RISK_ASSESSMENT_LEAK

        retry_messages = adapter.chat_timed.call_args_list[1].args[0]
        retry_user_content = retry_messages[-1].content
        assert "임상 기록" in retry_user_content


class TestBug037BudgetExhaustionShipsNeutralFallback:
    """`_archive/plans/fix_design_exhaustion_bug037.md` §2 hard requirement: this
    check must NOT fall through shipping the violating text on budget
    exhaustion — a minimal neutral continuation ships instead."""

    @pytest.mark.asyncio
    async def test_exhausts_budget_ships_fallback_not_violating_text(self) -> None:
        agent, adapter = _run_agent([
            _json_response(_RISK_ASSESSMENT_LEAK),
            _json_response(_RISK_ASSESSMENT_LEAK),
            _json_response(_RISK_ASSESSMENT_LEAK),
        ])
        out = await agent.run(DialogueInput(
            session_id="t",
            user_message=_PATIENT_DENIAL_VP001,
            conversation_history=[],
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            safety_result=None,
            session_state=None,
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
        ))
        assert adapter.chat_timed.call_count == 3  # 1 draft + 2 retries, no 4th
        assert out.retry_count == 2
        # The distinguishing assertion vs the other 3 checks' exhaustion
        # path: fall_through stays False (nothing was "shipped anyway"),
        # output_isolation_fallback is True instead.
        assert out.fall_through is False
        assert out.output_isolation_fallback is True
        assert out.assistant_response == dialogue_module._OUTPUT_ISOLATION_FALLBACK_RESPONSE
        assert out.assistant_response != _RISK_ASSESSMENT_LEAK
        assert all(r == "output_isolation_this_turn" for r in out.retry_reasons)


class TestCVR012F2PatientEchoSharedMechanism:
    """CVR-012 F2 bridge note: a second, structurally distinct broken-
    generation at the SAME SI-screen-result pivot — `assistant_response`
    verbatim-echoes the patient's own denial (`VP-010_20260712_141728`
    turn 7). The design note assesses this as the SAME mechanism
    (containment/equality against a "must never ship verbatim" text set),
    just a different comparison source — proven live here."""

    @pytest.mark.asyncio
    async def test_patient_echo_triggers_retry_and_ships_regenerated_reply(self) -> None:
        agent, adapter = _run_agent([
            _json_response(_PATIENT_DENIAL_VP010),
            _json_response(_PROPER_REPLY_VP010),
        ])
        out = await agent.run(DialogueInput(
            session_id="t",
            user_message=_PATIENT_DENIAL_VP010,
            conversation_history=[],
            filled_slots={},
            safety_result=None,
            session_state=None,
        ))
        assert adapter.chat_timed.call_count == 2
        assert out.retry_count == 1
        assert out.retry_reasons == ["output_isolation_patient_echo"]
        assert out.fall_through is False
        assert out.assistant_response == _PROPER_REPLY_VP010

        retry_messages = adapter.chat_timed.call_args_list[1].args[0]
        retry_user_content = retry_messages[-1].content
        assert "그대로 반복" in retry_user_content


class TestOutputIsolationPriorityOrdering:
    """Design §2 priority: output_isolation > presence_missing >
    exact_repeat > near_dup. Placed ABOVE presence_missing deliberately
    (ADR-029 Decision 5 binds presence_missing's priority over exact_
    repeat/near_dup specifically, not over a check that did not exist at
    ratification time) — an isolation violation means the candidate is
    not a valid patient-facing message at all, the more severe failure
    class per CVR-012 F1."""

    @pytest.mark.asyncio
    async def test_isolation_wins_over_presence_missing(self) -> None:
        agent, adapter = _run_agent([
            _json_response(_RISK_ASSESSMENT_LEAK),  # leak + bare, no empathy
            _json_response("정말 힘드셨겠어요. " + _PROPER_REPLY_VP001),
        ])
        out = await agent.run(DialogueInput(
            session_id="t",
            user_message=_PATIENT_DENIAL_VP001,
            conversation_history=[],
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            safety_result={"risk_level": "high", "ctrs_level": "3"},
            session_state=None,
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
        ))
        assert out.crisis_adjacent is True
        assert out.retry_reasons == ["output_isolation_this_turn"]

        retry_messages = adapter.chat_timed.call_args_list[1].args[0]
        retry_user_content = retry_messages[-1].content
        assert "임상 기록" in retry_user_content
        assert "위기 인접" not in retry_user_content

    @pytest.mark.asyncio
    async def test_isolation_wins_over_exact_repeat(self) -> None:
        history = [
            {"role": "assistant", "content": _RISK_ASSESSMENT_LEAK},
        ]
        agent, adapter = _run_agent([
            _json_response(_RISK_ASSESSMENT_LEAK),  # exact_repeat AND isolation
            _json_response(_PROPER_REPLY_VP001),
        ])
        out = await agent.run(DialogueInput(
            session_id="t",
            user_message=_PATIENT_DENIAL_VP001,
            conversation_history=history,
            filled_slots={"risk_assessment": _RISK_ASSESSMENT_LEAK},
            safety_result=None,
            session_state=None,
            slot_updates_this_turn={"risk_assessment": _RISK_ASSESSMENT_LEAK},
        ))
        assert out.retry_reasons == ["output_isolation_this_turn"]


class TestF1TurnLogAndSchemaTelemetryThreading:
    """`f1.py`'s F1TurnLog carries the new BUG-037 telemetry field verbatim
    from a DialogueOutput, and safe defaults hold for non-guard-aware
    construction sites."""

    def test_f1_turn_log_accepts_output_isolation_fallback(self) -> None:
        dialogue_out = DialogueOutput(
            model_used="m", prompt_version="v4", latency_ms=1.0,
            assistant_response="응답",
            retry_count=2,
            retry_reasons=["output_isolation_this_turn", "output_isolation_this_turn"],
            fall_through=False,
            output_isolation_fallback=True,
            near_dup_detail=[{"reason": "back_to_back", "family": "f", "count": 2}],
        )
        turn_log = F1TurnLog(
            turn=1, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response=dialogue_out.assistant_response,
            slot_updates={}, cumulative_slots={}, slot_coverage=0.0,
            latency_ms=1.0, timestamp="t",
            dialogue_fall_through=dialogue_out.fall_through,
            dialogue_output_isolation_fallback=dialogue_out.output_isolation_fallback,
            dialogue_near_dup_detail=list(dialogue_out.near_dup_detail),
        )
        assert turn_log.dialogue_output_isolation_fallback is True
        assert turn_log.dialogue_fall_through is False
        assert turn_log.dialogue_near_dup_detail == [
            {"reason": "back_to_back", "family": "f", "count": 2},
        ]

    def test_defaults_are_safe(self) -> None:
        dialogue_out = DialogueOutput(
            model_used="m", prompt_version="v4", latency_ms=1.0,
            assistant_response="응답",
        )
        assert dialogue_out.output_isolation_fallback is False
        assert dialogue_out.near_dup_detail == []
        turn_log = F1TurnLog(
            turn=0, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response="응답", slot_updates={}, cumulative_slots={},
            slot_coverage=0.0, latency_ms=1.0, timestamp="t",
        )
        assert turn_log.dialogue_output_isolation_fallback is False
        assert turn_log.dialogue_near_dup_detail == []
