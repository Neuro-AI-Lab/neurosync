"""Shared test helpers for F1 pipeline tests — no LLM, fully deterministic.

Builds an F1Pipeline whose three agents are message-driven stubs:
  - safety: patient message → (CTRS, categories)
  - dialogue: unique response per call; records DialogueInput for assertions
  - clinical_slot: callable(input, call_index) → extracted slots dict
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.f1 import F1Pipeline
from src.schemas.clinical_slot import ClinicalSlotOutput
from src.schemas.common import CTRS_TO_RISK, CTRSLevel
from src.schemas.dialogue import DialogueOutput
from src.schemas.safety import SafetyOutput


def make_safety_output(ctrs: int, categories: list[str] | None = None) -> SafetyOutput:
    """Build a realistic SafetyOutput for a given CTRS level."""
    level = CTRSLevel(ctrs)
    return SafetyOutput(
        model_used="stub",
        prompt_version="v1",
        latency_ms=0.0,
        reason_summary="stub",
        risk_level=CTRS_TO_RISK[level],
        categories=categories or [],
        flagged_phrases=[],
        confidence=1.0,
        ctrs_level=ctrs,
        requires_human_review=ctrs <= 3,
        crisis_protocol_activated=ctrs <= 2,
    )


class StubSafetyAgent:
    """Maps patient message → (ctrs, categories); default = (5, [])."""

    def __init__(self, mapping: dict[str, tuple[int, list[str]]] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[Any] = []

    async def run(self, inp: Any, **kwargs: Any) -> SafetyOutput:
        self.calls.append(inp)
        ctrs, cats = self.mapping.get(inp.user_message, (5, []))
        return make_safety_output(ctrs, cats)


class StubDialogueAgent:
    """Returns a unique response per call; records inputs for assertions."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def run(self, inp: Any, **kwargs: Any) -> DialogueOutput:
        self.calls.append(inp)
        n = len(self.calls)
        probe = ""
        if inp.session_state and inp.session_state.get("probe_instruction"):
            probe = " [probe]"
        return DialogueOutput(
            model_used="stub",
            prompt_version="v1",
            latency_ms=0.0,
            reason_summary="stub",
            assistant_response=f"응답 {n}{probe}: 조금 더 이야기해 주시겠어요?",
        )

    @property
    def probe_instructions(self) -> list[str | None]:
        """probe_instruction (or None) per dialogue call, in order.

        Dialogue v3 (PLAN-2026-W28-Q W2): DialogueAgent is now also called
        at turn 0 (the autonomous opening greeting, session_state
        `opening_turn=True`). That call is filtered out here so this
        property's index contract stays "one entry per round-robin/probe
        turn call" — unchanged for every pre-v3 caller of this test helper.
        """
        out: list[str | None] = []
        for c in self.calls:
            state = c.session_state or {}
            if state.get("opening_turn"):
                continue
            out.append(state.get("probe_instruction"))
        return out


class StubSlotAgent:
    """clinical_slot stub — slots_fn(inp, call_index) → extracted slots dict."""

    def __init__(
        self,
        slots_fn: Callable[[Any, int], dict[str, Any]] | None = None,
    ) -> None:
        self.slots_fn = slots_fn or (lambda inp, n: {})
        self.calls: list[Any] = []

    async def run(self, inp: Any, **kwargs: Any) -> ClinicalSlotOutput:
        self.calls.append(inp)
        extracted = self.slots_fn(inp, len(self.calls))
        return ClinicalSlotOutput(
            model_used="stub",
            prompt_version="v2",
            latency_ms=0.0,
            reason_summary="stub",
            extracted_slots=extracted,
        )


def make_pipeline(
    safety: StubSafetyAgent | None = None,
    dialogue: StubDialogueAgent | None = None,
    slots: StubSlotAgent | None = None,
) -> F1Pipeline:
    """F1Pipeline with stub agents (bypasses model router / prompt loader)."""
    pipeline = F1Pipeline.__new__(F1Pipeline)
    pipeline.safety = safety or StubSafetyAgent()
    pipeline.dialogue = dialogue or StubDialogueAgent()
    pipeline.clinical_slot = slots or StubSlotAgent()
    return pipeline


def make_patient_fn(utterances: list[str], filler: str = "음... 잘 모르겠어요."):
    """Async patient stub: plays utterances in order, then repeats filler."""
    state = {"i": 0}

    async def patient_fn(agent_message: str) -> str:
        i = state["i"]
        state["i"] += 1
        if i < len(utterances):
            return utterances[i]
        return filler

    return patient_fn
