"""BUG-084 regression tests — user-reported live P0, session `94f75e81`.

(a) `_degrade_empathy_clause`'s exhaustion path only ever splices the
LEADING empathy clause, byte-identical from the terminal punctuation
onward — routing a QUESTION-content repeat (`question_repeat_*`, or a
`near_dup_*` empathy violation whose trailing question ALSO independently
repeats this same iteration) through it ships the same already-answered
question verbatim. Fixed by intercepting both shapes at exhaustion and
forcing a deterministic, on-target, different question via
`_force_target_question` instead (same composer `target_mismatch`'s own
exhaustion path already uses).

(b) The `exact_repeat`/`question_repeat` guard-retry hints previously
joined raw English `SLOT_KEY` identifiers directly into the LLM-facing
hint text with no "internal-only, do not echo" instruction — the model
then echoed the raw list verbatim to the patient. Fixed by routing every
multi-slot prompt injection through `_topic_list`/`_topic_label`
(natural-language Korean labels, never a raw key) plus an explicit
echo-prohibition. This module also asserts the sweep is complete across
every multi-slot injection site in `dialogue.py`
(`_build_retry_hint`/`_build_opening_context`/`_build_slot_context`).

No live LLM calls — deterministic stub adapters, same pattern as
`test_dialogue_self_referential_relief.py`/
`test_bug079_si_rearm_and_question_presence.py`.
"""

from __future__ import annotations

import asyncio

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import (
    _ALL_SLOTS,
    _SLOT_TOPIC_LABELS,
    DialogueAgent,
)
from src.prompts.loader import PromptLoader
from src.schemas.dialogue import DialogueInput

_RAW_SLOT_KEY_TOKENS = tuple(_ALL_SLOTS)
_INTERNAL_TERMS = ("슬롯", "coverage", "grounding")


def _assert_no_raw_slot_keys(text: str) -> None:
    """For SYSTEM-PROMPT/hint text (LLM-facing, never patient-facing):
    the raw English `SLOT_KEY` identifier must never appear. The internal
    TERMS ("슬롯"/"coverage"/"grounding") are legitimately mentioned here
    as part of the meta-instruction telling the model not to say them
    (e.g. "슬롯 이름이나... 그대로 언급하지 마세요") — checked separately,
    only at the actual patient-facing response-text level, by
    `_assert_no_internal_leak` below."""
    for key in _RAW_SLOT_KEY_TOKENS:
        assert key not in text, f"raw SLOT_KEY '{key}' leaked into: {text!r}"


def _assert_no_internal_leak(text: str) -> None:
    """For the actual patient-facing `assistant_response` text: neither a
    raw `SLOT_KEY` identifier NOR the internal terms themselves may ever
    appear — there is no legitimate reason for either to reach the
    patient."""
    _assert_no_raw_slot_keys(text)
    for term in _INTERNAL_TERMS:
        assert term not in text, f"internal term '{term}' leaked into: {text!r}"


# ── (b) unit: hint/context builders never inject raw slot keys ─────────


class TestBug084bNoRawSlotKeyInjection:
    def test_exact_repeat_hint_has_no_raw_slot_keys(self) -> None:
        inp = DialogueInput(
            session_id="t-bug084b-exact-repeat",
            user_message="없다구요",
            conversation_history=[],
            filled_slots={"chief_complaint": "잠을 못 잠"},
            safety_result=None,
            session_state=None,
            slot_updates_this_turn=None,
        )
        hint = DialogueAgent._build_retry_hint(  # noqa: SLF001
            "exact_repeat", inp, candidate_clause="", target_slot=None,
        )
        _assert_no_raw_slot_keys(hint)
        # natural-language topic label must still be present (informative,
        # not just stripped) — this is the exact live symptom's own
        # missing-slot list, now rendered safely.
        assert _SLOT_TOPIC_LABELS["risk_assessment"] in hint
        assert "내부 참고용" in hint

    def test_question_repeat_hint_has_no_raw_slot_keys(self) -> None:
        inp = DialogueInput(
            session_id="t-bug084b-question-repeat",
            user_message="없다구요",
            conversation_history=[],
            filled_slots={},
            safety_result=None,
            session_state=None,
            slot_updates_this_turn=None,
        )
        hint = DialogueAgent._build_retry_hint(  # noqa: SLF001
            "question_repeat_back_to_back", inp, candidate_clause="", target_slot=None,
        )
        _assert_no_raw_slot_keys(hint)
        assert "내부 참고용" in hint

    def test_opening_context_prior_missing_has_no_raw_slot_keys(self) -> None:
        session_state = {
            "opening_turn": True,
            "is_revisit": True,
            "prior_missing_slots": ["personal_social_history", "family_history"],
        }
        context = DialogueAgent._build_opening_context(session_state)  # noqa: SLF001
        _assert_no_raw_slot_keys(context)

    def test_slot_context_remaining_and_header_have_no_raw_slot_keys(self) -> None:
        agent = DialogueAgent(model_router=None, prompt_loader=PromptLoader("prompts"))
        context = agent._build_slot_context(  # noqa: SLF001
            filled_slots={"chief_complaint": "잠을 못 잠"},
            session_state=None,
            conversation_history=[],
        )
        _assert_no_raw_slot_keys(context)

    def test_slot_context_unknown_denied_positive_labels_have_no_raw_slot_keys(self) -> None:
        """The system-prompt-only status ledger (this method's own text,
        never patient-facing) is allowed to carry bookkeeping labels like
        "denied"/"unknown" for the model's own reasoning — the BUG-084b
        contract is specifically about raw `SLOT_KEY` identifiers/internal
        TERMS ("슬롯"/"coverage"/"grounding") never leaking, which this
        still asserts. Whether "unknown"/"denied" themselves ever reach the
        patient-facing `assistant_response` is covered separately, at the
        response-text level, by `TestBug084RoleSeparationInternalLeakGuard`
        below (coordinator directive, item 2)."""
        agent = DialogueAgent(model_router=None, prompt_loader=PromptLoader("prompts"))
        context = agent._build_slot_context(  # noqa: SLF001
            filled_slots={
                "chief_complaint": "잠을 못 잠",
                "medical_history": "미상(환자 응답: '잘 모르겠습니다')",
                "substance_use_history": "없음(환자 부인: '없어요')",
            },
            session_state={
                "slot_status": {
                    "medical_history": "unknown",
                    "substance_use_history": "denied",
                },
            },
            conversation_history=[],
        )
        _assert_no_raw_slot_keys(context)
        # An unknown-status item must render under its own dedicated
        # section, never silently folded into "이미 수집 완료" (positive)
        # or "denied".
        assert "모른다고 답함" in context


# ── (a) end-to-end: exhaustion degrade forces a topic switch, not an ───
# empathy-only splice ────────────────────────────────────────────────


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


class _RepeatedSubstanceQuestionAdapter(LLMAdapter):
    """Deterministic stub — every call re-asks the substance-use question
    (already answered/denied two turns ago), reproducing the live
    `94f75e81` shape: `question_repeat_back_to_back`/`near_dup_back_to_back`
    fire every attempt, exhausting the retry budget."""

    @property
    def adapter_name(self) -> str:
        return "stub"

    async def healthcheck(self) -> bool:
        return True

    def redact_for_log(self, payload):
        return payload

    async def chat(self, messages, **kwargs):
        # Leading clause deliberately differs from every prior turn (so
        # `exact_repeat`'s whole-text equality check does NOT fire) while
        # the TRAILING/question clause is byte-identical to the immediately
        # prior assistant turn's own trailing clause (so `question_repeat_
        # back_to_back` fires instead) — isolates the question-content-
        # repeat shape from `exact_repeat` noise.
        return ChatResponse(
            content=(
                '{"assistant_response": "그렇게 솔직히 답해주셔서 고맙습니다. '
                '최근에 술을 비롯해 담배나 마약류 같은 의존성이 생길 수 있는 물질을 '
                '사용하신 적이 있으신가요?"}'
            ),
            model="stub-model",
        )


def test_exhaustion_forces_topic_switch_not_empathy_only_degrade() -> None:
    """BUG-084a live repro shape: `substance_use_history` is already
    grounded (denied) and the round-robin target this turn is a DIFFERENT
    slot — every candidate re-asks the already-answered substance-use
    question anyway. The exhaustion path must ship a fresh, on-TARGET
    question, never the repeated substance-use question with only the
    empathy clause swapped."""
    agent = DialogueAgent(
        model_router=_StubRouter(_RepeatedSubstanceQuestionAdapter()),
        prompt_loader=PromptLoader("prompts"),
    )
    conversation_history = [
        {
            "role": "assistant",
            "content": "최근에 술이나 수면제 같은 것을 사용하신 적이 있으신가요?",
        },
        {"role": "user", "content": "아니요 없습니다"},
        {
            "role": "assistant",
            "content": (
                "이렇게 솔직하게 이야기해 주셔서 감사합니다. 최근에 술을 비롯해 담배나 "
                "마약류 같은 의존성이 생길 수 있는 물질을 사용하신 적이 있으신가요?"
            ),
        },
        {"role": "user", "content": "없다구요"},
    ]
    inp = DialogueInput(
        session_id="test-bug084a-question-repeat",
        user_message="없다구요",
        conversation_history=conversation_history,
        filled_slots={
            "chief_complaint": "잠을 잘 못 자요",
            "history_of_present_illness": "한달 전부터 예민해짐",
            "substance_use_history": "없음(환자 부인: '아니요 없습니다')",
        },
        safety_result={"risk_level": "none"},
        session_state={},
        slot_updates_this_turn=None,
    )

    output = asyncio.run(agent.run(inp))

    # The repeated substance-use question content must NEVER ship.
    assert "마약류" not in output.assistant_response
    assert "의존성이 생길 수 있는 물질" not in output.assistant_response
    # It must instead be a deterministic, forced target-bound question —
    # not the generic empathy-only splice.
    assert output.exhaustion_degrade in (
        "question_repeat_back_to_back", "question_repeat_session_cap",
        "near_dup_back_to_back", "near_dup_session_cap",
    )
    assert "?" in output.assistant_response
    _assert_no_internal_leak(output.assistant_response)


def test_is_empathy_degradable_still_excludes_question_repeat() -> None:
    """No-regression companion: `_is_empathy_degradable` itself is
    unchanged (question_repeat_* is intercepted BEFORE that check, at the
    exhaustion-dispatch level in `run()`, not by widening this predicate)."""
    assert DialogueAgent._is_empathy_degradable("question_repeat_back_to_back") is False  # noqa: SLF001


# ── Coordinator directive (2026-07-25, item 2): role-separation ────────
# principle — the RESPONSE TEXT itself must never expose slot-layer
# internal machinery, regardless of source. Pinned as an active runtime
# guard (`_internal_leak_violation`), not only a prompt-injection-hygiene
# fix — this is the actual "응답 텍스트에 슬롯 키·내부 상태 용어 출현 시
# 실패하는 회귀 테스트" the directive asked for.


class TestBug084RoleSeparationInternalLeakGuard:
    def test_detector_flags_raw_slot_key(self) -> None:
        assert DialogueAgent._internal_leak_violation(  # noqa: SLF001
            "risk_assessment, personal_social_history, family_history 중 "
            "아직 다루지 않은 항목이 있습니다."
        ) is True

    def test_detector_flags_internal_term(self) -> None:
        assert DialogueAgent._internal_leak_violation(  # noqa: SLF001
            "아직 슬롯 coverage가 부족합니다."
        ) is True

    def test_detector_does_not_flag_ordinary_reply(self) -> None:
        assert DialogueAgent._internal_leak_violation(  # noqa: SLF001
            "많이 힘드셨겠어요. 잠은 잘 주무세요?"
        ) is False

    class _RawSlotKeyLeakAdapter(LLMAdapter):
        """Deterministic stub — every call leaks a raw internal slot-key
        list verbatim (BUG-084b's own live symptom, session `94f75e81`)."""

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
                    '{"assistant_response": "risk_assessment, personal_social_history, '
                    'family_history, substance_use_history 중 아직 다루지 않은 슬롯이 '
                    '있습니다. 가족 관계에 대해 여쭤보고 싶어요."}'
                ),
                model="stub-model",
            )

    def test_run_never_ships_raw_slot_key_leak_on_exhaustion(self) -> None:
        agent = DialogueAgent(
            model_router=_StubRouter(self._RawSlotKeyLeakAdapter()),
            prompt_loader=PromptLoader("prompts"),
        )
        inp = DialogueInput(
            session_id="test-bug084-internal-leak",
            user_message="없다구요",
            conversation_history=[],
            filled_slots={"chief_complaint": "잠을 잘 못 자요"},
            safety_result={"risk_level": "none"},
            session_state={},
            slot_updates_this_turn=None,
        )
        output = asyncio.run(agent.run(inp))

        _assert_no_internal_leak(output.assistant_response)
        # Mirrors the pre-existing `output_isolation_*` exhaustion
        # convention exactly: flagged via `output_isolation_fallback`
        # (never `exhaustion_degrade`, whose contract is reserved for the
        # OTHER degrade paths) — see `run()`'s own dispatch comment.
        assert output.output_isolation_fallback is True
        assert "internal_leak" in output.retry_reasons
