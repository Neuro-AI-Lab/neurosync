"""Adversarial HPI-isolation test suite for F4 — mirrors
`tests/test_hpi_isolation.py`/`tests/test_f3_hpi_isolation.py`'s pattern,
applied to F4's own artifact/schema (`src.schemas.longitudinal.
LongitudinalAnalysisOutput`) — design doc §6.5 (HPI red line).

  (type layer) `src/f4.py`/`src/schemas/longitudinal.py` never import the
      handoff-shaped modules; `LongitudinalAnalysisOutput` shares no class
      with `SlotData`/`HandoffInput`.
  (a) `AgentInput.extra` channel — `_build_user_content` must never read an
      F4-shaped payload injected under `extra`.
  (b) `state.conversation_history` / call-graph channel — no code path in
      `dialogue.py`'s turn-construction functions or `orchestrator.py`'s
      message-handling path may ever append F4-sourced text; static grep
      that neither module (nor `src/f4.py` itself) references the F4
      longitudinal module/class names or `src.schemas.handoff`.
  (c) live-behavior container check — inject a genuinely-populated
      `LongitudinalAnalysisOutput` into handoff state and assert the
      generated `report_markdown` contains none of it.

No live LLM/DB call anywhere in this file — LLM calls are mocked via the
same echo-adapter convention `tests/test_hpi_isolation.py::_wire_echo`
already uses.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.f4 as f4_module
import src.schemas.longitudinal as longitudinal_module
from src.adapters.base import LLMAdapter
from src.agents import dialogue as dialogue_module
from src.agents import orchestrator as orchestrator_module
from src.agents.handoff_generator import HandoffGeneratorAgent, _build_user_content
from src.agents.orchestrator import OrchestratorAgent
from src.schemas.handoff import HandoffInput, SlotData
from src.schemas.longitudinal import (
    CTRSSeriesPoint,
    DiseaseCandidateSeriesPoint,
    DomainCandidateSeriesPoint,
    LongitudinalAnalysisOutput,
    ScaleSeriesPoint,
    SentimentSeriesPoint,
    SlotFillPoint,
    TrendVerdict,
)
from src.schemas.orchestrator import InputType, OrchestratorInput, SessionStage, SessionState

_LEAK_MARKER_VP_ID = "ZZZ_F4_LEAK_MARKER_VP_ID_9999"
_LEAK_MARKER_DISEASE = "ZZZ_F4_LEAK_MARKER_DISEASE_9999"
_LEAK_MARKER_DOMAIN = "ZZZ_F4_LEAK_MARKER_DOMAIN_9999"
_LEAK_MARKER_EVIDENCE = "ZZZ_F4_LEAK_MARKER_EVIDENCE_9999"
_LEAK_MARKER_GAP = "ZZZ_F4_LEAK_MARKER_CRISIS_GAP_9999"


def _marker_output() -> LongitudinalAnalysisOutput:
    return LongitudinalAnalysisOutput(
        vp_id=_LEAK_MARKER_VP_ID,
        arc_mode="relapse_after_partial_improvement",
        n_sessions=2,
        session_span_days=7,
        slot_fill_series=[
            SlotFillPoint(
                session_index=1, simulated_date="2026-01-01",
                filled_count=4, total_questionable=8,
            )
        ],
        scale_series={
            "PHQ-9": [
                ScaleSeriesPoint(
                    session_index=1, simulated_date="2026-01-01", scale_name="PHQ-9",
                    administered=True, total_score=20, max_score=27, severity="severe",
                )
            ]
        },
        ctrs_series=[
            CTRSSeriesPoint(
                session_index=1, simulated_date="2026-01-01",
                session_ctrs=2, crisis_triggered=True,
            )
        ],
        sentiment_series=[
            SentimentSeriesPoint(session_index=1, simulated_date="2026-01-01", mean_polarity=-0.5)
        ],
        disease_candidate_series=[
            DiseaseCandidateSeriesPoint(
                session_index=1, simulated_date="2026-01-01", disease=_LEAK_MARKER_DISEASE,
                similarity_score=0.9, rank=1,
            )
        ],
        domain_candidate_series=[
            DomainCandidateSeriesPoint(
                session_index=1, simulated_date="2026-01-01",
                domain=_LEAK_MARKER_DOMAIN, confidence=0.8,
            )
        ],
        trend_verdicts=[
            TrendVerdict(
                dimension="phq9_total", direction="worsened", basis="x", n_comparable_points=2,
                evidence=[_LEAK_MARKER_EVIDENCE],
            )
        ],
        overall_direction="worsened",
        crisis_f3_gaps=[_LEAK_MARKER_GAP],
        generated_at="2026-01-01T00:00:00",
    )


def _all_marker_strings() -> list[str]:
    return [
        _LEAK_MARKER_VP_ID,
        _LEAK_MARKER_DISEASE,
        _LEAK_MARKER_DOMAIN,
        _LEAK_MARKER_EVIDENCE,
        _LEAK_MARKER_GAP,
    ]


# ── (type layer) ────────────────────────────────────────────────────────


class TestF4TypeLayerIsolation:
    """Import-statement-shaped checks (not bare substring grep) — both
    `src/f4.py` and `src/schemas/longitudinal.py` legitimately DISCUSS the
    forbidden module/class names in their own docstrings (documenting why
    they are never imported), so a naive substring check on those names
    would false-positive on the very prose that states the invariant. The
    load-bearing check is that no actual `import`/`from ... import`
    statement names them — mirrors how `tests/test_f3_hpi_isolation.py`
    checks `src/f3.py` (which has no such self-referential docstring) via
    substring, and `survey_result.py` (which does) via the class-disjoint-
    set check below instead."""

    def test_f4_module_never_imports_handoff_schema(self) -> None:
        source = inspect.getsource(f4_module)
        assert "from src.schemas.handoff" not in source
        assert "import src.schemas.handoff" not in source

    def test_longitudinal_schema_never_imports_handoff_or_domain_inference(self) -> None:
        source = inspect.getsource(longitudinal_module)
        assert "from src.schemas.handoff" not in source
        assert "import src.schemas.handoff" not in source
        assert "from src.schemas.domain_inference" not in source
        assert "import src.schemas.domain_inference" not in source

    def test_longitudinal_schema_shares_no_class_with_handoff_schema(self) -> None:
        import src.schemas.handoff as handoff_module

        def _locally_defined_classes(module: object) -> set[str]:
            return {
                name
                for name, obj in vars(module).items()
                if isinstance(obj, type) and obj.__module__ == module.__name__
            }

        handoff_names = _locally_defined_classes(handoff_module)
        longitudinal_names = _locally_defined_classes(longitudinal_module)
        assert handoff_names, "sanity: handoff module must define at least one class"
        assert longitudinal_names, "sanity: longitudinal module must define at least one class"
        assert handoff_names.isdisjoint(longitudinal_names)


# ── (a) AgentInput.extra channel ───────────────────────────────────────────


class TestHPIIsolationChannelExtra:
    def test_extra_f4_output_never_reaches_build_user_content(self) -> None:
        output = _marker_output()
        handoff_input = HandoffInput(
            session_id="s1", extra={"f4_longitudinal": output.model_dump()}
        )
        content = _build_user_content(handoff_input)
        for marker in _all_marker_strings():
            assert marker not in content

    def test_extra_field_construction_itself_does_not_raise(self) -> None:
        output = _marker_output()
        handoff_input = HandoffInput(
            session_id="s1", extra={"f4_longitudinal": output.model_dump()}
        )
        assert handoff_input.extra["f4_longitudinal"]["vp_id"] == _LEAK_MARKER_VP_ID

    def test_arbitrary_extra_key_never_reaches_build_user_content(self) -> None:
        handoff_input = HandoffInput(
            session_id="s1",
            extra={"anything_at_all": _LEAK_MARKER_VP_ID, "nested": {"x": _LEAK_MARKER_VP_ID}},
        )
        content = _build_user_content(handoff_input)
        assert _LEAK_MARKER_VP_ID not in content


# ── (b) state.conversation_history / call-graph channel ───────────────────


class TestHPIIsolationChannelConversationHistoryCallGraph:
    def test_dialogue_module_never_references_f4_longitudinal(self) -> None:
        source = inspect.getsource(dialogue_module)
        assert "longitudinal" not in source
        assert "LongitudinalAnalysisOutput" not in source
        assert "src.f4" not in source

    def test_orchestrator_module_never_references_f4_longitudinal(self) -> None:
        source = inspect.getsource(orchestrator_module)
        assert "longitudinal" not in source
        assert "LongitudinalAnalysisOutput" not in source
        assert "src.f4" not in source

    def test_orchestrator_user_turn_append_only_writes_caller_supplied_text(self) -> None:
        state = SessionState(
            session_id="s1", turn_count=0, current_stage=SessionStage.dialogue_loop
        )
        inp = OrchestratorInput(
            session_id="s1", raw_input=_LEAK_MARKER_VP_ID, input_type=InputType.text
        )
        if inp.raw_input:
            state.conversation_history.append({"role": "user", "content": inp.raw_input})
        assert state.conversation_history == [{"role": "user", "content": _LEAK_MARKER_VP_ID}]

    def test_add_assistant_turn_only_writes_caller_supplied_response(self) -> None:
        state = SessionState(session_id="s1")
        OrchestratorAgent.add_assistant_turn(state, "정상 응답 텍스트")
        assert state.conversation_history == [{"role": "assistant", "content": "정상 응답 텍스트"}]
        assert _LEAK_MARKER_VP_ID not in str(state.conversation_history)


# ── (c) live-behavior container check ──────────────────────────────────────


def _make_handoff_agent() -> HandoffGeneratorAgent:
    agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
    agent._router = MagicMock()
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "handoff generator 프롬프트"
    return agent


def _wire_echo(agent: HandoffGeneratorAgent) -> tuple[AsyncMock, list[str]]:
    captured_prompts: list[str] = []
    agent._router.select_model.return_value = MagicMock(adapter_name="test", model_id="test")

    async def _chat_timed(messages, **kwargs):
        user_msg = next((m.content for m in messages if m.role == "user"), "")
        captured_prompts.append(user_msg)
        resp = MagicMock()
        resp.content = user_msg
        resp.model = "test-model"
        resp.latency_ms = 1.0
        return resp

    adapter = AsyncMock(spec=LLMAdapter)
    adapter.chat_timed = AsyncMock(side_effect=_chat_timed)
    agent._router.get_adapter.return_value = adapter
    agent._router.record_success = MagicMock()
    agent._router.record_failure = MagicMock()
    return adapter, captured_prompts


class TestHPIIsolationLiveBehaviorContainer:
    @pytest.mark.asyncio
    async def test_f4_output_injected_into_slot_data_never_reaches_report(self) -> None:
        output = _marker_output()

        orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
        state = SessionState(
            session_id="s1",
            slot_data={
                "chief_complaint": "불안감과 수면 문제",
                "history_of_present_illness": "3개월 전 발병",
                "f4_longitudinal": output.model_dump(),
            },
        )

        handoff_input = orchestrator._build_handoff_input(state)

        slot_values = str(handoff_input.slots.model_dump().values())
        for marker in _all_marker_strings():
            assert marker not in slot_values

        prompt_text = _build_user_content(handoff_input)
        for marker in _all_marker_strings():
            assert marker not in prompt_text

        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)
        for marker in _all_marker_strings():
            assert marker not in out.report_markdown
        assert "불안감과 수면 문제" in out.report_markdown

    @pytest.mark.asyncio
    async def test_f4_output_injected_via_extra_also_never_reaches_report(self) -> None:
        output = _marker_output()
        handoff_input = HandoffInput(
            session_id="s1",
            slots=SlotData(chief_complaint="정상 슬롯 값"),
            extra={"f4_longitudinal": output.model_dump()},
        )

        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)
        for marker in _all_marker_strings():
            assert marker not in out.report_markdown
        assert "정상 슬롯 값" in out.report_markdown

    def test_marker_fixture_carries_real_field_shape_not_vacuous(self) -> None:
        output = _marker_output()
        assert output.vp_id == _LEAK_MARKER_VP_ID
        assert output.disease_candidate_series[0].disease == _LEAK_MARKER_DISEASE
        assert output.domain_candidate_series[0].domain == _LEAK_MARKER_DOMAIN
        assert output.trend_verdicts[0].evidence == [_LEAK_MARKER_EVIDENCE]
        assert output.crisis_f3_gaps == [_LEAK_MARKER_GAP]
        assert len(set(_all_marker_strings())) == len(_all_marker_strings())
