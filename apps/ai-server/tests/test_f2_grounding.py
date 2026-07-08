"""src.eval.f2_grounding — F2 evidence whitelist, mock/fixture-based (C-4).

Covers: accept valid chunk/utterance evidence; REJECT hallucinated chunk_id
(source_id not among what was actually retrieved); REJECT quote not present
in the chunk/utterance text (REV-006 issue #1 — content check, not just id
membership); department-derives-from-domain orphan detection; and the
위험!=도메인 (risk != domain) negative fixture at the schema/whitelist layer
(SM-04a-class risk-laden utterance content — see docstring on the last test).
"""

from __future__ import annotations

from src.eval.f2_grounding import (
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_QUOTE_MISMATCH,
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    VERDICT_REJECTED_UNKNOWN_TYPE,
    audit_domain_candidates,
    check_evidence,
    find_orphan_departments,
)
from src.schemas.domain_inference import DepartmentCandidate, DomainCandidate, DomainEvidence

_CHUNK_TEXTS = {"case_card:1": "불안감과 수면 문제로 상담을 시작한 사례입니다."}
_UTTERANCES = {"turn_0": "요즘 잠을 잘 못 자고 계속 불안해요."}


class TestCheckEvidenceAccepts:
    def test_valid_rag_chunk_evidence_accepted(self) -> None:
        v = check_evidence(
            "rag_chunk", "case_card:1", "불안감과 수면 문제",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_ACCEPTED
        assert v.accepted is True

    def test_valid_utterance_evidence_accepted(self) -> None:
        v = check_evidence(
            "utterance", "turn_0", "잠을 잘 못 자",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_ACCEPTED


class TestCheckEvidenceRejectsHallucinatedSource:
    """source_id not among what was ACTUALLY returned this run."""

    def test_unknown_chunk_id_rejected(self) -> None:
        v = check_evidence(
            "rag_chunk", "case_card:999", "불안감과 수면 문제",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_REJECTED_UNKNOWN_SOURCE

    def test_unknown_utterance_id_rejected(self) -> None:
        v = check_evidence(
            "utterance", "turn_99", "잠을 잘 못 자",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_REJECTED_UNKNOWN_SOURCE

    def test_unknown_source_type_rejected(self) -> None:
        v = check_evidence(
            "made_up_type", "turn_0", "잠을 잘 못 자",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_REJECTED_UNKNOWN_TYPE


class TestCheckEvidenceRejectsQuoteMismatch:
    """REV-006 #1 — a REAL source_id with an INVENTED quote must still fail."""

    def test_fabricated_quote_against_real_chunk_id_rejected(self) -> None:
        v = check_evidence(
            "rag_chunk", "case_card:1", "완전히 다른 내용의 지어낸 인용문입니다",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_REJECTED_QUOTE_MISMATCH

    def test_fabricated_quote_against_real_utterance_id_rejected(self) -> None:
        v = check_evidence(
            "utterance", "turn_0", "약을 많이 먹었어요",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_REJECTED_QUOTE_MISMATCH

    def test_empty_quote_rejected(self) -> None:
        v = check_evidence(
            "utterance", "turn_0", "",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_REJECTED_QUOTE_MISMATCH


class TestAuditDomainCandidates:
    def test_mixed_candidates_counted_correctly(self) -> None:
        candidates = [
            DomainCandidate(
                domain="sleep", confidence=0.6,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0", quote="잠을 잘 못 자"
                    ),
                    DomainEvidence(
                        source_type="rag_chunk", source_id="case_card:999", quote="지어낸 근거"
                    ),
                ],
            ),
        ]
        verdicts, counts = audit_domain_candidates(
            candidates, chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES
        )
        assert len(verdicts) == 2
        assert counts[VERDICT_ACCEPTED] == 1
        assert counts[VERDICT_REJECTED_UNKNOWN_SOURCE] == 1


class TestOrphanDepartments:
    """Department-derives-from-domain — an orphan domain_ref is a failure."""

    def test_domain_ref_matching_a_candidate_is_not_orphan(self) -> None:
        domains = [DomainCandidate(domain="sleep", confidence=0.5, evidence=[
            DomainEvidence(source_type="utterance", source_id="turn_0", quote="잠")
        ])]
        depts = [
            DepartmentCandidate(department="정신건강의학과", reason="수면 문제", domain_ref="sleep")
        ]
        assert find_orphan_departments(domains, depts) == []

    def test_domain_ref_with_no_matching_candidate_is_orphan(self) -> None:
        domains = [DomainCandidate(domain="sleep", confidence=0.5, evidence=[
            DomainEvidence(source_type="utterance", source_id="turn_0", quote="잠")
        ])]
        depts = [DepartmentCandidate(department="내과", reason="근거 불명", domain_ref="psychosis")]
        orphans = find_orphan_departments(domains, depts)
        assert len(orphans) == 1
        assert orphans[0].department == "내과"

    def test_no_domain_ref_is_not_orphan(self) -> None:
        """domain_ref is optional per the output contract — absence != orphan."""
        depts = [DepartmentCandidate(department="정신건강의학과", reason="일반 상담")]
        assert find_orphan_departments([], depts) == []


class TestRiskNotDomainNegativeFixture:
    """위험!=도메인: crisis-language input, sleep-domain content (SM-04a-class script).

    The whitelist/schema layer only checks lexical grounding — it cannot and
    does not judge domain-appropriateness (that mitigation is prompt-only,
    per REV-006 issue #3). This fixture demonstrates the boundary precisely:
    a domain candidate that legitimately cites a crisis-adjacent utterance as
    evidence for `sleep` still passes the WHITELIST (the quote is real and
    lexically present) — the rule that this must not happen in practice lives
    in the prompt text (asserted separately in
    test_prompt_domain_inference.py::TestAbsoluteRules::
    test_risk_not_domain_evidence_rule), not in this code layer.
    """

    def test_crisis_utterance_cited_for_sleep_domain_passes_whitelist_lexically(self) -> None:
        # SM-04a-class script content: self-harm ideation, no SI wording.
        crisis_utterances = {
            "turn_2": "요즘 자꾸 스스로를 해치고 싶다는 생각이 들어요. 잠도 계속 못 자고요.",
        }
        candidate = DomainCandidate(
            domain="sleep", confidence=0.5,
            evidence=[
                DomainEvidence(
                    source_type="utterance", source_id="turn_2",
                    quote="잠도 계속 못 자고요",
                )
            ],
        )
        verdicts, counts = audit_domain_candidates(
            [candidate], chunk_texts={}, utterances=crisis_utterances
        )
        # Whitelist layer: lexically grounded -> accepted (it cannot see that
        # the source utterance ALSO contains risk language elsewhere in the
        # same sentence). Domain-appropriateness of using a crisis-adjacent
        # utterance at all is enforced by the prompt rule, not this code.
        assert counts[VERDICT_ACCEPTED] == 1

    def test_prompt_forbids_citing_risk_language_as_domain_evidence(self) -> None:
        """The actual defense for this fixture class lives in the prompt text."""
        from pathlib import Path

        prompt = (
            Path(__file__).resolve().parents[3]
            / "docs" / "ai" / "prompts" / "domain_inference" / "v1.system.md"
        ).read_text(encoding="utf-8")
        assert "위험 표현을 domain confidence의 근거로 사용하지 않는다" in prompt
