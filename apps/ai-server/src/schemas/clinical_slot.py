"""Schemas for the Clinical Slot Extraction agent."""

from __future__ import annotations

from typing import Any

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
    dialogue_target_slot: str | None = Field(
        default=None,
        description="BUG-072/073: the slot dialogue steering was ACTUALLY "
        "asking about most recently (`SessionState.dialogue_target_slot`, "
        "single source of truth) — the one ask-evidence hint this route "
        "can construct from its own wire shape. When set, the LAST patient "
        "utterance in `conversation_history` is tagged with it for "
        "`src.grounding.evaluate_slot_grounding`'s ask-evidence-gated "
        "negative-template branch, so a bare denial reply ('없어') to a "
        "directly-asked slot question can ground instead of being dropped "
        "for lack of lexical evidence.",
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
    slot_status: dict[str, str] = Field(
        default_factory=dict,
        description="BUG-072: 3-state grounding verdict ('filled'|'denied') "
        "for keys ACCEPTED this call — see `src.grounding."
        "verdict_to_slot_status`. Keys absent here were either not "
        "proposed by the extractor this call or dropped by the grounding "
        "filter; the caller's own persistent view should treat those as "
        "'missing' unless already known 'denied'/'filled' from a prior "
        "turn (this field is additive per-call, not a full merged view).",
    )
