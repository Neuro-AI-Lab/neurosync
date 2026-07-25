"""CVR-058 regression coverage (2026-07-25, blocking finding — infinite
identical-utterance loop after `_build_post_handoff_result`'s
`unverified` branch first fires).

Before this fix, EVERY turn after `_run_post_dialogue_pipeline` concluded
with an evidence-verifier-rejected/regenerate-exhausted/exception outcome
(no escalation) shipped the exact same canned `_HANDOFF_ACK_MESSAGE`
string forever, regardless of what the patient actually said — live-
observed as a 7-turn identical-string non-responsive loop (qa session
`5f6583d4`), at a point where the patient may have just disclosed SI.

Fixed:
  1. `orchestrator.py::_build_post_handoff_result` now also sets
     `OrchestratorTurnResult.needs_closing_dialogue=True` on exactly the
     `unverified` sub-branch (never on escalation/real-success).
  2. `routes/chat.py` Step 3.5 reads that flag and, when set, calls
     `DialogueAgent`'s new lightweight "closing mode" path (ONE LLM call,
     content-aware, never re-running slot extraction/handoff generation)
     instead of shipping the canned string — with a same-content fallback
     to the canned string if the closing-mode call itself fails (BUG-086
     invariant preserved: assistant_response is never empty).
  3. `DialogueAgent._run_closing_mode` never ships the same sentence
     twice in a row (deterministic single anti-repeat retry).
  4. Crisis handling is unaffected: the safety-gate/crisis check in
     `_execute_pipeline` always runs BEFORE the `handoff_delivered`
     short-circuit, so a new crisis disclosure on an already-terminal
     session still returns via `_build_crisis_result`, never through
     `_build_post_handoff_result`/closing-mode.

Also covers the CVR-058 companion findings:
  (a) `utterance_type_classified` telemetry (CVR-057 recommendation) is
      confirmed still present in v5.7 (not regressed/removed).
  (b) `DialogueAgent._force_probe_question`'s forced-substitution splice
      no longer preserves the REJECTED candidate's own (possibly
      mismatched) leading clause — it substitutes a deterministic,
      register-neutral procedural bridge phrase instead.

No live LLM calls anywhere in this file — every adapter is a
deterministic stub.
"""

from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import (
    _PROBE_BRIDGE_POOL,
    DialogueAgent,
)
from src.agents.orchestrator import (
    _HANDOFF_ACK_MESSAGE,
    _INCOMPLETE_INTAKE_MESSAGE,
    OrchestratorAgent,
)
from src.prompts.loader import PromptLoader
from src.routes.chat import respond
from src.schemas.dialogue import DialogueInput
from src.schemas.orchestrator import OrchestratorInput, SessionStage

PROMPTS_DIR = "prompts"

_NINE_SLOTS = {
    "encounter_metadata": "40대 남성",
    "chief_complaint": "우울감",
    "history_of_present_illness": "3개월 전부터 악화",
    "past_psychiatric_history": "없음",
    "medical_history": "없음",
    "personal_social_history": "무직",
    "family_history": "없음",
    "substance_use_history": "없음",
    "mental_status_exam": "정상 외모, 저하된 기분",
}


# ── shared orchestrator-level stub fixtures (mirrors
#    test_bug086_090_stall_and_deferred_handoff.py's own scaffolding) ──


class _StubSafetyAgent:
    def __init__(self, ctrs_level: int = 5) -> None:
        self._ctrs_level = ctrs_level

    async def run(self, inp):
        from src.schemas.common import RISK_TO_CTRS, RiskLevel
        from src.schemas.safety import SafetyOutput

        risk = next(
            (r for r, c in RISK_TO_CTRS.items() if int(c) == self._ctrs_level),
            RiskLevel.none,
        )
        return SafetyOutput(
            ctrs_level=self._ctrs_level, risk_level=risk, categories=[],
            crisis_protocol_activated=self._ctrs_level <= 2,
            requires_human_review=self._ctrs_level <= 3,
        )


class _StubSlotAgentNoOp:
    async def run(self, inp):
        from src.schemas.clinical_slot import ClinicalSlotOutput

        return ClinicalSlotOutput(
            extracted_slots={}, filled_slots=[], missing_slots=[],
            essential_filled=[], essential_missing=[], slot_coverage=0.0,
        )


class _StubHandoffAgent:
    async def run(self, inp):
        from src.schemas.common import RiskLevel
        from src.schemas.handoff import HandoffOutput

        return HandoffOutput(
            report_markdown="# 테스트 핸드오프 리포트\n\n주호소: 우울감",
            evidence_packets=[], missing_slots=[], risk_level=RiskLevel.none,
        )


class _StubVerifierAgentAlwaysReject:
    async def run(self, inp):
        from src.agents.evidence_verifier import (
            EvidenceVerifierOutput,
            VerifierAction,
            VerifierIssue,
        )

        return EvidenceVerifierOutput(
            action=VerifierAction.reject,
            issues=[
                VerifierIssue(
                    severity="critical", issue_type="fabrication",
                    location="section 1", description="test-forced rejection",
                )
            ],
        )


def _orch(handoff_agent=None, verifier_agent=None, safety_agent=None) -> OrchestratorAgent:
    orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
    orch._safety_agent = safety_agent or _StubSafetyAgent()  # noqa: SLF001
    orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
    orch._handoff_agent = handoff_agent or _StubHandoffAgent()  # noqa: SLF001
    orch._verifier_agent = verifier_agent or _StubVerifierAgentAlwaysReject()  # noqa: SLF001
    return orch


def _ground_risk(orch: OrchestratorAgent, session_id: str):
    turn1 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id=session_id, raw_input="네 알겠습니다", filled_slots=_NINE_SLOTS,
            )
        )
    )
    assert turn1.probe_instruction is not None
    turn2 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id=session_id, raw_input="아니요, 그런 생각은 전혀 없어요",
                filled_slots=_NINE_SLOTS, session_state=turn1.session_state,
            )
        )
    )
    return turn2


def _drive_to_unverified(session_id: str) -> tuple[OrchestratorAgent, object]:
    """Drive a fresh session all the way to `handoff_delivered=True,
    handoff_unverified=True` (the exact BUG-086/CVR-058 terminal shape) —
    returns the orchestrator (reusable for further turns) and the
    resulting `OrchestratorTurnResult`."""
    orch = _orch()
    term_turn = _ground_risk(orch, session_id)
    resumed = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id=session_id, raw_input="",
                filled_slots=_NINE_SLOTS, session_state=term_turn.session_state,
            )
        )
    )
    assert resumed.session_state.handoff_unverified is True
    assert resumed.session_state.handoff_delivered is True
    return orch, resumed


# ── 1. orchestrator.py: needs_closing_dialogue set correctly ───────────


class TestNeedsClosingDialogueFlag:
    def test_unverified_branch_sets_flag_true(self) -> None:
        orch, resumed = _drive_to_unverified("t-cvr058-flag-unverified")

        follow_up = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-flag-unverified", raw_input="그냥 배가 아파요",
                    filled_slots=_NINE_SLOTS, session_state=resumed.session_state,
                )
            )
        )
        assert follow_up.current_stage == SessionStage.completed
        assert follow_up.clinical_escalation_required is False
        assert follow_up.needs_closing_dialogue is True
        # Safe fallback text is still populated (BUG-086 invariant).
        assert follow_up.assistant_response == _HANDOFF_ACK_MESSAGE

    def test_escalation_branch_never_sets_flag(self) -> None:
        from src.agents.orchestrator import _MAX_DIALOGUE_TURNS
        from src.schemas.orchestrator import SessionState

        orch = _orch()
        state = SessionState(
            session_id="t-cvr058-escalation", turn_count=_MAX_DIALOGUE_TURNS - 1,
            risk_grounded=False,
        )
        first = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-escalation", raw_input="네", session_state=state,
                )
            )
        )
        assert first.clinical_escalation_required is True
        assert first.needs_closing_dialogue is False
        assert first.assistant_response == _INCOMPLETE_INTAKE_MESSAGE

        follow_up = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-escalation", raw_input="추가 발화",
                    session_state=first.session_state,
                )
            )
        )
        assert follow_up.needs_closing_dialogue is False
        assert follow_up.assistant_response == _INCOMPLETE_INTAKE_MESSAGE

    def test_real_success_branch_never_sets_flag(self) -> None:
        from src.agents.evidence_verifier import EvidenceVerifierOutput, VerifierAction

        class _StubVerifierPass:
            async def run(self, inp):
                return EvidenceVerifierOutput(action=VerifierAction.passed)

        orch = _orch(verifier_agent=_StubVerifierPass())
        term_turn = _ground_risk(orch, "t-cvr058-success")
        resumed = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-success", raw_input="",
                    filled_slots=_NINE_SLOTS, session_state=term_turn.session_state,
                )
            )
        )
        assert resumed.handoff_ready is True  # real success, returns via a different route branch

        follow_up = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-success", raw_input="감사합니다",
                    session_state=resumed.session_state,
                )
            )
        )
        assert follow_up.current_stage == SessionStage.completed
        assert follow_up.needs_closing_dialogue is False


# ── 2. crisis path preserved after an unverified terminal outcome ──────


class TestCrisisPathPreservedAfterUnverified:
    def test_new_crisis_disclosure_bypasses_closing_dialogue(self) -> None:
        orch, resumed = _drive_to_unverified("t-cvr058-crisis")

        # Swap in a crisis-triggering safety agent for the NEXT turn only —
        # mirrors a genuine new disclosure after the intake concluded.
        orch._safety_agent = _StubSafetyAgent(ctrs_level=1)  # noqa: SLF001
        crisis_turn = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-crisis", raw_input="지금 당장 죽고 싶어요",
                    filled_slots=_NINE_SLOTS, session_state=resumed.session_state,
                )
            )
        )
        assert crisis_turn.crisis_triggered is True
        assert crisis_turn.current_stage == SessionStage.crisis_flow
        # Never routed through the post-handoff/closing-dialogue guard.
        assert crisis_turn.needs_closing_dialogue is False


# ── 3. DialogueAgent closing-mode: content-aware, no infinite repeat ───


class _StubSelection:
    adapter_name = "stub"
    model_id = "stub-model"
    supports_json_schema = False
    supports_json_object = True


class _StubRouter:
    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    def select_model(self, agent_name, require_json=True):
        return _StubSelection()

    def get_adapter(self, name):
        return self._adapter

    def record_success(self, name):
        pass

    def record_failure(self, name, exc):
        pass

    def get_fallback(self, agent_name, adapter_name, err):
        return None


class _ContentEchoAdapter(LLMAdapter):
    """Deterministic content-aware stub: echoes the last user message into
    the JSON reply, so the test can assert the response actually reflects
    what the patient said (never a content-blind canned string)."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_messages = None

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        self.calls += 1
        self.last_messages = messages
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        text = f'네, "{last_user}" 잘 들었습니다. 상담원이 확인 후 연락드리겠습니다.'
        return ChatResponse(
            content=json.dumps({"assistant_response": text}),
            model="stub-model",
        )


class _AlwaysSameAdapter(LLMAdapter):
    """Never varies its output regardless of anti-repeat nudge — isolates
    the case where the model itself cannot self-correct (both attempts
    exhausted, ships the repeat anyway rather than crash/hang)."""

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        return ChatResponse(
            content=json.dumps({"assistant_response": _HANDOFF_ACK_MESSAGE}),
            model="stub-model",
        )


def _closing_input(user_message: str, prior_assistant: str | None) -> DialogueInput:
    history = []
    if prior_assistant is not None:
        history.append({"role": "assistant", "content": prior_assistant})
    return DialogueInput(
        session_id="test-cvr058-closing",
        user_message=user_message,
        conversation_history=history,
        filled_slots=_NINE_SLOTS,
        session_state={"closing_mode": True},
    )


class TestDialogueClosingMode:
    def test_content_aware_response_reflects_patient_message(self) -> None:
        adapter = _ContentEchoAdapter()
        agent = DialogueAgent(
            model_router=_StubRouter(adapter), prompt_loader=PromptLoader(PROMPTS_DIR),
        )
        inp = _closing_input("사실 아직도 잠을 잘 못 자요", prior_assistant=None)
        output = asyncio.run(agent.run(inp))

        assert "사실 아직도 잠을 잘 못 자요" in output.assistant_response
        assert output.assistant_response != _HANDOFF_ACK_MESSAGE
        assert output.handoff_ready is False
        assert output.slot_updates == {}
        assert adapter.calls == 1  # no anti-repeat retry needed (content differs from prior)

    def test_never_reruns_slot_extraction_or_handoff_pipeline(self) -> None:
        """Closing mode must not import/touch clinical-slot or handoff
        machinery at all — a structural check on the method's own source,
        the same discipline BUG-090's docstring applies to its own
        deferral design."""
        source = inspect.getsource(DialogueAgent._run_closing_mode)
        assert "slot_agent" not in source
        assert "handoff_agent" not in source
        assert "verifier" not in source

    def test_anti_repeat_retries_once_when_candidate_matches_prior_turn(self) -> None:
        class _FirstRepeatsThenVaries(LLMAdapter):
            def __init__(self) -> None:
                self.calls = 0

            @property
            def adapter_name(self) -> str:
                return "stub"

            async def healthcheck(self) -> bool:
                return True

            def redact_for_log(self, payload):
                return payload

            async def chat(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    text = _HANDOFF_ACK_MESSAGE
                else:
                    text = "네, 말씀 반영해서 다시 답변드립니다."
                return ChatResponse(
                    content=f'{{"assistant_response": "{text}"}}', model="stub-model",
                )

        adapter = _FirstRepeatsThenVaries()
        agent = DialogueAgent(
            model_router=_StubRouter(adapter), prompt_loader=PromptLoader(PROMPTS_DIR),
        )
        inp = _closing_input("또 다른 이야기예요", prior_assistant=_HANDOFF_ACK_MESSAGE)
        output = asyncio.run(agent.run(inp))

        assert adapter.calls == 2  # first candidate repeated -> one anti-repeat retry
        assert output.assistant_response != _HANDOFF_ACK_MESSAGE

    def test_repeat_guard_ships_best_effort_when_model_cannot_vary(self) -> None:
        """Bounded budget (never more than 2 calls) — never hangs/loops
        indefinitely even if the model itself keeps repeating."""
        adapter = _AlwaysSameAdapter()
        agent = DialogueAgent(
            model_router=_StubRouter(adapter), prompt_loader=PromptLoader(PROMPTS_DIR),
        )
        inp = _closing_input("세 번째 이야기", prior_assistant=_HANDOFF_ACK_MESSAGE)
        output = asyncio.run(agent.run(inp))
        assert output.assistant_response  # never empty, even in the worst case


# ── 4. routes/chat.py Step 3.5: real integration through respond() ─────


class _DummyOrchestrator:
    def __init__(self, result) -> None:
        self._result = result

    async def process_turn(self, inp):
        return self._result


class TestRespondRouteClosingModeIntegration:
    def test_unverified_turn_calls_dialogue_agent_not_canned_string(self) -> None:
        orch, resumed = _drive_to_unverified("t-cvr058-route")
        follow_up_result = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-route", raw_input="사실 요즘 너무 불안해요",
                    filled_slots=_NINE_SLOTS, session_state=resumed.session_state,
                )
            )
        )
        assert follow_up_result.needs_closing_dialogue is True

        adapter = _ContentEchoAdapter()
        body = DialogueInput(
            session_id="t-cvr058-route",
            user_message="사실 요즘 너무 불안해요",
            conversation_history=[
                {"role": "assistant", "content": _HANDOFF_ACK_MESSAGE},
            ],
            filled_slots=_NINE_SLOTS,
            session_state=follow_up_result.session_state.model_dump(),
        )
        output = asyncio.run(
            respond(
                body,
                model_router=_StubRouter(adapter),
                prompt_loader=PromptLoader(PROMPTS_DIR),
                orchestrator=_DummyOrchestrator(follow_up_result),
            )
        )
        assert "사실 요즘 너무 불안해요" in output.assistant_response
        assert output.assistant_response != _HANDOFF_ACK_MESSAGE

    def test_dialogue_agent_failure_falls_back_to_canned_ack_never_empty(self) -> None:
        orch, resumed = _drive_to_unverified("t-cvr058-route-fail")
        follow_up_result = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-cvr058-route-fail", raw_input="또 다른 발화",
                    filled_slots=_NINE_SLOTS, session_state=resumed.session_state,
                )
            )
        )

        class _RaisingAdapter(LLMAdapter):
            @property
            def adapter_name(self) -> str:
                return "stub"

            async def healthcheck(self) -> bool:
                return True

            def redact_for_log(self, payload):
                return payload

            async def chat(self, messages, **kwargs):
                raise RuntimeError("simulated LLM outage")

        body = DialogueInput(
            session_id="t-cvr058-route-fail",
            user_message="또 다른 발화",
            conversation_history=[],
            filled_slots=_NINE_SLOTS,
            session_state=follow_up_result.session_state.model_dump(),
        )
        output = asyncio.run(
            respond(
                body,
                model_router=_StubRouter(_RaisingAdapter()),
                prompt_loader=PromptLoader(PROMPTS_DIR),
                orchestrator=_DummyOrchestrator(follow_up_result),
            )
        )
        # BUG-086 invariant preserved even when the closing-mode call itself fails.
        assert output.assistant_response == _HANDOFF_ACK_MESSAGE
        assert output.assistant_response != ""


# ── 5. (b) _force_probe_question: neutral bridge, not the candidate's
#        own (possibly mismatched) leading clause ──────────────────────


class TestForceProbeQuestionNeutralBridge:
    def test_mismatched_leading_clause_replaced_with_neutral_bridge(self) -> None:
        rejected_candidate = (
            "진료 예약을 하시려는 마음이 드셨군요. 혹시 근처에 원하시는 병원이 있으세요?"
        )
        result = DialogueAgent._force_probe_question(
            rejected_candidate, "plan", conversation_history=[],
        )
        assert "진료 예약을 하시려는 마음이 드셨군요" not in result
        assert any(bridge in result for bridge in _PROBE_BRIDGE_POOL)
        assert "?" in result

    def test_no_leading_clause_ships_bare_question_unchanged(self) -> None:
        candidate_starting_with_question = "혹시 방법을 생각해 보셨나요?"
        result = DialogueAgent._force_probe_question(
            candidate_starting_with_question, "plan", conversation_history=[],
        )
        assert not any(bridge in result for bridge in _PROBE_BRIDGE_POOL)
        assert "?" in result

    def test_bridge_phrase_rotates_across_session(self) -> None:
        first = DialogueAgent._select_probe_bridge_phrase(conversation_history=[])
        # Mirrors `_force_probe_question`'s own composition shape exactly
        # (`f"{bridge}. {question}"` — the pool entries carry no trailing
        # period themselves, see that constant's own docstring).
        history_with_first = [{"role": "assistant", "content": f"{first}. 이어지는 질문?"}]
        second = DialogueAgent._select_probe_bridge_phrase(history_with_first)
        assert second != first


# ── 6. (a) utterance_type_classified telemetry still present in v5.7 ──


class TestUtteranceTypeTelemetryPresent:
    def test_classify_utterance_type_method_still_exists_and_logs(self) -> None:
        """CVR-058 asked qa/developer to confirm this CVR-057-era telemetry
        (`DialogueAgent utterance_type_classified=...`) is still present in
        v5.7, not silently dropped. Confirmed: the classifier method still
        exists and `run()`'s source still logs it (non-blocking,
        deliberately not on the wire schema — see that log call's own
        comment in dialogue.py)."""
        assert hasattr(DialogueAgent, "_classify_utterance_type")
        run_source = inspect.getsource(DialogueAgent.run)
        assert "utterance_type_classified" in run_source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
