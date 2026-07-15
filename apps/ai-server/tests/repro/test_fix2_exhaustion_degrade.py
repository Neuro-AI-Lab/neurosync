"""Fix 2 — retry-budget-exhaustion safe-degrade regression tests.

Design: `docs/ai/fix_design_exhaustion_bug037.md` §3. Ratified: `ADR-030`
(Decisions 1/2/3/5), `CVR-013` (Option C pick, 3 binding conditions),
`REV-034` (splice/byte-identical-remainder condition, marker-contamination
requirement). Filed under: `PLAN-2026-W28-U`.

Covers:
  - Pool-phrase semantic-empathy-test compliance (requirement 1(a)).
  - Guard-drift exclusion — `_DEGRADE_MARKER_CLAUSES` (requirement 4,
    REV-034's live finding, both Fix-2 pool phrases AND the pre-existing
    BUG-037 `_OUTPUT_ISOLATION_FALLBACK_RESPONSE`).
  - Deterministic pool rotation (requirement 1(c)).
  - Splice-boundary / byte-identical-remainder proofs for all 3
    empathy-degradable violation types (requirement 2), including the
    real comma-joined single-sentence artifact shape (CVR-013 condition
    3, spot-checked offline against `docs/ai/simulation_results/`).
  - run()-level wiring for near_dup / presence_missing / exact_repeat
    exhaustion, and non-interference with the Fix-3 output-isolation
    exhaustion path.
  - Telemetry threading (`DialogueOutput` -> `F1TurnLog`) and the
    elevated-review checklist surface (ADR-030 Decision 3(1)).
  - ADR-030 Decision 5 test-hardening items: BUG-036 run()-level wiring,
    sub-15-char SI-content collision on the isolation guard.

Mirrors the mock-adapter idiom already established in
`tests/repro/test_bug_030_iter2.py` / `tests/repro/test_bug_037.py`.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import f1 as f1_module
from src.adapters.base import LLMAdapter
from src.agents import dialogue as dialogue_module
from src.agents.dialogue import DialogueAgent
from src.f1 import F1Result, F1TurnLog
from src.schemas.dialogue import DialogueInput, DialogueOutput

# rubric_bug030_acceptance.md §1's own cited characteristic empathic
# markers (semantic test, independent of the production `_EMPATHY_
# MARKERS` list — CVR-011 Finding 5's own instrument-precedence ruling).
_RUBRIC_EMPATHY_MARKERS = (
    "겠", "것 같아요", "감사합니다", "이해됩니다", "이해",
    "공감됩니다", "공감", "힘드셨", "지치셨",
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
    return json.dumps({"assistant_response": text}, ensure_ascii=False)


class TestSplicePointBoundaryRule:
    """`_splice_point` mirrors `_extract_leading_clause`'s own boundary
    rule but returns a raw index into the ORIGINAL (unstripped) text."""

    def test_period_boundary(self) -> None:
        text = "정말 힘드셨겠어요. 잠은 잘 주무세요?"
        end = DialogueAgent._splice_point(text)
        assert end == text.find(".")
        assert text[end:] == ". 잠은 잘 주무세요?"

    def test_exclamation_boundary(self) -> None:
        text = "정말 힘드셨겠어요! 잠은 잘 주무세요?"
        end = DialogueAgent._splice_point(text)
        assert end is not None
        assert text[end] == "!"

    def test_question_first_returns_none(self) -> None:
        assert DialogueAgent._splice_point("혹시 최근에 잠은 잘 주무시나요?") is None

    def test_no_terminal_punctuation_returns_none(self) -> None:
        assert DialogueAgent._splice_point("그냥 아무 말이나 쓴 문장") is None

    def test_comma_joined_single_sentence_real_artifact_shape(self) -> None:
        """`docs/ai/simulation_results/VP-001/
        VP-001_20260711_223422_conversation.json` turn 5 (verbatim,
        spot-checked offline — CVR-013 condition 3): a single sentence
        joined by a comma, terminated only by '?', no '.'/'!' anywhere."""
        text = (
            "지난번에 여쭤보지 못했는데, 과거 정신 건강 관련 진단이나 치료를 "
            "받으신 적이 있으신가요?"
        )
        assert DialogueAgent._splice_point(text) is None

    def test_second_real_artifact_shape(self) -> None:
        """`docs/ai/simulation_results/VP-002/
        VP-002_20260711_220528_conversation.json` turn 3 (verbatim) — a
        second, independent confirmation of the same comma-joined shape."""
        text = (
            "현재 복용 중인 약이 어떤 종류인지, 그리고 처방받은 약 외에 추가로 "
            "드시는 약이 있는지 알려주시겠어요?"
        )
        assert DialogueAgent._splice_point(text) is None


class TestDegradeMarkerClausesConstant:
    """`_DEGRADE_MARKER_CLAUSES` — the closed, enumerable exclusion set
    (REV-034 live finding / ADR-030 Decision 1)."""

    def test_fallback_leading_clause_included_and_nonempty(self) -> None:
        expected = DialogueAgent._extract_leading_clause(
            dialogue_module._OUTPUT_ISOLATION_FALLBACK_RESPONSE,
        )
        assert expected
        assert expected in dialogue_module._DEGRADE_MARKER_CLAUSES

    def test_all_pool_phrases_included(self) -> None:
        for phrase in dialogue_module._EMPATHY_DEGRADE_POOL:
            assert phrase in dialogue_module._DEGRADE_MARKER_CLAUSES

    def test_no_accidental_collision_5_distinct_entries(self) -> None:
        assert len(dialogue_module._DEGRADE_MARKER_CLAUSES) == (
            len(dialogue_module._EMPATHY_DEGRADE_POOL) + 1
        )


class TestPoolPhrasesAreMutuallyDistinctFamilies:
    """CVR-013 condition 3-adjacent hygiene / requirement 1(c): every pool
    phrase (and the fallback's own clause) must be a DIFFERENT phrase
    family under the production rubric near-dup rule — verified by direct
    pairwise computation, not eyeballed."""

    def test_all_pairs_different_family(self) -> None:
        fallback_clause = DialogueAgent._extract_leading_clause(
            dialogue_module._OUTPUT_ISOLATION_FALLBACK_RESPONSE,
        )
        all_clauses = list(dialogue_module._EMPATHY_DEGRADE_POOL) + [fallback_clause]
        for i in range(len(all_clauses)):
            for j in range(i + 1, len(all_clauses)):
                a, b = all_clauses[i], all_clauses[j]
                assert DialogueAgent._same_phrase_family(a, b) is False, (
                    f"{a!r} vs {b!r} unexpectedly same family"
                )


class TestPoolPhrasesSatisfySemanticEmpathyTest:
    """Requirement 1(a): pool phrases MUST satisfy
    `rubric_bug030_acceptance.md` §1/§10.1's semantic empathy test —
    affective acknowledgment (references feeling/situation OR carries a
    characteristic empathic marker), never a question, never a
    slot-content restatement."""

    def test_not_a_question(self) -> None:
        for phrase in dialogue_module._EMPATHY_DEGRADE_POOL:
            assert "?" not in phrase

    def test_carries_a_rubric_cited_empathic_marker(self) -> None:
        for phrase in dialogue_module._EMPATHY_DEGRADE_POOL:
            assert any(m in phrase for m in _RUBRIC_EMPATHY_MARKERS), phrase

    def test_recognized_by_production_marker_check_too(self) -> None:
        """Not required by the rubric (whose own semantic test governs
        the acceptance verdict, independent of the production marker
        list — CVR-011 Finding 5) — but a useful consistency check: every
        pool phrase also reads as is_empathy=True under the current
        production markers, so the guard's own retry-triggering logic and
        the rubric's acceptance verdict never disagree about a
        degrade-shipped clause."""
        for phrase in dialogue_module._EMPATHY_DEGRADE_POOL:
            assert DialogueAgent._is_empathy_clause(phrase) is True, phrase

    def test_not_a_slot_content_restatement(self) -> None:
        banned_fragments = ("진단", "약물", "복용", "가족력", "위험평가", "자살")
        for phrase in dialogue_module._EMPATHY_DEGRADE_POOL:
            assert not any(b in phrase for b in banned_fragments), phrase


class TestSelectDegradePhraseRotation:
    """Requirement 1(c): deterministic, session-scoped rotation — no
    randomness, reproducible."""

    def test_empty_session_picks_first_pool_entry(self) -> None:
        pool = dialogue_module._EMPATHY_DEGRADE_POOL
        assert DialogueAgent._select_degrade_phrase([]) == pool[0]
        assert DialogueAgent._select_degrade_phrase(None) == pool[0]

    def test_skips_already_used_pool_phrase(self) -> None:
        pool = dialogue_module._EMPATHY_DEGRADE_POOL
        history = [{"role": "assistant", "content": f"{pool[0]}. 이전 질문?"}]
        assert DialogueAgent._select_degrade_phrase(history) == pool[1]

    def test_wraps_around_when_pool_exhausted(self) -> None:
        pool = dialogue_module._EMPATHY_DEGRADE_POOL
        history = [
            {"role": "assistant", "content": f"{p}. 질문{i}?"}
            for i, p in enumerate(pool)
        ]
        assert DialogueAgent._select_degrade_phrase(history) == pool[0]

    def test_deterministic_rotation_across_consecutive_degrades(self) -> None:
        """Consecutive degrades within one session must not ship
        identical clauses — simulate 3 successive degrade events
        appending to the same session's history."""
        pool = dialogue_module._EMPATHY_DEGRADE_POOL
        history: list[dict[str, str]] = []
        picked = []
        for i in range(3):
            phrase = DialogueAgent._select_degrade_phrase(history)
            picked.append(phrase)
            history.append({"role": "assistant", "content": f"{phrase}. 질문{i}?"})
        assert picked == list(pool[:3])
        assert len(set(picked)) == 3


class TestExcludeDegradeMarkerClauses:
    def test_filters_out_pool_and_fallback_clauses(self) -> None:
        pool = dialogue_module._EMPATHY_DEGRADE_POOL
        fallback_clause = DialogueAgent._extract_leading_clause(
            dialogue_module._OUTPUT_ISOLATION_FALLBACK_RESPONSE,
        )
        clauses = ["정말 힘드셨겠어요", pool[0], "다른 표현", fallback_clause]
        filtered = DialogueAgent._exclude_degrade_marker_clauses(clauses)
        assert filtered == ["정말 힘드셨겠어요", "다른 표현"]

    def test_no_op_when_nothing_matches(self) -> None:
        clauses = ["정말 힘드셨겠어요", "다른 표현"]
        assert DialogueAgent._exclude_degrade_marker_clauses(clauses) == clauses


class TestIsEmpathyDegradable:
    def test_near_dup_variants_true(self) -> None:
        assert DialogueAgent._is_empathy_degradable("near_dup_back_to_back") is True
        assert DialogueAgent._is_empathy_degradable("near_dup_session_cap") is True

    def test_presence_missing_true(self) -> None:
        assert DialogueAgent._is_empathy_degradable("presence_missing") is True

    def test_exact_repeat_true(self) -> None:
        assert DialogueAgent._is_empathy_degradable("exact_repeat") is True

    def test_output_isolation_variants_false(self) -> None:
        for v in (
            "output_isolation_this_turn", "output_isolation_prior_turn",
            "output_isolation_patient_echo",
        ):
            assert DialogueAgent._is_empathy_degradable(v) is False


class TestDegradeEmpathyClauseSplicing:
    """Requirement 2 — index-precision splice + byte-identical-remainder
    proof per violation type, plus the fail-safe prepend path."""

    def test_near_dup_replaces_leading_clause_byte_identical_remainder(self) -> None:
        original = "많이 힘드셨겠어요. 오늘 컨디션은요?"
        degraded, phrase = DialogueAgent._degrade_empathy_clause(
            original, "near_dup_back_to_back", [],
        )
        assert phrase == dialogue_module._EMPATHY_DEGRADE_POOL[0]
        assert degraded == f"{phrase}. 오늘 컨디션은요?"
        remainder_start = original.find(".")
        assert degraded[len(phrase):] == original[remainder_start:]

    def test_exact_repeat_replaces_leading_clause_byte_identical_remainder(self) -> None:
        original = "정말 힘드셨겠어요. 잠은 잘 주무세요?"
        degraded, phrase = DialogueAgent._degrade_empathy_clause(
            original, "exact_repeat", [],
        )
        remainder_start = original.find(".")
        assert degraded[len(phrase):] == original[remainder_start:]
        assert "잠은 잘 주무세요?" in degraded
        assert degraded != original

    def test_presence_missing_prepends_original_ships_byte_identical(self) -> None:
        original = "혹시 최근에 잠은 잘 주무시나요?"
        degraded, phrase = DialogueAgent._degrade_empathy_clause(
            original, "presence_missing", [],
        )
        assert degraded == f"{phrase}. {original}"
        assert degraded.endswith(original)

    def test_exact_repeat_fails_safe_to_prepend_when_no_splice_point(self) -> None:
        """A bare-question repeat with no leading clause at all (no
        '.'/'!' anywhere) — the replace path has nothing to replace;
        must prepend, never guess a boundary or leave content untouched."""
        original = "잠은 잘 주무세요"  # no terminal punctuation at all
        degraded, phrase = DialogueAgent._degrade_empathy_clause(
            original, "exact_repeat", [],
        )
        assert degraded == f"{phrase}. {original}"
        assert original in degraded
        assert degraded != original  # repetition IS broken

    def test_exact_repeat_comma_joined_single_sentence_shape_fails_safe(self) -> None:
        """Real artifact shape (`VP-001_20260711_223422_conversation.json`
        turn 5, spot-checked offline — CVR-013 condition 3): `_splice_
        point` correctly finds no boundary (the '?' is the earliest
        terminal punctuation), so the fail-safe prepend path fires and
        the ENTIRE original ships byte-identical."""
        original = (
            "지난번에 여쭤보지 못했는데, 과거 정신 건강 관련 진단이나 치료를 "
            "받으신 적이 있으신가요?"
        )
        degraded, phrase = DialogueAgent._degrade_empathy_clause(
            original, "exact_repeat", [],
        )
        assert degraded == f"{phrase}. {original}"
        assert degraded.endswith(original)

    def test_rotation_threaded_through_conversation_history(self) -> None:
        pool = dialogue_module._EMPATHY_DEGRADE_POOL
        history = [{"role": "assistant", "content": f"{pool[0]}. 이전?"}]
        _, phrase = DialogueAgent._degrade_empathy_clause(
            "많이 힘드셨겠어요. 새 질문?", "near_dup_back_to_back", history,
        )
        assert phrase == pool[1]


class TestCF1TwoQuestionShapeNeverDeletesClinicalContent:
    """CVR-014 finding CF1 — reproduced live at
    `docs/ai/simulation_results/VP-003/
    VP-003_20260711_222843_conversation.json` turn 7 (`safety_risk="medium"`).
    The CVR-013-cited fail-safe artifacts (`TestSplicePointBoundaryRule`'s
    `test_comma_joined_single_sentence_real_artifact_shape` /
    `test_second_real_artifact_shape`) are BOTH single-question shapes with
    only `?` as terminal punctuation — they exercise `_splice_point`'s
    `None` branch and were never at risk. This artifact is a DIFFERENT,
    untested shape: a comma-joined psychiatric-history probe terminated by
    its OWN `.` before a SECOND, later `?` — `_splice_point` finds a valid
    index (the `.`), so the pre-fix replace branch fired unconditionally
    and silently deleted the entire first clinical question (a
    past-psychiatric-history probe), splicing a pool phrase in its place.
    Hard constraint: replace is only legitimate when the leading span
    `_splice_point` identifies actually IS empathy content (per
    `_is_empathy_clause`) — this artifact's leading span is a clinical
    question, not empathy, so it must always fail safe to prepend."""

    _CF1_TEXT = (
        "지난번에 여쭤보지 못했는데, 과거에 정신건강의학과 진료나 진단을 받으신 "
        "적이 있는지 궁금합니다. 그리고 혹시 현재 다른 신체질환이나 복용 중인 약이 "
        "있는지 여쭤봐도 될까요?"
    )

    def test_shape_sanity_splice_point_is_not_none(self) -> None:
        """Confirms this artifact exercises the REPLACE branch pre-fix —
        distinguishing it from the CVR-013-cited fail-safe artifacts, which
        return `None` here."""
        assert DialogueAgent._splice_point(self._CF1_TEXT) is not None

    def test_shape_sanity_leading_span_is_not_empathy(self) -> None:
        """The span `_splice_point` would replace is the first CLINICAL
        question, not an empathy clause — confirms this is the exact CF1
        gap, not a variant of the already-covered near-dup/exact-repeat
        replace tests (whose leading spans ARE empathy content)."""
        clause = DialogueAgent._extract_leading_clause(self._CF1_TEXT)
        assert DialogueAgent._is_empathy_clause(clause) is False

    def test_exact_repeat_never_deletes_probe_content(self) -> None:
        degraded, phrase = DialogueAgent._degrade_empathy_clause(
            self._CF1_TEXT, "exact_repeat", [],
        )
        assert self._CF1_TEXT in degraded
        assert degraded == f"{phrase}. {self._CF1_TEXT}"

    def test_near_dup_never_deletes_probe_content(self) -> None:
        """`near_dup_*` cannot actually become the run()-acted-upon
        violation for THIS exact text (near_dup_reason is only computed
        when `is_empathy` is True for the candidate's own leading clause —
        see `run()`'s per-iteration check), so this exercises
        `_degrade_empathy_clause` as a function-level invariant / defense-
        in-depth against a future caller, not a reachable run() path for
        this shape (see `TestCF1ExactRepeatExhaustionAtRunLevel` below for
        the actually-reachable end-to-end path)."""
        degraded, phrase = DialogueAgent._degrade_empathy_clause(
            self._CF1_TEXT, "near_dup_back_to_back", [],
        )
        assert self._CF1_TEXT in degraded
        assert degraded == f"{phrase}. {self._CF1_TEXT}"


class TestCF1ExactRepeatExhaustionAtRunLevel:
    """Same CF1 shape, driven through `agent.run()` end-to-end on
    `exact_repeat` — the only violation type production wiring can
    actually reach this shape via."""

    @pytest.mark.asyncio
    async def test_probe_content_ships_intact_after_exhaustion(self) -> None:
        text = TestCF1TwoQuestionShapeNeverDeletesClinicalContent._CF1_TEXT
        history = [{"role": "assistant", "content": text}]
        agent, adapter = _run_agent([
            _json_response(text), _json_response(text), _json_response(text),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="괜찮아요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        assert adapter.chat_timed.call_count == 3
        assert out.exhaustion_degrade == "exact_repeat"
        assert text in out.assistant_response
        assert out.assistant_response != text  # repetition still broken


class TestNearDupExhaustionDegradesAtRunLevel:
    @pytest.mark.asyncio
    async def test_near_dup_exhaustion_ships_degraded_not_fall_through(self) -> None:
        history = [
            {"role": "assistant", "content": "정말 힘드셨겠어요. 잠은 잘 주무세요?"},
        ]
        agent, adapter = _run_agent([
            _json_response("많이 힘드셨겠어요. 식사는 잘 하시나요?"),
            _json_response("많이 힘드셨겠어요. 잠은 좀 어떠세요?"),
            _json_response("많이 힘드셨겠어요. 오늘 컨디션은요?"),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="여전히 힘들어요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        assert adapter.chat_timed.call_count == 3  # no 4th call
        assert out.retry_count == 2
        assert out.fall_through is False
        assert out.exhaustion_degrade == "near_dup_back_to_back"
        assert out.exhaustion_degrade_phrase is not None
        assert out.assistant_response.endswith(". 오늘 컨디션은요?")
        assert out.assistant_response.startswith(out.exhaustion_degrade_phrase)


class TestPresenceMissingExhaustionDegradesAtRunLevel:
    @pytest.mark.asyncio
    async def test_presence_missing_exhaustion_prepends_pool_phrase(self) -> None:
        agent, adapter = _run_agent([
            _json_response("혹시 최근에 잠은 잘 주무시나요?"),
            _json_response("식사는 잘 하고 계신가요?"),
            _json_response("오늘 컨디션은 어떠세요?"),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="죽고 싶다는 생각이 자꾸 들어요.",
            conversation_history=[],
            filled_slots={}, safety_result=None,
            session_state={"probe_instruction": "안전 탐색 질문"},
        ))
        assert adapter.chat_timed.call_count == 3
        assert out.crisis_adjacent is True
        assert out.fall_through is False
        assert out.exhaustion_degrade == "presence_missing"
        assert out.assistant_response == (
            f"{out.exhaustion_degrade_phrase}. 오늘 컨디션은 어떠세요?"
        )


class TestExactRepeatExhaustionDegradesAtRunLevel:
    @pytest.mark.asyncio
    async def test_exact_repeat_exhaustion_replaces_leading_clause(self) -> None:
        history = [
            {"role": "assistant", "content": "이미 나온 응답입니다. 질문?"},
        ]
        agent, adapter = _run_agent([
            _json_response("이미 나온 응답입니다. 질문?"),
            _json_response("이미 나온 응답입니다. 질문?"),
            _json_response("이미 나온 응답입니다. 질문?"),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="여전히 힘들어요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        assert adapter.chat_timed.call_count == 3
        assert out.fall_through is False
        assert out.exhaustion_degrade == "exact_repeat"
        assert out.assistant_response.endswith(". 질문?")
        assert out.assistant_response != "이미 나온 응답입니다. 질문?"

    @pytest.mark.asyncio
    async def test_exact_repeat_exhaustion_fails_safe_prepend_when_no_clause(self) -> None:
        bare_question = "잠은 잘 주무시나요?"  # no '.'/'!' anywhere
        history = [{"role": "assistant", "content": bare_question}]
        agent, adapter = _run_agent([
            _json_response(bare_question),
            _json_response(bare_question),
            _json_response(bare_question),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="여전히 힘들어요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        assert out.exhaustion_degrade == "exact_repeat"
        assert out.assistant_response.endswith(bare_question)
        assert out.assistant_response != bare_question


class TestOutputIsolationExhaustionUnaffectedByFix2:
    """Priority/mutual-exclusivity regression: Fix 2 must not touch the
    higher-priority Fix-3 output-isolation exhaustion path."""

    @pytest.mark.asyncio
    async def test_isolation_exhaustion_still_ships_neutral_fallback(self) -> None:
        leak = "자살/자해 사고 탐색 질문에 부인 — 환자 발화: 예시 임상 노트 문구 계속"
        agent, adapter = _run_agent([
            _json_response(leak),
            _json_response(leak),
            _json_response(leak),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="괜찮아요.",
            conversation_history=[],
            filled_slots={"risk_assessment": leak},
            safety_result=None, session_state=None,
            slot_updates_this_turn={"risk_assessment": leak},
        ))
        assert out.output_isolation_fallback is True
        assert out.fall_through is False
        assert out.exhaustion_degrade is None
        assert out.exhaustion_degrade_phrase is None
        assert out.assistant_response == dialogue_module._OUTPUT_ISOLATION_FALLBACK_RESPONSE


class TestGuardDriftExclusionAtRunLevel:
    """ADR-030 Decision 1 / REV-034 live finding, requirement 4: a
    system-shipped degrade/fallback clause in history must NOT feed the
    production near-dup guard's `session_clauses` population — the guard
    must not react to text the model never generated."""

    @pytest.mark.asyncio
    async def test_prior_pool_degrade_clause_does_not_trigger_back_to_back(self) -> None:
        pool = dialogue_module._EMPATHY_DEGRADE_POOL
        history = [
            {"role": "assistant", "content": f"{pool[0]}. 이전 질문?"},
        ]
        agent, adapter = _run_agent([
            _json_response(f"{pool[0]}. 새 질문?"),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="계속 힘들어요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        # If the exclusion were missing, this candidate (identical family
        # to the "prior" degrade clause) would trigger back_to_back and
        # retry — a single call proves it did not.
        assert adapter.chat_timed.call_count == 1
        assert out.retry_count == 0
        assert out.retry_reasons == []

    @pytest.mark.asyncio
    async def test_prior_output_isolation_fallback_does_not_trigger_back_to_back(self) -> None:
        """REV-034's ORIGINAL live finding: `_OUTPUT_ISOLATION_FALLBACK_
        RESPONSE`'s own opener must also be excluded — a genuinely
        empathetic later candidate sharing that phrase family must not be
        penalized against system-inserted text."""
        history = [
            {
                "role": "assistant",
                "content": dialogue_module._OUTPUT_ISOLATION_FALLBACK_RESPONSE,
            },
        ]
        # Same family as the fallback's own leading clause ("네, 말씀해
        # 주셔서 감사합니다") — Jaccard 3/4 = 0.75.
        same_family_candidate = "말씀해 주셔서 감사합니다. 새 질문?"
        assert DialogueAgent._same_phrase_family(
            "말씀해 주셔서 감사합니다",
            DialogueAgent._extract_leading_clause(
                dialogue_module._OUTPUT_ISOLATION_FALLBACK_RESPONSE,
            ),
        ) is True  # sanity: the test fixture actually exercises the risk
        agent, adapter = _run_agent([_json_response(same_family_candidate)])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="계속 힘들어요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        assert adapter.chat_timed.call_count == 1
        assert out.retry_count == 0


class TestBug036RunLevelWiring:
    """ADR-030 Decision 5 test-hardening item (REV-034 mutation-resistance
    finding): `test_bug_036.py`'s core ABA/session_cap assertions call
    static helpers directly, not through `agent.run()`'s actual wiring.
    Closes that gap: a compact A-C-A-B history (2 non-adjacent same-family
    uses split by a distinct clause, with a distinct clause immediately
    preceding the candidate so `back_to_back` is isolated OUT) driven
    through `run()` end-to-end — the exact regression class BUG-036 fixed
    (the OLD exact-string dedup would have undercounted the 2nd use,
    keeping `prior_family_count` at 1 and structurally unable to reach the
    >=2 session-cap threshold on this 3rd use)."""

    @pytest.mark.asyncio
    async def test_third_nonadjacent_use_triggers_session_cap_retry(self) -> None:
        history = [
            {"role": "user", "content": "그냥 너무 힘들어요."},
            {"role": "assistant", "content": "정말 힘드셨겠어요. 언제부터요?"},
            {"role": "user", "content": "거의 매일이에요."},
            {"role": "assistant", "content": "전혀 다른 표현입니다. 질문2?"},
            {"role": "user", "content": "그렇군요."},
            {"role": "assistant", "content": "정말 힘드셨겠어요. 잠은 어떠세요?"},
            {"role": "user", "content": "잘 못 자요."},
            {"role": "assistant", "content": "이야기해 주셔서 감사합니다. 다른 것도 여쭤볼게요."},
        ]
        agent, adapter = _run_agent([
            _json_response("정말 힘드셨겠어요. 식사는 어떠세요?"),  # A, 3rd use
            _json_response("전혀 새로운 표현이에요. 오늘 컨디션은요?"),
        ])
        out = await agent.run(DialogueInput(
            session_id="t", user_message="계속 그래요.",
            conversation_history=history,
            filled_slots={}, safety_result=None, session_state=None,
        ))
        assert adapter.chat_timed.call_count == 2  # draft + 1 retry, no 3rd
        assert out.retry_count == 1
        assert out.retry_reasons == ["near_dup_session_cap"]
        assert any(
            d["reason"] == "session_cap" and d["count"] == 2
            for d in out.near_dup_detail
        )


class TestSubMinLengthSIContentCollision:
    """CVR-013 residual (Fix 3 offline-gated review): the isolation
    guard's `_MIN_OUTPUT_ISOLATION_LEN=15` gate was previously untested
    against a genuinely SHORT SI-content slot value. Locks in the CURRENT,
    documented boundary behavior — Fix 2's scope is the exhaustion path
    only; changing the threshold would need its own review — so a future
    threshold change is a deliberate, reviewed decision, not a silent
    regression in either direction."""

    def test_sub_15_char_si_content_not_flagged_documented_gap(self) -> None:
        """A short, genuinely risk-relevant slot value that happens to
        also appear in the model's response is NOT caught by the
        isolation guard today — the min-length gate exists precisely to
        avoid short-string coincidental collisions (e.g. a 2-3 char slot
        value), but as a side effect also does not catch a short SI-
        content leak. Documented, not fixed, here."""
        short_si_value = "자살 생각 있음"
        assert len(short_si_value) < dialogue_module._MIN_OUTPUT_ISOLATION_LEN
        violation = DialogueAgent._output_isolation_violation(
            f"네, {short_si_value} 확인했습니다. 다른 것도 여쭤볼게요.",
            filled_slots={"risk_assessment": short_si_value},
            slot_updates_this_turn={"risk_assessment": short_si_value},
            patient_message="",
        )
        assert violation is None  # documented gap — see class docstring

    def test_at_or_above_min_length_si_content_is_flagged(self) -> None:
        """Contrast case: once the SI-content slot value reaches the
        15-char gate, it IS caught — confirms the boundary sits exactly
        at `_MIN_OUTPUT_ISOLATION_LEN`, not some other off-by-one value."""
        si_value_ge_15 = "자살 생각이 있다고 분명히 말함"
        assert len(si_value_ge_15) >= dialogue_module._MIN_OUTPUT_ISOLATION_LEN
        violation = DialogueAgent._output_isolation_violation(
            f"네, {si_value_ge_15} 확인했습니다.",
            filled_slots={"risk_assessment": si_value_ge_15},
            slot_updates_this_turn={"risk_assessment": si_value_ge_15},
            patient_message="",
        )
        assert violation == "this_turn"


class TestF1TurnLogThreadsExhaustionDegrade:
    """`f1.py`'s `F1TurnLog` carries the new Fix-2 telemetry verbatim from
    a `DialogueOutput`, and safe defaults hold for non-guard-aware
    construction sites."""

    def test_f1_turn_log_accepts_exhaustion_degrade_fields(self) -> None:
        dialogue_out = DialogueOutput(
            model_used="m", prompt_version="v4", latency_ms=1.0,
            assistant_response="응답",
            retry_count=2,
            retry_reasons=["near_dup_back_to_back"] * 3,
            fall_through=False,
            exhaustion_degrade="near_dup_back_to_back",
            exhaustion_degrade_phrase=dialogue_module._EMPATHY_DEGRADE_POOL[0],
        )
        turn_log = F1TurnLog(
            turn=1, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response=dialogue_out.assistant_response,
            slot_updates={}, cumulative_slots={}, slot_coverage=0.0,
            latency_ms=1.0, timestamp="t",
            dialogue_fall_through=dialogue_out.fall_through,
            dialogue_exhaustion_degrade=dialogue_out.exhaustion_degrade,
            dialogue_exhaustion_degrade_phrase=dialogue_out.exhaustion_degrade_phrase,
        )
        assert turn_log.dialogue_exhaustion_degrade == "near_dup_back_to_back"
        assert turn_log.dialogue_exhaustion_degrade_phrase == (
            dialogue_module._EMPATHY_DEGRADE_POOL[0]
        )

    def test_defaults_are_safe(self) -> None:
        dialogue_out = DialogueOutput(
            model_used="m", prompt_version="v4", latency_ms=1.0,
            assistant_response="응답",
        )
        assert dialogue_out.exhaustion_degrade is None
        assert dialogue_out.exhaustion_degrade_phrase is None
        turn_log = F1TurnLog(
            turn=0, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response="응답", slot_updates={}, cumulative_slots={},
            slot_coverage=0.0, latency_ms=1.0, timestamp="t",
        )
        assert turn_log.dialogue_exhaustion_degrade is None
        assert turn_log.dialogue_exhaustion_degrade_phrase is None


class TestChecklistSurfacesExhaustionDegrade:
    """ADR-030 Decision 3(1) / CVR-013 condition 1: the elevated-review
    flag must reach an actually-reviewed surface (the per-run checklist
    markdown), not just a WARNING log line."""

    def test_checklist_reports_degrade_count_and_subrules(self) -> None:
        turn = F1TurnLog(
            turn=1, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response="이렇게 솔직하게 이야기해 주셔서 감사합니다. 질문?",
            slot_updates={}, cumulative_slots={}, slot_coverage=0.0,
            latency_ms=1.0, timestamp="t",
            dialogue_retry_count=2,
            dialogue_retry_reasons=["near_dup_back_to_back"] * 3,
            dialogue_exhaustion_degrade="near_dup_back_to_back",
            dialogue_exhaustion_degrade_phrase=dialogue_module._EMPATHY_DEGRADE_POOL[0],
        )
        result = F1Result(
            session_id="s", persona_id="VP-TEST", persona_name="Test",
            total_turns=1, turns=[turn],
        )
        checklist = f1_module._build_checklist(result)
        assert "Empathy-degrade events (Fix 2 exhaustion) | 1건" in checklist
        assert "near_dup_back_to_back" in checklist
        assert "exhaustion_degrade=near_dup_back_to_back" in checklist
        assert dialogue_module._EMPATHY_DEGRADE_POOL[0] in checklist

    def test_checklist_reports_zero_when_no_degrades(self) -> None:
        turn = F1TurnLog(
            turn=1, patient_message="p", safety_ctrs=5, safety_risk="none",
            safety_crisis=False, safety_categories=[], safety_flagged=[],
            agent_response="응답", slot_updates={}, cumulative_slots={},
            slot_coverage=0.0, latency_ms=1.0, timestamp="t",
        )
        result = F1Result(
            session_id="s", persona_id="VP-TEST", persona_name="Test",
            total_turns=1, turns=[turn],
        )
        checklist = f1_module._build_checklist(result)
        assert "Empathy-degrade events (Fix 2 exhaustion) | 0건" in checklist
        assert "Dialogue guard:" not in checklist
