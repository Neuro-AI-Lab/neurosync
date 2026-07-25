"""BUG-074 — dialogue v5.2 prompt gains a meta-utterance-referent section.
BUG-077 (2026-07-25) bumped the runtime pin to v5.3 (widened meta-utterance
recognition + catch-all-question prohibition, addition-only over v5.2).
BUG-078 / CVR-055 finding 3 (2026-07-25) bumped the runtime pin again to
v5.4 — NOT addition-only: the two meta-utterance sections' own worked-
example sentences (reproduced verbatim live, a BUG-030-lineage prompt-
example-anchoring recurrence) are replaced with an abstract shape
description; every other line is unchanged. This module's assertions are
updated to resolve against the current pin; the BUG-074 content this file
originally verified is unaffected (still present, minus the two literal
example sentences, inside v5.4 — see the dedicated v5.4 tests below).

Prompt-only fix for the meta-utterance-referent section (a matching CODE-
level guard for the BUG-077 catch-all-question class was added separately
in `agents/dialogue.py`'s `run()`, see that module's own `PROMPT_VERSION`
docstring) — actual model behavior on a live meta-complaint turn is out of
this offline pass's scope (would require a real Upstage call). What IS
deterministically, offline-verifiable: (1) the runtime pin resolves to
v5.4, (2) the loaded prompt content distinguishes patient self-disclosure
from a meta-utterance about the conversation/agent itself, explicitly
rejects the third-party-referent empathy phrasing the live repro
(`d2d9ba21`) produced, and requires acknowledging the repetition instead,
(3) v5.1's body is preserved byte-identical inside v5.2, and v5.2's body
is preserved byte-identical inside v5.3 (addition-only discipline,
mirroring `test_dialogue_self_referential_relief.py`'s existing
v5.1-pin-resolution test pattern), and (4) v5.4 removes the two literal
worked-example sentences that were reproduced verbatim live (BUG-078 /
CVR-055 finding 3) while preserving every other v5.3 line unchanged.
"""

from __future__ import annotations

from pathlib import Path

from src.agents.dialogue import PROMPT_VERSION
from src.prompts.loader import PromptLoader

AI_SERVER_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = AI_SERVER_ROOT / "prompts"


def test_prompt_version_pinned_v5_6() -> None:
    # BUG-079 / REV-022 §4 (2026-07-25): bumped v5.4 -> v5.5. Only the
    # "공감 캘리브레이션" section changed (condensed to a principle + one
    # safety-critical ban). BUG-085-follow-up (session `04cfe927`): bumped
    # v5.5 -> v5.6 (CVR-057 6-type table + meta-utterance section widened
    # with a third, capability/memory-complaint subtype). BUG-089
    # (session `2671d9fe`): bumped v5.6 -> v5.7 (addition-only — one new
    # "공감 캘리브레이션" bullet, meta-utterance sections untouched) —
    # every meta-utterance-section assertion this module makes below is
    # still satisfied, resolved via `PROMPT_VERSION`.
    assert PROMPT_VERSION == "v5.7"


def test_v5_4_prompt_resolves_and_keeps_meta_utterance_section() -> None:
    loader = PromptLoader(PROMPTS_DIR)
    content = loader.load_system_prompt("dialogue", PROMPT_VERSION)
    assert content, "dialogue v5.6 prompt loaded empty"

    # New section present.
    assert "메타-발화" in content

    # Referent-distinguishing directive present (self-disclosure vs
    # meta-utterance about the agent/conversation itself).
    assert "제3자" in content
    assert "왜 자꾸 물어봐" in content

    # The live repro's exact tone-deaf anti-pattern is named as forbidden,
    # not merely implied.
    assert "그런 말을 계속 들으시다니" in content

    # Empathy-reduction directive for this case (acknowledge + move on,
    # not the weight-proportional empathy calibration used for real
    # disclosures).
    assert "공감 절감" in content

    # v5.1's own content (self-referential-relief ban) is still present —
    # addition-only, not a rewrite.
    assert "다행" in content
    assert "공감 캘리브레이션" in content


def test_v5_1_body_preserved_byte_identical_inside_v5_2() -> None:
    """Addition-only guard: every line of v5.1 still appears, in order,
    somewhere inside v5.2 — the new section/changelog are pure insertions,
    never edits to existing v5.1 lines."""
    v51_lines = (PROMPTS_DIR / "dialogue" / "v5.1.system.md").read_text(
        encoding="utf-8"
    ).splitlines()
    v52_lines = (PROMPTS_DIR / "dialogue" / "v5.2.system.md").read_text(
        encoding="utf-8"
    ).splitlines()

    # Drop v5.1's own title/changelog blockquote (lines 1-73, see that
    # file) — v5.2 legitimately rewrites the title and prepends a new
    # changelog paragraph. Everything from "## 역할" onward must be an
    # exact ordered subsequence.
    body_start = next(i for i, line in enumerate(v51_lines) if line == "## 역할")
    v51_body = v51_lines[body_start:]

    it = iter(v52_lines)
    for line in v51_body:
        for candidate in it:
            if candidate == line:
                break
        else:
            raise AssertionError(
                f"v5.1 body line not found (in order) inside v5.2: {line!r}"
            )


def test_v5_2_body_preserved_byte_identical_inside_v5_3() -> None:
    """BUG-077: same addition-only guard, one version later — every line of
    v5.2 still appears, in order, somewhere inside v5.3."""
    v52_lines = (PROMPTS_DIR / "dialogue" / "v5.2.system.md").read_text(
        encoding="utf-8"
    ).splitlines()
    v53_lines = (PROMPTS_DIR / "dialogue" / "v5.3.system.md").read_text(
        encoding="utf-8"
    ).splitlines()

    body_start = next(i for i, line in enumerate(v52_lines) if line == "## 역할")
    v52_body = v52_lines[body_start:]

    it = iter(v53_lines)
    for line in v52_body:
        for candidate in it:
            if candidate == line:
                break
        else:
            raise AssertionError(
                f"v5.2 body line not found (in order) inside v5.3: {line!r}"
            )


def test_v5_4_keeps_indirect_meta_utterance_and_scope_boundary() -> None:
    """BUG-074 residual (v5.3-introduced, unaffected by the v5.4 example
    swap): the prompt still recognizes indirect repetition-complaint
    phrasing (not just direct "왜 자꾸 물어봐" style) and explicitly scopes
    the repeat-acknowledgment opener to turns that actually carry a
    meta-utterance (closing the observed plain-turn over-application)."""
    loader = PromptLoader(PROMPTS_DIR)
    content = loader.load_system_prompt("dialogue", PROMPT_VERSION)

    assert "아까도 말했잖아요" in content
    assert "적용 범위 경계" in content
    assert "평소와 같이 위 \"공감 캘리브레이션\"을 그대로 따른다" in content


def test_v5_4_keeps_catchall_question_prohibition() -> None:
    """BUG-077 item (A), unaffected by the v5.4 example swap: the prompt
    still explicitly forbids substituting the assigned target topic with a
    vague catch-all question (defense-in-depth alongside the code-level
    `target_mismatch` guard)."""
    loader = PromptLoader(PROMPTS_DIR)
    content = loader.load_system_prompt("dialogue", PROMPT_VERSION)

    assert "혹시 다른 증상이나 걱정되는 부분이 있으신가요" in content
    assert "막연한 범용 질문" in content


def test_v5_4_removes_anchored_worked_example_sentences() -> None:
    """BUG-078 / CVR-055 finding 3: the exact worked-example sentences the
    model reproduced verbatim live (`experiments/EXP-032_f1_reverify`
    iteration2, turns 6/8) are gone from the runtime-pinned prompt — the
    model has no single copyable sentence left to anchor on for this
    section. The section's MEANING (판별 기준/공감 절감 지시/안티패턴/적용
    범위 경계) survives via the other, still-present assertions above."""
    loader = PromptLoader(PROMPTS_DIR)
    content = loader.load_system_prompt("dialogue", PROMPT_VERSION)

    assert "같은 질문을 반복해서 불편하셨겠어요" not in content
    assert "같은 걸 다시 여쭤서 불편하셨겠어요" not in content
    # The forbidden anti-pattern quote is a DIFFERENT sentence and must
    # stay (it is explicitly labeled "do not do this", not a worked
    # example to copy) — its removal would be a scope overreach.
    assert "그런 말을 계속 들으시다니" in content


def test_v5_3_body_preserved_except_two_example_bullets_inside_v5_4() -> None:
    """Not addition-only (unlike every prior version bump in this file's
    history — see v5.4's own changelog note): every v5.3 body line must
    still appear, in order, inside v5.4, EXCEPT the two literal
    worked-example lines this fix intentionally removes."""
    v53_lines = (PROMPTS_DIR / "dialogue" / "v5.3.system.md").read_text(
        encoding="utf-8"
    ).splitlines()
    v54_lines = (PROMPTS_DIR / "dialogue" / "v5.4.system.md").read_text(
        encoding="utf-8"
    ).splitlines()

    _removed_bullets = {
        '- **예시(형태만 참고, 문구 암기 금지):** 환자: "없다니까 왜 자꾸 물어봐." → "같은',
        '  질문을 반복해서 불편하셨겠어요." 정도의 짧은 시인(제3자-지향 공감 문구 없음) 뒤,',
        '  다른 미수집 슬롯으로 자연스럽게 전환한다.',
        '- **예시(간접 언급, 형태만 참고, 문구 암기 금지):** 환자: "그거 아까도 말했잖아요." →',
        '  위 절과 동일하게 "같은 걸 다시 여쭤서 불편하셨겠어요." 정도의 짧은 시인(제3자-지향',
        '  공감 문구 없음) 뒤, 다른 미수집 슬롯으로 자연스럽게 전환한다.',
    }

    body_start = next(i for i, line in enumerate(v53_lines) if line == "## 역할")
    v53_body = [line for line in v53_lines[body_start:] if line not in _removed_bullets]

    it = iter(v54_lines)
    for line in v53_body:
        for candidate in it:
            if candidate == line:
                break
        else:
            raise AssertionError(
                f"v5.3 body line not found (in order) inside v5.4: {line!r}"
            )
