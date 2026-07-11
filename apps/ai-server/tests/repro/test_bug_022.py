"""BUG-022 standing regression guard: per-clinical-agent Pydantic input-schema
field allowlist.

`error.md` BUG-022: `rag.session_insights` carries unredacted persona.md
ground-truth diagnostic labels (`class`, `phq9_score`, `gad7_score`,
`flag_suicidal`) into `retrieve_grounding()`'s `my_past` payload. No live
production caller reaches it today, but no schema-level guard prevents a
future wiring into a clinical agent's input. This file IS that guard —
`docs/ai/validation_plan_f1f2_continuous.md` §3's "BUG-022 mitigating guard
timing" paragraph and §6's "qa detection procedure" step 2 both require it to
run as a STANDING REGRESSION GATE from W1 through W6 (REV-023 ruling 6, Issue
9) — every `uv run pytest`, not first executed at W7's audit-only run.

Two independent assertions per model, mirroring plan §6's per-agent static
info-flow allowlist table (REV-023 ruling 1b, transcribed verbatim in the
plan) — columns (a) current-session/carry and (c) licensed upstream are the
only ones with a field-level representation on a Pydantic input model;
columns (b) own prompt and (d) persona-independent external resources are
accessed via `self._prompt_loader`/RAG queries, not passed as input fields:

1. `set(Model.model_fields) == APPROVED_FIELDS` — exact-match allowlist, so
   ANY drift (a new field, whether malicious or an innocent feature add)
   breaks this test and forces a conscious, reviewed update — not a silent
   pass. Mirrors the allowlist exactly (REV-023 ruling 1b); no extra
   licensed field is invented beyond what plan §6 names for each agent.
2. The 4 `retrieve_grounding()` ground-truth columns are explicitly asserted
   absent from every model's field set — defense in depth, independent of
   assertion 1 (still catches a forbidden field even if a well-meaning but
   incomplete allowlist update papered over assertion 1).

F2's `DomainInferenceAgent` is included per this mission's brief ("the F2
DomainInference input construction") — `error.md` BUG-022 repro step 6
already confirms F2 calls `retrieve_domain_chunks` (case_card/qa tables
only), never `retrieve_grounding`/`rag.session_insights`.
"""

from __future__ import annotations

from src.agents.base import AgentInput
from src.schemas.clinical_slot import ClinicalSlotInput
from src.schemas.dialogue import DialogueInput
from src.schemas.domain_inference import DomainInferenceInput
from src.schemas.input_normalizer import InputNormalizerInput
from src.schemas.safety import SafetyInput
from src.schemas.sentiment import SentimentSessionInput, SentimentUtteranceInput

# rag.session_insights' 4 persona-ground-truth columns (error.md BUG-022,
# load_simulations.py PERSONA_META / _phq_gad) — forbidden as an input field
# name on every clinical-agent input model.
BUG_022_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {"class", "phq9_score", "gad7_score", "flag_suicidal"}
)

# AgentInput's own base fields (src/agents/base.py) — present on every model
# below via inheritance, licensed for all agents (session/trace bookkeeping,
# not persona-derived).
_BASE_FIELDS: frozenset[str] = frozenset({"session_id", "request_id", "extra"})

# Per-agent allowlist, mirroring plan §6's per-agent static info-flow
# allowlist table (REV-023 ruling 1b) columns (a)/(c) exactly — do not invent
# extra licensed fields beyond what the table names for each agent.
APPROVED_FIELDS: dict[type[AgentInput], frozenset[str]] = {
    # (a) user_message, conversation_history
    SafetyInput: _BASE_FIELDS | {"user_message", "conversation_history"},
    # (a) conversation_history, current_slots (incl. narrowed carry per A2)
    ClinicalSlotInput: _BASE_FIELDS | {"conversation_history", "current_slots"},
    # (a) user_message, conversation_history, filled_slots (incl. carry),
    #     session_state; (c) safety_result, licensed upstream from
    #     SafetyClassifierAgent
    DialogueInput: _BASE_FIELDS
    | {
        "user_message",
        "conversation_history",
        "filled_slots",
        "safety_result",
        "session_state",
    },
    # (a) current-turn text (+ own config: input_type/dialect_hint)
    InputNormalizerInput: _BASE_FIELDS | {"raw_text", "input_type", "dialect_hint"},
    SentimentUtteranceInput: _BASE_FIELDS
    | {"utterance", "turn_index", "conversation_context"},
    SentimentSessionInput: _BASE_FIELDS
    | {"per_utterance_results", "conversation_history"},
    # (a) F1's saved conversation.json — turns/final_slots plus the other
    #     session-scoped fields F1Result already carries (session_ctrs,
    #     crisis_triggered/crisis_turn, is_first_visit, prior_handoff,
    #     probe_events, scale_scores); (d) Stage-1 RAG-corpus output
    #     (retrieved_chunks/retrieval_mode/queries) — a persona-independent
    #     external resource assembled by f2.py from case_card/qa, never from
    #     rag.session_insights (BUG-022 repro step 6: F2 calls
    #     retrieve_domain_chunks, not retrieve_grounding)
    DomainInferenceInput: _BASE_FIELDS
    | {
        "final_slots",
        "session_ctrs",
        "crisis_triggered",
        "crisis_turn",
        "is_first_visit",
        "turns",
        "prior_handoff",
        "probe_events",
        "scale_scores",
        "retrieved_chunks",
        "retrieval_mode",
        "queries",
    },
}


class TestBug022InputSchemaFieldAllowlist:
    """qa detection procedure #2 (plan §6): standing regression gate,
    W1 through W6 (REV-023 ruling 6, Issue 9) — not first executed at W7's
    audit-only run."""

    def test_every_named_model_has_an_allowlist_entry(self) -> None:
        """Fixture sanity: the 7 models this mission's brief names are all
        present — SafetyInput, ClinicalSlotInput, DialogueInput,
        InputNormalizerInput + SentimentAnalyzer's two inputs, and the F2
        DomainInference input construction."""
        expected = {
            SafetyInput,
            ClinicalSlotInput,
            DialogueInput,
            InputNormalizerInput,
            SentimentUtteranceInput,
            SentimentSessionInput,
            DomainInferenceInput,
        }
        assert set(APPROVED_FIELDS) == expected

    def test_field_allowlist_exact_match(self) -> None:
        for model, approved in APPROVED_FIELDS.items():
            actual = set(model.model_fields)
            assert actual == approved, (
                f"{model.__name__} field set drifted from the pre-registered "
                f"allowlist (plan §6, REV-023 ruling 1b) — "
                f"added: {sorted(actual - approved)}, "
                f"removed: {sorted(approved - actual)}. A genuinely new "
                "field requires an explicit, reviewed allowlist update, not "
                "a silent pass."
            )

    def test_bug_022_forbidden_fields_never_appear_on_any_clinical_agent_input(
        self,
    ) -> None:
        for model in APPROVED_FIELDS:
            leaked = set(model.model_fields) & BUG_022_FORBIDDEN_FIELDS
            assert not leaked, (
                f"{model.__name__} carries BUG-022 forbidden ground-truth "
                f"field(s): {sorted(leaked)} — rag.session_insights persona "
                "columns must never reach a clinical-agent input schema"
            )

    def test_forbidden_fields_are_exactly_the_four_bug_022_columns(self) -> None:
        """Guards the guard: pins the exact 4 columns `error.md` BUG-022
        names (load_simulations.py PERSONA_META / _phq_gad), not an
        accidentally narrower or wider set."""
        assert BUG_022_FORBIDDEN_FIELDS == {
            "class",
            "phq9_score",
            "gad7_score",
            "flag_suicidal",
        }
