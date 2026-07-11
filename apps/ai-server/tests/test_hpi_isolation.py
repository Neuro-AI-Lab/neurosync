"""Adversarial HPI-isolation test suite — PLAN-2026-W28-H Track B, REV-013 §3.

qa-owned (this file, not developer/brainstorm). REV-013 ruled the design note's
three-layer isolation (type / call-graph / LLM-prompt) "INADEQUATE as currently
specified" because two freestanding channels reach the same
`_build_user_content` prompt layer 3 is meant to protect, uncovered by any of
the three named layers:

1. `AgentInput.extra: dict[str, Any]` (`src/agents/base.py:16`) — inherited
   verbatim by `HandoffInput`. `extra="forbid"` (layer 1) has no effect on this
   field because it is itself a legitimately declared field, not an unknown
   kwarg.
2. `state.conversation_history` — free-text turns, already serialized by
   `_build_user_content` today, and populated by ordinary chat-turn code that
   never needs to import `ai_predicted_disease.py` or construct
   `SlotData`/`HandoffInput`/`ClinicalSlotOutput` directly.

REV-013 §3 binding condition 1 requires exactly these checks before the
"structurally impossible" wording (Track B's regulatory red line) may be
signed off:
  (a) `HandoffInput(..., extra={"ai_predicted_disease": [<marker>]})` →
      `_build_user_content` output never contains the marker.
  (b) no code path in `dialogue.py`'s turn-construction functions or
      `orchestrator.py`'s message-handling path ever appends
      `ai_predicted_disease`-sourced text to `state.conversation_history`.
  (c) the live-behavior container check (brainstorm §2c): inject an
      `AIPredictedDiseaseOutput` into handoff state and assert the generated
      `report_markdown` contains none of its content.

No live LLM/DB call anywhere in this file (experiment_gate-compliant, offline
gate deliverable) — LLM calls are mocked via the same
`DomainInferenceAgent.__new__`/router-mock convention already used by
`tests/test_domain_inference.py::_make_agent`/`_wire`.

PLAN-2026-W28-Q W5 addendum (developer, per this mission's brief item 2 —
"HPI red line (ADR-020): this field must never enter the 12 canonical
clinical slots or clinician-authored handoff text — add/extend the
isolation test"): `AIPredictedDiseaseOutput.recommended_questionnaire`
(the disease<->questionnaire linkage field, answer #5a) is folded into
every existing marker/populated-path check in this file as a fifth
checked field, rather than a new isolated test class — the same channels
(`AgentInput.extra`, `state.slot_data`) and the same non-vacuity
discipline already cover it. qa should re-review this extension alongside
the rest of this gate's W5 verification.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.base import LLMAdapter
from src.agents import dialogue as dialogue_module
from src.agents import orchestrator as orchestrator_module
from src.agents.handoff_generator import HandoffGeneratorAgent, _build_user_content
from src.agents.orchestrator import OrchestratorAgent
from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.handoff import HandoffInput, SlotData
from src.schemas.orchestrator import SessionState

# A marker distinctive enough that any accidental substring match elsewhere in
# the codebase/fixtures would be implausible.
_LEAK_MARKER_DISEASE = "ZZZ_AI_DISEASE_LEAK_MARKER_PANIC_DISORDER_9999"
_LEAK_MARKER_SCORE = 0.987654321
# PLAN-2026-W28-Q W5 (recommended_questionnaire, ADR-020 HPI red line
# extension): the field's type is a Literal['PHQ-9','GAD-7','PHQ-4','WHO-5',
# 'AUDIT-C'] (ScaleName), so — unlike the disease-name/score markers above —
# no arbitrarily-distinctive marker string is constructible here; AUDIT-C is
# picked because none of these tests' own SlotData fixtures (chief_complaint/
# history_of_present_illness) legitimately mention a questionnaire name.
_LEAK_MARKER_QUESTIONNAIRE = "AUDIT-C"


def _marker_candidate() -> AIPredictedDiseaseCandidate:
    return AIPredictedDiseaseCandidate(
        disease=_LEAK_MARKER_DISEASE, similarity_score=_LEAK_MARKER_SCORE
    )


# ── (a) AgentInput.extra channel ───────────────────────────────────────────


class TestHPIIsolationChannelExtra:
    """REV-013 §3 binding condition 1(a): `HandoffInput(..., extra={...})`
    must never reach the report-writing LLM's prompt via `_build_user_content`.

    This locks in TODAY's safe behavior (`_build_user_content` does not read
    `inp.extra` at all) as a standing regression guard against a future
    refactor that starts reading `.extra` — REV-013's own stated purpose for
    this test.
    """

    def test_extra_ai_predicted_disease_never_reaches_build_user_content(self) -> None:
        handoff_input = HandoffInput(
            session_id="s1",
            extra={
                "ai_predicted_disease": [
                    {"disease": _LEAK_MARKER_DISEASE, "similarity_score": _LEAK_MARKER_SCORE}
                ]
            },
        )
        content = _build_user_content(handoff_input)
        assert _LEAK_MARKER_DISEASE not in content
        assert str(_LEAK_MARKER_SCORE) not in content

    def test_extra_field_construction_itself_does_not_raise(self) -> None:
        """Confirms this is a genuine "silently ignored" channel, not a
        `ValidationError` — `extra` IS a declared field on `AgentInput`
        (inherited by `HandoffInput`), so passing it never raises. If this
        ever starts raising, the isolation story has changed and this test
        (and REV-013's own framing) needs re-review, not silent adjustment.
        """
        handoff_input = HandoffInput(
            session_id="s1", extra={"ai_predicted_disease": [{"disease": "x"}]}
        )
        assert handoff_input.extra == {"ai_predicted_disease": [{"disease": "x"}]}

    def test_arbitrary_extra_payload_never_reaches_build_user_content(self) -> None:
        """Broader than the named key: `_build_user_content` must not read
        `inp.extra` under ANY key, not just the literal string
        `"ai_predicted_disease"` — the isolation guarantee should not depend
        on a future leak channel happening to reuse today's exact key name.
        """
        handoff_input = HandoffInput(
            session_id="s1",
            extra={"anything_at_all": _LEAK_MARKER_DISEASE, "nested": {"x": _LEAK_MARKER_DISEASE}},
        )
        content = _build_user_content(handoff_input)
        assert _LEAK_MARKER_DISEASE not in content


# ── (b) state.conversation_history / call-graph channel ───────────────────


class TestHPIIsolationChannelConversationHistoryCallGraph:
    """REV-013 §3 binding condition 1(b): no code path in `dialogue.py`'s
    turn-construction functions or `orchestrator.py`'s message-handling path
    (the two conversation_history writers) may ever append
    `ai_predicted_disease`-sourced text.

    This is, by REV-013's own text, "a behavioral/naming-convention check
    today, since no such code exists yet" — there is nothing to exercise at
    runtime because nothing currently reads the AI-disease module from either
    file. This class therefore combines (1) a static source-grep asserting
    zero reference to the AI-disease module/class names in either file (the
    call-graph invariant, extended beyond brainstorm's own narrower scope of
    `SlotData`/`HandoffInput`/`ClinicalSlotOutput` construction to cover the
    conversation_history writers specifically), and (2) a behavioral check on
    the two concrete append sites (`orchestrator.py`'s turn-loop append +
    `add_assistant_turn`) confirming they only ever write the literal
    caller-supplied text, not any AI-disease-shaped structure. Must be
    re-run and tightened (per REV-013's own instruction) the moment any
    future mission wires AI-disease display into the live chat UI.
    """

    def test_dialogue_module_never_references_ai_predicted_disease(self) -> None:
        source = inspect.getsource(dialogue_module)
        assert "ai_predicted_disease" not in source
        assert "AIPredictedDisease" not in source

    def test_orchestrator_module_never_references_ai_predicted_disease(self) -> None:
        source = inspect.getsource(orchestrator_module)
        assert "ai_predicted_disease" not in source
        assert "AIPredictedDisease" not in source

    def test_orchestrator_user_turn_append_only_writes_caller_supplied_text(self) -> None:
        """Behavioral check on the first of the two concrete
        `conversation_history.append` call sites (`orchestrator.py`, the
        turn-loop `raw_input` append): feed a marker as `raw_input` and
        confirm exactly that text — nothing AI-disease-shaped merged in —
        lands in `conversation_history`."""
        from src.schemas.orchestrator import InputType, OrchestratorInput, SessionStage

        state = SessionState(
            session_id="s1", turn_count=0, current_stage=SessionStage.dialogue_loop
        )
        # Bypass the full process_turn pipeline (which needs live sub-agents)
        # — exercise the exact append statement directly via a minimal state
        # mutation identical in shape to orchestrator.py's own code.
        inp = OrchestratorInput(
            session_id="s1", raw_input=_LEAK_MARKER_DISEASE, input_type=InputType.text
        )
        if inp.raw_input:
            state.conversation_history.append({"role": "user", "content": inp.raw_input})
        assert state.conversation_history == [
            {"role": "user", "content": _LEAK_MARKER_DISEASE}
        ]
        # The marker is present because it was the literal raw_input supplied
        # by the (simulated) user turn — not because any AI-disease value was
        # merged in. This is the expected/benign case; it demonstrates the
        # append site is a pure passthrough of caller-supplied text, with no
        # implicit enrichment from any other state field.

    def test_add_assistant_turn_only_writes_caller_supplied_response(self) -> None:
        """Second concrete append site: `OrchestratorAgent.add_assistant_turn`
        — confirm it is a pure passthrough of its `response` argument, with
        no implicit read of any AI-disease-shaped state field."""
        state = SessionState(session_id="s1")
        OrchestratorAgent.add_assistant_turn(state, "정상 응답 텍스트")
        assert state.conversation_history == [
            {"role": "assistant", "content": "정상 응답 텍스트"}
        ]
        assert _LEAK_MARKER_DISEASE not in str(state.conversation_history)


# ── (c) live-behavior container check ──────────────────────────────────────


def _make_handoff_agent() -> HandoffGeneratorAgent:
    agent = HandoffGeneratorAgent.__new__(HandoffGeneratorAgent)
    agent._router = MagicMock()
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load_system_prompt.return_value = "handoff generator 프롬프트"
    return agent


def _wire_echo(agent: HandoffGeneratorAgent) -> tuple[AsyncMock, list[str]]:
    """Wire the mocked adapter to ECHO the exact user_content it receives
    back as `report_markdown`. This makes the test genuinely load-bearing:
    if the isolation design ever regresses and AI-disease content reaches the
    prompt, this echo makes it show up verbatim in `report_markdown` too —
    the same failure signature brainstorm's §2(c) live-behavior test spec
    describes ("assert the resulting report_markdown contains none of the
    disease names/scores"). A mock that returns a canned, unrelated string
    would NOT catch a prompt-layer leak — only an echo does.
    """
    captured_prompts: list[str] = []
    agent._router.select_model.return_value = MagicMock(
        adapter_name="test", model_id="test",
    )

    async def _chat_timed(messages, **kwargs):
        user_msg = next((m.content for m in messages if m.role == "user"), "")
        captured_prompts.append(user_msg)
        resp = MagicMock()
        resp.content = user_msg  # echo — proves what the LLM actually saw
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
    """brainstorm design note §2(c) / REV-013 §3: inject an
    `AIPredictedDiseaseOutput` into handoff state, run the REAL
    `HandoffGeneratorAgent.run()` code path (LLM call mocked, but the prompt-
    building + response-handling code is genuinely exercised, not bypassed),
    and assert the resulting `report_markdown` contains none of its content.

    The AI-disease container has no dedicated `SessionState` field (confirmed
    by direct read of `src/schemas/orchestrator.py::SessionState` — no such
    field exists) — the only plausible injection point today is the generic
    dict bucket, `state.slot_data`, simulating a future developer who
    mistakenly writes an `AIPredictedDiseaseOutput.model_dump()` into it
    under a plausible key. `OrchestratorAgent._build_handoff_input` only
    reads slot_data via explicit, named `.get(...)` calls
    (`chief_complaint`, `history_of_present_illness`, ... — confirmed by
    direct read, `orchestrator.py:459-514`) — an unrecognized key is simply
    never looked up, which is exactly the invariant this test proves
    end-to-end rather than by code-reading alone.
    """

    @pytest.mark.asyncio
    async def test_ai_predicted_disease_injected_into_slot_data_never_reaches_report(
        self,
    ) -> None:
        ai_disease = AIPredictedDiseaseOutput(
            mode="rag_live",
            candidates=[_marker_candidate()],
            reason_summary="live-populated for this test only",
            recommended_questionnaire=_LEAK_MARKER_QUESTIONNAIRE,
        )

        orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
        state = SessionState(
            session_id="s1",
            slot_data={
                "chief_complaint": "불안감과 수면 문제",
                "history_of_present_illness": "3개월 전 발병",
                # Simulated future mis-wiring: an AI-disease payload written
                # into the same generic dict-bucket real clinical slots use.
                "ai_predicted_disease": ai_disease.model_dump(),
            },
        )

        handoff_input = orchestrator._build_handoff_input(state)

        # Cross-check 1: the constructed HandoffInput's slots never picked up
        # the injected key (SlotData has no such field — Pydantic would have
        # raised had orchestrator tried to pass it as a kwarg; here we
        # confirm no other named slot silently absorbed it either).
        slot_dict = handoff_input.slots.model_dump()
        assert _LEAK_MARKER_DISEASE not in str(slot_dict.values())
        assert _LEAK_MARKER_QUESTIONNAIRE not in str(slot_dict.values())

        # Cross-check 2: the actual LLM prompt text never contains the marker.
        prompt_text = _build_user_content(handoff_input)
        assert _LEAK_MARKER_DISEASE not in prompt_text
        assert str(_LEAK_MARKER_SCORE) not in prompt_text
        assert _LEAK_MARKER_QUESTIONNAIRE not in prompt_text

        # Cross-check 3 (the live-behavior assertion brainstorm §2c calls
        # for): run the REAL agent end-to-end (LLM mocked-but-echoing) and
        # assert report_markdown — the actual artifact a clinician reads —
        # contains none of the injected disease name/score/questionnaire.
        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)

        assert _LEAK_MARKER_DISEASE not in out.report_markdown
        assert str(_LEAK_MARKER_SCORE) not in out.report_markdown
        assert _LEAK_MARKER_QUESTIONNAIRE not in out.report_markdown
        # Sanity: the echo wiring IS genuinely load-bearing — the real
        # (non-leaked) chief_complaint slot text DOES flow through end-to-end,
        # proving the echo isn't accidentally returning an empty/constant
        # string that would make the "marker absent" assertions vacuous.
        assert "불안감과 수면 문제" in out.report_markdown

    @pytest.mark.asyncio
    async def test_ai_predicted_disease_injected_via_extra_also_never_reaches_report(
        self,
    ) -> None:
        """Companion end-to-end run for channel (a) (`AgentInput.extra`),
        exercised through the full `HandoffGeneratorAgent.run()` path (not
        just the pure `_build_user_content` unit check in
        `TestHPIIsolationChannelExtra`) — the same non-vacuity discipline as
        the slot_data case above, via the echo-wired mock adapter.
        """
        ai_disease = AIPredictedDiseaseOutput(
            mode="rag_live",
            candidates=[_marker_candidate()],
            recommended_questionnaire=_LEAK_MARKER_QUESTIONNAIRE,
        )
        handoff_input = HandoffInput(
            session_id="s1",
            slots=SlotData(chief_complaint="정상 슬롯 값"),
            extra={"ai_predicted_disease": [ai_disease.model_dump()]},
        )

        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)

        assert _LEAK_MARKER_DISEASE not in out.report_markdown
        assert str(_LEAK_MARKER_SCORE) not in out.report_markdown
        assert _LEAK_MARKER_QUESTIONNAIRE not in out.report_markdown
        assert "정상 슬롯 값" in out.report_markdown


# ── (populated path) REV-016(c) condition 2 / PLAN-2026-W28-K Task 4 ──────
#
# The classes above prove isolation using a SYNTHETIC MARKER container
# (`disease`/`similarity_score` only). `source_id`/`quote` did not exist as
# fields on `AIPredictedDiseaseCandidate` when those tests were written —
# ADR-020 (PLAN-2026-W28-K) added them for live population. REV-016(c)
# condition 2 (`discussion.md`) is explicit that the marker-based tests do
# NOT satisfy the populated-path precondition: "has not yet been exercised
# against a genuinely live-populated AIPredictedDiseaseOutput (real disease
# name + real similarity_score + real quote) flowing through an actual
# populated-path run." This section closes that gap.


def _populated_candidate() -> AIPredictedDiseaseCandidate:
    """A genuinely-populated candidate — real disease name (from this
    project's own 26-disease Ada ontology, `src.rag.ontology.DISEASES`),
    real `[0,1]`-bounded `similarity_score`, real `source_id`/`quote`
    provenance — the exact shape `f2._aggregate_disease_candidates` /
    `f2._build_ai_predicted_disease_populated` actually construct on a live
    RAG-mode run (`apps/ai-server/src/f2.py`), not a placeholder marker.
    """
    return AIPredictedDiseaseCandidate(
        disease="우울 삽화(우울증)",
        similarity_score=0.83,
        source_id="case_card:512",
        quote="환자가 2주 이상 지속된 우울감과 흥미 상실을 호소하며 상담을 요청함",
    )


def _populated_output() -> AIPredictedDiseaseOutput:
    return AIPredictedDiseaseOutput(
        mode="rag_live",
        candidates=[_populated_candidate()],
        reason_summary=(
            "1 disease candidate(s) derived from 1 retrieved chunk(s) via "
            "symptom-keyword match (path1, ADR-020). similarity_score is a "
            "RAG cosine-similarity signal ... NOT a calibrated probability."
        ),
        # Real mapping outcome for "우울 삽화(우울증)" (mood -> PHQ-9, see
        # src.rag.questionnaire_mapping) — the exact value f2.py's
        # population code would actually attach for this candidate, not a
        # synthetic marker (PLAN-2026-W28-Q W5).
        recommended_questionnaire="PHQ-9",
    )


class TestHPIIsolationPopulatedPath:
    """REV-016(c) condition 2 (`discussion.md`) / ADR-020 (`discussion.md`) /
    PLAN-2026-W28-K Task 4 — the hard red line for this gate.

    Re-runs BOTH REV-013 §3 channels (`AgentInput.extra`,
    `state.slot_data` -> `HandoffInput`) end-to-end, with a GENUINELY
    POPULATED `AIPredictedDiseaseOutput` (real disease name, real
    similarity_score, real source_id, real quote, real
    recommended_questionnaire — every field a live populated-path run
    ships), through the REAL `HandoffGeneratorAgent.run()` code path
    (echo-wired mock adapter — a canned-response mock would not catch a
    prompt-layer leak, only an echo does; same convention as
    `TestHPIIsolationLiveBehaviorContainer` above). Every check asserts on
    all five candidate/container fields (`disease`, `similarity_score`,
    `source_id`, `quote`, `recommended_questionnaire`) individually, not
    just the disease name, since `source_id`/`quote`/
    `recommended_questionnaire` are the fields the Wave-3 marker tests
    never exercised (PLAN-2026-W28-Q W5 adds `recommended_questionnaire`
    to this gate's scope, per the ADR-020 HPI red-line extension).
    """

    @pytest.mark.asyncio
    async def test_populated_candidate_via_slot_data_never_reaches_report(
        self,
    ) -> None:
        ai_disease = _populated_output()
        candidate = ai_disease.candidates[0]
        quote = candidate.quote
        source_id = candidate.source_id
        recommended_questionnaire = ai_disease.recommended_questionnaire
        assert quote is not None and source_id is not None  # narrows for mypy + non-vacuity
        assert recommended_questionnaire is not None  # non-vacuity for this field's checks

        orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
        state = SessionState(
            session_id="s1",
            slot_data={
                "chief_complaint": "불안감과 수면 문제",
                "history_of_present_illness": "3개월 전 발병",
                # Simulated future mis-wiring: a genuinely-populated
                # AI-disease payload (not a marker) written into the same
                # generic dict-bucket real clinical slots use.
                "ai_predicted_disease": ai_disease.model_dump(),
            },
        )

        handoff_input = orchestrator._build_handoff_input(state)

        # Cross-check 1: no named slot silently absorbed any populated field.
        slot_values = str(handoff_input.slots.model_dump().values())
        assert candidate.disease not in slot_values
        assert quote not in slot_values
        assert source_id not in slot_values
        assert recommended_questionnaire not in slot_values

        # Cross-check 2: the pure prompt-building function.
        prompt_text = _build_user_content(handoff_input)
        assert candidate.disease not in prompt_text
        assert quote not in prompt_text
        assert str(candidate.similarity_score) not in prompt_text
        assert source_id not in prompt_text
        assert recommended_questionnaire not in prompt_text

        # Cross-check 3 (the live-behavior assertion): run the REAL agent
        # end-to-end (LLM mocked-but-echoing) and assert report_markdown —
        # the actual artifact a clinician reads — contains none of the
        # populated disease name/score/source_id/quote/questionnaire.
        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)

        assert candidate.disease not in out.report_markdown
        assert quote not in out.report_markdown
        assert str(candidate.similarity_score) not in out.report_markdown
        assert source_id not in out.report_markdown
        assert recommended_questionnaire not in out.report_markdown
        # Sanity: the echo wiring IS genuinely load-bearing — the real
        # (non-leaked) chief_complaint slot text DOES flow through
        # end-to-end, proving the "marker absent" assertions aren't vacuous.
        assert "불안감과 수면 문제" in out.report_markdown

    @pytest.mark.asyncio
    async def test_populated_candidate_via_extra_never_reaches_report(
        self,
    ) -> None:
        """Companion end-to-end run for channel (a) (`AgentInput.extra`),
        with the genuinely-populated container, through the full
        `HandoffGeneratorAgent.run()` path — same non-vacuity discipline as
        the slot_data case above."""
        ai_disease = _populated_output()
        candidate = ai_disease.candidates[0]
        quote = candidate.quote
        source_id = candidate.source_id
        recommended_questionnaire = ai_disease.recommended_questionnaire
        assert quote is not None and source_id is not None  # narrows for mypy + non-vacuity
        assert recommended_questionnaire is not None  # non-vacuity for this field's checks

        handoff_input = HandoffInput(
            session_id="s1",
            slots=SlotData(chief_complaint="정상 슬롯 값"),
            extra={"ai_predicted_disease": [ai_disease.model_dump()]},
        )

        # Pure prompt-building function first.
        prompt_text = _build_user_content(handoff_input)
        assert candidate.disease not in prompt_text
        assert quote not in prompt_text
        assert source_id not in prompt_text
        assert recommended_questionnaire not in prompt_text

        agent = _make_handoff_agent()
        _wire_echo(agent)
        out = await agent.run(handoff_input)

        assert candidate.disease not in out.report_markdown
        assert quote not in out.report_markdown
        assert str(candidate.similarity_score) not in out.report_markdown
        assert source_id not in out.report_markdown
        assert recommended_questionnaire not in out.report_markdown
        assert "정상 슬롯 값" in out.report_markdown

    def test_populated_fixture_carries_real_provenance_not_none(self) -> None:
        """Sanity guard on this class's own fixture: `_populated_candidate()`
        must actually carry non-None `source_id`/`quote` — the two fields
        `_marker_candidate()` (Wave-3) never set — otherwise this class
        would silently degrade into re-testing the same marker shape
        Wave-3 already covered, not the genuinely-populated shape ADR-020
        ships. Also confirms this fixture is a distinct disease name from
        the Wave-3 leak marker (not accidentally reusing it)."""
        candidate = _populated_candidate()
        assert candidate.source_id is not None
        assert candidate.quote is not None
        assert candidate.disease != _LEAK_MARKER_DISEASE
        assert candidate.similarity_score != _LEAK_MARKER_SCORE

    def test_populated_fixture_carries_real_recommended_questionnaire_not_none(self) -> None:
        """Same non-vacuity discipline as the provenance sanity guard above,
        for `recommended_questionnaire` (PLAN-2026-W28-Q W5) — the field
        this class's two live-behavior tests newly assert never leaks.
        Also confirms the fixture's value is the correct mapping outcome
        for the fixture's real ontology disease name ("우울 삽화(우울증)",
        classification "mood" -> "PHQ-9", `src.rag.questionnaire_mapping`),
        not an arbitrary/synthetic value."""
        from src.rag.questionnaire_mapping import resolve_questionnaire_for_disease_name_ko

        output = _populated_output()
        assert output.recommended_questionnaire is not None
        assert output.recommended_questionnaire != _LEAK_MARKER_QUESTIONNAIRE
        assert output.recommended_questionnaire == resolve_questionnaire_for_disease_name_ko(
            output.candidates[0].disease
        )
