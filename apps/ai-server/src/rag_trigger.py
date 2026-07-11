"""RAG trigger policy A/B — PLAN-2026-W28-Q W4.

Decides WHEN F2's Stage-1 retrieval fires and WHICH query text reaches it,
config-switchable between two arms (``f2.py --rag-trigger-policy {A,B}``,
default A):

  - **Policy A** (code-side, no new LLM surface): trigger the whole-
    conversation fallback when ``chief_complaint``+``history_of_present_
    illness`` (``STAGE1_QUERY_SLOTS`` — the SAME two slots ``f2.py``'s
    pre-existing default query composition already used) are insufficient
    — combined ``len()`` < ``SLOT_INSUFFICIENCY_THRESHOLD_N`` chars, or both
    falsy (``docs/ai/validation_plan_f1f2_continuous.md`` §3 Policy-A row,
    Appendix A). Fallback queries are drawn from conversation turns
    EXCLUDING Safety-Probe/SI-screen-adjacent turns (``probe_events``-tagged
    turns).
  - **Policy B** (LLM-judged, new agent ``src.agents.rag_trigger_judge``):
    sees the session transcript + slot state (NOT persona paths, NOT
    ``retrieve_grounding()``, NOT ``risk_assessment`` — plan §6 allowlist
    row) and outputs ``{retrieve: bool, query: str|None}``.

Binding design requirement (``discussion.md`` REV-022 Issues 9/10, blocking-
scoped on this W4 wave): REV-011 §2's own project-proven finding is that the
open VAL-010 residual channel is ORDINARY ``chief_complaint``/HPI content,
not probe turns and not ``risk_assessment`` alone. Excluding probe turns
(Policy A) or hard-excluding only ``risk_assessment`` (Policy B) does not,
by itself, address that channel — both mitigations, as REV-022 found them
originally specified, targeted a channel this project already proved is
NOT the open one. This module's fix is architectural, not lexical:
``apply_risk_lexicon_filter`` is the SINGLE CHOKE POINT every composed
query — from EVERY source (primary slot text, whole-conversation fallback
turns, judge-composed text) and BOTH arms — passes through immediately
before Stage 1 ever sees it, so cc/HPI-content exposure (the actually-open
channel) is mitigated at the same place for both arms, not scattered
per-source. ``decide_policy_a``/``decide_policy_b`` below both call it as
their LAST step, unconditionally — including on the "sufficient/no-
fallback" path, which is itself a fix: ``f2.py``'s pre-existing default
cc/HPI query composition was NEVER filtered before this change (REV-022
finding 3d).

Residual exposure, disclosed (not closed by this module — critic
adjudicates redesign-vs-disclosure at the W4 gate, per this dispatch's
brief): the risk lexicon (``src.eval.f2_grounding._RISK_PHRASES``) is a
20-stem-family taxonomy (37 literal entries; REV-024 corrected the earlier
"15-stem" undercount — ``tests/test_f2_grounding.py::
test_risk_lexicon_stem_family_count_is_20_not_15`` pins the mechanical
count) with this project's own documented paraphrase-coverage-gap history
(BUG-014/VAL-009) — a query whose risk content is worded outside every
stem's paraphrase family is not caught by this filter. This module
closes the "which channel is filtered" gap REV-022 found (cc/HPI content
now IS filtered, for both arms, at one place); it does not, and cannot by
construction, close the separate "is the lexicon's coverage complete"
question — that is the same standing limitation ``_RISK_PHRASES`` already
carries everywhere else it is used in this codebase.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from src.eval.f2_grounding import _RISK_PHRASES, _contains_any
from src.grounding import RISK_SLOT_KEY
from src.schemas.domain_inference import UtteranceTurn

# Appendix A (docs/ai/validation_plan_f1f2_continuous.md), data's W1 finding
# (discussion.md PLAN-2026-W28-Q status append "threshold N, COMPLETE"),
# orchestrator-adopted: N=75 chars, distinct-12 p10, Python len() semantics
# (REV-022 §2's own fallback method — no genuinely insufficient historical
# exemplar existed until SC-3 runs). Policy-A-TRIGGER-ONLY — never ground
# truth for scoring Policy B (orchestrator adoption item 2, same status
# entry): an empirical percentile is not a clinician-validated label.
SLOT_INSUFFICIENCY_THRESHOLD_N: int = 75

# SAME two slots f2.py's pre-existing default Stage-1 query composition
# used. Single source of truth now — f2.py imports this under its
# historical name (`f2._STAGE1_QUERY_SLOTS`) so the two can never silently
# drift apart. `risk_assessment` intentionally excluded (VAL-010, REV-007
# finding #3 / REV-010's two named options): composed from the Safety
# Probe/SI-screen exchange, genuinely risk-worded by construction, and
# embedding it verbatim as a retrieval query systematically biased Stage 1
# toward risk/crisis-topic chunks for higher-risk personas (EXP-005).
STAGE1_QUERY_SLOTS: tuple[str, str] = ("chief_complaint", "history_of_present_illness")

# Policy A's whole-conversation fallback caps how many extra turn-derived
# queries it adds, so an insufficiency trigger on a long multi-turn session
# does not balloon Stage-1's query count unboundedly.
_MAX_FALLBACK_QUERIES = 3


def compose_slot_queries(final_slots: Mapping[str, str]) -> list[str]:
    """Primary Stage-1 queries — mirrors ``f2.py``'s pre-existing
    composition EXACTLY (same slots, same non-falsy filter, same order)."""
    return [final_slots[k] for k in STAGE1_QUERY_SLOTS if final_slots.get(k)]


def combined_slot_length(final_slots: Mapping[str, str]) -> int:
    """``sum(len(q) for q in compose_slot_queries(...))`` — Python ``len()``
    on the decoded string (REV-022 §2's operational definition), identical
    to what ``analysis/threshold_n_met8_w1_20260711.py`` computed as
    ``combined_len`` when it derived ``SLOT_INSUFFICIENCY_THRESHOLD_N`` from
    historical data."""
    return sum(len(q) for q in compose_slot_queries(final_slots))


def is_slot_insufficient(
    final_slots: Mapping[str, str], *, threshold: int = SLOT_INSUFFICIENCY_THRESHOLD_N
) -> bool:
    """Policy A's trigger condition (plan §3 Policy-A row): combined
    cc+HPI length < *threshold*, OR both falsy.

    The "both falsy" clause is logically subsumed whenever ``threshold >
    0`` (an empty/absent slot value has ``len() == 0``) but is kept
    explicit — matching the ratified A5 text verbatim (REV-022 §2) — so the
    condition stays correct even if a caller ever passes ``threshold <=
    0``.
    """
    both_falsy = not any(final_slots.get(k) for k in STAGE1_QUERY_SLOTS)
    return both_falsy or combined_slot_length(final_slots) < threshold


def probe_adjacent_turns(probe_events: Sequence[Mapping[str, Any]]) -> set[int]:
    """Turn numbers touched by ``f1.py``'s Safety-Probe/SI-screen state
    machine. Every ``probe_events`` entry (``trigger``/``progress``/
    ``escalation``/``deescalation``/``si_screen_result``) carries a
    ``turn`` key naming the turn whose patient utterance IS the probe/
    SI-screen exchange, by construction (``f1.py``'s
    ``_compose_probe_risk_assessment``/``_compose_screen_risk_assessment``
    build ``risk_assessment`` directly from these turns' utterances).
    """
    return {int(e["turn"]) for e in probe_events if "turn" in e}


def compose_fallback_queries(
    turns: Sequence[UtteranceTurn],
    probe_events: Sequence[Mapping[str, Any]],
    *,
    max_queries: int = _MAX_FALLBACK_QUERIES,
) -> list[str]:
    """Policy A's whole-conversation fallback (plan §3 Policy-A row):
    queries drawn from conversation turns EXCLUDING Safety-Probe/SI-screen-
    adjacent turns.

    NOT itself a complete VAL-010/REV-022 mitigation on its own — probe-turn
    exclusion targets a channel REV-011 §2 already showed is not the open
    one (ordinary chief_complaint/HPI content is). The actual mitigation is
    ``apply_risk_lexicon_filter``, applied to the COMBINED query set (this
    fallback output + the primary slot queries) at the single choke point
    in ``decide_policy_a`` — never here.
    """
    excluded = probe_adjacent_turns(probe_events)
    candidates = [
        t.patient_message for t in turns if t.turn not in excluded and t.patient_message
    ]
    return candidates[:max_queries] if max_queries else candidates


def apply_risk_lexicon_filter(queries: Sequence[str]) -> tuple[list[str], list[str]]:
    """SINGLE CHOKE POINT (REV-022 Issues 9/10, binding): every composed
    Stage-1 query, from EVERY source and BOTH policy arms, passes through
    this exact filter immediately before Stage 1 sees it — see this
    module's own docstring for the full rationale.

    Mirrors ``src.eval.f2_grounding``'s established discipline (ADR-014): a
    risk-lexicon hit is a hard rejection, never a redaction/clip/summary —
    a query containing any ``_RISK_PHRASES`` stem is DROPPED outright (the
    same "no evidence, no candidate"-style discipline, applied here to
    queries instead of evidence). Duplicate queries are NOT deduplicated
    here — that is the caller's concern, not this filter's.

    Returns:
        ``(clean_queries, dropped_queries)`` in original order — callers
        use ``dropped_queries`` for the MET-8 risk-worded-query incidence
        audit (plan §5) and for artifact persistence (this wave's audit-
        surface requirement).
    """
    clean: list[str] = []
    dropped: list[str] = []
    for q in queries:
        if q and _contains_any(q, _RISK_PHRASES):
            dropped.append(q)
        else:
            clean.append(q)
    return clean, dropped


@dataclass(frozen=True)
class TriggerDecision:
    """Uniform decision record for BOTH policy arms — persisted as an audit
    surface in F2's run artifact (``rag_trigger`` top-level key, ``f2.py``).
    """

    policy: Literal["A", "B"]
    retrieve: bool
    queries: list[str]
    dropped_queries: list[str]
    trigger_reason: str
    fallback_used: bool
    judge_output: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "retrieve": self.retrieve,
            "queries": list(self.queries),
            "dropped_queries": list(self.dropped_queries),
            "trigger_reason": self.trigger_reason,
            "fallback_used": self.fallback_used,
            "judge_output": self.judge_output,
        }


def no_rag_decision(policy: Literal["A", "B"]) -> TriggerDecision:
    """``--no-rag`` short-circuit — the trigger is never evaluated (no LLM
    judge call, no fallback composition), but the artifact still records a
    real, honest ``TriggerDecision`` (MET-6 mode-consistency: ``rag_
    trigger.retrieve`` must always agree with ``repro.mode``, even on this
    path)."""
    return TriggerDecision(
        policy=policy, retrieve=False, queries=[], dropped_queries=[],
        trigger_reason="no_rag_flag", fallback_used=False,
    )


def decide_policy_a(
    final_slots: Mapping[str, str],
    turns: Sequence[UtteranceTurn],
    probe_events: Sequence[Mapping[str, Any]],
    *,
    threshold: int = SLOT_INSUFFICIENCY_THRESHOLD_N,
    max_fallback_queries: int = _MAX_FALLBACK_QUERIES,
) -> TriggerDecision:
    """Policy A — slot-based trigger + whole-conversation fallback."""
    primary = compose_slot_queries(final_slots)
    insufficient = is_slot_insufficient(final_slots, threshold=threshold)

    fallback: list[str] = []
    if insufficient:
        fallback = compose_fallback_queries(
            turns, probe_events, max_queries=max_fallback_queries
        )

    # Fallback SUPPLEMENTS the primary queries (never replaces them) — the
    # primary slot text still carries retrieval signal even when short;
    # de-duplicated so an identical fallback turn (e.g. turn 0 restating the
    # chief complaint verbatim) is not sent to Stage 1 twice.
    composed = list(primary)
    for q in fallback:
        if q not in composed:
            composed.append(q)

    clean, dropped = apply_risk_lexicon_filter(composed)
    fallback_used = bool(fallback)
    retrieve = bool(clean)

    reason = "sufficient" if not insufficient else "insufficient"
    reason += "_fallback_used" if fallback_used else "_no_fallback"
    reason += "_retrieve" if retrieve else "_no_usable_queries"

    return TriggerDecision(
        policy="A", retrieve=retrieve, queries=clean, dropped_queries=dropped,
        trigger_reason=reason, fallback_used=fallback_used,
    )


async def decide_policy_b(
    judge: Any,
    *,
    session_id: str,
    final_slots: Mapping[str, str],
    turns: Sequence[UtteranceTurn],
) -> TriggerDecision:
    """Policy B — LLM-judged trigger.

    *judge* is a ``src.agents.rag_trigger_judge.RagTriggerJudgeAgent`` (typed
    ``Any`` here to keep this module's pure trigger logic import-free of the
    agent/adapter/model-router stack — only this one function has an LLM
    dependency, and only via the injected agent instance, never a module-
    level import of the router/adapter machinery).
    """
    from src.schemas.rag_trigger_judge import RagTriggerJudgeInput

    # REV-022 Issue 10's ORIGINAL mitigation (still valid, now layered under
    # the single choke point below, not relied on alone): risk_assessment
    # is hard-excluded as a query source — the judge never even sees it.
    licensed_slots = {k: v for k, v in final_slots.items() if k != RISK_SLOT_KEY}

    judge_input = RagTriggerJudgeInput(
        session_id=session_id, turns=list(turns), final_slots=licensed_slots,
    )
    judge_output = await judge.run(judge_input)

    raw_query = judge_output.query or ""
    composed = [raw_query] if raw_query.strip() else []
    clean, dropped = apply_risk_lexicon_filter(composed)

    # Final, EFFECTIVE retrieve decision requires BOTH the judge's own
    # retrieve=True AND a surviving (non-risk-lexicon-flagged) query to
    # actually search with — a judge that says "retrieve" but whose only
    # composed query is risk-worded must not reach Stage 1 (ADR-014
    # zero-tolerance precedent, applied here to queries). The judge's OWN
    # raw decision is preserved unmodified in `judge_output` below (Gate
    # 0.5 / SC-3b's stability check reads THAT field, not this one).
    retrieve = bool(judge_output.retrieve) and bool(clean)

    if judge_output.retrieve and not clean:
        reason = "judge_retrieve_but_query_risk_filtered"
    elif judge_output.retrieve:
        reason = "judge_retrieve"
    else:
        reason = "judge_no_retrieve"

    return TriggerDecision(
        policy="B", retrieve=retrieve, queries=clean, dropped_queries=dropped,
        trigger_reason=reason, fallback_used=False,
        judge_output={
            "retrieve": judge_output.retrieve,
            "query": judge_output.query,
            "reason_summary": judge_output.reason_summary,
            "model_used": judge_output.model_used,
            "prompt_version": judge_output.prompt_version,
            "prompts_degraded": judge_output.prompts_degraded,
            "latency_ms": judge_output.latency_ms,
        },
    )
