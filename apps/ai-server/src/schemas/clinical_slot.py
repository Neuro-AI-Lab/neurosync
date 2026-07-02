"""Schemas for the Clinical Slot Extraction agent."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from src.agents.base import AgentInput, AgentOutput


class ClinicalSlotInput(AgentInput):
    """Input to the clinical slot extractor."""

    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Full conversation [{role, content}, ...]",
    )
    current_slots: dict[str, Any] = Field(
        default_factory=dict,
        description="Already-collected slot values",
    )


class ClinicalSlotOutput(AgentOutput):
    """Output from the clinical slot extractor."""

    extracted_slots: dict[str, Any] = Field(
        default_factory=dict,
        description="Full extracted slot data (nested structure)",
    )
    filled_slots: list[str] = Field(
        default_factory=list,
        description="Slot keys that have values",
    )
    missing_slots: list[str] = Field(
        default_factory=list,
        description="Slot keys still missing",
    )
    essential_filled: list[str] = Field(default_factory=list)
    essential_missing: list[str] = Field(default_factory=list)
    slot_coverage: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of all slots filled",
    )
