"""T1-F1-VER-007/008: SentimentAnalyzer accuracy tests.

VER-007: Per-utterance emotion classification (20 Korean utterances)
VER-008: Session-level report consistency

Tests Mode B (session aggregation) directly — deterministic, no LLM.
Mode A would require LLM calls, tested via simulation instead.
"""

import pytest

from src.agents.sentiment_analyzer import SentimentAnalyzerAgent
from src.schemas.sentiment import (
    EmotionScore,
    SentimentSessionInput,
    SentimentSessionOutput,
    SentimentUtteranceOutput,
)


def _make_utterance_output(
    turn: int, label: str, intensity: float, polarity: float, risk: bool = False
) -> SentimentUtteranceOutput:
    return SentimentUtteranceOutput(
        model_used="test",
        prompt_version="v1",
        latency_ms=0,
        reason_summary="test",
        turn_index=turn,
        emotions=[EmotionScore(label=label, intensity=intensity)],
        polarity=polarity,
        arousal="medium",
        evidence_phrase="test",
        risk_signal=risk,
    )


# ── VER-007: Per-utterance classification via session aggregation ────


class TestPerUtteranceClassification:
    """Verify Mode B correctly aggregates per-utterance results."""

    @pytest.mark.asyncio
    async def test_mild_patient_emotions(self):
        """VP-001-like: anxiety + neutral pattern → mild signal."""
        results = [
            _make_utterance_output(1, "neutral", 0.6, -0.1),
            _make_utterance_output(2, "anxiety", 0.4, -0.3),
            _make_utterance_output(3, "neutral", 0.5, -0.1),
            _make_utterance_output(4, "anxiety", 0.3, -0.2),
            _make_utterance_output(5, "neutral", 0.5, 0.0),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="mild", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        assert out.signal_strength in ("none", "mild")
        assert "neutral" in out.dominant_emotions or "anxiety" in out.dominant_emotions

    @pytest.mark.asyncio
    async def test_severe_patient_emotions(self):
        """VP-003-like: despair + sadness pattern → strong signal."""
        results = [
            _make_utterance_output(1, "sadness", 0.7, -0.6),
            _make_utterance_output(2, "despair", 0.8, -0.8),
            _make_utterance_output(3, "despair", 0.9, -0.9, risk=True),
            _make_utterance_output(4, "sadness", 0.7, -0.7),
            _make_utterance_output(5, "despair", 0.8, -0.8, risk=True),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="severe", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        assert out.signal_strength == "strong"
        assert "despair" in out.dominant_emotions

    @pytest.mark.asyncio
    async def test_improving_patient_emotions(self):
        """VP-002-like: hope + relief pattern → none/mild signal."""
        results = [
            _make_utterance_output(1, "hope", 0.6, 0.3),
            _make_utterance_output(2, "relief", 0.5, 0.4),
            _make_utterance_output(3, "neutral", 0.5, 0.2),
            _make_utterance_output(4, "hope", 0.4, 0.3),
            _make_utterance_output(5, "neutral", 0.5, 0.1),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="improving", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        assert out.signal_strength == "none"  # no negative emotions
        assert "hope" in out.dominant_emotions or "neutral" in out.dominant_emotions


# ── VER-008: Session-level report consistency ────────────────────────


class TestSessionReportConsistency:
    """Verify session report fields are internally consistent."""

    @pytest.mark.asyncio
    async def test_empty_session(self):
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="empty", per_utterance_results=[])
        out = await agent._analyze_session(inp)

        assert out.signal_strength == "none"
        assert out.dominant_emotions == []
        assert out.polarity_trajectory == []
        assert out.per_utterance_tags == []

    @pytest.mark.asyncio
    async def test_polarity_trajectory_matches_turns(self):
        results = [
            _make_utterance_output(1, "anxiety", 0.5, -0.3),
            _make_utterance_output(2, "sadness", 0.6, -0.5),
            _make_utterance_output(3, "anxiety", 0.7, -0.7),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="traj", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        assert len(out.polarity_trajectory) == 3
        assert out.polarity_trajectory[0].turn == 1
        assert out.polarity_trajectory[2].turn == 3
        assert out.polarity_trajectory[0].polarity == -0.3
        assert out.polarity_trajectory[2].polarity == -0.7

    @pytest.mark.asyncio
    async def test_per_utterance_tags_match_input(self):
        results = [
            _make_utterance_output(1, "anxiety", 0.5, -0.3),
            _make_utterance_output(2, "hope", 0.4, 0.2),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="tags", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        assert len(out.per_utterance_tags) == 2
        assert out.per_utterance_tags[0].emotions == ["anxiety"]
        assert out.per_utterance_tags[1].emotions == ["hope"]

    @pytest.mark.asyncio
    async def test_emotional_shift_detection(self):
        """Shift > 0.3 polarity between halves → shift detected."""
        results = [
            _make_utterance_output(1, "sadness", 0.7, -0.7),
            _make_utterance_output(2, "despair", 0.8, -0.8),
            _make_utterance_output(3, "neutral", 0.5, -0.1),
            _make_utterance_output(4, "hope", 0.5, 0.2),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="shift", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        assert out.emotional_shift_detected is True
        assert "호전" in out.shift_description  # second half more positive

    @pytest.mark.asyncio
    async def test_repeated_patterns(self):
        """Same emotion 3+ times → repeated pattern flagged."""
        results = [
            _make_utterance_output(1, "anxiety", 0.5, -0.3),
            _make_utterance_output(2, "anxiety", 0.6, -0.4),
            _make_utterance_output(3, "anxiety", 0.7, -0.5),
            _make_utterance_output(4, "sadness", 0.4, -0.3),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="repeat", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        assert len(out.repeated_patterns) >= 1
        assert any("anxiety" in p for p in out.repeated_patterns)

    @pytest.mark.asyncio
    async def test_emotion_distribution_sums_to_one(self):
        results = [
            _make_utterance_output(1, "anxiety", 0.5, -0.3),
            _make_utterance_output(2, "sadness", 0.6, -0.5),
            _make_utterance_output(3, "neutral", 0.5, 0.0),
        ]
        agent = SentimentAnalyzerAgent.__new__(SentimentAnalyzerAgent)
        inp = SentimentSessionInput(session_id="dist", per_utterance_results=results)
        out = await agent._analyze_session(inp)

        total = sum(out.emotion_distribution.values())
        assert abs(total - 1.0) < 0.05  # allow rounding error
