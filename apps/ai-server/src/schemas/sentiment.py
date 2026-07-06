"""Schemas for the Sentiment Analyzer agent."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput


class EmotionScore(BaseModel):
    """Single emotion with intensity."""

    label: str = Field(..., description="anxiety|sadness|anger|despair|fear|hope|neutral|relief")
    intensity: float = Field(default=0.0, ge=0.0, le=1.0)


class SentimentUtteranceInput(AgentInput):
    """Input for per-utterance sentiment analysis (Mode A)."""

    utterance: str = Field(..., description="Patient's single utterance")
    turn_index: int = Field(default=0)
    conversation_context: list[dict[str, str]] = Field(default_factory=list)


class SentimentUtteranceOutput(AgentOutput):
    """Output of per-utterance sentiment analysis."""

    turn_index: int = 0
    emotions: list[EmotionScore] = Field(default_factory=list)
    polarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: str = Field(default="medium", description="low|medium|high")
    evidence_phrase: str = Field(default="")
    risk_signal: bool = Field(default=False)


class PolarityPoint(BaseModel):
    turn: int
    polarity: float


class PerUtteranceTag(BaseModel):
    turn: int
    emotions: list[str] = Field(default_factory=list)
    polarity: float = 0.0


class SentimentSessionInput(AgentInput):
    """Input for session-level sentiment report (Mode B)."""

    per_utterance_results: list[SentimentUtteranceOutput] = Field(default_factory=list)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


class SentimentSessionOutput(AgentOutput):
    """Output of session-level sentiment report."""

    dominant_emotions: list[str] = Field(default_factory=list)
    emotion_distribution: dict[str, float] = Field(default_factory=dict)
    polarity_trajectory: list[PolarityPoint] = Field(default_factory=list)
    signal_strength: str = Field(default="none", description="none|mild|moderate|strong")
    emotional_shift_detected: bool = Field(default=False)
    shift_description: str = Field(default="")
    repeated_patterns: list[str] = Field(default_factory=list)
    per_utterance_tags: list[PerUtteranceTag] = Field(default_factory=list)
