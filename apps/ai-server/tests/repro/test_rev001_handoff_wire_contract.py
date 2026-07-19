"""REV-001 Issue 1 regression tests (critic, `discussion.md`) — the
`handoff_ready=True`/`handoff_report=None` wire-contract gap.

Two independent parts, both required for the fix to be complete:
1. `OrchestratorTurnResult.handoff_ready` must be False whenever
   `handoff_report` is None (covered directly by
   `tests/test_orchestrator.py`/`tests/test_handoff_pipeline_integration.py`
   — this file does not duplicate those).
2. `DialogueOutput` previously had NO field that could carry
   `handoff_report` onto the wire at all — a structural absence, not a
   null-check gap (REV-001's own correction to the evidence-scan doc under
   review). This file proves the field now exists and that
   `routes/chat.py::respond` actually threads
   `OrchestratorTurnResult.handoff_report` onto it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.routes.chat import respond
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.dialogue import DialogueInput, DialogueOutput
from src.schemas.orchestrator import (
    OrchestratorTurnResult,
    SafetyStatus,
    SessionStage,
    SessionState,
)


class TestDialogueOutputHandoffReportField:
    """Part 2a — the field exists, defaults to None, is a passthrough dict."""

    def test_field_exists_and_defaults_none(self) -> None:
        out = DialogueOutput(
            model_used="test", prompt_version="v1", latency_ms=0, reason_summary="t",
            assistant_response="hi",
        )
        assert out.handoff_report is None

    def test_field_accepts_a_report_dict(self) -> None:
        report = {"report_markdown": "# Report", "evidence_packets": [], "missing_slots": []}
        out = DialogueOutput(
            model_used="test", prompt_version="v1", latency_ms=0, reason_summary="t",
            assistant_response="hi", handoff_ready=True, handoff_report=report,
        )
        assert out.handoff_report == report


def _make_orch_result(
    *, handoff_ready: bool, handoff_report: dict | None, session_id: str = "s1"
) -> OrchestratorTurnResult:
    state = SessionState(session_id=session_id, turn_count=10, slot_coverage=0.8)
    return OrchestratorTurnResult(
        session_id=session_id,
        current_stage=SessionStage.completed,
        safety_status=SafetyStatus(ctrs_level=CTRSLevel.STABLE, risk_level=RiskLevel.none),
        crisis_triggered=False,
        slot_coverage=0.8,
        handoff_ready=handoff_ready,
        handoff_report=handoff_report,
        session_state=state,
        stage_history=[],
    )


def _make_body() -> DialogueInput:
    return DialogueInput(session_id="s1", user_message="test", filled_slots={})


class TestChatRouteThreadsHandoffReport:
    """Part 2b — `routes/chat.py::respond`'s handoff-ready branch actually
    carries `OrchestratorTurnResult.handoff_report` onto `DialogueOutput`,
    closing the structural wire-contract gap REV-001 identified."""

    @pytest.mark.asyncio
    async def test_handoff_ready_response_carries_report_content(self) -> None:
        report = {
            "report_markdown": "# 사전문진 보고서\n\n내용",
            "evidence_packets": [],
            "missing_slots": [],
            "risk_level": "none",
            "trend_plot_base64": None,
        }
        orch_result = _make_orch_result(handoff_ready=True, handoff_report=report)
        orchestrator = AsyncMock()
        orchestrator.process_turn = AsyncMock(return_value=orch_result)

        out = await respond(
            _make_body(), model_router=object(), prompt_loader=object(), orchestrator=orchestrator
        )

        assert isinstance(out, DialogueOutput)
        assert out.handoff_ready is True
        assert out.handoff_report is not None
        assert out.handoff_report["report_markdown"] == report["report_markdown"]

    @pytest.mark.asyncio
    async def test_non_handoff_ready_response_never_falls_into_handoff_branch(self) -> None:
        """When the orchestrator's `handoff_ready` is False (post-REV-001-fix
        behavior on a failed handoff), the route must NOT take the
        handoff-ready shortcut — it falls through to the normal DialogueAgent
        turn instead of shipping a fake "ready" response."""
        orch_result = _make_orch_result(handoff_ready=False, handoff_report=None)
        orch_result.current_stage = SessionStage.dialogue_loop
        orchestrator = AsyncMock()
        orchestrator.process_turn = AsyncMock(return_value=orch_result)

        dialogue_output = DialogueOutput(
            model_used="test", prompt_version="v1", latency_ms=0, reason_summary="t",
            assistant_response="계속 진행할게요",
        )
        with pytest.MonkeyPatch.context() as mp:
            dialogue_agent_mock = AsyncMock()
            dialogue_agent_mock.run = AsyncMock(return_value=dialogue_output)
            mp.setattr(
                "src.routes.chat.DialogueAgent",
                lambda **kwargs: dialogue_agent_mock,
            )
            out = await respond(
                _make_body(), model_router=object(), prompt_loader=object(),
                orchestrator=orchestrator,
            )

        assert out.handoff_ready is False
        assert out.handoff_report is None
        dialogue_agent_mock.run.assert_called_once()
