"""Schemas for the Temporal Summary agent."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput


class DomainDirection(StrEnum):
    improved = "improved"
    worsened = "worsened"
    unchanged = "unchanged"
    unknown = "unknown"

class DomainTrend(BaseModel):
    domain: str
    direction: DomainDirection = DomainDirection.unknown
    previous_value: Any = None
    current_value: Any = None
    delta: float | None = None
    confidence: float | None = None
    evidence: list[str] = Field(default_factory=list)

class SentimentTrend(BaseModel):
    current_polarity: float | None = None
    previous_polarity: float | None = None
    direction: DomainDirection = DomainDirection.unknown
    note: str = ""

class PlotPoint(BaseModel):
    date: str
    phq9: int | None = Field(default=None)
    gad7: int | None = Field(default=None)
    ctrs_level: int | None = None
    sentiment_polarity: float | None = None
    events: list[str] = Field(default_factory=list)

class TemporalSummaryInput(AgentInput):
    patient_id: str = ""
    is_first_visit: bool = True
    current_scales: dict[str, Any] = Field(default_factory=dict)  # {"PHQ-9": 15, "GAD-7": 10}
    prior_scales: dict[str, Any] = Field(default_factory=dict)    # {"PHQ-9": 8, "GAD-7": 6}
    current_ctrs: int | None = None
    prior_ctrs: int | None = None
    current_sentiment_polarity: float | None = None
    prior_sentiment_polarity: float | None = None
    current_date: str = ""
    prior_date: str = ""

class TemporalSummaryOutput(AgentOutput):
    overall_direction: DomainDirection = DomainDirection.unknown
    domain_trends: list[DomainTrend] = Field(default_factory=list)
    new_symptoms: list[str] = Field(default_factory=list)
    relapse_signals: list[str] = Field(default_factory=list)
    sentiment_trend: SentimentTrend = Field(default_factory=SentimentTrend)
    plot_data: list[PlotPoint] = Field(default_factory=list)
    is_first_visit: bool = True
