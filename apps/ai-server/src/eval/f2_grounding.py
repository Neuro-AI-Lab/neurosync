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

ADR-014 / VAL-006 / REV-008 (2026-07-08): the domain_inference prompt's rule 2
("위험 표현을 domain confidence의 근거로 사용하지 않는다") is prose-only and was
confirmed to fail live — VP-003 2/2 runs cited a verbatim passive-suicidal-
ideation utterance ("살고 싶지 않아요...") as `depression` evidence, the fourth
recurrence of this project's prompt-only-enforcement gap (see BUG-010/ADR-012,
VAL-002/VAL-004 for the prior three). This module now ALSO code-enforces rule
2: any evidence quote containing a risk-class expression is rejected before it
can reach an accepted candidate, regardless of what the prompt says.

Design decision (lexicon source): a small, dedicated lexicon is defined below
rather than importing `src.agents.safety_classifier`'s `_CRITICAL_KEYWORDS` /
`_HIGH_KEYWORDS` / `_MEDIUM_KEYWORDS`. Reasons: (1) those are private
(underscore-prefixed) internals of a different agent's triage module, not a
published interface — importing them couples F2's evidence filter to Safety's
triage tuning and would break silently on unrelated Safety changes; (2) their
scope is triage-breadth (e.g. bare `"죽을"` as a suicidal-ideation stem in
`_CRITICAL_KEYWORDS`), which is deliberately broader than a "must never be
domain evidence" filter needs and would collide with the ISS-046 panic-idiom
carve-out this module must preserve (SM-07a: "그때 정말 죽는 줄 알았어요" must
NOT be rejected — `_CRITICAL_KEYWORDS` alone would reject it via the bare
`"죽을"` substring); (3) `_MEDIUM_KEYWORDS` mixes in general despair/distress
terms ("너무 힘들", "미치겠", "희망이 없") that are not the SI/self-harm/
death-directed class this filter targets. A dedicated, disjoint-by-construction
lexicon keeps this filter's blast radius small and auditable independent of
Safety's own tuning.

Pure, no I/O, no LLM — mirrors `src.grounding`'s verdict-object style so audit
output stays uniform across F1 and F2.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

from src.grounding import has_lexical_evidence
from src.schemas.domain_inference import DepartmentCandidate, DomainCandidate, DomainEvidence

logger = logging.getLogger(__name__)

VERDICT_ACCEPTED = "accepted"
VERDICT_REJECTED_UNKNOWN_SOURCE = "rejected_unknown_source"
VERDICT_REJECTED_QUOTE_MISMATCH = "rejected_quote_mismatch"
VERDICT_REJECTED_UNKNOWN_TYPE = "rejected_unknown_source_type"
VERDICT_REJECTED_RISK_LEXICON = "rejected_risk_lexicon"

_ALL_VERDICTS = (
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_UNKNOWN_SOURCE,
    VERDICT_REJECTED_QUOTE_MISMATCH,
    VERDICT_REJECTED_UNKNOWN_TYPE,
    VERDICT_REJECTED_RISK_LEXICON,
)

# ── Risk lexicon (ADR-014 / VAL-006 / REV-008; BUG-014 / BUG-015 revision) ─
#
# Dedicated, F2-specific list of 자살/자해/죽음-지향 SI-class expressions.
# A quote containing any of these is mechanically unusable as domain-
# confidence evidence — see rejection reason text in `check_evidence` for
# the rule-2 citation. Kept intentionally small and reviewed deliberately
# (not copy-pasted from another module's triage tables — see module
# docstring) so its behavior stays predictable and testable.
#
# BUG-015: every entry below is multi-word and SI/self-harm-directed by
# construction. The prior bare, context-free "손목" ("wrist") / "목숨"
# ("life") entries are removed — they rejected benign clinical quotes with
# no SI/self-harm meaning at all (wrist-pain somatic complaints,
# accident-survivor narratives, idiomatic-effort expressions). Replaced
# with "손목을 긋"/"손목을 그" (self-harm-by-cutting; same multi-word,
# ISS-038-precedented stem convention already used by
# `src.agents.safety_classifier`/`src.agents.input_normalizer` for exactly
# this over-match reason) and "목숨을 끊"/"목숨을 버리" (suicide-directed
# "end one's life" usage) instead of the bare nouns.
_RISK_PHRASES: tuple[str, ...] = (
    "자살",
    "살고 싶지 않",
    "살고싶지않",
    "죽고 싶",
    "죽고싶",
    "사라지고 싶",
    "사라지고싶",
    "없어지고 싶",
    "없어지고싶",
    "내가 없으면",
    "내가없으면",
    "자해",
    "손목을 긋",
    "손목을긋",
    "손목을 그",
    "손목을그",
    "목숨을 끊",
    "목숨을끊",
    "목숨을 버리",
    "목숨을버리",
    "유서",
    # BUG-014 / VAL-009 / REV-009 Attack 1: burdensomeness paraphrase family
    # — same construct as "내가 없으면 다 편할 텐데", different surface
    # wording (live-observed VP-003 run1 turn_5/9: "짐이 되기 싫어서").
    "짐이 되",
    "짐이되",
    "짐만 되",
    "짐만되",
    "부담이 되",
    "부담이되",
    # BUG-014: meaninglessness paraphrase family — BUG-007/ADR-010's
    # canonical anchor "사는 게 의미가 없다" (previously zero lexicon
    # coverage) and its live-observed paraphrase (VP-003 run1 turn_10/12:
    # "살아서 뭐하나"). "사는 게 의미" is scoped to the life-context anchor,
    # not a bare "의미가 없" (which would over-match unrelated "이 일은
    # 의미가 없어요"-style statements).
    "사는 게 의미",
    "사는게의미",
    "살아서 뭐하",
    "살아서뭐하",
    # BUG-014: standalone death-directed ideation (qa's additional exposure
    # beyond REV-008/VAL-009's 3 named quotes) — same family as "죽고 싶다".
    "죽으면 편할",
    "죽으면편할",
    # BUG-014 QA re-verification (2026-07-08, REV-009 Attack 4 residual):
    # "better off dead" via 낫다 ("preferable/better") — "죽는 게 낫다"/
    # "차라리 죽는 게 나을 것 같다" family. Two narrow stems, not one broad
    # "죽는 게 나"-style stem: 낫다 is a ㅅ-irregular adjective whose stem
    # keeps ㅅ before a consonant-initial ending (낫다, 낫겠다) but drops it
    # before a vowel-initial ending (나을, 나아) — so "낫" and "나을" share no
    # common substring past "죽는 게 ", and a single broad "죽는 게 나" stem
    # would ALSO match unrelated third-person narrative (e.g. "그가 죽는 게
    # 나에게는 슬펐다" — "their dying was sad for me"), the same
    # over-blocking failure class BUG-015 just fixed. "죽는 게 낫" catches
    # the ㅅ-preserved forms; "차라리 죽" catches the 나을/나아 forms via the
    # co-occurring "차라리" ("rather/instead") prefix qa's synthetic
    # phrasing and the actual VP-004 artifact both use, without the broader
    # stem's over-match risk. Verified disjoint from `_PANIC_IDIOM_PHRASES`
    # (test_risk_and_panic_idiom_lexicons_are_disjoint) — neither stem is a
    # substring of "죽는 줄 알았"/"죽을 것 같"/"죽는 것 같" or vice versa.
    "죽는 게 낫",
    "죽는게낫",
    "차라리 죽",
    "차라리죽",
    # VAL-015 (docs/ai/workflow_discussion_f1f2.md ISS-F2V-019; EXP-016
    # finding 43, SC-5 VP-003 session2 live artifact
    # `_archive/simulation_results/VP-003/VP-003_20260711_222853_
    # domain_inference.json` `retrieval_meta.queries`: "...살기 싫어요."):
    # grammatically distinct "hate/dislike living" construction (나 + 기
    # nominalizer + 싫다) from the 4 already-covered stems VAL-015
    # confirmed do NOT match it (살고 싶지 않/죽고 싶/사라지고 싶/짐이 되) —
    # verified no shared substring with any of them, and disjoint from
    # `_PANIC_IDIOM_PHRASES` (no idiom stem contains "살").
    "살기 싫",
    "살기싫",
    # VAL-015: the Korean-only lexicon does not catch English-language
    # risk-worded content — real, structural exposure via the (retired)
    # Policy-B's judge-composed retrieval queries (EXP-016 findings 27/31/34,
    # verbatim `retrieval_meta.queries` text re-extracted from
    # `_archive/simulation_results/VP-003/VP-003_20260711_220220_domain_
    # inference.json` / `..._220541_...json`: "...passive suicidal
    # ideation..." / "persistent thoughts of death..."). Matching is
    # case-insensitive (`_contains_any` casefolds both sides below);
    # Hangul is unaffected by casefold so existing Korean stems are
    # unchanged. "thoughts of death" is deliberately narrower than a bare
    # "death" stem to avoid unrelated clinical narrative (e.g. "history
    # of death in the family"); checked disjoint from this project's
    # English panic-fear-of-dying phrasing, which uses "going to die"/
    # "feared I would die" (event-fear) rather than "thoughts of death"
    # (ideation-about-death-as-outcome) — see
    # test_english_panic_fear_quote_not_risk_lexicon_rejected.
    "suicidal ideation",
    "thoughts of death",
    # Remaining minimal English SI class (want to die / don't want to
    # live / kill myself / end my life / self-harm) — brief-directed
    # (docs/ai/lexicon_expansion_val010.md §2b), not independently
    # observed verbatim in EXP-016/EXP-026 evidence, but each is the
    # direct English analogue of an already-covered Korean stem (죽고
    # 싶/살고 싶지 않/자해) so the exposure class is the same, just
    # untested in this project's own live English-query corpus to date.
    "want to die",
    "don't want to live",
    "do not want to live",
    "kill myself",
    "end my life",
    "self-harm",
    "self harm",
)

# ISS-046 exception (SM-07a precedent): panic-attack fear-of-dying idioms
# ("그때 정말 죽는 줄 알았어요", "죽을 것 같고") are legitimate anxiety-domain
# clinical evidence, not suicidal-risk content (DSM-5 recognizes fear-of-
# dying as a panic-attack criterion) — they must NOT be rejected by this
# filter. The exemption is enforced structurally: `_PANIC_IDIOM_PHRASES` is
# disjoint from `_RISK_PHRASES` by construction (asserted in
# tests/test_f2_grounding.py::test_risk_and_panic_idiom_lexicons_are_disjoint)
# rather than via a runtime carve-out that special-cases a rejection decision
# — REV-008 issue #6 already flagged that LLM-judged idiom carve-outs are a
# "circular qualifier" failure class; a structural (lexicon-level) guarantee
# avoids that fragility entirely. `is_panic_idiom_evidence()` below is a
# separate, positive classifier used only to annotate accepted evidence for
# audit traceability (and by prompt v2 / SM-07b tests) — it never gates a
# rejection, so a genuine risk phrase co-occurring with idiom text in the
# same quote (SM-07b) is still rejected on its own terms.
_PANIC_IDIOM_PHRASES: tuple[str, ...] = (
    "죽는 줄 알았",
    "죽는줄알았",
    "죽을 것 같",
    "죽을것같",
    "죽는 것 같",
    "죽는것같",
)

# Physical panic-symptom context words (SM-07a script: "심장이 미친듯이 뛰고
# 숨을 못 쉬어서"; VP-004: "공황 발작이 오면") — `is_panic_idiom_evidence`
# requires one of these alongside an idiom phrase; a bare death-fear phrase
# with no symptom context is not confidently classified as this carve-out.
_PANIC_SYMPTOM_CONTEXT: tuple[str, ...] = (
    "심장", "숨", "가슴", "어지럽", "질식", "공황", "발작",
    "떨림", "떨려", "답답", "메스꺼", "저림", "저려",
)


# BUG-016 (REV-010 finding 1): `DomainInferenceAgent._build_user_content`
# (`src/agents/domain_inference.py`) used to header the retrieved-chunk block
# and list each chunk with the literal string `chunk_id=` sitting directly
# adjacent to the id — Solar Pro3 sometimes echoed that literal label back
# into the `source_id` field it emitted (e.g. `"chunk_id=case_card:687"`
# instead of `"case_card:687"`), which the exact-match lookup below then
# rejected as `rejected_unknown_source` even though the cited chunk/quote
# were both genuine. The prompt-wording side of this is fixed too (defense
# in depth — the literal string no longer appears adjacent to the id), but a
# prompt-only fix is not deterministic (this project's own history —
# VAL-006/REV-008/ADR-014 — is exactly why rule enforcement here is
# code-level, not prompt-only). This regex defensively strips a leading
# `chunk_id=` (and whitespace variants around `=`) from a `rag_chunk`
# source_id BEFORE the lookup, so a benign formatting echo does not cost
# genuine, well-grounded evidence.
_CHUNK_ID_PREFIX_RE = re.compile(r"^\s*chunk_id\s*=\s*")


def _normalize_rag_chunk_source_id(source_id: str) -> str:
    """Strip a leading `chunk_id=` prefix (BUG-016) from a rag_chunk source_id.

    Space-insensitive around `=` (e.g. ``"chunk_id = case_card:1"``), applied
    once. A source_id with no such prefix is returned unchanged.
    """
    return _CHUNK_ID_PREFIX_RE.sub("", source_id, count=1)


def _contains_any(text: str, phrases: tuple[str, ...]) -> list[str]:
    """Phrases (space- and case-insensitive) actually present in *text*, in
    list order.

    VAL-015 (docs/ai/lexicon_expansion_val010.md §2b): case-folding added
    to catch English-stem casing variants (e.g. a judge-composed query
    capitalizing "Suicidal Ideation" at a sentence start). `.casefold()` is
    a no-op on Hangul, so existing Korean-only matching behavior is
    unchanged.
    """
    collapsed = text.replace(" ", "").casefold()
    return [p for p in phrases if p.replace(" ", "").casefold() in collapsed]


def is_panic_idiom_evidence(quote: str) -> bool:
    """True when *quote* is an ISS-046 panic fear-of-dying idiom (SM-07a).

    Requires BOTH an idiom phrase and physical-symptom context in the same
    quote. Informational only — never gates the risk-lexicon rejection
    decision (see module note above / SM-07b).
    """
    return bool(_contains_any(quote, _PANIC_IDIOM_PHRASES)) and bool(
        _contains_any(quote, _PANIC_SYMPTOM_CONTEXT)
    )


def _risk_lexicon_hits(quote: str) -> list[str]:
    """Risk-class phrases (`_RISK_PHRASES`) found in *quote*, else []."""
    return _contains_any(quote, _RISK_PHRASES)


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
    ocr_texts: Mapping[str, str] | None = None,
    domain: str = "",
) -> EvidenceVerdict:
    """Whitelist check for a single evidence item.

    Args:
        chunk_texts: {chunk_id: full_text} for chunks ACTUALLY returned this
            run (Stage 1 output, e.g. ``{"case_card:12": "..."}``).
        utterances: {utterance_id: text} for F1 patient utterances ACTUALLY
            available this run (e.g. ``{"turn_3": "..."}``).
        ocr_texts: {document_id: full_text} for OCR documents ACTUALLY
            available this run. PLAN-2026-W28-Q W1: the ``ocr_document``
            ``EvidenceSourceType`` value exists (auditability), but no
            caller wires real OCR content into this run yet — defaults to
            ``{}``, so any ``ocr_document`` citation today correctly falls
            through to ``rejected_unknown_source`` (no evidence, no
            candidate) rather than being misclassified as an unrecognized
            type.
    """
    quote = (quote or "").strip()
    source_id = (source_id or "").strip()
    ocr_texts = ocr_texts or {}

    if source_type == "rag_chunk":
        # BUG-016: normalize a benign `chunk_id=` prefix echo ONCE, before
        # the lookup — the normalized id is used for both the lookup and the
        # recorded verdict (a caller reading `EvidenceVerdict.source_id` back
        # sees the same id that was actually checked, not the raw model output).
        source_id = _normalize_rag_chunk_source_id(source_id)
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
    elif source_type == "ocr_document":
        text = ocr_texts.get(source_id)
        if text is None:
            return EvidenceVerdict(
                domain, source_type, source_id, quote, VERDICT_REJECTED_UNKNOWN_SOURCE,
                f"source_id {source_id!r} is not among the OCR documents actually "
                "available this run",
            )
    else:
        return EvidenceVerdict(
            domain, source_type, source_id, quote, VERDICT_REJECTED_UNKNOWN_TYPE,
            f"unknown source_type {source_type!r} — must be "
            "rag_chunk|utterance|ocr_document",
        )

    if not quote:
        return EvidenceVerdict(
            domain, source_type, source_id, quote, VERDICT_REJECTED_QUOTE_MISMATCH,
            "empty quote",
        )

    # ADR-014 / VAL-006 / REV-008: code-enforced rule 2 — risk-class quotes
    # are never usable as domain-confidence evidence, regardless of source
    # legitimacy or lexical grounding. Checked before the lexical-grounding
    # check below so a risky AND fabricated quote is reported for the more
    # specific, actionable reason.
    risk_hits = _risk_lexicon_hits(quote)
    if risk_hits:
        return EvidenceVerdict(
            domain, source_type, source_id, quote, VERDICT_REJECTED_RISK_LEXICON,
            "quote contains risk-class expression(s) "
            f"({', '.join(risk_hits)}) — suicidal-ideation/self-harm/"
            "death-directed content is never domain-confidence evidence "
            "(prompt rule 2, code-enforced per ADR-014); cite a non-risk "
            "symptom or 징후 instead",
        )

    # Same lexical-grounding primitive F1 uses for utterance evidence — now
    # applied to rag_chunk text too (REV-006 #1: content check, not id-only).
    if not has_lexical_evidence(quote, [text]):
        return EvidenceVerdict(
            domain, source_type, source_id, quote, VERDICT_REJECTED_QUOTE_MISMATCH,
            f"quote is not lexically supported by the {source_type}'s actual text",
        )

    reason = f"quote lexically matches the retrieved {source_type} text"
    if is_panic_idiom_evidence(quote):
        reason += (
            " (ISS-046 panic fear-of-dying idiom — legitimate anxiety-domain "
            "evidence, not risk content; SM-07a precedent)"
        )
    return EvidenceVerdict(domain, source_type, source_id, quote, VERDICT_ACCEPTED, reason)


def audit_domain_candidates(
    domain_candidates: list[DomainCandidate],
    *,
    chunk_texts: Mapping[str, str],
    utterances: Mapping[str, str],
    ocr_texts: Mapping[str, str] | None = None,
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
                    ocr_texts=ocr_texts,
                    domain=cand.domain,
                )
            )
    counts = {v: 0 for v in _ALL_VERDICTS}
    for verdict in verdicts:
        counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
    return verdicts, counts


def filter_domain_candidates(
    domain_candidates: list[DomainCandidate],
    *,
    chunk_texts: Mapping[str, str],
    utterances: Mapping[str, str],
    ocr_texts: Mapping[str, str] | None = None,
) -> tuple[list[DomainCandidate], list[EvidenceVerdict], dict[str, int]]:
    """Apply the whitelist (incl. the risk-lexicon filter) AND cascade the result.

    ADR-014 rejection cascade: rejected evidence items (any reason, incl. the
    new risk-lexicon class) are removed from a candidate's evidence list. If
    a candidate's ACCEPTED evidence count drops to 0, the candidate itself is
    eliminated — ``DomainCandidate.evidence`` has ``min_length=1`` (plan C-2
    hard rule: "no evidence, no candidate"), so a candidate with zero
    surviving evidence is not a schema-valid candidate and must not be
    emitted, not emitted with an empty ``evidence: []``.

    A candidate that survives with SOME (not all) evidence rejected keeps
    only its accepted items; the stripped count is logged for audit.

    Returns:
        (filtered_candidates, verdicts, counts) — ``verdicts``/``counts``
        cover every evidence item submitted (accepted + all rejection
        reasons), same shape as :func:`audit_domain_candidates`, so callers
        retain the full audit trail even though rejected items are removed
        from ``filtered_candidates``.
    """
    verdicts: list[EvidenceVerdict] = []
    filtered: list[DomainCandidate] = []
    for cand in domain_candidates:
        accepted_evidence: list[DomainEvidence] = []
        n_stripped = 0
        for ev in cand.evidence:
            v = check_evidence(
                ev.source_type, ev.source_id, ev.quote,
                chunk_texts=chunk_texts, utterances=utterances, ocr_texts=ocr_texts,
                domain=cand.domain,
            )
            verdicts.append(v)
            if v.accepted:
                accepted_evidence.append(ev)
            else:
                n_stripped += 1

        if not accepted_evidence:
            logger.info(
                "f2_grounding.cascade.candidate_eliminated — domain=%s, "
                "all %d evidence item(s) rejected",
                cand.domain, n_stripped,
            )
            continue

        if n_stripped:
            logger.info(
                "f2_grounding.cascade.evidence_stripped — domain=%s, "
                "stripped=%d, remaining=%d",
                cand.domain, n_stripped, len(accepted_evidence),
            )
        filtered.append(cand.model_copy(update={"evidence": accepted_evidence}))

    counts = {v: 0 for v in _ALL_VERDICTS}
    for verdict in verdicts:
        counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
    return filtered, verdicts, counts


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
