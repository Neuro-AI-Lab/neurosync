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


def grounded_coverage(filled_slots: Mapping[str, str]) -> float:
    """Fraction of the 8 question-able slots present in *filled_slots*.

    Callers must only pass values that already passed the grounding filter
    (or were composed by the safety probe protocol).
    """
    filled = [k for k in QUESTIONABLE_SLOT_KEYS if filled_slots.get(k)]
    return len(filled) / len(QUESTIONABLE_SLOT_KEYS)
