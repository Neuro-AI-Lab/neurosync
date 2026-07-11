"""Disease-classification -> recommended-questionnaire static mapping.

PLAN-2026-W28-Q W5 (disease<->questionnaire linkage), plan §3 "Disease
questionnaire linkage" row / §9 answer #5a: "Team-authored static mapping,
clinical-validator review. Scales: PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C; the new
AUD entry maps to AUDIT-C (already supported)." This module is the
team-authored code-side half; clinical-validator content review is a
separate, later gate (not performed by this module or its tests).

Binding no-forced-mismatch rule (`CVR-001` weak-point register item 7,
plan §3): a classification the 5 `SUPPORTED_SCALES` scales cannot
construct-validly cover maps to `None` — an explicit "no questionnaire"
value with a documented reason — never a forced best-effort fit. OCD/PTSD/
psychosis/ADHD-territory classifications are the canonical examples named
in the register; this module extends the same discipline to every
classification `rag.ontology.DISEASES` currently ships.

Mapping is keyed on `rag.ontology.DISEASES`' classification field (index 3
of each disease 5-tuple), not on individual disease slugs — matching how
the plan names this linkage ("`rag/ontology.py`'s `DISEASES` classification
field -> a `ScaleName`"). Every classification value currently shipped in
`DISEASES` must appear as a key in `CLASSIFICATION_TO_SCALE` below; this is
enforced both by the module-level assertions here (fail fast on a bad
scale name) and by `tests/test_questionnaire_mapping.py`'s structural
offline check (fail fast on a classification silently falling through to
"unmapped").

Non-diagnostic framing: every non-`None` mapping is a "consider
administering this standardized self-report scale" recommendation, never
a diagnostic claim and never a scale score itself (`REV-013` §4 lineage —
the same discipline that keeps `similarity_score` off the
probability/confidence naming).

W6 forward-compat note: the AUD ontology addition (`alcohol-use-disorder`,
plan §9) classifies as `substance` (plan: "Mapping consequence:
Classification `substance` -> AUDIT-C ... low-risk addition") — it slots
into the existing `"substance"` row below with ZERO code change here, since
this mapping is keyed on classification, not disease slug.
"""

from __future__ import annotations

import logging

from src.rag.ontology import DISEASES
from src.scoring.survey_scorer import SUPPORTED_SCALES, ScaleName

logger = logging.getLogger(__name__)

# ── Classification -> recommended scale (or None), with per-row rationale ──
#
# Each row's rationale cites the scale's own construct focus
# (`survey_scorer.py`'s module docstring citations) and why it does/doesn't
# construct-validly cover this classification. Team-authored per answer
# #5a; clinical-validator reviews this content next — this table is a
# deterministic code-side default, not a clinical adequacy sign-off.
CLASSIFICATION_TO_SCALE: dict[str, ScaleName | None] = {
    # mood — PHQ-9 (Kroenke et al., 2001) is this project's only
    # depression-severity scale; the closest standardized proxy for the
    # depressive-episode / bipolar / cyclothymic / seasonal / PMDD
    # presentations bucketed under "mood" in DISEASES today.
    # Caveat for clinical-validator review: PHQ-9 screens depressive
    # symptom burden only, not manic/hypomanic history — for
    # bipolar-affective-disorder/cyclothymic-disorder specifically this is
    # a partial-construct match, not a full one. Recommended over no
    # questionnaire because a depression-severity read is still clinically
    # useful pending the validator's content verdict, but this partial-fit
    # caveat must be surfaced in that review, not silently absorbed here.
    "mood": "PHQ-9",
    # anxiety — GAD-7 (Spitzer et al., 2006) is this project's only anxiety
    # scale; covers generalized-anxiety-disorder directly and is the
    # closest available construct match for the panic-attack entries (not
    # panic-specific, but the best fit among the 5 SUPPORTED_SCALES).
    "anxiety": "GAD-7",
    # ocd — NO SCALE. Obsessive-compulsive-disorder's core construct
    # (obsessions/compulsions) is not covered by PHQ-9/GAD-7/PHQ-4/WHO-5/
    # AUDIT-C. Forcing GAD-7 would misrepresent OCD as generalized anxiety.
    # Explicit no-forced-mismatch (CVR-001 weak-point register item 7,
    # OCD named verbatim as no-coverage territory).
    "ocd": None,
    # trauma — NO SCALE. DISEASES currently buckets
    # post-traumatic-stress-disorder together with acute-stress-disorder/
    # adjustment-disorder/burnout under this single classification (coarser
    # than per-disease). PTSD's construct (PCL-5 territory) is not covered
    # by any of the 5 scales, and since this mapping operates at
    # classification granularity, forcing any scale onto "trauma" would
    # also force it onto PTSD — the exact case CVR-001 item 7 names.
    # Explicit no-forced-mismatch; flagged for clinical-validator as a
    # candidate for a future finer per-disease split if
    # adjustment-disorder/burnout alone would otherwise warrant PHQ-4.
    "trauma": None,
    # psychotic — NO SCALE. Schizophrenia's core construct
    # (hallucinations/delusions/disorganized thought) is not covered by any
    # of the 5 scales. Explicit no-forced-mismatch (CVR-001 item 7,
    # psychosis named verbatim as no-coverage territory).
    "psychotic": None,
    # personality — NO SCALE. Borderline personality disorder's construct
    # (identity disturbance, interpersonal instability, chronic emptiness,
    # impulsivity) is not covered by any of the 5 scales.
    "personality": None,
    # neurodevelopmental — NO SCALE. Autism/Asperger/ADHD/FASD. ADHD is
    # explicitly named in CVR-001 item 7 as no-coverage territory; none of
    # the 5 scales construct-validly screen any neurodevelopmental
    # presentation in this bucket.
    "neurodevelopmental": None,
    # substance — AUDIT-C (Bush et al., 1998), this project's only
    # substance-use scale. Covers alcohol-intoxication/alcohol-withdrawal
    # today; per plan §9's "Mapping consequence" row, the W6 AUD ontology
    # entry (`alcohol-use-disorder`) also classifies as "substance" and
    # slots into this SAME row with zero code change here.
    "substance": "AUDIT-C",
    # somatic — NO SCALE. Conversion disorder's construct (functional
    # neurological symptoms without a neurological cause) is not covered by
    # any of the 5 scales; forcing PHQ-4 would misrepresent a functional
    # neurological disorder as generalized mood/anxiety distress.
    "somatic": None,
    # neurocognitive — NO SCALE. Alzheimer's disease / dementia with Lewy
    # bodies / HIV dementia need a cognitive-impairment instrument (MMSE/
    # MoCA territory); none of the 5 scales screen cognitive impairment.
    "neurocognitive": None,
}

# Fail fast at import time: every value must be None or a scale this
# project actually supports (`survey_scorer.SUPPORTED_SCALES`) — guards
# against a future typo shipping an unscoreable scale name.
for _cls, _scale in CLASSIFICATION_TO_SCALE.items():
    if _scale is not None and _scale not in SUPPORTED_SCALES:
        raise AssertionError(
            f"CLASSIFICATION_TO_SCALE[{_cls!r}] = {_scale!r} is not in "
            f"SUPPORTED_SCALES {sorted(SUPPORTED_SCALES)}"
        )


def resolve_questionnaire_for_classification(classification: str) -> ScaleName | None:
    """Look up the recommended scale for a `DISEASES` classification value.

    Returns `None` both for an explicit no-questionnaire classification
    (see the rationale comments above) and for an unrecognized
    classification (logged as a warning — should never happen once
    `tests/test_questionnaire_mapping.py`'s structural offline check is
    green in CI, but this function stays defensive against a future
    unmapped classification reaching a live population path).
    """
    if classification not in CLASSIFICATION_TO_SCALE:
        logger.warning(
            "questionnaire_mapping.unmapped_classification classification=%r "
            "-- no recommended_questionnaire will be set",
            classification,
        )
        return None
    return CLASSIFICATION_TO_SCALE[classification]


# ── Disease name (Korean) -> recommended scale, derived reverse lookup ────
#
# `f2.py`'s live-population path carries candidates by `disease` (Korean
# display name, `rag.disease.name_ko` — see `rag/retrieval.py`'s
# `match_diseases_for_chunk_text`), not by ontology slug. This reverse
# lookup lets the container field be populated without any DB/retrieval
# schema change. Built once, at import time, directly from `DISEASES` — a
# name collision would silently make this table wrong, so uniqueness is
# asserted rather than assumed.
_NAME_KO_TO_CLASSIFICATION: dict[str, str] = {}
for _slug, (_name_en, _name_ko, _kcd, _classification, _summary) in DISEASES.items():
    if _name_ko in _NAME_KO_TO_CLASSIFICATION:
        raise AssertionError(
            f"Duplicate DISEASES name_ko {_name_ko!r} -- "
            "questionnaire_mapping's reverse lookup assumes uniqueness"
        )
    _NAME_KO_TO_CLASSIFICATION[_name_ko] = _classification


def resolve_questionnaire_for_disease_name_ko(disease_name_ko: str) -> ScaleName | None:
    """Look up the recommended scale for a disease by its Korean display
    name -- the shape `AIPredictedDiseaseCandidate.disease` actually
    carries on a live-populated run.

    Returns `None` if the name is not a recognized ontology disease name
    (e.g. a synthetic test marker, or DB drift from `DISEASES`) or if its
    classification has no construct-valid scale (see rationale above).
    """
    classification = _NAME_KO_TO_CLASSIFICATION.get(disease_name_ko)
    if classification is None:
        return None
    return resolve_questionnaire_for_classification(classification)


def resolve_questionnaire_for_disease_slug(slug: str) -> ScaleName | None:
    """Look up the recommended scale for a disease by its ontology slug
    (`rag.ontology.DISEASES` key) -- the structural-check entry point."""
    entry = DISEASES.get(slug)
    if entry is None:
        return None
    return resolve_questionnaire_for_classification(entry[3])
