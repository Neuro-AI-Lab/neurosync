"""Schemas for the "AI 예상질환" (AI-predicted disease) entity — Track B,
PLAN-2026-W28-H, REV-013 §3/§4 (critic ruling), brainstorm design note
`papers/notes/ai-predicted-disease-hpi-isolation-design.md`.

Standalone by design (REV-013 §3 type-layer + call-graph-layer invariants):
this module shares NO base class, field, or inheritance relationship with
`SlotData`/`HandoffInput`/`HandoffOutput` (`src/schemas/handoff.py`) or
`DomainCandidate` (`src/schemas/domain_inference.py`). This module must
never import any of those modules, and none of them may import this one —
qa's Wave-4 adversarial call-graph test enforces the cross-codebase half of
that invariant; this module's own (empty) import list of those modules is
the half it owns directly.

Wiring (this mission, `f2.py`): `_build_artifact` attaches an
`AIPredictedDiseaseOutput.model_dump()` as a SIBLING top-level key
(`"ai_predicted_disease"`) in the saved F2 artifact JSON — never nested
inside `domain_candidates`, `summary`, or any handoff-shaped object.

Live population (`mode="rag_live"`) is now IMPLEMENTED (PLAN-2026-W28-K
Task 3, ADR-020 — RAG-arm certification, ADR-018, is met): `f2.py`
derives candidates from the SAME Stage-1 `raw_chunks` DomainInferenceAgent
already retrieved, via the existing `case_card`/`qa` symptom-keyword ->
`disease_symptom` ontology join (path1; a `rag.disease` embedding column,
path2, is filed as a DB-handoff item, not implemented). A `llm_only`-mode
run (no chunks retrieved) still emits `mode="experimental_unpopulated"`
with empty `candidates` and an honest `reason_summary` — there is nothing
to populate from.

Labeling (REV-013 §4, binding): `similarity_score`, never `probability`/
`confidence`/`확률`. Each candidate's score is independent and
`[0,1]`-bounded; nothing in this module computes or exposes a
softmax/normalized view across the top-5.

Provenance (ADR-020 condition 2): `source_id`/`quote` are OPTIONAL at the
schema level (default `None`) — this preserves backward compatibility with
pre-existing callers (e.g. `tests/test_hpi_isolation.py`'s synthetic-marker
fixture, which constructs a candidate with only `disease`/`similarity_score`
to test HPI isolation, not population correctness) and with the
`experimental_unpopulated` empty-candidates convention. The "no evidence, no
candidate" discipline (mirroring `DomainEvidence`) is enforced at the
POPULATION-CODE level instead (`f2.py`'s live-population path never
constructs a candidate without both fields set) — every `mode="rag_live"`
candidate that ships with >=1 entry always carries real provenance in
practice, checked by `tests/test_ai_predicted_disease.py` and
`tests/test_f2_pipeline.py`.

Disease-questionnaire linkage (PLAN-2026-W28-Q W5, plan §3 "Disease
questionnaire linkage" row / §9 answer #5a): `recommended_questionnaire`
below is populated by `f2.py`'s population code from the team-authored
static classification->scale mapping (`src.rag.questionnaire_mapping`),
never invented at the schema layer. `ScaleName` is imported from
`src.scoring.survey_scorer` — a leaf module with no dependency on the two
forbidden modules named above, so this import does not weaken this
module's standalone-by-design invariant (REV-013 §3): `ScaleName` is a
plain `Literal` type alias, not a class from either forbidden module, and
the survey-scoring module itself imports neither of them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.scoring.survey_scorer import ScaleName

# REV-013 §4(c): fixed, non-model-generated disclaimer sentinel — a constant,
# not text the LLM authors. Kept as a plain `str` field with this constant as
# its default (rather than a `Literal` on the field itself, unlike
# `is_diagnostic` below) because a future copy edit to the exact wording
# should not require widening a type; the *meaning* guarantee ("not a
# diagnosis") is what `is_diagnostic: Literal[False]` fixes at the type
# level. qa's regression coverage should assert this field equals the
# constant below, not merely that it is a non-empty string.
AI_PREDICTED_DISEASE_DISCLAIMER_KO = (
    "이 정보는 AI가 생성한 참고용 예상 질환 후보이며 의학적 진단이 아닙니다. "
    "최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다."
)


class AIPredictedDiseaseCandidate(BaseModel):
    """One AI-predicted-disease candidate.

    `similarity_score`, never a probability (REV-013 §4) — a RAG
    cosine-similarity retrieval signal, independent per candidate,
    `[0,1]`-bounded, never softmax-normalized across the top-5.
    """

    model_config = ConfigDict(extra="forbid")

    disease: str = Field(..., min_length=1)
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "RAG cosine-similarity retrieval signal, NOT a calibrated "
            "probability. Never label/rename this value as 'probability'/"
            "'confidence'/'확률' anywhere it is surfaced (REV-013 §4, "
            "binding). Independent per candidate — no softmax/normalization "
            "is ever computed across the top-5 here."
        ),
    )
    source_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "The winning chunk's chunk_id (e.g. 'case_card:687'), same "
            "convention as DomainEvidence.source_id. Optional at the schema "
            "level for backward compat (see module docstring); always set "
            "by the live-population path (ADR-020 condition 2)."
        ),
    )
    quote: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "A short verbatim excerpt of the winning chunk's own text, "
            "around the matched symptom keyword — same auditability "
            "convention as DomainEvidence.quote. Optional at the schema "
            "level for backward compat (see module docstring); always set "
            "by the live-population path, and always cleared through the "
            "risk-lexicon filter first (VAL-011/ADR-020 condition 1 — a "
            "candidate is DROPPED, never shipped with a redacted/clipped "
            "risk-flagged quote)."
        ),
    )


class AIPredictedDiseaseOutput(BaseModel):
    """Container for the "AI 예상질환" entity.

    Attached as a SIBLING top-level artifact key by `f2.py` — never nested
    inside the handoff object / `SlotData` / `domain_candidates` (REV-013
    §3). Non-diagnostic by construction: `is_diagnostic` is fixed at the
    type level to `Literal[False]`, not merely a runtime default, so a
    future schema edit cannot silently widen it without changing the type
    annotation itself.
    """

    model_config = ConfigDict(extra="forbid")

    candidates: list[AIPredictedDiseaseCandidate] = Field(default_factory=list, max_length=5)
    mode: Literal["experimental_unpopulated", "rag_live"]
    is_diagnostic: Literal[False] = False
    disclaimer: str = Field(default=AI_PREDICTED_DISEASE_DISCLAIMER_KO)
    reason_summary: str = Field(default="")
    recommended_questionnaire: ScaleName | None = Field(
        default=None,
        description=(
            "A standardized self-report scale to CONSIDER administering — "
            "never a diagnosis, and never a scale score/result itself. "
            "Derived from the top-ranked candidate's disease classification "
            "via the team-authored static classification->scale mapping "
            "(src.rag.questionnaire_mapping, PLAN-2026-W28-Q W5, answer "
            "#5a); clinical-validator content review is a separate, later "
            "gate. None when candidates is empty, or when the top "
            "candidate's classification has no construct-valid match among "
            "SUPPORTED_SCALES (e.g. OCD/PTSD/psychosis/ADHD territory — "
            "an explicit no-forced-mismatch result, not a missing value; "
            "see src.rag.questionnaire_mapping for the per-classification "
            "rationale)."
        ),
    )
