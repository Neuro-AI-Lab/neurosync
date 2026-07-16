"""Schemas for the F5 clinical hand-off report (static + longitudinal).

`docs/ai/f5_quick_dev_plan.md` §2/§4.2, `PLAN-2026-W29-E`, `ADR-037`.
Standalone by design, same discipline as `schemas.ai_predicted_disease` /
`schemas.survey_result` / `schemas.longitudinal` (REV-013 §3 lineage / this
design's own §6.1 hard red lines): this module shares NO base class, field,
or inheritance relationship with `SlotData`/`HandoffInput`/`HandoffOutput`
(`src/schemas/handoff.py`) or `DomainCandidate`/`DepartmentCandidate`/
`DomainInferenceOutput` (`src/schemas/domain_inference.py`) — it must never
import either of those modules, and neither of them may import this one.
`tests/test_f5_hpi_isolation.py`'s type-layer checks enforce the
cross-codebase half of that invariant; this module's own (empty) import
list of those two modules is the half it owns directly.

This module DOES import `schemas.longitudinal.LongitudinalAnalysisOutput`
(F4's own output, consumed verbatim for Part B — never recomputed) and
`schemas.ai_predicted_disease.AIPredictedDiseaseCandidate` (F2's own
candidate schema, consumed verbatim for A6) — both are themselves
standalone-by-design modules that do not import `schemas.handoff`/
`schemas.domain_inference`, so importing them here does not weaken this
module's own isolation invariant (same precedent `src/f4.py` already
establishes by importing `schemas.ai_predicted_disease`).

Hard red lines (design doc §6.1, structural at the type level here):
  1. AI-predicted-disease content (`AIPredictedDiseaseSection`) is its own
     dedicated field/section type (`a6_ai_predicted_disease`) — no other
     section field on `HandoffReportOutput` ever carries an
     `AIPredictedDiseaseCandidate`/`RankedDiseaseCandidate` value. The A8
     narrative section is a plain, structurally inert `NarrativeSection`
     (a `str | None` field defaulting to `None`, gated by
     `narrative_enabled: bool = False`) — it can never structurally embed
     A6 content because it has no field capable of holding one.
  2. `similarity_score` is never relabeled "probability"/"confidence
     값"/"확률" anywhere in this module's field names, descriptions, or
     constants (REV-013 §4 lineage, inherited via
     `AIPredictedDiseaseCandidate` unchanged).
  3. `is_diagnostic: Literal[False]` fixed at the type level (not merely a
     runtime default) on the top-level container, matching
     `AIPredictedDiseaseOutput`/`SurveyResultOutput`/
     `LongitudinalAnalysisOutput` — a future schema edit cannot silently
     widen it without changing the type annotation itself.

`extra="forbid"` on every model in this module, same discipline as every
other F1-F4 production schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate
from src.schemas.longitudinal import LongitudinalAnalysisOutput

# ── A0 header disclaimer constants (ADR-037 Decision 4) ────────────────────

HEADER_SELF_REPORT_ONLY_KO = (
    "이 보고서의 내용은 환자의 자가보고(AI가 진행한 대화형 문진)로만 구성되며, "
    "보호자·가족 등 제3자(협력 정보 제공자, collateral informant)의 진술은 "
    "포함되어 있지 않습니다."
)
HEADER_AI_ASSEMBLED_KO = (
    "이 보고서는 AI가 F1-F4 산출물을 규칙 기반(rule-based)으로 자동 조합한 문서이며, "
    "새로운 임상 판단을 추가하지 않습니다."
)
HEADER_NOT_OFFICIAL_RECORD_KO = (
    "이 문서는 비공식 문서(비공식 참고 자료)이며 공식 의무기록이 아닙니다."
)
HEADER_NON_DIAGNOSTIC_KO = (
    "이 문서는 의학적 진단이 아니며(is_diagnostic=false), 최종 진단과 치료 방향은 "
    "반드시 의료진의 판단에 따라 결정되어야 합니다."
)

# ── A5 / B1 wording-law constants (design doc §6.1 point 3, REV-039) ──────

NON_VALIDATED_ADMINISTRATION_CAVEAT_KO = (
    "AI가 진행한 대화형 문진 결과이며, 검증된 임상 설문 시행이 아닙니다."
)
SLOT_OVERVIEW_CAVEAT_KO = (
    "이 표의 값은 AI가 진행한 대화형 문진(F1)에서 환자가 자가보고한 내용이며, "
    "임상의의 직접 평가나 검증된 척도 시행이 아닙니다."
)
GAD7_THRESHOLD_CAVEAT_ASYMMETRY_NOTE_KO = (
    "GAD-7의 threshold_caveat 필드는 현재 이 시스템의 모든 산출물에서 구조적으로 "
    "null입니다 — AUDIT-C와의 비대칭이며 값이 누락된 것이 아니라 설계상 특성입니다 "
    "(CVR-016/CVR-017 binding condition, REV-039 row 5)."
)

# ── A7 medication disclosure (ADR-037 Decision 5) ──────────────────────────

MEDICATION_NOTE_KO = "약물 정보: 별도 구조화 항목 없음, HPI/병력 서술 포함 여부만 확인"

# ── A4 MSE partial-rendering constants ──────────────────────────────────

MSE_FLAT_TEXT_LABEL_KO = "텍스트 기반 정신상태 메모 — 비구조화"
MSE_TEXT_DERIVABLE_DOMAINS: tuple[str, ...] = (
    "mood",
    "thought_process",
    "thought_content",
    "insight",
    "judgment",
    "cognition",
)
MSE_OBSERVATION_DEPENDENT_DOMAINS: tuple[str, ...] = (
    "appearance",
    "behavior",
    "motor_activity",
    "speech",
    "affect",
)
MSE_TEXT_DERIVABLE_NOTE_KO = "이 슬롯에서 개별 추출 불가"
MSE_OBSERVATION_DEPENDENT_NOTE_KO = "평가 불가 — 텍스트 전용 문진"

# ── B1 / A5 gap-acuity framing (CVR-022 binding condition 3) ──────────────

CRISIS_F3_GAP_ACUITY_FRAMING_KO = (
    "F3 시행 완결성은 환자 위기도(acuity)와 역상관 관계를 보일 수 있습니다 — "
    "위험이 높은 세션일수록 오히려 척도가 시행되지 않는 경향이 있을 수 있으므로, "
    "아래 목록의 개수만이 아니라 이 경향 자체를 함께 고려해야 합니다 "
    "(CVR-022 binding condition 3)."
)

# ── B section overall_direction sensitivity (REV-045 row 2) ───────────────

OVERALL_DIRECTION_SENSITIVITY_NOTE_KO = (
    "overall_direction은 세션별 척도/CTRS/sentiment 방향의 다수결(worsened-priority)로 "
    "계산되며(src.f4::_overall_direction), sentiment 포함 여부에 따라 verdict가 달라질 "
    "수 있습니다(REV-045 row 2) — 세부 근거는 trend_verdicts의 evidence를 참고하십시오."
)

# ── A8 narrative absent marker (ADR-037 Decision 1) ────────────────────────

NARRATIVE_ABSENT_MARKER_KO = "AI 종합 소견 미생성 (narrative disabled)"

# ── A8 narrative — Task 2 (`handoff_generator` v3, PLAN-2026-W29-<F5-handoff>)
# additions. The narrative path stays OPTIONAL (`HandoffReportInput.
# narrative_enabled`, still `False` by default) — these constants are only
# ever used when a caller supplies an externally-generated `narrative_text`
# (`src.f5` itself still makes zero LLM calls; see `f5.py::_build_a8`). ────

NARRATIVE_ENABLED_LABEL_KO = "AI 생성 — 임상 진단 아님 (자가보고 기반, 비공식)"

# Defense-in-depth rejection marker (HPI hard red line, design doc §6.1
# point 1): `f5.py::_build_a8` scans a caller-supplied `narrative_text` for
# any A6 candidate `disease` string and — if found — REFUSES to render the
# narrative rather than merely omitting/redacting the match, replacing
# `a8_narrative.absent_marker` with this constant instead of the generic
# `NARRATIVE_ABSENT_MARKER_KO` above so a reader can tell "never generated"
# apart from "generated but blocked" (grep-distinguishable in qa's own
# regression checks).
NARRATIVE_REJECTED_DISEASE_LEAK_KO = (
    "AI 종합 소견 생성 거부 — 제공된 내러티브 텍스트에 AI 예상질환(A6) 후보 병명이 "
    "포함되어 있어 HPI 격리 원칙(A6/A8 구조적 분리, design doc §6.1)에 따라 거부되었습니다."
)

# ── A8 FHIR-bundle omission note (ADR-038 Decision 2d, CVR-024 Finding 6 /
# Recommendation 6) ─────────────────────────────────────────────────────
# md/PDF render an explicit A8 disabled marker (NARRATIVE_ABSENT_MARKER_KO
# above); the FHIR bundle's Composition.section list omits an A8 entry
# entirely (REV-047 Criterion 6a: ruled a MORE conservative resolution,
# not reversed here). This one-line note closes the resulting cross-format
# reconciliation gap CVR-024 flagged (a clinician comparing 8 md/PDF
# sections against 7 FHIR sections, with no explanation) — appended to the
# FHIR bundle's own disclaimer section text, not a new A8-titled section
# (that would recreate exactly the "checkable A8 placeholder" surface
# REV-047's stronger-disposition ruling deliberately avoided).

A8_FHIR_OMISSION_NOTE_KO = (
    "A8(임상 종합 소견, 내러티브) 섹션은 이 FHIR 번들에 별도로 포함되지 않았습니다 — "
    "narrative_enabled=false로 이번 미션에서 비활성화되었습니다 (A8 omitted — "
    "narrative disabled this mission)."
)

# ── A7 validation-drop disclosure (ADR-038 Decision 2a, VAL-016) ──────────
# Distinguishes a genuine model judgment of "no department to recommend"
# from an upstream F2 atomic-schema-validation drop that silently
# discarded already-generated candidates (VAL-016 lineage: a single
# `source_id`-missing evidence item nested under `domain_candidates`
# collapses the WHOLE LLM-response object, including an already-valid
# `department_candidates` list). Never a bare "정보 없음" when the source
# artifact's own `validation_errors` field is non-empty.

A7_NO_CANDIDATES_MODEL_JUDGED_KO = "정보 없음 (권장 진료과 후보 없음 — 모델 판정)"
A7_NO_CANDIDATES_VALIDATION_DROPPED_KO = (
    "정보 없음 — 후보가 스키마 검증 오류로 제외됨 (validation_errors 존재, VAL-016/"
    "BUG-031 계열). 모델이 후보를 찾지 못했다는 의미가 아니라, 상위 F2 단계에서 이미 "
    "생성된 후보가 스키마 검증 실패로 삭제되었을 가능성이 있습니다."
)

# ── Ceiling-score over-endorsement caveat (ADR-038 Decision 2c, CVR-024
# Finding 4) ────────────────────────────────────────────────────────────
# A VERBATIM excerpt of `schemas.longitudinal.LONGITUDINAL_DISCLAIMER_KO`'s
# own over-endorsement sentence (never invented fresh here — see
# `tests/test_f5_report.py`'s substring-containment assertion binding the
# two constants together). Co-located directly adjacent to any A3/A5 score
# where `total_score == max_score` (scale ceiling), not only in B1's
# longitudinal narrative. Exact-ceiling only — no near-ceiling threshold
# judgment is computed here (`ADR-038` explicitly scopes that out).

CEILING_SCORE_CAVEAT_KO = (
    "동일 척도가 전 세션에서 체계적으로 과대추정(over-endorsement, ISS-F2V-028)되었을 "
    "가능성은 이 결과에서 별도로 보정되지 않습니다."
)

# ── Top-level container disclaimer ─────────────────────────────────────────

HANDOFF_REPORT_DISCLAIMER_KO = (
    "이 F5 인계 요약 보고서는 F1-F4 산출물을 규칙 기반으로 조합한 문서이며 "
    "의학적 진단이 아닙니다(is_diagnostic=false). AI 예상질환(A6)의 similarity_score는 "
    "RAG 유사도 신호일 뿐 확률·가능성이 아니며(REV-013 §4), 이 문서 어디에 등장하든 "
    "시행된 설문(A3/A5/B1) 점수는 모두 검증된 임상 설문 시행이 아닌 AI 대화형 문진 "
    "결과입니다. 이 문서는 환자의 자가보고만으로 구성되며(보호자 등 제3자 진술 없음), "
    "AI가 자동 조합한 비공식 문서로 공식 의무기록이 아닙니다. 최종 진단과 치료 방향은 "
    "반드시 의료진의 판단에 따라 결정되어야 합니다."
)


# ── A0 ──────────────────────────────────────────────────────────────────


class HeaderDisclaimer(BaseModel):
    """Standing disclaimer block (`ADR-037` Decision 4 / `CVR-023` Finding 6)."""

    model_config = ConfigDict(extra="forbid")

    self_report_only: str = Field(default=HEADER_SELF_REPORT_ONLY_KO)
    ai_assembled: str = Field(default=HEADER_AI_ASSEMBLED_KO)
    not_official_record: str = Field(default=HEADER_NOT_OFFICIAL_RECORD_KO)
    non_diagnostic: str = Field(default=HEADER_NON_DIAGNOSTIC_KO)


class HeaderSection(BaseModel):
    """A0 — situation-first micro-header (SBAR-motivated, design doc §2.1)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    persona_id: str
    persona_name: str
    session_index: int
    simulated_date: str
    model: str
    chief_complaint_summary: str | None = None
    session_ctrs: int | None = None
    risk_level: str | None = None
    crisis_triggered: bool = False
    crisis_turn: int | None = None
    disclaimer: HeaderDisclaimer = Field(default_factory=HeaderDisclaimer)


# ── A1 / A2 ────────────────────────────────────────────────────────────


class ChiefComplaintSection(BaseModel):
    """A1."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    text: str | None = None


class HistoryOfPresentIllnessSection(BaseModel):
    """A2."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    text: str | None = None


# ── All-session slot overview (Task 1, extends A1/A2's "latest session
# only" default with a per-slot BEST-AVAILABLE picture across the WHOLE
# ledger) ───────────────────────────────────────────────────────────────
#
# `CANONICAL_SLOT_KEYS` DUPLICATES (never imports) `agents.clinical_slot.
# ALL_SLOT_KEYS` verbatim, in the same order — this module and `f5.py` stay
# zero-LLM-agent-import by construction (module docstring's own isolation
# discipline), so the 12-key list is re-declared here rather than imported
# from an `agents/` module. `tests/test_f5.py` asserts byte-for-byte key
# equality against the live `ALL_SLOT_KEYS` so the two never silently
# drift apart.

SLOT_NEVER_COLLECTED_KO = "미수집"

CANONICAL_SLOT_KEYS: tuple[tuple[str, str], ...] = (
    ("encounter_metadata", "진료 기본정보"),
    ("chief_complaint", "주호소"),
    ("history_of_present_illness", "현병력"),
    ("past_psychiatric_history", "정신과 과거력"),
    ("medical_history", "신체질환/신경학적 병력"),
    ("personal_social_history", "개인사/사회력"),
    ("family_history", "가족력"),
    ("substance_use_history", "음주·흡연·물질사용"),
    ("mental_status_exam", "정신상태검사"),
    ("risk_assessment", "위험평가"),
    ("clinical_assessment", "평가/진단적 인상"),
    ("treatment_plan", "치료계획/치료내용"),
)

# For slots already covered in detail by an existing Part A section, point
# there instead of duplicating a lossy truncated copy as the reader's only
# source — improves readability without hiding the slot from the one
# consolidated table (design goal: maximum information, high visibility).
# `encounter_metadata`/`clinical_assessment`/`treatment_plan` are F1
# `SYSTEM_SLOT_KEYS` (`grounding.py`) — never populated by the conversation
# extractor; `encounter_metadata` alone has an existing deterministic home
# (A0), the other two have none anywhere in this system.
SLOT_SECTION_POINTERS_KO: dict[str, str] = {
    "encounter_metadata": (
        "A0 참조 (시스템이 conversation.json 메타데이터에서 조합 — 대화 슬롯 아님)"
    ),
    "chief_complaint": "A1 참조 (전문 서술)",
    "history_of_present_illness": "A2 참조 (전문 서술)",
    "mental_status_exam": "A4 참조 (전문 서술)",
    "risk_assessment": "A3 참조 (전문 서술 + 종단 위험 신호)",
}


class SlotOverviewRow(BaseModel):
    """One canonical slot's best-available picture across ALL sessions in
    the ledger (Task 1) — never only the latest session."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    collected: bool
    latest_value: str | None = None
    source_session_index: int | None = None
    source_simulated_date: str | None = None
    change_history: list[str] = Field(default_factory=list)
    change_history_full: list[str] = Field(
        default_factory=list,
        description=(
            "Same (session, value) points as `change_history`, but each "
            "value only whitespace-flattened — NEVER character-truncated "
            "(CVR-026 Finding 1/2: `change_history`'s own 60-char-per-entry "
            "cap loses clinically material text, e.g. an early HPI "
            "precipitant/symptom mentioned only in an early session). "
            "Renderer-only field: consumed exclusively by the 상세 부록 "
            "(detail appendix) section, never the compact slot table."
        ),
    )
    section_pointer: str | None = None


class SlotOverviewSection(BaseModel):
    """All-session slot overview — extends A1/A2's default "latest session
    only" static-state rule (Task 1, this mission) with a per-slot
    BEST-AVAILABLE value + provenance + compact change-history across the
    whole VP arc. Deliberately a SEPARATE section from A1/A2 (which keep
    rendering the header/latest session's own value unchanged, per Part
    A's documented "latest session" architecture, design doc §2.2 preamble)
    rather than a redefinition of either — mirrors the precedent A3's own
    "종단 위험 신호" subsection already set (`ADR-037` Decision 2)."""

    model_config = ConfigDict(extra="forbid")

    rows: list[SlotOverviewRow] = Field(default_factory=list)
    non_validated_caveat: str = Field(default=SLOT_OVERVIEW_CAVEAT_KO)


# ── A3 ──────────────────────────────────────────────────────────────────


class LongitudinalRiskSignal(BaseModel):
    """One item-9-positive/`safety_referral`-triggered F3 administration,
    ANY session (`ADR-037` Decision 2 / `CVR-023` recommendation 4) —
    date-stamped, co-displayed against that SAME session's F1 CTRS value."""

    model_config = ConfigDict(extra="forbid")

    session_index: int
    simulated_date: str
    scale_name: str | None = None
    total_score: int | None = None
    max_score: int | None = None
    severity: str | None = None
    safety_referral: bool = False
    critical_item_positive: bool | None = None
    same_session_ctrs: int | None = None
    same_session_crisis_triggered: bool = False
    discordance_note: str
    ceiling_caveat: str | None = Field(
        default=None,
        description=(
            "Set to CEILING_SCORE_CAVEAT_KO iff total_score == max_score "
            "(exact scale ceiling only, ADR-038 Decision 2c). None otherwise."
        ),
    )


class StalenessPointer(BaseModel):
    """Mandatory latest-scored-instrument staleness pointer, rendered
    whenever the current (header) session has no F3 data of its own
    (`ADR-037` Decision 2, VP-003 worked example)."""

    model_config = ConfigDict(extra="forbid")

    applicable: bool
    latest_scored_session_index: int | None = None
    latest_scored_simulated_date: str | None = None
    scale_name: str | None = None
    total_score: int | None = None
    max_score: int | None = None
    severity: str | None = None
    safety_referral: bool | None = None
    critical_item_positive: bool | None = None
    sessions_stale: int | None = None
    days_stale: int | None = None
    note: str
    ceiling_caveat: str | None = Field(
        default=None,
        description=(
            "Set to CEILING_SCORE_CAVEAT_KO iff total_score == max_score "
            "(exact scale ceiling only, ADR-038 Decision 2c). None otherwise, "
            "including when applicable=False (no scored administration exists)."
        ),
    )


class RiskSafetySection(BaseModel):
    """A3 — promoted top-level risk/safety section (design principle 2).
    Current-session fields per Part A's own rule PLUS the "종단 위험 신호"
    (longitudinal risk-signal) subsection (`ADR-037` Decision 2)."""

    model_config = ConfigDict(extra="forbid")

    current_session_index: int
    current_simulated_date: str
    risk_assessment_present: bool
    risk_assessment_text: str | None = None
    session_ctrs: int | None = None
    risk_level: str | None = None
    risk_floor: int | None = None
    probe_event_count: int = 0
    crisis_triggered: bool = False
    crisis_turn: int | None = None
    current_session_has_f3: bool
    current_session_safety_referral: bool | None = None
    current_session_critical_item_positive: bool | None = None
    longitudinal_risk_signals: list[LongitudinalRiskSignal] = Field(default_factory=list)
    trend_concordance_flag: Literal["concordant", "discordant", "unknown"] = "unknown"
    staleness_pointer: StalenessPointer


# ── A4 ──────────────────────────────────────────────────────────────────


class MSEDomainStatus(BaseModel):
    """One of the research note's 11 canonical MSE domains, honestly marked
    not individually extractable from F1's single flat-string slot (design
    doc §2.2 A4 row)."""

    model_config = ConfigDict(extra="forbid")

    domain: str
    assessable: bool = False
    note: str


class MentalStatusSection(BaseModel):
    """A4 — partial, text-derived only."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    raw_text: str | None = None
    label: str = Field(default=MSE_FLAT_TEXT_LABEL_KO)
    domain_checklist: list[MSEDomainStatus] = Field(default_factory=list)


# ── A5 ──────────────────────────────────────────────────────────────────


class QuestionnaireSection(BaseModel):
    """A5 — latest ADMINISTERED session's F3 data, which may diverge from
    the header's latest-conversation session index (design doc §2.2 Part A
    preamble, VP-003 S9-vs-S11 worked example)."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    administering_session_index: int | None = None
    administering_simulated_date: str | None = None
    is_stale_relative_to_header: bool = False
    scale_name: str | None = None
    item_bank_version: str | None = None
    item_bank_provenance: str | None = None
    responses: list[int] = Field(default_factory=list)
    total_score: int | None = None
    max_score: int | None = None
    severity: str | None = None
    critical_item_positive: bool | None = None
    administration_mode: str | None = None
    threshold_caveat: str | None = None
    threshold_caveat_asymmetry_note: str | None = None
    non_validated_caveat: str = Field(default=NON_VALIDATED_ADMINISTRATION_CAVEAT_KO)
    gap_disclosure: list[str] = Field(default_factory=list)
    gap_acuity_framing_note: str | None = None
    ceiling_caveat: str | None = Field(
        default=None,
        description=(
            "Set to CEILING_SCORE_CAVEAT_KO iff total_score == max_score "
            "(exact scale ceiling only, ADR-038 Decision 2c). None otherwise, "
            "including when present=False."
        ),
    )


# ── A6 (hard red line — own section, never merged elsewhere) ──────────────


class RankedDiseaseCandidate(BaseModel):
    """One A6 candidate + its co-rank position (`ADR-037` Decision 3 —
    tied `similarity_score` candidates share a rank, never an arbitrary
    #1/#2 ordering)."""

    model_config = ConfigDict(extra="forbid")

    candidate: AIPredictedDiseaseCandidate
    rank: int
    co_ranked: bool = False
    tie_marker: str | None = None


class AIPredictedDiseaseSection(BaseModel):
    """A6 — AI decision-support, non-diagnostic. HARD RED LINE: this is
    the ONLY field on `HandoffReportOutput` (transitively) capable of
    carrying an `AIPredictedDiseaseCandidate`/`RankedDiseaseCandidate`
    value — no other section type in this module has a field of either
    type."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    mode: Literal["experimental_unpopulated", "rag_live"] | None = None
    candidates: list[RankedDiseaseCandidate] = Field(default_factory=list)
    disclaimer: str | None = None
    recommended_questionnaire: str | None = None
    recommendation_caveat: str | None = None
    no_data_note: str | None = None
    reason_summary: str | None = Field(
        default=None,
        description=(
            "Surfaced verbatim from the source artifact's own "
            "AIPredictedDiseaseOutput.reason_summary (never invented here) "
            "ONLY when candidates is empty AND mode != 'rag_live' (ADR-038 "
            "Decision 2b, CVR-024 Finding 2/Recommendation 2) — e.g. "
            "explains an 'experimental_unpopulated' mode's own cause (no "
            "RAG chunks retrieved, or all candidate queries were "
            "risk-lexicon-rejected). None when candidates is non-empty, "
            "when mode == 'rag_live', or when the source artifact carried "
            "no reason_summary."
        ),
    )


# ── A7 ──────────────────────────────────────────────────────────────────


class DepartmentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: str
    reason: str
    domain_ref: str | None = None


class RecommendationSection(BaseModel):
    """A7 — recommended department / questionnaire, + medication disclosure
    (`ADR-037` Decision 5)."""

    model_config = ConfigDict(extra="forbid")

    department_candidates: list[DepartmentRecommendation] = Field(default_factory=list)
    department_candidates_absence_note: str | None = Field(
        default=None,
        description=(
            "Populated ONLY when department_candidates is empty -- "
            "A7_NO_CANDIDATES_VALIDATION_DROPPED_KO if the source "
            "domain_inference artifact carried non-empty validation_errors "
            "(VAL-016 lineage: an atomic Pydantic parse failure can silently "
            "collapse an already-valid department_candidates list), else "
            "A7_NO_CANDIDATES_MODEL_JUDGED_KO (ADR-038 Decision 2a). None "
            "when department_candidates is non-empty."
        ),
    )
    recommended_questionnaire: str | None = None
    recommendation_caveat: str | None = None
    medication_note: str = Field(default=MEDICATION_NOTE_KO)


# ── A8 (structurally disabled this mission, `ADR-037` Decision 1) ─────────


class NarrativeSection(BaseModel):
    """A8 — always rendered, either as an explicit disabled marker (this
    mission, `narrative_enabled=False`) or (future wave only) as narrative
    text. This model has NO field capable of holding an
    `AIPredictedDiseaseCandidate` — the A6 hard red line is structural, not
    merely a convention."""

    model_config = ConfigDict(extra="forbid")

    narrative_enabled: bool = False
    text: str | None = None
    absent_marker: str = Field(default=NARRATIVE_ABSENT_MARKER_KO)


# ── Part B (longitudinal, entirely from F4's own output) ──────────────────


class ChartReferences(BaseModel):
    """B5 — filename-only references to the 4 existing F4 PNGs (F5 never
    regenerates or reads chart bytes itself, design doc §2.2 B5 row)."""

    model_config = ConfigDict(extra="forbid")

    scales_ctrs_sentiment: str | None = None
    ctrs_zoom: str | None = None
    disease_similarity: str | None = None
    domain_confidence: str | None = None


class LongitudinalSection(BaseModel):
    """B1-B5 — consumes F4's `LongitudinalAnalysisOutput` verbatim (never
    recomputed, design doc §2.2 Part B preamble); `analysis.disclaimer`
    already carries VAL-014/evidence-필수 disclosures verbatim."""

    model_config = ConfigDict(extra="forbid")

    analysis: LongitudinalAnalysisOutput
    chart_filenames: ChartReferences = Field(default_factory=ChartReferences)
    overall_direction_sensitivity_note: str = Field(default=OVERALL_DIRECTION_SENSITIVITY_NOTE_KO)
    gap_acuity_framing_note: str | None = None


# ── Top-level container ────────────────────────────────────────────────


class HandoffReportOutput(BaseModel):
    """Container for the F5 production artifact
    (`<vp_id>_<ts>_handoff.{md,pdf,fhir.json}`). `extra="forbid"` — same
    discipline as every other F1-F4 production schema.
    `is_diagnostic: Literal[False]` fixed at the type level (hard red
    line 3, module docstring)."""

    model_config = ConfigDict(extra="forbid")

    vp_id: str
    generated_at: str = ""
    is_diagnostic: Literal[False] = False
    disclaimer: str = Field(default=HANDOFF_REPORT_DISCLAIMER_KO)

    a0_header: HeaderSection
    a1_chief_complaint: ChiefComplaintSection
    a2_hpi: HistoryOfPresentIllnessSection
    slot_overview: SlotOverviewSection
    a3_risk_safety: RiskSafetySection
    a4_mental_status: MentalStatusSection
    a5_questionnaires: QuestionnaireSection
    a6_ai_predicted_disease: AIPredictedDiseaseSection
    a7_recommendations: RecommendationSection
    a8_narrative: NarrativeSection

    b_longitudinal: LongitudinalSection
