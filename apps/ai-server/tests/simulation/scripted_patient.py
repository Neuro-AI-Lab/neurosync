"""Scripted patient — deterministic utterance playback for safety-matrix scenarios.

Unlike PatientLLM (persona + LLM), ScriptedPatient plays a fixed list of
utterances in order. Steps can branch on keywords found in the AI's question,
which is needed for probe-branch scenarios (e.g. SM-04a/SM-04b answer the
plan-stage probe question differently).

Resolution order per AI message:
  1. Next script step (string → play as-is; dict → keyword branch).
  2. If the script is exhausted: first matching global responder.
  3. Otherwise: default_utterance.

No LLM, no network — fully deterministic given the same AI messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ScriptStep = str | dict[str, Any]


@dataclass
class ScriptedPatient:
    """Deterministic patient simulator for scenario testing."""

    script: list[ScriptStep] = field(default_factory=list)
    responders: list[dict[str, Any]] = field(default_factory=list)
    default_utterance: str = "네... 그런 것 같아요."
    persona_id: str = "SM-XX"
    name: str = "scripted"

    _cursor: int = field(default=0, init=False)
    _log: list[dict[str, str]] = field(default_factory=list, init=False)

    @classmethod
    def from_scenario(cls, scenario: dict[str, Any]) -> ScriptedPatient:
        """Build a ScriptedPatient from a scenario JSON dict."""
        patient_cfg = scenario.get("patient", {})
        return cls(
            script=list(patient_cfg.get("script", [])),
            responders=list(patient_cfg.get("responders", [])),
            default_utterance=patient_cfg.get("default", "네... 그런 것 같아요."),
            persona_id=scenario.get("id", "SM-XX"),
            name=patient_cfg.get("name", scenario.get("id", "scripted")),
        )

    @staticmethod
    def _match_branch(
        branches: list[dict[str, Any]], counselor_message: str
    ) -> str | None:
        """Return the first branch utterance whose keyword appears in the message."""
        for branch in branches:
            keywords = branch.get("keywords", [])
            if any(kw in counselor_message for kw in keywords):
                say = branch.get("say", "")
                if say:
                    return str(say)
        return None

    def _resolve(self, counselor_message: str) -> str:
        # 1. Ordered script.
        if self._cursor < len(self.script):
            step = self.script[self._cursor]
            self._cursor += 1
            if isinstance(step, str):
                return step
            if isinstance(step, dict):
                matched = self._match_branch(step.get("branches", []), counselor_message)
                if matched is not None:
                    return matched
                default = step.get("default")
                if isinstance(default, str) and default:
                    return default
                # fall through to responders/default when the step matched nothing

        # 2. Global keyword responders (script exhausted or step unresolved).
        matched = self._match_branch(self.responders, counselor_message)
        if matched is not None:
            return matched

        # 3. Last resort.
        return self.default_utterance

    async def respond(self, counselor_message: str) -> str:
        """Return the next scripted patient utterance for the AI message."""
        utterance = self._resolve(counselor_message)
        self._log.append({"ai": counselor_message, "patient": utterance})
        return utterance

    @property
    def turns_played(self) -> int:
        return len(self._log)

    @property
    def conversation_log(self) -> list[dict[str, str]]:
        return list(self._log)
