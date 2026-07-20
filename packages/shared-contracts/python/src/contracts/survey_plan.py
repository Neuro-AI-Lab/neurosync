"""POST /ai/survey/plan — request/response schema.

Single source of truth between apps/api (consumer) and apps/ai-server
(producer) for the F3 administration-planning endpoint
(`docs/ai/deployment_integration_plan.md` R3). Exposes
`src.f3.resolve_effective_scale`/`resolve_si_supplement_needed` (F2 output +
crisis/CTRS state in -> administer-plan out) so the APP can administer real
items to the real patient — no planner/scoring logic is duplicated here or
in the route; both resolve functions are called exactly as `src.f3`'s own
production callers already call them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ScaleNameContract = Literal["PHQ-9", "GAD-7", "PHQ-4", "WHO-5", "AUDIT-C"]

AdministrationModeContract = Literal["natural", "safety_net", "si_supplement-plan"]

# CVR-031 Finding 1 (major): byte-identical crisis-hotline copy reused from
# `apps/ai-server/src/f1.py::CRISIS_RESPONSE` (109 자살예방상담전화 / 119
# 응급전화). This package (`neuro-sync-contracts`) has NO dependency on
# `apps.ai-server.src` (dependency direction is the reverse — ai-server
# depends on this package, `apps/ai-server/pyproject.toml` `[tool.uv.sources]`
# — importing across that boundary would invert it), so the same clinical
# copy is intentionally duplicated here verbatim rather than paraphrased or
# freshly authored. Any future wording change to `CRISIS_RESPONSE` must be
# mirrored here by hand.
SI_POSITIVE_ACTION_KO = (
    "지금 많이 힘드시군요. 당신의 이야기를 듣고 있습니다. "
    "자살예방상담전화 109, 응급전화 119로 연락해 주세요."
)

# CVR-031 Finding 5 (minor): deterministic refusal/no-response guidance —
# content specified verbatim by the routing brief (강요 금지 + 기록 후 진행),
# not independently authored clinical text.
REFUSAL_GUIDANCE_KO = (
    "환자가 응답을 거부하거나 무응답인 경우 강요하지 말고, 거부/무응답 사실을 "
    "기록한 후 다음 문항으로 진행하세요."
)


class SurveyPlanRequest(BaseModel):
    """`f2_recommendation` mirrors the F2 `ai_predicted_disease` artifact's
    own top-level fields this route reads (`src.f3.SurveyRecommendation`) —
    `recommended_questionnaire`/`recommendation_caveat` plus the top
    candidate's `disease`/`similarity_score` (both optional, informational
    only; `resolve_effective_scale` never reads them).

    `crisis_triggered`/`session_ctrs`: the SAME session-level risk-context
    fields the F2 artifact itself reprojects (`src.f3.SurveyRecommendation`
    docstring) — required here directly since this route never reads a
    domain-inference artifact off disk.

    `administered_scale`: the scale, if any, ALREADY administered this
    session before this plan call (e.g. a natural-mode PHQ-9 already run) —
    informational context only; not consumed by `resolve_effective_scale`/
    `resolve_si_supplement_needed` today, carried for forward-compatible
    caller bookkeeping.
    """

    recommended_questionnaire: ScaleNameContract | None = None
    recommendation_caveat: str | None = None
    top_candidate_disease: str | None = None
    top_candidate_similarity_score: float | None = None
    crisis_triggered: bool = False
    session_ctrs: int | None = None
    administered_scale: ScaleNameContract | None = None

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_orchestrator_turn(
        cls,
        *,
        crisis_triggered: bool,
        safety_status: Any | None = None,
        recommended_questionnaire: ScaleNameContract | None = None,
        recommendation_caveat: str | None = None,
        top_candidate_disease: str | None = None,
        top_candidate_similarity_score: float | None = None,
        administered_scale: ScaleNameContract | None = None,
    ) -> SurveyPlanRequest:
        """CVR-031 Finding 2 (major): documented shape adapter from the
        upstream orchestrator-turn shapes to this route's flat request
        fields — the backend must call THIS, never hand-roll the mapping,
        so it cannot mistranslate `crisis_triggered`/`ctrs_level`.

        Upstream shapes this maps FROM (`apps/ai-server/src/schemas/
        orchestrator.py`): `OrchestratorTurnResult.crisis_triggered: bool`
        (top-level) + `OrchestratorTurnResult.safety_status.ctrs_level:
        CTRSLevel` (nested `IntEnum`, 1=most urgent .. 5=stable,
        `src/schemas/common.py`). `safety_status` here is accepted
        duck-typed (an object with a `.ctrs_level` attribute, or a
        `{"ctrs_level": ...}` mapping) so this module never needs to import
        `apps.ai-server.src` types — that dependency would invert the real
        one (ai-server depends on this package, not the reverse).

        CVR-028 Finding 1 safety-net dependency (binding): `src.f3.
        resolve_effective_scale`'s entire crisis safety net (force PHQ-9
        when F2 recommends nothing on a high-acuity session) reads
        `SurveyPlanRequest.crisis_triggered`/`session_ctrs` and NOTHING
        else — if this mapping is wrong, that safety net goes clinically
        dark for real patients with no error signal (CVR-031 Finding 2).

        Safety-first missing-data rule (do NOT weaken): if `safety_status`
        is absent/`None` or carries no readable `ctrs_level`, `session_ctrs`
        resolves to `None` (`resolve_effective_scale` still evaluates its
        `session_ctrs is not None and session_ctrs <= 3` branch as False for
        that field alone) — but `crisis_triggered` is passed through
        EXACTLY as given, never downgraded to `False` because ctrs is
        missing. A `crisis_triggered=True` session stays trigger-eligible
        for the safety net through the `crisis_triggered` field alone, even
        with zero CTRS information — absent CTRS data must never silently
        disable the net.
        """
        ctrs_level: int | None = None
        if safety_status is not None:
            raw = (
                safety_status.get("ctrs_level")
                if isinstance(safety_status, dict)
                else getattr(safety_status, "ctrs_level", None)
            )
            if raw is not None:
                ctrs_level = int(raw)
        return cls(
            recommended_questionnaire=recommended_questionnaire,
            recommendation_caveat=recommendation_caveat,
            top_candidate_disease=top_candidate_disease,
            top_candidate_similarity_score=top_candidate_similarity_score,
            crisis_triggered=crisis_triggered,
            session_ctrs=ctrs_level,
            administered_scale=administered_scale,
        )


class ItemBankItemPlan(BaseModel):
    """One administrable item — mirrors `src.scoring.item_bank.ScaleItem`'s
    caller-facing fields verbatim (no re-authoring)."""

    index: int
    text_ko: str
    response_min: int
    response_max: int
    response_anchors: dict[int, str] | None = None
    primary_track_label: str | None = None
    secondary_track_label: str | None = None
    secondary_response_anchors: dict[int, str] | None = None
    secondary_track_conversion_note_ko: str | None = None
    is_si_item: bool = Field(
        default=False,
        description=(
            "CVR-031 Finding 1: True for PHQ-9 item 9 (index=9, the "
            "suicidal/self-harm ideation item) and for the standalone "
            "si_supplement_item — lets the APP act on a positive answer "
            "(>= si_positive_threshold) IMMEDIATELY, without waiting for "
            "a separate /score call."
        ),
    )

    model_config = ConfigDict(extra="forbid")


class SurveyPlanResponse(BaseModel):
    """`scale`: `None` when `resolve_effective_scale` yields no
    administration this session (genuinely no questionnaire indicated,
    `src.f3.resolve_effective_scale` case 4) — `items`/`instruction_ko` are
    then empty/`None` and `not_administrable_reason` explains why.

    `administration_mode`: `"natural"` (F2's own recommendation) |
    `"safety_net"` (`resolve_effective_scale`'s CVR-028 Finding 1 fallback)
    | `"si_supplement-plan"` (a REAL F2-recommended non-PHQ-9 scale is being
    administered AND `resolve_si_supplement_needed` also fires, CVR-030) —
    the third value takes precedence over `"natural"` in this field
    specifically so a caller checking this one field never misses the
    supplemental-item requirement; `si_supplement`/`si_supplement_item`
    below carry the actual supplemental content either way.
    """

    scale: ScaleNameContract | None = None
    administration_mode: AdministrationModeContract | None = None
    item_bank_version: str | None = None
    item_bank_provenance: str | None = None
    instruction_ko: str | None = None
    items: list[ItemBankItemPlan] = Field(default_factory=list)
    si_supplement: bool = False
    si_supplement_item: ItemBankItemPlan | None = None
    not_administrable_reason: str | None = None

    # CVR-031 Finding 1 (major): same-call SI actionability. Whenever this
    # plan carries an `is_si_item` item (PHQ-9 item 9 in `items`, or
    # `si_supplement_item`), `si_positive_action_ko` is populated so the APP
    # rule is trivial: `if answer_to_si_item >= si_positive_threshold: show
    # si_positive_action_ko` — no waiting for `/score`. `None` when this
    # plan carries no SI item at all (`not_administrable`/non-PHQ-9 plans
    # with no si_supplement).
    si_positive_action_ko: str | None = None
    si_positive_threshold: int = Field(
        default=1,
        description=(
            "Matches src.scoring.survey_scorer.is_phq9_item9_positive's own "
            "rule (response >= 1 is critical, Kroenke et al. 2001) — kept "
            "here so the APP never hardcodes the threshold separately."
        ),
    )

    # CVR-031 Finding 3 (minor): echo of the request's recommendation_caveat
    # (e.g. PHQ-9's mania/hypomania blind spot, ai_predicted_disease.py:
    # 186-199, CVR-003) so it survives to the administering surface.
    recommendation_caveat: str | None = None

    # CVR-031 Finding 4 (minor): non-blocking warning only — backend decides
    # what to do, this route never blocks re-administration.
    duplicate_administration: bool = False

    # CVR-031 Finding 5 (minor): deterministic refusal/no-response guidance,
    # populated whenever this plan has administrable items.
    refusal_guidance_ko: str | None = None

    model_config = ConfigDict(extra="forbid")
