"""BUG-007 repro: safety_classifier v2 prompt silently drops indirect-SI
calibration anchors present in v1, with no rule-engine backstop for one of
them.

`docs/ai/prompts/safety_classifier/v1.system.md`'s "간접 표현 CTRS 하한"
table (lines 34-38) has:
  | "살고 싶지 않다", "사라지고 싶다", "없어지고 싶다", "죽고 싶다" | 3 이상 |
  | "내가 없으면 다 편할 텐데", "사는 게 의미가 없다"           | 3 이상 |

`docs/ai/prompts/safety_classifier/v2.system.md` (PLAN-2026-W28 C1,
prompt_redesign_v3.md §2.1) keeps only:
  | "살고 싶지 않다", "사라지고 싶다", "죽고 싶다" | 최소 3단계 |

"없어지고 싶다" is dropped from the prompt row but still has a rule-engine
backstop (`_HIGH_KEYWORDS`), so LLM-only coverage loss there is mitigated
by defense-in-depth. The entire second row -- "내가 없으면 다 편할 텐데"
(perceived-burdensomeness ideation) and "사는 게 의미가 없다" -- is gone
with zero mention in prompt_redesign_v3.md's §2.1 table, its changelog
note ("방향 표기 수정"), ADR-006, or ADR-007. Nothing documents this as an
intentional removal; it is indistinguishable from a silent drop of a
crisis-detection calibration anchor -- the exact failure mode critic's
REV-002 status-update watch item asked qa to escalate on.

"사는 게 의미가 없다" retains partial rule-engine coverage via the
"의미가 없" MEDIUM keyword (matches the CTRS>=3/medium floor v1 assigned).
"내가 없으면 다 편할 텐데" has no rule-engine coverage at all -- for that
phrase, prompt content is the *only* line of defense, and it was cut.
"""

from __future__ import annotations

from pathlib import Path

from src.agents.safety_classifier import _CRITICAL_KEYWORDS, _HIGH_KEYWORDS, _MEDIUM_KEYWORDS

_PROMPTS_DIR = (
    Path(__file__).resolve().parents[4] / "docs" / "ai" / "prompts" / "safety_classifier"
)


def _read(version: str) -> str:
    return (_PROMPTS_DIR / f"{version}.system.md").read_text(encoding="utf-8")


V1 = _read("v1")
V2 = _read("v2")

_DROPPED_V1_ANCHORS = [
    "내가 없으면 다 편할 텐데",
    "사는 게 의미가 없다",
]


def test_v1_fixture_sanity() -> None:
    """The phrases really are in v1 -- fixture isn't stale."""
    for phrase in _DROPPED_V1_ANCHORS:
        assert phrase in V1, f"test fixture stale: {phrase!r} missing from v1 itself"


def test_burden_ideation_anchors_survive_in_v2() -> None:
    """BUG-007: v1's burden-ideation calibration row must survive in v2
    (verbatim or in clearly-equivalent substance), per the same
    "no rule deleted" policy already applied to the 7 핵심 규칙
    (prompt_redesign_v3.md §2.1, REV-002 #2). Currently FAILS -- this is
    the repro, not a pre-existing regression test.
    """
    for phrase in _DROPPED_V1_ANCHORS:
        assert phrase in V2, (
            f"safety_classifier v2 silently dropped v1 calibration anchor: {phrase!r}"
        )


def test_burden_ideation_phrase_now_has_rule_engine_backstop() -> None:
    """BUG-007 fix: the deterministic rule engine now catches "내가 없으면
    다 편할 텐데" independently of the LLM prompt.

    Renamed from `test_burden_ideation_phrase_has_no_rule_engine_backstop`
    (assertion inverted, not weakened) as part of the BUG-007 fix. That
    test's own docstring anticipated this exact outcome: "If this test
    starts failing, the rule engine has gained coverage." `_MEDIUM_KEYWORDS`
    in `src/agents/safety_classifier.py` now carries "내가 없으면" /
    "내가없으면" (added as defense-in-depth per BUG-007's proposed fix),
    which is by construction a substring of this phrase -- any keyword
    granular enough to close this gap necessarily is. This test now
    asserts the positive (coverage exists) instead of the negative
    (coverage is absent); it is a stricter regression guard than before,
    not a weaker one -- it fails if the backstop keyword is ever removed
    without the prompt-side anchor being restored too.
    """
    phrase = "내가 없으면 다 편할 텐데"
    all_keywords = [k for k, _ in _CRITICAL_KEYWORDS + _HIGH_KEYWORDS + _MEDIUM_KEYWORDS]
    matched = [kw for kw in all_keywords if kw.replace(" ", "") in phrase.replace(" ", "")]
    assert matched != [], (
        f"expected a rule-engine keyword to match {phrase!r} (BUG-007 backstop), found none"
    )
