"""BUG-016 repro: `src.eval.f2_grounding.check_evidence` requires an EXACT
match between an evidence item's `source_id` and a key in `chunk_texts`
(Stage 1's actually-retrieved chunk_id -> text map) -- `chunk_texts.get(
source_id)` at `src/eval/f2_grounding.py:248`. The DomainInferenceAgent's
own prompt-construction code (`src/agents/domain_inference.py:75,77`)
headers the retrieved-chunk block "source_type=rag_chunk, source_id=
chunk_id" and lists each chunk as `f"- chunk_id={c.chunk_id} [...]"` --
i.e. the literal string `chunk_id=` sits directly adjacent to the ID in
the prompt text the model reads. Solar Pro3 sometimes echoes that literal
label into the `source_id` field it emits (e.g. `"chunk_id=case_card:687"`
instead of `"case_card:687"`), which `check_evidence`'s exact-match lookup
then rejects as `rejected_unknown_source` -- even though the cited chunk
and quote are both genuinely real and retrieved that run (not fabrication;
an over-rejection / false negative).

Confirmed live in EXP-005 (RAG arm, first activation, REV-010 finding 1 /
`discussion.md`, 2026-07-08): all 10 of that batch's `rejected_unknown_
source` verdicts (`rag/VP-001/run1` x6, `rag/VP-002/run1` x2, `rag/VP-002/
run2` x2) carry this exact `chunk_id=` prefix -- ~29% of the RAG arm's
`rag_chunk` evidence this batch (10/35 would-be-accepted items). Root
cause independently re-confirmed by qa at the cited line numbers (see
`apps/ai-server/src/agents/domain_inference.py:75,77`).

`_REAL_CHUNK_ID` / `_REAL_CHUNK_TEXT` below are copied verbatim from the
real artifact `experiments/EXP-005/runs/rag/VP-001/run1/
VP-001_20260708_200259_domain_inference.json` (`chunk_texts["case_card:
687"]`, whitelist_audit verdict #1: `source_id="chunk_id=case_card:687"`,
`verdict="rejected_unknown_source"`) -- truncated to its first two
sentences for test readability; the truncation point does not affect the
lexical-overlap check (`has_lexical_evidence` only requires token overlap,
not a full-string match). The artifact itself lives under `experiments/`
(gitignored) and is NOT read at test runtime, so this repro stays
reproducible in any clone/CI without the `experiments/` tree present --
this file is self-contained.

Severity/fix options: see `error.md` BUG-016 (prompt wording vs. code-level
source_id normalization in `check_evidence`).
"""

from __future__ import annotations

from src.eval.f2_grounding import (
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    check_evidence,
    filter_domain_candidates,
)
from src.schemas.domain_inference import DomainCandidate, DomainEvidence

# Verbatim from experiments/EXP-005/runs/rag/VP-001/run1/
# VP-001_20260708_200259_domain_inference.json, chunk_texts["case_card:687"]
# (truncated to its first two sentences).
_REAL_CHUNK_ID = "case_card:687"
_REAL_CHUNK_TEXT = (
    "내담자는 우울과 관련하여 몇 가지 주요 증상을 보이고 있다. 첫째, 수면 패턴의 "
    "변화가 나타나며, 새벽에 잠들고 중간에 자주 깨는 등의 수면 장애를 겪고 있다."
)
_REAL_QUOTE = _REAL_CHUNK_TEXT


class TestBug016ChunkIdPrefixEcho:
    def test_prefixed_source_id_rejected_as_unknown_source(self) -> None:
        """Reproduces the exact production defect: the model's source_id
        carries the literal `chunk_id=` prefix from the prompt's own
        per-chunk listing wording (domain_inference.py:75,77);
        check_evidence's exact-match lookup rejects it even though the
        chunk and quote are both genuine."""
        v = check_evidence(
            "rag_chunk",
            f"chunk_id={_REAL_CHUNK_ID}",
            _REAL_QUOTE,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT},
            utterances={},
            domain="depression",
        )
        assert v.verdict == VERDICT_REJECTED_UNKNOWN_SOURCE, (
            f"BUG-016: expected the prefixed source_id to reproduce "
            f"rejected_unknown_source (pre-fix behavior); got {v.verdict!r}. "
            "If this now passes, the source_id lookup may already be "
            "prefix-tolerant -- update error.md and invert this assertion "
            "per the BUG-007/BUG-015 precedent."
        )
        assert "not among the chunk_ids actually retrieved" in v.reason

    def test_unprefixed_source_id_is_accepted_control(self) -> None:
        """Control: the SAME chunk_id/quote pair, without the spurious
        prefix, is accepted -- isolates the defect to the FORMAT of
        source_id, not the content/grounding of the evidence itself (i.e.
        confirms this is an over-rejection, not a fabrication finding)."""
        v = check_evidence(
            "rag_chunk",
            _REAL_CHUNK_ID,
            _REAL_QUOTE,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT},
            utterances={},
            domain="depression",
        )
        assert v.verdict == VERDICT_ACCEPTED

    def test_stripping_the_prefix_recovers_acceptance(self) -> None:
        """Demonstrates the normalization-strip fix option (one of the two
        REV-010/BUG-016 fix options: defensively stripping a literal
        'chunk_id=' prefix from source_id before the chunk_texts lookup).
        This is a self-contained oracle computed inline -- it does NOT
        modify src/eval/f2_grounding.py; qa's charter is repro tests only."""
        prefixed = f"chunk_id={_REAL_CHUNK_ID}"
        normalized = prefixed.removeprefix("chunk_id=")
        assert normalized == _REAL_CHUNK_ID

        v_before = check_evidence(
            "rag_chunk", prefixed, _REAL_QUOTE,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT}, utterances={},
            domain="depression",
        )
        v_after = check_evidence(
            "rag_chunk", normalized, _REAL_QUOTE,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT}, utterances={},
            domain="depression",
        )
        assert v_before.verdict == VERDICT_REJECTED_UNKNOWN_SOURCE
        assert v_after.verdict == VERDICT_ACCEPTED

    def test_cascade_eliminates_candidate_when_sole_evidence_is_prefixed(self) -> None:
        """REV-010's flagged downstream risk (not observed in EXP-005 --
        every affected domain that batch retained >=1 other accepted item
        -- but a live risk in a sparser-evidence run, per REV-010's own
        wording: "could push a candidate to 0 accepted evidence and
        trigger an incorrect elimination"): a domain candidate whose ONLY
        evidence item carries the chunk_id= prefix is fully eliminated by
        filter_domain_candidates's "no evidence, no candidate" cascade
        (DomainCandidate.evidence min_length=1), even though the evidence
        is genuine and well-grounded."""
        domain_candidates = [
            DomainCandidate(
                domain="depression", confidence=0.6,
                evidence=[DomainEvidence(
                    source_type="rag_chunk",
                    source_id=f"chunk_id={_REAL_CHUNK_ID}",
                    quote=_REAL_QUOTE,
                )],
            ),
        ]
        filtered, verdicts, counts = filter_domain_candidates(
            domain_candidates,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT},
            utterances={},
        )
        assert filtered == [], (
            "BUG-016 cascade risk: expected the sole-evidence candidate to "
            "be eliminated (pre-fix). If this now survives, the source_id "
            "lookup may already be prefix-tolerant -- update error.md."
        )
        assert counts["rejected_unknown_source"] == 1
        assert counts["accepted"] == 0
