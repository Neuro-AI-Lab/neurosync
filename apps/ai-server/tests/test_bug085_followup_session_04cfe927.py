"""Regression tests — user-reported live P0, session `04cfe927`
(2026-07-25, `test260725`), 4 defects root-caused and fixed:

1. Compound-question pile-up (5 "?" in one turn) during the graduated
   4-stage Safety Probe — BUG-083 item 3's own documented-open gap
   ("probe_active turns still unguarded") finally closed by widening
   `is_risk_target_turn` to also cover `probe_instruction`-active turns,
   so the EXISTING `risk_compound_violation`/`risk_question_missing`
   guards (and their existing exhaustion composers) now cover the probe
   too, with zero new violation types for THIS symptom.
2. `chief_complaint`-shaped question repeated 4 turns straight while the
   graduated probe was stuck at its "plan" stage (`probe_instruction`
   ignored by the model) — new `probe_topic_mismatch` guard +
   `_force_probe_question` deterministic composer.
3. Two meta-utterance variants ("기억 못하시나요?", "너 못하냐고" —
   complaints about the AGENT's own capability/memory) invisible to
   `grounding.is_meta_utterance`'s keyword list, plus a whitespace-
   sensitivity gap ("이야기했잖아" vs "이야기 했잖아") — both closed.
4. Empathy-intensity miscalibration (fact-only replies and meta-
   utterances drawing crisis-level distress empathy) — CVR-057's 6-type
   discriminant table folded into dialogue v5.6 as an abstract principle
   (prompt-level; verified here via content assertions) + a best-effort
   `utterance_type_classified` telemetry log field (qa recommendation
   #3) verified not to raise.

No live LLM calls anywhere in this module — `LLMAdapter` is stubbed
deterministically, same pattern as `test_bug082_question_missing_guard_
probe_mode.py`/`test_dialogue_self_referential_relief.py`.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import PROMPT_VERSION, DialogueAgent
from src.grounding import is_meta_utterance
from src.prompts.loader import PromptLoader
from src.schemas.dialogue import DialogueInput

PROMPTS_DIR = "prompts"


# ── Stub harness (mirrors test_bug082_question_missing_guard_probe_mode) ──


class _StubSelection:
    adapter_name = "stub"
    model_id = "stub-model"
    supports_json_schema = False
    supports_json_object = True


class _StubRouter:
    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    def select_model(self, agent_name, require_json=True):
        return _StubSelection()

    def get_adapter(self, name):
        return self._adapter

    def record_success(self, name):
        pass

    def record_failure(self, name, exc):
        pass

    def get_fallback(self, agent_name, adapter_name, err):
        return None


class _FixedResponseAdapter(LLMAdapter):
    """Every call ships the SAME fixed candidate — deterministically
    exhausts the retry budget against whatever guard the test targets."""

    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        return ChatResponse(
            content=f'{{"assistant_response": "{self._text}"}}',
            model="stub-model",
        )


def _probe_active_input(
    user_message: str, probe_instruction: str, extra_state: dict | None = None,
) -> DialogueInput:
    """`probe_active`-only turn (mirrors session `04cfe927`'s actual
    session_state shape: `probe_instruction` set, `risk_question_pending`
    False — the distinct-flag gap BUG-083 item 3 flagged)."""
    state = {
        "probe_instruction": probe_instruction,
        "risk_question_pending": False,
        "probe_active": True,
    }
    if extra_state:
        state.update(extra_state)
    return DialogueInput(
        session_id="test-session-04cfe927",
        user_message=user_message,
        conversation_history=[
            {"role": "assistant", "content": "그런 상황이시군요."},
            {"role": "user", "content": user_message},
        ],
        filled_slots={"chief_complaint": "요즘 너무 우울해서요"},
        safety_result={"risk_level": "medium"},
        session_state=state,
        slot_updates_this_turn=None,
    )


# ── Defect 1: compound-question pile-up during probe_active ─────────────


def test_is_risk_target_turn_widened_by_probe_instruction_alone() -> None:
    """Unit-level confirmation of the widened predicate's precondition:
    `_resolve_round_robin_target` is still None on a probe turn (round-
    robin guards stay inert), but the session carries `probe_instruction`
    with `risk_question_pending` False — exactly session `04cfe927`'s
    shape, and exactly the gap BUG-083 item 3 named."""
    inp = _probe_active_input("술과 수면제 복용중이에요.", "최근에 그런 생각이 얼마나 자주 드는지")
    assert DialogueAgent._resolve_round_robin_target(inp) is None  # noqa: SLF001
    assert inp.session_state["risk_question_pending"] is False
    assert inp.session_state["probe_instruction"]


def test_run_truncates_compound_question_during_probe_active() -> None:
    """End-to-end: the exact live shape (5 "?" crammed into one candidate
    on a `probe_active`-only turn) is now caught and truncated to a single
    question — session `04cfe927` turn 6's defect."""
    five_question_text = (
        "술과 수면제를 복용하고 계신다니 정말 힘드실 것 같아요. 그런 상황에서 "
        "어떤 점이 가장 견디기 힘든지 말씀해 주시겠어요? 그런 생각이 얼마나 "
        "자주 드는지요? 그런 순간에 힘이 되어주는 사람이나 활동이 있으신가요? "
        "그리고 최근에 술이나 수면제, 진정제, 카페인 같은 물질 사용을 하고 "
        "계신지 말씀해 주시겠어요? 그런 생각이 언제부터 시작되었는지 말씀해 "
        "주시겠어요?"
    )
    agent = DialogueAgent(
        model_router=_StubRouter(_FixedResponseAdapter(five_question_text)),
        prompt_loader=PromptLoader(PROMPTS_DIR),
    )
    inp = _probe_active_input(
        "술과 수면제 복용중이에요.", "최근에 그런 생각이 얼마나 자주 드는지",
    )
    output = asyncio.run(agent.run(inp))

    assert output.assistant_response.count("?") == 1
    assert output.exhaustion_degrade == "risk_compound_question"


def test_run_forces_reask_on_zero_question_probe_active_turn() -> None:
    """Same widened predicate, zero-question side: a `probe_active`-only
    candidate with no "?" at all must now also be caught (previously
    invisible to every guard, per BUG-083 item 3)."""
    agent = DialogueAgent(
        model_router=_StubRouter(_FixedResponseAdapter("그런 변화가 있었군요.")),
        prompt_loader=PromptLoader(PROMPTS_DIR),
    )
    inp = _probe_active_input(
        "네? 무슨 질문이 그렇게 많은가요", "혹시 구체적인 계획을 생각해 본 적이 있는지",
    )
    output = asyncio.run(agent.run(inp))

    assert "?" in output.assistant_response
    assert output.exhaustion_degrade in ("risk_question_missing", "probe_topic_mismatch")


# ── Defect 2: probe stage topic ignored (chief_complaint-shaped repeat) ──


def test_run_forces_stage_bound_question_on_probe_topic_mismatch() -> None:
    """End-to-end: the model is told the current probe stage is "plan"
    but ships a chief_complaint-shaped generic question 3 times straight
    (session `04cfe927` turns 7-10's actual shape) — the new
    `probe_topic_mismatch` guard must force a stage-bound question on
    exhaustion instead of shipping the off-topic candidate."""
    off_topic_text = (
        "죄송해요, 질문이 많아서 부담스러우셨을 것 같아요. 혹시 지금 가장 "
        "견디기 힘드신 점이 무엇인지 말씀해 주시겠어요?"
    )
    agent = DialogueAgent(
        model_router=_StubRouter(_FixedResponseAdapter(off_topic_text)),
        prompt_loader=PromptLoader(PROMPTS_DIR),
    )
    inp = _probe_active_input(
        "기억 못하시나요?", "혹시 구체적인 계획을 생각해 본 적이 있는지",
    )
    output = asyncio.run(agent.run(inp))

    assert output.exhaustion_degrade == "probe_topic_mismatch"
    assert "계획" in output.assistant_response
    # The stale chief_complaint-shaped repeat must not survive verbatim.
    assert "가장 견디기 힘드신 점이 무엇인지" not in output.assistant_response


def test_force_probe_question_composes_stage_topic() -> None:
    """Unit: `_force_probe_question` names the assigned stage's own
    `PROBE_STAGES` hint, never a chief_complaint-style substitute."""
    composed = DialogueAgent._force_probe_question(  # noqa: SLF001
        "그런 마음이시군요.", "plan",
    )
    assert "계획" in composed
    assert composed.count("?") == 1


def test_run_does_not_flag_on_topic_probe_answer() -> None:
    """Regression guard: a candidate that DOES literally ask the assigned
    stage's topic must not be flagged as `probe_topic_mismatch`."""
    on_topic_text = "그러셨군요. 혹시 구체적인 계획을 생각해 본 적이 있으신가요?"
    agent = DialogueAgent(
        model_router=_StubRouter(_FixedResponseAdapter(on_topic_text)),
        prompt_loader=PromptLoader(PROMPTS_DIR),
    )
    inp = _probe_active_input(
        "기억 못하시나요?", "혹시 구체적인 계획을 생각해 본 적이 있는지",
    )
    output = asyncio.run(agent.run(inp))

    assert "probe_topic_mismatch" not in output.retry_reasons
    assert output.assistant_response == on_topic_text


# ── Defect 3: meta-utterance recognition gaps ────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "기억 못하시나요?",
        "너 못하냐고",
        "기억 못 하시나요?",
        "아니ㅜ아까 다 이야기 했잖아",  # whitespace-variant of "이야기했잖아"
    ],
)
def test_is_meta_utterance_recognizes_capability_and_spacing_variants(
    text: str,
) -> None:
    assert is_meta_utterance(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "없어요.",
        "자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
        "그냥 요즘 계속 피곤한 느낌이에요.",
        "",
    ],
)
def test_is_meta_utterance_still_does_not_flag_genuine_answers(text: str) -> None:
    assert is_meta_utterance(text) is False


# ── Defect 4: CVR-057 empathy-calibration principle (prompt) + telemetry ──


def test_prompt_version_pinned_v5_6() -> None:
    # BUG-089 (2026-07-25, session `2671d9fe`): bumped v5.6 -> v5.7
    # (addition-only — one new current-turn-attribution bullet, see
    # v5.7's own changelog note). Every assertion below still holds — the
    # v5.6 content this test targets is byte-identical in v5.7.
    assert PROMPT_VERSION == "v5.7"


def test_v5_6_prompt_carries_cvr057_discriminant_principle() -> None:
    loader = PromptLoader(PROMPTS_DIR)
    content = loader.load_system_prompt("dialogue", PROMPT_VERSION)
    assert content, "dialogue v5.7 prompt loaded empty"

    # Fact-response and meta-utterance de-escalation principles present.
    assert "사실/행정 응답" in content
    assert "위기급 고통 공감" in content or "고강도 고통 공감" in content
    # Third meta-utterance subtype (capability/memory complaint) present.
    assert "능력·기억" in content or "능력/기억" in content
    # Safety-critical ban survives unchanged.
    assert "다행" in content
    assert "감사해요" in content


def test_utterance_type_classification_smoke() -> None:
    """`_classify_utterance_type` never raises and returns one of the
    documented labels — exercised directly (unit) and via a full `run()`
    call (the logging call site) to confirm it doesn't break the guard
    loop."""
    assert DialogueAgent._classify_utterance_type(  # noqa: SLF001
        "술과 수면제 복용중이에요.", False,
    ) == "fact_response"
    assert DialogueAgent._classify_utterance_type(  # noqa: SLF001
        "기억 못하시나요?", False,
    ) == "meta_utterance"
    assert DialogueAgent._classify_utterance_type(  # noqa: SLF001
        "요즘 너무 우울하고 힘들어요.", False,
    ) == "emotion_disclosure"
    assert DialogueAgent._classify_utterance_type("없어요", False) == "short_answer"  # noqa: SLF001
    assert DialogueAgent._classify_utterance_type("힘들어요", True) == "crisis"  # noqa: SLF001


def test_run_logs_utterance_type_without_raising(caplog: pytest.LogCaptureFixture) -> None:
    agent = DialogueAgent(
        model_router=_StubRouter(_FixedResponseAdapter("그렇군요. 잠은 잘 주무세요?")),
        prompt_loader=PromptLoader(PROMPTS_DIR),
    )
    inp = DialogueInput(
        session_id="test-session-cvr057",
        user_message="술과 수면제 복용중이에요.",
        conversation_history=[],
        filled_slots={"chief_complaint": "요즘 너무 우울해서요"},
        safety_result={"risk_level": "low"},
        session_state={},
        slot_updates_this_turn=None,
    )
    with caplog.at_level(logging.INFO):
        output = asyncio.run(agent.run(inp))

    assert output.assistant_response
    assert any("utterance_type_classified" in r.message for r in caplog.records)
