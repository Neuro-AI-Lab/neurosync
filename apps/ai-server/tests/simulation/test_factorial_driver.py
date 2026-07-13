"""`tests.simulation.factorial_driver` — EXP-021 factorial cell driver.

REV-040 (6) developer per-role conditions covered here: hybrid item-bank
transcription fidelity (no hand-retyped text_ko/anchors), the
`instruction_ko_override` leak-prevention discipline applied at the driver
level (Resolution 1), raw item-9/`critical_item_positive` capture
(Resolution 3), and the structural disclosure fields (safety-pathway,
artifact-schema, HPI-isolation). No live LLM calls anywhere in this file —
`SurveyAnswerLLM._ask` is monkeypatched (mirrors `test_survey_answer_llm.py`'s
own offline discipline).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.scoring.item_bank import get_item_bank, get_item_bank_v0
from tests.simulation.factorial_driver import (
    ARTIFACT_SCHEMA_NOTE,
    CELL_FACTORS,
    HPI_ISOLATION_NOTE,
    SAFETY_PATHWAY_DISCLOSURE,
    _build_arg_parser,
    build_cell_answer_llm,
    build_cell_item_bank_entry,
    cell_label,
    main,
    run_cell,
)
from tests.simulation.patient_llm import PatientPersona
from tests.simulation.survey_answer_llm import SurveyAnswerLLM

_PERSONA = PatientPersona(
    persona_id="VP-TEST", name="test", severity="mild", ctrs_expected=5,
    visit_type="first_visit", system_prompt="당신은 테스트 환자입니다.", example_utterances="",
)


class TestCellFactorTable:
    """Byte-identity of the design's §2 cell table (brainstorm's own
    factor-level assignment; not developer's to redesign — REV-040 verified
    it, so the driver must reproduce it exactly)."""

    def test_eight_cells_present(self) -> None:
        assert sorted(CELL_FACTORS) == list(range(1, 9))

    @pytest.mark.parametrize(
        "cell, text_source, anchor_on, instr_on",
        [
            (1, "v0", False, False),
            (2, "v0", False, True),
            (3, "v0", True, False),
            (4, "v0", True, True),
            (5, "v1", False, False),
            (6, "v1", False, True),
            (7, "v1", True, False),
            (8, "v1", True, True),
        ],
    )
    def test_cell_factor_levels(
        self, cell: int, text_source: str, anchor_on: bool, instr_on: bool
    ) -> None:
        f = CELL_FACTORS[cell]
        assert (f.text_source, f.anchor_on, f.instr_on) == (text_source, anchor_on, instr_on)

    def test_cell_label_encodes_all_three_factors(self) -> None:
        assert cell_label(1) == "cell1_v0text_anchoroff_instroff"
        assert cell_label(3) == "cell3_v0text_anchoron_instroff"
        assert cell_label(7) == "cell7_v1text_anchoron_instroff"
        assert cell_label(8) == "cell8_v1text_anchoron_instron"


class TestBuildCellItemBankEntry:
    def test_invalid_cell_raises(self) -> None:
        with pytest.raises(ValueError, match="cell must be one of"):
            build_cell_item_bank_entry(9)

    @pytest.mark.parametrize("cell", range(1, 9))
    def test_nine_items_response_range_and_index_order(self, cell: int) -> None:
        entry = build_cell_item_bank_entry(cell)
        assert entry.populated is True
        assert len(entry.items) == 9
        for i, item in enumerate(entry.items):
            assert item.index == i + 1
            assert (item.response_min, item.response_max) == (0, 3)

    @pytest.mark.parametrize("cell", [1, 2, 3, 4])
    def test_v0_text_cells_match_v0_registry_verbatim(self, cell: int) -> None:
        """Transcription-fidelity check (design §5.3): F_text=v0 cells must
        carry text_ko IDENTICAL to get_item_bank_v0 — never hand-retyped."""
        entry = build_cell_item_bank_entry(cell)
        v0_entry = get_item_bank_v0("PHQ-9")
        for built, source in zip(entry.items, v0_entry.items, strict=True):
            assert built.text_ko == source.text_ko

    @pytest.mark.parametrize("cell", [5, 6, 7, 8])
    def test_v1_text_cells_match_v1_registry_verbatim(self, cell: int) -> None:
        entry = build_cell_item_bank_entry(cell)
        v1_entry = get_item_bank("PHQ-9")
        for built, source in zip(entry.items, v1_entry.items, strict=True):
            assert built.text_ko == source.text_ko

    @pytest.mark.parametrize("cell", [1, 2, 5, 6])
    def test_anchor_off_cells_have_no_anchors(self, cell: int) -> None:
        entry = build_cell_item_bank_entry(cell)
        assert all(item.response_anchors is None for item in entry.items)

    @pytest.mark.parametrize("cell", [3, 4, 7, 8])
    def test_anchor_on_cells_match_v1_registry_anchors_verbatim(self, cell: int) -> None:
        entry = build_cell_item_bank_entry(cell)
        v1_entry = get_item_bank("PHQ-9")
        for built, source in zip(entry.items, v1_entry.items, strict=True):
            assert built.response_anchors == source.response_anchors

    def test_version_and_provenance_encode_the_cell(self) -> None:
        entry = build_cell_item_bank_entry(3)
        assert "cell3" in entry.version
        assert "EXP-021" in entry.provenance


class TestBuildCellAnswerLLM:
    @pytest.mark.parametrize(
        "cell, instr_on",
        [
            (1, False), (2, True), (3, False), (4, True),
            (5, False), (6, True), (7, False), (8, True),
        ],
    )
    def test_instruction_resolution_per_cell(self, cell: int, instr_on: bool) -> None:
        llm = build_cell_answer_llm(cell, _PERSONA, api_key="k", model="m")
        entry = get_item_bank("PHQ-9")
        if instr_on:
            assert llm._instruction_ko == entry.instruction_ko
        else:
            assert llm._instruction_ko is None

    def test_scale_name_always_set_for_bookkeeping(self) -> None:
        llm = build_cell_answer_llm(3, _PERSONA, api_key="k", model="m")
        assert llm.scale_name == "PHQ-9"

    def test_cell3_and_cell7_do_not_leak_instruction_despite_scale_name(self) -> None:
        """The exact REV-040 Issue 1 scenario, exercised at the driver level
        (not just the low-level SurveyAnswerLLM unit test in
        test_survey_answer_llm.py): both leak-risk cells must resolve
        _instruction_ko to None even though scale_name="PHQ-9" is passed."""
        for cell in (3, 7):
            llm = build_cell_answer_llm(cell, _PERSONA, api_key="k", model="m")
            assert llm.scale_name == "PHQ-9"
            assert llm._instruction_ko is None
            item = get_item_bank("PHQ-9").items[0]
            prompt = llm._build_prompt(item)
            assert get_item_bank("PHQ-9").instruction_ko not in prompt
            assert "문항:" in prompt  # F_anchor=on still reached for both cells

    def test_invalid_cell_raises(self) -> None:
        with pytest.raises(ValueError, match="cell must be one of"):
            build_cell_answer_llm(0, _PERSONA, api_key="k", model="m")


class TestAllCellsPromptIndependence:
    """Parametrized coverage across all 8 cells: instruction-line presence
    and anchor-menu presence in the constructed prompt track exactly the
    cell's own factor levels, never each other — the property REV-040 (2)
    required the harness to guarantee structurally."""

    @pytest.mark.parametrize("cell", range(1, 9))
    def test_prompt_matches_declared_factor_levels(self, cell: int) -> None:
        factors = CELL_FACTORS[cell]
        llm = build_cell_answer_llm(cell, _PERSONA, api_key="k", model="m")
        entry = build_cell_item_bank_entry(cell)
        item = entry.items[0]
        prompt = llm._build_prompt(item)

        instruction_text = get_item_bank("PHQ-9").instruction_ko
        assert (instruction_text in prompt) is factors.instr_on
        assert ("문항:" in prompt) is factors.anchor_on
        assert ("응답 척도:" in prompt) is factors.anchor_on
        assert item.text_ko in prompt


class TestRunCell:
    @staticmethod
    def _stub_factory(fixed_answer: str = "2"):
        def factory(cell: int, persona: PatientPersona) -> SurveyAnswerLLM:
            llm = build_cell_answer_llm(cell, persona, api_key="k", model="m")
            llm._ask = AsyncMock(return_value=fixed_answer)
            return llm

        return factory

    @pytest.mark.asyncio
    async def test_run_cell_writes_artifact_with_all_required_fields(self, tmp_path: Path) -> None:
        artifact = await run_cell(
            5,
            replicate_index=2,
            persona_id="VP-001",
            out_dir=tmp_path,
            answer_llm_factory=self._stub_factory("2"),
        )
        assert artifact["cell"] == 5
        assert artifact["replicate_index"] == 2
        assert artifact["persona_id"] == "VP-001"
        assert artifact["scale_name"] == "PHQ-9"
        assert artifact["responses"] == [2] * 9
        assert artifact["total_score"] == 18
        assert artifact["temperature"] == 0.7
        assert artifact["factors"] == {"text_source": "v1", "anchor": "off", "instruction": "off"}
        # Structural disclosure fields (REV-040 (4)/Resolutions 3/5/6) — every
        # artifact carries these, never inferable from directory naming alone.
        assert artifact["safety_pathway_exercised"] is False
        assert artifact["safety_pathway_disclosure"] == SAFETY_PATHWAY_DISCLOSURE
        assert artifact["artifact_schema_note"] == ARTIFACT_SCHEMA_NOTE
        assert artifact["hpi_isolation_check"] == HPI_ISOLATION_NOTE
        assert "critical_item_positive" in artifact
        assert "critical_items" in artifact
        assert "band_index" in artifact

        written = json.loads(Path(artifact["_artifact_path"]).read_text(encoding="utf-8"))
        assert written["cell"] == 5
        assert written["total_score"] == 18

    @pytest.mark.asyncio
    async def test_run_cell_captures_item9_positive_response(self, tmp_path: Path) -> None:
        """Item-9 (suicidal ideation) raw response and
        critical_item_positive must be captured even though the safety-
        pathway ROUTING is not exercised (REV-040 Resolution 3)."""
        artifact = await run_cell(
            8, out_dir=tmp_path, answer_llm_factory=self._stub_factory("1")
        )
        assert artifact["responses"][8] == 1
        assert artifact["critical_item_positive"] is True
        assert len(artifact["critical_items"]) == 1

    @pytest.mark.asyncio
    async def test_run_cell3_leak_risk_cell_artifact_has_no_instruction_leak(
        self, tmp_path: Path
    ) -> None:
        artifact = await run_cell(
            3, out_dir=tmp_path, answer_llm_factory=self._stub_factory("1")
        )
        assert artifact["factors"] == {"text_source": "v0", "anchor": "on", "instruction": "off"}

    @pytest.mark.asyncio
    async def test_run_cell_invalid_cell_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cell must be one of"):
            await run_cell(42, out_dir=tmp_path, answer_llm_factory=self._stub_factory())

    @pytest.mark.asyncio
    async def test_run_cell_clamped_items_reported(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        def factory(cell: int, persona: PatientPersona) -> SurveyAnswerLLM:
            llm = build_cell_answer_llm(cell, persona, api_key="k", model="m")
            llm._ask = AsyncMock(side_effect=["blah", "still blah"] * 9)
            return llm

        with caplog.at_level(logging.WARNING):
            artifact = await run_cell(1, out_dir=tmp_path, answer_llm_factory=factory)
        assert artifact["clamped_items"] == list(range(1, 10))


class TestArgParser:
    def test_requires_cell_and_out(self) -> None:
        parser = _build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_cell_choice_out_of_range_rejected(self) -> None:
        parser = _build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--cell", "9", "--out", "/tmp/x"])

    def test_valid_args_parsed(self, tmp_path: Path) -> None:
        parser = _build_arg_parser()
        args = parser.parse_args(
            ["--cell", "3", "--replicate-index", "1", "--persona", "VP-001", "--out", str(tmp_path)]
        )
        assert args.cell == 3
        assert args.replicate_index == 1
        assert args.out == tmp_path
        assert args.patient_sex == "unknown"


class TestMainCLI:
    def test_main_end_to_end_with_mocked_ask(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        async def _fake_ask(self: SurveyAnswerLLM, user_content: str) -> str:
            return "1"

        monkeypatch.setattr(SurveyAnswerLLM, "_ask", _fake_ask)
        exit_code = main(
            [
                "--cell",
                "7",
                "--replicate-index",
                "0",
                "--persona",
                "VP-001",
                "--out",
                str(tmp_path),
                "--api-key",
                "k",
                "--model",
                "m",
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        printed = json.loads(out)
        assert printed["cell"] == 7
        assert printed["total_score"] == 9
        artifact_files = list(tmp_path.glob("*_administration.json"))
        assert len(artifact_files) == 1
