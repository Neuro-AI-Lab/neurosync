"""Schemas for the survey scoring route."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SurveyItemResponse(BaseModel):
    """One administered item's response — id/index + selected value, the
    same `index` convention `ItemBankItemPlan.index` (`POST /ai/survey/
    plan`) already uses, so the app can round-trip plan -> administer ->
    score without a separate item-numbering scheme."""

    index: int = Field(..., description="1-based item index (matches ItemBankItemPlan.index)")
    value: int = Field(..., description="Selected response value for this item")


class SurveyScoreInput(BaseModel):
    """Input for deterministic survey scoring."""

    session_id: str = Field(default="", description="Optional session ID")
    scale_name: str = Field(..., description="PHQ-9, GAD-7, PHQ-4, WHO-5, or AUDIT-C")
    responses: list[SurveyItemResponse] = Field(
        ...,
        description=(
            "Item id/index + selected value pairs, any order — reordered by "
            "index before scoring"
        ),
    )
    patient_sex: str = Field(default="unknown", description="male/female/unknown (for AUDIT-C)")
    administration_mode: str | None = Field(
        default=None,
        description=(
            "Passthrough from POST /ai/survey/plan's own `administration_mode` "
            "(e.g. natural / safety_net / si_supplement-plan) — echoed into the "
            "ready-to-store `record` only, never re-derived or validated here. "
            "Defaults to 'natural' in `record` when omitted."
        ),
    )


class SurveyScoreOutput(BaseModel):
    """Deterministic scoring result for a clinical survey scale."""

    scale_name: str
    total_score: int
    max_score: int
    severity: str
    critical_item_positive: bool = Field(
        default=False,
        description=(
            "PHQ-9 item-9 (suicidal/self-harm ideation) positivity flag — the "
            "SAME single source of truth as POST /ai/survey/plan's "
            "`is_si_item`/`si_positive_action_ko` gating "
            "(`src.scoring.survey_scorer.is_phq9_item9_positive`). Always "
            "False for every scale other than PHQ-9."
        ),
    )
    critical_items: list[dict] = Field(default_factory=list)
    subscale_scores: dict[str, int] = Field(default_factory=dict)
    interpretation: str = ""
    recommended_action: str = ""

    # ── Additive fields (backend-integration closure) ──────────────────
    items: list[SurveyItemResponse] = Field(
        default_factory=list, description="Per-item echo, index-sorted"
    )
    si_positive_action_ko: str | None = Field(
        default=None,
        description=(
            "109/119 crisis-hotline action text — the SAME constant "
            "`POST /ai/survey/plan` uses (`contracts.survey_plan."
            "SI_POSITIVE_ACTION_KO`), present iff `critical_item_positive`."
        ),
    )
    is_diagnostic: Literal[False] = False
    administration_mode: str | None = Field(
        default=None, description="Echo of the request's administration_mode (see `record` too)"
    )
    record: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Ready-to-store session-record sub-object — assign directly to "
            "`contracts.longitudinal.LongitudinalSessionEntry.f3` for the "
            "SAME session's `POST /ai/temporal/analyze` call. Field set "
            "mirrors `src.services.stateless_longitudinal.build_f3_"
            "administration`'s own `.get(...)` reads verbatim (outcome, "
            "scale_name, item_bank_version, item_bank_provenance, responses, "
            "total_score, max_score, severity, critical_item_positive, "
            "safety_referral, administration_mode, threshold_caveat) plus "
            "subscale_scores (ledger-shape parity, harmless extra key — "
            "`LongitudinalSessionEntry.f3` is untyped `dict[str, Any]`)."
        ),
    )
