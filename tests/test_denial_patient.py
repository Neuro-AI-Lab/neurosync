"""Offline smoke test for `harness.denial_patient.DenialPatientLLM`
(EXP-030, CVR-046 finding 5 remediation). Exercises the deterministic
scripted-reply logic on toy data only — no network/API calls, no
production route. Run with `pytest tests/` from repo root.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXP_HARNESS_DIR = REPO_ROOT / "experiments" / "EXP-030"
sys.path.insert(0, str(EXP_HARNESS_DIR))

from harness.denial_patient import (  # noqa: E402
    _DENIAL_FROM_TURN,
    _DENIAL_REPLY,
    DenialPatientLLM,
)
from harness.patient_llm import PatientPersona  # noqa: E402

# Keyword tables this reply must never match (hand-verified in the module
# docstring against apps/ai-server/src/agents/safety_classifier.py).
_SI_KEYWORDS = (
    "자살", "죽고", "죽을", "죽어버리", "목숨", "끝내고", "세상을 떠나", "유서",
    "자해", "손목", "칼로", "약을 많이 먹", "약물 과다", "살고 싶지 않",
    "사라지고 싶", "없어지고 싶", "해치고 싶", "때리고 싶", "죽이고 싶",
)


def _toy_persona() -> PatientPersona:
    return PatientPersona(
        persona_id="VP-TEST",
        name="테스트환자",
        severity="mild",
        ctrs_expected=5,
        visit_type="first_visit",
        system_prompt="toy persona system prompt",
        example_utterances="",
        patient_sex="female",
    )


def test_denial_reply_has_no_si_keywords() -> None:
    """The scripted denial reply must not itself keyword-match any SI/
    self-harm category, or the screen answer would re-trigger a probe
    episode instead of grounding directly via the denial format."""
    for kw in _SI_KEYWORDS:
        assert kw not in _DENIAL_REPLY, f"denial reply unexpectedly contains {kw!r}"


def test_denial_reply_has_negation_morpheme() -> None:
    """Must contain a negation morpheme (없/아니/않/모르/안) so
    `compose_screen_risk_assessment` picks the denial-format branch."""
    assert any(m in _DENIAL_REPLY for m in ("없", "아니", "않", "모르"))


def test_turn_indexed_script_matches_public_surface() -> None:
    """Same public surface as MockPatientLLM/EvasivePatientLLM/PatientLLM,
    and turn 1-2 neutral / turn >= _DENIAL_FROM_TURN denial-reply script."""

    async def run() -> None:
        patient = DenialPatientLLM(_toy_persona())
        first = await patient.start_conversation()
        assert isinstance(first, str) and first

        replies = [first]
        for _ in range(6):
            reply = await patient.respond("(counselor turn placeholder)")
            replies.append(reply)

        # Turn indices are 1-based; index 0 in `replies` is turn 1.
        for turn_idx, reply in enumerate(replies, start=1):
            if turn_idx < _DENIAL_FROM_TURN:
                assert reply != _DENIAL_REPLY
            else:
                assert reply == _DENIAL_REPLY

        log = patient.conversation_log
        # start_conversation appends 1 assistant entry; each respond()
        # appends a user entry (the counselor message) + an assistant
        # entry (the patient's reply): 1 + 2*(len(replies) - 1).
        assert len(log) == 1 + 2 * (len(replies) - 1)
        assert all(entry["role"] in ("assistant", "user") for entry in log)

    asyncio.run(run())


def test_denial_reply_stable_across_turns_regardless_of_assistant_text() -> None:
    """Never parses the assistant's free-form message text (module
    docstring rationale) — the same denial reply must fire regardless of
    what the counselor's message says."""

    async def run() -> None:
        patient = DenialPatientLLM(_toy_persona())
        await patient.start_conversation()
        await patient.respond("아무 질문")
        r1 = await patient.respond("가족력에 대해 질문")
        r2 = await patient.respond("최근에 스스로를 해치고 싶다거나 죽고 싶다는 생각이 든 적이 있나요?")
        assert r1 == r2 == _DENIAL_REPLY

    asyncio.run(run())
