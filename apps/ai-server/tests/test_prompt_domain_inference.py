"""domain_inference/v1.system.md — offline prompt-content assertions (F2, C-4).

Same convention as test_prompt_v3.py: placeholder-only examples, output-key
documentation, absolute-rule phrase presence (incl. the risk!=domain rule),
and char/line budget ceilings.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "ai" / "prompts"
DOMAIN_INFERENCE_V1 = (_PROMPTS_DIR / "domain_inference" / "v1.system.md").read_text(
    encoding="utf-8"
)

# DR-001/ISS-027 echo-risk class — no realistic clinical values as "examples".
_KNOWN_BAD_STRINGS = [
    "서울대병원",
    "Escitalopram",
    "F33.1",
    "요즘 죽고 싶다는 생각이",
    "PHQ-9 | 18",
]
_ICD_CODE_PATTERN = re.compile(r"F\d{2}")


class TestNoRealisticExampleValues:
    def test_no_known_bad_strings(self) -> None:
        for bad in _KNOWN_BAD_STRINGS:
            assert bad not in DOMAIN_INFERENCE_V1, f"contains echo-risk string: {bad!r}"

    def test_no_icd_code_pattern(self) -> None:
        assert not _ICD_CODE_PATTERN.search(DOMAIN_INFERENCE_V1)

    def test_examples_are_placeholder_bracketed(self) -> None:
        """Every '<예:' style example must stay inside angle brackets."""
        for m in re.finditer(r"<예[:：][^>]*>", DOMAIN_INFERENCE_V1):
            assert m.group(0).startswith("<") and m.group(0).endswith(">")


class TestOutputSchemaKeysDocumented:
    def test_top_level_keys_present(self) -> None:
        for key in [
            "domain_candidates", "department_candidates", "summary", "additional_questions",
        ]:
            assert key in DOMAIN_INFERENCE_V1, f"missing output key: {key}"

    def test_candidate_keys_present(self) -> None:
        for key in ["domain", "confidence", "evidence", "recommended_surveys"]:
            assert key in DOMAIN_INFERENCE_V1, f"missing domain_candidate key: {key}"

    def test_evidence_keys_present(self) -> None:
        for key in ["source_type", "source_id", "quote"]:
            assert key in DOMAIN_INFERENCE_V1, f"missing evidence key: {key}"

    def test_department_keys_present(self) -> None:
        for key in ["department", "reason", "domain_ref"]:
            assert key in DOMAIN_INFERENCE_V1, f"missing department_candidate key: {key}"

    def test_domain_enum_documented(self) -> None:
        assert (
            "anxiety|depression|alcohol|substance|trauma|sleep|psychosis|other"
            in DOMAIN_INFERENCE_V1
        )


class TestAbsoluteRules:
    def test_no_diagnosis_rule(self) -> None:
        assert "진단하지 않는다" in DOMAIN_INFERENCE_V1

    def test_risk_not_domain_evidence_rule(self) -> None:
        """The load-bearing safety-scope rule (REV-006 issue #3 mitigation,
        DR-005 boundary caveat): risk language must never be used as domain
        confidence evidence — that judgment belongs to the Safety pipeline."""
        assert "위험 표현을 domain confidence의 근거로 사용하지 않는다" in DOMAIN_INFERENCE_V1
        assert "Safety 파이프라인" in DOMAIN_INFERENCE_V1

    def test_no_ungrounded_candidate_rule(self) -> None:
        assert "근거 없는 후보 금지" in DOMAIN_INFERENCE_V1
        assert "evidence를 최소 1개" in DOMAIN_INFERENCE_V1

    def test_cite_only_provided_sources_rule(self) -> None:
        assert "실제로 주어진 자료에서만" in DOMAIN_INFERENCE_V1

    def test_no_extra_fields_rule(self) -> None:
        assert "지정된 필드 외" in DOMAIN_INFERENCE_V1

    def test_at_most_five_absolute_rules(self) -> None:
        """'절대 규칙 (N개' header must not exceed 5."""
        m = re.search(r"절대 규칙 \((\d+)개", DOMAIN_INFERENCE_V1)
        assert m, "absolute-rule count header not found"
        assert int(m.group(1)) <= 5


class TestCandidateAndUncertaintyRules:
    def test_max_three_candidates_rule(self) -> None:
        assert "최대 3개" in DOMAIN_INFERENCE_V1

    def test_ranking_rule(self) -> None:
        assert "confidence 내림차순" in DOMAIN_INFERENCE_V1

    def test_orphan_department_rule(self) -> None:
        assert "고아 참조 금지" in DOMAIN_INFERENCE_V1

    def test_uncertainty_confidence_floor_rule(self) -> None:
        """C-4 spec: evidence==1 or llm_only -> confidence < 0.4 recommended."""
        assert "0.4 미만" in DOMAIN_INFERENCE_V1
        assert "evidence가 1개뿐" in DOMAIN_INFERENCE_V1
        assert "llm_only" in DOMAIN_INFERENCE_V1


class TestBudget:
    def test_char_budget(self) -> None:
        assert len(DOMAIN_INFERENCE_V1) <= 3000, (
            f"measured {len(DOMAIN_INFERENCE_V1)} chars > 3000 ceiling"
        )

    def test_line_budget(self) -> None:
        assert len(DOMAIN_INFERENCE_V1.splitlines()) <= 90, (
            f"measured {len(DOMAIN_INFERENCE_V1.splitlines())} lines > 90 ceiling"
        )
