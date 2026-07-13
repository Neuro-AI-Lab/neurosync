"""`tests.simulation.survey_answer_llm` — F3 answer_fn adapters.

`docs/ai/f3_quick_dev_plan.md` §7. No live LLM calls anywhere in this file —
`SurveyAnswerLLM._ask` is monkeypatched (mirrors this module's own retry/
clamp contract without a real K-EXAONE call). `expected_answer_fn` is
exercised against the REAL repo persona files (VP-001/VP-003/VP-012) — zero
LLM either way, so this is safe offline.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from src.scoring.item_bank import ScaleItem, get_item_bank, get_item_bank_v0
from tests.simulation.patient_llm import PatientPersona
from tests.simulation.survey_answer_llm import (
    ExpectedAnswerFn,
    SurveyAnswerLLM,
    _parse_first_integer,
    build_item_prompt,
    expected_answer_fn,
)

_PERSONA = PatientPersona(
    persona_id="VP-TEST", name="test", severity="mild", ctrs_expected=5,
    visit_type="first_visit", system_prompt="당신은 테스트 환자입니다.", example_utterances="",
)


def _phq9_item(index: int = 1) -> ScaleItem:
    return get_item_bank("PHQ-9").items[index - 1]


class TestParseFirstInteger:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("2", 2), ("숫자: 2 입니다", 2), ("답은 -1입니다", -1), ("no digits here", None),
            ("", None), ("점수는 3점이에요", 3),
        ],
    )
    def test_parse(self, text: str, expected: int | None) -> None:
        assert _parse_first_integer(text) == expected


class TestSurveyAnswerLLMConstruction:
    def test_missing_credentials_raise_loudly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LG_K_EXAONE_API_KEY", raising=False)
        monkeypatch.delenv("LG_K_EXAONE_ENDPOINT_ID", raising=False)
        with pytest.raises(ValueError, match="LG_K_EXAONE"):
            SurveyAnswerLLM(_PERSONA)

    def test_explicit_credentials_bypass_env(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        assert llm.clamped_items == []


class TestSurveyAnswerLLMAnswerFlow:
    @pytest.mark.asyncio
    async def test_in_range_first_response_used_no_retry(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        llm._ask = AsyncMock(return_value="숫자: 2 입니다")
        value = await llm.answer(_phq9_item())
        assert value == 2
        assert llm._ask.call_count == 1
        assert llm.clamped_items == []

    @pytest.mark.asyncio
    async def test_out_of_range_then_valid_retry_succeeds(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        llm._ask = AsyncMock(side_effect=["9", "1"])
        value = await llm.answer(_phq9_item())
        assert value == 1
        assert llm._ask.call_count == 2
        assert llm.clamped_items == []

    @pytest.mark.asyncio
    async def test_unparseable_then_valid_retry_succeeds(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        llm._ask = AsyncMock(side_effect=["blah blah", "0"])
        value = await llm.answer(_phq9_item())
        assert value == 0

    @pytest.mark.asyncio
    async def test_both_calls_fail_clamps_to_nearest_bound_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        llm._ask = AsyncMock(side_effect=["blah", "still blah"])
        with caplog.at_level(logging.WARNING):
            value = await llm.answer(_phq9_item())
        assert value == 0  # response_min for PHQ-9
        assert llm.clamped_items == [1]
        assert any("survey_answer_llm.clamped" in r.message for r in caplog.records)
        assert llm._ask.call_count == 2  # exactly one re-prompt, never more

    @pytest.mark.asyncio
    async def test_both_calls_out_of_range_high_clamps_to_max(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        llm._ask = AsyncMock(side_effect=["99", "100"])
        value = await llm.answer(_phq9_item())
        assert value == 3  # response_max for PHQ-9
        assert llm.clamped_items == [1]

    @pytest.mark.asyncio
    async def test_call_dunder_delegates_to_answer(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        llm._ask = AsyncMock(return_value="1")
        value = await llm(_phq9_item())
        assert value == 1

    @pytest.mark.asyncio
    async def test_prompt_contains_item_text_and_anchors_v1(self) -> None:
        """Item bank v1: the prompt presents the item's real
        `response_anchors` — no more bare-integer-only ask."""
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        item = _phq9_item()
        prompt = llm._build_prompt(item)
        assert item.text_ko in prompt
        assert item.response_anchors, "sanity: PHQ-9 v1 items must carry anchors"
        for value, label in item.response_anchors.items():
            assert label in prompt
            assert str(value) in prompt
        assert f"{item.response_min}-{item.response_max}" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_instruction_when_scale_name_supplied(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m", scale_name="PHQ-9")
        item = _phq9_item()
        prompt = llm._build_prompt(item)
        entry = get_item_bank("PHQ-9")
        assert entry.instruction_ko in prompt

    @pytest.mark.asyncio
    async def test_prompt_omits_instruction_when_scale_name_not_supplied(self) -> None:
        """Backward-compatible construction (no `scale_name`) still produces
        an anchor-aware prompt, just without the entry-level instruction
        line — never crashes, never fabricates an instruction."""
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        assert llm.scale_name is None
        item = _phq9_item()
        prompt = llm._build_prompt(item)
        entry = get_item_bank("PHQ-9")
        assert entry.instruction_ko not in prompt
        assert item.text_ko in prompt  # anchors/item text still present

    @pytest.mark.asyncio
    async def test_no_anchors_falls_back_to_bare_integer_ask(self) -> None:
        """An item with `response_anchors=None` (hand-built, not from the
        real v1 bank) must fall back to v0's bare-integer ask, never crash
        or fabricate anchor wording."""
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")
        bare_item = ScaleItem(index=1, text_ko="x", response_min=0, response_max=3)
        prompt = llm._build_prompt(bare_item)
        assert bare_item.text_ko in prompt
        assert "0-3" in prompt
        assert "문항:" not in prompt
        assert "응답 척도:" not in prompt

    def test_unrecognized_scale_name_degrades_to_no_instruction(self) -> None:
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m", scale_name="NOT-A-SCALE")
        assert llm._instruction_ko is None


class TestExp021FactorialGoldenPrompts:
    """REV-040 (2)/Issue 1's three REQUIRED golden prompt tests, gating
    `docs/ai/exp021_factorial_design.md` implementation. Item text/anchors
    are always read directly from `get_item_bank`/`get_item_bank_v0` — never
    hand-retyped (§3 of the design; CVR-016 Finding 3 transcription-fidelity
    discipline).
    """

    def test_golden_cell1_v0_bare_reproduction(self) -> None:
        """Cell 1 (v0 text, F_anchor=off, F_instr=off) must byte-reproduce
        the pre-EXP-021 bare-integer ask exactly — no instruction, no anchor
        menu, regardless of the `build_item_prompt` refactor."""
        item = get_item_bank_v0("PHQ-9").items[0]
        assert item.response_anchors is None, "sanity: v0 items carry no anchors"
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m")  # no scale_name, no override
        prompt = llm._build_prompt(item)
        expected = (
            "다음 항목에 대해 지난 2주간 당신의 상태를 가장 잘 나타내는 숫자를 "
            f"{item.response_min}-{item.response_max} 사이에서 하나만 답하세요: {item.text_ko}"
        )
        assert prompt == expected
        assert "\n" not in prompt  # single-line, byte-identical to the pre-refactor branch

    def test_golden_cell8_v1_full_reproduction(self) -> None:
        """Cell 8 (v1 text, F_anchor=on, F_instr=on — the shipped v1
        combination) must byte-reproduce the pre-EXP-021 anchor-menu ask
        exactly, sourced through the original `scale_name`-based resolution
        path (no override involved), matching every existing v1 caller."""
        item = get_item_bank("PHQ-9").items[0]
        entry = get_item_bank("PHQ-9")
        llm = SurveyAnswerLLM(_PERSONA, api_key="k", model="m", scale_name="PHQ-9")
        prompt = llm._build_prompt(item)
        anchor_text = " / ".join(
            f"{value}: {label}" for value, label in sorted(item.response_anchors.items())
        )
        expected = "\n".join(
            [
                entry.instruction_ko,
                f"문항: {item.text_ko}",
                f"응답 척도: {anchor_text}",
                "위 응답 척도 중 당신의 상태를 가장 잘 나타내는 숫자 하나만 답하세요 "
                f"({item.response_min}-{item.response_max}).",
            ]
        )
        assert prompt == expected

    def test_cell3_shaped_instruction_override_prevents_leak(self) -> None:
        """REV-040 Issue 1 (blocking-scoped) / Resolution 1: a Cell-3/Cell-7-
        shaped administration (F_anchor=on, F_instr=off) must NOT silently
        receive the live v1 instruction merely because `scale_name="PHQ-9"`
        was ALSO passed (e.g. for bookkeeping) — explicitly passing
        `instruction_ko_override=None` must take precedence over the
        scale_name-based live-registry fallback. If this precedence is ever
        removed or the `_UNSET` sentinel is reintroduced without honoring an
        explicit override, `llm._instruction_ko` resolves to the live
        instruction text and BOTH assertions below fail — this test fails
        by construction if the leak this review found is reintroduced.
        """
        item = get_item_bank("PHQ-9").items[0]  # v1 text + anchors -> F_anchor=on
        entry = get_item_bank("PHQ-9")
        assert entry.instruction_ko  # sanity: the live registry DOES carry an instruction
        llm = SurveyAnswerLLM(
            _PERSONA,
            api_key="k",
            model="m",
            scale_name="PHQ-9",  # bookkeeping only — deliberately ALSO supplied
            instruction_ko_override=None,  # F_instr=off, explicit per Resolution 1
        )
        assert llm._instruction_ko is None
        prompt = llm._build_prompt(item)
        assert entry.instruction_ko not in prompt
        # F_anchor=on is still reached — this isn't accidentally falling back
        # to the bare-ask branch too.
        assert "문항:" in prompt
        assert "응답 척도:" in prompt

    def test_build_item_prompt_all_four_instruction_anchor_combinations_independent(self) -> None:
        """Direct coverage of `build_item_prompt`'s decoupling for all four
        (F_anchor, F_instr) combinations the factorial design needs — anchor
        presence and instruction presence never imply each other."""
        item = get_item_bank("PHQ-9").items[1]
        instruction = get_item_bank("PHQ-9").instruction_ko
        for anchors_on, instr_on in [(False, False), (False, True), (True, False), (True, True)]:
            prompt = build_item_prompt(
                text_ko=item.text_ko,
                response_min=item.response_min,
                response_max=item.response_max,
                response_anchors=item.response_anchors if anchors_on else None,
                instruction_ko=instruction if instr_on else None,
            )
            assert (instruction in prompt) is instr_on, (anchors_on, instr_on)
            assert ("문항:" in prompt) is anchors_on, (anchors_on, instr_on)
            assert item.text_ko in prompt


class TestExpectedAnswerFn:
    @pytest.mark.asyncio
    async def test_vp001_phq9_matches_documented_total(self) -> None:
        fn = expected_answer_fn("VP-001", "PHQ-9")
        entry = get_item_bank("PHQ-9")
        responses = [await fn(item) for item in entry.items]
        assert sum(responses) == 7  # VP-001 persona doc: PHQ-9 합계 7

    @pytest.mark.asyncio
    async def test_vp003_phq9_matches_documented_total_and_q9_positive(self) -> None:
        fn = expected_answer_fn("VP-003", "PHQ-9")
        entry = get_item_bank("PHQ-9")
        responses = [await fn(item) for item in entry.items]
        assert sum(responses) == 23  # VP-003 persona doc: PHQ-9 합계 23
        assert responses[8] == 2  # Q9 positive (documented "양성")

    @pytest.mark.asyncio
    async def test_vp012_audit_c_matches_documented_total(self) -> None:
        fn = expected_answer_fn("VP-012", "AUDIT-C")
        entry = get_item_bank("AUDIT-C")
        responses = [await fn(item) for item in entry.items]
        assert sum(responses) == 11  # VP-012 persona doc: AUDIT-C 합계 11

    @pytest.mark.asyncio
    async def test_vp012_phq9_matches_documented_total(self) -> None:
        fn = expected_answer_fn("VP-012", "PHQ-9")
        entry = get_item_bank("PHQ-9")
        responses = [await fn(item) for item in entry.items]
        assert sum(responses) == 10  # VP-012 persona doc: PHQ-9 합계 10 (comorbid)

    def test_undocumented_scale_for_persona_raises_loudly_no_guess(self) -> None:
        with pytest.raises(ValueError, match="No '### GAD-7"):
            expected_answer_fn("VP-001", "GAD-7")

    def test_unknown_persona_raises_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            expected_answer_fn("VP-999-DOES-NOT-EXIST", "PHQ-9")

    @pytest.mark.asyncio
    async def test_undocumented_item_index_raises_loudly(self) -> None:
        fn = ExpectedAnswerFn("VP-001", "PHQ-9")
        fake_item = ScaleItem(index=99, text_ko="x", response_min=0, response_max=3)
        with pytest.raises(ValueError, match="No documented expected score"):
            await fn(fake_item)

    @pytest.mark.asyncio
    async def test_out_of_range_documented_value_raises_loudly(self) -> None:
        fn = ExpectedAnswerFn("VP-001", "PHQ-9")
        # Force-narrow the item's own range below the documented value (1)
        # to exercise the range-validation branch deterministically.
        narrow_item = ScaleItem(index=1, text_ko="x", response_min=5, response_max=6)
        with pytest.raises(ValueError, match="out of the item bank's valid range"):
            await fn(narrow_item)


class TestExtractExpectedScoresTable:
    def test_parses_all_nine_phq9_rows(self) -> None:
        from tests.simulation.survey_answer_llm import _extract_expected_scores_table

        md = (
            "### PHQ-9 예상 항목별 점수\n\n"
            "| 항목 | 점수 | 근거 |\n|---|---|---|\n"
            "| 1. 흥미/즐거움 감소 | 1 | x |\n"
            "| 2. 우울감 | 2 | x |\n"
            "| **합계** | **3** | |\n\n---\n"
        )
        scores = _extract_expected_scores_table(md, "PHQ-9")
        assert scores == {1: 1, 2: 2}  # the 합계 (total) row must NOT be parsed as an item

    def test_missing_table_raises(self) -> None:
        from tests.simulation.survey_answer_llm import _extract_expected_scores_table

        with pytest.raises(ValueError, match="No '### GAD-7"):
            _extract_expected_scores_table("no such table here", "GAD-7")
