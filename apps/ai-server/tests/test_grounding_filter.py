"""T1-F1-DEV-018: grounding filter unit tests.

The 2026-07-03 F1 validation failed because the v1 clinical_slot prompt's
example JSON was echoed verbatim into slot values. These tests pin the
structural defense: fabricated/template values are rejected, patient-quoted
values are grounded, and negative templates require ask evidence.
"""

from __future__ import annotations

from src.grounding import (
    QUESTIONABLE_SLOT_KEYS,
    evaluate_slot_grounding,
    grounded_coverage,
    has_lexical_evidence,
    is_negative_template,
    reply_has_negation,
)

# The actual VP-003 07-03 first utterance (suicidal patient).
_VP003_UTTERANCE = "살고 싶지 않아요. 그냥 사라지고 싶은 생각이 들어요."


class TestFabricatedValuesRejected:
    """v1-prompt example strings must never pass for a suicidal patient."""

    def test_fabricated_psych_history_rejected(self):
        v = evaluate_slot_grounding(
            "past_psychiatric_history", "정신과 진료 경험 없음", [_VP003_UTTERANCE]
        )
        assert v.verdict == "ungrounded"
        assert not v.accepted

    def test_fabricated_medical_history_rejected(self):
        v = evaluate_slot_grounding(
            "medical_history", "진단받은 신체 질환 없음, 복용 약 없음", [_VP003_UTTERANCE]
        )
        assert not v.accepted

    def test_fabricated_substance_use_rejected(self):
        v = evaluate_slot_grounding(
            "substance_use_history", "주 1-2회 맥주 1캔, 수면제 미사용", [_VP003_UTTERANCE]
        )
        assert not v.accepted

    def test_fabricated_family_history_rejected(self):
        v = evaluate_slot_grounding("family_history", "모름", [_VP003_UTTERANCE])
        assert not v.accepted

    def test_fabricated_social_history_rejected(self):
        v = evaluate_slot_grounding(
            "personal_social_history", "어머니와 주 2회 통화", [_VP003_UTTERANCE]
        )
        assert not v.accepted

    def test_mixed_negative_positive_fabrication_rejected(self):
        """Values mixing negation with fabricated substantive claims must not
        slip through the negative-template path even WITH ask evidence."""
        v = evaluate_slot_grounding(
            "substance_use_history",
            "주 1-2회 맥주 1캔, 수면제 미사용",
            ["아니요, 술은 안 마셔요."],
            ["substance_use_history"],
        )
        assert not v.accepted


class TestGroundedValues:
    def test_patient_quoted_chief_complaint_grounded(self):
        v = evaluate_slot_grounding(
            "chief_complaint", "살고 싶지 않음, 사라지고 싶은 생각", [_VP003_UTTERANCE]
        )
        assert v.verdict == "grounded"
        assert v.accepted

    def test_paraphrase_with_shared_tokens_grounded(self):
        v = evaluate_slot_grounding(
            "chief_complaint",
            "잠을 못 자고 불안감이 심함",
            ["요즘 잠을 통 못 자요. 불안해서 계속 뒤척여요."],
        )
        assert v.verdict == "grounded"

    def test_clinical_framing_paraphrase_rejected(self):
        """Extractor framing not present in patient words → rejected (err to reject)."""
        v = evaluate_slot_grounding(
            "history_of_present_illness",
            "현재 극심한 정서적 고통으로 인해 살고 싶지 않은 생각이 듦",
            [_VP003_UTTERANCE],
        )
        assert not v.accepted

    def test_verbatim_quote_grounded(self):
        v = evaluate_slot_grounding(
            "history_of_present_illness",
            "두 달 전부터 새벽 세 시까지 잠이 안 옴",
            ["두 달 전부터요. 요즘은 새벽 세 시까지 잠이 안 와요."],
        )
        assert v.accepted


class TestNegativeTemplates:
    _UTTS = ["요즘 잠이 안 와요.", "아니요, 술은 안 마셔요."]

    def test_negative_with_ask_evidence_accepted(self):
        v = evaluate_slot_grounding(
            "substance_use_history", "음주 안 함", self._UTTS,
            [None, "substance_use_history"],
        )
        assert v.verdict == "negative_grounded"
        assert v.accepted

    def test_negative_without_ask_evidence_rejected(self):
        v = evaluate_slot_grounding(
            "substance_use_history", "음주 안 함", self._UTTS, [None, None]
        )
        assert v.verdict == "ungrounded"

    def test_negative_asked_for_other_slot_rejected(self):
        v = evaluate_slot_grounding(
            "family_history", "가족력 없음", self._UTTS,
            [None, "substance_use_history"],
        )
        assert v.verdict == "ungrounded"

    def test_negative_ask_without_negation_reply_rejected(self):
        v = evaluate_slot_grounding(
            "substance_use_history", "음주 안 함",
            ["요즘 잠이 안 와요.", "네, 매일 마셔요."],
            [None, "substance_use_history"],
        )
        assert v.verdict == "ungrounded"

    def test_asked_slots_as_mapping(self):
        v = evaluate_slot_grounding(
            "substance_use_history", "음주 안 함", self._UTTS,
            {1: "substance_use_history"},
        )
        assert v.verdict == "negative_grounded"


class TestSystemAndRiskSlots:
    def test_system_slots_always_rejected(self):
        for key in ("encounter_metadata", "clinical_assessment", "treatment_plan"):
            v = evaluate_slot_grounding(key, "임의의 값", ["임의의 값"])
            assert v.verdict == "system_slot"
            assert not v.accepted

    def test_risk_assessment_never_accepted_from_extractor(self):
        """Even a 'plausible' risk value quoting patient words is rejected —
        risk_assessment is populated only by the safety probe protocol."""
        v = evaluate_slot_grounding(
            "risk_assessment", "자살/자해 사고 명시적 부인", [_VP003_UTTERANCE]
        )
        assert v.verdict == "ungrounded"
        assert "probe" in v.reason

        v2 = evaluate_slot_grounding(
            "risk_assessment", "살고 싶지 않다고 표현함", [_VP003_UTTERANCE]
        )
        assert not v2.accepted

    def test_mse_without_evidence_rejected(self):
        v = evaluate_slot_grounding(
            "mental_status_exam",
            "말투: 절망적, 감정: 극심한 우울감",
            [_VP003_UTTERANCE],
        )
        assert v.verdict == "ungrounded"


class TestPlaceholderEcho:
    def test_v2_placeholder_echo_rejected(self):
        v = evaluate_slot_grounding(
            "chief_complaint", "<환자가 실제로 말한 주호소 표현 요약>", [_VP003_UTTERANCE]
        )
        assert v.verdict == "ungrounded"
        assert "placeholder" in v.reason

    def test_empty_value_rejected(self):
        v = evaluate_slot_grounding("chief_complaint", "  ", [_VP003_UTTERANCE])
        assert not v.accepted


class TestTextHeuristics:
    def test_reply_negation_positive_cases(self):
        assert reply_has_negation("아니요, 없어요")
        assert reply_has_negation("안 마셔요")
        assert reply_has_negation("잘 모르겠어요")
        assert reply_has_negation("그렇게까지 하지는 않을 거예요")

    def test_reply_negation_negative_cases(self):
        assert not reply_has_negation("네, 맞아요")
        # 불안/안정 must not count as standalone 안-negation
        assert not reply_has_negation("요즘 너무 불안해요")
        assert not reply_has_negation("마음이 안정되었어요")

    def test_is_negative_template(self):
        assert is_negative_template("음주 안 함")
        assert is_negative_template("가족력 없음")
        assert is_negative_template("모름")
        assert not is_negative_template("매일 소주 한 병 마심")
        # mixed positive claims disqualify the negative-template shortcut
        assert not is_negative_template("주 1-2회 맥주 1캔, 수면제 미사용")

    def test_lexical_evidence_empty_utterances(self):
        assert not has_lexical_evidence("아무 값", [])
        assert not has_lexical_evidence("아무 값", [""])


class TestQABypassProbes:
    """Regression tests for the QA bypass probes (ISS-044, ISS-045 + B4 set)."""

    def test_iss044_polarity_inversion_rejected(self):
        """Exact ISS-044 case: value negates what the patient AFFIRMED.
        Shared topic tokens must not ground a polarity-inverted claim."""
        v = evaluate_slot_grounding(
            "past_psychiatric_history",
            "우울증 치료 받은 적 없음, 정신과 이력 부인",
            ["예전에 우울증 치료를 받은 적이 있어요"],
        )
        assert v.verdict == "ungrounded"
        assert not v.accepted

    def test_iss044_negative_template_never_grounds_via_lexical(self):
        """A negative template sharing its topic noun with an affirming
        utterance must not ground lexically — ask-evidence path only."""
        v = evaluate_slot_grounding(
            "family_history", "가족력 없음", ["가족들이랑 잘 지내요"]
        )
        assert v.verdict == "ungrounded"

    def test_iss045_duplicate_token_stuffing_rejected(self):
        """Exact ISS-045 case: repeated topic noun must not inflate matches."""
        v = evaluate_slot_grounding(
            "family_history", "가족 갈등, 가족 문제", ["가족들이랑 잘 지내요"]
        )
        assert v.verdict == "ungrounded"

    def test_single_topic_noun_match_rejected(self):
        v = evaluate_slot_grounding(
            "family_history", "가족력: 어머니 우울증 병력 있음", ["가족들이랑 잘 지내요"]
        )
        assert v.verdict == "ungrounded"

    def test_fabricated_detail_with_verbatim_topic_rejected(self):
        v = evaluate_slot_grounding(
            "substance_use_history", "소주 매일 2병 마심", ["소주는 가끔 한두 잔 마셔요"]
        )
        assert v.verdict == "ungrounded"

    def test_short_two_token_fabrication_rejected(self):
        v = evaluate_slot_grounding(
            "personal_social_history", "직장 스트레스로 퇴사", ["회사 일이 좀 힘들어요"]
        )
        assert v.verdict == "ungrounded"

    def test_cross_slot_ask_evidence_rejected(self):
        """Negative template must not borrow ask evidence of a DIFFERENT slot."""
        v = evaluate_slot_grounding(
            "family_history", "가족력 없음",
            ["요즘 잠을 못 자요", "없어요"],
            [None, "medical_history"],
        )
        assert v.verdict == "ungrounded"

    def test_qa_paraphrase_positive_control(self):
        v = evaluate_slot_grounding(
            "chief_complaint", "잠을 잘 못 자는 게 제일 힘들다",
            ["요즘 잠을 잘 못 자는 게 제일 힘들어요"],
        )
        assert v.verdict == "grounded"

    def test_polarity_consistent_negated_quote_still_grounded(self):
        """Positive control for the ISS-044 fix: a verbatim quote of a
        genuinely NEGATED patient statement must still ground."""
        v = evaluate_slot_grounding(
            "family_history",
            "가족 중에 우울증을 앓은 사람은 없어요",
            ["가족 중에 우울증을 앓은 사람은 없어요. 다들 건강해요."],
        )
        assert v.verdict == "grounded"

    def test_mixed_negated_and_affirmative_quote_still_grounded(self):
        """Positive control: value combining a negated clause and an
        affirmative clause, both actually said (VP-003 chief complaint)."""
        v = evaluate_slot_grounding(
            "chief_complaint", "살고 싶지 않음, 사라지고 싶은 생각", [_VP003_UTTERANCE]
        )
        assert v.verdict == "grounded"


class TestGroundedCoverage:
    def test_empty(self):
        assert grounded_coverage({}) == 0.0

    def test_full(self):
        filled = {k: "v" for k in QUESTIONABLE_SLOT_KEYS}
        assert grounded_coverage(filled) == 1.0

    def test_system_slots_excluded_from_denominator(self):
        filled = {
            "chief_complaint": "v",
            "mental_status_exam": "v",       # not questionable
            "clinical_assessment": "v",      # not questionable
            "treatment_plan": "v",           # not questionable
            "encounter_metadata": "v",       # not questionable
        }
        assert grounded_coverage(filled) == 1 / 8

    def test_denominator_is_eight(self):
        assert len(QUESTIONABLE_SLOT_KEYS) == 8
        assert "risk_assessment" in QUESTIONABLE_SLOT_KEYS
        assert "mental_status_exam" not in QUESTIONABLE_SLOT_KEYS
