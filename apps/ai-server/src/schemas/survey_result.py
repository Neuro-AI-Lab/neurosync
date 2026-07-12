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
always `false`) — a RECORD, never a trigger. Nothing in `src/f3.py` calls
`OrchestratorAgent.score_and_check_safety` or any safety route (plan §5,
out of scope §9).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.scoring.survey_scorer import ScaleName

# Non-diagnostic framing, same discipline as
# `ai_predicted_disease.AI_PREDICTED_DISEASE_DISCLAIMER_KO` — a constant, not
# text an LLM authors (src/f3.py makes zero LLM calls to begin with).
SURVEY_RESULT_DISCLAIMER_KO = (
    "이 결과는 AI가 채점한 자가보고 설문 응답이며 의학적 진단이 아닙니다. "
    "설문 문항은 이 프로젝트 저장소에 실존하는 축약형 구성 라벨(construct label)로만 "
    "구성되어 있으며(v0, 비검증), 공식 표준 문항/응답 앵커 문구가 아닙니다. "
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
    recommendation_provenance: RecommendationProvenance
    answer_mode: Literal["llm", "expected"] | None = Field(
        default=None,
        description="The caller-requested answer_fn mode, recorded verbatim regardless of outcome.",
    )
    is_diagnostic: Literal[False] = False
    disclaimer: str = Field(default=SURVEY_RESULT_DISCLAIMER_KO)
