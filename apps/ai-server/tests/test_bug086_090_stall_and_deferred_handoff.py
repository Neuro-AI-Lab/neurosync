"""BUG-086/BUG-090 regression coverage (2026-07-25).

BUG-086 (critical, qa live-reproduced session `2671d9fe`): the handoff/
verification loop's exhaustion path (`VerifierAction.reject`/regenerate-
budget-exhausted/pipeline exception, WITHOUT the `risk_screening_
incomplete` escalation) used to return `OrchestratorTurnResult.
assistant_response=""` — apps/api's `ChatResponse.assistant_response`
contract (`min_length=1`) rejects that outright and silently drops the
entire turn, and because `state.handoff_delivered` never latched True on
this path, EVERY subsequent turn re-ran the full extraction+handoff+
verification pipeline and hit the same empty-string drop again — a
permanent, repeating, silent stall. Fixed: `assistant_response` is never
empty on ANY terminal outcome of `_run_post_dialogue_pipeline`, and
`state.handoff_delivered` is now latched True unconditionally once that
pipeline has run, regardless of outcome.

BUG-090 (major, same call path — also present on the SUCCESS side):
the stage-1 patient-facing ack used to be computed only AFTER the full
extraction+handoff-generation+evidence-verification chain (49-58s
live-measured), never before it. Fixed: the ack ships the instant
termination criteria are met (`_should_extract_slots` returns True);
the expensive chain is deferred to the NEXT `process_turn` call for the
session (`state.pending_handoff_pipeline`), never blocking the
termination turn's own response.
"""

from __future__ import annotations

import asyncio

import pytest

from src.agents.orchestrator import (
    _HANDOFF_ACK_MESSAGE,
    _INCOMPLETE_INTAKE_MESSAGE,
    OrchestratorAgent,
)
from src.schemas.orchestrator import OrchestratorInput, SessionStage

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


class _StubSafetyAgent:
    def __init__(self, ctrs_level: int = 5) -> None:
        self._ctrs_level = ctrs_level

    async def run(self, inp):
        from src.schemas.common import RISK_TO_CTRS, RiskLevel
        from src.schemas.safety import SafetyOutput

        risk = next(
            (r for r, c in RISK_TO_CTRS.items() if int(c) == self._ctrs_level), RiskLevel.none
        )
        return SafetyOutput(
            ctrs_level=self._ctrs_level, risk_level=risk, categories=[],
            crisis_protocol_activated=False, requires_human_review=self._ctrs_level <= 3,
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


class _StubVerifierAgentPass:
    async def run(self, inp):
        from src.agents.evidence_verifier import EvidenceVerifierOutput, VerifierAction

        return EvidenceVerifierOutput(action=VerifierAction.passed)


class _StubVerifierAgentAlwaysReject:
    """BUG-086 repro fixture: every attempt is rejected — the pipeline
    exhausts WITHOUT ever producing a verified report, and (since risk
    IS grounded) WITHOUT the ADR-044 escalation either — exactly the
    `handoff_report is None and not escalation` state BUG-086's live
    evidence hit."""

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


def _orch(handoff_agent=None, verifier_agent=None) -> OrchestratorAgent:
    orch = OrchestratorAgent(model_router=None, prompt_loader=None)  # type: ignore[arg-type]
    orch._safety_agent = _StubSafetyAgent()  # noqa: SLF001
    orch._slot_agent = _StubSlotAgentNoOp()  # noqa: SLF001
    orch._handoff_agent = handoff_agent or _StubHandoffAgent()  # noqa: SLF001
    orch._verifier_agent = verifier_agent or _StubVerifierAgentPass()  # noqa: SLF001
    return orch


def _ground_risk(orch: OrchestratorAgent, session_id: str):
    """Drive a session to the coverage+risk-grounded termination point,
    WITHOUT yet triggering the deferred handoff pipeline (turn2, the
    termination/ack turn) — the caller decides what happens next."""
    turn1 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id=session_id, raw_input="네 알겠습니다", filled_slots=_NINE_SLOTS,
            )
        )
    )
    assert turn1.probe_instruction is not None  # mandatory SI screen fired
    turn2 = asyncio.run(
        orch.process_turn(
            OrchestratorInput(
                session_id=session_id, raw_input="아니요, 그런 생각은 전혀 없어요",
                filled_slots=_NINE_SLOTS, session_state=turn1.session_state,
            )
        )
    )
    return turn2


class TestBug090DeferredHandoffPipeline:
    def test_ack_ships_before_pipeline_runs(self) -> None:
        """The termination turn itself never invokes the handoff/verifier
        agents — `pending_handoff_pipeline` is armed instead."""
        handoff_agent = _StubHandoffAgent()
        verifier_agent = _StubVerifierAgentPass()
        orch = _orch(handoff_agent, verifier_agent)

        class _CountingHandoff(_StubHandoffAgent):
            def __init__(self):
                self.calls = 0

            async def run(self, inp):
                self.calls += 1
                return await super().run(inp)

        class _CountingVerifier(_StubVerifierAgentPass):
            def __init__(self):
                self.calls = 0

            async def run(self, inp):
                self.calls += 1
                return await super().run(inp)

        counting_handoff = _CountingHandoff()
        counting_verifier = _CountingVerifier()
        orch = _orch(counting_handoff, counting_verifier)

        term_turn = _ground_risk(orch, "t-bug090-ack-first")

        assert term_turn.session_state.risk_grounded is True
        assert term_turn.current_stage == SessionStage.completed
        assert term_turn.handoff_ready is False
        assert term_turn.handoff_report is None
        assert term_turn.session_state.pending_handoff_pipeline is True
        assert term_turn.session_state.handoff_delivered is False
        assert term_turn.assistant_response == _HANDOFF_ACK_MESSAGE
        assert counting_handoff.calls == 0
        assert counting_verifier.calls == 0

    def test_pipeline_actually_runs_on_the_next_call(self) -> None:
        orch = _orch()
        term_turn = _ground_risk(orch, "t-bug090-resume")

        resumed = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-bug090-resume", raw_input="",
                    filled_slots=_NINE_SLOTS, session_state=term_turn.session_state,
                )
            )
        )
        assert resumed.handoff_ready is True
        assert resumed.handoff_report is not None
        assert resumed.session_state.handoff_delivered is True
        assert resumed.session_state.pending_handoff_pipeline is False


class TestBug086NeverEmptyAssistantResponse:
    def test_verifier_reject_exhaustion_never_ships_empty_string(self) -> None:
        """The exact BUG-086 shape: risk IS grounded (no escalation), but
        the evidence verifier rejects every attempt — `handoff_report`
        stays None. `assistant_response` must never be "" on this
        outcome, on EITHER the deferred-ack turn or the resumed
        (pipeline-run) turn."""
        orch = _orch(_StubHandoffAgent(), _StubVerifierAgentAlwaysReject())
        term_turn = _ground_risk(orch, "t-bug086-reject")

        assert term_turn.assistant_response  # ack turn — never empty
        assert term_turn.assistant_response != ""

        resumed = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-bug086-reject", raw_input="",
                    filled_slots=_NINE_SLOTS, session_state=term_turn.session_state,
                )
            )
        )
        # The invariant this bug is about: never "".
        assert resumed.assistant_response != ""
        assert resumed.assistant_response == _HANDOFF_ACK_MESSAGE
        assert resumed.handoff_ready is False
        assert resumed.handoff_report is None
        assert resumed.clinical_escalation_required is False
        assert resumed.session_state.handoff_unverified is True
        # BUG-086 latch fix: this terminal outcome must NOT re-trigger the
        # pipeline on a further turn.
        assert resumed.session_state.handoff_delivered is True

    def test_latch_prevents_infinite_pipeline_rerun_on_unverified_outcome(self) -> None:
        """The core of BUG-086's live symptom: every subsequent turn used
        to re-run the ENTIRE pipeline and drop again, forever. Now the
        pipeline runs exactly ONCE for this terminal shape."""

        class _CountingVerifierAlwaysReject(_StubVerifierAgentAlwaysReject):
            def __init__(self):
                self.calls = 0

            async def run(self, inp):
                self.calls += 1
                return await super().run(inp)

        verifier = _CountingVerifierAlwaysReject()
        orch = _orch(_StubHandoffAgent(), verifier)
        term_turn = _ground_risk(orch, "t-bug086-latch")

        resumed = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-bug086-latch", raw_input="",
                    filled_slots=_NINE_SLOTS, session_state=term_turn.session_state,
                )
            )
        )
        calls_after_first_run = verifier.calls
        assert calls_after_first_run > 0

        # Simulate several MORE patient turns after the unverified outcome
        # — none of them should re-invoke the verifier.
        state = resumed.session_state
        for i in range(3):
            follow_up = asyncio.run(
                orch.process_turn(
                    OrchestratorInput(
                        session_id="t-bug086-latch", raw_input=f"turn {i}",
                        filled_slots=_NINE_SLOTS, session_state=state,
                    )
                )
            )
            assert follow_up.assistant_response != ""
            assert follow_up.assistant_response == _HANDOFF_ACK_MESSAGE
            state = follow_up.session_state

        assert verifier.calls == calls_after_first_run  # never re-ran

    def test_escalation_ack_ships_immediately_never_empty(self) -> None:
        """The ADR-044 backstop-escalation shape: also must never emit an
        empty string, and (BUG-090) also ships immediately without
        waiting on the pipeline."""
        from src.agents.orchestrator import _MAX_DIALOGUE_TURNS
        from src.schemas.orchestrator import SessionState

        class _CountingHandoff(_StubHandoffAgent):
            def __init__(self):
                self.calls = 0

            async def run(self, inp):
                self.calls += 1
                return await super().run(inp)

        handoff_agent = _CountingHandoff()
        orch = _orch(handoff_agent, _StubVerifierAgentPass())

        state = SessionState(
            session_id="t-bug086-escalation",
            turn_count=_MAX_DIALOGUE_TURNS - 1,
            risk_grounded=False,
        )
        turn = asyncio.run(
            orch.process_turn(
                OrchestratorInput(
                    session_id="t-bug086-escalation", raw_input="네", session_state=state,
                )
            )
        )
        assert turn.clinical_escalation_required is True
        assert turn.assistant_response == _INCOMPLETE_INTAKE_MESSAGE
        assert turn.assistant_response != ""
        assert handoff_agent.calls == 0  # pipeline deferred, never blocked this turn
        assert turn.session_state.pending_handoff_pipeline is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
