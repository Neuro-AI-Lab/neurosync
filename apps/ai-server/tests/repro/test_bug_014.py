"""BUG-014 repro/regression: `src.eval.f2_grounding._RISK_PHRASES` (ADR-014 v2
remediation code-enforced risk-lexicon filter) did not cover this project's
own already-established passive-SI/burdensomeness taxonomy (BUG-007/ADR-010),
and REV-008 (`discussion.md`) confirmed live occurrences of exactly the
missed phrasing variants in VP-003's actual conversation.

BUG-007's canonical anchor family (`docs/ai/prompts/safety_classifier/v2.system.md`
간접 표현 CTRS 하한표, restored per BUG-007's fix):
    "살고 싶지 않다", "사라지고 싶다", "없어지고 싶다", "죽고 싶다",
    "내가 없으면 다 편할 텐데", "사는 게 의미가 없다"

Pre-fix, `_RISK_PHRASES` covered 5 of these 6 anchors but had no phrase
matching "사는 게 의미가 없다" at all.

REV-008 (`discussion.md`, REV-008 rollback-adjudication section, item (a))
additionally documented THREE live VP-003 evidence quotes from this same
established family that were not caught by the pre-fix lexicon:
  - turn_5/9: "짐이 되기 싫어서" (burdensomeness ideation, same construct as
    "내가 없으면 다 편할 텐데")
  - turn_10/12: "살아서 뭐하나" -- REV-008's own words: "closely paraphrases
    the '사는 게 의미가 없다' anchor"
  - turn_11: "죽으면 편할 것 같다" (death-directed ideation, same family as
    "죽고 싶다")

BUG-014 fix (this revision): `_RISK_PHRASES` now adds stems for the
burdensomeness family ("짐이 되", "짐만 되", "부담이 되"), the meaninglessness
family ("사는 게 의미", "살아서 뭐하"), and standalone death-directed
ideation ("죽으면 편할"). See `src/eval/f2_grounding.py`'s `_RISK_PHRASES`
comment block for the full stem list and rationale.

Following this project's established repro-test convention (BUG-007, BUG-009,
BUG-011): these tests originally asserted the CURRENT (buggy) behavior --
i.e. they PASSED pre-fix, demonstrating the coverage gap. Per the BUG-007
precedent (`test_burden_ideation_phrase_now_has_rule_engine_backstop`), the
assertions below are now INVERTED (not weakened) to assert the fixed
behavior, so this file continues to serve as qa's concrete re-verification
path and becomes a permanent regression guard against this exact gap
resurfacing (the scenario EXP-005 re-runs VP-003 to check for -- 재발 = 0).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval.f2_grounding import (
    VERDICT_ACCEPTED,
    VERDICT_REJECTED_RISK_LEXICON,
    check_evidence,
)

# BUG-007/ADR-010's canonical anchor phrase, verbatim -- pre-fix, absent from
# _RISK_PHRASES entirely; post-fix, covered by the "사는 게 의미" stem.
_MISSING_CANONICAL_ANCHOR = "사는 게 의미가 없다"

# REV-008's three live-observed VP-003 quotes (attested variants of the same
# established taxonomy family) that the pre-fix lexicon did not catch.
_REV_008_MISSED_VARIANTS = [
    ("burdensomeness (turn_5/9 family)", "짐이 되기 싫어서 그래요."),
    ("meaninglessness paraphrase (turn_10/12)", "살아서 뭐하나 싶어요."),
    ("death-directed ideation (turn_11)", "죽으면 편할 것 같다는 생각이 들어요."),
]

# qa's additional exposure named in BUG-014 beyond REV-008's three named
# quotes -- a standalone occurrence of the death-directed phrasing that, in
# the actual VP-003 turn_11 artifact, happens to co-occur with the
# already-caught "사라지고 싶" phrase (so it did not leak in that specific
# run), but a quote containing *only* this phrasing would have.
_QA_EXTRA_EXPOSURE = "죽으면 편할 것 같다."


def _check(quote: str):
    return check_evidence(
        "utterance", "turn_x", quote, chunk_texts={}, utterances={"turn_x": quote},
        domain="depression",
    )


class TestBug014RiskLexiconUndercoverage:
    def test_canonical_bug007_anchor_phrase_now_rejected(self) -> None:
        """BUG-014 fix: `_RISK_PHRASES` now rejects BUG-007/ADR-010's own
        canonical anchor "사는 게 의미가 없다" (via the "사는 게 의미" stem).

        Renamed from `test_canonical_bug007_anchor_phrase_currently_not_rejected`
        (assertion inverted, not weakened) -- that test's own docstring
        anticipated this exact outcome ("If this fails, the anchor may
        already have been added; update error.md and invert this
        assertion")."""
        quote = f"요즘 {_MISSING_CANONICAL_ANCHOR}는 생각이 들어요."
        v = _check(quote)
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON, (
            "BUG-014 regression: the canonical BUG-007 anchor "
            f"{_MISSING_CANONICAL_ANCHOR!r} is accepted again "
            f"(verdict={v.verdict!r}). The '사는 게 의미' stem may have been "
            "removed from _RISK_PHRASES."
        )

    @pytest.mark.parametrize("label,quote", _REV_008_MISSED_VARIANTS)
    def test_rev008_live_observed_variant_now_rejected(
        self, label: str, quote: str
    ) -> None:
        """BUG-014 fix: each of REV-008's three live-observed VP-003 evidence
        quotes (established taxonomy family, different surface phrasing) is
        now rejected, not accepted -- closing the exact live violation
        pattern EXP-005 re-runs VP-003 to verify has zero recurrence for.

        Renamed from `test_rev008_live_observed_variant_currently_not_rejected`
        (assertion inverted, not weakened)."""
        v = _check(quote)
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON, (
            f"BUG-014 regression [{label}]: quote {quote!r} is accepted "
            f"again (verdict={v.verdict!r}). A burdensomeness/meaninglessness/"
            "death-directed stem may have been removed from _RISK_PHRASES."
        )

    def test_qa_extra_exposure_now_rejected(self) -> None:
        """BUG-014 fix: qa's additional standalone-phrasing exposure (the
        death-directed "죽으면 편할 것 같다" quote in isolation, not just
        co-occurring with an already-caught passive-SI phrase) is now
        rejected via the "죽으면 편할" stem."""
        v = _check(_QA_EXTRA_EXPOSURE)
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON, (
            f"BUG-014 regression: qa's exposure quote {_QA_EXTRA_EXPOSURE!r} "
            f"is accepted again (verdict={v.verdict!r}). The '죽으면 편할' "
            "stem may have been removed from _RISK_PHRASES."
        )


# ── REV-009 artifact replay (Attack 1) ────────────────────────────────────
#
# REV-009 replayed the SHIPPED, real EXP-004 VP-003 artifacts (not synthetic
# quotes) against the pre-fix lexicon and found 10/13 (run1: 10, run2: 3)
# broader-taxonomy-flagged evidence quotes rejected, 4 surviving (all in
# run1: turn_5, turn_9, turn_10, turn_12). This section re-runs that exact
# replay against the post-fix lexicon as a permanent regression guard tied
# to the authoritative artifact data, not just the hand-picked quotes above.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SIM_DIR = _REPO_ROOT / "docs" / "ai" / "simulation_results" / "VP-003"
_RUN1_PATH = _SIM_DIR / "VP-003_20260708_120459_domain_inference.json"
_RUN2_PATH = _SIM_DIR / "VP-003_20260708_120509_domain_inference.json"

# REV-009 Attack 1's table: turn_0/1 (passive SI), turn_2/3/6/11 (passive SI
# "사라지고 싶"), turn_5/9 (burdensomeness), turn_10/12 (meaninglessness) --
# 10 of run1's 13 quotes. turn_4/7/8 are NOT part of the broader taxonomy
# (no SI/burden/meaninglessness content) and are deliberately excluded, so
# this replay also implicitly guards against over-blocking those three.
_RUN1_BROAD_TAXONOMY_TURNS = frozenset(
    {"turn_0", "turn_1", "turn_2", "turn_3", "turn_6", "turn_11", "turn_5", "turn_9",
     "turn_10", "turn_12"}
)
# REV-009 Attack 1: run2's 3/3 quotes are all passive SI, all broad-taxonomy.
_RUN2_BROAD_TAXONOMY_TURNS = frozenset({"turn_0", "turn_1", "turn_2"})


def _load_artifact(path: Path) -> tuple[dict, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["domain_candidates"][0], data["utterances"]


class TestBug014Rev009ArtifactReplay:
    """Replays REV-009 Attack 1 against the real VP-003 run1+run2 artifacts.

    Target (REV-009/BUG-014's stated goal): 13/13 of the broader-taxonomy
    quotes caught, 0 surviving. Pre-fix this class would report 9/13 caught,
    4 surviving (turn_5, turn_9, turn_10, turn_12 of run1)."""

    @pytest.mark.skipif(
        not (_RUN1_PATH.exists() and _RUN2_PATH.exists()),
        reason="EXP-004 VP-003 simulation artifacts not present in this checkout",
    )
    def test_all_broad_taxonomy_quotes_caught_zero_survivors(self) -> None:
        survived: list[tuple[str, str, str]] = []
        caught = 0
        for path, broad_turns in (
            (_RUN1_PATH, _RUN1_BROAD_TAXONOMY_TURNS),
            (_RUN2_PATH, _RUN2_BROAD_TAXONOMY_TURNS),
        ):
            candidate, utterances = _load_artifact(path)
            for ev in candidate["evidence"]:
                if ev["source_id"] not in broad_turns:
                    continue
                v = check_evidence(
                    "utterance", ev["source_id"], ev["quote"],
                    chunk_texts={}, utterances=utterances, domain=candidate["domain"],
                )
                if v.verdict == VERDICT_REJECTED_RISK_LEXICON:
                    caught += 1
                else:
                    survived.append((path.name, ev["source_id"], ev["quote"]))

        total = len(_RUN1_BROAD_TAXONOMY_TURNS) + len(_RUN2_BROAD_TAXONOMY_TURNS)
        assert survived == [], (
            f"BUG-014 regression: {len(survived)}/{total} broad-taxonomy "
            f"quotes still ship as accepted evidence: {survived}"
        )
        assert caught == total == 13

    def test_run1_non_taxonomy_turns_remain_accepted(self) -> None:
        """Guard against over-blocking: turn_4/7/8 (help-seeking futility,
        medication/doctor-avoidance content -- no SI/burden/meaninglessness
        wording) must remain accepted, not swept up by the new stems."""
        if not _RUN1_PATH.exists():
            pytest.skip("EXP-004 VP-003 run1 artifact not present in this checkout")
        candidate, utterances = _load_artifact(_RUN1_PATH)
        non_taxonomy_turns = {"turn_4", "turn_7", "turn_8"}
        for ev in candidate["evidence"]:
            if ev["source_id"] not in non_taxonomy_turns:
                continue
            v = check_evidence(
                "utterance", ev["source_id"], ev["quote"],
                chunk_texts={}, utterances=utterances, domain=candidate["domain"],
            )
            assert v.verdict != VERDICT_REJECTED_RISK_LEXICON, (
                f"over-blocking regression: non-taxonomy turn {ev['source_id']!r} "
                f"({ev['quote']!r}) is now rejected as risk-lexicon content"
            )


# ── QA re-verification residual (REV-009 Attack 4 / BUG-014 "GATE: FAIL") ──
#
# qa's narrow re-gate on `feat/f2-v2-remediation` (error.md BUG-014
# "### QA re-verification") independently confirmed the original 4/4 named
# quotes fixed, then found one adjacent residual: the "better off dead" via
# 낫다 ("preferable") construct family -- "죽는 게 낫다"/"차라리 죽는 게
# 나을 것 같다" -- survived as accepted evidence. qa's own three synthetic
# phrasings (verified directly against `check_evidence` in that gate) are
# reused here verbatim as the regression fixture.
_QA_BETTER_OFF_DEAD_VARIANTS = [
    ("차라리 + 나을 (ㅅ-dropped, vowel ending)", "차라리 죽는 게 나을 것 같아요."),
    (
        "낫다는 (ㅅ-preserved, comparative clause)",
        "이렇게 힘들게 사느니 죽는 게 낫다는 생각이 들어요.",
    ),
    ("낫겠다 (ㅅ-preserved, prospective)", "죽는 게 낫겠다 싶어요."),
]


class TestBug014QaReverificationResidual:
    """BUG-014 fix (this revision): `_RISK_PHRASES` now adds the "죽는 게
    낫"/"차라리 죽" stems, closing the residual REV-009 Attack 4 gap qa's
    re-gate flagged as GATE: FAIL. Per this project's established repro-test
    convention, these assertions target the fixed (rejected) behavior
    directly -- there is no separate pre-fix demonstration commit for this
    specific residual since it was caught and closed within the same gate."""

    @pytest.mark.parametrize("label,quote", _QA_BETTER_OFF_DEAD_VARIANTS)
    def test_qa_synthetic_phrasing_now_rejected(self, label: str, quote: str) -> None:
        v = _check(quote)
        assert v.verdict == VERDICT_REJECTED_RISK_LEXICON, (
            f"BUG-014 regression [{label}]: quote {quote!r} is accepted again "
            f"(verdict={v.verdict!r}). The '죽는 게 낫'/'차라리 죽' stem may "
            "have been removed from _RISK_PHRASES."
        )

    def test_panic_idioms_still_accepted_both_ways(self) -> None:
        """Disjointness sanity, both ways: the new stems must not have swept
        up the ISS-046 panic fear-of-dying idiom carve-out (SM-07a/SM-07b),
        and the panic idioms themselves must not contain the new stems'
        substrings (structural guarantee also asserted directly against the
        lexicons in test_f2_grounding.py::test_risk_and_panic_idiom_lexicons_are_disjoint)."""
        panic_quote = (
            "심장이 미친듯이 뛰고 숨을 못 쉬어서 응급실에 실려간 적이 있어요. "
            "그때 정말 죽는 줄 알았어요."
        )
        v = _check(panic_quote)
        assert v.verdict == VERDICT_ACCEPTED, (
            f"over-blocking regression: panic idiom quote {panic_quote!r} is "
            f"now rejected (verdict={v.verdict!r}) -- the new '죽는 게 낫'/"
            "'차라리 죽' stems may collide with '죽는 줄 알았'."
        )
