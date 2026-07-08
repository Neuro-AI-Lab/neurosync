"""BUG-015 repro/regression: `src.eval.f2_grounding._RISK_PHRASES` used to
include two bare, polysemous single/short-word entries -- `"손목"` ("wrist")
and `"목숨"` ("life"/"one's life") -- with no co-occurring context
requirement, unlike every other entry in the list (multi-word SI-directed
phrases) and unlike the structural ISS-046 panic-idiom carve-out
(`is_panic_idiom_evidence`), which specifically requires an idiom phrase AND
physical-symptom context before treating fear-of-dying language as non-risk.

Both words have common, entirely benign clinical usages unrelated to
self-harm/suicide:
  - "손목" ("wrist"): RSI/carpal-tunnel-style somatic complaints
    ("손목이 계속 아파요") are legitimate physical-symptom evidence for
    ANY domain, not risk content.
  - "목숨" ("life"): survivor narratives ("목숨을 건졌다" = "I survived" /
    "my life was saved") and common idiomatic-effort expressions
    ("목숨 걸고 준비했다" = "I prepared like my life depended on it") are
    not suicidal-risk content -- in the survivor-narrative case the
    quote is the OPPOSITE of suicidal ideation.

Because `DomainCandidate.evidence` has `min_length=1` (plan C-2 "no
evidence, no candidate") and `filter_domain_candidates` eliminates any
candidate whose accepted-evidence count drops to 0, a candidate whose
ONLY evidence is one of these benign quotes was silently dropped from the
artifact entirely -- a false-negative domain-candidate loss for a
patient's actual trauma/somatic content, the concrete case this repro
demonstrated for the `trauma` domain via a car-accident survivor quote.

BUG-015 fix (this revision): the bare `"손목"`/`"목숨"` entries are removed
from `_RISK_PHRASES` and replaced with multi-word, SI-directed stems --
`"손목을 긋"`/`"손목을 그"` (self-harm-by-cutting; the same stem convention
already used elsewhere in this codebase, e.g. `src.agents.safety_classifier`'s
ISS-038 fix for the analogous bare-`"칼로"` over-match) and
`"목숨을 끊"`/`"목숨을 버리"` (suicide-directed "end one's life" usage). See
`src/eval/f2_grounding.py`'s `_RISK_PHRASES` comment block for the full stem
list and rationale.

Following this project's established repro-test convention (BUG-007, BUG-009,
BUG-011): these tests originally asserted the CURRENT (buggy, over-blocking)
behavior -- i.e. they PASSED pre-fix. Per the BUG-007 precedent, the
assertions below are now INVERTED (not weakened) to assert the fixed
behavior, so this file becomes a permanent regression guard against the
bare, context-free entries resurfacing.
"""

from __future__ import annotations

import pytest

from src.eval.f2_grounding import (
    VERDICT_ACCEPTED,
    check_evidence,
    filter_domain_candidates,
)
from src.schemas.domain_inference import DomainCandidate, DomainEvidence

_BENIGN_QUOTES = [
    ("wrist pain, somatic complaint (any domain)", "요즘 손목이 계속 아파서 타이핑도 힘들어요."),
    (
        "car-accident survivor narrative (trauma domain)",
        "교통사고 났을 때 정말 목숨을 건졌다고 생각해요.",
    ),
    ("idiomatic-effort expression (no domain relevance)", "이번 발표를 목숨 걸고 준비했어요."),
]


class TestBug015RiskLexiconOverBlocking:
    @pytest.mark.parametrize("label,quote", _BENIGN_QUOTES)
    def test_benign_quote_now_accepted(
        self, label: str, quote: str
    ) -> None:
        """BUG-015 fix: a benign clinical quote with no suicidal/self-harm
        meaning is now accepted, not rejected as risk-class content.

        Renamed from `test_benign_quote_currently_rejected_as_risk_lexicon`
        (assertion inverted, not weakened) -- that test's own docstring
        anticipated this exact outcome ("If this fails, the bare
        '손목'/'목숨' entries may already have been scoped or removed;
        update error.md and invert this assertion")."""
        v = check_evidence(
            "utterance", "turn_x", quote, chunk_texts={}, utterances={"turn_x": quote},
            domain="trauma",
        )
        assert v.verdict == VERDICT_ACCEPTED, (
            f"BUG-015 regression [{label}]: quote {quote!r} is rejected "
            f"again (verdict={v.verdict!r}). A bare '손목'/'목숨' entry may "
            "have been reintroduced into _RISK_PHRASES."
        )

    def test_trauma_candidate_with_only_survivor_narrative_evidence_now_survives(
        self,
    ) -> None:
        """BUG-015 fix, cascade level: a `trauma` domain candidate whose
        SOLE evidence is a genuine survivor narrative (opposite in meaning
        to suicidal ideation) now survives the whitelist cascade instead of
        being silently eliminated.

        Renamed from
        `test_trauma_candidate_with_only_survivor_narrative_evidence_is_silently_eliminated`
        (assertion inverted, not weakened)."""
        quote = "교통사고 났을 때 정말 목숨을 건졌다고 생각해요."
        domain_candidates = [
            DomainCandidate(
                domain="trauma", confidence=0.5,
                evidence=[DomainEvidence(source_type="utterance", source_id="turn_0", quote=quote)],
            ),
        ]
        filtered, verdicts, counts = filter_domain_candidates(
            domain_candidates, chunk_texts={}, utterances={"turn_0": quote}
        )
        assert len(filtered) == 1, (
            "BUG-015 regression: the trauma candidate was eliminated again. "
            "A bare '손목'/'목숨' entry may have been reintroduced into "
            "_RISK_PHRASES."
        )
        assert filtered[0].domain == "trauma"
        assert len(filtered[0].evidence) == 1
        assert filtered[0].evidence[0].quote == quote
        assert counts["rejected_risk_lexicon"] == 0
        assert counts["accepted"] == 1
