"""T1-F1-VER-006: Safety keyword recall test.

Tests that the rule-based keyword detector catches all defined crisis phrases.
Target: recall ≥ 95% for high/critical keywords.
This tests the RULE ENGINE ONLY (no LLM call), so it's deterministic.
"""

import pytest

from src.agents.safety_classifier import SafetyClassifierAgent, _RISK_ORDER
from src.schemas.common import RiskLevel


def _risk_ge(a: RiskLevel, b: RiskLevel) -> bool:
    """Compare risk levels by severity (not alphabetical)."""
    return _RISK_ORDER[a] >= _RISK_ORDER[b]


# Instantiate a partial agent just for rule classification
# (no model_router/prompt_loader needed for _rule_classify)
class _RuleOnlyClassifier:
    """Minimal wrapper to test _rule_classify without LLM dependencies."""

    def __init__(self):
        self._agent = SafetyClassifierAgent.__new__(SafetyClassifierAgent)

    def classify(self, text: str) -> tuple[RiskLevel, list[str], list[str]]:
        return self._agent._rule_classify(text)


@pytest.fixture
def classifier():
    return _RuleOnlyClassifier()


# ── CRITICAL keywords → must return critical ─────────────────────────

_CRITICAL_CASES = [
    ("자살하고 싶어요", RiskLevel.critical, "자살"),
    ("죽고 싶어요", RiskLevel.critical, "죽고 싶"),
    ("죽고싶다", RiskLevel.critical, "죽고싶"),
    ("목숨을 끊으려고", RiskLevel.critical, "목숨"),
    ("끝내고 싶어", RiskLevel.critical, "끝내고 싶"),
    ("죽을 거야", RiskLevel.critical, "죽을"),
    ("죽어버리고 싶어", RiskLevel.critical, "죽어버리"),
    ("세상을 떠나고 싶어", RiskLevel.critical, "세상을 떠나"),
    ("유서를 썼어요", RiskLevel.critical, "유서"),
    ("자해를 했어요", RiskLevel.critical, "자해"),
    ("손목을 그었어요", RiskLevel.critical, "손목을 긋"),
    ("칼로 그었어요", RiskLevel.critical, "칼로"),
    ("약을 많이 먹었어요", RiskLevel.critical, "약을 많이 먹"),
    ("약물 과다복용 했어요", RiskLevel.critical, "약물 과다"),
]


class TestCriticalKeywordRecall:
    @pytest.mark.parametrize("text,expected_level,keyword", _CRITICAL_CASES)
    def test_critical_detection(self, classifier, text, expected_level, keyword):
        level, categories, flagged = classifier.classify(text)
        assert level == expected_level, f"'{text}' should be {expected_level}, got {level}"
        assert len(flagged) > 0, f"'{text}' should flag keyword '{keyword}'"


# ── HIGH keywords → must return high ─────────────────────────────────

_HIGH_CASES = [
    ("살고 싶지 않아요", RiskLevel.high, "살고 싶지 않"),
    ("사라지고 싶어요", RiskLevel.high, "사라지고 싶"),
    ("없어지고 싶어요", RiskLevel.high, "없어지고 싶"),
    ("해치고 싶어요", RiskLevel.high, "해치고 싶"),
    ("때리고 싶어요", RiskLevel.high, "때리고 싶"),
    ("죽이고 싶어요", RiskLevel.high, "죽이고 싶"),
]


class TestHighKeywordRecall:
    @pytest.mark.parametrize("text,expected_level,keyword", _HIGH_CASES)
    def test_high_detection(self, classifier, text, expected_level, keyword):
        level, categories, flagged = classifier.classify(text)
        assert _risk_ge(level, expected_level), f"'{text}' should be >= {expected_level}, got {level}"


# ── MEDIUM keywords → must return medium ─────────────────────────────

_MEDIUM_CASES = [
    ("힘들어서 못 살겠어요", RiskLevel.medium, "힘들어서 못 살"),
    ("너무 힘들어요", RiskLevel.medium, "너무 힘들"),
    ("미치겠어요", RiskLevel.medium, "미치겠"),
    ("포기하고 싶어요", RiskLevel.medium, "포기하고 싶"),
    ("희망이 없어요", RiskLevel.medium, "희망이 없"),
    ("의미가 없어요", RiskLevel.medium, "의미가 없"),
]


class TestMediumKeywordRecall:
    @pytest.mark.parametrize("text,expected_level,keyword", _MEDIUM_CASES)
    def test_medium_detection(self, classifier, text, expected_level, keyword):
        level, categories, flagged = classifier.classify(text)
        assert _risk_ge(level, expected_level), f"'{text}' should be >= {expected_level}, got {level}"


# ── SAFE expressions → must return none ──────────────────────────────

_SAFE_CASES = [
    "안녕하세요",
    "요즘 잠을 잘 못 자요",
    "업무 스트레스가 좀 있어요",
    "가슴이 답답할 때가 있어요",
    "그런 생각은 없어요",
    "괜찮아요, 그냥 좀 피곤해요",
    "약을 먹고 있어요",  # medication compliance, NOT overdose (ISS-013)
    "처방받은 약을 복용 중이에요",
]


class TestSafeExpressions:
    @pytest.mark.parametrize("text", _SAFE_CASES)
    def test_no_false_positive(self, classifier, text):
        level, categories, flagged = classifier.classify(text)
        assert level == RiskLevel.none, f"'{text}' should be none, got {level} (false positive)"


# ── Recall statistics ────────────────────────────────────────────────

class TestRecallRate:
    """Aggregate recall test — must be ≥ 95% for high/critical."""

    def test_high_critical_recall(self, classifier):
        all_cases = _CRITICAL_CASES + _HIGH_CASES
        detected = 0
        for text, expected, _ in all_cases:
            level, _, _ = classifier.classify(text)
            if _risk_ge(level, RiskLevel.high):
                detected += 1
        recall = detected / len(all_cases)
        assert recall >= 0.95, f"High/critical recall {recall:.0%} < 95% target ({detected}/{len(all_cases)})"

    def test_overall_recall(self, classifier):
        all_cases = _CRITICAL_CASES + _HIGH_CASES + _MEDIUM_CASES
        detected = 0
        for text, expected, _ in all_cases:
            level, _, _ = classifier.classify(text)
            if _risk_ge(level, RiskLevel.medium):
                detected += 1
        recall = detected / len(all_cases)
        assert recall >= 0.90, f"Overall recall {recall:.0%} < 90% target ({detected}/{len(all_cases)})"
