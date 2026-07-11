"""`src.avc12_instrumentation` — AVC-12 activation-rate counters.

PLAN-2026-W28-Q W3 (`docs/ai/validation_plan_f1f2_continuous.md` §6
AVC-12). Deterministic, artifact/log-fixture-based coverage only — every
counter reads an already-existing artifact field or log message, never a
new production emission point.
"""

from __future__ import annotations

import logging

import pytest

from src.avc12_instrumentation import (
    ActivationStats,
    DialogueRetryHintCapture,
    build_avc12_report,
    dialogue_retry_hint_activation_from_messages,
    greeting_generation_activation,
    input_normalizer_activation,
    input_normalizer_activation_pooled,
    policy_b_judge_activation,
)


class TestActivationStats:
    def test_rate_is_none_when_no_attempts(self) -> None:
        stats = ActivationStats(component="x", attempts=0, activations=0)
        assert stats.rate is None

    def test_rate_computed_normally(self) -> None:
        stats = ActivationStats(component="x", attempts=4, activations=1)
        assert stats.rate == 0.25

    def test_rejects_activations_exceeding_attempts(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            ActivationStats(component="x", attempts=1, activations=2)

    def test_rejects_negative_counts(self) -> None:
        with pytest.raises(ValueError):
            ActivationStats(component="x", attempts=-1, activations=0)

    def test_as_dict_shape(self) -> None:
        stats = ActivationStats(component="x", attempts=2, activations=1, notes="n")
        assert stats.as_dict() == {
            "component": "x", "attempts": 2, "activations": 1, "rate": 0.5, "notes": "n",
        }


class TestInputNormalizerActivation:
    def test_counts_turns_with_change_count_positive(self) -> None:
        conversation_json = {
            "turns": [
                {"normalizer_meta": {"change_count": 1}},
                {"normalizer_meta": {"change_count": 0}},
                {"normalizer_meta": {"change_count": 3}},
            ]
        }
        stats = input_normalizer_activation(conversation_json)
        assert stats.attempts == 3
        assert stats.activations == 2
        assert stats.rate == pytest.approx(2 / 3)

    def test_skipped_empty_input_turns_excluded_from_attempts(self) -> None:
        conversation_json = {
            "turns": [
                {"normalizer_meta": {"skipped": "empty_input"}},
                {"normalizer_meta": {"change_count": 1}},
            ]
        }
        stats = input_normalizer_activation(conversation_json)
        assert stats.attempts == 1
        assert stats.activations == 1

    def test_no_turns_yields_zero_attempts_not_error(self) -> None:
        stats = input_normalizer_activation({"turns": []})
        assert stats.attempts == 0
        assert stats.rate is None

    def test_reproduces_bug_020_zero_activation_case(self) -> None:
        """If BUG-020's suspected no-op is real, change_count stays 0 across
        every turn even though the normalizer ran — this must surface as a
        measured 0.0 rate (not None, since attempts > 0)."""
        conversation_json = {
            "turns": [
                {"normalizer_meta": {"change_count": 0}},
                {"normalizer_meta": {"change_count": 0}},
            ]
        }
        stats = input_normalizer_activation(conversation_json)
        assert stats.attempts == 2
        assert stats.activations == 0
        assert stats.rate == 0.0

    def test_pooled_across_multiple_sessions(self) -> None:
        c1 = {"turns": [{"normalizer_meta": {"change_count": 1}}]}
        c2 = {"turns": [{"normalizer_meta": {"change_count": 0}},
                         {"normalizer_meta": {"change_count": 0}}]}
        stats = input_normalizer_activation_pooled([c1, c2])
        assert stats.attempts == 3
        assert stats.activations == 1


class TestDialogueRetryHintCapture:
    def test_captures_matching_warning_only(self) -> None:
        logger = logging.getLogger("src.agents.dialogue")
        with DialogueRetryHintCapture() as capture:
            logger.warning("DialogueAgent repeated — retrying with stronger hint")
            logger.warning("some unrelated warning")
            logger.info("DialogueAgent repeated — retrying with stronger hint")  # below level
        stats = capture.activation_stats(total_turns=5)
        assert stats.attempts == 5
        assert stats.activations == 1

    def test_detaches_after_context_exit(self) -> None:
        logger = logging.getLogger("src.agents.dialogue")
        with DialogueRetryHintCapture() as capture:
            pass
        assert capture not in logger.handlers

    def test_multiple_firings_counted(self) -> None:
        logger = logging.getLogger("src.agents.dialogue")
        with DialogueRetryHintCapture() as capture:
            for _ in range(3):
                logger.warning("DialogueAgent repeated — retrying with stronger hint")
        stats = capture.activation_stats(total_turns=12)
        assert stats.activations == 3
        assert stats.rate == pytest.approx(3 / 12)


class TestDialogueRetryHintFromMessages:
    def test_counts_matching_messages(self) -> None:
        messages = [
            "DialogueAgent repeated — retrying with stronger hint",
            "unrelated",
            "DialogueAgent repeated — retrying with stronger hint",
        ]
        stats = dialogue_retry_hint_activation_from_messages(messages, total_turns=10)
        assert stats.attempts == 10
        assert stats.activations == 2


class TestGreetingGenerationActivation:
    def test_fallback_marker_not_counted_as_activation(self) -> None:
        sessions = [
            {"prompt_version": "v3"},
            {"prompt_version": "fallback_static"},
            {"prompt_version": "v3"},
        ]
        stats = greeting_generation_activation(sessions)
        assert stats.attempts == 3
        assert stats.activations == 2

    def test_empty_prompt_version_not_counted(self) -> None:
        sessions = [{"prompt_version": ""}]
        stats = greeting_generation_activation(sessions)
        assert stats.attempts == 1
        assert stats.activations == 0

    def test_no_sessions_yields_none_rate(self) -> None:
        stats = greeting_generation_activation([])
        assert stats.attempts == 0
        assert stats.rate is None


class TestPolicyBJudgeActivation:
    """PLAN-2026-W28-Q W4 — replaces the pre-W4 placeholder with the real
    counter, reading the `rag_trigger` field `f2.py`'s `_run()` now
    persists on every `domain_inference.json` artifact."""

    def test_no_runs_yields_zero_attempts_and_none_rate(self) -> None:
        stats = policy_b_judge_activation([])
        assert stats.component == "policy_b_judge"
        assert stats.attempts == 0
        assert stats.rate is None

    def test_policy_a_runs_excluded_from_attempts(self) -> None:
        """A run where Policy A was active must not count toward Policy B's
        own activation rate — the two arms measure different things."""
        runs = [{"rag_trigger": {"policy": "A", "retrieve": True}}]
        stats = policy_b_judge_activation(runs)
        assert stats.attempts == 0
        assert stats.rate is None

    def test_pre_w4_artifact_without_rag_trigger_field_excluded(self) -> None:
        stats = policy_b_judge_activation([{"repro": {"mode": "rag"}}])
        assert stats.attempts == 0

    def test_counts_policy_b_retrieve_true_as_activation(self) -> None:
        runs = [
            {"rag_trigger": {"policy": "B", "retrieve": True}},
            {"rag_trigger": {"policy": "B", "retrieve": False}},
            {"rag_trigger": {"policy": "A", "retrieve": True}},  # excluded
        ]
        stats = policy_b_judge_activation(runs)
        assert stats.attempts == 2
        assert stats.activations == 1
        assert stats.rate == pytest.approx(0.5)


class TestBuildAvc12Report:
    def test_report_lists_all_components(self) -> None:
        report = build_avc12_report(
            input_normalizer_activation({"turns": []}),
            greeting_generation_activation([]),
            policy_b_judge_activation([]),
        )
        components = [s["component"] for s in report["avc12_activation_rates"]]
        assert components == [
            "input_normalizer_correction",
            "greeting_v3_autonomous_generation",
            "policy_b_judge",
        ]
