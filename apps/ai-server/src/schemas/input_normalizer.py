"""Schemas for the InputNormalizer agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.agents.base import AgentInput, AgentOutput


class NormalizationChange(BaseModel):
    """Single change made during text normalization."""

    original: str = Field(..., description="Original text span")
    normalized: str = Field(..., description="Normalized text span")
    type: Literal["stt_error", "colloquial", "dialect", "typo", "spacing"] = Field(
        ..., description="Category of the normalization"
    )
    position: dict[str, int] = Field(
        default_factory=dict, description="Position in original text: {start, end}"
    )


class InputNormalizerInput(AgentInput):
    """Input to the InputNormalizer agent."""

    raw_text: str = Field(..., description="Original text (STT transcript or user input)")
    input_type: Literal["stt_transcript", "user_text", "ocr_document"] = Field(
        default="user_text", description="Input modality"
    )
    dialect_hint: str | None = Field(
        default=None, description="Regional dialect hint, e.g. 경상, 전라, 충청"
    )


class InputNormalizerOutput(AgentOutput):
    """Output from the InputNormalizer agent."""

    normalized_text: str = Field(default="", description="Normalized text")
    original_text: str = Field(default="", description="Original text preserved")
    changes: list[NormalizationChange] = Field(
        default_factory=list, description="All changes made"
    )
    change_count: int = Field(default=0, description="Number of changes applied")
    clinical_content_preserved: bool = Field(
        default=True, description="True if all clinical terms were preserved"
    )
    risk_expressions_preserved: bool = Field(
        default=True, description="True if all safety-critical expressions were preserved"
    )
