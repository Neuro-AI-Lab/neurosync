"""Schemas for F4 longitudinal (between-session) state-change analysis.

`docs/ai/f4_quick_dev_plan.md` §4.3, `PLAN-2026-W29-D`, `ADR-036` items 1/9.
Standalone by design, same discipline as `schemas.ai_predicted_disease` /
`schemas.survey_result` (REV-013 §3 lineage / this design's own §6.5 HPI red
line): this module shares NO base class, field, or inheritance relationship
with `SlotData`/`HandoffInput`/`HandoffOutput` (`src/schemas/handoff.py`) or
`DomainCandidate`/`DomainInferenceOutput` (`src/schemas/domain_inference.py`)
— it must never import either of those modules, and neither of them may
import this one. `LongitudinalAnalysisOutput` is structured data for a
future F5 consumer, never injected into any clinician-authored narrative
slot (design doc §6.5).

`is_diagnostic: Literal[False]` is fixed at the type level, matching
`AIPredictedDiseaseOutput`/`SurveyResultOutput` — a future schema edit
cannot silently widen it without changing the type annotation itself.

Wording laws (design doc §5.3, binding on every field below):
  1. `similarity_score`/`confidence` (disease/domain candidate series) are
     NEVER labeled "probability"/"confidence 값이 곧 가능성"/"확률" — only
     "similarity"/"유사도"/"confidence" (the schema's own field name),
     inherited from `AIPredictedDiseaseCandidate.similarity_score`'s own
     binding rule (REV-013 §4).
  2. Evidence-필수: any `TrendVerdict` with `direction != "unknown"` MUST
     carry a non-empty `evidence` list (enforced in `src/f4.py`, not at the
     schema layer — Pydantic cannot express a cross-field conditional this
     specific without a custom validator, and the analysis engine is the
     single writer of this schema).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# CVR-020 Condition 3 machinery / REV-044 §5.3 item 5 (VAL-014 inheritance) /
# ISS-F2V-028 (CVR-019 #1, whole-instrument over-endorsement) — every
# sentence below traces to a specific binding rule this design inherits,
# never invented fresh for F4.
LONGITUDINAL_DISCLAIMER_KO = (
    "이 결과는 여러 세션에 걸친 F1/F2/F3 기록의 값 변화를 규칙 기반(rule-based)으로 "
    "계산한 종단 분석 요약이며, 의학적 진단이 아닙니다(is_diagnostic=false). "
    "disease_candidate_series/domain_candidate_series의 similarity_score/"
    "confidence는 RAG 유사도 신호일 뿐 확률·가능성이 아니며, 그 위에서 계산된 "
    "추세(trend) 역시 원 신호가 노이즈가 많으면 추세도 노이즈가 많습니다 "
    "(VAL-014, 미해결 — 이 산출물은 F2 후보의 임상 타당성을 검증하지 않습니다). "
    "scale_series의 심각도(severity) 구간 판정은 F3의 비-공식 대화형 설문 진행 "
    "방식에 따른 캐비어트(threshold_caveat)를 그대로 승계하며, 동일 척도가 "
    "전 세션에서 체계적으로 과대추정(over-endorsement, ISS-F2V-028)되었을 "
    "가능성은 이 결과에서 별도로 보정되지 않습니다. 이 결과에 evidence로 인용되지 "
    "않은 값은 어떤 세션/필드에 대해서도 임의로 추정하지 않습니다(evidence-필수). "
    "최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다."
)

Direction = Literal["improved", "worsened", "unchanged", "unknown"]


class SlotFillPoint(BaseModel):
    """F1-1 slot-fill point (§3 row F1-1) — scoped to the 8
    `QUESTIONABLE_SLOT_KEYS` only, per the design's own denominator.
    `mental_status_exam_observed` (ADR-036 item 9 / CVR-020 Rec 1) is a
    lightweight *qualitative* observed-flag riding alongside the numeric
    trend, not folded into `filled_count`/`total_questionable` — the 9th
    (observation) slot stays outside the 8-slot denominator by design
    (`grounding.py::OBSERVATION_SLOT_KEY`)."""

    model_config = ConfigDict(extra="forbid")

    session_index: int
    simulated_date: str
    filled_count: int
    total_questionable: int
    newly_filled: list[str] = Field(default_factory=list)
    newly_missing: list[str] = Field(default_factory=list)
    mental_status_exam_observed: bool = False


class ScaleSeriesPoint(BaseModel):
    """F3-1/F3-2/F3-3/F3-4/F3-5/F3-6 point, one per (session, scale)."""

    model_config = ConfigDict(extra="forbid")

    session_index: int
    simulated_date: str
    scale_name: str | None = None
    administered: bool = False
    total_score: int | None = None
    max_score: int | None = None
    severity: str | None = None
    critical_item_positive: bool | None = None
    subscale_scores: dict[str, int] = Field(default_factory=dict)


class CTRSSeriesPoint(BaseModel):
    """F1-3/F1-4/F1-5/F1-6 point."""

    model_config = ConfigDict(extra="forbid")

    session_index: int
    simulated_date: str
    session_ctrs: int | None = None
    crisis_triggered: bool = False
    probe_event_count: int = 0
    risk_floor: int | None = None


class SentimentSeriesPoint(BaseModel):
    """F1-7/F1-8 point. `mean_polarity` is ALWAYS the F1-8 per-turn-derived
    mean (`source="mode_a_derived"`) whenever >=1 turn exists — the design's
    own stated reason: F1-7 (`session_sentiment`, Mode B) can be an empty
    `{}` on a crisis-early-exit session while F1-8 (per-turn) is not.
    `source="mode_b"` is a defensive-only fallback for the (should-not-occur)
    case of zero turns. `risk_signal_count`/`signal_strength`/
    `emotional_shift_detected` (ADR-036 item 9 / CVR-020 Rec 2) surface
    Mode-A's per-turn `risk_signal` and Mode-B's own computed fields that
    the original design left uncaptured — zero marginal LLM cost, both
    already persisted on the F1 artifact this session reads."""

    model_config = ConfigDict(extra="forbid")

    session_index: int
    simulated_date: str
    mean_polarity: float | None = None
    dominant_emotions: list[str] = Field(default_factory=list)
    source: Literal["mode_a_derived", "mode_b"] = "mode_a_derived"
    risk_signal_count: int = 0
    signal_strength: str | None = None
    emotional_shift_detected: bool | None = None


class DiseaseCandidateSeriesPoint(BaseModel):
    """F2-2 point. `rank` = 1-based position in that session's own top-5
    (as F2 shipped it, never re-sorted here). `similarity_score` is a
    similarity TREND datum, never a probability (wording law 1)."""

    model_config = ConfigDict(extra="forbid")

    session_index: int
    simulated_date: str
    disease: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    rank: int


class DomainCandidateSeriesPoint(BaseModel):
    """F2-1 point."""

    model_config = ConfigDict(extra="forbid")

    session_index: int
    simulated_date: str
    domain: str
    confidence: float = Field(ge=0.0, le=1.0)


class TrendVerdict(BaseModel):
    """`basis` is a human-readable, code-fixed string naming the exact
    aggregation mechanism used (Criterion 0/0b, `ADR-036` item 1) — never a
    free-form LLM sentence, never chosen post-hoc per dimension. `evidence`
    is non-empty whenever `direction != "unknown"` (evidence-필수,
    enforced by the writer, `src/f4.py`)."""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    direction: Direction = "unknown"
    basis: str
    n_comparable_points: int
    evidence: list[str] = Field(default_factory=list)


class LongitudinalAnalysisOutput(BaseModel):
    """Container for the F4 production artifact
    (`<vp_id>_<ts>_temporal.json`). `extra="forbid"` — same discipline as
    `AIPredictedDiseaseOutput`/`SurveyResultOutput`."""

    model_config = ConfigDict(extra="forbid")

    vp_id: str
    arc_mode: str | None = None
    n_sessions: int
    session_span_days: int | None = None

    slot_fill_series: list[SlotFillPoint] = Field(default_factory=list)
    scale_series: dict[str, list[ScaleSeriesPoint]] = Field(default_factory=dict)
    ctrs_series: list[CTRSSeriesPoint] = Field(default_factory=list)
    sentiment_series: list[SentimentSeriesPoint] = Field(default_factory=list)
    disease_candidate_series: list[DiseaseCandidateSeriesPoint] = Field(default_factory=list)
    domain_candidate_series: list[DomainCandidateSeriesPoint] = Field(default_factory=list)

    trend_verdicts: list[TrendVerdict] = Field(default_factory=list)
    overall_direction: Direction = "unknown"
    # ADR-036 item 9 / CVR-020 Rec 3 — reuses design doc §2.1's own archetype
    # vocabulary; classification rule disclosed in `src/f4.py::_course_shape`.
    course_shape: Literal[
        "gradual_improvement",
        "improvement_with_plateau",
        "relapse_after_partial_improvement",
        "worsening_sustained",
        "crisis_episode",
        "unknown",
    ] = "unknown"
    # ADR-036 item 9 / CVR-020 Rec 4 — rule disclosed in
    # `src/f4.py::_concordance_flag`.
    concordance_flag: Literal["concordant", "discordant", "unknown"] = "unknown"
    # CVR-020 binding condition 3 machinery — never merely a routine `None`
    # buried in scale_series; a dedicated, always-present (possibly empty)
    # list the report renders prominently in its risk section.
    crisis_f3_gaps: list[str] = Field(default_factory=list)

    is_diagnostic: Literal[False] = False
    disclaimer: str = Field(default=LONGITUDINAL_DISCLAIMER_KO)
    generated_at: str = ""
