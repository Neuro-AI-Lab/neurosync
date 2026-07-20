"""POST /ai/survey/score — Deterministic survey scoring (no LLM).

POST /ai/survey/plan — F3 administration-plan endpoint
(`docs/ai/deployment_integration_plan.md` R3). A THIN wrapper over
`src.f3.resolve_effective_scale`/`resolve_si_supplement_needed` (both pure,
deterministic, zero-LLM, zero I/O) — no planner/scoring logic is duplicated
here; the item-bank content returned is `src.scoring.item_bank.ITEM_BANK`
verbatim. The APP administers the returned items to the real patient.
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

from src.f3 import (
    SurveyRecommendation,
    resolve_administration_mode,
    resolve_effective_scale,
    resolve_si_supplement_needed,
)
from src.schemas.survey import SurveyScoreInput, SurveyScoreOutput
from src.scoring.item_bank import ITEM_BANK, ScaleItem
from src.scoring.survey_scorer import score_survey

router = APIRouter(prefix="/ai/survey", tags=["survey"])


@router.post("/score", response_model=SurveyScoreOutput)
async def score(body: SurveyScoreInput) -> SurveyScoreOutput:
    """Score a clinical survey scale using deterministic rules."""
    try:
        result = score_survey(body.scale_name, body.responses, patient_sex=body.patient_sex)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SurveyScoreOutput(**asdict(result))


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
