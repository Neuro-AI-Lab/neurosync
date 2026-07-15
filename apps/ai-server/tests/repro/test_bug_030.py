"""BUG-030 / ADR-028 (`docs/ai/fix_proposal_bug030.md`) — empathy-phrase
repetition fix, regression tests.

Diagnosis (fix_proposal_bug030.md, channels (a)/(b)): a hardcoded
`alternatives` list in `DialogueAgent._build_slot_context` re-recommended
banned empathy phrases every turn (the O-block was never filtered against
`used_empathy`), and 2 of the 5 hardcoded alternatives were byte-identical
to 2 of v3's own 3 canonical example phrases (`docs/ai/prompts/dialogue/
v3.system.md` rule 2) — a directive self-contradiction that collapsed
generation onto a single reused phrase (9 of 10 scored turns, counting the
turn-0 opener, in the cited VP-001 artifact).

Fix, locked in by this file: delete the `alternatives` re-recommendation
menu entirely (nothing is positively re-recommended); keep only the
negative constraint (`used_empathy` -> X lines, "do not reuse"); replace
the removed positive-menu pointer with a principle-level "generate natural
empathy matched to what the patient just said" instruction. The v4 prompt
file itself (`docs/ai/prompts/dialogue/v4.system.md`) drops v3's 3 canned
example phrases — covered by `test_prompt_v3.py::TestDialogueV4File`, not
here; this file covers only the runtime `_build_slot_context` injection.
"""

from __future__ import annotations

from src.agents.dialogue import DialogueAgent

# The 5 strings that used to populate `_build_slot_context`'s deleted
# `alternatives` list (fix_proposal_bug030.md §1 channel (a)) — locks in
# "menu deleted, not filtered" (proposal §3 item 2). 2 of these were
# byte-identical to 2 of v3's 3 canonical example phrases (channel (b)).
_FORMER_ALTERNATIVES = [
    "그런 상황이라면 정말 지치셨을 것 같아요.",
    "이야기해 주셔서 감사합니다.",
    "쉽지 않은 시간이셨겠어요.",
    "말씀하신 상황이 충분히 이해됩니다.",
    "그 마음 충분히 공감됩니다.",
]

# The literal clause BUG-030's cited artifact (VP-001) reproduced: it was
# `alternatives[0]` — the first surviving item of the unconditional O-list
# every turn after being banned by the X-list.
_BUG030_REPRODUCED_PHRASE = "그런 상황이라면 정말 지치셨을 것 같아요"


def _agent() -> DialogueAgent:
    return DialogueAgent.__new__(DialogueAgent)


class TestNegativeConstraintOnly:
    """Channel (a) fix: `used_empathy` still bans reuse (X lines), but
    nothing is positively re-recommended (no O lines, no menu)."""

    def test_negative_constraint_lists_used_phrases(self) -> None:
        history = [
            {"role": "assistant", "content": "많이 힘드셨겠어요. 잠은 잘 주무세요?"},
            {"role": "user", "content": "네 잘 못 자요."},
            {"role": "assistant", "content": "그러셨군요, 어려운 시간이었겠어요. 식사는요?"},
            {"role": "user", "content": "그럭저럭요."},
        ]
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=history,
        )
        assert 'X "많이 힘드셨겠어요' in ctx
        assert 'X "그러셨군요, 어려운 시간이었겠어요' in ctx

    def test_no_positive_recommendation_menu(self) -> None:
        """Locks in 'menu deleted, not filtered' — no `O "` line survives,
        and none of the 5 legacy `alternatives` strings leak into the
        context even though prior-turn history now exists."""
        history = [
            {"role": "assistant", "content": "많이 힘드셨겠어요. 잠은 잘 주무세요?"},
        ]
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=history,
        )
        assert 'O "' not in ctx
        for alt in _FORMER_ALTERNATIVES:
            assert alt not in ctx, f"deleted alternative leaked into context: {alt!r}"

    def test_empty_history_no_used_phrase_block(self) -> None:
        """Regression check: turn 0/1 (no assistant turns yet) renders no
        X block — preserves the existing `if used_empathy:` guard."""
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=None,
        )
        assert 'X "' not in ctx
        assert "이미 사용했으므로" not in ctx

    def test_long_prior_clause_rendered_uncapped(self) -> None:
        """BUG-030 iter-2 (`docs/ai/fix_design_bug030_iter2.md` §1): the old
        inline extraction capped at `[:30]` — `fix_proposal_bug030.md`
        finding c-v flagged this as a latent under-match risk once a filter
        is compared against it (the near-dup guard, `test_bug_030_iter2.py`).
        A prior assistant clause >30 chars must render in the X-list FULL,
        not truncated."""
        long_clause = (
            "그런 상황이라면 정말 많이 힘드셨을 것 같고 걱정도 되셨을 것 같아요"
        )
        assert len(long_clause) > 30
        history = [
            {"role": "assistant", "content": f"{long_clause}. 잠은 잘 주무세요?"},
        ]
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=history,
        )
        assert f'X "{long_clause}...' in ctx
        assert long_clause[:30] + '..."' not in ctx


class TestPrincipleLevelInstructionPresent:
    """The replacement instruction — natural generation, not menu
    selection — is present on every plain round-robin turn, regardless of
    whether prior-turn history exists yet."""

    def test_present_with_no_history(self) -> None:
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=None,
        )
        assert "그때그때 새로 표현" in ctx

    def test_present_with_history(self) -> None:
        history = [{"role": "assistant", "content": "많이 힘드셨겠어요."}]
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=history,
        )
        assert "그때그때 새로 표현" in ctx

    def test_empathy_block_still_present_structurally(self) -> None:
        """Guard-rail (fix_proposal_bug030.md §2 'Guard-rail'): the empathy
        directive block must never disappear — only the broken
        re-recommendation menu was removed, not the requirement that a
        turn opens with an empathetic acknowledgment."""
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=None,
        )
        assert "## 공감 표현 규칙" in ctx
        assert "생략하지 마세요" in ctx


class TestMutationCheckPreviouslyUsedPhraseNeverRecommendedAgain:
    """Explicit mutation-check ask (fix_proposal_bug030.md §3 item 5): this
    test is constructed to FAIL against the pre-fix code (where
    `alternatives[0]` duplicated the just-banned phrase into an O line 3
    lines below the X line) and PASS against the fix. If the
    negative-constraint-only design is ever reverted back to a
    filtered-or-unfiltered `alternatives` menu, this test must catch it.
    """

    def test_previously_used_phrase_never_recommended_again(self) -> None:
        history = [
            {
                "role": "assistant",
                "content": (
                    f"{_BUG030_REPRODUCED_PHRASE}. 혹시 이전에 정신건강의학과 "
                    "진료를 받아보신 적이 있으신가요?"
                ),
            },
        ]
        ctx = _agent()._build_slot_context(
            filled_slots={}, session_state=None, conversation_history=history,
        )

        # Appears exactly once, as the X (banned) line — never also as an O
        # (recommended) line further down, and never as a bare
        # recommendation anywhere else in the context.
        assert ctx.count(_BUG030_REPRODUCED_PHRASE) == 1
        assert f'X "{_BUG030_REPRODUCED_PHRASE}...' in ctx
        assert 'O "' not in ctx
