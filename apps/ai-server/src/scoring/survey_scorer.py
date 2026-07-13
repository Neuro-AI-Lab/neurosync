"""Rule-based scoring for standardised psychiatric scales.

All scoring is deterministic — no LLM calls.
References:
  - PHQ-9: Kroenke et al., 2001
  - GAD-7: Spitzer et al., 2006
  - PHQ-4: Kroenke et al., 2009
  - WHO-5: WHO, 1998
  - AUDIT-C: Bush et al., 1998
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ScaleName = Literal["PHQ-9", "GAD-7", "PHQ-4", "WHO-5", "AUDIT-C"]


@dataclass(frozen=True)
class ScoreResult:
    """Immutable result of a survey scoring operation."""

    scale_name: ScaleName
    total_score: int
    max_score: int
    severity: str
    critical_item_positive: bool = False
    critical_items: list[dict] = field(default_factory=list)
    subscale_scores: dict[str, int] = field(default_factory=dict)
    interpretation: str = ""
    recommended_action: str = ""


# ── PHQ-9 ────────────────────────────────────────────────────────────

_PHQ9_SEVERITY = [
    (0, 4, "minimal"),
    (5, 9, "mild"),
    (10, 14, "moderate"),
    (15, 19, "moderately_severe"),
    (20, 27, "severe"),
]


def _score_phq9(responses: list[int]) -> ScoreResult:
    if len(responses) != 9:
        raise ValueError(f"PHQ-9 requires 9 responses, got {len(responses)}")
    for i, v in enumerate(responses):
        if not 0 <= v <= 3:
            raise ValueError(f"PHQ-9 item {i+1}: value {v} out of range 0-3")

    total = sum(responses)
    severity = next(s for lo, hi, s in _PHQ9_SEVERITY if lo <= total <= hi)

    # Item 9 (index 8): suicidal ideation
    q9_positive = responses[8] >= 1
    critical = []
    if q9_positive:
        critical.append({"item": 9, "value": responses[8], "flag": "suicidal_ideation"})

    action = "none"
    if severity == "minimal":
        action = "none"
    elif severity == "mild":
        action = "watchful_waiting"
    elif severity == "moderate":
        action = "treatment_plan"
    elif severity in ("moderately_severe", "severe"):
        action = "clinician_review"

    if q9_positive:
        action = "safety_referral"

    return ScoreResult(
        scale_name="PHQ-9",
        total_score=total,
        max_score=27,
        severity=severity,
        critical_item_positive=q9_positive,
        critical_items=critical,
        interpretation=f"PHQ-9 {total}점: {severity}",
        recommended_action=action,
    )


# ── GAD-7 ────────────────────────────────────────────────────────────

_GAD7_SEVERITY = [
    (0, 4, "minimal"),
    (5, 9, "mild"),
    (10, 14, "moderate"),
    (15, 21, "severe"),
]


def _score_gad7(responses: list[int]) -> ScoreResult:
    if len(responses) != 7:
        raise ValueError(f"GAD-7 requires 7 responses, got {len(responses)}")
    for i, v in enumerate(responses):
        if not 0 <= v <= 3:
            raise ValueError(f"GAD-7 item {i+1}: value {v} out of range 0-3")

    total = sum(responses)
    severity = next(s for lo, hi, s in _GAD7_SEVERITY if lo <= total <= hi)

    action = "none"
    if severity in ("moderate", "severe"):
        action = "clinician_review"
    elif severity == "mild":
        action = "watchful_waiting"

    return ScoreResult(
        scale_name="GAD-7",
        total_score=total,
        max_score=21,
        severity=severity,
        interpretation=f"GAD-7 {total}점: {severity}",
        recommended_action=action,
    )


# ── PHQ-4 ────────────────────────────────────────────────────────────

_PHQ4_SEVERITY = [
    (0, 2, "normal"),
    (3, 5, "mild"),
    (6, 8, "moderate"),
    (9, 12, "severe"),
]


def _score_phq4(responses: list[int]) -> ScoreResult:
    if len(responses) != 4:
        raise ValueError(f"PHQ-4 requires 4 responses, got {len(responses)}")
    for i, v in enumerate(responses):
        if not 0 <= v <= 3:
            raise ValueError(f"PHQ-4 item {i+1}: value {v} out of range 0-3")

    total = sum(responses)
    severity = next(s for lo, hi, s in _PHQ4_SEVERITY if lo <= total <= hi)

    anxiety_sub = responses[0] + responses[1]    # Q1 + Q2
    depression_sub = responses[2] + responses[3]  # Q3 + Q4

    return ScoreResult(
        scale_name="PHQ-4",
        total_score=total,
        max_score=12,
        severity=severity,
        subscale_scores={"anxiety": anxiety_sub, "depression": depression_sub},
        interpretation=f"PHQ-4 {total}점: {severity} (불안 {anxiety_sub}, 우울 {depression_sub})",
        recommended_action="clinician_review" if total >= 6 else "none",
    )


# ── WHO-5 ────────────────────────────────────────────────────────────


def _score_who5(responses: list[int]) -> ScoreResult:
    if len(responses) != 5:
        raise ValueError(f"WHO-5 requires 5 responses, got {len(responses)}")
    for i, v in enumerate(responses):
        if not 0 <= v <= 5:
            raise ValueError(f"WHO-5 item {i+1}: value {v} out of range 0-5")

    raw = sum(responses)
    percentage = raw * 4  # WHO-5 percentage score = raw × 4

    # Source-caveat comment only (CVR-016 condition 5 / ADR-033 decision 5)
    # — NO behavior change, band boundary byte-frozen. Kim et al. 2010 (한국판
    # WHO-5, docs/ai/item_bank_v1_sources.md §4.4/§A9b, directly fetched from
    # 3 independent database mirrors): "The total score of WHO-5 below 13
    # indicates low well-being" (i.e. raw < 13, not raw <= 13). The `<= 13`
    # boundary below flags raw == 13 as low_wellbeing where the Korean source
    # would not — a real, sourced off-by-one, in the over-triage (safer)
    # direction. WHO-5 currently ships 0 items (item_bank.py v1) and is
    # structurally unreachable via CLASSIFICATION_TO_SCALE, so this has no
    # live consequence today; flagged here so it is not forgotten if WHO-5
    # ever ships items.
    if raw <= 13:
        severity = "low_wellbeing"
        action = "further_assessment"
    else:
        severity = "adequate_wellbeing"
        action = "none"

    return ScoreResult(
        scale_name="WHO-5",
        total_score=raw,
        max_score=25,
        severity=severity,
        subscale_scores={"percentage": percentage},
        interpretation=f"WHO-5 raw {raw} (percentage {percentage}%): {severity}",
        recommended_action=action,
    )


# ── AUDIT-C ──────────────────────────────────────────────────────────


def _score_audit_c(
    responses: list[int], *, patient_sex: str = "unknown"
) -> ScoreResult:
    if len(responses) != 3:
        raise ValueError(f"AUDIT-C requires 3 responses, got {len(responses)}")
    if not 0 <= responses[0] <= 4:
        raise ValueError(f"AUDIT-C item 1: value {responses[0]} out of range 0-4")
    for i in (1, 2):
        if not 0 <= responses[i] <= 4:
            raise ValueError(f"AUDIT-C item {i+1}: value {responses[i]} out of range 0-4")

    total = sum(responses)

    # Source-caveat comment only (CVR-016 condition 3 / ADR-033 decision 2)
    # — NO behavior change, thresholds byte-frozen this mission. Two
    # independent Korean-population studies (docs/ai/item_bank_v1_sources.md
    # §5.4/§A6) suggest substantially higher cutoffs than the international
    # standard below: Seong et al. 2009 (N=302 Korean men, full-PDF-read)
    # found an optimal cutoff of >= 8; Woo et al. 2017 (N=509, summary-basis)
    # found men >= 7 / women >= 6. Neither study's item wording is confirmed
    # identical to this project's SBIRT-Oregon-sourced AUDIT-C text. Reported
    # to the user as an open disposition question, not applied here — see
    # `src.scoring.item_bank.AUDIT_C_THRESHOLD_CAVEAT`, attached to the F3
    # artifact by `src.f3.run_f3_administration` for AUDIT-C outcomes.
    if patient_sex == "female":
        threshold = 3
    else:
        threshold = 4  # male or unknown

    if total >= threshold:
        severity = "hazardous_drinking"
        action = "clinician_review"
    else:
        severity = "low_risk"
        action = "none"

    return ScoreResult(
        scale_name="AUDIT-C",
        total_score=total,
        max_score=12,
        severity=severity,
        interpretation=f"AUDIT-C {total}점 (threshold {threshold}): {severity}",
        recommended_action=action,
    )


# ── Public API ───────────────────────────────────────────────────────

_SCORERS = {
    "PHQ-9": _score_phq9,
    "GAD-7": _score_gad7,
    "PHQ-4": _score_phq4,
    "WHO-5": _score_who5,
    "AUDIT-C": _score_audit_c,
}

SUPPORTED_SCALES: frozenset[str] = frozenset(_SCORERS.keys())


def score_survey(
    scale_name: str,
    responses: list[int],
    *,
    patient_sex: str = "unknown",
) -> ScoreResult:
    """Score a standardised psychiatric survey.

    Args:
        scale_name: One of PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C
        responses: List of integer item responses
        patient_sex: "male", "female", or "unknown" (used by AUDIT-C)

    Returns:
        ScoreResult with total_score, severity, critical items, etc.

    Raises:
        ValueError: Invalid scale name, wrong item count, or out-of-range values.
    """
    scorer = _SCORERS.get(scale_name)
    if scorer is None:
        raise ValueError(
            f"Unsupported scale '{scale_name}'. Supported: {sorted(SUPPORTED_SCALES)}"
        )

    if scale_name == "AUDIT-C":
        return scorer(responses, patient_sex=patient_sex)
    return scorer(responses)
