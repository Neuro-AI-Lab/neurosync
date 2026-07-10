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

from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

import src.f2 as f2
from src.eval.f2_grounding import (
    _PANIC_IDIOM_PHRASES,
    _RISK_PHRASES,
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_QUOTE_MISMATCH,
    VERDICT_REJECTED_RISK_LEXICON,
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    VERDICT_REJECTED_UNKNOWN_TYPE,
    _normalize_rag_chunk_source_id,
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


class TestBug016ChunkIdPrefixNormalization:
    """BUG-016 (REV-010 finding 1) — a rag_chunk source_id carrying a benign
    `chunk_id=` prefix echo (the model sometimes reflects the prompt's own
    per-chunk listing label back into source_id) must not cost genuine,
    well-grounded evidence. See tests/repro/test_bug_016.py for the
    production-artifact-derived repro; this class covers the normalization
    primitive and its edge cases directly."""

    def test_normalize_strips_exact_prefix(self) -> None:
        assert _normalize_rag_chunk_source_id("chunk_id=case_card:687") == "case_card:687"

    def test_normalize_strips_whitespace_variant(self) -> None:
        assert _normalize_rag_chunk_source_id("chunk_id = case_card:687") == "case_card:687"
        assert _normalize_rag_chunk_source_id("chunk_id= case_card:687") == "case_card:687"
        assert _normalize_rag_chunk_source_id("chunk_id =case_card:687") == "case_card:687"

    def test_normalize_leaves_unprefixed_id_unchanged(self) -> None:
        assert _normalize_rag_chunk_source_id("case_card:687") == "case_card:687"

    def test_normalize_only_strips_leading_prefix(self) -> None:
        """A chunk_id that legitimately CONTAINS the substring elsewhere
        (not as a leading prefix) must not be mangled."""
        assert _normalize_rag_chunk_source_id("qa:chunk_id=5") == "qa:chunk_id=5"

    def test_check_evidence_accepts_prefixed_rag_chunk_source_id(self) -> None:
        v = check_evidence(
            "rag_chunk", "chunk_id=case_card:1", "불안감과 수면 문제",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_ACCEPTED
        assert v.source_id == "case_card:1"  # normalized id recorded, not raw

    def test_check_evidence_normalization_is_rag_chunk_only(self) -> None:
        """The `chunk_id=` prefix strip must not apply to `utterance`
        source_ids (a turn_id like `turn_0` would never legitimately carry
        this prefix; normalizing it anyway would be scope creep)."""
        v = check_evidence(
            "utterance", "chunk_id=turn_0", "잠을 잘 못 자",
            chunk_texts=_CHUNK_TEXTS, utterances=_UTTERANCES,
        )
        assert v.verdict == VERDICT_REJECTED_UNKNOWN_SOURCE


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


class TestVal011AiPredictedDiseasePopulationRiskLexiconGate:
    """VAL-011 (`error.md`) / ADR-020 condition 1 (binding, blocking-scoped),
    PLAN-2026-W28-K Task 3/4 qa gate.

    RES-001's path1 population design derives each
    ``AIPredictedDiseaseCandidate.quote`` verbatim from a retrieved
    ``case_card``/``qa`` chunk's own text — the SAME failure class REV-008's
    live VP-003 finding already forced ``domain_candidates`` to close via
    ``filter_domain_candidates``/``_RISK_PHRASES`` (ADR-014). Developer's
    Track B fix (`f2._aggregate_disease_candidates`) reuses
    ``f2_grounding._contains_any(quote, _RISK_PHRASES)`` — the EXACT SAME
    primitives, not a re-implemented/drifting copy — before a vote is
    allowed to become a shipped candidate. This class independently
    re-verifies that reuse is genuine (not a no-op / vacuously-always-empty
    result for an unrelated reason) via a mutation check, and locks in the
    two behavioral guarantees ADR-020 condition 1 requires: DROP (never
    clip/redact) the risk-flagged vote, and a sole-risk-flagged-match
    candidate reduces to a legitimate 0-candidate outcome, not an error.

    Fixture: a VP-003-style ``case_card`` excerpt (this project's own
    governing high-scrutiny persona, DATASET-004/VAL-010) — constructed
    (not copied from a live artifact; no live-populated-path batch has run
    yet as of this gate) to match the same "자살 생각을 표현하며..." class
    the brief names and the same lexicon coverage this project's
    established ``_RISK_PHRASES`` list already provides (verbatim
    ``"자살"`` entry).
    """

    _RISKY_CASE_CARD_TEXT = "환자는 최근 상담에서 자살 생각을 표현하며 매우 힘들어했다고 진술함."
    _CLEAN_CASE_CARD_TEXT = "환자가 불안하고 잠을 잘 못 잔다고 호소함."

    def test_risk_flagged_case_card_quote_dropped_not_shipped(self) -> None:
        """Core VAL-011 claim: a risk-lexicon-flagged case_card chunk quote
        must never reach `ai_predicted_disease.candidates` — the candidate
        is DROPPED entirely (`candidates == []`), not shipped with a
        clipped/redacted quote."""
        chunk = {
            "chunk_id": "case_card:9001", "source_type": "case_card",
            "text": self._RISKY_CASE_CARD_TEXT, "score": 0.81,
        }
        candidates, n_dropped = f2._aggregate_disease_candidates(
            [(chunk, "우울 삽화(우울증)", "힘들어")]
        )
        assert candidates == []
        assert n_dropped == 1

    async def test_sole_risk_flagged_match_reduces_to_legitimate_zero_candidate_outcome(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ADR-020 condition 1 / RES-001 §2 step 7: a candidate whose SOLE
        matched chunk is risk-lexicon-flagged reduces the whole
        populated-path run to a legitimate, honestly-explained 0-candidate
        outcome via the real async entry point
        `_build_ai_predicted_disease_populated` — not a crash, not a
        redacted candidate, not a silent empty list with no explanation."""
        chunk = {
            "chunk_id": "case_card:9001", "source_type": "case_card",
            "text": self._RISKY_CASE_CARD_TEXT, "score": 0.81,
        }
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(return_value=[("우울 삽화(우울증)", 1, "힘들어")]),
        )
        out = await f2._build_ai_predicted_disease_populated(object(), [chunk])
        assert out.mode == "rag_live"
        assert out.candidates == []
        assert out.is_diagnostic is False
        assert "legitimate" in out.reason_summary
        assert "risk-lexicon filter" in out.reason_summary
        assert "1 candidate vote(s)" in out.reason_summary

    def test_risk_flagged_drop_does_not_eliminate_an_unrelated_clean_sibling(
        self,
    ) -> None:
        """The drop is scoped to the risk-flagged vote only — an unrelated
        clean candidate in the same population batch still ships."""
        risky_chunk = {
            "chunk_id": "case_card:9001", "source_type": "case_card",
            "text": self._RISKY_CASE_CARD_TEXT, "score": 0.81,
        }
        clean_chunk = {
            "chunk_id": "case_card:9003", "source_type": "case_card",
            "text": self._CLEAN_CASE_CARD_TEXT, "score": 0.6,
        }
        votes = [
            (risky_chunk, "우울 삽화(우울증)", "힘들어"),
            (clean_chunk, "공황장애", "불안"),
        ]
        candidates, n_dropped = f2._aggregate_disease_candidates(votes)
        assert n_dropped == 1
        assert len(candidates) == 1
        assert candidates[0].disease == "공황장애"
        assert candidates[0].source_id == "case_card:9003"

    def test_mutation_check_filter_is_load_bearing_not_vacuous(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-vacuity guard for `test_risk_flagged_case_card_quote_dropped_not_shipped`
        above: patch `f2._RISK_PHRASES` (the module-level name
        `_aggregate_disease_candidates` actually reads at call time, via
        `from src.eval.f2_grounding import _RISK_PHRASES`) to an empty
        tuple and confirm the SAME risky quote now SURVIVES as a shipped
        candidate. This proves the sibling test's `candidates == []`
        assertion is genuinely exercising the risk-lexicon filter, not
        passing for an unrelated reason (e.g. the disease-vote lookup
        itself yielding nothing) — a regression that silently disabled the
        filter (patched to a no-op, per this project's established
        mutation-check convention — BUG-014/BUG-016 precedent) would flip
        this test's own assertions, catching the regression."""
        monkeypatch.setattr(f2, "_RISK_PHRASES", ())
        chunk = {
            "chunk_id": "case_card:9001", "source_type": "case_card",
            "text": self._RISKY_CASE_CARD_TEXT, "score": 0.81,
        }
        candidates, n_dropped = f2._aggregate_disease_candidates(
            [(chunk, "우울 삽화(우울증)", "힘들어")]
        )
        assert n_dropped == 0
        assert len(candidates) == 1
        assert candidates[0].disease == "우울 삽화(우울증)"
        assert candidates[0].quote == self._RISKY_CASE_CARD_TEXT


class TestRev017Finding1FullChunkRiskLexiconGate:
    """REV-017 Finding 1 (`discussion.md`) / VAL-011 reopened (`error.md`) —
    the ±40-char extracted-quote window is not the full source chunk, and a
    risk phrase sitting more than a window-width away from the matched
    *symptom* term (in a longer, multi-sentence chunk) escaped
    `TestVal011AiPredictedDiseasePopulationRiskLexiconGate`'s single-sentence
    fixture entirely. Live-reproduced twice by critic on the project's own
    VP-003 persona: `case_card:664` ("자해를 하려는 생각") and `case_card:563`
    ("자살 생각을 표현") both shipped as disease-candidate evidence with a
    clean-looking quote while the SAME chunk was independently rejected by
    the `domain_candidates` whitelist as risk-lexicon-flagged.

    Fixtures below reproduce that shape directly (constructed, not copied
    verbatim from the live artifact, but same structural property: risk
    phrase near the start of a multi-sentence chunk, matched symptom term
    later in the same chunk, distance between them exceeds the ±40-char
    quote-extraction window so the shipped `quote` itself is clean).
    """

    # Risk phrase ("자해") sits at index 12; matched term ("식욕") sits at
    # index 85 — verified this fixture's ±40-char quote window around the
    # matched term does NOT contain the risk phrase (the exact blind spot
    # REV-017 documents), while the full chunk text does.
    _LONG_CHUNK_RISK_FAR_FROM_TERM = (
        "환자는 최근 상담에서 자해를 하려는 생각이 가끔 들기도 하며, 자신을 실패자로 여기거나 "
        "쓸모없다고 느끼는 경우가 있다고 진술하였다. 내담자는 최근 들어 식욕이 줄어들어 "
        "거의 매일 조금씩 먹는 상태이며, 밤에 잠을 이루지 못하고 뒤척이는 경우가 많고, "
        "사람들과의 만남을 피하고 혼자 있으려는 경향이 뚜렷하게 나타나고 있다."
    )
    _LONG_CHUNK_TERM = "식욕"

    # Same length/shape, no risk phrase anywhere — must NOT be blocked
    # (regression guard against over-blocking).
    _LONG_CHUNK_BENIGN = (
        "환자는 최근 상담에서 대인관계에서의 어려움을 자주 언급하며, 회사 업무에서 스트레스를 "
        "크게 받고 있다고 진술하였다. 내담자는 최근 들어 식욕이 줄어들어 "
        "거의 매일 조금씩 먹는 상태이며, 밤에 잠을 이루지 못하고 뒤척이는 경우가 많고, "
        "사람들과의 만남을 피하고 혼자 있으려는 경향이 뚜렷하게 나타나고 있다."
    )

    def test_quote_window_does_not_contain_risk_phrase_precondition(self) -> None:
        """Precondition check: confirms the fixture actually reproduces the
        gap REV-017 describes — the ±40-char quote extracted around the
        matched term is itself clean, so a quote-only check would (wrongly)
        pass this vote. If this assertion ever fails, the fixture no longer
        exercises the blind spot and must be revised."""
        quote = f2._extract_quote(self._LONG_CHUNK_RISK_FAR_FROM_TERM, self._LONG_CHUNK_TERM)
        assert not f2._contains_any(quote, f2._RISK_PHRASES)
        assert f2._contains_any(self._LONG_CHUNK_RISK_FAR_FROM_TERM, f2._RISK_PHRASES)

    def test_long_chunk_distant_risk_phrase_is_dropped(self) -> None:
        """The REV-017 fix: even though the extracted quote is clean, the
        candidate must be dropped because the risk phrase appears elsewhere
        in the SAME source chunk (case_card:664/563 shape)."""
        chunk = {
            "chunk_id": "case_card:9101", "source_type": "case_card",
            "text": self._LONG_CHUNK_RISK_FAR_FROM_TERM, "score": 0.77,
        }
        candidates, n_dropped = f2._aggregate_disease_candidates(
            [(chunk, "우울 삽화(우울증)", self._LONG_CHUNK_TERM)]
        )
        assert candidates == []
        assert n_dropped == 1

    async def test_long_chunk_distant_risk_phrase_dropped_via_real_entry_point(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Same as above via the real async entry point
        `_build_ai_predicted_disease_populated` — reduces to a legitimate
        0-candidate outcome, not a crash or a leaked candidate."""
        chunk = {
            "chunk_id": "case_card:9101", "source_type": "case_card",
            "text": self._LONG_CHUNK_RISK_FAR_FROM_TERM, "score": 0.77,
        }
        monkeypatch.setattr(
            "src.rag.retrieval.match_diseases_for_chunk_text",
            AsyncMock(return_value=[("우울 삽화(우울증)", 1, self._LONG_CHUNK_TERM)]),
        )
        out = await f2._build_ai_predicted_disease_populated(object(), [chunk])
        assert out.mode == "rag_live"
        assert out.candidates == []
        assert "legitimate" in out.reason_summary
        assert "risk-lexicon filter" in out.reason_summary

    def test_long_chunk_no_risk_phrase_anywhere_still_ships_no_over_blocking(self) -> None:
        """Regression guard: a benign long, multi-sentence chunk (same
        shape/length as the risky fixture, matched term far from the start,
        but NO risk phrase anywhere in the full text) must still produce a
        shipped candidate — the full-chunk check must not become an
        over-broad block on long chunks in general."""
        assert not f2._contains_any(self._LONG_CHUNK_BENIGN, f2._RISK_PHRASES)
        chunk = {
            "chunk_id": "case_card:9102", "source_type": "case_card",
            "text": self._LONG_CHUNK_BENIGN, "score": 0.65,
        }
        candidates, n_dropped = f2._aggregate_disease_candidates(
            [(chunk, "우울 삽화(우울증)", self._LONG_CHUNK_TERM)]
        )
        assert n_dropped == 0
        assert len(candidates) == 1
        assert candidates[0].disease == "우울 삽화(우울증)"
        assert candidates[0].source_id == "case_card:9102"

    def test_case_card_664_shape_direct_repro(self) -> None:
        """Closest reproduction of the actual live leak (`case_card:664`,
        EXP-009 VP-003/run2): "자해를 하려는 생각" opens the chunk, the
        matched symptom term is drawn from the sentence describing
        appetite/hopelessness much later in the same multi-sentence
        record — confirms the exact shipped `source_id`/leak class from
        REV-017 Finding 1 is now closed."""
        case_card_664_shape = (
            "환자는 식욕이 줄어들어 거의 매일 조금씩 먹는 상태이다. 자해를 하려는 생각이 "
            "가끔 들기도 하며, 자신을 실패자로 여기거나 쓸모없다고 느끼는 경우가 있다. "
            "내담자는 자신을 쓸모없다고 느끼고, 미래에 대한 절망감을 가지고 있으며, "
            "사람들의 비난을 두려워하고 있다. 또한, 부모님의 기대에 미치지 못한다고 여긴다."
        )
        term = "절망감"
        quote = f2._extract_quote(case_card_664_shape, term)
        assert not f2._contains_any(quote, f2._RISK_PHRASES)  # precondition: quote-only was blind
        chunk = {
            "chunk_id": "case_card:664", "source_type": "case_card",
            "text": case_card_664_shape, "score": 0.9,
        }
        candidates, n_dropped = f2._aggregate_disease_candidates(
            [(chunk, "우울 삽화(우울증)", term)]
        )
        assert candidates == []
        assert n_dropped == 1


class TestVal011ProvenanceEnforcementBoundary:
    """REV-016(b) binding condition 2 / ADR-020 condition 2 — qa gate
    scrutiny of the developer's own deviation claim ("`_aggregate_disease_candidates`
    never constructs a candidate without both `source_id` and `quote`...
    the discipline is enforced at the population-code level, checked by
    tests, not by the Pydantic schema itself").

    Finding (non-blocking, reported to critic per this gate's brief, NOT a
    `src/` fix — out of this gate's charter): the claim is true for the
    shape `retrieve_domain_chunks()` actually returns on the live path
    (every chunk dict always carries `chunk_id`/`text`) but is NOT a
    standalone invariant of `_aggregate_disease_candidates` itself. A
    malformed vote tuple whose chunk dict lacks `chunk_id` DOES construct a
    candidate with `source_id=None` (schema-legal — the field is Optional,
    so no `ValidationError` catches it). The reason this is unreachable on
    the actual `f2.py::_run()` call path is INCIDENTAL, not a designed
    guard of the population code itself: `_run()`'s own
    `chunk_texts = {c["chunk_id"]: c["text"] for c in raw_chunks}`
    (`f2.py:864`) runs strictly BEFORE the population call (`f2.py:898`)
    and would already raise an uncaught `KeyError`, aborting the entire F2
    run, for any `raw_chunks` entry missing `chunk_id`/`text` — so a
    provenance-less candidate cannot ship today, but only because the
    whole pipeline dies first for an unrelated reason, not because
    `_aggregate_disease_candidates` itself enforces "no evidence, no
    candidate" at its own function boundary. Flagged to critic; not
    blocking per this gate's own charter (a candidate cannot actually ship
    without provenance on the live path today).
    """

    def test_malformed_chunk_missing_chunk_id_ships_candidate_with_source_id_none(
        self,
    ) -> None:
        """Documents the function-boundary gap (this is NOT asserting
        desired behavior — see class docstring): a chunk dict lacking
        `chunk_id` produces a candidate with `source_id=None` today. A
        future caller of `_aggregate_disease_candidates` that does not go
        through `retrieve_domain_chunks()`'s guaranteed shape (e.g. a
        differently-constructed votes list, or a future refactor of
        `_collect_chunk_disease_votes`) could silently ship a
        provenance-less candidate without any error."""
        chunk_without_chunk_id = {"text": "환자가 불안 증상을 호소함", "score": 0.6}
        candidates, n_dropped = f2._aggregate_disease_candidates(
            [(chunk_without_chunk_id, "불안장애", "불안")]
        )
        assert n_dropped == 0
        assert len(candidates) == 1
        assert candidates[0].source_id is None

    def test_malformed_chunk_missing_text_raises_validation_error_uncaught_here(
        self,
    ) -> None:
        """A chunk dict with no `text` key produces an empty-string quote
        (`_extract_quote("", term)` returns `""`), which the schema's
        `min_length=1` constraint on `quote` rejects with an uncaught
        `pydantic.ValidationError` raised INSIDE `_aggregate_disease_candidates`
        itself (not caught here). `_run()`'s own outer `try/except`
        (`f2.py:901`) does catch this at the call-site level and degrades
        the WHOLE batch to `experimental_unpopulated` — coarser than
        per-candidate isolation, but not a crash of the whole F2 run.
        Unreachable via the real `_collect_chunk_disease_votes` (which
        filters blank/missing-text chunks before a vote is ever created) —
        documented here for a hypothetical direct/future caller that
        bypasses that guard."""
        chunk_without_text = {"chunk_id": "qa:1", "score": 0.5}
        with pytest.raises(ValidationError):
            f2._aggregate_disease_candidates([(chunk_without_text, "불안장애", "불안")])
