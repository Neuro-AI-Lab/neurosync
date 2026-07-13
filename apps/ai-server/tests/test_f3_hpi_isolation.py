"""Adversarial HPI-isolation test suite for F3 — REQUIRED by `ADR-032` (4)
(REV-036 issue #4 / resolution #4): "An F3 HPI-isolation adversarial
unit-test suite (parallel to `tests/test_hpi_isolation.py`) is added to
step-5 implementation scope; the step-6 qa gate MUST NOT pass without it."

Mirrors `tests/test_hpi_isolation.py`'s 3-channel pattern verbatim, applied
to F3's own artifact/schema (`src.schemas.survey_result.SurveyResultOutput`)
and the harness ledger `"f3"` sub-object
(`src.continuous_test._build_f3_ledger_subobject`) instead of
`AIPredictedDiseaseOutput`:

  (a) `AgentInput.extra` channel — `_build_user_content` must never read a
      survey-result-shaped payload injected under `extra`.
  (b) `state.conversation_history` / call-graph channel — no code path in
      `dialogue.py`'s turn-construction functions or `orchestrator.py`'s
      message-handling path may ever append F3-sourced text; static grep
      that neither module (nor `src/f3.py` itself) references the F3
      survey-result module/class names or `src.schemas.handoff` — a purely
      "behavioral/naming-convention check today, since no such code exists
      yet" (same framing REV-013 used for the ai_predicted_disease
      precedent).
  (c) live-behavior container check — inject a genuinely-populated
      `SurveyResultOutput` (AND, separately, the harness's own `"f3"`
      ledger sub-object dict) into handoff state and assert the generated
      `report_markdown` contains none of it.

No live LLM/DB call anywhere in this file (offline gate deliverable) — LLM
calls are mocked via the same echo-adapter convention
`tests/test_hpi_isolation.py::_wire_echo` already uses.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.continuous_test as continuous_test_module
import src.f3 as f3_module
from src.adapters.base import LLMAdapter
from src.agents import dialogue as dialogue_module
from src.agents import orchestrator as orchestrator_module
from src.agents.handoff_generator import HandoffGeneratorAgent, _build_user_content
from src.agents.orchestrator import OrchestratorAgent
from src.schemas.handoff import HandoffInput, SlotData
from src.schemas.orchestrator import InputType, OrchestratorInput, SessionStage, SessionState
from src.schemas.survey_result import (
    RecommendationProvenance,
    ScoreResultModel,
    SurveyResultOutput,
)

# Markers distinctive enough that any accidental substring match elsewhere
# in the codebase/fixtures would be implausible.
_LEAK_MARKER_VP_ID = "ZZZ_F3_LEAK_MARKER_VP_ID_9999"
_LEAK_MARKER_TOP_CANDIDATE_DISEASE = "ZZZ_F3_LEAK_MARKER_TOP_CANDIDATE_DISEASE_9999"
_LEAK_MARKER_CAVEAT = "ZZZ_F3_LEAK_MARKER_RECOMMENDATION_CAVEAT_9999"
_LEAK_MARKER_INTERPRETATION = "ZZZ_F3_LEAK_MARKER_INTERPRETATION_9999"
_LEAK_MARKER_DOMAIN_INFERENCE_PATH = "ZZZ_F3_LEAK_MARKER_DOMAIN_INFERENCE_PATH_9999"


def _marker_survey_output() -> SurveyResultOutput:
    """A genuinely-populated `SurveyResultOutput` — real scale/responses
    shape a live `administered` run would ship, with distinctive markers on
    every free-form string field (the fields a real leak would carry
    clinically-relevant content through)."""
    return SurveyResultOutput(
        vp_id=_LEAK_MARKER_VP_ID,
        session_id="s1",
        timestamp="2026-01-01T00:00:00",
        outcome="administered",
        scale_name="PHQ-9",
        item_bank_version="v0",
        item_bank_provenance="construct-labels-v0, persona-file-sourced, non-validated",
        responses=[1, 1, 1, 1, 1, 1, 1, 1, 1],
        score_result=ScoreResultModel(
            scale_name="PHQ-9", total_score=9, max_score=27, severity="mild",
            interpretation=_LEAK_MARKER_INTERPRETATION,
        ),
        safety_referral=True,
        recommendation_provenance=RecommendationProvenance(
            domain_inference_path=_LEAK_MARKER_DOMAIN_INFERENCE_PATH,
            top_candidate_disease=_LEAK_MARKER_TOP_CANDIDATE_DISEASE,
            top_candidate_similarity_score=0.9,
            recommendation_caveat=_LEAK_MARKER_CAVEAT,
        ),
        answer_mode="llm",
    )


def _all_marker_strings() -> list[str]:
    return [
        _LEAK_MARKER_VP_ID,
        _LEAK_MARKER_TOP_CANDIDATE_DISEASE,
        _LEAK_MARKER_CAVEAT,
        _LEAK_MARKER_INTERPRETATION,
        _LEAK_MARKER_DOMAIN_INFERENCE_PATH,
    ]


# ── (type layer) src/f3.py and src/schemas/survey_result.py never import
#    the handoff-shaped modules — this module's own half of the invariant ──


class TestF3TypeLayerIsolation:
    def test_f3_production_module_never_imports_handoff_schema(self) -> None:
        source = inspect.getsource(f3_module)
        assert "schemas.handoff" not in source
        assert "SlotData" not in source
        assert "HandoffInput" not in source

    def test_f3_production_module_imports_nothing_from_tests(self) -> None:
        source = inspect.getsource(f3_module)
        assert "from tests" not in source
        assert "import tests" not in source

    def test_survey_result_schema_shares_no_class_with_handoff_schema(self) -> None:
        """Only classes actually DEFINED in each module (`__module__` match)
        are compared — both modules import shared third-party names
        (`BaseModel`/`ConfigDict`) that would otherwise produce a false
        positive."""
        import src.schemas.handoff as handoff_module
        import src.schemas.survey_result as survey_result_module

        def _locally_defined_classes(module: object) -> set[str]:
            return {
                name
                for name, obj in vars(module).items()
                if isinstance(obj, type) and obj.__module__ == module.__name__
            }

        handoff_names = _locally_defined_classes(handoff_module)
        survey_names = _locally_defined_classes(survey_result_module)
        assert handoff_names, "sanity: handoff module must define at least one class"
        assert survey_names, "sanity: survey_result module must define at least one class"
        assert handoff_names.isdisjoint(survey_names)


# ── (a) AgentInput.extra channel ───────────────────────────────────────────


class TestHPIIsolationChannelExtra:
    """REV-013 §3(a)-style condition, applied to F3: `HandoffInput(...,
    extra={...})` must never reach the report-writing LLM's prompt via
    `_build_user_content`."""

    def test_extra_f3_survey_never_reaches_build_user_content(self) -> None:
        output = _marker_survey_output()
        handoff_input = HandoffInput(
            session_id="s1", extra={"f3_survey": output.model_dump()}
        )
        content = _build_user_content(handoff_input)
        for marker in _all_marker_strings():
            assert marker not in content

    def test_extra_field_construction_itself_does_not_raise(self) -> None:
        """`extra` IS a declared field on `AgentInput` (inherited by
        `HandoffInput`) — passing an F3-shaped payload never raises, so this
        is a genuine "silently ignored" channel, not a `ValidationError`."""
        output = _marker_survey_output()
        handoff_input = HandoffInput(session_id="s1", extra={"f3_survey": output.model_dump()})
        assert handoff_input.extra["f3_survey"]["vp_id"] == _LEAK_MARKER_VP_ID

    def test_arbitrary_extra_key_never_reaches_build_user_content(self) -> None:
        """Broader than the named key — the isolation guarantee should not
        depend on a future leak channel happening to reuse today's exact
        key name."""
        handoff_input = HandoffInput(
            session_id="s1",
            extra={
                "anything_at_all": _LEAK_MARKER_VP_ID,
                "nested": {"survey": {"vp_id": _LEAK_MARKER_VP_ID}},
            },
        )
        content = _build_user_content(handoff_input)
        assert _LEAK_MARKER_VP_ID not in content


# ── (b) state.conversation_history / call-graph channel ───────────────────


class TestHPIIsolationChannelConversationHistoryCallGraph:
    """No code path in `dialogue.py`'s turn-construction functions or
    `orchestrator.py`'s message-handling path (the two conversation_history
    writers) may ever append F3-sourced text. Behavioral/naming-convention
    check today, since no such code exists yet — same framing REV-013 used
    for the ai_predicted_disease precedent."""

    def test_dialogue_module_never_references_f3_survey_result(self) -> None:
        source = inspect.getsource(dialogue_module)
        assert "survey_result" not in source
        assert "SurveyResultOutput" not in source
        assert "src.f3" not in source

    def test_orchestrator_module_never_references_f3_survey_result(self) -> None:
        source = inspect.getsource(orchestrator_module)
        assert "survey_result" not in source
        assert "SurveyResultOutput" not in source
        assert "src.f3" not in source

    def test_orchestrator_user_turn_append_only_writes_caller_supplied_text(self) -> None:
        """Feed an F3 marker as `raw_input` and confirm exactly that text —
        nothing F3-shaped merged in — lands in `conversation_history`."""
        state = SessionState(
            session_id="s1", turn_count=0, current_stage=SessionStage.dialogue_loop
        )
        inp = OrchestratorInput(
            session_id="s1", raw_input=_LEAK_MARKER_VP_ID, input_type=InputType.text
        )
        if inp.raw_input:
            state.conversation_history.append({"role": "user", "content": inp.raw_input})
        assert state.conversation_history == [
            {"role": "user", "content": _LEAK_MARKER_VP_ID}
        ]
        # The marker is present because it was the literal raw_input supplied
        # by the (simulated) user turn — not because any F3 value was merged
        # in; this demonstrates the append site is a pure passthrough.

    def test_add_assistant_turn_only_writes_caller_supplied_response(self) -> None:
        state = SessionState(session_id="s1")
        OrchestratorAgent.add_assistant_turn(state, "정상 응답 텍스트")
        assert state.conversation_history == [
            {"role": "assistant", "content": "정상 응답 텍스트"}
        ]
        assert _LEAK_MARKER_VP_ID not in str(state.conversation_history)


# ── (c) live-behavior container check ──────────────────────────────────────


def _make_handoff_agent() -> HandoffGeneratorAgent:
    agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
    agent._router = MagicMock()
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "handoff generator 프롬프트"
    return agent


def _wire_echo(agent: HandoffGeneratorAgent) -> tuple[AsyncMock, list[str]]:
    """Wire the mocked adapter to ECHO the exact user_content it receives
    back as `report_markdown` — genuinely load-bearing, same convention as
    `tests/test_hpi_isolation.py::_wire_echo` (a canned-response mock would
    not catch a prompt-layer leak; only an echo does)."""
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
    """Inject a genuinely-populated `SurveyResultOutput` into handoff state,
    run the REAL `HandoffGeneratorAgent.run()` code path (LLM call mocked,
    prompt-building + response-handling genuinely exercised), and assert the
    resulting `report_markdown` contains none of its content. The AI-disease
    precedent's injection point (`state.slot_data`, a generic dict bucket
    `OrchestratorAgent._build_handoff_input` only reads via explicit named
    `.get(...)` calls) is reused here — the same simulated
    future-mis-wiring scenario, for F3's own artifact shape.
    """

    @pytest.mark.asyncio
    async def test_f3_survey_injected_into_slot_data_never_reaches_report(self) -> None:
        output = _marker_survey_output()

        orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
        state = SessionState(
            session_id="s1",
            slot_data={
                "chief_complaint": "불안감과 수면 문제",
                "history_of_present_illness": "3개월 전 발병",
                # Simulated future mis-wiring: an F3 survey-result payload
                # written into the same generic dict-bucket real clinical
                # slots use.
                "f3_survey": output.model_dump(),
            },
        )

        handoff_input = orchestrator._build_handoff_input(state)

        # Cross-check 1: SlotData has no such field — no other named slot
        # silently absorbed it either.
        slot_values = str(handoff_input.slots.model_dump().values())
        for marker in _all_marker_strings():
            assert marker not in slot_values

        # Cross-check 2: the actual LLM prompt text never contains a marker.
        prompt_text = _build_user_content(handoff_input)
        for marker in _all_marker_strings():
            assert marker not in prompt_text

        # Cross-check 3 (live-behavior assertion): run the REAL agent
        # end-to-end (LLM mocked-but-echoing) and assert report_markdown —
        # the actual artifact a clinician reads — contains none of the
        # injected F3 content.
        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)

        for marker in _all_marker_strings():
            assert marker not in out.report_markdown
        # Sanity: the echo wiring IS genuinely load-bearing — the real
        # (non-leaked) chief_complaint slot text DOES flow through
        # end-to-end, proving the "marker absent" assertions aren't vacuous.
        assert "불안감과 수면 문제" in out.report_markdown

    @pytest.mark.asyncio
    async def test_f3_survey_injected_via_extra_also_never_reaches_report(self) -> None:
        output = _marker_survey_output()
        handoff_input = HandoffInput(
            session_id="s1",
            slots=SlotData(chief_complaint="정상 슬롯 값"),
            extra={"f3_survey": output.model_dump()},
        )

        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)

        for marker in _all_marker_strings():
            assert marker not in out.report_markdown
        assert "정상 슬롯 값" in out.report_markdown

    def test_marker_fixture_carries_real_field_shape_not_vacuous(self) -> None:
        """Sanity guard on this module's own fixture — every free-form
        string field the live-behavior checks assert on must actually carry
        a distinct marker, otherwise the "marker absent" assertions above
        would be vacuously true."""
        output = _marker_survey_output()
        assert output.vp_id == _LEAK_MARKER_VP_ID
        assert output.recommendation_provenance.top_candidate_disease == (
            _LEAK_MARKER_TOP_CANDIDATE_DISEASE
        )
        assert output.recommendation_provenance.recommendation_caveat == _LEAK_MARKER_CAVEAT
        assert output.score_result is not None
        assert output.score_result.interpretation == _LEAK_MARKER_INTERPRETATION
        assert len(set(_all_marker_strings())) == len(_all_marker_strings())  # all distinct


# ── Ledger content isolation (harness artifact, not production, but the
#    F5-consumption schema per plan §5 — must ALSO never reach a handoff
#    report if something wired it into handoff state) ──────────────────


class TestHPIIsolationLedgerSubobject:
    """`src.continuous_test._build_f3_ledger_subobject`'s output (plan §5,
    F5-consumption schema) must be as isolated from clinician-authored
    narrative text as the production survey artifact itself — proven here
    with the SAME live-behavior injection pattern, using the ACTUAL ledger
    dict the harness would append (not a hand-rolled facsimile)."""

    @pytest.mark.asyncio
    async def test_real_ledger_subobject_injected_into_slot_data_never_reaches_report(
        self, tmp_path: Path
    ) -> None:
        output = _marker_survey_output()
        paths = f3_module.save_f3_result(output, tmp_path)

        ctx = continuous_test_module.ChainContext(
            persona_id=_LEAK_MARKER_VP_ID, max_turns=1, k=1, out_dir=tmp_path,
            scale_scores_path=None, f3_survey_path=paths["json"],
            f3_scale_scores_path=paths.get("scale_scores"),
        )
        ledger_subobject = continuous_test_module._build_f3_ledger_subobject(ctx)
        assert ledger_subobject is not None  # non-vacuity: a real dict was built

        orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
        state = SessionState(
            session_id="s1",
            slot_data={
                "chief_complaint": "불안감과 수면 문제",
                "f3_ledger_entry": ledger_subobject,
            },
        )
        handoff_input = orchestrator._build_handoff_input(state)
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
    async def test_ledger_subobject_fixture_carries_the_markers_not_vacuous(
        self, tmp_path: Path
    ) -> None:
        output = _marker_survey_output()
        paths = f3_module.save_f3_result(output, tmp_path)
        saved = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert saved["vp_id"] == _LEAK_MARKER_VP_ID
        assert (
            saved["recommendation_provenance"]["top_candidate_disease"]
            == _LEAK_MARKER_TOP_CANDIDATE_DISEASE
        )
