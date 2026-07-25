"""Smoke tests — `DialogueAgent._banned_self_referential_relief_violation`
and its wiring into the `run()` guard loop (CVR-039 finding 5 / PLAN-2026-
W30 cluster B #2, `experiments/EXP-030/plan.md` §3).

Scope: unit-level detector behavior + the retry-budget-exhaustion degrade
path, on synthetic (non-LLM) data. No live model calls — `_StubAdapter`
below always returns the banned "다행" phrase so the exhaustion branch is
deterministically reached within the fixed retry budget.
"""

from __future__ import annotations

import asyncio

import pytest

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import PROMPT_VERSION, DialogueAgent
from src.prompts.loader import PromptLoader
from src.schemas.dialogue import DialogueInput

# ── Unit: the detector itself ───────────────────────────────────────────

@pytest.mark.parametrize(
    "clause",
    [
        "자해나 자살 생각이 없으시다니 다행이에요",
        "그런 위험한 생각이 전혀 없다는 말씀, 정말 다행이에요",
        "다행입니다",
        "다행이네요",
        "다행스럽네요",
    ],
)
def test_banned_marker_detected(clause: str) -> None:
    assert DialogueAgent._banned_self_referential_relief_violation(clause) is True


@pytest.mark.parametrize(
    "clause",
    [
        "그렇게 말씀해 주셔서 감사해요",
        "그런 변화가 있었군요",
        "",
        "많이 힘드셨겠어요",
    ],
)
def test_allowed_patient_directed_forms_not_flagged(clause: str) -> None:
    assert DialogueAgent._banned_self_referential_relief_violation(clause) is False


# ── CVR-041 pin: full-response scan (not leading-clause-only) ──────────

@pytest.mark.parametrize(
    "assistant_response",
    [
        # "다행" is the SECOND clause, after an allowed leading empathy
        # clause — CVR-041 finding 1's exact undetected shape under the
        # old leading-clause-only scope.
        "그렇게 말씀해 주셔서 감사해요. 다행이네요. 언제부터 그러셨나요?",
        "그런 변화가 있었군요. 정말 다행이에요. 잠은 잘 주무세요?",
        # "다행" appears only in the trailing/question span.
        "요즘 어떠세요? 큰 문제 없다니 다행입니다.",
    ],
)
def test_banned_marker_detected_outside_leading_clause(assistant_response: str) -> None:
    """CVR-041 pin (EXP-030 pin-fix wave): the scan now covers the FULL
    `assistant_response`, not just the leading clause — a "다행" occurrence
    in a later clause must still be caught."""
    assert DialogueAgent._banned_self_referential_relief_violation(
        assistant_response
    ) is True


def test_allowed_full_response_with_no_banned_root_not_flagged() -> None:
    assistant_response = "그렇게 말씀해 주셔서 감사해요. 요즘 잠은 잘 주무세요?"
    assert DialogueAgent._banned_self_referential_relief_violation(
        assistant_response
    ) is False


def test_is_empathy_clause_recognizes_banned_marker() -> None:
    # Required for `_degrade_empathy_clause`'s REPLACE (not PREPEND) branch
    # to fire on a `self_referential_relief` violation.
    assert DialogueAgent._is_empathy_clause("자살 생각이 없으시다니 다행이에요") is True


def test_is_empathy_degradable_covers_new_violation() -> None:
    assert DialogueAgent._is_empathy_degradable("self_referential_relief") is True


def test_degrade_empathy_clause_replaces_banned_phrase_not_prepends() -> None:
    response = "자해나 자살 생각이 없으시다니 다행이에요. 요즘 잠은 잘 주무세요?"
    degraded, phrase = DialogueAgent._degrade_empathy_clause(
        response, "self_referential_relief", conversation_history=None,
    )
    assert "다행" not in degraded
    assert degraded.startswith(phrase)
    # the trailing question must survive byte-identical
    assert degraded.endswith("요즘 잠은 잘 주무세요?")


# ── Prompt version pin / loader resolution ──────────────────────────────

def test_prompt_version_pinned_v5_6() -> None:
    # BUG-079 / REV-022 §4 (2026-07-25): bumped v5.4 -> v5.5 (NOT
    # addition-only — the "공감 캘리브레이션" section was condensed to a
    # principle + one safety-critical ban, see v5.5's own changelog note).
    # BUG-085-follow-up (2026-07-25, session `04cfe927`): bumped v5.5 ->
    # v5.6 (CVR-057 6-type discriminant table, see v5.6's own changelog
    # note). The safety-critical "다행" ban itself (this test module's
    # subject) is preserved, unchanged in substance, by both revisions.
    assert PROMPT_VERSION == "v5.6"


def test_v5_1_prompt_resolves_and_bans_root_while_allowing_gratitude() -> None:
    loader = PromptLoader("prompts")
    content = loader.load_system_prompt("dialogue", PROMPT_VERSION)
    assert "다행" in content  # explicit prohibition text present
    assert "금지" in content
    assert "감사해요" in content  # patient-directed gratitude stays allowed


# ── End-to-end guard loop: exhaustion degrades instead of shipping ──────

class _AlwaysBannedAdapter(LLMAdapter):
    """Deterministic stub — every call returns a self-referential-relief
    response, forcing the guard loop's retry budget to exhaust so the
    `self_referential_relief` exhaustion-degrade branch is exercised.
    Subclasses `LLMAdapter` (not duck-typed) to satisfy `run()`'s own
    `assert isinstance(adapter, LLMAdapter)` guard."""

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        return ChatResponse(
            content=(
                '{"assistant_response": "자살 생각이 없으시다니 다행이에요. '
                '요즘 잠은 잘 주무세요?"}'
            ),
            model="stub-model",
        )


class _StubSelection:
    adapter_name = "stub"
    model_id = "stub-model"
    supports_json_schema = False
    supports_json_object = True


class _StubRouter:
    def select_model(self, agent_name, require_json=True):
        return _StubSelection()

    def get_adapter(self, name):
        return _AlwaysBannedAdapter()

    def record_success(self, name):
        pass

    def record_failure(self, name, exc):
        pass

    def get_fallback(self, agent_name, adapter_name, err):
        return None


def test_run_degrades_self_referential_relief_on_exhaustion() -> None:
    agent = DialogueAgent(model_router=_StubRouter(), prompt_loader=PromptLoader("prompts"))
    inp = DialogueInput(
        session_id="test-session-cluster-b2",
        user_message="자해나 자살 생각은 없어요.",
        conversation_history=[],
        filled_slots={},
        safety_result={"risk_level": "medium"},
        session_state={},
        slot_updates_this_turn=None,
    )
    output = asyncio.run(agent.run(inp))
    assert "다행" not in output.assistant_response
    assert output.exhaustion_degrade == "self_referential_relief"
    assert "self_referential_relief" in output.retry_reasons
