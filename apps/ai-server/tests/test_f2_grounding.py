"""src.eval.f2_grounding — F2 evidence whitelist, mock/fixture-based (C-4).

Covers: accept valid chunk/utterance evidence; REJECT hallucinated chunk_id
(source_id not among what was actually retrieved); REJECT quote not present
in the chunk/utterance text (REV-006 issue #1 — content check, not just id
membership); department-derives-from-domain orphan detection; and the
위험!=도메인 (risk != domain) negative fixture at the schema/whitelist layer
(SM-04a-class risk-laden utterance content — see docstring on the last test).

ADR-014 / VAL-006 / REV-008 (2026-07-08) additions: the code-enforced
risk-lexicon filter (``TestRiskLexiconFilter``) and its rejection cascade
(``TestRejectionCascade``) — the v2 remediation for the confirmed live
violation where VP-003's passive-SI quotes ("살고 싶지 않아요...") were
accepted as `depression` evidence by the pre-v2 whitelist.
"""

from __future__ import annotations

from src.eval.f2_grounding import (
    _PANIC_IDIOM_PHRASES,
    _RISK_PHRASES,
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_QUOTE_MISMATCH,
    VERDICT_REJECTED_RISK_LEXICON,
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    VERDICT_REJECTED_UNKNOWN_TYPE,
    audit_domain_candidates,
    check_evidence,
    filter_domain_candidates,
    find_orphan_departments,
    is_panic_idiom_evidence,
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


class TestRiskLexiconFilter:
    """ADR-014 / VAL-006 / REV-008 — code-enforced rule 2 (risk != domain evidence).

    Mandatory regression fixture (item a): the EXACT EXP-004/VP-003 failure
    pattern — a verbatim passive-suicidal-ideation quote accepted as
    `depression` evidence by the pre-v2 whitelist — must now be mechanically
    rejected as ``rejected_risk_lexicon``.
    """

    def test_vp003_run1_passive_si_quote_rejected(self) -> None:
        """`VP-003_20260708_120459_domain_inference.json` run1 evidence, verbatim
        (REV-008 adjudication) — was VERDICT_ACCEPTED before this filter."""
        utterances = {
            "turn_0": "살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
        }
        v = check_evidence(
            "utterance", "turn_0", "살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
            chunk_texts={}, utterances=utterances, domain="depression",
        )
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON
        assert v.accepted is False

    def test_vp003_run2_passive_si_quote_rejected(self) -> None:
        """`..._120509_domain_inference.json` run2 evidence, verbatim — the
        second of REV-008's 2 confirmed live occurrences."""
        utterances = {
            "turn_1": "살고 싶지 않다는 생각이 들어요. 매일 그런 생각이 들어요.",
        }
        v = check_evidence(
            "utterance", "turn_1", "살고 싶지 않다는 생각이 들어요. 매일 그런 생각이 들어요.",
            chunk_texts={}, utterances=utterances, domain="depression",
        )
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON

    def test_risk_lexicon_reason_names_cite_a_non_risk_symptom_instead(self) -> None:
        """Rejection reason must be actionable, not just a bare label."""
        utterances = {"turn_0": "이제 자살하고 싶다는 생각뿐이에요."}
        v = check_evidence(
            "utterance", "turn_0", "이제 자살하고 싶다는 생각뿐이에요.",
            chunk_texts={}, utterances=utterances,
        )
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON
        assert "자살" in v.reason
        assert "cite a non-risk symptom" in v.reason

    def test_various_risk_phrases_rejected(self) -> None:
        """Every phrase in the deliberate risk lexicon triggers rejection."""
        for phrase in _RISK_PHRASES:
            quote = f"{phrase}는 생각이 계속 들어요."
            utterances = {"turn_0": quote}
            v = check_evidence(
                "utterance", "turn_0", quote, chunk_texts={}, utterances=utterances,
            )
            assert v.verdict == VERDICT_REJECTED_RISK_LEXICON, f"phrase {phrase!r} not rejected"

    def test_panic_idiom_quote_accepted(self) -> None:
        """ISS-046 exception (SM-07a): idiom + physical-symptom context in the
        same quote must NOT be rejected — legitimate anxiety-domain evidence."""
        utterances = {
            "turn_0": (
                "심장이 미친듯이 뛰고 숨을 못 쉬어서 응급실에 실려간 적이 있어요. "
                "그때 정말 죽는 줄 알았어요."
            ),
        }
        v = check_evidence(
            "utterance", "turn_0",
            "심장이 미친듯이 뛰고 숨을 못 쉬어서 응급실에 실려간 적이 있어요. "
            "그때 정말 죽는 줄 알았어요.",
            chunk_texts={}, utterances=utterances, domain="anxiety",
        )
        assert v.verdict == VERDICT_ACCEPTED
        assert "ISS-046" in v.reason

    def test_panic_idiom_vp004_style_quote_accepted(self) -> None:
        """VP-004's actual quote (REV-008 (c)) — fear-of-dying during panic,
        not suicidal risk content."""
        text = "공황 발작이 오면 진짜 죽을 것 같고, 그 생각만 하면 또 올까 봐 무서워요."
        utterances = {"turn_5": text}
        v = check_evidence(
            "utterance", "turn_5", text, chunk_texts={}, utterances=utterances,
            domain="anxiety",
        )
        assert v.verdict == VERDICT_ACCEPTED

    def test_panic_idiom_without_symptom_context_not_risk_rejected(self) -> None:
        """A bare idiom with no risk phrase is still not risk-lexicon content
        even without symptom context — the risk filter is keyed off
        `_RISK_PHRASES` only, disjoint from the idiom set by construction."""
        text = "그때 정말 죽을 것 같았어요."
        utterances = {"turn_0": text}
        v = check_evidence(
            "utterance", "turn_0", text, chunk_texts={}, utterances=utterances,
        )
        assert v.verdict == VERDICT_ACCEPTED
        assert is_panic_idiom_evidence(text) is False  # no symptom context

    def test_panic_idiom_co_occurring_with_genuine_si_still_rejected(self) -> None:
        """SM-07b balance (both-ways): a genuine risk phrase co-occurring with
        idiom text in the SAME quote is not shielded by the idiom."""
        text = "심장이 미친듯이 뛰고 죽을 것 같았는데, 이제 진짜 죽고 싶어요."
        utterances = {"turn_0": text}
        v = check_evidence(
            "utterance", "turn_0", text, chunk_texts={}, utterances=utterances,
        )
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON

    def test_risk_and_panic_idiom_lexicons_are_disjoint(self) -> None:
        """Structural guarantee behind the ISS-046 exemption (see module
        docstring): no risk phrase is a substring of an idiom phrase or
        vice versa, space-insensitively."""
        risk = [p.replace(" ", "") for p in _RISK_PHRASES]
        idiom = [p.replace(" ", "") for p in _PANIC_IDIOM_PHRASES]
        for r in risk:
            for i in idiom:
                assert r not in i and i not in r, f"overlap between {r!r} and {i!r}"

    def test_risk_lexicon_verdict_counted_separately_in_audit(self) -> None:
        """New verdict class must be distinguishable from existing reject
        reasons in the audit counts, not folded into quote_mismatch."""
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.35,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0",
                        quote="살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
                    ),
                ],
            ),
        ]
        utterances = {"turn_0": "살고 싶지 않아요. 매일 밤 그 생각만 들어요."}
        verdicts, counts = audit_domain_candidates(
            candidates, chunk_texts={}, utterances=utterances
        )
        assert counts[VERDICT_REJECTED_RISK_LEXICON] == 1
        assert counts[VERDICT_REJECTED_QUOTE_MISMATCH] == 0
        assert counts[VERDICT_ACCEPTED] == 0


class TestRejectionCascade:
    """ADR-014 item 2 — rejected evidence removed; under-evidenced candidate
    eliminated entirely (schema contract: DomainCandidate.evidence >= 1)."""

    def test_candidate_with_only_risk_evidence_is_eliminated(self) -> None:
        utterances = {"turn_0": "살고 싶지 않아요. 매일 밤 그 생각만 들어요."}
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.35,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0",
                        quote="살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
                    ),
                ],
            ),
        ]
        filtered, verdicts, counts = filter_domain_candidates(
            candidates, chunk_texts={}, utterances=utterances
        )
        assert filtered == []
        assert counts[VERDICT_REJECTED_RISK_LEXICON] == 1

    def test_candidate_with_mixed_evidence_survives_with_risk_stripped(self) -> None:
        utterances = {
            "turn_0": "살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
            "turn_1": "요즘 잠을 잘 못 자고 계속 불안해요.",
        }
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.5,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0",
                        quote="살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
                    ),
                    DomainEvidence(
                        source_type="utterance", source_id="turn_1",
                        quote="잠을 잘 못 자고 계속 불안해요",
                    ),
                ],
            ),
        ]
        filtered, verdicts, counts = filter_domain_candidates(
            candidates, chunk_texts={}, utterances=utterances
        )
        assert len(filtered) == 1
        assert len(filtered[0].evidence) == 1
        assert filtered[0].evidence[0].source_id == "turn_1"
        assert counts[VERDICT_REJECTED_RISK_LEXICON] == 1
        assert counts[VERDICT_ACCEPTED] == 1

    def test_only_bad_candidate_eliminated_among_several(self) -> None:
        utterances = {
            "turn_0": "살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
            "turn_1": "요즘 잠을 잘 못 자고 계속 불안해요.",
        }
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.4,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0",
                        quote="살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
                    ),
                ],
            ),
            DomainCandidate(
                domain="anxiety", confidence=0.6,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_1",
                        quote="잠을 잘 못 자고 계속 불안해요",
                    ),
                ],
            ),
        ]
        filtered, verdicts, counts = filter_domain_candidates(
            candidates, chunk_texts={}, utterances=utterances
        )
        assert [c.domain for c in filtered] == ["anxiety"]

    def test_cascade_logs_eliminated_and_stripped_counts(self, caplog) -> None:
        import logging

        utterances = {
            "turn_0": "살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
            "turn_1": "요즘 잠을 잘 못 자고 계속 불안해요.",
        }
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.35,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0",
                        quote="살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
                    ),
                ],
            ),
            DomainCandidate(
                domain="sleep", confidence=0.5,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0",
                        quote="살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
                    ),
                    DomainEvidence(
                        source_type="utterance", source_id="turn_1",
                        quote="잠을 잘 못 자고 계속 불안해요",
                    ),
                ],
            ),
        ]
        with caplog.at_level(logging.INFO, logger="src.eval.f2_grounding"):
            filter_domain_candidates(candidates, chunk_texts={}, utterances=utterances)
        assert any("candidate_eliminated" in r.message for r in caplog.records)
        assert any("evidence_stripped" in r.message for r in caplog.records)

    def test_cascade_verdicts_cover_all_submitted_evidence(self) -> None:
        """verdicts/counts shape matches audit_domain_candidates — full audit
        trail retained even though rejected items are removed from output."""
        utterances = {"turn_0": "살고 싶지 않아요. 매일 밤 그 생각만 들어요."}
        candidates = [
            DomainCandidate(
                domain="depression", confidence=0.35,
                evidence=[
                    DomainEvidence(
                        source_type="utterance", source_id="turn_0",
                        quote="살고 싶지 않아요. 매일 밤 그 생각만 들어요.",
                    ),
                ],
            ),
        ]
        filtered, verdicts, counts = filter_domain_candidates(
            candidates, chunk_texts={}, utterances=utterances
        )
        assert len(verdicts) == 1
        assert sum(counts.values()) == 1
