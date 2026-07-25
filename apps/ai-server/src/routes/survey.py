"""POST /ai/survey/score — Deterministic survey scoring (no LLM).

POST /ai/survey/plan — F3 administration-plan endpoint
(`docs/ai/deployment_integration_plan.md` R3). A THIN wrapper over
`src.f3.resolve_effective_scale`/`resolve_si_supplement_needed` (both pure,
deterministic, zero-LLM, zero I/O) — no planner/scoring logic is duplicated
here; the item-bank content returned is `src.scoring.item_bank.ITEM_BANK`
verbatim. The APP administers the returned items to the real patient.

`/ai/survey/score` (backend-integration closure, 2026-07-20): wraps
`src.scoring.survey_scorer.score_survey` verbatim — the app POSTs the
administered item responses once here and gets back (a) the same scoring
result `/ai/survey/plan` implicitly promises (severity band, PHQ-9 item-9
SI flag + hotline text, `is_diagnostic: false`) and (b) a ready-to-store
`record` sub-object to assign directly onto `contracts.longitudinal.
LongitudinalSessionEntry.f3` for that session's later `POST /ai/temporal/
analyze` call — no client-side re-derivation of scoring/threshold logic.
"""

from __future__ import annotations

from dataclasses import asdict

from contracts.survey_plan import (
    REFUSAL_GUIDANCE_KO,
    SI_POSITIVE_ACTION_KO,
    ItemBankItemPlan,
    SurveyPlanRequest,
    SurveyPlanResponse,
)
from fastapi import APIRouter, HTTPException

from src.f3 import _SEVERITY_CAVEATS as F3_SEVERITY_CAVEATS
from src.f3 import (
    ADMINISTERED_OUTCOME,
    SurveyRecommendation,
    resolve_administration_mode,
    resolve_effective_scale,
    resolve_si_supplement_needed,
)
from src.schemas.survey import SurveyItemResponse, SurveyScoreInput, SurveyScoreOutput
from src.scoring.item_bank import ITEM_BANK, ScaleItem
from src.scoring.survey_scorer import score_survey

router = APIRouter(prefix="/ai/survey", tags=["survey"])


def _ordered_responses(items: list[SurveyItemResponse]) -> list[int]:
    """Sort by 1-based `index`, verify a contiguous 1..N set (no gaps, no
    duplicates), return the flat value list `score_survey` expects."""
    by_index = sorted(items, key=lambda it: it.index)
    expected = list(range(1, len(items) + 1))
    actual = [it.index for it in by_index]
    if actual != expected:
        raise HTTPException(
            status_code=422,
            detail=(
                f"item indices must be exactly 1..{len(items)} with no "
                f"gaps/duplicates, got {actual}"
            ),
        )
    return [it.value for it in by_index]


@router.post("/score", response_model=SurveyScoreOutput)
async def score(body: SurveyScoreInput) -> SurveyScoreOutput:
    """Score a clinical survey scale using deterministic rules — thin
    wrapper over `score_survey`, no scoring/threshold logic reimplemented
    here (AUDIT-C Korean sex-split cutoffs, PHQ-9 item-9 SI rule, etc. all
    live in `src.scoring.survey_scorer` unmodified)."""
    if not body.responses:
        raise HTTPException(status_code=422, detail="responses must be non-empty")
    flat_responses = _ordered_responses(body.responses)

    try:
        result = score_survey(body.scale_name, flat_responses, patient_sex=body.patient_sex)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry = ITEM_BANK.get(result.scale_name)
    administration_mode = body.administration_mode or "natural"
    safety_referral = result.recommended_action == "safety_referral"

    record = {
        "outcome": ADMINISTERED_OUTCOME,
        "scale_name": result.scale_name,
        "administration_mode": administration_mode,
        "item_bank_version": entry.version if entry else None,
        "item_bank_provenance": entry.provenance if entry else None,
        "responses": flat_responses,
        "total_score": result.total_score,
        "max_score": result.max_score,
        "severity": result.severity,
        "subscale_scores": result.subscale_scores or None,
        "critical_item_positive": result.critical_item_positive,
        "safety_referral": safety_referral,
        "threshold_caveat": F3_SEVERITY_CAVEATS.get(result.scale_name),
    }

    return SurveyScoreOutput(
        **asdict(result),
        items=sorted(body.responses, key=lambda it: it.index),
        si_positive_action_ko=SI_POSITIVE_ACTION_KO if result.critical_item_positive else None,
        administration_mode=administration_mode,
        record=record,
    )


def _item_plan(item: ScaleItem, *, is_si_item: bool = False) -> ItemBankItemPlan:
    """CVR-031 Finding 1: `is_si_item=True` marks PHQ-9 item 9 (index=9) and
    the standalone `si_supplement_item` — never any other item."""
    return ItemBankItemPlan(
        index=item.index,
        text_ko=item.text_ko,
        response_min=item.response_min,
        response_max=item.response_max,
        response_anchors=item.response_anchors,
        primary_track_label=item.primary_track_label,
        secondary_track_label=item.secondary_track_label,
        secondary_response_anchors=item.secondary_response_anchors,
        secondary_track_conversion_note_ko=item.secondary_track_conversion_note_ko,
        is_si_item=is_si_item,
    )


@router.post("/plan", response_model=SurveyPlanResponse)
async def plan(body: SurveyPlanRequest) -> SurveyPlanResponse:
    """Resolve which scale (if any) F3 should administer this session, plus
    whether the standalone SI-supplement item is additionally required
    (CVR-030) — reuses `src.f3`'s own resolve functions unmodified, never a
    forced-scale override (that is a harness-only `--force-questionnaire`
    concept, out of scope for a live-patient administration plan)."""
    recommendation = SurveyRecommendation(
        recommended_questionnaire=body.recommended_questionnaire,
        recommendation_caveat=body.recommendation_caveat,
        top_candidate_disease=body.top_candidate_disease,
        top_candidate_similarity_score=body.top_candidate_similarity_score,
        crisis_triggered=body.crisis_triggered,
        session_ctrs=body.session_ctrs,
    )
    effective_scale, safety_net_triggered = resolve_effective_scale(recommendation)
    base_mode = resolve_administration_mode(
        forced_scale=None, safety_net_triggered=safety_net_triggered
    )
    si_supplement_needed = resolve_si_supplement_needed(
        recommendation, effective_scale, base_mode
    )
    administration_mode = "si_supplement-plan" if si_supplement_needed else base_mode

    # CVR-031 Finding 4 (minor, non-blocking): same scale already
    # administered this session — backend decides what to do with the flag.
    duplicate_administration = (
        body.administered_scale is not None and body.administered_scale == effective_scale
    )

    if effective_scale is None:
        return SurveyPlanResponse(
            scale=None,
            administration_mode=None,
            si_supplement=False,
            not_administrable_reason=(
                "no questionnaire indicated this session — F2 produced no recommendation "
                "and the session was not high-acuity (resolve_effective_scale case 4)"
            ),
            recommendation_caveat=body.recommendation_caveat,
            duplicate_administration=duplicate_administration,
        )

    entry = ITEM_BANK.get(effective_scale)
    if entry is None or not entry.populated:
        return SurveyPlanResponse(
            scale=effective_scale,
            administration_mode=administration_mode,
            si_supplement=si_supplement_needed,
            not_administrable_reason=(
                f"item bank entry for {effective_scale} is unpopulated — "
                "0 items administrable (src.scoring.item_bank)"
            ),
            recommendation_caveat=body.recommendation_caveat,
            duplicate_administration=duplicate_administration,
        )

    si_supplement_item: ItemBankItemPlan | None = None
    if si_supplement_needed:
        phq9_entry = ITEM_BANK.get("PHQ-9")
        if phq9_entry is not None and phq9_entry.populated:
            si_supplement_item = _item_plan(phq9_entry.items[8], is_si_item=True)

    items = [
        _item_plan(item, is_si_item=(effective_scale == "PHQ-9" and item.index == 9))
        for item in entry.items
    ]
    has_si_item = si_supplement_item is not None or any(item.is_si_item for item in items)

    return SurveyPlanResponse(
        scale=effective_scale,
        administration_mode=administration_mode,
        item_bank_version=entry.version,
        item_bank_provenance=entry.provenance,
        instruction_ko=entry.instruction_ko,
        items=items,
        si_supplement=si_supplement_needed,
        si_supplement_item=si_supplement_item,
        si_positive_action_ko=SI_POSITIVE_ACTION_KO if has_si_item else None,
        recommendation_caveat=body.recommendation_caveat,
        duplicate_administration=duplicate_administration,
        refusal_guidance_ko=REFUSAL_GUIDANCE_KO,
    )
