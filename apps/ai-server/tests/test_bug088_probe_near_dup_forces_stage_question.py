"""BUG-088 regression (2026-07-25, qa live session `2671d9fe`).

Guard-exhaustion on a `near_dup_*` violation (e.g. `near_dup_session_cap`)
during an ACTIVE probe/SI-screen turn (`expected_probe_stage is not
None`) used to fall through to `_is_empathy_degradable` -> `_degrade_
empathy_clause`, which only splices the leading empathy clause and ships
the QUESTION span unchanged — live-confirmed to leave a topically
mismatched SI-method question shipping across turns regardless of the
patient's actual (non-SI-method) replies. Fixed: a `near_dup_*`
exhaustion on a probe-active turn now forces the deterministic stage-
bound question (`_force_probe_question`), the same composer
`probe_topic_mismatch`'s own exhaustion path already used.

No live LLM calls — `LLMAdapter` is stubbed deterministically, same
pattern as `test_bug085_followup_session_04cfe927.py`.
"""

from __future__ import annotations

import asyncio

from src.adapters.base import ChatResponse, LLMAdapter
from src.agents.dialogue import DialogueAgent
from src.prompts.loader import PromptLoader
from src.schemas.dialogue import DialogueInput

PROMPTS_DIR = "prompts"

_REPEATED_EMPATHY_CLAUSE = "진료 예약을 하시려는 마음이 드셨군요"


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
    """Every call ships the SAME off-topic candidate whose leading clause
    repeats a PRIOR turn's empathy clause family — deterministically
    exhausts the retry budget as a `near_dup_*` violation (never
    self-corrects, by construction)."""

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


def _probe_turn_with_prior_empathy_repeat() -> DialogueInput:
    """Active probe/SI-screen turn (`probe_instruction` set, stage
    `"plan"`) whose conversation history already used the SAME leading
    empathy clause family (`_REPEATED_EMPATHY_CLAUSE`) on the
    immediately preceding assistant turn — guarantees `near_dup_back_
    to_back` on any fixed candidate reusing that family, regardless of
    retries."""
    return DialogueInput(
        session_id="test-session-bug088",
        user_message="근처 병원을 알아볼 거예요",
        conversation_history=[
            {
                "role": "assistant",
                "content": (
                    f"{_REPEATED_EMPATHY_CLAUSE}. 혹시 구체적인 방법이나 수단을 "
                    "생각해 두셨는지 말씀해 주실 수 있을까요?"
                ),
            },
            {"role": "user", "content": "진료 예약 하려구요"},
        ],
        filled_slots={"chief_complaint": "우울감"},
        safety_result={"risk_level": "medium"},
        session_state={
            "probe_instruction": "혹시 구체적인 계획을 생각해 본 적이 있는지",
            "risk_question_pending": False,
            "probe_active": True,
        },
        slot_updates_this_turn=None,
    )


def test_near_dup_exhaustion_on_probe_turn_forces_stage_bound_question() -> None:
    # On-stage question (contains "구체적인 계획" — matches the "plan"
    # stage's own keyword set, so `probe_topic_mismatch` itself stays
    # FALSE on every attempt) but the LEADING EMPATHY clause repeats the
    # prior turn's own family — isolates the near_dup exhaustion path
    # from the probe_topic_mismatch one (which already has its own
    # dedicated, correct exhaustion handler and must NOT be what fires
    # here).
    off_topic_repeat = (
        f"{_REPEATED_EMPATHY_CLAUSE}. 혹시 구체적인 계획을 다시 한번 여쭤봐도 될까요?"
    )
    agent = DialogueAgent(
        model_router=_StubRouter(_FixedResponseAdapter(off_topic_repeat)),
        prompt_loader=PromptLoader(PROMPTS_DIR),
    )
    inp = _probe_turn_with_prior_empathy_repeat()
    output = asyncio.run(agent.run(inp))

    assert "?" in output.assistant_response
    assert output.exhaustion_degrade is not None
    # The violation actually degraded here is the near_dup one (empathy
    # clause repetition) — the on-topic question construction above is
    # what keeps `probe_topic_mismatch` from pre-empting it, isolating
    # this test to the gap BUG-088 identified.
    assert output.exhaustion_degrade.startswith("near_dup")
    # BUG-088 fix in effect: `_force_probe_question` composed the
    # question (its own `exhaustion_degrade_phrase` contract — the
    # assigned stage name), NOT `_degrade_empathy_clause` (which would
    # instead set `exhaustion_degrade_phrase` to a pool phrase and leave
    # the question span byte-identical to the candidate).
    assert output.exhaustion_degrade_phrase == "plan"
