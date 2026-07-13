"""Schemas for the F3 survey-administration production artifact.

`docs/ai/f3_quick_dev_plan.md` §4. Standalone by design, same discipline as
`src.schemas.ai_predicted_disease` (REV-013 §3 lineage): this module shares
NO base class, field, or inheritance relationship with `SlotData`/
`HandoffInput`/`HandoffOutput` (`src/schemas/handoff.py`) — it must never
import that module, and that module must never import this one. The
adversarial isolation suite (`tests/test_f3_hpi_isolation.py`, ADR-032 (4))
enforces the cross-codebase half of that invariant; this module's own
(empty) import list of `src.schemas.handoff` is the half it owns directly.

`is_diagnostic: Literal[False]` is fixed at the type level, not merely a
runtime default (same discipline as `AIPredictedDiseaseOutput`) — a future
schema edit cannot silently widen it without changing the type annotation
itself.

`score_result` mirrors `src.scoring.survey_scorer.ScoreResult` verbatim
(`dataclasses.asdict` shape) — never recomputed or reinterpreted by this
schema layer.

`safety_referral` is `score_result.critical_item_positive` surfaced as its
own top-level field (PHQ-9 Q9 >= 1 only; every other scale's field is
always `false`) — a RECORD field on this artifact. `src/f3.py` itself still
makes zero calls to `OrchestratorAgent.score_and_check_safety` or any
safety route (plan §5, out of scope §9); as of `PLAN-2026-W29-A` step 3,
the F3 artifact/ledger CONSUMER side (`src.continuous_test`, the harness)
routes a PHQ-9 item-9-positive administration to that existing safety
machinery deterministically — see
`src.continuous_test._route_phq9_safety_pathway`. This module's own
boundary (schema layer) is unchanged: no import of orchestrator/safety code.

`administration_mode` (`PLAN-2026-W29-A` step 6 / `ADR-033` decision 6):
`"natural"` (F2's own recommendation drove which scale was administered,
the default) or `"forced"` (a harness-only `--force-questionnaire`
override at the F2->F3 stage boundary; production behavior is otherwise
unchanged — see `src/f3.py::run_f3_administration`'s `forced_scale` kwarg).
Every artifact self-describes which mode produced it.

`threshold_caveat` (`CVR-016` condition 3 / `ADR-033` decision 2, extended to
GAD-7 by `CVR-016`/`CVR-017` binding condition 1 and `REV-039` correction D;
rewritten for AUDIT-C's Korean-primary threshold by `CVR-018` Q4 / `ADR-034`
decision 1-2): populated for an AUDIT-C or GAD-7 `administered` outcome
(`None` for every other scale) — AUDIT-C: the Korean-primary male>=6/
female>=5 threshold's basis and the international cutoff's non-adoption
rationale; GAD-7: the byte-frozen 0-4/5-9/10-14/15-21 bands' Korean-language
scoring-table citation was retracted during v1 sourcing (`item_bank_v1_
sources.md` §2.4) and now rest on international-convention-only sourcing
(Spitzer et al. 2006). Carried as a machine-readable field alongside
`score_result.severity` so a consumer never sees "hazardous_drinking"/
"severe"/etc. without it. The source table lives in `src.f3._SEVERITY_
CAVEATS`, never recomputed here.

`audit_c_international_threshold` (`CVR-018` Q1 Recommendation 1 / `ADR-034`
decision 1): AUDIT-C-only, populated for an AUDIT-C `administered` outcome
(`None` for every other scale/outcome). Carries the international cutoff
(Bush et al. 1998, male/unknown >= 4, female >= 3) as non-action-driving
structured reference metadata alongside the Korean-primary threshold that
actually drives `score_result.severity`/`recommended_action` — this field is
a RECORD only, computed once at administration time by `src.f3.run_f3_
administration` and never read back by any severity/action/`clinician_review`
decision anywhere in this codebase (enforced by
`tests/test_f3.py::TestAuditCInternationalThresholdMetadata`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.scoring.survey_scorer import ScaleName

# Non-diagnostic framing, same discipline as
# `ai_predicted_disease.AI_PREDICTED_DISEASE_DISCLAIMER_KO` — a constant, not
# text an LLM authors (src/f3.py makes zero LLM calls to begin with).
# Version-neutral by design (item_bank v0 vs v1 both exist in this repo,
# `EXP-019`'s v0 artifacts must stay accurately described too) — the actual
# sourcing/validation status of the administered content is on
# `item_bank_version`/`item_bank_provenance`, not hardcoded into this string.
SURVEY_RESULT_DISCLAIMER_KO = (
    "이 결과는 AI가 채점한 자가보고 설문 응답이며 의학적 진단이 아닙니다. "
    "설문 문항의 출처, 버전, 검증 상태는 이 결과의 item_bank_version 및 "
    "item_bank_provenance 필드에 기록되어 있으며, 항목에 따라 검증되지 않았거나 "
    "한국 인구집단 자료와 조정되지 않은 내용이 포함될 수 있습니다. "
    "최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다."
)


class ScoreResultModel(BaseModel):
    """Mirrors `src.scoring.survey_scorer.ScoreResult` verbatim."""

    model_config = ConfigDict(extra="forbid")

    scale_name: str
    total_score: int
    max_score: int
    severity: str
    critical_item_positive: bool = False
    critical_items: list[dict] = Field(default_factory=list)
    subscale_scores: dict[str, int] = Field(default_factory=dict)
    interpretation: str = ""
    recommended_action: str = ""


class AuditCInternationalThresholdMetadata(BaseModel):
    """Non-action-driving structured metadata (`CVR-018` Q1 Recommendation 1
    / `ADR-034` decision 1): the international AUDIT-C cutoff (Bush et al.
    1998), retained on the artifact for reference alongside the
    Korean-primary threshold (male/unknown >= 6, female >= 5,
    `src.scoring.survey_scorer._score_audit_c`) that actually drives
    `score_result.severity`/`score_result.recommended_action`. A RECORD
    only — nothing in `src.f3`/`src.scoring.survey_scorer` reads this field
    to decide severity, `recommended_action`, or `safety_referral`.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = "Bush et al. 1998"
    male_or_unknown_threshold: int = 4
    female_threshold: int = 3
    crossed_international_threshold: bool = Field(
        description=(
            "Whether the raw AUDIT-C total crossed the international threshold "
            "applicable to the administered patient_sex (male_or_unknown_threshold "
            "for male/unknown, female_threshold for female) -- CVR-018 Q1 "
            "Recommendation 1. Computed once at administration time from "
            "score_result.total_score, never recomputed downstream."
        )
    )


class RecommendationProvenance(BaseModel):
    """Passthrough of F2's already-schema-validated fields — never new
    judgment (plan §3). `recommendation_caveat` is carried verbatim.
    """

    model_config = ConfigDict(extra="forbid")

    domain_inference_path: str | None = None
    top_candidate_disease: str | None = None
    top_candidate_similarity_score: float | None = None
    recommendation_caveat: str | None = None


class SurveyResultOutput(BaseModel):
    """Container for the F3 production artifact (`<vp_id>_<ts>_survey.json`).

    `extra="forbid"` — same discipline as `AIPredictedDiseaseOutput`.
    """

    model_config = ConfigDict(extra="forbid")

    vp_id: str
    session_id: str
    timestamp: str
    outcome: Literal["administered", "no_questionnaire_indicated", "item_bank_unpopulated"]
    scale_name: ScaleName | None = None
    item_bank_version: str | None = None
    item_bank_provenance: str | None = None
    responses: list[int] = Field(default_factory=list)
    score_result: ScoreResultModel | None = None
    safety_referral: bool = Field(
        default=False,
        description=(
            "score_result.critical_item_positive surfaced at the top level — a RECORD, "
            "never a trigger. Always false for outcome != 'administered'."
        ),
    )
    administration_mode: Literal["natural", "forced"] = Field(
        default="natural",
        description=(
            "'natural': F2's own recommended_questionnaire drove this administration. "
            "'forced': a harness-only --force-questionnaire override at the F2->F3 "
            "stage boundary (PLAN-2026-W29-A step 6, ADR-033 decision 6) — F3-administration "
            "evidence only, never natural-chain (F2-linkage) evidence."
        ),
    )
    threshold_caveat: str | None = Field(
        default=None,
        description=(
            "Machine-readable band-output caveat, populated for an AUDIT-C or GAD-7 "
            "'administered' outcome (CVR-016 condition 3 / ADR-033 decision 2; extended "
            "to GAD-7 by CVR-016/CVR-017 binding condition 1 / REV-039 correction D; "
            "AUDIT-C rewritten for the Korean-primary threshold by CVR-018 Q4 / ADR-034 "
            "decision 1-2, BUG-040 fix) — AUDIT-C: the Korean-primary male>=6/female>=5 "
            "threshold's basis (Lee JH et al. 2018 KNHANES) and the international "
            "cutoff's (Bush et al. 1998) non-adoption rationale, retained only as "
            "non-action-driving metadata (see audit_c_international_threshold for its "
            "numeric values). GAD-7: the byte-frozen "
            "severity bands' Korean-language scoring-table citation was retracted "
            "during v1 sourcing; bands now rest on international-convention-only "
            "sourcing (Spitzer et al. 2006). `None` for every other scale."
        ),
    )
    audit_c_international_threshold: AuditCInternationalThresholdMetadata | None = Field(
        default=None,
        description=(
            "AUDIT-C-only, populated for an 'administered' AUDIT-C outcome (None for "
            "every other scale/outcome) -- CVR-018 Q1 Recommendation 1 / ADR-034 "
            "decision 1. The international cutoff (Bush et al. 1998) retained as "
            "non-action-driving reference metadata; never independently triggers "
            "severity, recommended_action, or clinician_review."
        ),
    )
    recommendation_provenance: RecommendationProvenance
    answer_mode: Literal["llm", "expected"] | None = Field(
        default=None,
        description="The caller-requested answer_fn mode, recorded verbatim regardless of outcome.",
    )
    is_diagnostic: Literal[False] = False
    disclaimer: str = Field(default=SURVEY_RESULT_DISCLAIMER_KO)
