"""F5 — clinical hand-off report assembly (production engine).

`_archive/plans/f5_quick_dev_plan.md` §2/§4, `PLAN-2026-W29-E`, `ADR-037`. This
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

Narrative section (A8): OFF BY DEFAULT (`ADR-037` Decision 1,
`narrative_enabled=False`). A future-mission addition (Task 2 /
`handoff_generator` v3) makes it an OPT-IN path, never a call this module
makes itself: `assemble_handoff_report` still raises `ValueError` if
`HandoffReportInput.narrative_enabled=True` and `narrative_text` is
empty/absent — no code path in this module ever calls
`HandoffGeneratorAgent`/`EvidenceVerifierAgent`, and no code path in this
module ever imports `src.agents.handoff_generator` or `src.schemas.
handoff`. When `narrative_enabled=True` WITH a non-empty caller-supplied
`narrative_text`, `_build_a8` renders it verbatim UNLESS it contains any
A6 candidate's `disease` name (a pure string check, still zero LLM calls),
in which case it refuses and ships a distinct rejection marker instead. A8
always ships an explicit marker either way, never silently blank.

Every number this module renders is CONSUMED from an already-computed F1-F4
field, never a new clinical judgment: banding/severity/CTRS-risk-level/
trend-verdict/course-shape values are looked up or juxtaposed (e.g. the A3
same-session item-9-vs-CTRS discordance note, which only compares two
already-computed fields — F3's `safety_referral` against F4's own
`ctrs_series` point for that same `session_index`), never recomputed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime
from typing import Literal

from src.grounding import reply_has_negation
from src.schemas.ai_predicted_disease import AIPredictedDiseaseCandidate, AIPredictedDiseaseOutput
from src.schemas.common import CTRS_TO_RISK, CTRSLevel
from src.schemas.handoff_report import (
    A7_NO_CANDIDATES_MODEL_JUDGED_KO,
    A7_NO_CANDIDATES_VALIDATION_DROPPED_KO,
    CANONICAL_SLOT_KEYS,
    CEILING_SCORE_CAVEAT_KO,
    CRISIS_F3_GAP_ACUITY_FRAMING_KO,
    GAD7_THRESHOLD_CAVEAT_ASYMMETRY_NOTE_KO,
    MSE_FLAT_TEXT_LABEL_KO,
    MSE_OBSERVATION_DEPENDENT_DOMAINS,
    MSE_OBSERVATION_DEPENDENT_NOTE_KO,
    MSE_TEXT_DERIVABLE_DOMAINS,
    MSE_TEXT_DERIVABLE_NOTE_KO,
    NARRATIVE_REJECTED_DISEASE_LEAK_KO,
    NON_VALIDATED_ADMINISTRATION_CAVEAT_KO,
    SLOT_SECTION_POINTERS_KO,
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
    SlotOverviewRow,
    SlotOverviewSection,
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
class SessionSlotSnapshot:
    """One session's `final_slots` dict, across the WHOLE VP arc (Task 1,
    all-session slot maximization) — the harness supplies one per ledger
    entry, NOT only the header/latest session (contrast `SessionSnapshot`
    above, which is latest-session-only by Part A's own design). Used
    exclusively to build the all-session `SlotOverviewSection`; every other
    section keeps reading `SessionSnapshot.final_slots` (the header
    session) unchanged."""

    session_index: int
    simulated_date: str
    final_slots: dict[str, str]


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
    (A6) + `department_candidates` (A7).

    `validation_errors_present` (`ADR-038` Decision 2a / `VAL-016`):
    whether the SOURCE `domain_inference.json` artifact carried a
    non-empty top-level `validation_errors` field — an atomic Pydantic
    parse failure on `domain_candidates`/`department_candidates` (e.g. a
    missing-`source_id` evidence item) can silently collapse an
    ALREADY-VALID `department_candidates` list to `[]`. This flag is the
    harness-supplied fact A7's rendering needs to distinguish that from a
    genuine model judgment of "no department to recommend" — `src.f5`
    itself never reads `domain_inference.json` (module docstring), so the
    harness (`continuous_test.py`) computes this from the same artifact it
    already reads to build `department_candidates` below."""

    ai_predicted_disease: AIPredictedDiseaseOutput | None
    department_candidates: tuple[DepartmentCandidateInput, ...] = ()
    validation_errors_present: bool = False


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
    # Task 1 — all-session slot maximization. Caller-sorted by non-
    # decreasing `session_index` (same non-re-validated discipline as
    # `all_f3_administrations` above). SHOULD include an entry for the
    # header session too (`_build_slot_overview` below falls back to
    # synthesizing one from `session.final_slots` alone when empty, so
    # existing/older callers that never set this keep working unchanged).
    all_sessions: tuple[SessionSlotSnapshot, ...] = ()
    narrative_enabled: bool = False
    # Task 2 (`handoff_generator` v3) — an ALREADY-GENERATED narrative
    # string the caller obtained externally (e.g.
    # `HandoffGeneratorAgent.generate_narrative`, `src/services/f5_report.
    # py::build_narrative_input_text`) — `src.f5` itself never calls that
    # agent (module docstring's zero-LLM invariant, unchanged). Required
    # (non-empty) whenever `narrative_enabled=True`; ignored otherwise.
    narrative_text: str | None = None


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


def _flatten_full(text: str) -> str:
    """Collapses internal newlines/repeated whitespace to single spaces,
    NEVER character-truncates (CVR-026 Finding 1/2: `SlotOverviewRow.
    latest_value` is the renderer's own source of truth for a slot's full
    text — a 상세 부록 appendix entry built from an already-160-char-capped
    `latest_value` would still be a dead-end truncation, just moved one
    layer down). Table-cell-safe compaction (removing the newline, which a
    markdown/PDF table cell cannot safely contain) still happens — only the
    LENGTH cap is gone; the renderer applies its OWN 80-char compact-cell
    truncation on top of this at render time, with a real appendix pointer."""
    return " ".join(text.split())


def _flatten_for_cell(text: str, max_len: int = 160) -> str:
    """Collapses internal newlines/repeated whitespace to single spaces
    (never drops content after the first line, unlike `_truncate_one_line`
    above) then truncates to `max_len` — a markdown/PDF TABLE CELL cannot
    safely contain a literal newline, but the all-session slot table
    (Task 1) still wants as much of a long free-text slot value visible as
    fits, not just its first line."""
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    if len(collapsed) > max_len:
        return collapsed[:max_len].rstrip() + "…"
    return collapsed


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


# CVR-028 (near-ceiling caveat coverage, major): `ADR-038` Decision 2c /
# `CVR-024` Finding 4 originally scoped this to EXACT scale-ceiling only
# ("no near-ceiling threshold judgment is computed here") — CVR-028
# extends coverage to scores within `_NEAR_CEILING_CAVEAT_MARGIN` point(s)
# of max (e.g. PHQ-9 26/27), the same over-endorsement risk
# (`ISS-F2V-028`) is not meaningfully different one point off the ceiling.
_NEAR_CEILING_CAVEAT_MARGIN = 1


def _ceiling_caveat(total_score: int | None, max_score: int | None) -> str | None:
    """CVR-028 remediation of `ADR-038` Decision 2c / `CVR-024` Finding 4:
    within `_NEAR_CEILING_CAVEAT_MARGIN` point(s) of `max_score` (both
    present) now also triggers this caveat, not only an EXACT match.
    Returns the verbatim `CEILING_SCORE_CAVEAT_KO` excerpt of
    `schemas.longitudinal.LONGITUDINAL_DISCLAIMER_KO`'s own
    over-endorsement sentence, or `None`."""
    if total_score is None or max_score is None:
        return None
    if total_score >= max_score - _NEAR_CEILING_CAVEAT_MARGIN:
        return CEILING_SCORE_CAVEAT_KO
    return None


# CVR-028 Finding 4 (major, VP-010): F1's own `_compose_probe_risk_assessment`/
# `_compose_screen_risk_assessment` (`src.f1`) prefix a composed
# `risk_assessment` slot value with a categorical label at COMPOSE time
# (session of the actual probe/screen event) — that label then rides
# UNCHANGED inside the slot's carried-forward text across every later
# session that never re-triggers a new probe (VP-010: labeled "자살/자해
# 사고 표현 있음" from S3 through S10), even when the CURRENT session's own
# quoted patient utterance directly under that label is an explicit denial.
# A clinician reading only the summary-table/SBAR-box row sees an
# SI-positive categorical label directly contradicted by its own cited
# evidence text.
#
# Fix scope, deliberately narrow (never a new clinical judgment/diagnosis,
# `f5.py`'s own module-level invariant): this checks ONLY whether the FIRST
# quoted "환자 발화: "..."" segment immediately following the "표현 있음"
# label contains a negation/denial morpheme, via the SAME deterministic,
# already-tested pattern `src.grounding.reply_has_negation` uses everywhere
# else in this codebase (F1's own compose functions call it too) — no new
# lexicon, no new free-text semantic parsing invented for this fix. When it
# matches, the DISPLAY label is corrected to "자살사고 부인(탐색 완료)"; the
# underlying quoted text is never altered/redacted, only the categorical
# framing shown alongside it.
_SI_EXPRESSED_LABEL_KO = "자살/자해 사고 표현 있음"
_SI_DENIAL_RELABEL_KO = "자살사고 부인(탐색 완료)"
_FIRST_QUOTE_AFTER_LABEL_RE = re.compile(r'환자\s*발화\s*:\s*"([^"]*)"')


def _relabel_risk_assessment_text(text: str | None) -> str | None:
    """Correct a stale/content-contradicted "표현 있음" categorical prefix
    on a `risk_assessment` slot value, per CVR-028 Finding 4.

    Only touches text that literally starts with `_SI_EXPRESSED_LABEL_KO`
    (F1's own compose-time label, the exact known collision shape — never a
    blanket rewrite of arbitrary risk_assessment prose) AND whose first
    quoted "환자 발화: "..."" segment matches `reply_has_negation`. Anything
    else (no label prefix, no quote to check, or a quote that is NOT a
    denial) is returned unchanged — this function never invents content,
    only relabels a prefix already proven content-inconsistent.
    """
    if text is None or not text.startswith(_SI_EXPRESSED_LABEL_KO):
        return text
    match = _FIRST_QUOTE_AFTER_LABEL_RE.search(text)
    if match is None:
        return text
    quoted = match.group(1)
    if not quoted or not reply_has_negation(quoted):
        return text
    return _SI_DENIAL_RELABEL_KO + text[len(_SI_EXPRESSED_LABEL_KO) :]


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


# ── All-session slot overview (Task 1) ────────────────────────────────────


def _slot_history_sessions(inp: HandoffReportInput) -> list[SessionSlotSnapshot]:
    """`inp.all_sessions`, sorted ascending by `session_index` — falls back
    to a single synthetic entry built from the header session alone when
    the caller never populated `all_sessions` (older/toy callers), so
    existing fixtures/tests keep behaving exactly as before this addition."""
    if inp.all_sessions:
        return sorted(inp.all_sessions, key=lambda s: s.session_index)
    s = inp.session
    return [SessionSlotSnapshot(s.session_index, s.simulated_date, s.final_slots)]


def _slot_row(key: str, label: str, sessions: list[SessionSlotSnapshot]) -> SlotOverviewRow:
    """One canonical slot's best-available value across `sessions`: the
    LATEST non-empty value + its provenance, plus a compact change-history
    line built from every DISTINCT non-empty value in chronological order
    (consecutive duplicates collapsed — a slot re-stated identically across
    3 sessions is not a "change"). `change_history` stays empty when the
    slot was never filled, or was filled with the same value every time.

    `risk_assessment` (CVR-028 Finding 4): each session's raw value passes
    through `_relabel_risk_assessment_text` BEFORE the latest/distinct-value
    computation below, so a per-session stale "표현 있음" label that its own
    quoted content contradicts is corrected in both `latest_value` and every
    `change_history`/`change_history_full` entry, not only the current-
    session A3 narrative. Every other slot key is unaffected (identity
    passthrough)."""
    relabel = _relabel_risk_assessment_text if key == "risk_assessment" else (lambda v: v)
    filled = [
        (s.session_index, s.simulated_date, relabel(v))
        for s in sessions
        if (v := s.final_slots.get(key))
    ]
    if not filled:
        return SlotOverviewRow(
            key=key,
            label=label,
            collected=False,
            section_pointer=SLOT_SECTION_POINTERS_KO.get(key),
        )

    distinct: list[tuple[int, str, str]] = []
    for idx, date, value in filled:
        if not distinct or distinct[-1][2] != value:
            distinct.append((idx, date, value))

    latest_idx, latest_date, latest_value = distinct[-1]
    change_history: list[str] = []
    change_history_full: list[str] = []
    if len(distinct) > 1:
        change_history = [
            f"S{idx}: '{_flatten_for_cell(value, 60)}'" for idx, _date, value in distinct
        ]
        # CVR-026 Finding 1/2: `change_history` above is a 60-char-per-entry
        # COMPACT preview for the slot table cell — this parallel field
        # keeps the same (session, value) points whitespace-flattened only
        # (never character-truncated), so the renderer's 상세 부록 (detail
        # appendix) can restore the full quote a clinician would otherwise
        # never see (e.g. an S1 precipitant/symptom mentioned only once,
        # early in the arc).
        change_history_full = [
            f"S{idx}: '{' '.join(value.split())}'" for idx, _date, value in distinct
        ]

    return SlotOverviewRow(
        key=key,
        label=label,
        collected=True,
        latest_value=_flatten_full(latest_value),
        source_session_index=latest_idx,
        source_simulated_date=latest_date,
        change_history=change_history,
        change_history_full=change_history_full,
        section_pointer=SLOT_SECTION_POINTERS_KO.get(key),
    )


def _build_slot_overview(inp: HandoffReportInput) -> SlotOverviewSection:
    sessions = _slot_history_sessions(inp)
    rows = [_slot_row(key, label, sessions) for key, label in CANONICAL_SLOT_KEYS]
    return SlotOverviewSection(rows=rows)


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
        ceiling_caveat=_ceiling_caveat(latest.total_score, latest.max_score),
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
                ceiling_caveat=_ceiling_caveat(admin.total_score, admin.max_score),
            )
        )

    return RiskSafetySection(
        current_session_index=s.session_index,
        current_simulated_date=s.simulated_date,
        risk_assessment_present=bool(s.final_slots.get("risk_assessment")),
        risk_assessment_text=_relabel_risk_assessment_text(s.final_slots.get("risk_assessment")),
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
        ceiling_caveat=_ceiling_caveat(latest.total_score, latest.max_score),
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
        # `ADR-038` Decision 2b / `CVR-024` Finding 2, Recommendation 2:
        # surface the artifact's OWN already-computed reason_summary
        # (never invented here) whenever candidates is empty AND the mode
        # is not "rag_live" — e.g. `mode="experimental_unpopulated"`
        # explains itself ("no RAG chunks retrieved this run" / all
        # candidate queries risk-lexicon-rejected). Excluded for
        # `mode="rag_live"` per the same decision: a live RAG run that
        # genuinely found nothing is a materially different (less
        # ambiguous) case than an unpopulated run.
        reason_summary = None
        if apd is not None and apd.mode != "rag_live" and apd.reason_summary:
            reason_summary = apd.reason_summary
        return AIPredictedDiseaseSection(
            present=False,
            mode=apd.mode if apd else None,
            disclaimer=apd.disclaimer if apd else None,
            no_data_note="정보 없음 (AI 예상질환 후보 없음)",
            reason_summary=reason_summary,
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
    # `ADR-038` Decision 2a / `VAL-016`: when no department candidates
    # survived, distinguish a genuine model judgment from an upstream F2
    # atomic-schema-validation drop (`inp.domain_inference.
    # validation_errors_present`, harness-supplied from the same source
    # artifact) — never a bare "정보 없음" when validation errors exist.
    absence_note = None
    if not depts:
        absence_note = (
            A7_NO_CANDIDATES_VALIDATION_DROPPED_KO
            if inp.domain_inference.validation_errors_present
            else A7_NO_CANDIDATES_MODEL_JUDGED_KO
        )
    return RecommendationSection(
        department_candidates=depts,
        department_candidates_absence_note=absence_note,
        recommended_questionnaire=apd.recommended_questionnaire if apd else None,
        recommendation_caveat=apd.recommendation_caveat if apd else None,
    )


# ── A8 (optional narrative hook, Task 2 / `handoff_generator` v3) ────────


def _leak_normalize(s: str) -> str:
    """NFKC + casefold so the A6→A8 refusal cannot be dodged by case or
    unicode-width variants ("ptsd", "ＰＴＳＤ" must match candidate "PTSD")."""
    return unicodedata.normalize("NFKC", s).casefold()


def _disease_leaks(disease: str, normalized_text: str) -> bool:
    r"""True when *disease* appears in the already-normalized narrative NOT
    merely as a substring of a larger ASCII word — a short Latin candidate
    ("AD") must not match inside "had" (false-positive narrative rejection),
    while a CJK candidate still matches when followed by a Korean particle
    ("우울증" in "우울증이"). Boundaries are ASCII-only (``[a-z0-9]`` after
    casefold), so CJK adjacency is intentionally NOT treated as a boundary. The
    candidate is stripped first so surrounding whitespace can't become part of
    the boundary-anchored pattern and defeat the match (e.g. candidate "PTSD "
    against "…has PTSD symptoms" — codex clinical-isolation guarantee)."""
    norm = _leak_normalize(disease).strip()
    if not norm:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(norm)}(?![a-z0-9])", normalized_text) is not None


def _build_a8(inp: HandoffReportInput) -> NarrativeSection:
    """`ADR-037` Decision 1 default (`narrative_enabled=False`) is
    UNCHANGED — A8 still ships the explicit disabled marker, never blank,
    whenever the caller does not opt in. Task 2 adds the OPT-IN path: when
    `narrative_enabled=True` (enforced non-empty `narrative_text`,
    `assemble_handoff_report` below), this function applies ONE
    defense-in-depth check before rendering it — an NFKC+casefold
    normalized, ASCII-token-boundary scan of every A6 candidate's `disease`
    name against the given text (HPI hard red line, design doc §6.1 point 1).
    A match REFUSES the narrative
    entirely (never silently strips/redacts the matched substring, which
    could leave a mangled sentence that still implies the missing
    content) — this function still never calls any LLM/agent itself
    (module docstring's zero-LLM invariant is unaffected: this is a pure,
    boundary-aware containment check over caller-supplied data)."""
    if not inp.narrative_enabled:
        return NarrativeSection(narrative_enabled=False, text=None)

    text = (inp.narrative_text or "").strip()
    apd = inp.domain_inference.ai_predicted_disease
    candidate_diseases = [c.disease for c in (apd.candidates if apd else []) if c.disease]
    normalized_text = _leak_normalize(text)
    leaked = [d for d in candidate_diseases if _disease_leaks(d, normalized_text)]
    if leaked:
        return NarrativeSection(
            narrative_enabled=False, text=None, absent_marker=NARRATIVE_REJECTED_DISEASE_LEAK_KO
        )
    return NarrativeSection(narrative_enabled=True, text=text)


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

    Raises `ValueError` if `inp.narrative_enabled` is `True` but
    `inp.narrative_text` is empty/absent — the narrative path (A8) is
    OFF BY DEFAULT (`ADR-037` Decision 1) and, when opted into (Task 2 /
    `handoff_generator` v3), still requires the caller to supply an
    ALREADY-GENERATED narrative string; no code path in this module ever
    calls `HandoffGeneratorAgent` itself, so it cannot produce that text on
    its own. Set `narrative_enabled=False` to omit A8 (default, always
    ships the explicit disabled marker, never blank).
    """
    if inp.narrative_enabled and not (inp.narrative_text or "").strip():
        raise ValueError(
            "HandoffReportInput.narrative_enabled=True requires a non-empty "
            "narrative_text (ADR-037 Decision 1 default is narrative_enabled=False; "
            "Task 2 / handoff_generator v3 permits an OPT-IN narrative section, but "
            "only when the caller supplies an externally-generated narrative_text — "
            "src.f5 makes zero LLM calls itself, e.g. via "
            "HandoffGeneratorAgent.generate_narrative). Set narrative_enabled=False "
            "to omit A8."
        )

    return HandoffReportOutput(
        vp_id=inp.vp_id,
        generated_at=datetime.now().astimezone().isoformat(),
        a0_header=_build_header(inp),
        a1_chief_complaint=_build_a1(inp),
        a2_hpi=_build_a2(inp),
        slot_overview=_build_slot_overview(inp),
        a3_risk_safety=_build_a3(inp),
        a4_mental_status=_build_a4(inp),
        a5_questionnaires=_build_a5(inp),
        a6_ai_predicted_disease=_build_a6(inp),
        a7_recommendations=_build_a7(inp),
        a8_narrative=_build_a8(inp),
        b_longitudinal=_build_b(inp),
    )
