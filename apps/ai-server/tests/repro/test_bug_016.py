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

FIXED (2026-07-08, PLAN-2026-W28-G T1-dev): both options landed. Primary
(deterministic, option b) -- `check_evidence` now strips a leading
`chunk_id=` prefix (`_normalize_rag_chunk_source_id`,
`src/eval/f2_grounding.py`) before the `chunk_texts` lookup, once, using the
normalized id for both the lookup and the recorded verdict. Defense in
depth (option a) -- `_build_user_content`'s per-chunk listing wording
(`domain_inference.py`) no longer places the literal string `chunk_id=`
directly adjacent to the id. Tests 1 and 4 below are inverted accordingly
(were: reproduce the over-rejection; now: confirm it no longer occurs) per
the BUG-007/BUG-014/BUG-015 repro-test convention; test 2 (control) is
unchanged. Test 3 (previously a self-contained inline oracle computed
WITHOUT calling the still-buggy `check_evidence` for the prefixed case) is
updated to call `check_evidence` for both the prefixed and unprefixed id
and confirm they now converge -- the oracle it demonstrated is now the
real, live code path, not a hypothetical for a future developer to port.
"""

from __future__ import annotations

from src.eval.f2_grounding import (
    VERDICT_ACCEPTED,
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
    def test_prefixed_source_id_accepted_after_normalization_fix(self) -> None:
        """BUG-016 fixed (2026-07-08, PLAN-2026-W28-G T1-dev): the exact
        production defect -- the model's source_id carries the literal
        `chunk_id=` prefix from the prompt's own per-chunk listing wording
        (domain_inference.py, now reworded as defense-in-depth) -- no longer
        causes an over-rejection. `check_evidence` (`f2_grounding.py`,
        `_normalize_rag_chunk_source_id`) strips the prefix before the
        `chunk_texts` lookup, so the genuine, well-grounded chunk/quote is
        accepted. Inverted from the pre-fix assertion
        (`rejected_unknown_source`) per the BUG-007/BUG-014/BUG-015
        repro-test convention."""
        v = check_evidence(
            "rag_chunk",
            f"chunk_id={_REAL_CHUNK_ID}",
            _REAL_QUOTE,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT},
            utterances={},
            domain="depression",
        )
        assert v.verdict == VERDICT_ACCEPTED, (
            f"BUG-016 regression: expected the chunk_id=-prefixed source_id "
            f"to be normalized and accepted (post-fix behavior); got "
            f"{v.verdict!r} ({v.reason!r})."
        )
        # The recorded verdict carries the NORMALIZED id (BUG-016 fix
        # requirement: normalize once, use for both the lookup and the
        # recorded verdict), not the raw prefixed one the model emitted.
        assert v.source_id == _REAL_CHUNK_ID

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

    def test_prefixed_and_unprefixed_source_id_now_converge(self) -> None:
        """BUG-016 fixed: this test used to demonstrate the normalization-
        strip fix option as a self-contained inline oracle WITHOUT calling
        into `check_evidence` for the prefixed case (`check_evidence` itself
        was still buggy at the time). Now that the fix has landed in
        `check_evidence` (`_normalize_rag_chunk_source_id`), both the
        prefixed and unprefixed source_id for the SAME chunk/quote converge
        on the same accepted verdict through the real code path -- there is
        no longer a behavioral difference to strip manually."""
        prefixed = f"chunk_id={_REAL_CHUNK_ID}"

        v_prefixed = check_evidence(
            "rag_chunk", prefixed, _REAL_QUOTE,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT}, utterances={},
            domain="depression",
        )
        v_unprefixed = check_evidence(
            "rag_chunk", _REAL_CHUNK_ID, _REAL_QUOTE,
            chunk_texts={_REAL_CHUNK_ID: _REAL_CHUNK_TEXT}, utterances={},
            domain="depression",
        )
        assert v_prefixed.verdict == VERDICT_ACCEPTED
        assert v_unprefixed.verdict == VERDICT_ACCEPTED
        assert v_prefixed.source_id == v_unprefixed.source_id == _REAL_CHUNK_ID

    def test_cascade_no_longer_eliminates_candidate_when_sole_evidence_is_prefixed(
        self,
    ) -> None:
        """BUG-016 fixed: REV-010's flagged downstream risk ("could push a
        candidate to 0 accepted evidence and trigger an incorrect
        elimination") no longer materializes. A domain candidate whose ONLY
        evidence item carries the chunk_id= prefix now SURVIVES
        filter_domain_candidates's cascade -- the normalization fix means
        the genuine, well-grounded evidence is accepted, not stripped.
        Inverted from the pre-fix assertion (`filtered == []`) per the
        BUG-007/BUG-014/BUG-015 repro-test convention."""
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
        assert len(filtered) == 1, (
            "BUG-016 regression: expected the sole-evidence candidate to "
            "survive (post-fix behavior) -- it was eliminated instead."
        )
        assert filtered[0].domain == "depression"
        assert len(filtered[0].evidence) == 1
        # NOTE: the normalized id is used for the LOOKUP and the recorded
        # EvidenceVerdict (see the prior test) -- the surviving
        # DomainCandidate.evidence item itself is the model's original,
        # un-mutated DomainEvidence object, so its source_id stays the raw
        # (prefixed) string the model actually emitted. This preserves full
        # audit fidelity of what the LLM said, distinct from what was
        # verified against.
        assert filtered[0].evidence[0].source_id == f"chunk_id={_REAL_CHUNK_ID}"
        assert counts["accepted"] == 1
        assert counts["rejected_unknown_source"] == 0
