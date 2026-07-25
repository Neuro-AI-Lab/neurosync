"""Runtime grounding filter for clinical slot values (T1-F1-DEV-018).

Structural defense against extractor fabrication: a slot value is only
accepted into the session state when it can be tied to what the patient
actually said. This module is pure (no LLM, no I/O) and is shared by the
F1 pipeline runtime merge (src/f1.py) and the offline audit tool
(src/eval/grounding_audit.py) so both always agree.

Verdicts:
  - grounded           lexical evidence found in patient utterances
  - negative_grounded  negative-template value ("~없음" 계열) with ask evidence:
                       the AI targeted that slot and the patient's reply to that
                       question contains a negation morpheme
  - system_slot        system-side slots — never accepted from the extractor
  - ungrounded         everything else (rejected)

Design bias: err toward rejecting. A dropped true value costs one extra
question; an accepted fabricated value corrupts the clinical record.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# ── Slot key groups (12 Standard Clinical Slots) ─────────────────────

#: Slots produced by the system, never by the conversation extractor.
SYSTEM_SLOT_KEYS = frozenset({
    "encounter_metadata",
    "clinical_assessment",
    "treatment_plan",
})

#: Populated exclusively by the Safety Probe protocol in the pipeline.
RISK_SLOT_KEY = "risk_assessment"

#: Observation-based slot — only accepted with lexical evidence (rare by design).
OBSERVATION_SLOT_KEY = "mental_status_exam"

#: The 8 question-able slots — denominator of grounded_coverage.
QUESTIONABLE_SLOT_KEYS: list[str] = [
    "chief_complaint",
    "history_of_present_illness",
    "past_psychiatric_history",
    "medical_history",
    "personal_social_history",
    "family_history",
    "substance_use_history",
    "risk_assessment",
]

# ── Verdict labels ───────────────────────────────────────────────────

VERDICT_GROUNDED = "grounded"
VERDICT_NEGATIVE_GROUNDED = "negative_grounded"
VERDICT_SYSTEM_SLOT = "system_slot"
VERDICT_UNGROUNDED = "ungrounded"


@dataclass(frozen=True)
class GroundingVerdict:
    """Result of grounding evaluation for a single slot value."""

    key: str
    value: str
    verdict: str
    reason: str

    @property
    def accepted(self) -> bool:
        """True when the value may enter the session slot state."""
        return self.verdict in (VERDICT_GROUNDED, VERDICT_NEGATIVE_GROUNDED)


# ── Korean-tolerant lexical heuristics ───────────────────────────────

# Charting boilerplate that appears in fabricated/template fills. These tokens
# carry no patient-specific information, so they never count as evidence.
_GENERIC_TOKENS = frozenset({
    "없음", "없다", "없어요", "않음", "안함", "부인", "모름", "모른다", "미상",
    "아님", "미사용", "안됨", "안힘",
    "정보", "관련", "내용", "여부", "상태", "환자", "본인", "보고", "언급",
    "확인", "명시적", "구체적", "현재", "최근", "이력", "경험", "과거",
    "기록", "미수집", "해당", "특이사항", "사항", "관찰됨", "관찰",
})

_TOKEN_SPLIT_RE = re.compile(r"[^0-9A-Za-z가-힣]+")

# Negative-template markers in a slot VALUE ("~없음" 계열 charting shorthand).
_NEGATIVE_VALUE_RE = re.compile(
    r"(없음|없다|없어|부인|모름|모른|몰라|미사용|안\s?함|안\s?마심|안\s?먹|"
    r"하지\s?않|않음|않는다|않았|아니라고|아님)"
)

# Negation morphemes in a patient REPLY (없, 아니, 않, 모르 + standalone 안).
# Standalone 안 must be preceded by start/whitespace/punctuation so that
# words like 불안 do not count, and must not begin common 안-initial nouns
# (안정/안녕/안전/안심/안경/안내/안부/안방/안쪽/안과).
_REPLY_NEGATION_RE = re.compile(
    r"(없|아니|않|모르|몰라)"
    r"|(?:^|[\s.,!?~…\"'()\[\]-])안(?![정녕전심경내부방쪽과])\s*[가-힣]"
)


def _is_generic(token: str) -> bool:
    """True for boilerplate tokens that cannot serve as evidence."""
    if token in _GENERIC_TOKENS:
        return True
    # Negation-morpheme-initial tokens are boilerplate variants (없-, 않-).
    return token.startswith("없") or token.startswith("않")


def _content_tokens(text: str) -> list[str]:
    """DISTINCT content chunks of >= 2 chars, dropping boilerplate.

    ISS-045: tokens are deduplicated so repeating a topic noun
    ("가족 갈등, 가족 문제") cannot inflate the matched count.
    """
    tokens = [t for t in _TOKEN_SPLIT_RE.split(text) if len(t) >= 2]
    return list(dict.fromkeys(t for t in tokens if not _is_generic(t)))


def _token_matches(token: str, text: str) -> bool:
    """True if *token* or any prefix of it (>= 2 chars) occurs in *text*.

    Prefix matching tolerates Korean particles/endings: "불안감이" matches an
    utterance containing "불안해서" via the shared prefix "불안".
    """
    for length in range(len(token), 1, -1):
        if token[:length] in text:
            return True
    return False


def has_lexical_evidence(value: str, patient_utterances: Sequence[str]) -> bool:
    """Korean-tolerant check that *value* is traceable to patient utterances.

    Two directions, both conservative (tuned in tests/test_grounding_filter.py):
      forward: >= 50% of the value's content tokens match the utterances, AND
               at least 2 tokens match (unless the value has only 1 content token)
      reverse: >= 2 distinct utterance content tokens (>= 3 chars) appear
               verbatim inside the value
    """
    text = " ".join(u for u in patient_utterances if u).lower()
    if not text.strip():
        return False

    content = _content_tokens(value.lower())
    if content:
        matched = sum(1 for t in content if _token_matches(t, text))
        fraction_ok = (matched / len(content)) >= 0.5
        count_ok = matched >= 2 or (matched == 1 and len(content) == 1)
        if fraction_ok and count_ok:
            return True

    # Reverse direction: extractor quoted utterance chunks verbatim.
    value_lower = value.lower()
    reverse_hits = {
        t
        for u in patient_utterances
        for t in _content_tokens(u.lower())
        if len(t) >= 3 and t in value_lower
    }
    return len(reverse_hits) >= 2


def is_negative_template(value: str) -> bool:
    """True when *value* is essentially a negative-template fill ("~없음" 계열).

    The value must contain a negation marker AND be mostly boilerplate
    (<= 3 content tokens). Values mixing negation with substantive claims
    (e.g. "주 1-2회 맥주 1캔, 수면제 미사용") are NOT negative templates and
    must pass full lexical grounding instead.
    """
    if not _NEGATIVE_VALUE_RE.search(value):
        return False
    return len(_content_tokens(value)) <= 3


def reply_has_negation(text: str) -> bool:
    """True when a patient reply contains a negation morpheme (없/아니/않/모르/안)."""
    return bool(_REPLY_NEGATION_RE.search(text))


# BUG-084/coordinator directive (2026-07-25, "수집-불가 응답의 즉시-이동
# 규칙"): a "don't-know"/unanswerable reply ("잘 모르겠습니다"/"모르겠어요"/
# "모름") is clinically DISTINCT from an active denial ("없어요") — the
# patient is not affirmatively ruling the item out, they genuinely cannot
# answer. `_REPLY_NEGATION_RE` above already matches "모르"/"몰라" as a
# negation morpheme (by design, for the denial-detection use case), so a
# caller distinguishing the two MUST check `reply_is_dont_know` BEFORE
# `reply_has_negation` and branch on it first — otherwise a don't-know
# reply silently collapses into the "denied" bucket, mislabeling the
# clinical record (a patient who doesn't know whether they take a
# medication is not the same as one who denies taking any).
_DONT_KNOW_RE = re.compile(r"(모르겠|모름|모르겟|잘\s*몰라|모르겠구)")


def reply_is_dont_know(text: str) -> bool:
    """True when a patient reply expresses inability to answer / genuine
    not-knowing ("잘 모르겠습니다"/"모르겠어요"/"모름"), as opposed to an
    active denial. Checked separately from — and, by callers, BEFORE —
    `reply_has_negation`, since "모르"-rooted text also matches that
    broader negation check."""
    return bool(_DONT_KNOW_RE.search(text))


_SENTENCE_SPLIT_RE = re.compile(r"[.!?…~\n]")


def _negated_segments(patient_utterances: Sequence[str]) -> list[str]:
    """Sentence-level segments of the utterances that contain a negation.

    ISS-044 (polarity gate): a negation-bearing slot value may only ground
    against patient statements that are themselves negated — never against
    affirming statements sharing the same topic words.
    """
    segments: list[str] = []
    for utterance in patient_utterances:
        if not utterance:
            continue
        for segment in _SENTENCE_SPLIT_RE.split(utterance):
            segment = segment.strip()
            if segment and reply_has_negation(segment):
                segments.append(segment)
    return segments


def _normalize_asked_slots(
    asked_slots: Sequence[str | None] | Mapping[int, str] | None,
    n_utterances: int,
) -> list[str | None]:
    """Normalize asked-slot info to a list aligned with patient utterances."""
    aligned: list[str | None] = [None] * n_utterances
    if asked_slots is None:
        return aligned
    if isinstance(asked_slots, Mapping):
        for idx, slot in asked_slots.items():
            if isinstance(idx, int) and 0 <= idx < n_utterances:
                aligned[idx] = slot
        return aligned
    for i, slot in enumerate(asked_slots):
        if i < n_utterances:
            aligned[i] = slot
    return aligned


# ── Main entry point ─────────────────────────────────────────────────


def evaluate_slot_grounding(
    key: str,
    value: str,
    patient_utterances: Sequence[str],
    asked_slots: Sequence[str | None] | Mapping[int, str] | None = None,
) -> GroundingVerdict:
    """Evaluate whether an extractor-supplied slot value is grounded.

    Args:
        key: One of the 12 standard slot keys.
        value: The extractor-supplied flat string value.
        patient_utterances: All patient utterances so far, in order.
        asked_slots: Which slot the AI's question targeted for each patient
            utterance (aligned by index). Accepts a list aligned with
            *patient_utterances* or a mapping {utterance_index: slot_key}.
            ``None`` entries mean "unknown" — negative templates then fail
            the ask-evidence requirement (old runs are audited strictly).

    Returns:
        A GroundingVerdict; only grounded/negative_grounded are accepted.
    """
    value = (value or "").strip()
    if not value:
        return GroundingVerdict(key, value, VERDICT_UNGROUNDED, "empty value")

    # Placeholder echo — the v2 prompt uses <...> placeholders; any echo of
    # them (or any other angle-bracket template) is a fabrication signal.
    if "<" in value or ">" in value:
        return GroundingVerdict(
            key, value, VERDICT_UNGROUNDED, "placeholder/template echo in value"
        )

    if key in SYSTEM_SLOT_KEYS:
        return GroundingVerdict(
            key, value, VERDICT_SYSTEM_SLOT,
            "system-side slot — extractor-supplied values are always rejected",
        )

    if key == RISK_SLOT_KEY:
        return GroundingVerdict(
            key, value, VERDICT_UNGROUNDED,
            "risk_assessment is never accepted from the extractor "
            "(populated only by the safety probe protocol)",
        )

    if key == OBSERVATION_SLOT_KEY:
        if has_lexical_evidence(value, patient_utterances):
            return GroundingVerdict(
                key, value, VERDICT_GROUNDED,
                "observation slot with lexical evidence in patient utterances",
            )
        return GroundingVerdict(
            key, value, VERDICT_UNGROUNDED,
            "observation slot without lexical evidence "
            "(excluded from grounded coverage by design)",
        )

    # Question-able slots.
    # ISS-044 polarity gate: any negation-bearing value is checked BEFORE
    # plain lexical evidence — a negated claim must never ground against an
    # affirming utterance that merely shares topic words.
    if _NEGATIVE_VALUE_RE.search(value):
        if is_negative_template(value):
            # Essentially-negative template ("~없음" 계열): the ask-evidence
            # path is the ONLY way to ground it (never plain lexical).
            aligned = _normalize_asked_slots(asked_slots, len(patient_utterances))
            for i, utterance in enumerate(patient_utterances):
                if aligned[i] == key and reply_has_negation(utterance):
                    return GroundingVerdict(
                        key, value, VERDICT_NEGATIVE_GROUNDED,
                        f"negative template with ask evidence (utterance {i} "
                        f"answered a question targeting '{key}' with negation)",
                    )
            return GroundingVerdict(
                key, value, VERDICT_UNGROUNDED,
                "negative template without ask evidence "
                "(slot was never asked and answered with negation)",
            )
        # Negated value with substantive content: besides normal lexical
        # evidence, the negation must be polarity-consistent — at least one
        # content token of the value must be supported by a patient statement
        # that is itself negated. This blocks the ISS-044 inversion (value
        # negates what the patient affirmed) while still accepting values
        # that quote a real negated clause alongside affirmative content.
        negated_segments = _negated_segments(patient_utterances)
        negated_text = " ".join(negated_segments).lower()
        polarity_ok = negated_text and any(
            _token_matches(t, negated_text) for t in _content_tokens(value.lower())
        )
        if polarity_ok and has_lexical_evidence(value, patient_utterances):
            return GroundingVerdict(
                key, value, VERDICT_GROUNDED,
                "lexical evidence with polarity-consistent negation "
                "(negated patient statement supports the value)",
            )
        return GroundingVerdict(
            key, value, VERDICT_UNGROUNDED,
            "negated value without polarity-consistent evidence "
            "(no negated patient statement supports it)",
        )

    if has_lexical_evidence(value, patient_utterances):
        return GroundingVerdict(
            key, value, VERDICT_GROUNDED,
            "lexical evidence in patient utterances",
        )

    return GroundingVerdict(
        key, value, VERDICT_UNGROUNDED,
        "no lexical evidence in patient utterances",
    )


# ── BUG-077: literal-question topic inference ──────────────────────────

# Distinctive keyword sets per question-able slot — substrings that
# reliably indicate the LITERAL topic of a rendered assistant question,
# independent of any internally-tracked steering target. Deliberately
# narrow/non-overlapping and false-negative-biased: an ambiguous/generic
# question (e.g. a catch-all "혹시 다른 증상이나 걱정되는 부분은
# 없으신가요?") must infer NO slot rather than guess wrong — BUG-077's own
# repro showed that trusting the internally-recorded target unconditionally
# both over-attributes denials to slots never literally asked AND silently
# starves slots that WERE literally asked but not internally targeted.
# Sourced from `DialogueAgent._SLOT_QUESTION_GUIDE`'s own guide phrases and
# the v5.2 prompt's own worked examples — not independently invented, so
# the topic vocabulary here cannot drift from what the prompt/guide
# actually instructs the model to ask.
_SLOT_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "chief_complaint": ("가장 도움받고 싶은", "가장 힘든 문제", "오늘 어떤"),
    "history_of_present_illness": (
        "언제부터 시작", "최근 좋아지", "최근 악화", "일상생활에서",
        "수면/식사/일/대인관계", "증상이 언제부터",
    ),
    "risk_assessment": (
        "스스로를 해치", "죽고 싶다는 생각", "자해", "자살", "타해",
    ),
    "substance_use_history": (
        "음주", "수면제", "진정제", "카페인", "물질 사용", "담배", "흡연",
    ),
    "past_psychiatric_history": (
        "정신건강의학과 진료", "심리상담", "진단받은 병명", "정신과 진료",
        "기존 진료기록",
    ),
    "medical_history": (
        "신체질환", "처방 약 외", "복용 중인 약", "변경된 약",
    ),
    "personal_social_history": (
        "힘이 되어주는 사람", "도움을 요청할 수 있는 사람", "연락하거나 도움",
    ),
    "family_history": (
        "가족분들 중에", "비슷한 어려움을 겪으셨던", "가족력",
    ),
}


def infer_literal_target_slot(text: str) -> str | None:
    """BUG-077: infer which question-able slot a rendered assistant
    question LITERALLY, recognizably asked about — via topic-keyword match
    against `_SLOT_TOPIC_KEYWORDS`. Returns None when no slot's keywords
    match (an ambiguous/generic "catch-all" question) — deliberately
    conservative (no guess), since a wrong guess here would recreate
    BUG-077's over-attribution symptom at a different call site.

    BUG-085 (live repro, session `de33cf67`): a rendered turn routinely
    RECAPS the prior turn's answer before asking THIS turn's new question
    (e.g. "신체질환이나 복용 중인 약이 없으시다고 하셨는데, 혹시 가족분들 중에서
    ... 계신가요?" — recaps `medical_history`, then asks `family_history`).
    The previous dict-insertion-order first-match scan returned whichever
    slot happened to be earlier in `_SLOT_TOPIC_KEYWORDS`'s iteration order
    (`medical_history` before `family_history`), regardless of where in
    the TEXT it occurred — so a recap phrase silently outranked the actual
    closing question. That misattribution fed straight into
    `OrchestratorAgent._update_asked_slot_tracking`'s ask-evidence check:
    the true target (`family_history`) never matched the wrongly-inferred
    `literal_slot` (`medical_history`, already filled), so a valid
    don't-know/denial reply was NEVER grounded — the round-robin kept
    re-selecting `family_history` turn after turn (observed live: asked 3
    times, turns 7/9/13, despite two "모르겠" replies).
    Fix: among ALL matching slots, return the one whose keyword occurs at
    the RIGHTMOST (latest) position in `text` — the closing question, not
    an earlier recap clause, is what the turn is actually asking. Ties
    (same rightmost index) fall back to `_SLOT_TOPIC_KEYWORDS` iteration
    order for determinism.

    Pure, no I/O — shared by `DialogueAgent` (BUG-077 item A: target-
    binding validation guard on its own generated candidate) and
    `OrchestratorAgent` (BUG-077 item B: bare-denial ask-evidence
    attribution) so both use the exact same "what did this text literally
    ask about" definition."""
    if not text:
        return None
    best_slot: str | None = None
    best_index = -1
    for slot, keywords in _SLOT_TOPIC_KEYWORDS.items():
        for kw in keywords:
            idx = text.rfind(kw)
            if idx > best_index:
                best_index = idx
                best_slot = slot
    return best_slot


# ── BUG-078: patient meta-utterance detection (topic-relevance gate) ────

# Substrings that reliably indicate a patient reply is a meta-complaint
# about the CONVERSATION/AGENT itself (repetitive questioning, or the
# agent's own competence/memory) rather than an answer to whatever was
# just asked — direct protest ("왜 자꾸 물어봐", "몇 번을 말해요", "그만 좀
# 물어보세요"), indirect "I already answered this" phrasing ("아까도
# 말했잖아요", "방금 말씀드렸는데요", "이미 얘기했잖아요"), and (2026-07-25,
# user-reported live session `04cfe927`) a THIRD shape this list previously
# had zero coverage for: complaints directed at the AGENT'S OWN
# capability/memory ("기억 못하시나요?", "너 못하냐고") — the patient is not
# disclosing anything about themselves in any of these three shapes; all
# three are "this conversation/you, the agent, are the problem" utterances,
# the same underlying category `is_meta_utterance` exists to recognize.
# Principle, not an exhaustive enumeration (CVR-057 / BUG-030 lesson —
# keyword lists here are a narrow, conservative CODE-LEVEL gate; the
# broader, generalizable recognition principle lives in the dialogue
# prompt's own "환자 메타-발화 처리" section). Deliberately narrow/
# false-negative-biased, same discipline as `_SLOT_TOPIC_KEYWORDS`: a
# genuine SI answer must never be misread as a meta-complaint (a false
# positive here would drop a real denial), so only reasonably distinctive
# phrasing is listed.
_META_UTTERANCE_KEYWORDS: tuple[str, ...] = (
    "왜 자꾸", "왜 또", "몇 번을", "몇 번이나", "몇번을", "그만 좀", "그만좀",
    "말했잖아", "말씀드렸잖아", "말씀드렸는데", "얘기했잖아", "이야기했잖아",
    "이미 말했", "이미 말씀드렸", "이미 얘기했", "아까도 말", "아까 말했",
    "방금 말씀드렸", "또 물어봐", "다시 물어봐", "자꾸 물어봐",
    # 2026-07-25 (session `04cfe927`): agent capability/memory complaints.
    "기억 못", "기억을 못", "기억못", "못하시나요", "못 하시나요",
    "못하냐고", "못 하냐고", "못하는거야", "못 하는거야",
)


def is_meta_utterance(text: str) -> bool:
    """BUG-078/BUG-085-follow-up: True when *text* is a patient
    meta-complaint about the conversation/agent itself (repetitive
    questioning, or the agent's own competence/memory) — NOT a
    substantive answer to whatever the AI just asked (SI screen
    included). Deliberately conservative — matches only the direct/
    indirect repetition-complaint and capability/memory-complaint
    phrasing the dialogue prompt itself teaches (see
    `_META_UTTERANCE_KEYWORDS`); an unmatched reply is assumed to be a
    genuine, on-topic answer.

    Matching is whitespace-collapsed on both sides (2026-07-25, session
    `04cfe927` live finding): a patient reply with natural spacing
    variance ("이야기 했잖아" vs the keyword's "이야기했잖아") previously
    fell through this substring check silently — collapsing internal
    whitespace before comparison closes that gap without widening the
    keyword list's own conservative scope.

    Pure, no I/O — used by `OrchestratorAgent._advance_safety_probe` to
    gate `safety_probe.compose_screen_risk_assessment` so a repetition
    complaint is never fabricated into a permanent SI-denial citation
    (BUG-078's own live repro: "없다니까 왜 자꾸 물어봐요." falsely
    grounding risk_assessment via `reply_has_negation` alone)."""
    if not text:
        return False
    collapsed = re.sub(r"\s+", "", text)
    return any(re.sub(r"\s+", "", kw) in collapsed for kw in _META_UTTERANCE_KEYWORDS)


def verdict_to_slot_status(verdict: GroundingVerdict) -> str:
    """Map a `GroundingVerdict` to the 3-state wire label (BUG-072/073 wave):
    ``"filled"`` | ``"denied"`` | ``"missing"``.

    Used by both `routes/slots.py::_apply_grounding_filter` and
    `agents/orchestrator.py` so the two callers never hand-duplicate this
    mapping. ``system_slot``/``ungrounded`` both collapse to ``"missing"``
    — the extractor proposed no *accepted* value for this turn; callers
    must not confuse this with "confirmed absent" (only
    `VERDICT_NEGATIVE_GROUNDED` means that).
    """
    if verdict.verdict == VERDICT_NEGATIVE_GROUNDED:
        return "denied"
    if verdict.verdict == VERDICT_GROUNDED:
        return "filled"
    return "missing"


def grounded_coverage(filled_slots: Mapping[str, str]) -> float:
    """Fraction of the 8 question-able slots present in *filled_slots*.

    Callers must only pass values that already passed the grounding filter
    (or were composed by the safety probe protocol).
    """
    filled = [k for k in QUESTIONABLE_SLOT_KEYS if filled_slots.get(k)]
    return len(filled) / len(QUESTIONABLE_SLOT_KEYS)
