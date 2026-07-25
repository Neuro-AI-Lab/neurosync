"""BUG-079 regression tests — CVR-056 follow-up.

Three independent defects, all confirmed via existing offline logs / a live
read-only DB inspection of session `db6da0e2` (2026-07-25, no new live
calls made by this fix):

1. SI-screen re-arm gap: `_advance_safety_probe`'s `risk_question_pending`
   branch reset `risk_question_pending=False` on a failed attempt (meta-
   utterance, BUG-078) but relied on the plain round-robin's turn-count
   modulo to eventually re-select `risk_assessment` — which live evidence
   (`experiments/EXP-032_f1_reverify/iteration3/logs_run2_offtopic_denial_
   gap`) showed does not reliably happen before session end. Fixed via
   `state.risk_screen_retry_needed`, consumed exclusively by
   `_resolve_dialogue_probe_instruction` (the only place that ever sets
   `risk_question_pending=True`), so a re-arm is always tied to a turn
   where the SI screen instruction is actually rendered.

2. Over-attribution parity gap: the same branch had no literal-target
   check (unlike BUG-077 item B's `_update_asked_slot_tracking`) — live
   session `db6da0e2` shows `risk_assessment` grounded from a reply to a
   turn that never literally asked about self-harm/suicide.

3. Question-presence + risk-turn compound-question guards (user directive
   2026-07-25 + CVR-056 finding 3): a collection turn must never ship with
   zero questions (live repro `db6da0e2` turn 4), and the SI-screen turn
   must never compound self-harm and other-directed-harm into one turn
   (live repro `iteration3/logs_run1_natural_requery` t5).

No live LLM calls — `_advance_safety_probe`/`_resolve_dialogue_probe_
instruction` are rule-based (per the orchestrator module's own docstring);
the DialogueAgent guard-loop tests use a deterministic stub adapter (same
pattern as `test_dialogue_self_referential_relief.py`).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.agents.orchestrator import OrchestratorAgent
from src.grounding import RISK_SLOT_KEY
from src.prompts.loader import PromptLoader
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.dialogue import DialogueInput
from src.schemas.orchestrator import OrchestratorInput, SessionState
from src.schemas.safety import SafetyOutput


def _safe_output() -> SafetyOutput:
    return SafetyOutput(
        model_used="test", prompt_version="v1", latency_ms=1,
        reason_summary="no risk detected", risk_level=RiskLevel.none,
        ctrs_level=CTRSLevel.STABLE, crisis_protocol_activated=False,
        requires_human_review=False, classifications=[],
    )


def _make_orchestrator() -> OrchestratorAgent:
    agent = OrchestratorAgent.__new__(OrchestratorAgent)
    agent._safety_agent = AsyncMock()
    agent._safety_agent.run = AsyncMock(return_value=_safe_output())
    return agent


# ── (1) SI-screen re-arm: run2's exact structure ─────────────────────────


class TestSiScreenRearmAfterFailedAttempt:
    def test_meta_complaint_arms_retry_needed_flag(self) -> None:
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug079-rearm-flag")
        state.risk_question_pending = True
        state.conversation_history = [
            {"role": "assistant", "content": "다른 증상이나 걱정되는 부분은 없으신가요?"},
            {"role": "user", "content": "없다니까 왜 자꾸 물어봐요."},
        ]

        agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug079-rearm-flag",
                raw_input="없다니까 왜 자꾸 물어봐요.",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert state.risk_grounded is False
        assert state.risk_screen_retry_needed is True

    def test_resolve_dialogue_probe_instruction_forces_si_screen_next_turn(self) -> None:
        """The exact gap CVR-056 found in `logs_run2_offtopic_denial_gap`:
        many OTHER slots are still missing (so the un-forced condition
        would NOT fire) and the backstop is nowhere near — yet the retry
        flag alone must force the SI screen as THIS turn's render target."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug079-rearm-force")
        state.turn_count = 6  # far from the 20-turn backstop
        state.risk_screen_retry_needed = True
        # Mirrors run2: several other question-able slots still missing.
        state.slot_data = {"chief_complaint": "우울감"}

        instruction = agent._resolve_dialogue_probe_instruction(state)  # noqa: SLF001

        assert instruction is not None
        assert state.risk_question_pending is True
        assert state.risk_screen_retry_needed is False  # consumed

    def test_full_run2_structure_real_denial_captured_after_meta_complaint(self) -> None:
        """End-to-end structural reproduction of run2 (session `59a4621a`):
        SI screen pending -> meta-complaint (fails) -> orchestrator resolves
        THIS turn's target (forced back to SI screen, per the fix) -> the
        patient's genuine, explicit denial on the immediately-following
        turn is captured — closing the exact gap CVR-056 flagged (the real
        denial arrived off-topic and was never grounded before this fix)."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug079-run2-repro")
        state.turn_count = 5
        state.slot_data = {
            "chief_complaint": "우울감", "history_of_present_illness": "한달 전부터",
        }
        state.risk_question_pending = True
        state.conversation_history = [
            {"role": "assistant", "content": "다른 증상이나 걱정되는 부분은 없으신가요?"},
        ]

        # Turn 6: meta-complaint fails the pending SI screen.
        state.conversation_history.append(
            {"role": "user", "content": "없다니까 왜 자꾸 물어봐요."}
        )
        escalated = agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug079-run2-repro",
                raw_input="없다니까 왜 자꾸 물어봐요.",
                session_state=state,
            ),
            state, _safe_output(),
        )
        assert escalated is False
        assert state.risk_grounded is False

        # Orchestrator resolves turn 6's OWN render target — forced back to
        # the SI screen instead of drifting to an unrelated slot.
        instruction = agent._resolve_dialogue_probe_instruction(state)  # noqa: SLF001
        assert instruction is not None
        assert state.risk_question_pending is True
        state.conversation_history.append(
            {"role": "assistant", "content": instruction}
        )

        # Turn 7: the patient's genuine, explicit SI denial.
        state.conversation_history.append(
            {
                "role": "user",
                "content": "자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
            }
        )
        agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug079-run2-repro",
                raw_input="자살이나 자해 생각은 전혀 없어요. 명확히 없다고 말씀드릴 수 있어요.",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data
        assert "자살이나 자해 생각은 전혀 없어요" in state.slot_data[RISK_SLOT_KEY]


# ── (2) Over-attribution parity: literal-target check on Cluster C ──────


class TestSiScreenLiteralTargetCheck:
    def test_reply_not_grounded_when_prior_turn_never_literally_asked_about_si(self) -> None:
        """Live repro `db6da0e2`: `risk_question_pending=True` was armed but
        the rendered prior turn ("잠을 잘 못 주무시고 짜증이 많이
        나셨겠어요. 그럴 때는 정말 지치고 힘들죠.") never literally asked
        about self-harm/suicide — the reply must NOT be grounded as an SI
        answer, and the retry flag must arm instead."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug079-literal-mismatch")
        state.risk_question_pending = True
        state.conversation_history = [
            {
                "role": "assistant",
                "content": "잠을 잘 못 주무시고 짜증이 많이 나셨겠어요. "
                "그럴 때는 정말 지치고 힘들죠.",
            },
            {"role": "user", "content": "잠을 잘 못자고 그냥 다 짜증나"},
        ]

        agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug079-literal-mismatch",
                raw_input="잠을 잘 못자고 그냥 다 짜증나",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert state.risk_grounded is False
        assert RISK_SLOT_KEY not in state.slot_data
        assert state.risk_screen_retry_needed is True

    def test_reply_grounds_when_prior_turn_literally_asked_about_si(self) -> None:
        """No-regression companion: when the rendered prior turn DID
        literally ask about self-harm/suicide, grounding proceeds exactly
        as before."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug079-literal-match")
        state.risk_question_pending = True
        state.conversation_history = [
            {
                "role": "assistant",
                "content": "최근에 스스로를 해치고 싶다거나 죽고 싶다는 생각이 든 적이 있으신가요?",
            },
            {"role": "user", "content": "없어요."},
        ]

        agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug079-literal-match",
                raw_input="없어요.",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data

    def test_no_conversation_history_falls_back_to_accepting(self) -> None:
        """When the caller never threaded conversation history back
        (`_last_assistant_message` returns ""), `infer_literal_target_slot`
        returns None — deliberately treated as acceptable (ambiguous, not a
        confirmed mismatch) so existing BUG-078 unit tests that construct
        `SessionState` without history keep passing unchanged."""
        agent = _make_orchestrator()
        state = SessionState(session_id="t-bug079-no-history")
        state.risk_question_pending = True

        agent._advance_safety_probe(  # noqa: SLF001
            OrchestratorInput(
                session_id="t-bug079-no-history",
                raw_input="없어요.",
                session_state=state,
            ),
            state, _safe_output(),
        )

        assert state.risk_grounded is True
        assert RISK_SLOT_KEY in state.slot_data


# ── (3a) DialogueAgent: question-presence guard ──────────────────────────


class _NoQuestionAdapter(LLMAdapter):
    """Deterministic stub — always ships pure empathy, no question at all
    (byte-identical to live repro `db6da0e2` turn 4)."""

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
                '{"assistant_response": "잠을 잘 못 주무시고 짜증이 많이 '
                '나셨겠어요. 그럴 때는 정말 지치고 힘들죠."}'
            ),
            model="stub-model",
        )


class _RiskCompoundQuestionAdapter(LLMAdapter):
    """Deterministic stub — always compounds SI + other-directed-harm into
    one turn (live repro `logs_run1_natural_requery` t5 shape)."""

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
                '{"assistant_response": "혹시 최근 스스로를 해치고 싶다는 생각이 '
                '들거나 죽고 싶다는 마음이 생기신 적이 있으신가요? 아니면 타인에게 '
                '해를 끼치고 싶다는 충동도 느껴지신 적이 있으신가요?"}'
            ),
            model="stub-model",
        )


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


def test_question_missing_guard_forces_a_question_on_exhaustion() -> None:
    """User directive (2026-07-25): a collection turn's response must
    never ship with zero questions — the exhaustion path must FORCE one,
    never silently ship the question-less candidate."""
    agent = DialogueAgent(
        model_router=_StubRouter(_NoQuestionAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    inp = DialogueInput(
        session_id="test-bug079-question-missing",
        user_message="잠을 잘 못자고 그냥 다 짜증나",
        conversation_history=[
            {"role": "user", "content": "안녕하세요"},
            {"role": "assistant", "content": "안녕하세요, 오늘 어떤 이야기든 편하게 나눠 보세요."},
        ],
        filled_slots={"chief_complaint": "요즘 너무 힘들어요"},
        safety_result={"risk_level": "none"},
        session_state={"dialogue_target_slot": "history_of_present_illness"},
        slot_updates_this_turn=None,
    )
    output = asyncio.run(agent.run(inp))

    assert "?" in output.assistant_response
    assert output.exhaustion_degrade == "question_missing"
    assert "question_missing" in output.retry_reasons


def test_question_missing_guard_does_not_fire_on_opening_turn() -> None:
    """No round-robin target applies on the opening turn — the guard must
    stay inert there (mirrors `_resolve_round_robin_target`'s own
    opening-turn exemption)."""
    agent = DialogueAgent(
        model_router=_StubRouter(_NoQuestionAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    inp = DialogueInput(
        session_id="test-bug079-opening-turn",
        user_message="",
        conversation_history=[],
        filled_slots={},
        safety_result=None,
        session_state={"opening_turn": True},
        slot_updates_this_turn=None,
    )
    output = asyncio.run(agent.run(inp))

    assert output.exhaustion_degrade != "question_missing"
    assert "question_missing" not in output.retry_reasons


# ── (3b) DialogueAgent: crisis-turn compound-question safety net ────────


def test_risk_compound_question_guard_truncates_on_exhaustion() -> None:
    """CVR-056 finding 3: the SI-screen turn must never ship 2+ questions
    — the exhaustion path truncates to the first question only."""
    agent = DialogueAgent(
        model_router=_StubRouter(_RiskCompoundQuestionAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    inp = DialogueInput(
        session_id="test-bug079-risk-compound",
        user_message="딱히 없어요.",
        conversation_history=[],
        filled_slots={
            "chief_complaint": "x", "history_of_present_illness": "x",
            "medical_history": "x", "family_history": "x",
        },
        safety_result={"risk_level": "low"},
        session_state={"risk_question_pending": True},
        slot_updates_this_turn=None,
    )
    output = asyncio.run(agent.run(inp))

    assert output.assistant_response.count("?") == 1
    assert output.exhaustion_degrade == "risk_compound_question"
    assert "risk_compound_question" in output.retry_reasons


def test_risk_compound_question_guard_inert_on_non_risk_turn() -> None:
    """Anti-forcing scope guard: an ordinary (non-risk-targeted) turn is
    NEVER subject to the 1-question cap, even if it happens to ask 2
    questions — this safety net is crisis-turn-scoped only."""
    agent = DialogueAgent(
        model_router=_StubRouter(_RiskCompoundQuestionAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    inp = DialogueInput(
        session_id="test-bug079-non-risk-turn",
        user_message="그냥 요즘 계속 피곤해요.",
        conversation_history=[],
        filled_slots={},
        safety_result={"risk_level": "none"},
        session_state={"dialogue_target_slot": "history_of_present_illness"},
        slot_updates_this_turn=None,
    )
    output = asyncio.run(agent.run(inp))

    assert output.exhaustion_degrade != "risk_compound_question"
    assert "risk_compound_question" not in output.retry_reasons


def test_slot_question_guide_risk_assessment_is_single_topic() -> None:
    """Source-level companion to the guard above: the deterministic guide
    text `_force_target_question` composes from must itself be single-
    topic — CVR-056 finding 3's root cause was the guide combining SI and
    other-directed-harm into one sentence."""
    from src.agents.dialogue import _SLOT_QUESTION_GUIDE

    guide = _SLOT_QUESTION_GUIDE["risk_assessment"]
    assert "타해" not in guide
