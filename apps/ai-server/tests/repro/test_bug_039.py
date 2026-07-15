"""BUG-039 regression tests — AUDIT-C v2 item 2's secondary ("기타 술")
track is now rendered into the LLM-facing prompt.

Filed: `error.md` BUG-039. `docs/ai/audit_c_korean_research.md` §3.2 /
`CVR-018` Q2(c) / `ADR-034` decision 2: the sourced [별지 제15호의3서식]
form bifurcates AUDIT-C item 2 into a native 소주-bottle track and a
glasses-based "기타 술" (other-drinks) track with its own explicit
beer/makgeolli/draft-beer unit-conversion table, adopted "specifically
because it structurally eliminates the Western/soju unit-conversion
confound CVR-017 Finding 4 live-confirmed under v1's Western-unit-only
item 2" (`apps/ai-server/src/scoring/item_bank.py` `ScaleItem` docstring,
and `AUDIT_C_V2_PROVENANCE`).

**Fix (this file, post-BUG-039):** `build_item_prompt`/`SurveyAnswerLLM.
_build_prompt` (`tests/simulation/survey_answer_llm.py`) now render BOTH
tracks + the conversion note whenever an item carries
`secondary_response_anchors` — presentation-only, since both tracks' anchor
values already sit on the same 0-4 point scale (each label carries its own
point value, e.g. "1병 이하(1점)" / "3~4잔(1점)" both = 1 point), so no
parsing/scoring change was needed. `item_bank.py` also gained a new sourced
`ScaleItem.primary_track_label` field ("소주 트랙", verbatim from
`docs/ai/audit_c_korean_research.md` §3.2's own table row) so the primary
track can be labeled without inventing new Korean text in the harness.

This file used to lock in the CURRENT (defective) behavior as a regression
test; `test_rendered_prompt_omits_the_secondary_track_bug_039` has been
INVERTED (renamed `test_rendered_prompt_now_includes_the_secondary_track_
bug_039`) to instead assert the fixed behavior. The other two tests (data-
model precondition, signature check) are updated to match: the signature
check is inverted (the secondary-track keywords now DO exist), and a new
golden test pins the exact byte-for-byte item-2 dual-track prompt.
"""

from __future__ import annotations

import inspect

from src.scoring.item_bank import get_item_bank
from tests.simulation.survey_answer_llm import build_item_prompt


def test_audit_c_item2_secondary_track_is_populated_on_the_item() -> None:
    """Sanity precondition: the data model DOES carry the secondary track
    (unchanged by the BUG-039 fix -- the qa byte-fidelity gate for CVR-018
    binding condition 8 passed independently, and now the primary track
    also carries its own sourced label).
    """
    item2 = get_item_bank("AUDIT-C").items[1]
    assert item2.primary_track_label == "소주 트랙"
    assert item2.secondary_track_label == "기타 술 트랙"
    assert item2.secondary_response_anchors is not None
    assert set(item2.secondary_response_anchors) == {0, 1, 2, 3, 4}
    assert item2.secondary_track_conversion_note_ko is not None


def test_rendered_prompt_now_includes_the_secondary_track_bug_039() -> None:
    """BUG-039 fix: the prompt actually sent to the (simulated) patient for
    AUDIT-C v2 item 2 now contains BOTH the primary soju-track anchors AND
    the secondary "기타 술" track's content (label, anchors, conversion
    note) -- matching item 2's own `text_ko`, which promises "the two
    tracks below" (두 곳 중).
    """
    item2 = get_item_bank("AUDIT-C").items[1]
    assert "두 곳 중" in item2.text_ko  # the item text's own dual-track promise

    prompt = build_item_prompt(
        text_ko=item2.text_ko,
        response_min=item2.response_min,
        response_max=item2.response_max,
        response_anchors=item2.response_anchors,
        instruction_ko=None,  # AUDIT-C v2 entry-level instruction_ko is None
        primary_track_label=item2.primary_track_label,
        secondary_track_label=item2.secondary_track_label,
        secondary_response_anchors=item2.secondary_response_anchors,
        secondary_track_conversion_note_ko=item2.secondary_track_conversion_note_ko,
    )

    # Primary (soju) track anchors ARE present.
    assert "반병 이하(0점)" in prompt
    assert "2.5병 이상(4점)" in prompt

    # ...and now the secondary track's content is present too -- the
    # previously-documented defect is fixed.
    assert item2.secondary_track_label is not None
    assert item2.secondary_track_label in prompt
    assert item2.secondary_response_anchors is not None
    for label in item2.secondary_response_anchors.values():
        assert label in prompt
    assert item2.secondary_track_conversion_note_ko is not None
    assert item2.secondary_track_conversion_note_ko in prompt


def test_golden_item2_dual_track_prompt_byte_exact() -> None:
    """Golden test pinning the exact, byte-for-byte AUDIT-C v2 item-2
    dual-track prompt -- guards against silent future drift in either the
    rendering format or the sourced item-bank strings it's built from.
    """
    item2 = get_item_bank("AUDIT-C").items[1]
    prompt = build_item_prompt(
        text_ko=item2.text_ko,
        response_min=item2.response_min,
        response_max=item2.response_max,
        response_anchors=item2.response_anchors,
        instruction_ko=None,
        primary_track_label=item2.primary_track_label,
        secondary_track_label=item2.secondary_track_label,
        secondary_response_anchors=item2.secondary_response_anchors,
        secondary_track_conversion_note_ko=item2.secondary_track_conversion_note_ko,
    )
    expected = "\n".join(
        [
            "문항: 술을 마시는 날은 보통 어느 정도 마십니까? (아래의 두 곳 중 주로 드시는 술을 "
            "선택하여 한 곳에 표시해 주시면 됩니다.)",
            "소주 트랙 응답 척도: 0: 반병 이하(0점) / 1: 1병 이하(1점) / 2: 1.5병정도(2점) / "
            "3: 2병정도(3점) / 4: 2.5병 이상(4점)",
            "기타 술 트랙 응답 척도: 0: 1~2잔(0점) / 1: 3~4잔(1점) / 2: 5~6잔(2점) / "
            "3: 7~9잔(3점) / 4: 10잔 이상(4점)",
            "양주·와인은 각각의 술잔; 막걸리는 한 사발=1잔; 맥주는 캔맥주 1캔 또는 작은 병맥주 "
            "1병=1잔, 생맥주 500cc=1.3잔",
            "위 두 트랙 중 실제 마시는 술 종류에 해당하는 트랙을 선택하여, 그 트랙의 응답 척도 "
            "중 당신의 상태를 가장 잘 나타내는 숫자 하나만 답하세요 (0-4).",
        ]
    )
    assert prompt == expected


def test_build_item_prompt_signature_now_has_secondary_track_parameters() -> None:
    """Structural confirmation, inverted from the pre-fix version: every
    caller now CAN pass secondary-track content through `build_item_prompt`
    -- this is a capability gained by the shared prompt-construction
    function, not a call-site-only patch.
    """
    params = set(inspect.signature(build_item_prompt).parameters)
    assert "secondary_response_anchors" in params
    assert "secondary_track_label" in params
    assert "secondary_track_conversion_note_ko" in params
    assert "primary_track_label" in params


def test_item_without_secondary_track_renders_byte_identical_to_pre_fix() -> None:
    """Non-regression: an item that carries no secondary track (every item
    except AUDIT-C v2 item 2, e.g. PHQ-9) must render EXACTLY as before --
    the dual-track branch is additive, never a behavior change for any
    existing single-track item."""
    phq9_item1 = get_item_bank("PHQ-9").items[0]
    prompt_without_optional_kwargs = build_item_prompt(
        text_ko=phq9_item1.text_ko,
        response_min=phq9_item1.response_min,
        response_max=phq9_item1.response_max,
        response_anchors=phq9_item1.response_anchors,
        instruction_ko=None,
    )
    prompt_with_explicit_none_kwargs = build_item_prompt(
        text_ko=phq9_item1.text_ko,
        response_min=phq9_item1.response_min,
        response_max=phq9_item1.response_max,
        response_anchors=phq9_item1.response_anchors,
        instruction_ko=None,
        primary_track_label=phq9_item1.primary_track_label,
        secondary_track_label=phq9_item1.secondary_track_label,
        secondary_response_anchors=phq9_item1.secondary_response_anchors,
        secondary_track_conversion_note_ko=phq9_item1.secondary_track_conversion_note_ko,
    )
    assert prompt_without_optional_kwargs == prompt_with_explicit_none_kwargs
    assert "응답 척도:" in prompt_without_optional_kwargs
    assert "트랙" not in prompt_without_optional_kwargs
