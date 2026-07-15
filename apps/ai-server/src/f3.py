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

Exception (CVR-028 Finding 1, clinical-blocking): `resolve_effective_scale`
is a bounded, code-level safety net — when F2 produced NO recommendation
this session AND the session was high-acuity (`crisis_triggered=True` or
`session_ctrs<=3`), it defaults the effective scale to PHQ-9 instead of
leaving the highest-acuity sessions with zero quantified severity data.
This is still not "planner logic": it is a single deterministic fallback
rule, not subscale escalation or re-evaluation, and it never overrides a
real F2 recommendation.

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
    AuditCInternationalThresholdMetadata,
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

    `crisis_triggered`/`session_ctrs` (CVR-028 Finding 1): the SAME
    session-level risk-context fields `DomainInferenceInput` already carried
    into F2, reprojected onto the F2 artifact's own top level (see
    `f2.py::_build_artifact`) and read here read-only, same discipline as
    every other field on this dataclass — never a new judgment computed by
    this module. Default `False`/`None` only for a pre-CVR-028-fix artifact
    that predates these two keys.
    """

    recommended_questionnaire: ScaleName | None
    recommendation_caveat: str | None
    top_candidate_disease: str | None
    top_candidate_similarity_score: float | None
    crisis_triggered: bool = False
    session_ctrs: int | None = None


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
        crisis_triggered=bool(artifact.get("crisis_triggered", False)),
        session_ctrs=artifact.get("session_ctrs"),
    )


def load_recommendation(domain_inference_path: Path) -> SurveyRecommendation:
    """Convenience entry point: load the F2 artifact and resolve its
    recommendation in one call — used by callers (e.g. the
    `continuous_test.py` harness) that need to know the recommended scale
    BEFORE deciding how to construct an `answer_fn`.
    """
    artifact = _load_domain_inference_artifact(domain_inference_path)
    return resolve_recommendation_from_artifact(artifact)


# CVR-028 Finding 1 (blocking): "a safety-net administration path — when
# `crisis_triggered=True` or repeated critical-lexicon hits occur, force
# PHQ-9 item-9 (or the full instrument) independent of F2's domain-
# inference/questionnaire-recommendation success — is clinically required
# before this system is used on real crisis-presenting patients." PHQ-9
# carries the SI item (item 9) this project's other safety machinery
# (`OrchestratorAgent.score_and_check_safety`, `_route_phq9_safety_pathway`)
# already knows how to route on — the same instrument, not a new one.
SAFETY_NET_SCALE: ScaleName = "PHQ-9"

# CVR-029 (major, accepted): threshold widened from <=2 to <=3 — VP-003
# reproduction showed 8/11 sessions with critical-level rule hits while
# `crisis_triggered` stayed False at the CTRS-3 boundary specifically, so a
# `<=2` cutoff still missed most of the same high-acuity cohort CVR-028
# Finding 1 was about. `session_ctrs<=3` now also covers `orchestrator.py`'s
# `_CRISIS_CTRS = {EMERGENCY, HIGH_RISK}` cutoff (CTRSLevel 1-2,
# `src/schemas/common.py`) plus the adjacent CTRS-3 band VP-003 actually
# lived in — a low-CTRS session is acuity-equivalent to a crisis trigger for
# THIS purpose even when the rule-based crisis flag itself didn't fire.
_SAFETY_NET_CTRS_THRESHOLD = 3


def resolve_effective_scale(
    recommendation: SurveyRecommendation,
    *,
    forced_scale: ScaleName | None = None,
) -> tuple[ScaleName | None, bool]:
    """Resolve which scale F3 should actually administer this session.

    Single seam for BOTH F2->F3 consumption sites (`run_f3_administration`
    below and `continuous_test.run_f3_stage`'s harness call) — CVR-028
    Finding 1 requires the safety-net rule to live where the recommendation
    is CONSUMED, production-side, not duplicated per-caller and not living
    only in the harness.

    Precedence (highest first):
    1. `forced_scale` (harness-only `--force-questionnaire` override) — an
       explicit human override always wins, never overridden by the safety
       net.
    2. F2's own `recommended_questionnaire`, when F2 produced one — the
       normal, non-degraded path is never bypassed by the safety net.
    3. The safety net: when F2 yielded NO recommendation (`None` — the
       `llm_only`-fallback-with-no-candidates shape CVR-028 Finding 1
       reproduces) AND the session was high-acuity
       (`crisis_triggered=True` OR `session_ctrs<=3`), default to
       `SAFETY_NET_SCALE` (PHQ-9).
    4. Otherwise `None` (genuinely no questionnaire indicated this session
       — the pre-existing, still-legitimate 7-of-9-classifications outcome
       `resolve_outcome`'s own docstring describes).

    Returns `(effective_scale, safety_net_triggered)` — the second element
    is `True` only when case 3 fired, so callers can record a provenance
    marker (`administration_mode="safety_net"`) distinct from both
    `"natural"` (F2-driven) and `"forced"` (harness-driven).
    """
    if forced_scale is not None:
        return forced_scale, False
    if recommendation.recommended_questionnaire is not None:
        return recommendation.recommended_questionnaire, False
    high_acuity = recommendation.crisis_triggered or (
        recommendation.session_ctrs is not None
        and recommendation.session_ctrs <= _SAFETY_NET_CTRS_THRESHOLD
    )
    if high_acuity:
        logger.warning(
            "f3.safety_net_triggered — F2 yielded no recommended_questionnaire "
            "(crisis_triggered=%s, session_ctrs=%s) — defaulting to %s "
            "(CVR-028 Finding 1)",
            recommendation.crisis_triggered, recommendation.session_ctrs, SAFETY_NET_SCALE,
        )
        return SAFETY_NET_SCALE, True
    return None, False


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
    effective_scale, safety_net_triggered = resolve_effective_scale(
        recommendation, forced_scale=forced_scale
    )
    administration_mode: Literal["natural", "forced", "safety_net"] = (
        "forced"
        if forced_scale is not None
        else "safety_net"
        if safety_net_triggered
        else "natural"
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
    # Korean-primary threshold basis + international-cutoff non-adoption
    # rationale, CVR-018 Q4; GAD-7: band-sourcing citation retracted this
    # mission). `None` for every other scale, same as before this table
    # existed.
    threshold_caveat: str | None = None
    if outcome == ADMINISTERED_OUTCOME and effective_scale is not None:
        threshold_caveat = _SEVERITY_CAVEATS.get(effective_scale)

    # CVR-018 Q1 Recommendation 1 / ADR-034 decision 1: the international
    # AUDIT-C cutoff (Bush et al. 1998) ships as non-action-driving
    # structured metadata alongside the Korean-primary threshold that
    # actually drives severity/recommended_action (survey_scorer.py's own
    # byte-frozen 4/3 int'l values, mirrored here for the boundary check
    # only — never re-imported into the scoring decision itself). `None`
    # for every scale other than AUDIT-C.
    audit_c_international_threshold: AuditCInternationalThresholdMetadata | None = None
    if (
        outcome == ADMINISTERED_OUTCOME
        and effective_scale == "AUDIT-C"
        and score_result is not None
    ):
        intl_threshold = 3 if patient_sex == "female" else 4  # male or unknown
        audit_c_international_threshold = AuditCInternationalThresholdMetadata(
            crossed_international_threshold=score_result.total_score >= intl_threshold,
        )

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
        audit_c_international_threshold=audit_c_international_threshold,
        recommendation_provenance=RecommendationProvenance(
            domain_inference_path=str(domain_inference_path),
            top_candidate_disease=recommendation.top_candidate_disease,
            top_candidate_similarity_score=recommendation.top_candidate_similarity_score,
            recommendation_caveat=recommendation.recommendation_caveat,
        ),
        answer_mode=answer_mode,  # type: ignore[arg-type]
        # F4 quick-dev provenance (§2.7, ADR-036 item 3) — reprojected from
        # the F2 artifact's own top-level fields, never re-derived.
        scenario_pack_id=artifact.get("scenario_pack_id"),
        arc_mode=artifact.get("arc_mode"),
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
                f"- audit_c_international_threshold (non-action-driving metadata): "
                f"{output.audit_c_international_threshold}",
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
