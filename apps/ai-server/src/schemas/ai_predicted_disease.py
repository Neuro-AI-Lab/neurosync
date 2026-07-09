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
inside `domain_candidates`, `summary`, or any handoff-shaped object. Shipped
now with `mode="experimental_unpopulated"`, empty `candidates`, and an
honest `reason_summary`. Live population (`mode="rag_live"`) is GATED on
RAG-arm certification — currently UNCERTIFIED per ADR-016 (2/3 conditions
met; VP-003 RAG clean n=2 re-verification unmet, tracked as BUG-019, open;
no partial/per-persona certification licensed, REV-012 §4). The
disease-record SOURCE (a `case_card`/`qa` heuristic reuse vs. a future
`rag.disease` embedding column, DATASET-005 addendum Key finding #0) is NOT
resolved by this module — it only defines the shape.

Labeling (REV-013 §4, binding): `similarity_score`, never `probability`/
`confidence`/`확률`. Each candidate's score is independent and
`[0,1]`-bounded; nothing in this module computes or exposes a
softmax/normalized view across the top-5.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
