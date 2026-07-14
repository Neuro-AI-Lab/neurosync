"""F5 — clinical hand-off report assembly (production engine).

`docs/ai/f5_quick_dev_plan.md` §2/§4, `PLAN-2026-W29-E`, `ADR-037`. This
module is architected exactly like `f1.py`/`f2.py`/`f3.py`/`f4.py`: a
standalone module invocable by a harness that has already assembled every
input from F1-F4 artifacts — never a route, never wired into
`orchestrator.py`.

`assemble_handoff_report` is a PURE, 100% deterministic, ZERO-LLM function
over an explicit `HandoffReportInput` a caller has already built from F1-F4
artifacts. Per `REV-044` Criterion 6 (citation corrected from the plan's
own `REV-022` mis-citation, `REV-046` Issue 6 / `ADR-037` Decision 6): this
module performs ZERO direct filesystem access and ZERO harness/test-tree
imports — it never reads the session ledger, never reads a
`conversation.json`/`domain_inference.json`/`survey.json`/`temporal.json`
path itself. Reading those artifacts and building the typed inputs below is
the harness's own job, entirely outside this module; WRITING this module's
own output artifact (`_handoff.md`/`.pdf`/`_fhir.json`) is
`src/services/f5_report.py` — same deliberate split `f4.py`/`f4_report.py`
already establish, kept out of this module specifically so a whole-file
grep for `open(` on this file returns 0 hits with zero ambiguity.

Narrative section (A8): DESCOPED this mission (`ADR-037` Decision 1).
`assemble_handoff_report` raises `ValueError` if `HandoffReportInput.
narrative_enabled` is `True` — no code path in this module ever calls
`HandoffGeneratorAgent`/`EvidenceVerifierAgent`, and no code path in this
module ever imports `src.agents.handoff_generator` or
`src.schemas.handoff`. A8 always ships as an explicit disabled marker
(`schemas.handoff_report.NarrativeSection.absent_marker`), never silently
blank.

Every number this module renders is CONSUMED from an already-computed F1-F4
field, never a new clinical judgment: banding/severity/CTRS-risk-level/
trend-verdict/course-shape values are looked up or juxtaposed (e.g. the A3
same-session item-9-vs-CTRS discordance note, which only compares two
already-computed fields — F3's `safety_referral` against F4's own
`ctrs_series` point for that same `session_index`), never recomputed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime
from typing import Literal

from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.common import CTRS_TO_RISK, CTRSLevel
from src.schemas.handoff_report import (
    CRISIS_F3_GAP_ACUITY_FRAMING_KO,
    GAD7_THRESHOLD_CAVEAT_ASYMMETRY_NOTE_KO,
    MSE_FLAT_TEXT_LABEL_KO,
    MSE_OBSERVATION_DEPENDENT_DOMAINS,
    MSE_OBSERVATION_DEPENDENT_NOTE_KO,
    MSE_TEXT_DERIVABLE_DOMAINS,
    MSE_TEXT_DERIVABLE_NOTE_KO,
    NON_VALIDATED_ADMINISTRATION_CAVEAT_KO,
    AIPredictedDiseaseSection,
    ChartReferences,
    ChiefComplaintSection,
    DepartmentRecommendation,
    HandoffReportOutput,
    HeaderDisclaimer,
    HeaderSection,
    HistoryOfPresentIllnessSection,
    LongitudinalRiskSignal,
    LongitudinalSection,
    MentalStatusSection,
    MSEDomainStatus,
    NarrativeSection,
    QuestionnaireSection,
    RankedDiseaseCandidate,
    RecommendationSection,
    RiskSafetySection,
    StalenessPointer,
)
from src.schemas.longitudinal import LongitudinalAnalysisOutput

# ── Harness -> production contract (design doc §4.1) ────────────────────


@dataclass(frozen=True)
class SessionSnapshot:
    """The LATEST session's own F1 record fields — Part A's "latest
    session" rule for A0-A2/A4/A6-A8 (design doc §2.2 preamble). The
    harness builds this from that session's `conversation.json` top-level
    fields; this module never re-resolves any of it from a file path."""

    session_id: str
    persona_id: str
    persona_name: str
    session_index: int
    simulated_date: str
    model: str
    final_slots: dict[str, str]
    session_ctrs: int | None
    crisis_triggered: bool
    crisis_turn: int | None
    risk_floor: int | None
    probe_event_count: int


@dataclass(frozen=True)
class F3Administration:
    """One session's F3 `survey.json` record (any outcome). The harness
    supplies one per session across the WHOLE VP arc (`all_f3_
    administrations`) plus, separately, the one matching the header
    session (`current_session_f3`, may be `None`)."""

    session_index: int
    simulated_date: str
    outcome: Literal["administered", "no_questionnaire_indicated", "item_bank_unpopulated"]
    scale_name: str | None = None
    item_bank_version: str | None = None
    item_bank_provenance: str | None = None
    responses: tuple[int, ...] = ()
    total_score: int | None = None
    max_score: int | None = None
    severity: str | None = None
    critical_item_positive: bool | None = None
    safety_referral: bool = False
    administration_mode: Literal["natural", "forced"] = "natural"
    threshold_caveat: str | None = None


@dataclass(frozen=True)
class DepartmentCandidateInput:
    """Mirrors `schemas.domain_inference.DepartmentCandidate`'s 3 fields as
    a plain dataclass — this module never imports `schemas.domain_
    inference` itself (isolation invariant, module docstring)."""

    department: str
    reason: str
    domain_ref: str | None = None


@dataclass(frozen=True)
class DomainInferenceSnapshot:
    """The LATEST session's F2 artifact content — `ai_predicted_disease`
    (A6) + `department_candidates` (A7)."""

    ai_predicted_disease: AIPredictedDiseaseOutput | None
    department_candidates: tuple[DepartmentCandidateInput, ...] = ()


@dataclass(frozen=True)
class ChartFilenames:
    """B5 — filename-only (no paths, no bytes); this module never reads or
    generates chart bytes (design doc §2.2 B5 row)."""

    scales_ctrs_sentiment: str | None = None
    ctrs_zoom: str | None = None
    disease_similarity: str | None = None
    domain_confidence: str | None = None


@dataclass(frozen=True)
class HandoffReportInput:
    """Everything `assemble_handoff_report` needs, already resolved by the
    caller. `all_f3_administrations` must be caller-sorted by
    non-decreasing `session_index` (not re-validated here — F3
    administrations are usually few and the A3/A5 lookups below are
    order-independent max/filter operations, unlike F4's own strict
    monotonic-sort requirement over a much longer per-turn series)."""

    vp_id: str
    session: SessionSnapshot
    current_session_f3: F3Administration | None
    all_f3_administrations: tuple[F3Administration, ...]
    domain_inference: DomainInferenceSnapshot
    longitudinal: LongitudinalAnalysisOutput
    chart_filenames: ChartFilenames = field(default_factory=ChartFilenames)
    narrative_enabled: bool = False


# ── Shared helpers ─────────────────────────────────────────────────────

_GAP_SESSION_RE = re.compile(r"session (\d+)")


def _ctrs_risk_level(session_ctrs: int | None) -> str | None:
    """Reuses `CTRS_TO_RISK` verbatim (`common.py:33-39`) — zero new
    risk-banding logic, same discipline A0's design doc row requires."""
    if session_ctrs is None:
        return None
    try:
        return CTRS_TO_RISK[CTRSLevel(session_ctrs)].value
    except ValueError:
        return None


def _truncate_one_line(text: str, max_len: int = 80) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    first_line = stripped.splitlines()[0]
    if len(first_line) > max_len:
        return first_line[:max_len].rstrip() + "…"
    return first_line


def _parse_iso_date(value: str) -> _date | None:
    try:
        return _date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _days_between(earlier: str, later: str) -> int | None:
    d1, d2 = _parse_iso_date(earlier), _parse_iso_date(later)
    if d1 is None or d2 is None:
        return None
    return (d2 - d1).days


def _risk_elevated(session_ctrs: int | None, crisis_triggered: bool) -> bool:
    """Same rule `src.f4._crisis_f3_gap_notes` already uses (reused
    verbatim, never a new threshold): risk-elevated iff crisis-triggered OR
    `session_ctrs <= 2` (`CTRSLevel.HIGH_RISK`/`EMERGENCY`)."""
    return crisis_triggered or (session_ctrs is not None and session_ctrs <= 2)


def _relevant_gaps(
    gaps: list[str], after_session_index: int, up_to_session_index: int
) -> list[str]:
    """`crisis_f3_gaps` entries (carried verbatim from F4) whose parsed
    session index falls strictly after `after_session_index` and up to
    (inclusive) `up_to_session_index`."""
    out: list[str] = []
    for g in gaps:
        m = _GAP_SESSION_RE.search(g)
        if not m:
            continue
        idx = int(m.group(1))
        if after_session_index < idx <= up_to_session_index:
            out.append(g)
    return out


# ── A0 ──────────────────────────────────────────────────────────────────


def _build_header(inp: HandoffReportInput) -> HeaderSection:
    s = inp.session
    cc = s.final_slots.get("chief_complaint")
    return HeaderSection(
        session_id=s.session_id,
        persona_id=s.persona_id,
        persona_name=s.persona_name,
        session_index=s.session_index,
        simulated_date=s.simulated_date,
        model=s.model,
        chief_complaint_summary=_truncate_one_line(cc) if cc else None,
        session_ctrs=s.session_ctrs,
        risk_level=_ctrs_risk_level(s.session_ctrs),
        crisis_triggered=s.crisis_triggered,
        crisis_turn=s.crisis_turn,
        disclaimer=HeaderDisclaimer(),
    )


# ── A1 / A2 ────────────────────────────────────────────────────────────


def _build_a1(inp: HandoffReportInput) -> ChiefComplaintSection:
    text = inp.session.final_slots.get("chief_complaint")
    return ChiefComplaintSection(present=bool(text), text=text)


def _build_a2(inp: HandoffReportInput) -> HistoryOfPresentIllnessSection:
    text = inp.session.final_slots.get("history_of_present_illness")
    return HistoryOfPresentIllnessSection(present=bool(text), text=text)


# ── A3 ──────────────────────────────────────────────────────────────────


def _build_staleness_pointer(inp: HandoffReportInput, current_has_f3: bool) -> StalenessPointer:
    header_idx = inp.session.session_index
    if current_has_f3:
        return StalenessPointer(
            applicable=False,
            note="당해 세션에 F3 문진이 시행되어 별도 최신성 안내가 필요하지 않습니다.",
        )
    administered = [
        a
        for a in inp.all_f3_administrations
        if a.outcome == "administered" and a.session_index < header_idx
    ]
    if not administered:
        return StalenessPointer(
            applicable=True,
            note=(
                "당해 세션에 F3 문진이 시행되지 않았고, 이 환자의 이전 세션 중에도 "
                "시행된 문진 이력이 없습니다 — 참조할 과거 척도 결과가 없습니다."
            ),
        )
    latest = max(administered, key=lambda a: a.session_index)
    sessions_stale = header_idx - latest.session_index
    days_stale = _days_between(latest.simulated_date, inp.session.simulated_date)
    note = (
        f"당해 세션({header_idx}회차, {inp.session.simulated_date})에는 F3 문진이 "
        f"시행되지 않았습니다. 가장 최근 시행된 척도는 {latest.session_index}회차"
        f"({latest.simulated_date}) {latest.scale_name} {latest.total_score}/"
        f"{latest.max_score}점({latest.severity})이며, safety_referral="
        f"{latest.safety_referral}, critical_item_positive={latest.critical_item_positive}"
        f"입니다. {sessions_stale}회차"
        + (f"({days_stale}일)" if days_stale is not None else "")
        + " 경과된 결과입니다."
    )
    return StalenessPointer(
        applicable=True,
        latest_scored_session_index=latest.session_index,
        latest_scored_simulated_date=latest.simulated_date,
        scale_name=latest.scale_name,
        total_score=latest.total_score,
        max_score=latest.max_score,
        severity=latest.severity,
        safety_referral=latest.safety_referral,
        critical_item_positive=latest.critical_item_positive,
        sessions_stale=sessions_stale,
        days_stale=days_stale,
        note=note,
    )


def _build_a3(inp: HandoffReportInput) -> RiskSafetySection:
    s = inp.session
    current_f3 = inp.current_session_f3
    has_f3 = current_f3 is not None and current_f3.outcome == "administered"

    ctrs_by_session = {p.session_index: p for p in inp.longitudinal.ctrs_series}

    signals: list[LongitudinalRiskSignal] = []
    for admin in inp.all_f3_administrations:
        if admin.outcome != "administered":
            continue
        flagged = bool(admin.critical_item_positive) or bool(admin.safety_referral)
        if not flagged:
            continue
        ctrs_point = ctrs_by_session.get(admin.session_index)
        same_ctrs = ctrs_point.session_ctrs if ctrs_point else None
        same_crisis = ctrs_point.crisis_triggered if ctrs_point else False
        if ctrs_point is None:
            note = "확인 불가 — 동일 세션 CTRS 데이터 없음"
        elif _risk_elevated(same_ctrs, same_crisis):
            note = (
                f"일치 — 동일 세션 CTRS도 위험 상승(session_ctrs={same_ctrs}, "
                f"crisis_triggered={same_crisis})"
            )
        else:
            note = (
                f"불일치 — 동일 세션 CTRS 미상승(session_ctrs={same_ctrs}, "
                f"crisis_triggered={same_crisis}), 항목9 양성/safety_referral 신호가 "
                "F1 CTRS에 반영되지 않음 (CVR-022 binding condition 2)"
            )
        signals.append(
            LongitudinalRiskSignal(
                session_index=admin.session_index,
                simulated_date=admin.simulated_date,
                scale_name=admin.scale_name,
                total_score=admin.total_score,
                max_score=admin.max_score,
                severity=admin.severity,
                safety_referral=admin.safety_referral,
                critical_item_positive=admin.critical_item_positive,
                same_session_ctrs=same_ctrs,
                same_session_crisis_triggered=same_crisis,
                discordance_note=note,
            )
        )

    return RiskSafetySection(
        current_session_index=s.session_index,
        current_simulated_date=s.simulated_date,
        risk_assessment_present=bool(s.final_slots.get("risk_assessment")),
        risk_assessment_text=s.final_slots.get("risk_assessment"),
        session_ctrs=s.session_ctrs,
        risk_level=_ctrs_risk_level(s.session_ctrs),
        risk_floor=s.risk_floor,
        probe_event_count=s.probe_event_count,
        crisis_triggered=s.crisis_triggered,
        crisis_turn=s.crisis_turn,
        current_session_has_f3=has_f3,
        current_session_safety_referral=current_f3.safety_referral if current_f3 else None,
        current_session_critical_item_positive=(
            current_f3.critical_item_positive if current_f3 else None
        ),
        longitudinal_risk_signals=signals,
        trend_concordance_flag=inp.longitudinal.concordance_flag,
        staleness_pointer=_build_staleness_pointer(inp, has_f3),
    )


# ── A4 ──────────────────────────────────────────────────────────────────


def _build_a4(inp: HandoffReportInput) -> MentalStatusSection:
    raw = inp.session.final_slots.get("mental_status_exam")
    checklist = [
        MSEDomainStatus(domain=d, assessable=False, note=MSE_TEXT_DERIVABLE_NOTE_KO)
        for d in MSE_TEXT_DERIVABLE_DOMAINS
    ] + [
        MSEDomainStatus(domain=d, assessable=False, note=MSE_OBSERVATION_DEPENDENT_NOTE_KO)
        for d in MSE_OBSERVATION_DEPENDENT_DOMAINS
    ]
    return MentalStatusSection(
        present=bool(raw), raw_text=raw, label=MSE_FLAT_TEXT_LABEL_KO, domain_checklist=checklist
    )


# ── A5 ──────────────────────────────────────────────────────────────────


def _build_a5(inp: HandoffReportInput) -> QuestionnaireSection:
    administered = [a for a in inp.all_f3_administrations if a.outcome == "administered"]
    if not administered:
        return QuestionnaireSection(
            present=False, non_validated_caveat=NON_VALIDATED_ADMINISTRATION_CAVEAT_KO
        )

    latest = max(administered, key=lambda a: a.session_index)
    header_idx = inp.session.session_index
    is_stale = latest.session_index != header_idx
    gap_notes = _relevant_gaps(inp.longitudinal.crisis_f3_gaps, latest.session_index, header_idx)

    asymmetry_note = None
    if latest.scale_name == "GAD-7" and latest.threshold_caveat is None:
        asymmetry_note = GAD7_THRESHOLD_CAVEAT_ASYMMETRY_NOTE_KO

    return QuestionnaireSection(
        present=True,
        administering_session_index=latest.session_index,
        administering_simulated_date=latest.simulated_date,
        is_stale_relative_to_header=is_stale,
        scale_name=latest.scale_name,
        item_bank_version=latest.item_bank_version,
        item_bank_provenance=latest.item_bank_provenance,
        responses=list(latest.responses),
        total_score=latest.total_score,
        max_score=latest.max_score,
        severity=latest.severity,
        critical_item_positive=latest.critical_item_positive,
        administration_mode=latest.administration_mode,
        threshold_caveat=latest.threshold_caveat,
        threshold_caveat_asymmetry_note=asymmetry_note,
        non_validated_caveat=NON_VALIDATED_ADMINISTRATION_CAVEAT_KO,
        gap_disclosure=gap_notes,
        gap_acuity_framing_note=CRISIS_F3_GAP_ACUITY_FRAMING_KO if gap_notes else None,
    )


# ── A6 (hard red line — own section) ──────────────────────────────────────


def _rank_candidates(
    candidates: list[AIPredictedDiseaseCandidate],
) -> list[RankedDiseaseCandidate]:
    """`ADR-037` Decision 3 tie-handling: standard competition ranking —
    candidates sharing an identical `similarity_score` share a rank
    (co-ranked), never an arbitrary #1/#2 split. Original F2 order is
    preserved (never re-sorted), same discipline `f4.py`'s own disease
    series builder states for itself."""
    scores = [c.similarity_score for c in candidates]
    ranked: list[RankedDiseaseCandidate] = []
    for c in candidates:
        rank = 1 + sum(1 for other in scores if other > c.similarity_score)
        tie_count = sum(1 for other in scores if other == c.similarity_score)
        co_ranked = tie_count > 1
        ranked.append(
            RankedDiseaseCandidate(
                candidate=c,
                rank=rank,
                co_ranked=co_ranked,
                tie_marker=f"공동 {rank}위" if co_ranked else None,
            )
        )
    return ranked


def _build_a6(inp: HandoffReportInput) -> AIPredictedDiseaseSection:
    apd = inp.domain_inference.ai_predicted_disease
    if apd is None or not apd.candidates:
        return AIPredictedDiseaseSection(
            present=False,
            mode=apd.mode if apd else None,
            disclaimer=apd.disclaimer if apd else None,
            no_data_note="정보 없음 (AI 예상질환 후보 없음)",
        )
    return AIPredictedDiseaseSection(
        present=True,
        mode=apd.mode,
        candidates=_rank_candidates(apd.candidates),
        disclaimer=apd.disclaimer,
        recommended_questionnaire=apd.recommended_questionnaire,
        recommendation_caveat=apd.recommendation_caveat,
    )


# ── A7 ──────────────────────────────────────────────────────────────────


def _build_a7(inp: HandoffReportInput) -> RecommendationSection:
    depts = [
        DepartmentRecommendation(department=d.department, reason=d.reason, domain_ref=d.domain_ref)
        for d in inp.domain_inference.department_candidates
    ]
    apd = inp.domain_inference.ai_predicted_disease
    return RecommendationSection(
        department_candidates=depts,
        recommended_questionnaire=apd.recommended_questionnaire if apd else None,
        recommendation_caveat=apd.recommendation_caveat if apd else None,
    )


# ── A8 (structurally disabled this mission) ──────────────────────────────


def _build_a8(inp: HandoffReportInput) -> NarrativeSection:
    return NarrativeSection(narrative_enabled=False, text=None)


# ── Part B (longitudinal, entirely from F4's own output) ──────────────────


def _build_b(inp: HandoffReportInput) -> LongitudinalSection:
    charts = ChartReferences(
        scales_ctrs_sentiment=inp.chart_filenames.scales_ctrs_sentiment,
        ctrs_zoom=inp.chart_filenames.ctrs_zoom,
        disease_similarity=inp.chart_filenames.disease_similarity,
        domain_confidence=inp.chart_filenames.domain_confidence,
    )
    return LongitudinalSection(
        analysis=inp.longitudinal,
        chart_filenames=charts,
        gap_acuity_framing_note=(
            CRISIS_F3_GAP_ACUITY_FRAMING_KO if inp.longitudinal.crisis_f3_gaps else None
        ),
    )


# ── Public entry point ────────────────────────────────────────────────────


def assemble_handoff_report(inp: HandoffReportInput) -> HandoffReportOutput:
    """Pure, deterministic, ZERO-LLM hand-off report assembly over an
    explicit input a harness has already built from F1-F4 artifacts
    (design doc §4, `ADR-037`).

    Raises `ValueError` if `inp.narrative_enabled` is `True` — the
    narrative path (A8) is descoped this mission (`ADR-037` Decision 1);
    no code path in this module ever calls `HandoffGeneratorAgent`.
    """
    if inp.narrative_enabled:
        raise ValueError(
            "HandoffReportInput.narrative_enabled=True is not supported this mission "
            "(ADR-037 Decision 1) — the narrative path (A8) is descoped; src.f5 makes "
            "zero LLM calls. Set narrative_enabled=False."
        )

    return HandoffReportOutput(
        vp_id=inp.vp_id,
        generated_at=datetime.now().isoformat(),
        a0_header=_build_header(inp),
        a1_chief_complaint=_build_a1(inp),
        a2_hpi=_build_a2(inp),
        a3_risk_safety=_build_a3(inp),
        a4_mental_status=_build_a4(inp),
        a5_questionnaires=_build_a5(inp),
        a6_ai_predicted_disease=_build_a6(inp),
        a7_recommendations=_build_a7(inp),
        a8_narrative=_build_a8(inp),
        b_longitudinal=_build_b(inp),
    )
