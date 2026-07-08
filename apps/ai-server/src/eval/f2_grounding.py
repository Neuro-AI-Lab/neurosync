"""F2 evidence whitelist — code-level fabrication check for DomainInferenceAgent output.

PLAN-2026-W28-C C-3/C-4, REV-006 issue #1 (resolved by this module): every
evidence item cited by a domain candidate must (a) reference a source_id that
was ACTUALLY returned/available this run — a retrieved RAG chunk_id or an F1
utterance id — AND (b) have its quote lexically supported by that source's
ACTUAL TEXT. Checking (a) alone (source_id membership) would let a model cite
a real chunk_id next to an invented quote and still pass — the exact
"fabrication-0 hard gate" gap REV-006 flagged (rag_chunk evidence was
previously verifiable only by id, never by content, unlike utterance evidence
which already reused `has_lexical_evidence`).

Pure, no I/O, no LLM — mirrors `src.grounding`'s verdict-object style so audit
output stays uniform across F1 and F2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.grounding import has_lexical_evidence
from src.schemas.domain_inference import DepartmentCandidate, DomainCandidate

VERDICT_ACCEPTED = "accepted"
VERDICT_REJECTED_UNKNOWN_SOURCE = "rejected_unknown_source"
VERDICT_REJECTED_QUOTE_MISMATCH = "rejected_quote_mismatch"
VERDICT_REJECTED_UNKNOWN_TYPE = "rejected_unknown_source_type"

_ALL_VERDICTS = (
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    VERDICT_REJECTED_QUOTE_MISMATCH,
    VERDICT_REJECTED_UNKNOWN_TYPE,
)


@dataclass(frozen=True)
class EvidenceVerdict:
    """Whitelist verdict for one evidence item."""

    domain: str
    source_type: str
    source_id: str
    quote: str
    verdict: str
    reason: str

    @property
    def accepted(self) -> bool:
        return self.verdict == VERDICT_ACCEPTED


def check_evidence(
    source_type: str,
    source_id: str,
    quote: str,
    *,
    chunk_texts: Mapping[str, str],
    utterances: Mapping[str, str],
    domain: str = "",
) -> EvidenceVerdict:
    """Whitelist check for a single evidence item.

    Args:
        chunk_texts: {chunk_id: full_text} for chunks ACTUALLY returned this
            run (Stage 1 output, e.g. ``{"case_card:12": "..."}``).
        utterances: {utterance_id: text} for F1 patient utterances ACTUALLY
            available this run (e.g. ``{"turn_3": "..."}``).
    """
    quote = (quote or "").strip()
    source_id = (source_id or "").strip()

    if source_type == "rag_chunk":
        text = chunk_texts.get(source_id)
        if text is None:
            return EvidenceVerdict(
                domain, source_type, source_id, quote, VERDICT_REJECTED_UNKNOWN_SOURCE,
                f"source_id {source_id!r} is not among the chunk_ids actually "
                "retrieved this run",
            )
    elif source_type == "utterance":
        text = utterances.get(source_id)
        if text is None:
            return EvidenceVerdict(
                domain, source_type, source_id, quote, VERDICT_REJECTED_UNKNOWN_SOURCE,
                f"source_id {source_id!r} is not among the F1 utterances actually "
                "available this run",
            )
    else:
        return EvidenceVerdict(
            domain, source_type, source_id, quote, VERDICT_REJECTED_UNKNOWN_TYPE,
            f"unknown source_type {source_type!r} — must be rag_chunk|utterance",
        )

    if not quote:
        return EvidenceVerdict(
            domain, source_type, source_id, quote, VERDICT_REJECTED_QUOTE_MISMATCH,
            "empty quote",
        )

    # Same lexical-grounding primitive F1 uses for utterance evidence — now
    # applied to rag_chunk text too (REV-006 #1: content check, not id-only).
    if not has_lexical_evidence(quote, [text]):
        return EvidenceVerdict(
            domain, source_type, source_id, quote, VERDICT_REJECTED_QUOTE_MISMATCH,
            f"quote is not lexically supported by the {source_type}'s actual text",
        )

    return EvidenceVerdict(
        domain, source_type, source_id, quote, VERDICT_ACCEPTED,
        f"quote lexically matches the retrieved {source_type} text",
    )


def audit_domain_candidates(
    domain_candidates: list[DomainCandidate],
    *,
    chunk_texts: Mapping[str, str],
    utterances: Mapping[str, str],
) -> tuple[list[EvidenceVerdict], dict[str, int]]:
    """Run the whitelist check over every evidence item of every candidate.

    Returns (verdicts, counts) where counts maps each verdict label to its count.
    """
    verdicts: list[EvidenceVerdict] = []
    for cand in domain_candidates:
        for ev in cand.evidence:
            verdicts.append(
                check_evidence(
                    ev.source_type,
                    ev.source_id,
                    ev.quote,
                    chunk_texts=chunk_texts,
                    utterances=utterances,
                    domain=cand.domain,
                )
            )
    counts = {v: 0 for v in _ALL_VERDICTS}
    for verdict in verdicts:
        counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
    return verdicts, counts


def find_orphan_departments(
    domain_candidates: list[DomainCandidate],
    department_candidates: list[DepartmentCandidate],
) -> list[DepartmentCandidate]:
    """Department candidates whose domain_ref does not match any listed domain.

    A department-derives-from-domain violation (plan C-3/C-4 rollback trigger:
    "고아 department"). A department with no domain_ref at all is NOT an
    orphan — domain_ref is optional per the output contract.
    """
    known = {c.domain for c in domain_candidates}
    return [
        d for d in department_candidates
        if d.domain_ref is not None and d.domain_ref not in known
    ]
