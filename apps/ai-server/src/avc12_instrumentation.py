"""avc12_instrumentation.py — AVC-12 activation-rate instrumentation.

PLAN-2026-W28-Q W3 (`docs/ai/validation_plan_f1f2_continuous.md` §6 AVC-12,
§3 "STT/OCR arbitrary-turn injection" plan row: "AVC-12 instrumentation is
installed in W3 and checked in W8"). AVC-12 targets a specific failure
mode: a corrective/generative code path that is verified to exist and pass
its own unit tests, yet activates 0% of the time in real runs — "no
regressions" reported honestly, but only because the path never fired (the
`BUG-020` pattern: InputNormalizer's STT-correction path is suspected to be
a silent no-op even though nothing crashes).

This module is READ-ONLY instrumentation over EXISTING artifact/log
surfaces — per the brief's constraint, no new production-code emission
point is added for any of the four named components. Every counter here
reads a field or log message the production code ALREADY emits:

  - InputNormalizer (BUG-020 target): `F1TurnLog.normalizer_meta
    ["change_count"]` — already persisted per turn in `conversation.json`
    by `f1.py`'s existing `_normalize_patient_message()`.
  - Dialogue-v3 retry-hint: the existing WARNING log line
    `"DialogueAgent repeated — retrying with stronger hint"` already
    emitted by `src.agents.dialogue.DialogueAgent.run()` (unmodified this
    wave — see `tests/repro/test_bug_025.py`) — captured via a
    `logging.Handler` attached externally by the harness, never a new
    field.
  - Greeting-generation (v3 autonomous) path: `F1Result.prompt_version` —
    already set to the literal `"fallback_static"` by `f1.py`'s own
    turn-0 exception handler when the autonomous `DialogueAgent` greeting
    call fails; any other value means v3 generation actually fired.
  - Policy-B judge (PLAN-2026-W28-Q W4, landed): the `domain_inference.json`
    artifact's `rag_trigger` field (`src.rag_trigger.TriggerDecision.
    as_dict()`, written by `f2.py`'s `_run()`) — already-persisted per-run
    audit surface, read here exactly like every other counter in this
    module, no new emission point added.

No production module is imported-from/branched-for/parameterized-by this
module (AVC-03): this file only reads artifact dicts already written to
disk and attaches to Python's own public `logging` API. `src/f1.py` and
`src/agents/dialogue.py` are untouched.

This module ships the counters; it does not itself run a validation
battery (W7) or render a W8 verdict — `build_avc12_report()` produces the
raw per-run numbers experiment-tracker/critic consume at W8.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_DIALOGUE_RETRY_LOG_SUBSTRING = "retrying with stronger hint"
_GREETING_FALLBACK_PROMPT_VERSION = "fallback_static"
_DIALOGUE_LOGGER_NAME = "src.agents.dialogue"


@dataclass(frozen=True)
class ActivationStats:
    """One component's activation-rate record for a single instrumented run
    (or a pooled set of runs, at the caller's discretion — this dataclass
    does not distinguish; callers label pooling scope via `notes`)."""

    component: str
    attempts: int
    activations: int
    notes: str = ""

    def __post_init__(self) -> None:
        if self.attempts < 0 or self.activations < 0:
            raise ValueError("attempts/activations must be >= 0")
        if self.activations > self.attempts:
            raise ValueError(
                f"{self.component}: activations ({self.activations}) cannot exceed "
                f"attempts ({self.attempts})"
            )

    @property
    def rate(self) -> float | None:
        """None (not 0.0) when `attempts == 0` — an untested component must
        never silently read as "0% activation", which is itself the exact
        AVC-12 failure pattern this module exists to catch."""
        if self.attempts == 0:
            return None
        return self.activations / self.attempts

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "attempts": self.attempts,
            "activations": self.activations,
            "rate": self.rate,
            "notes": self.notes,
        }


def input_normalizer_activation(conversation_json: Mapping[str, Any]) -> ActivationStats:
    """AVC-12 for InputNormalizer (`BUG-020`): activation = a turn's
    `normalizer_meta.change_count` > 0 (the corrective path actually
    changed something), out of every turn that had non-empty input routed
    through the normalizer (`normalizer_meta` present and not an
    empty-input/error `skipped` marker).
    """
    turns = conversation_json.get("turns") or []
    attempts = 0
    activations = 0
    for t in turns:
        meta = (t or {}).get("normalizer_meta") or {}
        if not meta or "skipped" in meta:
            continue
        attempts += 1
        if int(meta.get("change_count") or 0) > 0:
            activations += 1
    return ActivationStats(
        component="input_normalizer_correction",
        attempts=attempts,
        activations=activations,
        notes=(
            "BUG-020 deferred-verification target — persistent 0% activation across a "
            "real battery reproduces the suspected STT-correction no-op."
        ),
    )


def input_normalizer_activation_pooled(
    conversation_jsons: Iterable[Mapping[str, Any]],
) -> ActivationStats:
    """Same as `input_normalizer_activation`, pooled across multiple session
    artifacts (e.g. a full validation battery) into one rate."""
    attempts = 0
    activations = 0
    for c in conversation_jsons:
        stat = input_normalizer_activation(c)
        attempts += stat.attempts
        activations += stat.activations
    return ActivationStats(
        component="input_normalizer_correction",
        attempts=attempts,
        activations=activations,
        notes="Pooled across the supplied session artifacts (BUG-020 target).",
    )


class DialogueRetryHintCapture(logging.Handler):
    """Attach to `logging.getLogger("src.agents.dialogue")` for the
    duration of one harness-driven session run to count retry-hint
    firings. This is the HARNESS's own `logging.Handler` — it does not
    change `dialogue.py`'s existing `logger.warning(...)` call in any way,
    it only listens.

    Usage::

        with DialogueRetryHintCapture() as capture:
            result = await pipeline.run_session(...)
        stats = capture.activation_stats(total_turns=len(result.turns))
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - trivial
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — a logging handler must never itself crash a run
            return
        if _DIALOGUE_RETRY_LOG_SUBSTRING in msg:
            self.messages.append(msg)

    def activation_stats(self, total_turns: int) -> ActivationStats:
        return ActivationStats(
            component="dialogue_v3_retry_hint",
            attempts=total_turns,
            activations=len(self.messages),
            notes=(
                "Repetition-guard self-correction (BUG-025 lineage, tests/repro/"
                "test_bug_025.py) — counts WARNING log firings of the existing "
                "dialogue.py retry path, harness-captured via logging.Handler, not a "
                "new production field."
            ),
        )

    def attach(self) -> None:
        logging.getLogger(_DIALOGUE_LOGGER_NAME).addHandler(self)

    def detach(self) -> None:
        logging.getLogger(_DIALOGUE_LOGGER_NAME).removeHandler(self)

    def __enter__(self) -> DialogueRetryHintCapture:
        self.attach()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.detach()


def dialogue_retry_hint_activation_from_messages(
    messages: Sequence[str], *, total_turns: int
) -> ActivationStats:
    """Pure-function variant of `DialogueRetryHintCapture.activation_stats`
    for callers that already have captured log message strings (e.g. from
    a saved run log file rather than a live `logging.Handler`)."""
    activations = sum(1 for m in messages if _DIALOGUE_RETRY_LOG_SUBSTRING in m)
    return ActivationStats(
        component="dialogue_v3_retry_hint",
        attempts=total_turns,
        activations=activations,
        notes="Computed from a pre-captured message sequence (e.g. a saved run log).",
    )


def greeting_generation_activation(
    conversation_jsons: Iterable[Mapping[str, Any]],
) -> ActivationStats:
    """AVC-12 for the v3 autonomous greeting: activation = a session's
    turn-0 `DialogueAgent` call succeeded (`prompt_version` is set and is
    NOT the literal `"fallback_static"` marker `f1.py`'s own turn-0
    exception handler writes on failure). The AVC-12 concern here is the
    static fallback silently masking a broken v3 greeting mechanism behind
    "a greeting still showed up, so nothing looks wrong."
    """
    sessions = list(conversation_jsons)
    attempts = len(sessions)
    activations = 0
    for c in sessions:
        pv = c.get("prompt_version")
        if pv and pv != _GREETING_FALLBACK_PROMPT_VERSION:
            activations += 1
    return ActivationStats(
        component="greeting_v3_autonomous_generation",
        attempts=attempts,
        activations=activations,
        notes=(
            "activation = turn-0 DialogueAgent call succeeded (prompt_version != "
            "'fallback_static'); a low rate here means the static fallback is "
            "silently carrying sessions that should be exercising v3 generation."
        ),
    )


def policy_b_judge_activation(
    domain_inference_jsons: Iterable[Mapping[str, Any]],
) -> ActivationStats:
    """AVC-12 for the Policy-B judge (PLAN-2026-W28-Q W4, plan §3 RAG
    trigger policy B row, landed): activation = a Policy-B-arm run whose
    judge decided ``retrieve=True``, out of every run where Policy B was
    the CONFIGURED/active arm this run (``rag_trigger.policy == "B"``
    present, regardless of that run's own retrieve/no-retrieve outcome).

    A run where Policy A was active (``rag_trigger.policy == "A"``, the
    default) or where ``rag_trigger`` is absent (a pre-W4 artifact) is
    excluded from ``attempts`` entirely — this counter measures the
    judge's own activation rate WITHIN its own arm, not "how often does
    RAG fire across the whole battery" (that is MET-8/the incidence
    measurement, a different question).
    """
    attempts = 0
    activations = 0
    for d in domain_inference_jsons:
        trigger = (d or {}).get("rag_trigger") or {}
        if trigger.get("policy") != "B":
            continue
        attempts += 1
        if trigger.get("retrieve"):
            activations += 1
    return ActivationStats(
        component="policy_b_judge",
        attempts=attempts,
        activations=activations,
        notes=(
            "activation = a Policy-B-arm run whose judge decided retrieve=True, out of "
            "every run where rag_trigger.policy == 'B' (regardless of that run's own "
            "retrieve/no-retrieve outcome). Reads the domain_inference.json artifact's "
            "rag_trigger field (PLAN-2026-W28-Q W4, src.rag_trigger.TriggerDecision) — "
            "same read-only-over-existing-surfaces discipline as this module's other "
            "counters. attempts=0 (rate=None) whenever no run this battery used Policy B "
            "at all — never misread as '0% activation'."
        ),
    )


def build_avc12_report(*stats: ActivationStats) -> dict[str, Any]:
    """Combine per-component `ActivationStats` into one run-artifact-shaped
    dict — `{"avc12_activation_rates": [...]}`, suitable to persist
    alongside a run's other harness artifacts (e.g. as a sidecar file, same
    pattern as `injection_protocol.write_provenance_sidecar`)."""
    return {"avc12_activation_rates": [s.as_dict() for s in stats]}
