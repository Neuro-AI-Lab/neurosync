"""`EvidenceSourceType` OCR-provenance schema test — PLAN-2026-W28-Q W1
(plan §3 row 1): `Literal["rag_chunk", "utterance"]` gains an `"ocr_document"`
value so document-origin evidence is auditable in F2 output (product need,
not a harness convenience). Covers every exhaustiveness site the value must
be accepted end-to-end at: the Pydantic schema itself, `src.eval.f2_grounding`
(validator), and `src.f2` (provenance-summary serializer) — no live OCR
content is wired into F2's evidence-grounding input yet (out of this
mission's scope — see the module docstring in `f2_grounding.check_evidence`),
so acceptance is verified with an explicit `ocr_texts` mapping standing in
for a future real caller.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

import src.f2 as f2
from src.eval.f2_grounding import (
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    VERDICT_REJECTED_UNKNOWN_TYPE,
    check_evidence,
)
from src.schemas.domain_inference import DomainCandidate, DomainEvidence


class TestEvidenceSourceTypeSchemaAcceptsOcrDocument:
    def test_domain_evidence_accepts_ocr_document_source_type(self) -> None:
        ev = DomainEvidence(
            source_type="ocr_document",
            source_id="ocr:VP-004_prescription",
            quote="에스시탈로프람 20mg 1일 1회",
        )
        assert ev.source_type == "ocr_document"

    def test_domain_evidence_still_rejects_a_genuinely_unknown_type(self) -> None:
        """The type extension does not turn the Literal into an open str —
        a truly invented value is still a Pydantic validation error."""
        with pytest.raises(ValidationError):
            DomainEvidence(
                source_type="garbage",  # type: ignore[arg-type]
                source_id="x",
                quote="x",
            )

    def test_domain_candidate_accepts_ocr_document_evidence(self) -> None:
        cand = DomainCandidate(
            domain="depression",
            confidence=0.5,
            evidence=[
                DomainEvidence(
                    source_type="ocr_document",
                    source_id="ocr:VP-004_prescription",
                    quote="에스시탈로프람 20mg 1일 1회",
                )
            ],
        )
        assert cand.evidence[0].source_type == "ocr_document"


class TestCheckEvidenceOcrDocumentValidator:
    def test_ocr_document_source_id_not_available_rejected_unknown_source(self) -> None:
        """No ocr_texts wired in (default) -> correctly rejected as
        unknown-SOURCE (no evidence, no candidate), NOT unknown-TYPE — the
        type is recognized, the content just isn't available this run."""
        v = check_evidence(
            "ocr_document", "ocr:VP-004_prescription", "에스시탈로프람 20mg",
            chunk_texts={}, utterances={},
        )
        assert v.verdict == VERDICT_REJECTED_UNKNOWN_SOURCE
        assert v.verdict != VERDICT_REJECTED_UNKNOWN_TYPE

    def test_ocr_document_accepted_when_ocr_texts_provided_and_quote_grounded(self) -> None:
        """When a caller DOES supply ocr_texts (the future real-wiring
        case), a lexically-grounded, non-risk quote is accepted exactly
        like rag_chunk/utterance evidence is today."""
        v = check_evidence(
            "ocr_document", "ocr:VP-004_prescription",
            "에스시탈로프람 20mg 1일 1회 처방",
            chunk_texts={}, utterances={},
            ocr_texts={"ocr:VP-004_prescription": "환자에게 에스시탈로프람 20mg 1일 1회 처방함."},
        )
        assert v.verdict == VERDICT_ACCEPTED

    def test_still_unknown_type_for_a_genuinely_invalid_source_type_string(self) -> None:
        """`check_evidence` takes a bare `str` (not the Pydantic Literal) —
        confirms the validator's own exhaustiveness switch still rejects a
        4th, genuinely-unrecognized value as unknown-type, and the updated
        error message names all 3 licensed values."""
        v = check_evidence(
            "garbage", "x", "x", chunk_texts={}, utterances={}, ocr_texts={},
        )
        assert v.verdict == VERDICT_REJECTED_UNKNOWN_TYPE
        assert "ocr_document" in v.reason


class TestF2ProvenanceSummaryCountsOcrDocument:
    def test_provenance_summary_counts_ocr_document_bucket(self) -> None:
        candidates = [
            DomainCandidate(
                domain="depression",
                confidence=0.5,
                evidence=[
                    DomainEvidence(
                        source_type="ocr_document",
                        source_id="ocr:VP-004_prescription",
                        quote="에스시탈로프람 20mg",
                    ),
                    DomainEvidence(
                        source_type="utterance", source_id="turn_1", quote="요즘 잠을 못 자요",
                    ),
                ],
            )
        ]
        counts = f2._build_evidence_provenance_summary(candidates)
        assert counts["ocr_document"] == 1
        assert counts["utterance"] == 1

    def test_provenance_summary_defaults_ocr_document_to_zero(self) -> None:
        """No candidates cite ocr_document -> the bucket is present and 0,
        never silently absent from the summary dict."""
        counts = f2._build_evidence_provenance_summary([])
        assert counts["ocr_document"] == 0
