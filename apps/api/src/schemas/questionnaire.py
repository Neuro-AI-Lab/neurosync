"""Questionnaire (PHQ-9 / GAD-7) request & response shapes — PRD §5.1."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QuestionnaireSubmit(BaseModel):
    type: Literal["PHQ9", "GAD7"]
    # Range/length is re-validated in the scoring service so the error envelope
    # is consistent with other domain errors; keep a loose guard here too.
    answers: list[int] = Field(min_length=1, max_length=9)
    completed_at: datetime | None = Field(default=None, alias="completedAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class QuestionnaireResultOut(BaseModel):
    id: UUID
    type: str
    total_score: int = Field(alias="totalScore")
    severity: str
    completed_at: datetime = Field(alias="completedAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
