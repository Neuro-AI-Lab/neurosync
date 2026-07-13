# [REV-034] Fix-2 option validity + Fix 1/Fix 3 offline-evidence adjudication | 2026-07-12 | critic

**Target:** `docs/ai/fix_design_exhaustion_bug037.md` §1 (Fix-2 options, design-only) and §2
(Fix 1 / Fix 3, as-implemented) — blind gate, live verification deferred by user word.
**Scope:** implementation + offline evidence only. Not a pick among Fix-2 options (clinical-
validator's call) and not an implementation-QA pass (qa's lane).
**Status:** open

## Scope note

Every claim below was re-derived directly from the artifacts named in the brief, not trusted from
the design note's or prior reviews' prose. Where a design claim is confirmed by my own trace, it is
marked "confirmed"; where a genuinely new issue was found (not present in REV-032/REV-033 or the
design note itself), it is marked "new finding."

---

## Part 1 — Fix-2 option validity ruling (§1, design-only)

### 1.0 Mechanical basis, re-derived

`_extract_leading_clause` (`dialogue.py:484-503`) returns `stripped[:end].strip()` where `end` is
the index, into the **`.strip()`-normalized** copy of the text, of the earliest `.`/`!`/`?`. It does
**not** return or expose `end` itself — only the clause substring. All three Fix-2 options describe
their mechanism as operating on "the span `_extract_leading_clause` identifies," but that function
is a clause-extractor, not a span-locator: it hands back text, not an index. This matters for the
"never touch clinical content" constraint specifically because:

- If the eventual splice is implemented as `original_text.replace(candidate_clause, opener, 1)`
  (naive substring replace on the **unstripped** original), it is safe only if
  `candidate_clause`'s first occurrence in `original_text` is unambiguous — true here (it is a
  literal prefix once leading whitespace is accounted for), so this specific implementation shape
  is safe.
- If instead implemented via `stripped[end:]`-style index arithmetic mixed with the unstripped
  original (e.g., slicing the original text at an index computed against the stripped copy), a
  leading-whitespace mismatch would corrupt the boundary — not by touching semantic clinical
  content, but by mis-locating where "the remainder" starts (dropping or duplicating characters
  immediately after the punctuation mark).

**Ruling:** none of the three options is unsafe by design, but none is yet a *proven* property
either, because the design note does not commit to one specific substring operation and no test
exists yet (Fix 2 is unimplemented). This is a concrete precondition, not a hypothetical: whichever
option is picked, the implementation **must** (a) use a whole-original-text operation keyed off the
literal `candidate_clause` prefix (the `.replace(candidate_clause, X, 1)` shape, or equivalent), and
(b) ship with a test asserting `assistant_response[len(candidate_clause):] ==
original_candidate[len(candidate_clause):]` (byte-identical remainder) on a fixture where the
original text has irregular leading whitespace — mirroring how `test_bug_037.py` pins its
`this_turn`/`prior_turn`/`patient_echo` boundaries with real artifact fixtures. Absent this test,
"never touches clinical content" is a stated intent, not a demonstrated property, for any of A/B/C.

**Failure mode "(1)" in all three options ("if `_extract_leading_clause` returns `''`... the
degrade is a no-op") is dead code for this specific trigger.** Traced `dialogue.py:302-329`:
`near_dup_reason` is computed only `if is_empathy else None` (line 304-307), and
`_is_empathy_clause` (line 505-515) requires `bool(clause)` — i.e. a **non-empty** clause — before
returning `True`. Since the exhaustion branch for Fix 2 is reached only when the final iteration's
acted-upon `violation` is `near_dup_back_to_back`/`near_dup_session_cap`, `candidate_clause` at that
point is guaranteed non-empty by construction. The empty-clause / bare-`?`-opener case the design
worries about cannot occur on this exhaustion path as currently coded. This is not a defect — the
design is conservatively over-disclosing a risk that is actually unreachable — but the future
implementation should not spend effort defensively handling it as if it were live, and should not
cite this disclosure as evidence of thoroughness beyond what it is (a moot edge case for this
trigger).

### 1.1 Per-option ruling

| Option | Content-preservation mechanics | New finding this session | Validity-safe? |
|:--|:--|:--|:--|
| A — neutral-opener splice | Fixed opener "네," contains none of the 12 `_EMPATHY_MARKERS` substrings (checked against `dialogue.py:65-71`) — the spliced-in text can never register as `is_empathy=True` on a later turn or in `analyze_criterion_a.py`'s independent re-scoring. Cleanest of the three on the measurement-contamination axis (see §1.2). | — | Yes, conditional on §1.0's index-precision + byte-identical test. |
| B — suppression (delete) | No substitute text at all — trivially cannot register as an empathy clause or contaminate anything downstream; also the only option immune to §1.2 by construction. | — | Yes, conditional on §1.0. Clinical-adequacy tradeoff (bare-question risk on crisis-adjacent turns) is explicitly clinical-validator's call, not re-litigated here. |
| C — phrase-pool substitution | Splice mechanics identical to A/B. But the design's own stated purpose ("always inserts SOME acknowledgment," content that should plausibly read as genuine empathy) means the pool phrases are likely to contain literal `_EMPATHY_MARKERS` substrings by design intent — untested since no literal phrase text is given in the design note. | **Yes — see §1.2, a concrete, code-verified contamination mechanism, not hypothetical.** | Conditional, and strictly more conditions than A/B: every pool phrase must be checked against `_EMPATHY_MARKERS`, and whichever way that check comes out, a corresponding criterion-A scoring exclusion (§1.2) is required before any future battery can trust a criterion-A verdict on a session containing a Fix-2 degrade. |

### 1.2 New finding — fallback/template text can silently enter the empathy-repetition population (measurement AND production-behavior risk)

This was verified directly against **already-shipped** code (Fix 3), not against Fix-2's
hypothetical Option C — meaning this is not a design risk to weigh for Fix 2 only, it is a live
finding that the same class of defect already exists in the codebase and Fix 2 must not repeat it.

`_OUTPUT_ISOLATION_FALLBACK_RESPONSE` (`dialogue.py:82-84`) is:
`"네, 말씀해 주셔서 감사합니다. 이어서 편하게 이야기 나눠 주세요."`

This string **contains the literal substring `"감사합니다"`**, one of the 12 `_EMPATHY_MARKERS`
(`dialogue.py:67`). Tracing `_extract_leading_clause` against this exact string: the first
terminal-punctuation match is the period immediately after `감사합니다`, so the extracted leading
clause is `"네, 말씀해 주셔서 감사합니다"` — which `_is_empathy_clause` classifies `True`.

Two independent, verified consequences:

1. **Production guard (in-session):** `_extract_used_empathy_clauses` (`dialogue.py:517-553`)
   extracts the leading clause of **every** assistant turn with no `is_empathy` filter and no
   origin-tracking (it cannot distinguish an LLM-generated turn from a guard-fallback-shipped
   turn). If `output_isolation_fallback` ships on turn N, `"네, 말씀해 주셔서 감사합니다"` enters
   `session_clauses` and is available for `_same_phrase_family` comparison against every later
   genuine candidate in the same session. A later turn whose own genuine leading clause shares
   token overlap with this fixed string (plausible — "감사합니다"-based openers are a marker the
   production prompt is free to generate) could false-trigger `near_dup_back_to_back`/
   `session_cap` against a template string the model never organically said, consuming retry
   budget for a phantom repetition.
2. **Measurement (EXP-018-style scoring):** confirmed by direct read of `analyze_criterion_a.py`
   (lines 38-44, 61-62, 128-144). Its `_EMPATHY_MARKERS` list is an exact copy of production's, its
   exclusion list is `turn0_greeting` / `crisis_substituted` / `empty_agent_response` only (lines
   124-133) — **no exclusion exists for a fallback-shipped or degraded-shipped turn** — and its
   `if not ar: excluded` check (line 131) does not catch the fallback text, since it is non-empty.
   A session containing one or more `output_isolation_fallback` ships will therefore have
   `"네, 말씀해 주셔서 감사합니다"` scored as a genuine empathy clause data point by
   `analyze_criterion_a.py`, indistinguishable in the artifact from organic model output. If this
   exact fallback fires ≥7 times in one degenerate session (extreme, but not excluded by anything
   in the current design), criterion A's own auto-FAIL override (`analyze_criterion_a.py:167,169`)
   would trigger for a reason that has nothing to do with genuine empathy-phrase repetition — the
   guard's own safety-net text repeating deterministically, by design, would itself manufacture a
   criterion-A FAIL.

**This generalizes directly to Fix-2 Option C**: any pool phrase containing an `_EMPATHY_MARKERS`
substring inherits both consequences above. Option A's "네," and Option B's suppression are immune
(§1.1) precisely because neither can register as `is_empathy=True`.

**Resolution required before the future battery can trust criterion A on any session containing an
isolation fallback or a Fix-2 degrade:**
- Add `output_isolation_fallback` (and, once implemented, the Fix-2 degrade flag —
  `near_dup_degraded` or equivalent) as a new exclusion category in `analyze_criterion_a.py`'s
  `excluded` list, parallel to `turn0_greeting`/`crisis_substituted`/`empty_agent_response`.
- For Option C specifically: either (a) constrain the phrase pool to strings provably free of every
  `_EMPATHY_MARKERS` substring (mirroring Option A's property, defeating part of Option C's own
  stated purpose of "reading as a genuine acknowledgment"), or (b) accept the exclusion-list fix
  above as the mitigation and disclose that Option C's pool entries are deliberately excluded from
  criterion-A's population by telemetry flag, not by content.
- This is additive to, not a replacement for, REV-033's still-outstanding marker/clustering
  correction (§3 below).

---

## Part 2 — Fix 1 (BUG-036) / Fix 3 (BUG-037) offline evidence

### 2.1 Fixture faithfulness vs. raw artifacts (spot-checked, not sampled)

Direct byte-level comparison, not trust in the design note's claim of verbatim derivation:

- `test_bug_037.py`'s `_RISK_ASSESSMENT_LEAK` and `_PATIENT_DENIAL_VP001` — compared verbatim
  against `VP-001_20260712_141413_conversation.json` turn 9 (`agent_response`, `patient_message`,
  `slot_updates.risk_assessment`, `dialogue_crisis_adjacent: false`): **exact match**, including the
  design's claim that the confirmed hit occurred on a `crisis_adjacent=False` turn.
- `test_bug_037.py`'s `_PATIENT_DENIAL_VP010` — compared against `VP-010_20260712_141728_
  conversation.json` turn 7 (`patient_message` and `agent_response` byte-identical to each other in
  the raw artifact, confirming the echo): **exact match**.
- `test_bug_036.py`'s `_ABA_TURNS` (10 entries) and `_AAA_TURNS` (11 entries) — compared turn-by-
  turn against `VP-003_20260712_142022_conversation.json` and `VP-003_20260712_141607_
  conversation.json` respectively, full read of both artifacts turns 0-10: **exact match** on every
  `patient_message`/`agent_response` pair checked, including the specific `dialogue_retry_reasons`/
  `dialogue_fall_through` values REV-033 cited (e.g. 141607 turn 6: `["exact_repeat",
  "near_dup_back_to_back"]`, `fall_through=false`; turn 7: `fall_through=true`).

No fixture drift found. This is a genuine positive finding — both regression suites are grounded in
real production incidents, not synthetic approximations.

### 2.2 Mutation resistance

- **`test_bug_037.py`** is uniformly strong: every assertion is an exact-equality check on
  `retry_reasons`, `assistant_response`, `fall_through`/`output_isolation_fallback`, or a substring
  check on the actual retry-hint text sent to the LLM (e.g. `"임상 기록" in retry_user_content` /
  `"위기 인접" not in retry_user_content` in `TestOutputIsolationPriorityOrdering`). These would
  catch a priority-ordering regression, a budget-arithmetic regression, or a wrong-hint regression.
- **`test_bug_036.py`** is weaker on one axis: `TestABAShapeNowDetected` and
  `TestAAAShapeStillDetected` — the two tests carrying the core BUG-036 regression claim (turns 4-9
  all detected; turn 5 correctly `session_cap`) — call `DialogueAgent._extract_leading_clause`,
  `_is_empathy_clause`, `_extract_used_empathy_clauses`, `_empathy_repetition_violation` **directly**
  via the `_violation_at_turn` helper, not through `agent.run()`. Only one test in the file
  (`TestNearDupTelemetryRecordsSubRuleFamilyCount::test_back_to_back_catch_records_reason_family_
  count`) exercises the full `run()` loop, and it covers only a single `back_to_back` case over a
  4-turn history — `session_cap` and the deeper ABA chain (turns 4-9) are never exercised through
  `run()`'s actual wiring (the `session_clauses = self._extract_used_empathy_clauses(inp.
  conversation_history)` call site at `dialogue.py:275`, computed once before the retry loop). A
  regression that broke only the `run()`-level wiring (e.g., reintroducing a dedup step before the
  call, or passing the wrong variable) would not be caught by the ABA/AAA tests as written — only a
  regression in the four static helpers themselves would be caught. Recommend (developer-scoped, not
  mine to implement): at least one `run()`-level test replaying the ABA fixture through a mocked
  adapter with `session_cap` as the asserted outcome, mirroring what `test_bug_037.py` already does
  well for output-isolation.
- **`TestXListDisplayStillDeduped::test_x_list_shows_distinct_phrases_only`**
  (`test_bug_036.py:315-326`) asserts `x_lines.count('  X "정말 힘드셨겠어요..."') <= 1` — an
  **upper-bound-only** assertion. A regression that emptied the X-list entirely (e.g., an exception
  silently swallowed in `_build_slot_context`, or `used_empathy_all` always returning `[]`) would
  satisfy `count == 0 <= 1` and pass silently, defeating the test's stated purpose ("must appear at
  most once, not 5 times" — never asserts it appears at least once). Minor, easily fixed
  (`== 1`, plus a presence check for the other 1-2 distinct clauses the docstring itself names).

### 2.3 BUG-022 allowlist change (`test_bug_022.py`)

`DialogueInput`'s allowlist entry gained `slot_updates_this_turn` (`test_bug_022.py:83-91`).
Verified this does not weaken the gate BUG-022 protects:

- The gate's actual protection is `test_bug_022_forbidden_fields_never_appear_on_any_clinical_agent_
  input` (line 169) checking field **names** against the 4 ground-truth columns
  (`class`/`phq9_score`/`gad7_score`/`flag_suicidal`) — `slot_updates_this_turn` is not one of these
  and does not touch this assertion.
- Traced the field's actual data origin in `f1.py`: `slot_updates_this_turn=dict(slot_updates)`
  (`f1.py:1579`) — `slot_updates` is a per-turn local populated by (a) `f1.py`'s own Step 1b
  risk-assessment composition (`f1.py:1371/1394/1426`, itself built from the *same-turn*
  `patient_message`, not from `rag.session_insights`) and (b) Step 2's `ClinicalSlotAgent`
  extraction result (`f1.py:1491-1504`, confirmed running **before** the Step 3 dialogue call at
  `f1.py:1566`, matching the design's "already-computed, non-persona runtime data" claim exactly).
  Neither source touches `retrieve_grounding()` or `rag.session_insights`, the actual BUG-022
  vector. The `test_field_allowlist_exact_match` test still forces a reviewed, conscious update
  (confirmed by the inline rationale comment at `test_bug_022.py:78-82`) rather than a silent pass.
  **Not weakened.**

### 2.4 Budget-arithmetic claim

"3 LLM calls total (no budget inflation)" on output-isolation exhaustion — re-traced against
`dialogue.py:334-401`: the exhaustion check (`retry_count >= _MAX_REGENERATION_ATTEMPTS`, i.e. `>=
2`) happens **before** `retry_count` is incremented, so the sequence is draft (call 1) → check
(retry_count=0, not exhausted) → retry (call 2, retry_count→1) → check (not exhausted) → retry
(call 3, retry_count→2) → check (exhausted, exit without a 4th call). Matches
`TestBug037BudgetExhaustionShipsNeutralFallback`'s `adapter.chat_timed.call_count == 3` exactly.
Confirmed correct, and confirmed the shared-budget claim holds under
`TestOutputIsolationPriorityOrdering` (only one violation reason recorded per attempt regardless of
how many of the four sub-checks simultaneously fire, since `retry_count` is a single counter
incremented once per loop iteration independent of which check is acted upon).

### 2.5 Telemetry adequacy for the future battery

Confirmed present and correctly threaded end-to-end (`DialogueOutput` → `F1TurnLog` → presumably
`conversation.json`, verified via `dialogue.py`, `schemas/dialogue.py`, `f1.py:217-220/1340-1341/
1591-1594/1647-1648`, and `TestF1TurnLogAndSchemaTelemetryThreading`): `output_isolation_fallback`,
`near_dup_detail`. Gaps for the future battery:

- **REV-032 criterion D (telemetry sanity) is stale relative to both Fix 3 and any future Fix 2.**
  Its pre-registered invariants (`fall_through == True ⟹ retry_count == _MAX_REGENERATION_
  ATTEMPTS`, etc.) predate `output_isolation_fallback` and say nothing about it. The actual code
  invariant that should be added and pre-registered: `output_isolation_fallback == True ⟹
  fall_through == False ∧ retry_count == _MAX_REGENERATION_ATTEMPTS` (confirmed true by direct code
  read, `dialogue.py:334-361`, and by `TestBug037BudgetExhaustionShipsNeutralFallback`), and,
  symmetrically once Fix 2 lands, whatever its degrade-flag is must be mutually exclusive with both
  `fall_through` and `output_isolation_fallback`. Without this addition, criterion D as currently
  worded will not catch a future regression where both flags are set simultaneously (a state the
  code's own comments say must never happen — `dialogue.py:198-200` — but which criterion D cannot
  currently detect).
- **Criterion A instrument correction — confirmed NOT applied, remains outstanding.** Grepped
  current `dialogue.py` (`_EMPATHY_MARKERS`, lines 65-71) and `analyze_criterion_a.py` (lines 38-44):
  neither carries the stem-level `것 같` marker `analyze_criterion_b.py` already added (REV-033's
  cited precedent). This fix cycle (Fix 1/Fix 2/Fix 3) does not touch the marker set at all — it was
  out of scope for BUG-036/BUG-037/the exhaustion redesign, and remains a **standing, unresolved**
  precondition from REV-033, now compounded by §1.2's new finding above.

---

## 3. Pre-registered criteria — remain decidable, restated scoring note for the future battery

Per the brief's binding constraint: REV-032's criteria A-E and REV-033's rulings are **not softened**
here. All are still mechanically computable against a future F1-F5 battery's artifacts (every
formula, threshold, and exclusion rule is crisp and re-derivable from raw `conversation.json`, as
this session's own re-derivations against VP-001/VP-003/VP-010 confirm). What changes is the set of
disclosures required before a criterion-A **verdict** can be cited as evidence about genuine LLM
behavior, which now stands at three, cumulative, none superseding the others:

1. (REV-033, outstanding) VP-001/VP-010-style sessions: a criterion-A PASS is PASS-ON-INSTRUMENT
   unless the marker set is stem-broadened (`것 같` bare stem, minimum) or clustering is broadened to
   all leading clauses regardless of marker match ("all-leading-clause clustering") — either fix, or
   an explicit disclosed decision not to apply either, must be on record before the future battery's
   criterion-A PASS verdicts are cited as clean.
2. (this session, new, §1.2) Any session containing an `output_isolation_fallback` ship (already
   live in Fix 3) must have that turn's clause excluded from criterion-A's `empathy_clauses`
   population, or any resulting FAIL/family-count for that session is potentially an artifact of the
   guard's own deterministic safety text, not genuine LLM repetition.
3. (this session, new, §1.2, Fix-2-conditional) If Option C is selected, its phrase-pool entries
   must be pre-registered as excluded from criterion-A's population by the same mechanism as (2), or
   shown free of every `_EMPATHY_MARKERS` substring.

None of A-E's PASS/FAIL mechanics themselves need to change; only the exclusion set and the
disclosure obligations grow. Criterion B, C, D positive rulings from REV-033 (presence bar
recount-confirmed PASS; SM regression PASS-with-conditions; telemetry PASS) are unaffected by
anything found this session — none of today's findings touch the mechanisms those criteria measure.

## 4. MAY / MUST-NOT additions (extends REV-033 §5's table)

| # | Wording | Status |
|:--|:--|:--|
| 13 | "Fix 1 (BUG-036) and Fix 3 (BUG-037) offline test evidence is fixture-faithful to the cited raw artifacts, spot-checked byte-for-byte" | MAY |
| 14 | "Fix 3's budget-exhaustion path never ships the violating text and never exceeds 3 LLM calls/turn" | MAY (code- and test-confirmed) |
| 15 | "The BUG-022 allowlist update for `slot_updates_this_turn` weakens the BUG-022 gate" | MUST NOT — traced data origin, gate scope unaffected |
| 16 | "Any Fix-2 option is validity-safe as implemented" | MUST NOT — none is implemented yet; §1.0's index-precision requirement and byte-identical-remainder test are preconditions, not yet met by any option |
| 17 | "Criterion-A verdicts on a session containing an `output_isolation_fallback` ship (or, later, a Fix-2 Option-C degrade) reflect genuine LLM repetition behavior" | MUST NOT, until §1.2's exclusion is added to `analyze_criterion_a.py` |
| 18 | "BUG-036's regression coverage is run()-level end-to-end" | MUST NOT (unqualified) — the core ABA/session_cap assertions are helper-level, not run()-level; qualify as such if cited |

## Tally

- Blocking (scoped, not gate-wide): 1 — §1.2/§3 item 2: no future criterion-A verdict on a session
  with an `output_isolation_fallback` ship may be cited as evidence of genuine repetition behavior
  until the exclusion fix lands; this is decidable and fixable, not a research-design flaw.
- Major: 3 — §1.0 (index-precision/byte-identical-remainder precondition, applies to all 3 Fix-2
  options), §1.2/Option C (pool-phrase marker contamination, conditional on CVR-013's pick), §2.2
  (BUG-036's helper-level-only test coverage for its core claims).
- Minor: 2 — §2.2 X-list upper-bound-only assertion; §2.5 criterion D staleness (fixable
  pre-registration addition, not a code defect).
- Positive findings: 5 — fixture faithfulness confirmed exact for all 4 cited artifacts (§2.1);
  BUG-037's test suite is uniformly mutation-resistant (§2.2); budget arithmetic confirmed exact
  (§2.4); BUG-022 gate confirmed unweakened with full data-origin trace (§2.3); Options A and B are
  structurally immune to the §1.2 contamination mechanism by construction, giving CVR-013 a concrete,
  code-grounded reason (beyond the design's own governance-surface argument) to prefer A/B over C if
  the marker-overlap risk in C's pool cannot be cleanly resolved.

---

# [REV-035] Fix 2 as-implemented verification + fix-cycle wording-license ruling | 2026-07-12 | critic

**Target:** Fix 2 as-implemented (`dialogue.py`, `schemas/dialogue.py`, `f1.py`, per
`docs/ai/fix_design_exhaustion_bug037.md` §3, ADR-030 Option C) — verifying REV-034's 3 conditions,
measurement integrity for the future battery, and closing wording license for the whole 3-fix cycle.
**Scope:** offline evidence only, bounded to the mission brief; no live runs, no clinical-adequacy
re-litigation (CVR-013's pick stands), no implementation-QA re-pass (qa's gate accepted verbatim).
**Status:** open

## 1. REV-034 condition verification

**(a) Byte-identical-remainder test — SATISFIED, one gap.** `_splice_point` (`dialogue.py:621-632`)
returns a raw index into the UNSTRIPPED text via `_leading_clause_boundary`, and
`_degrade_empathy_clause` (`dialogue.py:819-860`) slices that SAME unstripped string
(`assistant_response[end:]`) — index and slice target are always the same string object, so no
cross-string strip-mismatch is possible BY CONSTRUCTION, structurally eliminating the risk class
REV-034 §1.0 flagged (mixing a stripped-text index against an unstripped slice). Confirmed by
reading both functions directly, not trusted from the design note's prose.
`TestDegradeEmpathyClauseSplicing` (`test_fix2_exhaustion_degrade.py:279-345`) independently
re-derives the expected remainder via `original.find(".")` (not by calling `_splice_point` itself)
and asserts `degraded[len(phrase):] == original[remainder_start:]` for `near_dup`/`exact_repeat`;
two further tests exercise the fail-safe-prepend path against 2 real artifact fixtures with
comma-joined single-sentence, `?`-only-terminal shape (CVR-013 condition 3).
**Gap:** no fixture has LEADING WHITESPACE on the original text — the exact scenario REV-034 §1.0
asked for verbatim ("a fixture where the original text has irregular leading whitespace"). Today's
code is immune to this by construction (above), but a future refactor that made
`_leading_clause_boundary` strip internally (e.g. "for consistency with `_extract_leading_clause`")
would silently break the byte-identical guarantee for any LLM output beginning with whitespace, and
no current test would catch it. Minor, not blocking. Resolution: add one
`_degrade_empathy_clause`/`_splice_point` test with a `" 정말 힘드셨겠어요. ..."`-shaped (leading
space) fixture asserting the remainder stays byte-identical.

**(b) Contamination channel / flag-exclusion path — SATISFIED as scoped; deferral acceptable.**
Confirmed `_DEGRADE_MARKER_CLAUSES`/`_exclude_degrade_marker_clauses` (`dialogue.py:141-154,
763-775`) is exactly the flag-exclusion path licensed for PRODUCTION — closed-set, exact-string
match, covers both the Fix-2 pool AND the pre-existing Fix-3 fallback (REV-034's original live
finding). Tested at `run()` level (`TestGuardDriftExclusionAtRunLevel`, both cases) — confirmed
working. Direct read of `experiments/EXP-018/analyze_criterion_a.py` (its exclusion list, lines
28-30, and `_EMPATHY_MARKERS`, lines 38-44) confirms neither has been touched — no
`exhaustion_degrade`/`output_isolation_fallback` exclusion exists yet; the "deferred as pre-battery
prerequisite" claim is accurate, not merely asserted. Is deferring the SCORER side acceptable given
no scoring happens before the battery? **Yes, conditionally:** (i) ADR-030 Decision 4 records it as
a tracked prerequisite, not a silently dropped item; (ii) no criterion-A (or, §2 below, criterion-B)
verdict is being cited in any report yet; (iii) the constraint carries forward as a MUST-NOT (§4).
This is the same "decidable and fixable, not a research-design flaw" framing REV-034 used for its
own scoped-blocking item — extending it here is consistent, not a softening.

**(c) `test_bug_036` run()-level wiring + upper-bound fix — SATISFIED.**
`TestBug036RunLevelWiring::test_third_nonadjacent_use_triggers_session_cap_retry`
(`test_fix2_exhaustion_degrade.py:521-560`) drives a compact A-C-A-B history through `agent.run()`
end-to-end and asserts `retry_reasons == ["near_dup_session_cap"]` with `count == 2` — closes the
exact gap REV-034 §2.2 flagged (session_cap and the deeper ABA chain were previously only exercised
at the helper level, never through `run()`'s actual `session_clauses` wiring).
`test_x_list_shows_distinct_phrases_only` (`test_bug_036.py:315-335`) now asserts `== 1` (was
`<= 1`) plus a `len(x_lines) >= 1` non-vacuousness guard — confirmed landed exactly as claimed.

## 2. New finding — criterion B (presence bar) has the SAME contamination class REV-034 found for
criterion A, in the opposite direction, plus a now-stale telemetry check

Not covered by REV-034 (§1.2 scoped to criterion A/repetition only) or by ADR-030 Decision 4's
prerequisite list (names "scorer exclusion by flag" generically, written against REV-034's
criterion-A-only finding).

Verified directly against `experiments/EXP-018/analyze_criterion_b.py`:
- `_AFFECT_STEM_MARKERS` (lines 48-52) includes `감사합니다`/`힘드`/`이해`/`공감` — every one of the 4
  `_EMPATHY_DEGRADE_POOL` phrases and `_OUTPUT_ISOLATION_FALLBACK_RESPONSE`'s own opener contain
  `감사합니다`; `presence_missing` degrades additionally always PREPEND a pool phrase (never replace,
  per `_degrade_empathy_clause`'s own contract) — so any `presence_missing`-exhaustion-degrade turn,
  and any `output_isolation_fallback` turn, will register `rubric_semantic_answered=True` in
  `analyze_criterion_b.py`'s `score()` (lines 85-95, 165-190), inflating the presence rate for a
  reason that is the GUARD's mechanical backstop, not the LLM's own adherence to BUG-035. A
  criterion-B PASS on a session containing either event type is not clean evidence of genuine
  presence-bar adherence — the mirror image of REV-034's §1.2 logic (false-PASS rather than
  false-FAIL).
- `b1_telemetry` (lines 193-202) checks `dialogue_fall_through and reasons[-1]=='presence_missing'`
  — post-Fix-2, `presence_missing` exhaustion always sets `fall_through=False` (routes to
  `exhaustion_degrade` instead; confirmed by `_is_empathy_degradable`/`run()`'s exhaustion dispatch,
  `dialogue.py:441-477`), so this specific check can now never fire again, regardless of whether the
  underlying B.1 concern (a crisis-adjacent turn shipping with no acknowledgment) still occurs
  through some other path. Same class of defect REV-034 §2.5 already flagged for criterion D's
  invariant (a scorer/telemetry check written against a field contract a later fix changed), not
  previously caught for criterion B.

**Resolution required** (parallel to REV-034 §1.2's criterion-A resolution, before the future
battery can trust criterion-B PASS verdicts on a degrade/fallback-containing session): extend the
scorer exclusion to `analyze_criterion_b.py` (exclude `exhaustion_degrade`/`output_isolation_fallback`
turns from the qualifying/answered population, or disclose them as guard-backstop-answered rather
than organic), and update `b1_telemetry` to check `exhaustion_degrade == "presence_missing"` in
addition to (or instead of) the now-unreachable `fall_through` condition. Recommend ADR-030
Decision 4 be amended to name criterion B explicitly, not just "scorer exclusion by flag"
generically, so this does not silently fall out of scope when the pre-battery prerequisites are
actioned.

## 3. Measurement integrity for the future battery — remaining channels

Telemetry (`exhaustion_degrade`, `exhaustion_degrade_phrase`, `output_isolation_fallback`,
`near_dup_detail`) is sufficient to IDENTIFY degraded/fallback turns — confirmed threaded end-to-end
`DialogueOutput -> F1TurnLog -> conversation.json` (`f1.py:224-225,1347-1348,1602-1604,1660-1661`)
and surfaced to the per-run checklist (`f1.py:1818-1879`, `TestChecklistSurfacesExhaustionDegrade`).
It is NOT yet sufficient to EXCLUDE those turns from criterion-A or criterion-B scoring — neither
scorer reads or acts on these fields today (confirmed by direct read of both files). Remaining
channels by which a degrade/fallback could masquerade as organic behavior in future scoring:

1. Criterion A (repetition): a degrade/fallback clause scored as a genuine empathy-repetition data
   point — REV-034's original finding, confirmed still open this session.
2. Criterion B (presence): a degrade/fallback clause scored as genuine presence-bar adherence — new
   finding, §2 above.
3. Criterion D (telemetry sanity): the invariant set does not yet assert
   `exhaustion_degrade`/`output_isolation_fallback` mutual exclusivity with `fall_through` —
   REV-034 §2.5, confirmed still open via `analyze_cell4_rollup.py`'s unmodified invariant checks
   (lines 100-116).
4. Criterion B's `b1_telemetry`: now-unreachable check, §2 above (new).

No other channel was found — the production-side guard-drift channel (near-dup false-triggering
against a system-inserted clause) is closed and tested (§1(b)); no residual production-behavior
contamination path was found beyond the 4 scoring-side items above.

## 4. Wording-license ruling for the fix-cycle report

**Licensed frame:** "code-complete, offline-gated, NOT live-verified" — confirmed correct; no live
run exists for Fix 2, all evidence is mocked-adapter unit/`run()`-level tests plus
static/artifact-fixture verification, matching the framing already applied to Fix 1/Fix 3 in
REV-034.

**MUST-NOT additions specific to this cycle** (extends REV-033 §5 / REV-034 §4 tables):

| # | Wording | Status |
|:--|:--|:--|
| 19 | Claims about live repetition rates, presence rates, or ship-through elimination in PRODUCTION traffic | MUST NOT — unlicensed until F1-F5 battery |
| 20 | "Fix 2 eliminates ship-throughs" (unqualified) | MUST NOT — qualify as "zero DETECTED-violation ship-throughs under the 3 currently-enumerated degradable violation types, code- and test-confirmed"; detection itself has known gaps (REV-033's still-open A-B-A/stem-marker findings) |
| 21 | Criterion-A PASS/FAIL verdict cited on any session containing an `exhaustion_degrade` or `output_isolation_fallback` ship | MUST NOT (REV-034 #17, reaffirmed — scorer exclusion still absent, confirmed this session) |
| 22 | Criterion-B PASS cited as evidence of genuine LLM presence-bar adherence on any session containing a `presence_missing`-`exhaustion_degrade` or `output_isolation_fallback` ship | MUST NOT — new this session, §2 |
| 23 | "REV-034's conditions were met" without the leading-whitespace test-gap disclosure (§1a) | MUST NOT unqualified — the structural (code-level) property holds; the specific regression test REV-034 asked for is not yet present |

**MAY (new, this session):** "Fix 2 (Option C) is implemented and offline-tested: the
byte-identical-remainder property holds by construction and is test-verified for the non-whitespace
cases and both fail-safe boundary shapes; the production guard-drift exclusion closes REV-034's live
finding for both the Fix-2 pool phrases and the pre-existing Fix-3 fallback; the run()-level
test-hardening items (BUG-036 session_cap, X-list non-vacuousness) landed as specified."

**Pre-registered bars status:** UNCHANGED and decidable — repetition <=2/session + zero b2b;
presence >=0.90 + zero 2-consecutive; zero detected-violation ship-throughs; zero clinical-note text
patient-facing; SM assertion-identical; telemetry sanity — all still mechanically computable against
raw `conversation.json` (confirmed; no code change alters any of these definitions). Pre-battery
prerequisite list, now 4 items (was 3 in REV-034 §3):

1. (REV-033) criterion-A stem-level marker broadening, or an explicit disclosed decision not to fix.
2. (REV-034 §1.2) criterion-A scorer exclusion for `exhaustion_degrade`/`output_isolation_fallback`
   turns.
3. (this session, §2) criterion-B scorer exclusion for the SAME turn set, plus `b1_telemetry`'s
   stale `fall_through`-based check corrected to check `exhaustion_degrade`.
4. (REV-034 §2.5) criterion-D invariant extension for `exhaustion_degrade`/`output_isolation_fallback`
   mutual exclusivity.

## Tally

- Blocking (scoped to citation, not to shipping): 2 — criterion-A verdict citation (REV-034,
  reaffirmed) and criterion-B verdict citation (new, §2) on any degrade/fallback-containing session,
  until their respective scorer exclusions land.
- Major: 0 new (REV-034's major items are resolved by this cycle's implementation work, per §1).
- Minor: 2 — leading-whitespace splice test gap (§1a); `b1_telemetry` now-stale check (part of the
  criterion-B contamination finding, §2).
- Positive findings: 4 — all 3 REV-034 conditions substantively met with code-level verification;
  the guard-drift exclusion is correctly scoped and tested for BOTH contamination sources REV-034
  named; BUG-036 test-hardening closes the exact run()-level gap flagged; telemetry threading is
  complete end-to-end and reaches an actually-reviewed surface (checklist), not just raw JSON.

**Overall REV-035 disposition:** non-blocking-with-conditions for shipping Fix 2 as
offline-gated/code-complete; two scoped-blocking citation restrictions carried into the
future-battery pre-battery-prerequisite list (now 4 items, not 3).
