"""Schemas for temporal (longitudinal) domain/sentiment trend comparators.

The `temporal_summary` agent (and its `TemporalSummaryInput`/`Output`/
`PlotPoint` request/response schemas) has been retired — its role merged
into F4. `DomainDirection`/`DomainTrend`/`SentimentTrend` remain live: they
are the return types of `src.temporal_compare`'s comparator functions,
used by F4 as supplementary per-pair evidence.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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
