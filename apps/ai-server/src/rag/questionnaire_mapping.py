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

CVR-003 Findings 1/3 (W5 addendum, PLAN-2026-W28-Q W5 addendum mission):
the mood row's mania/bipolar-blind-spot caveat and the substance row's
AUDIT-C consumption-vs-dependence caveat previously existed only as the
per-row rationale comments below — they now ALSO have a machine-readable
home in `CLASSIFICATION_TO_CAVEAT` (a per-row caveat column paralleling
`CLASSIFICATION_TO_SCALE`, keyed on the same classification), so a
downstream reader of the actual `AIPredictedDiseaseOutput.recommendation_caveat`
field (never invented at the schema layer — populated from this table by
`f2.py`, same discipline as `recommended_questionnaire`) sees the caveat
alongside the recommendation, not only in this source comment.
"""

from __future__ import annotations

import logging

from src.rag.ontology import DISEASES
from src.schemas.domain_inference import DomainName
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
    # Caveat (CVR-003 Finding 1, ADOPTED, now machine-readable via
    # CLASSIFICATION_TO_CAVEAT below): PHQ-9 screens depressive symptom
    # burden only, not manic/hypomanic history — for
    # bipolar-affective-disorder/cyclothymic-disorder specifically this is
    # a partial-construct match, not a full one. Recommended over no
    # questionnaire because a depression-severity read is still clinically
    # useful, but the partial-fit caveat must reach the actual artifact, not
    # live only in this comment (CVR-003 Finding 1's binding disposition).
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
    # slots into this SAME row with zero code change here. Caveat (CVR-003
    # Finding 3, ADOPTED via this same W5 addendum mechanism): AUDIT-C is a
    # consumption/frequency screener, not a dependence-severity or
    # withdrawal-acuity instrument — see CLASSIFICATION_TO_CAVEAT below.
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

# ── Classification -> recommendation caveat (or None) ──────────────────────
#
# CVR-003 Findings 1/3 (W5 addendum, PLAN-2026-W28-Q W5 addendum mission,
# `discussion.md` "CVR-003 folded" disposition, 2026-07-11): a per-row
# caveat "column", keyed on the SAME classification as
# CLASSIFICATION_TO_SCALE above, so `resolve_questionnaire_caveat_for_*`
# below always describes the SAME row a `resolve_questionnaire_for_*` call
# just resolved. `None` means "no disclosed caveat beyond the scale's
# general non-diagnostic framing" — not "no scale" (a `None`-scale
# classification, e.g. `ocd`, also carries `None` here; there is no
# recommendation to caveat). Only two rows carry a caveat today (the two
# CVR-003 named, Findings 1 and 3); every other classification is an
# explicit `None` to keep this table's key set exactly matching
# CLASSIFICATION_TO_SCALE's (asserted below), so a future new
# classification cannot silently fall through either table.
CLASSIFICATION_TO_CAVEAT: dict[str, str | None] = {
    # mood — CVR-003 Finding 1 (major, ADOPTED). Exact content per this
    # W5 addendum mission's brief.
    "mood": (
        "PHQ-9 screens depressive-symptom burden only, does not screen "
        "manic/hypomanic symptoms — bipolar-spectrum presentations need "
        "clinician follow-up regardless of score."
    ),
    "anxiety": None,
    "ocd": None,
    "trauma": None,
    "psychotic": None,
    "personality": None,
    "neurodevelopmental": None,
    # substance — CVR-003 Finding 3 (minor, ADOPTED via this same
    # mechanism, "zero extra cost, CVR-flagged" per orchestrator
    # disposition).
    "substance": (
        "AUDIT-C screens alcohol consumption/frequency (hazardous-use "
        "pattern) only, not dependence severity or withdrawal acuity — for "
        "a dependence-level presentation, a result here is a first-line/"
        "gateway signal, not a severity determination; clinician follow-up "
        "is required regardless of score."
    ),
    "somatic": None,
    "neurocognitive": None,
}

# Fail fast at import time: key sets must match exactly — every
# CLASSIFICATION_TO_SCALE row has an explicit (possibly None) caveat
# disposition, and this table never invents a caveat for a classification
# CLASSIFICATION_TO_SCALE doesn't know about.
if set(CLASSIFICATION_TO_CAVEAT) != set(CLASSIFICATION_TO_SCALE):
    raise AssertionError(
        "CLASSIFICATION_TO_CAVEAT key set must exactly match "
        f"CLASSIFICATION_TO_SCALE's: {set(CLASSIFICATION_TO_CAVEAT) ^ set(CLASSIFICATION_TO_SCALE)}"
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


def resolve_questionnaire_caveat_for_classification(classification: str) -> str | None:
    """Look up the disclosed caveat (CVR-003 Findings 1/3) for a `DISEASES`
    classification value -- the SAME classification
    :func:`resolve_questionnaire_for_classification` resolves a scale for.

    Returns `None` both when the classification has no disclosed caveat
    (the common case -- most rows carry no caveat beyond the scale's
    general non-diagnostic framing) and for an unrecognized classification
    (defensive, mirrors the scale resolver above; should not happen once
    the CLASSIFICATION_TO_CAVEAT/CLASSIFICATION_TO_SCALE key-set-equality
    assertion above is green).
    """
    if classification not in CLASSIFICATION_TO_CAVEAT:
        logger.warning(
            "questionnaire_mapping.unmapped_classification_for_caveat "
            "classification=%r -- no recommendation_caveat will be set",
            classification,
        )
        return None
    return CLASSIFICATION_TO_CAVEAT[classification]


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


def resolve_questionnaire_caveat_for_disease_name_ko(disease_name_ko: str) -> str | None:
    """Look up the disclosed caveat (CVR-003 Findings 1/3) for a disease by
    its Korean display name -- the SAME lookup path
    :func:`resolve_questionnaire_for_disease_name_ko` uses, so `f2.py`'s
    population code derives `recommendation_caveat` from the identical
    `candidates[0].disease` value it already uses for
    `recommended_questionnaire`.

    Returns `None` if the name is not a recognized ontology disease name
    (e.g. a synthetic test marker, or DB drift from `DISEASES`) or if its
    classification has no disclosed caveat.
    """
    classification = _NAME_KO_TO_CLASSIFICATION.get(disease_name_ko)
    if classification is None:
        return None
    return resolve_questionnaire_caveat_for_classification(classification)


def resolve_questionnaire_for_disease_slug(slug: str) -> ScaleName | None:
    """Look up the recommended scale for a disease by its ontology slug
    (`rag.ontology.DISEASES` key) -- the structural-check entry point."""
    entry = DISEASES.get(slug)
    if entry is None:
        return None
    return resolve_questionnaire_for_classification(entry[3])


def resolve_questionnaire_caveat_for_disease_slug(slug: str) -> str | None:
    """Look up the disclosed caveat (CVR-003 Findings 1/3) for a disease by
    its ontology slug (`rag.ontology.DISEASES` key) -- the structural-check
    entry point, paralleling :func:`resolve_questionnaire_for_disease_slug`."""
    entry = DISEASES.get(slug)
    if entry is None:
        return None
    return resolve_questionnaire_caveat_for_classification(entry[3])


# ── DomainName (F2 domain_candidates) -> recommended scale ─────────────────
#
# BUG-031: a SEPARATE, parallel table from `CLASSIFICATION_TO_SCALE` above —
# `schemas.domain_inference.DomainName` (F2's `domain_candidates[].domain`
# field, the model-facing 9-value enum) is NOT the same taxonomy as
# `rag.ontology.DISEASES`' classification field (`CLASSIFICATION_TO_SCALE`'s
# key set): DomainName has no `mood`/`ocd`/`personality`/`neurodevelopmental`/
# `somatic`/`neurocognitive` values and DISEASES-classification has no
# `depression`/`alcohol`/`sleep`/`psychosis`/`other`/`panic` values. Every
# `DISEASES` entry whose surface text concerns panic attacks (e.g.
# `acute-panic-attack`, `signs-of-panic-attack`) already classifies as
# `"anxiety"` in `rag/ontology.py` and therefore already resolves to GAD-7
# via `CLASSIFICATION_TO_SCALE` above with ZERO code change there — this
# table exists for the DIFFERENT call site that reasons over F2's own
# `DomainCandidate.domain` value directly (never the disease-name path),
# extended here to cover the new `"panic"` `DomainName` value the SAME way:
# GAD-7, per the identical anxiety-family precedent (DSM-5 classifies Panic
# Disorder under Anxiety Disorders; `docs/ai/golden_labels_f1f2.md` VP-004's
# own reasoning cites the same precedent for its panic->anxiety mapping).
# Not wired into any production call site as of this fix (no current caller
# resolves a questionnaire from `DomainCandidate.domain` directly — F2's
# `recommended_questionnaire` is derived from the disease-name path only,
# `f2.py:565`); kept available so a future domain-candidate-triggered
# recommendation (e.g. CVR-028 Finding 6's "intake-time AUDIT/CAGE trigger
# keyed off domain-candidate presence") has a ready, reviewed mapping to use
# rather than inventing one ad hoc. `None` follows the same no-forced-
# mismatch discipline as `CLASSIFICATION_TO_SCALE` (`"other"` explicitly has
# no construct-valid scale among the 5 `SUPPORTED_SCALES`).
DOMAIN_TO_SCALE: dict[DomainName, ScaleName | None] = {
    "anxiety": "GAD-7",
    "panic": "GAD-7",  # anxiety-family precedent (DSM-5: Panic Disorder is an anxiety disorder)
    "depression": "PHQ-9",
    "alcohol": "AUDIT-C",
    "substance": "AUDIT-C",
    "trauma": None,  # PTSD/acute-stress construct not covered — same rationale as "trauma" above
    "sleep": None,  # no dedicated sleep-disorder scale among SUPPORTED_SCALES
    "psychosis": None,  # same no-forced-mismatch rationale as "psychotic" row above
    "other": None,
}

# Fail fast at import time — same discipline as CLASSIFICATION_TO_SCALE:
# every DomainName value must have an explicit (possibly None) disposition,
# and every non-None value must be a scale this project actually supports.
_DOMAIN_NAME_VALUES = set(DomainName.__args__)  # type: ignore[attr-defined]
if set(DOMAIN_TO_SCALE) != _DOMAIN_NAME_VALUES:
    raise AssertionError(
        f"DOMAIN_TO_SCALE key set must exactly match DomainName's: "
        f"{set(DOMAIN_TO_SCALE) ^ _DOMAIN_NAME_VALUES}"
    )
for _domain, _domain_scale in DOMAIN_TO_SCALE.items():
    if _domain_scale is not None and _domain_scale not in SUPPORTED_SCALES:
        raise AssertionError(
            f"DOMAIN_TO_SCALE[{_domain!r}] = {_domain_scale!r} is not in "
            f"SUPPORTED_SCALES {sorted(SUPPORTED_SCALES)}"
        )


def resolve_questionnaire_for_domain_name(domain: str) -> ScaleName | None:
    """Look up the recommended scale for an F2 `DomainCandidate.domain`
    value directly (the `DOMAIN_TO_SCALE` table above) — NOT the same lookup
    path as :func:`resolve_questionnaire_for_disease_name_ko`/
    :func:`resolve_questionnaire_for_classification`, which key on
    `rag.ontology.DISEASES`, a different taxonomy.

    Returns `None` both for an explicit no-questionnaire domain and for an
    unrecognized domain value (logged as a warning — should not happen once
    `DomainName`'s Literal validates the input, but this function stays
    defensive against a future unmapped domain reaching a live call site).
    """
    if domain not in DOMAIN_TO_SCALE:
        logger.warning(
            "questionnaire_mapping.unmapped_domain_name domain=%r -- "
            "no recommended_questionnaire will be resolved",
            domain,
        )
        return None
    return DOMAIN_TO_SCALE[domain]  # type: ignore[index]
