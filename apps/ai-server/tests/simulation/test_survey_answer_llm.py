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

from src.scoring.item_bank import ScaleItem, get_item_bank
from tests.simulation.patient_llm import PatientPersona
from tests.simulation.survey_answer_llm import (
    ExpectedAnswerFn,
    SurveyAnswerLLM,
    _parse_first_integer,
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
