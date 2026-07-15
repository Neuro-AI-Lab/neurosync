"""F4 — longitudinal (between-session) state-change analysis (production engine).

`docs/ai/f4_quick_dev_plan.md` §4/§6.1, `PLAN-2026-W29-D`, `ADR-036`. This
module is architected exactly like `f1.py`/`f2.py`/`f3.py`: a standalone
module invocable by the F1->F2->F3->F4 chaining validation harness — never
a route, never wired into `orchestrator.py`.

`analyze_longitudinal_series` is a PURE, 100% deterministic, ZERO-LLM
function over an explicit `LongitudinalSeriesInput` a harness has already
assembled from F1/F2/F3 artifacts + the session ledger. Per REV-044
Criterion 6 (grep-verified by qa, elevated from Wave 1's own done-when):
this module performs ZERO direct filesystem access and ZERO harness/test-
tree imports — it never reads the ledger file, never reads a
`conversation.json`/`domain_inference.json`/`survey.json` path itself.
Reading those artifacts and building `SessionRecord`s is the harness's own
job, entirely outside this module; WRITING this module's own output
artifact (`temporal.json`/`_report.md`/PNGs) is `src/services/f4_report.py`
— a deliberate deviation from the design doc's own architecture diagram
(§4), which listed the save function inside this file; kept out of this
module specifically so a whole-file check for direct filesystem access
returns 0 hits with zero ambiguity (Criterion 6's literal wording), while
`analyze_longitudinal_series` stays the single source of truth for every
number a caller reports.

Aggregation basis (Criterion 0/0b, `ADR-036` item 1) — disclosed once here,
detailed per-function below: `scale_series`/`session_ctrs`/`sentiment`
TrendVerdicts all share ONE non-naive basis, `first_vs_last_delta+slope_sign
(+band_transition for scales)` (`_first_last_slope_trend`, `_scale_trend_
verdict`/`_ctrs_trend_verdict`/`_sentiment_trend_verdict`) — NEVER
`temporal_summary.SCALE_THRESHOLD=5` pairwise-delta reuse as the sole
basis (REV-044 Issue 1: a single pairwise step in an 11-session
tapering-cadence arc rarely reaches +-5, which would silently suppress the
exact across-series signal Criterion 1 requires). Per-pair
`TemporalSummaryAgent._compare_scale`/`_compare_ctrs`/`_compare_sentiment`
outputs are still computed and attached, but ONLY as supplementary evidence
strings, explicitly labeled `"supplementary (pairwise reuse, ...)"` — never
the basis for `direction`. `overall_direction`'s N-dimension combination
rule is disclosed in `_overall_direction` (Criterion 0b).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Literal

import numpy as np
from pydantic import ValidationError

from src.agents.temporal_summary import SCALE_THRESHOLD as TEMPORAL_SCALE_THRESHOLD
from src.agents.temporal_summary import TemporalSummaryAgent
from src.grounding import QUESTIONABLE_SLOT_KEYS
from src.schemas.ai_predicted_disease import AIPredictedDiseaseOutput
from src.schemas.longitudinal import (
    CTRSSeriesPoint,
    DiseaseCandidateSeriesPoint,
    DomainCandidateSeriesPoint,
    LongitudinalAnalysisOutput,
    ScaleSeriesPoint,
    SentimentSeriesPoint,
    SlotFillPoint,
    TrendVerdict,
)

_Direction = Literal["improved", "worsened", "unchanged", "unknown"]

# ── Harness -> production contract (design doc §4.1) ────────────────────


@dataclass(frozen=True)
class SessionRecord:
    """One VP session's already-extracted dims — built by the harness from
    the ledger + F1/F2 artifact files (§3's field-path table). This module
    never re-resolves any of these values from a file path; it trusts the
    caller's extraction verbatim.

    `turn_sentiment_polarities`/`turn_risk_signal_count` (F1-8, Mode A):
    always derivable when >=1 patient turn exists. `session_sentiment_
    summary` (F1-7, Mode B): the raw `session_sentiment` dict, `{}`/`None`
    on a crisis-early-exit session (`f1.py`'s own sync-fallback comment).
    `f3`: the ledger's own `"f3"` sub-object as-is (`None` when the F3
    stage never produced a survey.json this session).
    """

    session_index: int
    simulated_date: str
    scenario_pack_id: str | None
    arc_mode: str | None
    final_slots: dict[str, str]
    missing_slots: list[str]
    session_ctrs: int | None
    crisis_triggered: bool
    crisis_turn: int | None
    probe_events: list[dict]
    risk_floor: int | None
    turn_sentiment_polarities: list[float]
    turn_risk_signal_count: int
    session_sentiment_summary: dict | None
    domain_candidates: list[dict]
    ai_predicted_disease: dict | None
    f3: dict | None


@dataclass(frozen=True)
class LongitudinalSeriesInput:
    """`sessions` must be caller-sorted by non-decreasing `session_index` —
    `analyze_longitudinal_series` validates this and raises loudly if not
    (never silently re-sorts, so a caller bug surfaces immediately)."""

    vp_id: str
    sessions: tuple[SessionRecord, ...]


# ── Severity-band ordinal ranks (never re-derives band boundaries — those
#    live only in `src.scoring.survey_scorer`; this table is ordinal RANK
#    only, "less severe" (0) -> "more severe" (N), used solely to detect a
#    same-scale >=2-band jump and to report a band-transition string) ─────

_SEVERITY_BAND_RANK: dict[str, dict[str, int]] = {
    "PHQ-9": {"minimal": 0, "mild": 1, "moderate": 2, "moderately_severe": 3, "severe": 4},
    "GAD-7": {"minimal": 0, "mild": 1, "moderate": 2, "severe": 3},
    "PHQ-4": {"normal": 0, "mild": 1, "moderate": 2, "severe": 3},
    "AUDIT-C": {"low_risk": 0, "hazardous_drinking": 1},
    "WHO-5": {"adequate_wellbeing": 0, "low_wellbeing": 1},
}

# Whether a HIGHER raw score is clinically better for this scale. All 4
# reachable scales in this project (PHQ-9/GAD-7/PHQ-4/AUDIT-C) are
# lower-is-better; WHO-5 (raw wellbeing score) is higher-is-better, listed
# for completeness even though it is structurally unreachable today
# (`item_bank.py` ships 0 WHO-5 items).
_SCALE_HIGHER_IS_BETTER: dict[str, bool] = {
    "PHQ-9": False,
    "GAD-7": False,
    "PHQ-4": False,
    "AUDIT-C": False,
    "WHO-5": True,
}

_COURSE_SHAPE_MIN_POINTS = 3
# `overall_direction`'s N-dimension vote (Criterion 0b, `_overall_direction`)
# excludes these dimensions explicitly — see that function's own docstring.
_OVERALL_DIRECTION_EXCLUDED_DIMENSIONS = frozenset({"slot_fill_count"})


def _scale_dimension_name(scale_name: str) -> str:
    """e.g. "PHQ-9" -> "phq9_total", "AUDIT-C" -> "auditc_total"."""
    return scale_name.lower().replace("-", "") + "_total"


def _parse_iso_date(value: str) -> _date | None:
    try:
        return _date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


# ── Shared first-vs-last + slope basis (Criterion 0) ─────────────────────


def _first_last_slope_trend(
    points: list[tuple[int, float]], *, higher_is_better: bool, label: str,
) -> tuple[_Direction, list[str]]:
    """PRIMARY basis for `scale_series`/`session_ctrs`/`sentiment`/
    `slot_fill_count` TrendVerdicts (Criterion 0, `ADR-036` item 1).

    `points`: caller-sorted `(session_index, value)` pairs, already
    filtered to comparable (non-`None`) points for one dimension.

    Rule (disclosed, fixed, applied identically regardless of outcome):
      1. `delta = last.value - first.value` (first vs LAST comparable
         session, never a consecutive pair) is the PRIMARY signal.
      2. `slope` = least-squares linear-fit slope (`numpy.polyfit`, degree
         1) across every comparable point, sign-only, is the CONFIRMATORY
         signal — used only when `delta == 0` (a flat first/last framing a
         real drift the slope can still see), and to flag a disagreement
         with `delta`'s sign in the evidence (never silently dropped).
      3. `direction`: "unknown" if `n < 2`; "unchanged" if both signals are
         flat; otherwise `delta`'s sign (or `slope`'s sign, if `delta==0`)
         mapped through `higher_is_better`.
    """
    n = len(points)
    if n < 2:
        return "unknown", []

    first_idx, first_val = points[0]
    last_idx, last_val = points[-1]
    delta = last_val - first_val

    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    slope = float(np.polyfit(xs, ys, 1)[0])

    sign_delta = 0 if delta == 0 else (1 if delta > 0 else -1)
    sign_slope = 0 if abs(slope) < 1e-9 else (1 if slope > 0 else -1)
    raw = sign_delta if sign_delta != 0 else sign_slope

    if raw == 0:
        direction: _Direction = "unchanged"
    elif (raw > 0) == higher_is_better:
        direction = "improved"
    else:
        direction = "worsened"

    evidence = [
        f"{label}: first-vs-last delta session {first_idx}->{last_idx}: "
        f"{first_val:g} -> {last_val:g} ({delta:+.3g})",
        f"{label}: linear slope across {n} comparable session(s): {slope:+.4g}/session",
    ]
    if sign_delta != 0 and sign_slope != 0 and sign_delta != sign_slope:
        evidence.append(
            f"{label}: NOTE first-vs-last delta sign and slope sign disagree "
            f"(delta_sign={sign_delta:+d}, slope_sign={sign_slope:+d}) — delta sign used "
            "as primary per this function's disclosed basis"
        )
    return direction, evidence


# ── Series builders (§3 field-path table) ─────────────────────────────────


def _build_slot_fill_series(sessions: list[SessionRecord]) -> list[SlotFillPoint]:
    """F1-1/F1-2. `newly_filled`/`newly_missing` are set-diffs against the
    IMMEDIATELY PRIOR session in this series (never re-fabricated content —
    presence/absence only, per §3's own discipline)."""
    points: list[SlotFillPoint] = []
    prev_filled: set[str] = set()
    prev_missing: set[str] = set()
    for i, s in enumerate(sessions):
        filled_keys = {k for k in QUESTIONABLE_SLOT_KEYS if s.final_slots.get(k)}
        missing_keys = set(s.missing_slots) & set(QUESTIONABLE_SLOT_KEYS)
        newly_filled = sorted(filled_keys - prev_filled) if i > 0 else []
        newly_missing = sorted(missing_keys - prev_missing) if i > 0 else []
        points.append(
            SlotFillPoint(
                session_index=s.session_index,
                simulated_date=s.simulated_date,
                filled_count=len(filled_keys),
                total_questionable=len(QUESTIONABLE_SLOT_KEYS),
                newly_filled=newly_filled,
                newly_missing=newly_missing,
                mental_status_exam_observed=bool(s.final_slots.get("mental_status_exam")),
            )
        )
        prev_filled, prev_missing = filled_keys, missing_keys
    return points


def _build_scale_series(sessions: list[SessionRecord]) -> dict[str, list[ScaleSeriesPoint]]:
    """F3-1..F3-6, keyed by `scale_name` actually seen. A session with
    `f3=None` or no `scale_name` (e.g. `no_questionnaire_indicated` with 0
    candidates) contributes NO point to any scale sub-series — it still
    contributes to every other series (§3.1's own missing-data rule)."""
    series: dict[str, list[ScaleSeriesPoint]] = {}
    for s in sessions:
        f3 = s.f3
        if not f3:
            continue
        scale_name = f3.get("scale_name")
        if not scale_name:
            continue
        administered = f3.get("outcome") == "administered"
        point = ScaleSeriesPoint(
            session_index=s.session_index,
            simulated_date=s.simulated_date,
            scale_name=scale_name,
            administered=administered,
            total_score=f3.get("total_score") if administered else None,
            max_score=f3.get("max_score") if administered else None,
            severity=f3.get("severity") if administered else None,
            critical_item_positive=f3.get("safety_referral") if administered else None,
            subscale_scores=(f3.get("subscale_scores") or {}) if administered else {},
        )
        series.setdefault(scale_name, []).append(point)
    return series


def _build_ctrs_series(sessions: list[SessionRecord]) -> list[CTRSSeriesPoint]:
    return [
        CTRSSeriesPoint(
            session_index=s.session_index,
            simulated_date=s.simulated_date,
            session_ctrs=s.session_ctrs,
            crisis_triggered=bool(s.crisis_triggered),
            probe_event_count=len(s.probe_events or []),
            risk_floor=s.risk_floor,
        )
        for s in sessions
    ]


def _session_mean_polarity(session: SessionRecord) -> tuple[float | None, str]:
    """F1-8 PRIMARY, F1-7 defensive-only fallback (Criterion 4). F1-8
    (`turn_sentiment_polarities`) is used whenever >=1 turn produced a
    polarity value — precisely because F1-7 (`session_sentiment`, Mode B)
    can be an empty `{}` on a crisis-early-exit session while F1-8 is not.
    Falling back to F1-7's own `polarity_trajectory` mean only happens when
    F1-8 is itself empty (should not occur once turn 0 always logs, per
    PRD §2.5 rule 1) — never a silent `unknown` when Mode-A data exists."""
    if session.turn_sentiment_polarities:
        return (
            float(np.mean(session.turn_sentiment_polarities)),
            "mode_a_derived",
        )
    traj = (session.session_sentiment_summary or {}).get("polarity_trajectory") or []
    values = [
        p.get("polarity") for p in traj if isinstance(p, dict) and p.get("polarity") is not None
    ]
    if values:
        return float(np.mean(values)), "mode_b"
    return None, "mode_a_derived"


def _build_sentiment_series(sessions: list[SessionRecord]) -> list[SentimentSeriesPoint]:
    points: list[SentimentSeriesPoint] = []
    for s in sessions:
        mean_polarity, source = _session_mean_polarity(s)
        summary = s.session_sentiment_summary or {}
        points.append(
            SentimentSeriesPoint(
                session_index=s.session_index,
                simulated_date=s.simulated_date,
                mean_polarity=mean_polarity,
                dominant_emotions=list(summary.get("dominant_emotions") or []),
                source=source,  # type: ignore[arg-type]
                risk_signal_count=s.turn_risk_signal_count,
                signal_strength=summary.get("signal_strength"),
                emotional_shift_detected=summary.get("emotional_shift_detected"),
            )
        )
    return points


def _build_disease_candidate_series(
    sessions: list[SessionRecord],
) -> list[DiseaseCandidateSeriesPoint]:
    """F2-2. Re-validates each session's raw `ai_predicted_disease` dict
    against the existing `AIPredictedDiseaseOutput` model (cheap
    correctness check, §4.2) before extracting fields — a malformed
    upstream dict is skipped honestly (never fabricated), not crashed on."""
    points: list[DiseaseCandidateSeriesPoint] = []
    for s in sessions:
        if not s.ai_predicted_disease:
            continue
        try:
            validated = AIPredictedDiseaseOutput.model_validate(s.ai_predicted_disease)
        except ValidationError:
            continue
        for rank, cand in enumerate(validated.candidates, start=1):
            points.append(
                DiseaseCandidateSeriesPoint(
                    session_index=s.session_index,
                    simulated_date=s.simulated_date,
                    disease=cand.disease,
                    similarity_score=cand.similarity_score,
                    rank=rank,
                )
            )
    return points


def _build_domain_candidate_series(
    sessions: list[SessionRecord],
) -> list[DomainCandidateSeriesPoint]:
    """F2-1. Reads the raw `domain_candidates` dicts defensively (no schema
    re-validation — the F2 domain-inference schema module transitively
    imports the handoff schema module, which this module's own
    standalone-by-design discipline (§6.5) never imports directly or
    transitively)."""
    points: list[DomainCandidateSeriesPoint] = []
    for s in sessions:
        for c in s.domain_candidates or []:
            domain = c.get("domain")
            confidence = c.get("confidence")
            if domain is None or confidence is None:
                continue
            points.append(
                DomainCandidateSeriesPoint(
                    session_index=s.session_index,
                    simulated_date=s.simulated_date,
                    domain=domain,
                    confidence=float(confidence),
                )
            )
    return points


# ── TrendVerdict builders ─────────────────────────────────────────────────


def _scale_trend_verdict(scale_name: str, points: list[ScaleSeriesPoint]) -> TrendVerdict:
    """Basis (Criterion 0): `_first_last_slope_trend` over every
    (administered, non-None) point for THIS scale, cross-checked against
    the net ordinal severity-band transition (never the band BOUNDARIES —
    those are `survey_scorer.py`'s alone). Supplementary evidence: every
    consecutive pair's `TemporalSummaryAgent._compare_scale` reuse
    (`temporal_summary.SCALE_THRESHOLD`), explicitly labeled — never the
    basis for `direction`.
    """
    administered_points = [p for p in points if p.administered and p.total_score is not None]
    comparable = [(p.session_index, float(p.total_score)) for p in administered_points]
    basis = "first_vs_last_delta+slope_sign+band_transition (non-naive-pairwise, ADR-036 item 1)"
    dimension = _scale_dimension_name(scale_name)
    higher_is_better = _SCALE_HIGHER_IS_BETTER.get(scale_name, False)

    direction, evidence = _first_last_slope_trend(
        comparable, higher_is_better=higher_is_better, label=scale_name
    )

    if len(administered_points) >= 2:
        first_point, last_point = administered_points[0], administered_points[-1]
        band_ranks = _SEVERITY_BAND_RANK.get(scale_name, {})
        first_rank = band_ranks.get(first_point.severity or "")
        last_rank = band_ranks.get(last_point.severity or "")
        if first_rank is not None and last_rank is not None:
            band_delta = last_rank - first_rank
            evidence.append(
                f"{scale_name}: severity band {first_point.severity} -> "
                f"{last_point.severity} (ordinal band delta {band_delta:+d})"
            )
            if abs(band_delta) >= 2:
                evidence.append(
                    f"{scale_name}: NOTABLE — same-scale severity-band jump of "
                    f"{abs(band_delta)} bands (>= 2), flagged regardless of raw delta magnitude"
                )

    for i in range(len(comparable) - 1):
        # `_compare_scale` formats its own evidence string with `{delta:+d}`
        # (int-only) — cast back to int for this call (total_score is
        # always an int on the artifact; `comparable` itself is float-typed
        # only for `_first_last_slope_trend`'s/`numpy`'s sake above).
        pair = TemporalSummaryAgent._compare_scale(
            scale_name, int(comparable[i + 1][1]), int(comparable[i][1])
        )
        pair_evidence = pair.evidence[0] if pair.evidence else ""
        evidence.append(
            f"supplementary (pairwise reuse, temporal_summary.SCALE_THRESHOLD="
            f"{TEMPORAL_SCALE_THRESHOLD}, session {comparable[i][0]}->{comparable[i + 1][0]}): "
            f"{pair.direction.value} — {pair_evidence}"
        )

    return TrendVerdict(
        dimension=dimension,
        direction=direction,
        basis=basis,
        n_comparable_points=len(comparable),
        evidence=evidence,
    )


def _ctrs_trend_verdict(points: list[CTRSSeriesPoint]) -> TrendVerdict:
    """Basis (Criterion 0): identical `_first_last_slope_trend` discipline.
    CTRS is inverted (1=highest risk .. 5=stable), so `higher_is_better=
    True`. Supplementary: per-pair `TemporalSummaryAgent._compare_ctrs`
    reuse, labeled."""
    comparable = [
        (p.session_index, float(p.session_ctrs)) for p in points if p.session_ctrs is not None
    ]
    basis = "first_vs_last_delta+slope_sign (non-naive-pairwise, ADR-036 item 1)"
    direction, evidence = _first_last_slope_trend(
        comparable, higher_is_better=True, label="session_ctrs"
    )

    # Supplementary annotations only attached once there is an actual trend
    # to describe (n>=2) — a single-session series stays direction="unknown"
    # with evidence=[] (evidence-필수: never attach evidence with nothing to
    # support behind an "unknown" verdict).
    if len(comparable) >= 2:
        crisis_sessions = [p.session_index for p in points if p.crisis_triggered]
        if crisis_sessions:
            evidence.append(f"session_ctrs: crisis_triggered at session(s) {crisis_sessions}")
        min_ctrs = min(v for _, v in comparable)
        evidence.append(f"session_ctrs: minimum CTRS reached across the series: {min_ctrs:g}")

    for i in range(len(comparable) - 1):
        pair = TemporalSummaryAgent._compare_ctrs(int(comparable[i + 1][1]), int(comparable[i][1]))
        evidence.append(
            "supplementary (pairwise reuse, temporal_summary._compare_ctrs, "
            f"session {comparable[i][0]}->{comparable[i + 1][0]}): {pair.direction.value}"
        )

    return TrendVerdict(
        dimension="session_ctrs", direction=direction, basis=basis,
        n_comparable_points=len(comparable), evidence=evidence,
    )


def _sentiment_trend_verdict(points: list[SentimentSeriesPoint]) -> TrendVerdict:
    """Basis (Criterion 0): identical `_first_last_slope_trend` discipline
    over `mean_polarity` (F1-8-primary, see `_session_mean_polarity`).
    Supplementary: per-pair `TemporalSummaryAgent._compare_sentiment`
    reuse, labeled."""
    comparable = [
        (p.session_index, p.mean_polarity) for p in points if p.mean_polarity is not None
    ]
    basis = "first_vs_last_delta+slope_sign (non-naive-pairwise, ADR-036 item 1)"
    direction, evidence = _first_last_slope_trend(
        comparable, higher_is_better=True, label="sentiment"
    )

    for i in range(len(comparable) - 1):
        pair = TemporalSummaryAgent._compare_sentiment(comparable[i + 1][1], comparable[i][1])
        evidence.append(
            "supplementary (pairwise reuse, temporal_summary._compare_sentiment, "
            f"session {comparable[i][0]}->{comparable[i + 1][0]}): {pair.direction.value}"
        )

    return TrendVerdict(
        dimension="sentiment", direction=direction, basis=basis,
        n_comparable_points=len(comparable), evidence=evidence,
    )


def _slot_fill_trend_verdict(points: list[SlotFillPoint]) -> TrendVerdict:
    """Basis: same `_first_last_slope_trend` discipline (no pairwise-reuse
    precedent exists for this dimension — `temporal_summary.py` never
    tracked slot-fill). Excluded from `overall_direction`'s vote (see
    `_overall_direction`) — a coverage/engagement metric, not a
    symptom-direction signal."""
    comparable = [(p.session_index, float(p.filled_count)) for p in points]
    basis = "first_vs_last_delta+slope_sign"
    direction, evidence = _first_last_slope_trend(
        comparable, higher_is_better=True, label="slot_fill_count"
    )
    return TrendVerdict(
        dimension="slot_fill_count", direction=direction, basis=basis,
        n_comparable_points=len(comparable), evidence=evidence,
    )


# ── Cross-dimension combination rules (Criterion 0b) ──────────────────────


def _overall_direction(trend_verdicts: list[TrendVerdict]) -> _Direction:
    """Cross-dimension combination rule (Criterion 0b, `ADR-036` item 1):
    generalizes PRD §5's as-built worsened-priority/majority-vote rule
    (fixed 3 domains: PHQ-9, GAD-7, CTRS — `temporal_summary.py`'s own
    `run()`, sentiment computed but historically NOT folded into that vote)
    to however many CLINICAL-STATE dimensions this N-session series
    actually has.

    Disclosed inclusion rule, fixed in code, applied identically regardless
    of the resulting verdict (never reverse-engineered from a preferred
    outcome): every TrendVerdict whose `dimension` is NOT in
    `_OVERALL_DIRECTION_EXCLUDED_DIMENSIONS` votes — concretely, every
    administered scale's `<scale>_total` TrendVerdict, `session_ctrs`, AND
    `sentiment` (this design's own deliberate choice to include sentiment,
    unlike the as-built pairwise rule, since the user's own directive names
    sentiment as an equal-standing longitudinal-analysis input, not a
    second-class one). `slot_fill_count` is excluded (a coverage/engagement
    metric, not a symptom-direction signal). Disease/domain-candidate
    trends are never TrendVerdicts at all, so they structurally cannot
    enter this vote (a similarity trend is never a clinical-state signal,
    §5.3 wording law 1).

    Then: any `worsened` among the voting directions wins outright
    (worsened-priority, unchanged from PRD §5); else `improved` if a
    strict majority of the (non-unknown) voting directions are `improved`;
    else `unchanged`; `unknown` if there are zero non-unknown voting
    directions.
    """
    directions = [
        tv.direction
        for tv in trend_verdicts
        if tv.dimension not in _OVERALL_DIRECTION_EXCLUDED_DIMENSIONS and tv.direction != "unknown"
    ]
    if not directions:
        return "unknown"
    if any(d == "worsened" for d in directions):
        return "worsened"
    improved_count = sum(1 for d in directions if d == "improved")
    if improved_count > len(directions) / 2:
        return "improved"
    return "unchanged"


def _pick_primary_scale(
    scale_series: dict[str, list[ScaleSeriesPoint]],
) -> tuple[str | None, str | None]:
    """The scale with the most administered comparable points is
    "primary" for `course_shape`/`concordance_flag` purposes — ties broken
    alphabetically by scale name for determinism. Returns
    `(dimension_name, scale_name)`, both `None` if no scale has >=1
    administered comparable point."""
    best_name: str | None = None
    best_count = -1
    for name in sorted(scale_series):
        count = sum(
            1 for p in scale_series[name] if p.administered and p.total_score is not None
        )
        if count > best_count:
            best_name, best_count = name, count
    if best_name is None or best_count < 1:
        return None, None
    return _scale_dimension_name(best_name), best_name


def _concordance_flag(
    trend_verdicts: list[TrendVerdict], primary_scale_dimension: str | None
) -> Literal["concordant", "discordant", "unknown"]:
    """Rule-based cross-dimension concordance check (CVR-020 Rec 4 /
    Finding 8): compares the PRIMARY scale-total direction against
    `session_ctrs` and `sentiment` directions. `discordant` iff at least
    one of these three reads `improved` while another reads `worsened` in
    the SAME analysis — the exact same-series structured-score-vs-
    behavioral-signal contradiction CVR-015 Finding 5 flagged at the
    pairwise level. `concordant` when >=2 of the three are non-`unknown`
    and none contradicts. `unknown` when fewer than 2 have a non-`unknown`
    direction."""
    watched_dims = {"session_ctrs", "sentiment"}
    if primary_scale_dimension:
        watched_dims.add(primary_scale_dimension)
    directions = [
        tv.direction for tv in trend_verdicts
        if tv.dimension in watched_dims and tv.direction != "unknown"
    ]
    if len(directions) < 2:
        return "unknown"
    if "improved" in directions and "worsened" in directions:
        return "discordant"
    return "concordant"


def _course_shape(
    points: list[ScaleSeriesPoint],
) -> Literal[
    "gradual_improvement",
    "improvement_with_plateau",
    "relapse_after_partial_improvement",
    "worsening_sustained",
    "crisis_episode",
    "unknown",
]:
    """Classification rule (CVR-020 Rec 3, Criterion-0b discipline applied):
    reuses design doc §2.1's own archetype vocabulary over the PRIMARY
    scale's administered comparable points (session-ordered `total_score`
    values). Fixed decision order (first match wins, disclosed, never
    reverse-engineered from a preferred label):

      1. `unknown` if fewer than 3 comparable points exist — not enough to
         characterize a shape (a 2-point series only has a net direction,
         already captured by `overall_direction`).
      2. `gradual_improvement`: every consecutive delta is <=0 (monotonic
         non-increasing) AND net (last-first) < 0.
      3. `worsening_sustained`: every consecutive delta is >=0 (monotonic
         non-decreasing) AND net > 0.
      4. `relapse_after_partial_improvement`: the series' overall-worst
         (highest-score) point is INTERIOR (neither first nor last), the
         series improved (dipped below its own start) at some point before
         reaching that worst point, the series recovered (ended below that
         worst point) after it, AND the worsening run leading to that peak
         spans >=2 consecutive rising steps (a genuine relapse, not a
         single-step wobble).
      5. `crisis_episode`: exactly one isolated single-step worsening run
         whose peak stands far above an otherwise near-flat baseline
         (`net` small, non-spike points tightly clustered) — checked
         BEFORE `improvement_with_plateau` below, since a flat-baseline
         spike would otherwise also satisfy that looser pattern. Reserved
         taxonomy slot; not produced by either VP arc scripted this
         mission (§2.1/§7.5 stable-arc/crisis-episode coverage gap,
         REV-044 Issue 3 / ADR-036 item 2), exercised only by synthetic
         unit-test data.
      6. `improvement_with_plateau`: every worsening run is at most 1 step
         long (isolated single-session upticks that each reverse) AND net
         <= 0 — a transient wobble that does not derail the overall
         improving trend.
      7. `unknown`: none of the above cleanly match — an honest fallback,
         never a forced fit.
    """
    comparable = [p for p in points if p.administered and p.total_score is not None]
    if len(comparable) < _COURSE_SHAPE_MIN_POINTS:
        return "unknown"

    values = [int(p.total_score) for p in comparable]  # type: ignore[arg-type]
    n = len(values)
    deltas = [values[i + 1] - values[i] for i in range(n - 1)]
    signs = [0 if d == 0 else (1 if d > 0 else -1) for d in deltas]
    net = values[-1] - values[0]

    is_nonincreasing = all(s <= 0 for s in signs)
    is_nondecreasing = all(s >= 0 for s in signs)
    if is_nonincreasing and net < 0:
        return "gradual_improvement"
    if is_nondecreasing and net > 0:
        return "worsening_sustained"

    runs: list[int] = []
    current = 0
    for s in signs:
        if s > 0:
            current += 1
        else:
            if current:
                runs.append(current)
            current = 0
    if current:
        runs.append(current)
    max_worsening_run = max(runs) if runs else 0
    count_worsening_runs = len(runs)

    global_max_idx = max(range(n), key=lambda i: values[i])
    pre_worst_min = min(values[: global_max_idx + 1]) if global_max_idx > 0 else values[0]
    improved_before_worst = pre_worst_min < values[0]
    recovered_after_worst = global_max_idx < n - 1 and values[-1] < values[global_max_idx]

    if (
        global_max_idx not in (0, n - 1)
        and improved_before_worst
        and recovered_after_worst
        and max_worsening_run >= 2
    ):
        return "relapse_after_partial_improvement"

    if max_worsening_run == 1 and count_worsening_runs == 1 and abs(net) <= 1:
        spike_idx = next(i for i, s in enumerate(signs) if s > 0) + 1
        others = values[:spike_idx] + values[spike_idx + 1 :]
        if others and (max(others) - min(others)) <= 1 and values[spike_idx] - min(others) >= 2:
            return "crisis_episode"

    if max_worsening_run <= 1 and count_worsening_runs >= 1 and net <= 0:
        return "improvement_with_plateau"

    return "unknown"


def _crisis_f3_gap_notes(
    ctrs_series: list[CTRSSeriesPoint], scale_series: dict[str, list[ScaleSeriesPoint]]
) -> list[str]:
    """CVR-020 binding condition 3 machinery: for every session flagged
    risk-elevated (`crisis_triggered=True` OR `session_ctrs<=2`), checks
    whether ANY scale was actually administered that same session; if not,
    records an explicit gap note. This list is a dedicated, always-present
    (possibly empty) schema field — never a routine `None` buried in
    `scale_series` that a reader could pass over silently.
    """
    administered_by_session: dict[int, bool] = {}
    for points in scale_series.values():
        for p in points:
            administered_by_session[p.session_index] = (
                administered_by_session.get(p.session_index, False) or p.administered
            )
    notes: list[str] = []
    for c in ctrs_series:
        risk_elevated = c.crisis_triggered or (c.session_ctrs is not None and c.session_ctrs <= 2)
        if not risk_elevated:
            continue
        if not administered_by_session.get(c.session_index, False):
            notes.append(
                f"session {c.session_index} ({c.simulated_date}): risk-elevated "
                f"(crisis_triggered={c.crisis_triggered}, session_ctrs={c.session_ctrs}) "
                "but NO scale was administered this session — F3 gap at a clinically "
                "high-value point (CVR-020 Finding 4 / binding condition 3)"
            )
    return notes


# ── Public entry point ────────────────────────────────────────────────────


def analyze_longitudinal_series(inp: LongitudinalSeriesInput) -> LongitudinalAnalysisOutput:
    """Pure, deterministic, ZERO-LLM longitudinal trend analysis over an
    explicit N-session series a harness has already assembled (design doc
    §4, `ADR-036`). Raises `ValueError` if `inp.sessions` is empty or not
    sorted by non-decreasing `session_index` — never silently re-sorts.
    """
    from datetime import datetime

    sessions = list(inp.sessions)
    if not sessions:
        raise ValueError("LongitudinalSeriesInput.sessions must not be empty")
    indices = [s.session_index for s in sessions]
    if indices != sorted(indices):
        raise ValueError(
            f"sessions must be sorted by non-decreasing session_index, got {indices}"
        )

    slot_fill_series = _build_slot_fill_series(sessions)
    scale_series = _build_scale_series(sessions)
    ctrs_series = _build_ctrs_series(sessions)
    sentiment_series = _build_sentiment_series(sessions)
    disease_series = _build_disease_candidate_series(sessions)
    domain_series = _build_domain_candidate_series(sessions)

    trend_verdicts: list[TrendVerdict] = []
    for scale_name in sorted(scale_series):
        trend_verdicts.append(_scale_trend_verdict(scale_name, scale_series[scale_name]))
    trend_verdicts.append(_ctrs_trend_verdict(ctrs_series))
    trend_verdicts.append(_sentiment_trend_verdict(sentiment_series))
    trend_verdicts.append(_slot_fill_trend_verdict(slot_fill_series))

    primary_dimension, primary_scale_name = _pick_primary_scale(scale_series)
    overall_direction = _overall_direction(trend_verdicts)
    primary_scale_points = scale_series.get(primary_scale_name, []) if primary_scale_name else []
    course_shape = _course_shape(primary_scale_points)
    concordance_flag = _concordance_flag(trend_verdicts, primary_dimension)
    crisis_f3_gaps = _crisis_f3_gap_notes(ctrs_series, scale_series)

    arc_mode = next((s.arc_mode for s in sessions if s.arc_mode), None)

    dates = [d for d in (_parse_iso_date(s.simulated_date) for s in sessions) if d is not None]
    session_span_days = (max(dates) - min(dates)).days if len(dates) >= 2 else None

    return LongitudinalAnalysisOutput(
        vp_id=inp.vp_id,
        arc_mode=arc_mode,
        n_sessions=len(sessions),
        session_span_days=session_span_days,
        slot_fill_series=slot_fill_series,
        scale_series=scale_series,
        ctrs_series=ctrs_series,
        sentiment_series=sentiment_series,
        disease_candidate_series=disease_series,
        domain_candidate_series=domain_series,
        trend_verdicts=trend_verdicts,
        overall_direction=overall_direction,
        course_shape=course_shape,
        concordance_flag=concordance_flag,
        crisis_f3_gaps=crisis_f3_gaps,
        generated_at=datetime.now().isoformat(),
    )
