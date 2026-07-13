"""EXP-021 factorial cell driver — HARNESS ONLY, never `src/`.

`docs/ai/exp021_factorial_design.md` (brainstorm), `discussion.md` REV-040
(critic pre-registration; per-role conditions at REV-040 (6) developer row —
implemented here). Isolates which of PHQ-9's three v0->v1 bundled changes
(item text, response-anchor presence, instruction/timeframe presence) drives
`SurveyAnswerLLM`'s whole-instrument over-endorsement finding (`REV-039`
§(3), `CVR-017` Recommendation 2), by administering all 2x2x2=8 hybrid
combinations against a single persona (VP-001) via the pre-existing
`f3.administer_survey`/`f3.resolve_outcome` `item_bank` override seam
(`f3.py:150-153,206-211` — REV-040 (1): CONFIRMED pre-existing, not new).

Bypass-mode, by design (REV-040 (4)/Issue 3, disclosed structurally in every
artifact this driver writes, not just here):
  - Calls `src.f3.administer_survey` directly — never
    `f3.run_f3_administration`/`src.continuous_test.run_f3_stage`. No F1/F2
    pipeline calls are made or needed (`SurveyAnswerLLM`'s own context is
    persona-system-prompt-only regardless of caller, per its own module
    docstring).
  - Consequently the deterministic item-9 safety-pathway ROUTING
    (`src.continuous_test._route_phq9_safety_pathway`) is NEVER invoked by
    any cell in this battery — the underlying signal is not lost
    (`score_survey`'s `critical_item_positive`/`critical_items` is computed
    from raw responses regardless of caller, and is captured/reported per
    cell below), but the routing exercise itself is absent. See the
    `safety_pathway_exercised`/`safety_pathway_disclosure` fields in every
    written artifact.
  - Artifacts are NOT `SurveyResultOutput`/`survey.json`-shaped (that shape
    is built only by `run_f3_administration`, which this driver bypasses) —
    see the `artifact_schema_note` field in every written artifact.
  - HPI-isolation is N/A: bypass mode generates no F1/F2 artifacts, so the
    Mechanical Check every prior F3 battery (EXP-019/EXP-020) ran does not
    apply — see the `hpi_isolation_check` field in every written artifact.

Reproducibility note: K-EXAONE sampling uses `temperature=0.7` hardcoded,
unconditional, in `survey_answer_llm.py:_ask` — this driver does not expose
a `--seed` flag because no seed parameter is passed to the completion call
anywhere in this codebase (verified by direct read); adding one would set
Python's own `random` module without affecting the actual source of
stochasticity, which would misrepresent reproducibility rather than provide
it. Administrations are therefore NOT bit-reproducible across replicates by
design — `--replicate-index` disambiguates artifacts, it does not reproduce
them. Item order, model identity, and temperature are held fixed instead
(§3 of the design doc), matching the tracker's own pre-run comparability
check (§2.1).

Cell table (design §2, byte-identical -- F_text in {v0, v1}, F_anchor/
F_instr in {off, on}):

    Cell 1: v0 / off / off   (== EXP-019 Cell 1 historical corner)
    Cell 2: v0 / off / on
    Cell 3: v0 / on  / off   <- REV-040 Issue 1 leak-risk cell
    Cell 4: v0 / on  / on
    Cell 5: v1 / off / off
    Cell 6: v1 / off / on
    Cell 7: v1 / on  / off   <- REV-040 Issue 1 leak-risk cell
    Cell 8: v1 / on  / on    (== EXP-020 Cell A historical corner)

CLI usage (one example per cell type — tracker invokes this per (cell,
replicate) pair; `--out` is required, never defaulted, so this driver never
writes into `experiments/` on its own initiative):

    # Corner cell, v0 bare-label/no-anchor/no-instruction (== EXP-019 Cell 1)
    python -m tests.simulation.factorial_driver --cell 1 --replicate-index 0 \\
        --persona VP-001 --out experiments/EXP-021/runs/cell1_v0_off_off_rep0/

    # Mixed cell, the REV-040 Issue-1 leak-risk shape (anchor-on, instr-off)
    python -m tests.simulation.factorial_driver --cell 3 --replicate-index 0 \\
        --persona VP-001 --out experiments/EXP-021/runs/cell3_v0_on_off_rep0/

    # Corner cell, shipped v1 combination (== EXP-020 Cell A)
    python -m tests.simulation.factorial_driver --cell 8 --replicate-index 1 \\
        --persona VP-001 --out experiments/EXP-021/runs/cell8_v1_on_on_rep1/

Requires `LG_K_EXAONE_API_KEY`/`LG_K_EXAONE_ENDPOINT_ID` in the environment
(or `--api-key`/`--model`) — this driver makes real K-EXAONE calls when run;
it is never invoked by this module's own test suite (which mocks
`SurveyAnswerLLM._ask`/injects a stub `answer_llm_factory`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src import f3
from src.scoring.item_bank import ItemBankEntry, ScaleItem, get_item_bank, get_item_bank_v0
from tests.simulation.patient_llm import PatientPersona, load_persona
from tests.simulation.survey_answer_llm import SurveyAnswerLLM

logger = logging.getLogger(__name__)

# PHQ-9-only convention (design doc §4.1): band_index runs 0(minimal) ..
# 4(severe). This is a REPORTING label lookup on `score_survey`'s own
# `severity` string -- it never recomputes or overrides the bands themselves
# (`survey_scorer.py:37-43`, byte-frozen).
_PHQ9_BAND_INDEX: dict[str, int] = {
    "minimal": 0,
    "mild": 1,
    "moderate": 2,
    "moderately_severe": 3,
    "severe": 4,
}

SAFETY_PATHWAY_DISCLOSURE = (
    "This bypass-mode administration calls src.f3.administer_survey directly, "
    "never f3.run_f3_administration/src.continuous_test.run_f3_stage -- the "
    "deterministic item-9 safety-pathway routing "
    "(src.continuous_test._route_phq9_safety_pathway) is NOT invoked for any "
    "EXP-021 cell (REV-040 Issue 3/(4)). critical_item_positive/critical_items "
    "above ARE still computed correctly by score_survey regardless of caller."
)

ARTIFACT_SCHEMA_NOTE = (
    "This artifact is NOT SurveyResultOutput-shaped / survey.json-shaped -- "
    "bypass mode never calls f3.run_f3_administration, the function that "
    "builds that schema (REV-040 (4)/Resolution 5)."
)

HPI_ISOLATION_NOTE = (
    "N/A -- bypass mode generates no F1/F2 artifacts, so the HPI-isolation "
    "Mechanical Check every prior F3 battery (EXP-019/EXP-020) ran does not "
    "apply here (REV-040 (4)/Resolution 6)."
)

CODE_REF = (
    "apps/ai-server/tests/simulation/factorial_driver.py::run_cell "
    "(tests.simulation.survey_answer_llm.SurveyAnswerLLM, src.f3.administer_survey)"
)
DESIGN_REF = "docs/ai/exp021_factorial_design.md; discussion.md REV-040"


@dataclass(frozen=True)
class CellFactors:
    """One cell's three factor levels (design §2 table, byte-identical)."""

    text_source: Literal["v0", "v1"]
    anchor_on: bool
    instr_on: bool


CELL_FACTORS: dict[int, CellFactors] = {
    1: CellFactors("v0", False, False),
    2: CellFactors("v0", False, True),
    3: CellFactors("v0", True, False),
    4: CellFactors("v0", True, True),
    5: CellFactors("v1", False, False),
    6: CellFactors("v1", False, True),
    7: CellFactors("v1", True, False),
    8: CellFactors("v1", True, True),
}


def cell_label(cell: int) -> str:
    """Descriptive label encoding a cell's three factor levels (§5.2 item 3
    of the design — required so no downstream consumer infers factor levels
    from directory naming alone without also carrying this label)."""
    f = CELL_FACTORS[cell]
    anchor = "on" if f.anchor_on else "off"
    instr = "on" if f.instr_on else "off"
    return f"cell{cell}_{f.text_source}text_anchor{anchor}_instr{instr}"


def build_cell_item_bank_entry(cell: int) -> ItemBankEntry:
    """Hybrid PHQ-9 item bank entry for one cell (design §5.2 item 3).

    `text_ko` is read from `get_item_bank_v0("PHQ-9")` or
    `get_item_bank("PHQ-9")` per F_text; `response_anchors` is `None` or the
    v1 item's own anchor dict per F_anchor. Both are read directly from the
    production accessors, never hand-retyped (§3 of the design; CVR-016
    Finding 3 transcription-fidelity discipline).
    """
    if cell not in CELL_FACTORS:
        raise ValueError(f"cell must be one of {sorted(CELL_FACTORS)}, got {cell}")
    factors = CELL_FACTORS[cell]

    text_entry = (
        get_item_bank("PHQ-9") if factors.text_source == "v1" else get_item_bank_v0("PHQ-9")
    )
    anchor_entry = get_item_bank("PHQ-9")  # anchors only ever exist on the v1 registry

    items: list[ScaleItem] = []
    for idx in range(9):
        text_item = text_entry.items[idx]
        anchor_item = anchor_entry.items[idx]
        if text_item.index != idx + 1 or anchor_item.index != idx + 1:
            raise AssertionError(
                f"item bank index misalignment at position {idx}: "
                f"text_item.index={text_item.index} anchor_item.index={anchor_item.index}"
            )
        items.append(
            ScaleItem(
                index=idx + 1,
                text_ko=text_item.text_ko,
                response_min=0,
                response_max=3,
                response_anchors=anchor_item.response_anchors if factors.anchor_on else None,
                source=(
                    f"EXP-021 cell {cell} ({cell_label(cell)}): text_ko from "
                    f"{'get_item_bank' if factors.text_source == 'v1' else 'get_item_bank_v0'}"
                    "('PHQ-9'); anchors "
                    + (
                        "from get_item_bank('PHQ-9')"
                        if factors.anchor_on
                        else "None (F_anchor=off)"
                    )
                ),
            )
        )

    return ItemBankEntry(
        scale_name="PHQ-9",
        version=f"exp021-{cell_label(cell)}",
        provenance=(
            f"EXP-021 factorial hybrid cell {cell}, per docs/ai/exp021_factorial_design.md "
            "as amended by discussion.md REV-040 -- item text and anchors sourced verbatim "
            "from the production item bank accessors, never hand-retyped"
        ),
        items=tuple(items),
        populated=True,
        # Entry-level instruction_ko is metadata only here -- f3.administer_survey
        # never reads it; the actual F_instr level is enforced at the
        # SurveyAnswerLLM.instruction_ko_override seam (build_cell_answer_llm).
        instruction_ko=(anchor_entry.instruction_ko if factors.instr_on else None),
    )


def build_cell_answer_llm(
    cell: int,
    persona: PatientPersona,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> SurveyAnswerLLM:
    """`SurveyAnswerLLM` for one cell — ALWAYS passes `instruction_ko_override`
    explicitly (REV-040 Resolution 1), never relying on the `_UNSET` default,
    even though `scale_name="PHQ-9"` is also passed (for `self.scale_name`
    bookkeeping only). This is exactly the discipline
    `test_cell3_shaped_instruction_override_prevents_leak`
    (`test_survey_answer_llm.py`) verifies is load-bearing.
    """
    if cell not in CELL_FACTORS:
        raise ValueError(f"cell must be one of {sorted(CELL_FACTORS)}, got {cell}")
    factors = CELL_FACTORS[cell]
    instruction = get_item_bank("PHQ-9").instruction_ko if factors.instr_on else None
    return SurveyAnswerLLM(
        persona,
        api_key=api_key,
        model=model,
        scale_name="PHQ-9",
        instruction_ko_override=instruction,
    )


AnswerLLMFactory = Callable[[int, PatientPersona], SurveyAnswerLLM]


async def run_cell(
    cell: int,
    *,
    replicate_index: int = 0,
    persona_id: str = "VP-001",
    out_dir: Path,
    patient_sex: str = "unknown",
    api_key: str | None = None,
    model: str | None = None,
    answer_llm_factory: AnswerLLMFactory | None = None,
) -> dict[str, Any]:
    """Run one (cell, replicate) administration and write its artifact.

    `answer_llm_factory`, when supplied, replaces `build_cell_answer_llm` —
    the sole test seam for injecting a mocked `SurveyAnswerLLM` (e.g. with
    `_ask` monkeypatched) without touching this function's control flow.
    Bypasses the full F1->F2->F3 chain by design (module docstring; design
    §5.1) via `f3.administer_survey`'s pre-existing `item_bank` override.
    """
    if cell not in CELL_FACTORS:
        raise ValueError(f"cell must be one of {sorted(CELL_FACTORS)}, got {cell}")
    factors = CELL_FACTORS[cell]

    persona = load_persona(persona_id)
    entry = build_cell_item_bank_entry(cell)
    factory = answer_llm_factory or (
        lambda c, p: build_cell_answer_llm(c, p, api_key=api_key, model=model)
    )
    answer_llm = factory(cell, persona)

    responses, score_result = await f3.administer_survey(
        "PHQ-9",
        answer_llm,
        item_bank={"PHQ-9": entry},
        patient_sex=patient_sex,
    )

    artifact: dict[str, Any] = {
        "cell": cell,
        "cell_label": cell_label(cell),
        "factors": {
            "text_source": factors.text_source,
            "anchor": "on" if factors.anchor_on else "off",
            "instruction": "on" if factors.instr_on else "off",
        },
        "replicate_index": replicate_index,
        "persona_id": persona_id,
        "scale_name": "PHQ-9",
        "model": getattr(answer_llm, "_model", model),
        "temperature": 0.7,
        "responses": responses,
        "total_score": score_result.total_score,
        "max_score": score_result.max_score,
        "severity": score_result.severity,
        "band_index": _PHQ9_BAND_INDEX.get(score_result.severity),
        "critical_item_positive": score_result.critical_item_positive,
        "critical_items": score_result.critical_items,
        "clamped_items": list(getattr(answer_llm, "clamped_items", [])),
        "item_bank_version": entry.version,
        "item_bank_provenance": entry.provenance,
        "administration_mode": "exp021-factorial-bypass",
        "safety_pathway_exercised": False,
        "safety_pathway_disclosure": SAFETY_PATHWAY_DISCLOSURE,
        "artifact_schema_note": ARTIFACT_SCHEMA_NOTE,
        "hpi_isolation_check": HPI_ISOLATION_NOTE,
        "code_ref": CODE_REF,
        "design_ref": DESIGN_REF,
        "timestamp": datetime.now().isoformat(),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{cell_label(cell)}_rep{replicate_index}_administration.json"
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    artifact["_artifact_path"] = str(out_path)
    return artifact


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "EXP-021 factorial cell driver -- administers one PHQ-9 cell of "
            "the 2x2x2 item-text x anchor x instruction design directly via "
            "f3.administer_survey's item_bank override (bypass-mode, no F1/F2)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--cell", type=int, required=True, choices=sorted(CELL_FACTORS))
    parser.add_argument("--replicate-index", type=int, default=0)
    parser.add_argument("--persona", type=str, default="VP-001")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for this cell's administration artifact",
    )
    parser.add_argument(
        "--patient-sex", type=str, default="unknown", choices=["male", "female", "unknown"]
    )
    parser.add_argument("--api-key", type=str, default=None, help="Overrides LG_K_EXAONE_API_KEY")
    parser.add_argument(
        "--model", type=str, default=None, help="Overrides LG_K_EXAONE_ENDPOINT_ID"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    artifact = asyncio.run(
        run_cell(
            args.cell,
            replicate_index=args.replicate_index,
            persona_id=args.persona,
            out_dir=args.out,
            patient_sex=args.patient_sex,
            api_key=args.api_key,
            model=args.model,
        )
    )
    print(
        json.dumps(
            {
                "cell": artifact["cell"],
                "cell_label": artifact["cell_label"],
                "total_score": artifact["total_score"],
                "severity": artifact["severity"],
                "critical_item_positive": artifact["critical_item_positive"],
                "artifact_path": artifact["_artifact_path"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
