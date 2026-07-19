"""Schemas for the DomainInference agent (F2, PLAN-2026-W28-C).

Output contract is fixed by the approved plan (`discussion.md` PLAN-2026-W28-C
C-2, REV-006 conditions): every ``domain_candidate`` must carry >=1 evidence
item citing a source that was ACTUALLY available this run (a retrieved RAG
chunk or an F1 patient utterance) — enforced here at the Pydantic level, not
left to prompt discipline alone (REV-006 issue #3's lesson).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput
from src.schemas.handoff import ScaleScore

# BUG-031 (8->9): "panic" added per EXP-025's live reproduction — the LLM
# emitted `domain="panic"` for 5/10 VP-004 (`fluctuating_panic_recurrence`
# arc) EXP-025 sessions, an out-of-enum `literal_error` under the original
# 8-value enum (per-candidate salvage above now drops only that ONE
# candidate instead of the whole response, but the LLM's own panic-naming
# behavior is real and recurring, not a one-off — worth a native enum value
# rather than perpetually salvaging it). `docs/ai/golden_labels_f1f2.md`'s
# VP-004 golden label currently maps panic->anxiety with the explicit
# rationale "the domain enum has no panic value" (line 29/43) — that
# rationale is now stale; flagged for data/CVR review, not changed here
# (golden labels are data-agent-owned, out of this fix's scope).
DomainName = Literal[
    "anxiety",
    "depression",
    "alcohol",
    "substance",
    "trauma",
    "sleep",
    "psychosis",
    "other",
    "panic",
]
# PLAN-2026-W28-Q W1 (plan §3 row 1): "ocr_document" added for product
# auditability — document-origin evidence (prescription/diagnosis PDFs) must
# be citable/auditable in F2 output. Naming matches
# InputNormalizerInput.input_type's existing "ocr_document" literal value
# (src/schemas/input_normalizer.py). This is a type-level + defensive-code
# extension only — no OCR text is wired into DomainInferenceInput or the
# certified domain_inference prompt this mission (AVC-17: no prompt-file
# edit); every exhaustiveness site that pattern-matches EvidenceSourceType
# now recognizes the value instead of misclassifying it as unknown.
EvidenceSourceType = Literal["rag_chunk", "utterance", "ocr_document"]
RetrievalMode = Literal["rag", "llm_only"]


class DomainEvidence(BaseModel):
    """A single evidence citation for a domain candidate.

    ``source_id`` must reference a source that was ACTUALLY provided to the
    model this run (a ``retrieved_chunks[].chunk_id`` or a ``turns[].turn``-
    derived utterance id, e.g. ``turn_3``) — verified at runtime by
    ``src.eval.f2_grounding`` (code-level, not prompt-only).
    """

    source_type: EvidenceSourceType
    source_id: str = Field(..., min_length=1)
    quote: str = Field(..., min_length=1, description="Verbatim-ish quote from the source text")


class DomainCandidate(BaseModel):
    """One mental-health domain candidate with grounded evidence."""

    domain: DomainName
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: list[DomainEvidence] = Field(
        ..., min_length=1, description="No evidence, no candidate (plan C-2 hard rule)"
    )
    recommended_surveys: list[str] | None = Field(
        default=None, description="e.g. ['GAD-7', 'PHQ-9']"
    )


class DepartmentCandidate(BaseModel):
    """A candidate referring department. May reference a domain candidate."""

    department: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    domain_ref: DomainName | None = Field(
        default=None,
        description="Must equal one of the domain values in domain_candidates, or be omitted "
        "(an orphan reference is a validity failure — src.eval.f2_grounding checks it)",
    )


class DomainInferenceLLMResponse(BaseModel):
    """Exact JSON schema the LLM must produce (code-parsed, model-facing contract)."""

    domain_candidates: list[DomainCandidate] = Field(default_factory=list, max_length=3)
    department_candidates: list[DepartmentCandidate] = Field(default_factory=list)
    summary: str = Field(default="")
    additional_questions: list[str] | None = Field(default=None)


# ── Stage 1 (code-side retrieval) primitives, fed into the agent as input ──


class RetrievedChunk(BaseModel):
    """One Stage-1 RAG chunk, WITH its full text (REV-006 #1: audit replay)."""

    chunk_id: str = Field(..., min_length=1, description="e.g. 'case_card:123', 'qa:45'")
    source_type: str = Field(..., description="case_card | qa (rag.* table origin)")
    text: str = Field(..., description="Full chunk text — stored so quotes can be verified")
    score: float | None = Field(default=None)


class UtteranceTurn(BaseModel):
    """One F1 patient utterance, used to build utterance-type evidence ids."""

    turn: int
    patient_message: str = Field(..., min_length=1)


class RetrievalMeta(BaseModel):
    """Stage-1 retrieval outcome — always present, mode reflects reality (REV-006 #6)."""

    mode: RetrievalMode
    chunks_returned: int = Field(default=0, ge=0)
    chunk_ids: list[str] = Field(default_factory=list)
    queries: list[str] | None = Field(default=None)


# ── Agent I/O ──────────────────────────────────────────────────────────────


class DomainInferenceInput(AgentInput):
    """Input to DomainInferenceAgent — F1 (+ optional F3) context, plan C-2."""

    final_slots: dict[str, str] = Field(..., description="F1 final_slots (12 keys)")
    session_ctrs: int = Field(..., ge=1, le=5)
    crisis_triggered: bool
    crisis_turn: int | None = Field(default=None)
    is_first_visit: bool

    turns: list[UtteranceTurn] = Field(default_factory=list)
    prior_handoff: str | None = Field(default=None)
    probe_events: list[dict] = Field(default_factory=list)
    scale_scores: list[ScaleScore] = Field(default_factory=list)

    # Stage-1 output, assembled by f2.py BEFORE calling the agent.
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    retrieval_mode: RetrievalMode = Field(default="llm_only")
    queries: list[str] = Field(default_factory=list)


class DomainInferenceOutput(AgentOutput):
    """Output from DomainInferenceAgent — LLM candidates + code-filled retrieval_meta."""

    domain_candidates: list[DomainCandidate] = Field(default_factory=list, max_length=3)
    department_candidates: list[DepartmentCandidate] = Field(default_factory=list)
    summary: str = Field(default="")
    retrieval_meta: RetrievalMeta
    additional_questions: list[str] | None = Field(default=None)
    # BUG-017 phase A (diagnostic instrumentation, 2026-07-08): the adapter's
    # raw ChatResponse.finish_reason/.usage (src/adapters/base.py), captured
    # so a future RAG-mode truncation hypothesis (finish_reason == "length")
    # is falsifiable from this agent's own output/logs, on success AND on
    # parse/schema failure alike. None whenever no ChatResponse was ever
    # obtained (transport failure before any LLM response existed).
    finish_reason: str | None = Field(default=None)
    usage: dict[str, int] | None = Field(default=None)
    # BUG-019 (2026-07-09): the schema-validation-failure root cause was
    # undiagnosable because neither the raw LLM response text nor the
    # Pydantic ValidationError's field-level detail was ever persisted —
    # only a bare `exc.error_count()` integer reached `reason_summary`.
    # Mirrors BUG-017 phase A's finish_reason/usage precedent: populated on
    # a parse/schema failure (JSON-parse OR schema-validation branch alike,
    # for symmetry), `None` on success (redundant with the already-
    # structured domain_candidates/etc.) and on a transport failure (no
    # ChatResponse was ever obtained — same None convention as
    # finish_reason/usage above). `default=None` — non-breaking for
    # existing callers/artifacts built before this field existed.
    raw_response: str | None = Field(
        default=None,
        description="Raw LLM response text, present only on a parse/schema "
        "failure. Model output, not patient PII by construction.",
    )
    validation_errors: list[dict[str, Any]] | None = Field(
        default=None,
        description="Pydantic ValidationError.errors() field-level detail "
        "(which field, what value, what constraint) — present only on a "
        "schema-validation failure; None on a JSON-parse failure (no "
        "ValidationError was ever raised) or success.",
    )
