"""F3 pipeline — F2-driven questionnaire administration (production engine).

`docs/ai/f3_quick_dev_plan.md` §1/§3/§4/§5.1, ADR-031, ADR-032. This is a
SECOND, separate administration path from the pre-existing
`OrchestratorAgent.plan_surveys`/`score_and_check_safety` planner
(`src/agents/orchestrator.py:592,638`, live in the 11-state chat flow) —
that code path is untouched by this module (plan §0/§9).

F3 administers exactly the ONE questionnaire F2 already recommended
(`ai_predicted_disease.recommended_questionnaire`) — no planner logic, no
subscale escalation, no safety re-evaluation wiring. ZERO LLM calls in this
module: `answer_fn` (mirroring `f1.py`'s `patient_input_fn` seam, f1.py:889)
is the sole variability point — this module has no knowledge of "llm" vs
"expected" vs a real UI behind that callable. This module imports NOTHING
from `tests/` (grep-enforced, `tests/test_f3_hpi_isolation.py` +
`ADR-032` (4) qa gate).

Architected the same way `f1.py`/`f2.py` are: a standalone module invocable
by the `continuous_test.py` validation harness (or a future patient-UI
route, or a CLI replay of pre-collected answers) — not a route, not wired
into `orchestrator.py`.

Item bank: `src.scoring.item_bank` (v1 as of `PLAN-2026-W29-A` — PHQ-9/
GAD-7/PHQ-4/AUDIT-C populated with sourced official item text + response
anchors, WHO-5 unpopulated). An unpopulated scale is NEVER improvised —
`outcome="item_bank_unpopulated"`, 0 items administered, loud WARNING log.

Scoring: `src.scoring.survey_scorer.score_survey` — REUSED unmodified, no
rescoring/reinterpretation.

`safety_referral` (= `score_result.critical_item_positive`) is a RECORD
field on this module's own artifact. Nothing in THIS module calls
`OrchestratorAgent.score_and_check_safety` or any safety route (plan §5,
out of scope §9) — that deterministic item-9 safety-pathway routing lives
at the F3 artifact/ledger CONSUMER seam instead
(`src.continuous_test._route_phq9_safety_pathway`, `PLAN-2026-W29-A` step 3),
never inside this LLM-0 production module.

`forced_scale` (`run_f3_administration`, `PLAN-2026-W29-A` step 6 /
`ADR-033` decision 6): an optional, default-`None` keyword override of
which scale gets administered, fed only by the harness's
`--force-questionnaire` flag. `None` (the default for every existing
caller) preserves this module's exact prior behavior — F2's own
`recommended_questionnaire` still decides everything. `administration_mode`
on the saved artifact records which mode produced it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src.f1 import OUTPUT_DIR
from src.schemas.survey_result import (
    RecommendationProvenance,
    ScoreResultModel,
    SurveyResultOutput,
)
from src.scoring.item_bank import (
    AUDIT_C_THRESHOLD_CAVEAT,
    GAD7_BAND_CAVEAT,
    ITEM_BANK,
    ItemBankEntry,
    ScaleItem,
)
from src.scoring.survey_scorer import ScaleName, ScoreResult, score_survey

logger = logging.getLogger(__name__)

# answer_fn mirrors f1.py's patient_input_fn seam (f1.py:889) — the ONLY
# variability point. Returns a raw (possibly out-of-range) int; this module
# validates/clamps it (see `_clamp_response`), never trusting it blindly.
AnswerFn = Callable[[ScaleItem], Awaitable[int]]

ADMINISTERED_OUTCOME = "administered"
NO_QUESTIONNAIRE_OUTCOME = "no_questionnaire_indicated"
UNPOPULATED_OUTCOME = "item_bank_unpopulated"

# `SurveyResultOutput.threshold_caveat` source table (CVR-016 condition 3 /
# CVR-017 binding condition 1 / REV-039 correction D): per-scale,
# machine-readable band/threshold caveat, attached whenever that scale is
# actually administered. AUDIT-C and GAD-7 today; a scale absent from this
# table simply carries no caveat (`None`) — same as before this table
# existed. Reprojected verbatim, never recomputed, by
# `continuous_test._build_f3_ledger_subobject`.
_SEVERITY_CAVEATS: dict[ScaleName, str] = {
    "AUDIT-C": AUDIT_C_THRESHOLD_CAVEAT,
    "GAD-7": GAD7_BAND_CAVEAT,
}


# ── F2 -> F3 trigger flow (plan §3) ─────────────────────────────────────


@dataclass(frozen=True)
class SurveyRecommendation:
    """F2's `ai_predicted_disease` fields this module reads, read-only,
    never mutated (plan §3). Passthrough of already-schema-validated F2
    output — not new judgment.
    """

    recommended_questionnaire: ScaleName | None
    recommendation_caveat: str | None
    top_candidate_disease: str | None
    top_candidate_similarity_score: float | None


def _load_domain_inference_artifact(path: Path) -> dict[str, Any]:
    """Read an F2 `<vp_id>_<ts>_domain_inference.json` artifact — read-only,
    never mutated (plan §3). Raises `FileNotFoundError` loudly if missing
    (no silent empty run, matching f2.py's own `_load_input` discipline).
    """
    if not path.exists():
        raise FileNotFoundError(f"F2 domain-inference artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_recommendation_from_artifact(artifact: dict[str, Any]) -> SurveyRecommendation:
    """Pure, defensive extraction — tolerates a pre-Track-B artifact missing
    `ai_predicted_disease` entirely (degrades to "no recommendation", never
    crashes) so this module never depends on an undocumented artifact shape
    beyond what it actually reads.
    """
    ai_disease = artifact.get("ai_predicted_disease") or {}
    candidates = ai_disease.get("candidates") or []
    top = candidates[0] if candidates else None
    return SurveyRecommendation(
        recommended_questionnaire=ai_disease.get("recommended_questionnaire"),
        recommendation_caveat=ai_disease.get("recommendation_caveat"),
        top_candidate_disease=(top or {}).get("disease"),
        top_candidate_similarity_score=(top or {}).get("similarity_score"),
    )


def load_recommendation(domain_inference_path: Path) -> SurveyRecommendation:
    """Convenience entry point: load the F2 artifact and resolve its
    recommendation in one call — used by callers (e.g. the
    `continuous_test.py` harness) that need to know the recommended scale
    BEFORE deciding how to construct an `answer_fn`.
    """
    artifact = _load_domain_inference_artifact(domain_inference_path)
    return resolve_recommendation_from_artifact(artifact)


def resolve_outcome(
    recommended_questionnaire: ScaleName | None,
    *,
    item_bank: Mapping[ScaleName, ItemBankEntry] | None = None,
) -> tuple[str, ItemBankEntry | None]:
    """Plan §3's decision table — pure, no I/O beyond the item bank lookup.

    Returns (outcome, entry). `entry` is `None` only for
    `no_questionnaire_indicated` (there was nothing to look up).
    """
    bank = item_bank if item_bank is not None else ITEM_BANK
    if recommended_questionnaire is None:
        # 7 of 9 classifications, or 0 candidates — NEVER force-pick a
        # SUPPORTED_SCALES member.
        return NO_QUESTIONNAIRE_OUTCOME, None

    entry = bank.get(recommended_questionnaire)
    if entry is None:
        raise KeyError(f"No item bank entry for scale {recommended_questionnaire!r}")

    if not entry.populated:
        logger.warning(
            "f3.item_bank_unpopulated — scale=%s provenance=%s — "
            "SKIPPED-item-bank-unpopulated, never improvised content",
            recommended_questionnaire,
            entry.provenance,
        )
        return UNPOPULATED_OUTCOME, entry

    return ADMINISTERED_OUTCOME, entry


# ── Administration engine ───────────────────────────────────────────────


def _clamp_response(raw: Any, item: ScaleItem) -> int:
    """Validate/clamp a raw `answer_fn` return value to the item's own
    `[response_min, response_max]` range — this module never trusts
    `answer_fn` blindly (a future real-UI `answer_fn` is untrusted input).
    Loud WARNING on clamp, never a silent substitution.
    """
    value = int(raw)
    if value < item.response_min or value > item.response_max:
        clamped = max(item.response_min, min(item.response_max, value))
        logger.warning(
            "f3.answer_out_of_range — item=%d raw=%r clamped_to=%d range=[%d,%d]",
            item.index,
            raw,
            clamped,
            item.response_min,
            item.response_max,
        )
        return clamped
    return value


async def administer_survey(
    scale_name: ScaleName,
    answer_fn: AnswerFn,
    *,
    item_bank: Mapping[ScaleName, ItemBankEntry] | None = None,
    patient_sex: str = "unknown",
) -> tuple[list[int], ScoreResult]:
    """`docs/ai/f3_quick_dev_plan.md` §1: resolves the item bank entry for
    `scale_name`, iterates its items in order calling
    ``response = await answer_fn(item)`` per item (the ONLY variability
    point), then scores via `score_survey` (REUSE, unmodified).

    Raises `ValueError` if `scale_name`'s entry is unpopulated — callers
    must check `resolve_outcome` first; this function never improvises
    content for a scale with no items.
    """
    bank = item_bank if item_bank is not None else ITEM_BANK
    entry = bank.get(scale_name)
    if entry is None:
        raise KeyError(f"No item bank entry for scale {scale_name!r}")
    if not entry.populated:
        raise ValueError(
            f"administer_survey called for unpopulated scale {scale_name!r} "
            f"(provenance={entry.provenance!r}) — caller must check "
            "resolve_outcome()/entry.populated first; this function never "
            "improvises content"
        )

    responses: list[int] = []
    for item in entry.items:
        raw = await answer_fn(item)
        responses.append(_clamp_response(raw, item))

    score_result = score_survey(scale_name, responses, patient_sex=patient_sex)
    return responses, score_result


# ── Full production flow: load -> resolve -> administer -> save ────────


async def run_f3_administration(
    *,
    domain_inference_path: Path,
    answer_fn: AnswerFn,
    patient_sex: str = "unknown",
    answer_mode: str | None = None,
    output_dir: Path | None = None,
    vp_id: str | None = None,
    session_id: str | None = None,
    forced_scale: ScaleName | None = None,
) -> dict[str, Any]:
    """End-to-end F3 flow for one session: load the F2 artifact, resolve the
    outcome, administer (only for `outcome="administered"`), score, build +
    save the artifact (+ scale_scores projection when administered).

    `answer_fn` is never called for a non-`administered` outcome (no items
    to answer) — callers may safely pass a stub that raises if invoked, to
    prove this invariant (see `tests/test_f3.py`).

    `forced_scale` (`PLAN-2026-W29-A` step 6 / `ADR-033` decision 6):
    optional, keyword-only override of which scale is resolved and
    administered in place of F2's own `recommended_questionnaire` — set
    only by the harness's `--force-questionnaire` flag. `None` (the default for this
    caller before this mission, and every caller that never passes it)
    preserves the exact prior behavior.

    Returns ``{"outcome": str, "output": SurveyResultOutput, "paths": {...}}``.
    """
    artifact = _load_domain_inference_artifact(domain_inference_path)
    recommendation = resolve_recommendation_from_artifact(artifact)
    administration_mode: Literal["natural", "forced"] = (
        "forced" if forced_scale is not None else "natural"
    )
    effective_scale: ScaleName | None = (
        forced_scale if forced_scale is not None else recommendation.recommended_questionnaire
    )
    outcome, entry = resolve_outcome(effective_scale)

    responses: list[int] = []
    score_result: ScoreResult | None = None
    item_bank_version: str | None = entry.version if entry is not None else None
    item_bank_provenance: str | None = entry.provenance if entry is not None else None

    if outcome == ADMINISTERED_OUTCOME:
        responses, score_result = await administer_survey(
            effective_scale,  # type: ignore[arg-type]
            answer_fn,
            patient_sex=patient_sex,
        )

    resolved_vp_id = vp_id or artifact.get("persona_id") or artifact.get("session_id")
    if not resolved_vp_id:
        raise ValueError(
            "Could not resolve vp_id — F2 artifact has neither persona_id nor "
            "session_id, and no explicit vp_id was supplied"
        )
    resolved_session_id = session_id or artifact.get("session_id") or resolved_vp_id

    score_result_model = (
        ScoreResultModel(**asdict(score_result)) if score_result is not None else None
    )
    safety_referral = (
        bool(score_result.critical_item_positive) if score_result is not None else False
    )

    # CVR-016 condition 3 / CVR-017 binding condition 1 / REV-039 correction
    # D: machine-readable, non-value-changing caveat attached whenever a
    # scale in `_SEVERITY_CAVEATS` is actually administered (AUDIT-C:
    # threshold not reconciled with Korean-population evidence; GAD-7: band-
    # sourcing citation retracted this mission). `None` for every other
    # scale, same as before this table existed.
    threshold_caveat: str | None = None
    if outcome == ADMINISTERED_OUTCOME and effective_scale is not None:
        threshold_caveat = _SEVERITY_CAVEATS.get(effective_scale)

    output = SurveyResultOutput(
        vp_id=resolved_vp_id,
        session_id=resolved_session_id,
        timestamp=datetime.now().isoformat(),
        outcome=outcome,  # type: ignore[arg-type]
        scale_name=effective_scale,
        item_bank_version=item_bank_version,
        item_bank_provenance=item_bank_provenance,
        responses=responses,
        score_result=score_result_model,
        safety_referral=safety_referral,
        administration_mode=administration_mode,
        threshold_caveat=threshold_caveat,
        recommendation_provenance=RecommendationProvenance(
            domain_inference_path=str(domain_inference_path),
            top_candidate_disease=recommendation.top_candidate_disease,
            top_candidate_similarity_score=recommendation.top_candidate_similarity_score,
            recommendation_caveat=recommendation.recommendation_caveat,
        ),
        answer_mode=answer_mode,  # type: ignore[arg-type]
    )
    paths = save_f3_result(output, output_dir)
    return {"outcome": outcome, "output": output, "paths": paths}


# ── Report + save (mirrors f2.py's _build_report/save_f2_result pair) ──


def _build_report(output: SurveyResultOutput) -> str:
    lines = [
        f"# F3 Survey Administration Report — {output.vp_id}",
        "",
        f"> session_id: {output.session_id} | timestamp: {output.timestamp}",
        f"> outcome: **{output.outcome}** | administration_mode: **{output.administration_mode}**",
        "",
        "## Recommendation provenance (F2)",
        "",
    ]
    prov = output.recommendation_provenance
    lines.extend(
        [
            f"- domain_inference_path: `{prov.domain_inference_path}`",
            f"- top_candidate_disease: {prov.top_candidate_disease}",
            f"- top_candidate_similarity_score: {prov.top_candidate_similarity_score}",
            f"- recommendation_caveat: {prov.recommendation_caveat}",
            "",
        ]
    )

    if output.outcome == ADMINISTERED_OUTCOME and output.score_result is not None:
        sr = output.score_result
        lines.extend(
            [
                f"## {output.scale_name} administration (item bank {output.item_bank_version}, "
                f"provenance: {output.item_bank_provenance})",
                "",
                f"- responses: {output.responses}",
                f"- total_score: {sr.total_score} / {sr.max_score}",
                f"- severity: {sr.severity}",
                f"- interpretation: {sr.interpretation}",
                f"- recommended_action: {sr.recommended_action}",
                f"- safety_referral (critical_item_positive): {output.safety_referral}",
                f"- subscale_scores: {sr.subscale_scores}",
                f"- answer_mode: {output.answer_mode}",
                f"- threshold_caveat: {output.threshold_caveat}",
                "",
            ]
        )
    elif output.outcome == UNPOPULATED_OUTCOME:
        lines.extend(
            [
                f"## {output.scale_name} — SKIPPED (item bank unpopulated)",
                "",
                f"- item_bank_version: {output.item_bank_version}",
                f"- item_bank_provenance: {output.item_bank_provenance}",
                "- 0 items administered. Never improvised content for an unpopulated scale.",
                "",
            ]
        )

    else:
        lines.extend(
            [
                "## No questionnaire indicated",
                "",
                "- F2's top-ranked candidate had no recommended_questionnaire this run "
                "(0 candidates, or a classification with no construct-valid scale match).",
                "",
            ]
        )

    lines.extend(["## Disclaimer", "", output.disclaimer, ""])
    return "\n".join(lines)


def save_f3_result(output: SurveyResultOutput, output_dir: Path | None = None) -> dict[str, Path]:
    """Same naming convention as `save_f1_result`/`save_f2_result`:
    ``docs/ai/simulation_results/<vp_id>/<vp_id>_<ts>_survey.json`` (full
    artifact) + ``_survey.md`` (report) always; ``_scale_scores.json``
    (plan §5.1, `handoff.ScaleScore`-shaped) ONLY when
    ``outcome == "administered"``.
    """
    base = output_dir or OUTPUT_DIR
    out = base / output.vp_id
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{output.vp_id}_{ts}"

    json_path = out / f"{prefix}_survey.json"
    json_path.write_text(
        json.dumps(output.model_dump(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    report_path = out / f"{prefix}_survey.md"
    report_path.write_text(_build_report(output), encoding="utf-8")

    paths: dict[str, Path] = {"json": json_path, "report": report_path}

    if output.outcome == ADMINISTERED_OUTCOME and output.score_result is not None:
        scale_scores_path = out / f"{prefix}_scale_scores.json"
        scale_scores = [
            {
                "scale_name": output.score_result.scale_name,
                "total_score": output.score_result.total_score,
                "severity": output.score_result.severity,
            }
        ]
        scale_scores_path.write_text(
            json.dumps(scale_scores, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        paths["scale_scores"] = scale_scores_path

    return paths
