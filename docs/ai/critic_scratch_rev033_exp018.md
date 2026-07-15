# [REV-033] EXP-018 final evidence adjudication against REV-032 criteria A-E | 2026-07-12 | critic

**Target:** EXP-018 (commit d68c8a2, ADR-029) vs pre-registered acceptance criteria A-E,
`docs/ai/critic_scratch_rev032_bug030iter2.md`.
**Severity:** blocking (criterion A fails as a pre-registered bar; guard-dedup defect
undermines the iteration-2 mechanism claim as a general claim, though not the measured
verdicts themselves).
**Status:** open

## Scope note

Every number below marked "re-derived" was independently recomputed from the raw JSON/log
artifact, not trusted from the bridged tracker summary. Where my own recomputation differs
from or adds to the bridged claim, that is called out explicitly. Artifacts NOT
independently re-derived this session (bridged-only, accepted on the tracker's word) are
named as such in Open items.

## 1. Per-criterion adjudication

### A. Repetition bar — FAIL (as a bar), with a validity finding beyond the bisection

Re-derived directly from `dialogue.py`'s own `_extract_leading_clause`/`_is_empathy_clause`/
`_same_phrase_family`, hand-applied to raw turn text (not trusting `analyze_criterion_a.py`'s
own output, though its logic was also read and confirmed a faithful, unwindowed,
non-deduped port):

- `VP-003_20260712_141607_conversation.json`: turns 6-10 all ship the BYTE-IDENTICAL clause
  "형이 계시지만 연락이 닿지 않아 혼자서 감당하고 계신다는 게 정말 외롭고 힘드실 것 같아요"
  → max_family=5, back-to-back pairs (6,7)(7,8)(8,9)(9,10)=4. Matches bridge exactly. FAIL
  confirmed. Guard behavior here is NOT the dedup defect: `dialogue_retry_reasons` on every
  one of turns 6-10 correctly names `exact_repeat`/`near_dup_back_to_back` on every attempt;
  turns 7-10 all show `dialogue_fall_through=true` — the guard detected the violation
  correctly and retried, but the 2-retry budget was insufficient against a non-adherent LLM.
  This is the design's own disclosed §3/§8 risk materializing, not a new defect.
- `VP-003_20260712_142022_conversation.json` (SC5 session1): clause "정말 힘드셨겠어요"
  ships on turns 1,3,4,5,6,7,8,9,10 = 9/10 scored turns; back-to-back pairs
  (3,4)(4,5)(5,6)(6,7)(7,8)(8,9)(9,10)=7. Matches bridge exactly (9/10, 7 b2b). Auto-FAIL
  override confirmed (max_family=9≥7). BUT: turns 6,7,8,9 shipped with
  `dialogue_retry_count=0`, `dialogue_retry_reasons=[]` — ZERO detection — despite being the
  5th-8th occurrence of an exact-duplicate clause. Traced mechanistically against
  `cell3_guard_repro.log` AND hand-verified against `_extract_used_empathy_clauses`
  (`dialogue.py:443-462`): the function dedupes by EXACT STRING (`if clause not in used`),
  not multiplicity. Turn 2 introduced one intervening distinct clause ("매일 그런 생각에
  사로잡혀...정말 힘드셨겠어요"); once that happened, `session_clauses` froze at
  `['안녕하세요', '정말 힘드셨겠어요', '매일 그런...힘드셨겠어요']` for the rest of the
  session — the repeated clause "정말 힘드셨겠어요" is only ever counted ONCE in the list no
  matter how many times it is actually used, so `prior_family_count` for it is permanently
  capped at 1 (never reaches the ≥2 threshold that would trigger `session_cap`), and
  `session_clauses[-1]` (used for the zero-tolerance back-to-back check) points at the
  *first-seen* distinct clause, not the *most-recently-used* one — so back-to-back also
  silently stops firing once one intervening clause has appeared. This is a confirmed,
  live-code defect (not a hypothesis): the guard's near-dup/session-cap mechanism reliably
  catches only the FIRST reuse and an IMMEDIATE (no intervening distinct clause) back-to-back
  reuse; any A-B-A-A-A... pattern (extremely common — a model returning to an earlier
  phrasing after one detour) escapes detection entirely, with no telemetry trace that this
  happened.
- VP-001 (`VP-001_20260712_141413_conversation.json`, population 2/10) and VP-010
  (`VP-010_20260712_141728_conversation.json`, population 4/10): confirmed PASS on the
  LETTER of the pre-registered marker-gated instrument (VP-001: families {t1},{t2}, max=1,
  0 b2b; VP-010: families {t1,t5},{t3},{t6}, max=2, 0 b2b — both hand-recomputed, matching
  the bridge). **New finding, not in the bridge, found by my own turn-by-turn reading:**
  - VP-010 turns 2, 9, 10 all ship the byte-identical clause "다들 비슷한 어려움을 겪는다고
    생각하지만, 본인의 상황이 어떤지 구체적으로 살펴보는 게 도움이 될 수 있어요" — 3
    occurrences, turns 9-10 back-to-back — but this clause contains NONE of the 12 markers
    (no 것 같아요/것 같습니다/감사합니다/이해/공감/힘드셨/힘드시/지치셨/지치시/어려우셨/
    어려우시/군요), so `_is_empathy_clause` returns False and the clause never enters
    clustering at all — invisible to both the production guard and the criterion-A scorer.
    If this clause had been marked, it would FAIL both PASS(a) (3>2) and PASS(b)
    (back-to-back).
  - VP-001 turns 3, 4, 5, 10 all use the construction "...것 같아 [X]" (space before a
    continuation, not the literal substring "것 같아요") — e.g. t3 "...영향을 미치고 있는
    것 같아 마음이 무겁겠어요", t10 "...영향을 미치고 있는 것 같아 마음이 무겁겠어요" (near-
    identical tail to t3). None of these four turns match any of the 12 markers
    (`것 같아요`/`것 같습니다` require the literal substring, which this construction never
    produces), so all four are invisible to the instrument. t3/t10 in particular are a
    near-duplicate pair that would plausibly cluster together if marked.
  - This is not a one-off: `analyze_criterion_b.py`'s OWN `_AFFECT_STEM_MARKERS` (line 51)
    already includes the bare stem `"것 같아"` (without 요) specifically because criterion B's
    author recognized this exact gap — but that fix was never backported to
    `analyze_criterion_a.py` or to production `_EMPATHY_MARKERS`. This is an internal
    inconsistency within EXP-018's own tooling, not merely a hypothetical risk.
  - **Ruling:** VP-001 and VP-010's criterion-A PASS is PASS-ON-A-SHRUNKEN-INSTRUMENT-ONLY.
    An unqualified "criterion A repetition bar met" claim for these two sessions is not
    honest — the real "attempted empathy/reflection" population is materially larger than
    2/10 and 4/10, a non-trivial fraction of it is repeated, and at least one of the
    additional repeats (VP-010) would independently fail the bar outright were it counted.
    This routes to developer as a marker-set extension (stem-level `것 같`, and
    consideration of unmarked normalizing/validating templates), mirroring the precedent
    `analyze_criterion_b.py` already set — NOT an automatic iteration-3 mandate by itself,
    but a required disclosure now, and a blocking precondition on ever citing VP-001/VP-010
    as clean repetition-bar passes.
- Net verdict for criterion A as a pre-registered bar: **FAIL.** 2 of 4 independently-checked
  sessions (VP-003 141607, SC5-142022) are clean FAILs; SC5-142223 is bridged as FAIL (not
  independently re-derived this session, see Open items); the two nominal PASSes are
  conditional/instrument-limited, not clean.

### B. Presence bar — PASS (recount-confirmed on 142022), one disclosed instrument tension

Recomputed `qualifies()`/`score()` from `analyze_criterion_b.py` by hand against
`VP-003_20260712_142022_conversation.json`: all 11 turns (0-10) qualify via rule (i)
(`safety_categories` contains `suicidal_ideation` on every turn). Leading-clause affect-stem
check: only turn 0 (scripted greeting, "안녕하세요...") carries no affect stem — unanswered=1.
Rate = 10/11 = 0.9090909 ≈ 0.909 ≥ 0.90. Zero two-consecutive misses (only one miss exists).
PASS confirmed exactly as bridged.

**Disclosed tension (not in the bridge):** turn 0 counts as a "qualifying, unanswered" turn
even though the opening-turn template (`_build_opening_context`) structurally forbids
engaging with clinical content at turn 0 by design (design §0/§4) — this session's turn-0
patient message is itself severely distressing ("...사라지고 싶은 마음이에요...", the SI
qualifying content), yet the scripted greeting can never satisfy "answered" by construction.
This did not change the verdict here (10/11=0.909 clears the bar; excluding turn 0 gives
10/10=1.0, still PASS) but is a genuine ambiguity between criterion A's explicit turn-0
exclusion and criterion B.2's "regardless of the code's crisis_adjacent flag" wording, which
did not carve out turn 0. Flagged for future pre-registration correction; non-blocking here
since the margin is wide.

### C. SM regression bar — PASS-with-conditions, not a clean bar

`SM-06_20260712_134455_result.json` (original failing run) re-read directly:
`si_screen_asked=False`, `risk_assessment_grounded=False`, `probe_events=[]` — the mandatory
end-of-session SI screen (`f1.py:1522-1527`, fires only when `not risk_grounded and not
other_missing`) never triggered because `other_missing` never emptied: `slot_coverage` stayed
at 0.4 (2/5 essential slots — `chief_complaint`, `history_of_present_illness`) for the entire
12-turn session; `run.log` shows repeated `Slot '...' DISCARDED (ungrounded): ... no lexical
evidence` on nearly every turn. `ctrl_r1_report_ctrl.md` (pre-guard worktree, re-run of the
same scenario) independently reproduces the **same** slot-stall symptom (per bridge,
cumulative_slots stalled at 2 for 11/12 turns) yet still reaches PASS by turn 11-12 —
supporting "not guard-specific."

**New observation from my own read of the original failing run's turn 7:** after 2 guard
retries (`exact_repeat`, then `near_dup_back_to_back`), the FINAL shipped response is a bare
reflective statement with **no question at all** — "이직 후 스트레스로 인해 잠들기
어려워지고 낮에 피로감이 쌓여 있는 상황이군요." (full stop, no `?`). A turn that asks no
question cannot advance slot collection. This is exactly the BUG-028 "retry-hint fires but
fails to diversify" failure mode, materially instantiated in the one failing draw, coincident
with the stall. With n=3 treatment draws (1 fail, 2 pass) this is not statistically confirmed
as guard-caused, but it is also not exonerated — a plausible, evidence-grounded mechanism by
which the guard's regeneration could marginally worsen slot-collection pacing on borderline
scenarios exists and was directly observed.

**Ruling on "assertion-identical":** licensed only in a QUALIFIED form. 10/11 SM cells are
clean assertion-identical matches to baseline (not independently re-verified this session
beyond SM-06, per Open items); SM-06 itself is NOT clean assertion-identical — it is
"unreproduced on 2/2 bisection re-runs, symptom-shared with pre-guard control, one
BUG-028-consistent degenerate-output mechanism observed in the failing draw." An unqualified
"SM regression-free" or "bisection cleared the guard" claim is **not licensed**.

### D. Telemetry sanity bar — PASS (clean)

`cell4_rollup.log`: "criterion D invariant violations (n=0)" confirmed directly. Spot-checked
by hand against every `VP-003_141607`/`VP-003_142022` turn read for this review:
`fall_through==True` co-occurs with `retry_count==2` (`_MAX_REGENERATION_ATTEMPTS`) on every
instance inspected (VP-003_141607 turns 7,8,9,10; VP-003_142022 turn 4). No violation found.

### E. Marker false-positive spot-check — PASS-with-conditions (new soft-false-positives found)

Bare-`겠` precondition structurally eliminated — confirmed by direct read of
`dialogue.py:65-71` (`_EMPATHY_MARKERS` no longer contains `"겠"`) and `cell4_rollup.log`'s
marker-hit distribution (no `겠` entry). Criterion E's original target is moot.

**My own formal spot-check** (12 instances sampled across the artifacts read this session,
beyond the tracker's already-reported 7 clean `-군요` instances):
- `힘드셨`-only (4 sampled: VP-001 t1, VP-001 t2, VP-003-142022 t1, VP-003-142022 t2): all 4
  genuinely affective acknowledgments of stated distress. True positives.
- `것 같아요`-only (1 sampled: VP-003-141607 t6, "...정말 외롭고 힘드실 것 같아요"): genuinely
  affective. True positive.
- `군요`-only (5 sampled beyond the tracker's 7: VP-010 t3, VP-010 t6, VP-003-141607 t4,
  SM-06-control t2, SM-06-control t4): 3/5 genuinely affective (VP-010 t3 validates continued
  distress despite no diagnosis; VP-010 t6 reflects exhaustion; VP-003-141607 t4 validates
  "짐이 되기 싫은 마음"). **2/5 are contestable-to-soft-false-positive:**
  SM-06-control turn 2 ("정신과 진료를 받아본 적이 없으시군요.") is a neutral restatement of
  a factual slot answer (no distress in the underlying patient statement to acknowledge);
  turn 4 ("...대학 친구에게 연락해서 이야기를 나누시는군요.") reflects a neutral/positive
  fact. Both read as reflective ACKNOWLEDGMENT-OF-FACT rather than AFFECTIVE
  acknowledgment-of-distress — precisely the class the rubric's own holistic test says should
  NOT count ("not... a slot-content restatement", cited in REV-032 Issue 1). This is a
  milder, but structurally identical, instance of the same concern Issue 1 raised for bare
  `겠` — the `-군요` marker (added by ADR-029 D2 to close a different gap) fires on neutral
  reflective restatement, not only on affectively-loaded reflection.
- **Combined tally:** 10 confirmed true positives (7 tracker + 3 mine) / 12 total sampled
  (tracker's 7 + my 5 additional), 2 contestable/soft-false-positives found by me (both
  `-군요`, both neutral-restatement pattern), out of 25 total `-군요` single-marker decisions
  logged in cell4 (non-exhaustive sample, ~48%). "0 false positives" is **not** licensed as
  an unqualified claim; "no confirmed false positives among the sampled instances, but 2
  contestable neutral-restatement cases found on independent re-sampling" is the honest
  statement.

## 2. SM-06 ruling — exact wording licensed

Not licensed: "SM regression-free", "bisection cleared/exonerated the guard",
"assertion-identical to baseline" (unqualified).

Licensed: "SM-01..08a: 10/11 assertion-identical to baseline (not independently re-verified
beyond SM-06 this session). SM-08b: known BUG-026 fail, unchanged, unrelated. SM-06: one
unreproduced failure across 3 treatment-code draws (original + 2 bisection re-runs, 2/2
PASS); the same slot-collection-stall symptom also reproduced on pre-guard control code,
consistent with pipeline/LLM-sampling flakiness rather than a deterministic guard
regression — but the original failing draw's turn 7 shows a concrete BUG-028-consistent
degenerate no-question retry output, so a guard-contribution mechanism at the margin is not
ruled out. Stochastic-flake-likely; not confirmed guard-caused; treat as inconclusive, not
cleared."

## 3. Criterion-A validity ruling (population caveat + unmarked-template repetition)

A PASS on a shrunken instrument population is **not honest** as an unqualified "repetition
resolved" claim. Both VP-001 (2/10) and VP-010 (4/10) show additional, materially-sized
attempted-empathy/reflection content that the 12-marker instrument cannot see, and in both
cases at least part of that invisible content is itself repeated (VP-010: 3x incl. 2 b2b,
would independently FAIL if counted; VP-001: a near-duplicate pair at t3/t10). This binds
criterion A's own verdict — it does not route around it to some other criterion — because
criterion A's OWN pre-registered scope ("computed over all non-excluded scored turns")
implicitly assumed the marker instrument would surface the relevant population, and that
assumption is now shown false in 2/2 checked "PASS" sessions. Ruling: VP-001 and VP-010 are
PASS-ON-INSTRUMENT / NOT-CLEARLY-PASS-ON-CONSTRUCT. Any report citing these two sessions as
clean repetition-bar passes must carry this caveat.

## 4. Guard-dedup defect — measurement vs. mechanism (section 5 of the brief)

**Does NOT invalidate EXP-018 verdicts as measurements.** Both `analyze_criterion_a.py` and
`analyze_criterion_b.py` independently recompute clause extraction/clustering directly from
the shipped `conversation.json` artifacts, with no dedup and no reliance on the guard's own
internal `session_clauses`/`retry_reasons` state — confirmed by direct code read of both
scorers (criterion A: `cluster_families` iterates every scored turn's clause with no
uniqueness filter; criterion B: `retry_reasons` is used only in the descriptive B.1
telemetry sub-check, explicitly NOT the acceptance bar per REV-032 B.5). The FAIL verdicts on
VP-003 141607 and SC5-142022 are sound, independently-derived measurements of what actually
shipped — if anything, SC5-142022's 9/10-turn near-identical-clause FAIL is itself the
clearest possible EMPIRICAL PROOF the defect has real, not merely theoretical, consequence.

**DOES invalidate the "iteration-2 mechanism" claim as a general claim.** The confirmed
defect (exact-string dedup in `_extract_used_empathy_clauses`, `dialogue.py:443-462`) means
the near-dup/session-cap enforcement reliably functions ONLY for (a) the first reuse of a
clause and (b) an IMMEDIATE back-to-back reuse with no intervening distinct clause — the
moment any A-B-A pattern occurs (returning to an earlier phrasing after one detour, which is
ordinary, expected dialogue behavior, not an edge case), enforcement for that clause family
silently and permanently disables for the rest of the session, with zero telemetry signature
distinguishing "no violation occurred" from "violation occurred but was undetectable." A
claim that "iteration-2 enforces the pre-registered session-wide ≤2-uses/zero-back-to-back
bar" is therefore false as a GENERAL claim about the mechanism, even though it is true for
the narrow "the first two occurrences and immediate reuse" sub-case. This also means cell4's
retry-reason counts (`near_dup_back_to_back: 27`, `exact_repeat: 28`, `presence_missing: 4`,
retry rate 35/137) are confirmed LOWER BOUNDS on true near-dup incidence, not the true rate —
any report citing these numbers as "the near-dup rate" must caption them as detected-only.

**Does not affect:** the presence/BUG-035 mechanism (`presence_missing` depends only on
`crisis_adjacent`/`is_empathy`, not on `session_clauses`) — criterion B's clean PASS stands
unqualified by this defect. Criterion D (telemetry invariants) and criterion E (marker set)
are also unaffected — they do not depend on `_extract_used_empathy_clauses`'s dedup
semantics.

**Routing:** confirmed live production defect, same severity class as prior BUG-028/BUG-030
lineage; qa is independently verifying in parallel (BUG-036 per brief) — my own live-artifact
trace (VP-003_142022 turns 6-9) and hand-derivation against `cell3_guard_repro.log`
corroborate the tracker's finding exactly, 5/5 turns match. Fix (developer-scoped, not mine to
design): `_extract_used_empathy_clauses` must either preserve full multiplicity or track
clauses in true recency order rather than first-seen order.

## 5. Binding MAY / MUST-NOT wording table

REV-031's standing table (unqualified user-hypothesis-confirmed / code-defect-eliminated /
no-verbatim-match / repetition-not-resolved / SM-regression-free-at-assertion-level /
badgering-persists MAY list; repetition-fixed-unqualified / novel-phrases-without-disclosure /
SM-PASS-as-resolution-evidence / SC5-session2-as-comparable-evidence /
BUG-030-closed MUST-NOT list) remains in force. EXP-018-specific additions:

| # | Wording | Status |
|:--|:--|:--|
| 1 | "Iteration-2 eliminates the exact-full-response-repeat and first-reuse/immediate-back-to-back near-dup cases" | MAY |
| 2 | "Criterion D telemetry invariants are clean, 0/137" | MAY |
| 3 | "Bare-겠 false-positive channel is structurally eliminated" | MAY |
| 4 | "Presence bar (criterion B) is met on both scored SC5 sessions, recount-confirmed" | MAY |
| 5 | "Retry/near-dup telemetry counts (35/137, 27 near_dup_back_to_back, etc.) are detected-only, known lower bounds on true near-dup incidence" | MAY (must be phrased as a lower bound) |
| 6 | "Criterion A repetition bar is met" / "repetition resolved" for VP-001 or VP-010 without stating the population caveat (2/10, 4/10) and the unmarked-template-repetition finding | MUST NOT |
| 7 | "The guard's near-duplicate/session-cap mechanism functions as designed" (unqualified, general claim) | MUST NOT |
| 8 | "Iteration-2's near-dup mechanism is proven at scale" or citing cell4 retry counts as the true near-dup rate | MUST NOT |
| 9 | "SM regression-free" / "bisection cleared the guard" / "assertion-identical to baseline" (unqualified, re: SM-06) | MUST NOT |
| 10 | "Criterion E spot-check: 0 false positives" (unqualified) | MUST NOT |
| 11 | "BUG-035 resolved" / "presence bar generally met" without the criterion-B.3 coverage-delta and turn-0 ambiguity disclosures already required by REV-032 | MUST NOT |
| 12 | "Criterion A: 2 of 4 scored sessions FAIL, guard-dedup defect confirmed to silently disable near-dup enforcement mid-session, VP-001/VP-010 PASS is instrument-limited not clean" | MAY |

## 6. Overall disposition

| Criterion | Verdict |
|:--|:--|
| A — repetition bar | **FAIL** (as a pre-registered bar; 2/4 checked sessions clean FAIL, 2/4 conditional-only) |
| B — presence bar | **PASS** (recount-confirmed) |
| C — SM regression | **PASS-with-conditions** (10/11 clean, SM-06 inconclusive not cleared) |
| D — telemetry sanity | **PASS** (clean) |
| E — marker spot-check | **PASS-with-conditions** (bare-겠 eliminated; new soft-false-positives found in `-군요`) |

Criterion A — the central deliverable of BUG-030 iteration-2 — **FAILS**. The mission's own
pre-registered stop-rule ("criteria FAIL -> STOP, no iteration-3 without user word") is
**TRIGGERED**. No autonomous iteration-3 dispatch. This mirrors the disposition
EXP-017/REV-031 already established for iteration-1 (repetition not resolved -> queued,
pending user word) — iteration-2 improves the mechanism (eliminates the exact-repeat/
immediate-reuse cases, adds a working presence bar) but does not meet its own bar, and a
newly-confirmed live code defect (not merely an LLM-adherence gap) is part of why.

## Tally

- Blocking: 1 (criterion A fails as a bar; guard-dedup defect confirmed live)
- Major: 4 (VP-001/VP-010 instrument-limited PASS; SM-06 inconclusive not cleared; criterion
  E new soft-false-positives; cell4 telemetry is a lower bound not a true rate)
- Minor: 1 (criterion B turn-0 qualifying/unanswered ambiguity, non-blocking this run)
- Positive findings: 5 (criterion B clean recount-confirmed PASS; criterion D clean; bare-겠
  eliminated as designed; VP-003 141607's guard correctly detected every violation before
  budget exhaustion — a real, working sub-case; ADR-029 D3/D5 mechanisms — probe_just_concluded
  threading and presence-priority — both confirmed correctly implemented by direct code read)
