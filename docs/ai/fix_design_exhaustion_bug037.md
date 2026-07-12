# Fix design — retry-budget-exhaustion redesign (Fix 2) + as-implemented summary (Fix 1, Fix 3)

**Scope:** PLAN-2026-W28-U. Fix 1 = BUG-036 (shape-robust empathy-repetition dedup). Fix 2 =
budget-exhaustion path redesign for the near-dup guard (**design only — not implemented**, awaits
`CVR-013`/`REV-034` review and `ADR-030` ratification). Fix 3 = BUG-037 (output-isolation guard).
Fix 1 and Fix 3 are implemented; this note is the developer deliverable required alongside them
(`docs/ai/fix_design_bug030_iter2.md` §1–§8 remains the base guard design — this note documents
only what changed/was added on top of it).

**Pins untouched:** dialogue v4 (`f93e995f68e3a3bc88ddd5ce1f6b01ef8feb5e5663bda46ce4958ae8e6317144`),
safety v2 (`3e9ca6b4...b390c`). No prompt file was edited for any of the three fixes below — every
mechanism is runtime code (retry hints, telemetry, guard logic), matching the existing guard's own
convention.

---

## §1. Fix 2 — retry-budget-exhaustion redesign options (design only, not implemented)

**Problem.** Today, when the near-dup guard's retry budget exhausts with a violation still held,
`fall_through=True` and the DETECTED-violating response ships to the patient as-is (CVR-012 F4;
reproduced live at `VP-003_20260712_141607_conversation.json` turns 7–10, where the guard
correctly detected `near_dup_back_to_back` on every attempt but shipped the repeated clause
anyway once the 2-retry budget was exhausted). CVR-012: "a caught safety-adjacent naturalness
violation is shipped to the patient rather than degraded safely."

**Hard constraint — binding on every option below:** the degrade must NEVER touch question or
clinical content. Only the leading empathy clause (the span `_extract_leading_clause` identifies,
`dialogue.py`) may be altered. Everything from the first `.`/`!`/`?` onward in the model's last
candidate ships byte-identical to what the model generated. This constraint is what makes a
degrade "safe" rather than a second, cruder LLM-non-adherence problem.

**Scope note.** This section is options only, for `CVR-013`/`REV-034` to adjudicate — a clinical
reviewer picks; this design does not pre-decide. All three options share the same trigger
condition (retry budget exhausted, `near_dup_*` still the held violation) and the same mechanical
substrate (`_extract_leading_clause` to locate the span to edit), differing only in what replaces
it and how loudly the substitution is flagged.

### Option A — Neutral-opener splice
**Mechanism:** replace the leading-clause span (start of string through the first terminal
punctuation) with one fixed, register-neutral opener (e.g. "네,"), then ship the remainder of the
model's last candidate verbatim from that punctuation mark onward.
**Latency cost:** zero extra LLM calls — pure string surgery on the already-generated candidate;
the 3-calls/turn budget is unaffected.
**Failure modes:** (1) if `_extract_leading_clause` returns `""` (response opens with `?`, or has
no `.`/`!`/`?` at all), there is no span to splice — the degrade is a no-op and the original
(un-fixed) candidate ships, identical to today's behavior for that shape; (2) targets ONLY the
leading clause — if the near-dup the guard flagged is a mid-response reflective clause with no
leading marker (not the shape any of the three sub-rules currently scan for, but a theoretical
future guard extension), splicing the leading span would not touch it; (3) grammatical seam risk —
if the model's leading clause was joined to the rest by a comma rather than `.`/`!`/`?` (not
observed in the calibration corpus, but not excluded by the boundary rule), the spliced opener
could read as attached to a sentence continuation that assumed the original clause's grammar.
**Telemetry:** `near_dup_degraded: bool`, `near_dup_stripped_clause: str` (the clause that was
replaced) — auditable, distinguishes "shipped as generated" from "shipped surgically edited."

### Option B — Suppression (delete, no replacement)
**Mechanism:** same span-detection as Option A, but the leading-clause span (plus its trailing
punctuation and any resulting leading whitespace) is deleted outright — no substitute text is
inserted; the response ships starting directly at the question/remaining content.
**Latency cost:** zero extra LLM calls, identical to Option A.
**Failure modes:** (1)/(3) same as Option A; (2, additional and more serious) a response with the
empathy clause fully removed opens as a bare question — exactly the shape the BUG-035
presence-missing check exists to catch elsewhere in this same turn's priority chain. Because this
path is reached only after the retry budget is exhausted, the presence check cannot re-fire this
turn — so on a crisis-adjacent turn, Option B can produce a response with literally zero
acknowledgment, which is a regression against BUG-035's own bar, concentrated on exactly the
population (crisis-adjacent, retries already spent) where it matters most. This is the strongest
argument against Option B as-is.
**Telemetry:** `near_dup_degraded: bool`, `near_dup_stripped_clause: str`, distinguished from
Option A's telemetry only by having no substitute-clause field (nothing was inserted).

### Option C — Deterministic session-aware phrase-pool substitution + prominent flag
**Mechanism:** maintain a small fixed pool of generic, register-neutral Korean acknowledgment
phrases (e.g. 3–5 entries spanning a couple of affect registers). On exhaustion, deterministically
select the first pool entry NOT already present in this turn's `session_clauses` (guarantees the
substitute itself is not a repeat within THIS session — no randomness, reproducible), splice it
into the leading-clause span (same mechanics as Option A), ship the remainder verbatim. In
addition to the ordinary `retry_reasons`/`near_dup_detail` telemetry, emit a distinctly
higher-visibility signal (e.g. a dedicated counter or a WARNING-level structured log line separate
from the routine per-turn logging) intended for a downstream QA/clinical review surface, not just
per-run log inspection.
**Latency cost:** zero extra LLM calls, identical to Options A/B.
**Failure modes:** (1)/(3) same boundary-detection edge cases as Option A (Option C does not have
Option B's bare-question risk, since it always inserts SOME acknowledgment); (2) a fixed phrase
pool is a smaller-scale reincarnation of BUG-030's original root cause (a static "alternatives"
menu) — within-session repetition is prevented by construction, but if the SAME small pool is
reused unmanaged across many sessions/patients over time it could itself need periodic rotation
governance; (3, disclosed trade-off) a template-selected phrase is inherently less content-matched
to what the patient just said than a genuine LLM-generated clause — in tension with the v4 prompt's
own design principle ("정해진 문구를 고르지 말고... 새로 표현", `docs/ai/prompts/dialogue/
v4.system.md`) that BUG-030's very fix was built around; using a template here is a knowingly
narrow exception (last-resort exhaustion path only, not the normal generation path).
**Telemetry:** `near_dup_degraded: bool`, `near_dup_substituted_clause: str` (which pool phrase was
used), plus the elevated review-surface flag described above.

### Recommendation framing (not a decision)
Option A is the simplest and lowest-risk (always produces SOME acknowledgment text, no new
governance surface). Option B is not recommended as-is given the BUG-035 interaction, unless
paired with an explicit acceptance that crisis-adjacent exhaustion cases may ship bare — a
clinical reviewer should weigh that explicitly rather than have it fall out of an implementation
default. Option C is the most "natural-reading" of the three but introduces a small new
governance surface (the phrase pool) and revives, in a narrow and disclosed way, the pattern
BUG-030 moved away from. `CVR-013` picks; none of the three is pre-selected here.

---

## §2. As-implemented summary — Fix 1 (BUG-036) and Fix 3 (BUG-037)

### Fix 1 — BUG-036: shape-robust empathy-repetition dedup

**Mechanism.** `_extract_used_empathy_clauses` (`apps/ai-server/src/agents/dialogue.py:518`) no
longer dedups by exact string. The prior `if clause not in used: used.append(clause)` guard
dropped every exact-repeat occurrence; the fix returns one entry per assistant turn, chronological
order, including exact repeats. This directly fixes both BUG-036 root causes: (a) the back-to-back
check's `session_clauses[-1]` pointer (`_empathy_repetition_violation`, `dialogue.py:594`) now
reflects the TRUE immediately-preceding turn instead of the last newly-introduced distinct clause;
(b) the session-cap's `prior_family_count` now counts every true occurrence instead of
undercounting exact-repeat families to at most 1 entry.

**Display-site regression guard.** `_build_slot_context`'s "이미 사용했으므로 절대 다시 사용하지
마세요" (X-list) hint (`dialogue.py:846`, dedup logic at `dialogue.py:893-899`) locally dedupes the
now-undeduped list (order-preserving) before rendering the last-5 hint shown to the LLM — the
underlying extractor's contract changed, but the X-list's original "show up to 5 DISTINCT prior
phrases" intent is preserved by moving the dedup to that specific call site.

**Telemetry (BUG-036 resolution-recommendation: "which sub-rule fired, family, count").**
`_family_count` (`dialogue.py:615`) is a new pure-function helper that counts prior same-family
occurrences without changing `_empathy_repetition_violation`'s tested `str | None` contract. In the
`run()` check-and-retry loop (`dialogue.py:253` onward), every attempt where the near-dup sub-check
itself detects a match — independent of whether it becomes the acted-upon violation this attempt,
since a higher-priority check can outrank it — appends `{reason, family, count}` to
`near_dup_detail` (`dialogue.py:309`). This is a new `DialogueOutput` field
(`apps/ai-server/src/schemas/dialogue.py`), threaded through `F1TurnLog.dialogue_near_dup_detail`
(`apps/ai-server/src/f1.py:218`, reset per-turn at `f1.py:1338`, read back at `f1.py:1589`,
constructed at `f1.py:1643`) — same threading discipline as the other 6 dialogue-guard telemetry
fields.

**Verification (calibration artifacts).** `tests/repro/test_bug_036.py` builds
conversation-history fixtures verbatim from the two cited artifacts. A-B-A shape
(`VP-003_20260712_142022_conversation.json`): turns 4–9 (including the 3 cited zero-detection
turns 6/7/8/9) now all fire `back_to_back`; turn 3 (the 2nd true use, non-adjacent to turn 1) is
asserted to correctly NOT fire, per rubric §2's own <=2-uses allowance — locked in as a test so a
future change doesn't silently over-fix into flagging every 2nd use. A-A-A contrast
(`VP-003_20260712_141607_conversation.json`): turns 7–10 still fire `back_to_back` (no
regression); turn 5 is additionally shown to be a second real BUG-036 instance in the same
artifact that the pre-fix dedup also missed (undercounted to `prior_family_count=1` when the true
count was 2), now correctly caught as `session_cap`.

### Fix 3 — BUG-037: output-isolation guard

**Mechanism.** New static check `_output_isolation_violation` (`dialogue.py:670`) tests, in
priority order: (1) any `slot_updates_this_turn` value — reason `"this_turn"`; (2) any other
`filled_slots` value — reason `"prior_turn"`; (3) the patient's own current-turn `user_message`,
verbatim — reason `"patient_echo"` (see "shared mechanism" below). Containment (`value in
response`), not just equality, is checked, so a partial embedded echo is also caught. A minimum
length gate (`_MIN_OUTPUT_ISOLATION_LEN = 15`, `dialogue.py:81`) guards every branch against
coincidental short-string collisions (e.g. a 2-char slot value, or a short "네"/"아니요" the model's
own legitimate response might independently contain).

**New input signal — `slot_updates_this_turn`.** `f1.py` Step 1b composes `risk_assessment`
BEFORE the Step 3 dialogue call and writes it into the shared `filled_slots` dict (`f1.py:1413-
1414`, unchanged) — this is the confirmed BUG-037 trigger shape. To let the guard prioritize
detecting a SAME-TURN leak over an older, already-shown one, `f1.py`'s existing per-turn
`slot_updates` local (already computed by that point — Step 1b's risk write plus Step 2's
ClinicalSlotAgent extraction, both before the Step 3 dialogue call) is threaded through a new
optional `DialogueInput.slot_updates_this_turn` field (`schemas/dialogue.py`), passed at
`f1.py:1575`. It is licensed, already-computed, non-persona runtime data (added to the standing
BUG-022 field allowlist gate, `tests/repro/test_bug_022.py`, as column (a) current-session data —
not new upstream/ground-truth exposure). Optional: the other live `DialogueInput` caller
(`routes/chat.py`) does not thread it, and the guard degrades gracefully to the `filled_slots`-only
check in that case (verified:
`test_bug_037.py::test_none_slot_updates_this_turn_falls_back_to_filled_slots`).

**Priority placement.** In the `run()` loop's violation-selection chain (`dialogue.py:253` onward),
`output_isolation` is checked and wins FIRST — above `presence_missing`, `exact_repeat`, and
`near_dup` (`dialogue.py:320`). ADR-029 Decision 5 binds `presence_missing`'s priority over
`exact_repeat`/`near_dup` specifically when `crisis_adjacent=True`; it does not speak to a check
that did not exist at ratification time, so placing `output_isolation` above it does not violate
Decision 5 — Decision 5's relative ordering among the original three is unchanged when
`output_isolation` does not fire. The placement is deliberate: an isolation violation means the
candidate is not a valid patient-facing message AT ALL (raw clinical-note prose or a mechanical
echo), a more severe failure class than a stylistically-imperfect-but-genuine reply missing an
empathy clause — CVR-012 F1: "not a naturalness defect but an interface-integrity/trust breach...
at the single highest-stakes moment of the intake." It is checked unconditionally (not gated on
`crisis_adjacent`), since the leak/echo shape does not depend on that turn's risk classification —
the confirmed BUG-037 hit itself occurred on a `crisis_adjacent=False` denial turn.
Locked in by `tests/repro/test_bug_037.py::TestOutputIsolationPriorityOrdering` (isolation wins
over a simultaneous `presence_missing` AND over a simultaneous `exact_repeat`).

**Exhaustion path — the one place Fix 3 does NOT reuse the standard `fall_through` mechanic.**
Per this mission's brief ("this check must NOT fall through shipping the violating text"), the
budget-exhaustion branch (`dialogue.py:352` onward) special-cases `output_isolation_*` violations:
instead of setting `fall_through=True` and shipping the last candidate, it substitutes a fixed,
generic, turn-agnostic neutral continuation (`_OUTPUT_ISOLATION_FALLBACK_RESPONSE`,
`dialogue.py:82` — "네, 말씀해 주셔서 감사합니다. 이어서 편하게 이야기 나눠 주세요.", no slot/clinical
content, no question) and sets a new `output_isolation_fallback: bool` field instead
(`schemas/dialogue.py`, threaded through `F1TurnLog.dialogue_output_isolation_fallback`,
`f1.py:219`/`1339`/`1590`/`1644`). `fall_through` and `output_isolation_fallback` are mutually
exclusive by construction — the former's field contract ("the violating text was shipped anyway")
would be false if set here. Verified:
`test_bug_037.py::TestBug037BudgetExhaustionShipsNeutralFallback` — 3 LLM calls total (no budget
inflation), `fall_through=False`, `output_isolation_fallback=True`, shipped text is the fallback
constant, never the leak. Known, disclosed, out-of-scope residual: the pre-existing retry-LLM-
exception branch (`dialogue.py`, unrelated to budget exhaustion — a network/parse failure mid-
retry) ships the last successfully-parsed candidate regardless of violation type, matching the
established `fall_through` telemetry-invariant precedent already documented for that branch in
`docs/ai/fix_design_bug030_iter2.md` §9; this mission's "on exhaustion" requirement is scoped to
the budget-exhausted branch specifically, not this separate, much rarer failure mode.

**Retry hint.** `_build_retry_hint` (`dialogue.py:729`) gained an `output_isolation` branch: for
`this_turn`/`prior_turn` it tells the model not to ship internal clinical-chart-register text and
to respond in natural conversational register instead; for `patient_echo` it tells the model not
to repeat the patient's own words back verbatim. Verified live in the retry-message assertions of
`test_bug_037.py`.

**CVR-012 F2 (patient-echo channel) — shared mechanism assessment: YES, folded in.** The bridge
note's second channel (`VP-010_20260712_141728_conversation.json` turn 7:
`assistant_response` verbatim-echoes the patient's own immediately-preceding denial) is
mechanistically the same defect class as the clinical-note leak: `assistant_response` shipping
some OTHER text verbatim instead of a genuine model-generated reply. The same containment/
equality primitive (`_matches`, inside `_output_isolation_violation`) and the same minimum-length
gate apply; only the comparison source differs (`patient_message` vs. `filled_slots`/
`slot_updates_this_turn` values). No separate check, no separate retry-budget consumption, no
separate exhaustion path was built — `patient_echo` is the 3rd priority tier of the SAME function
and SAME loop wiring. Verified live end-to-end against the real VP-010 turn 7 text:
`test_bug_037.py::TestCVR012F2PatientEchoSharedMechanism`.

**Regression surface.** Both fixes are additive (new optional input field with a safe `None`
default, new output fields with safe defaults) — no existing `DialogueInput`/`DialogueOutput`
construction site required changes, confirmed by the unmodified pass of
`tests/repro/test_session_state_allowlist.py` and the full existing `test_bug_030_iter2.py`/
`test_bug_029.py` suites. The single required regression-gate update was the standing BUG-022
field-allowlist exact-match test (`tests/repro/test_bug_022.py`), which mechanically forces a
reviewed acknowledgment of the new `DialogueInput.slot_updates_this_turn` field — done here, with
its licensing rationale recorded in that test file's own comment.

---

## §3. Fix 2 — as-implemented (Option C, ADR-030 Decisions 1–5)

**Ratified pick.** Option C (deterministic phrase-pool substitution + elevated review flag),
per `CVR-013` (3 binding conditions) and `REV-034` (marker-contamination requirement, splice
condition), reconciled in `ADR-030`. Implemented atomically with the test-hardening items in
ADR-030 Decision 5. No prompt file touched; dialogue v4 pin
(`f93e995f68e3a3bc88ddd5ce1f6b01ef8feb5e5663bda46ce4958ae8e6317144`) and safety v2 pin
(`3e9ca6b4...b390c`) untouched; zero extra LLM calls (retry budget stays 2 retries / 3 calls max
per turn — the degrade is post-exhaustion string surgery on the already-generated last candidate).

### Mechanism

`apps/ai-server/src/agents/dialogue.py`:

- **Shared boundary rule** — `_leading_clause_boundary` (module-level function, `dialogue.py:95`):
  index of the earliest `.`/`!` in a string, or `None` if the earliest terminal punctuation is `?`
  (bare-question opener) or none exists. `_extract_leading_clause` (`dialogue.py:602`, refactored,
  behavior-preserving) and the new `_splice_point` (`dialogue.py:622`) both delegate to it, so the
  two can never drift apart. `_splice_point` returns a raw index into the **unstripped** original
  string, so `text[end:]` is byte-identical to what the model generated — that index is the only
  thing a degrade is allowed to preserve verbatim from.
- **Pool** — `_EMPATHY_DEGRADE_POOL` (`dialogue.py:124`, 4 entries): `"이렇게 솔직하게 이야기해 주셔서
  감사합니다"`, `"편하게 마음을 나눠주셔서 감사합니다"`, `"그런 마음까지 들려주셔서 감사합니다"`,
  `"오늘 이야기 함께 나눠주셔서 감사합니다"`. All 4 are NORMALIZING/thanks-framed
  (`rubric_bug030_acceptance.md` §6 register category) — deliberately register-**neutral**, since
  `DialogueAgent` never receives `sentiment` (computed downstream in `f1.py`, after this call
  returns) and therefore has no runtime signal to match a DISTRESS/AFFIRMING register against; a
  wrong-register degrade would itself be a new §6 finding. Each phrase carries the `감사합니다`
  marker rubric §1 itself names as a characteristic empathic marker. Requirement 1(a) coverage:
  `tests/repro/test_fix2_exhaustion_degrade.py::TestPoolPhrasesSatisfySemanticEmpathyTest` (not a
  question, carries a rubric-cited marker, not a slot-content restatement, and — as a bonus
  consistency check, not itself rubric-required — also reads `is_empathy=True` under the
  production marker list). Requirement 1(c) coverage:
  `TestPoolPhrasesAreMutuallyDistinctFamilies` — every pairwise combination (all 4 pool entries
  plus `_OUTPUT_ISOLATION_FALLBACK_RESPONSE`'s own leading clause) is a **different** phrase family
  under `_same_phrase_family`, verified by direct pairwise computation.
- **Guard-drift exclusion (requirement 4 / REV-034 live finding)** — `_DEGRADE_MARKER_CLAUSES`
  (`dialogue.py:152`, a `frozenset` computed once at import time: the fallback response's own
  leading clause + all 4 pool phrases) and `_exclude_degrade_marker_clauses`
  (`dialogue.py:764`). `run()`'s `session_clauses` computation (`dialogue.py:348`) is now
  `self._exclude_degrade_marker_clauses(self._extract_used_empathy_clauses(...))` — any clause the
  SYSTEM itself shipped (Fix-2 pool substitution *or* Fix-3's `_OUTPUT_ISOLATION_FALLBACK_RESPONSE`)
  is excluded from the back-to-back/session-cap population, exact-string match only (both sources
  are fixed, closed, enumerable text). This closes REV-034's live finding for the **production**
  side only, per this mission's scope — `experiments/` scorer exclusion is a recorded pre-battery
  prerequisite (`ADR-030` Decision 4), not touched here. `_build_slot_context`'s X-list
  (`used_empathy`) is deliberately **not** filtered — showing a prior degrade phrase as "don't
  reuse this" to the model is harmless/desirable and out of REV-034's stated scope (guard drift,
  not the prompt hint). Verified:
  `TestGuardDriftExclusionAtRunLevel` (both the Fix-2-pool case and the original Fix-3-fallback
  case — a same-family candidate ships in exactly 1 call, proving the excluded clause is invisible
  to the guard).
- **Deterministic rotation (requirement 1(c))** — `_select_degrade_phrase` (`dialogue.py:778`):
  first pool entry not already present (exact match) among the RAW per-turn leading-clause
  extraction of `conversation_history` (not the guard-facing, degrade-excluded `session_clauses` —
  a prior degrade must remain visible to rotation even though it is invisible to the guard).
  Wraps to `pool[0]` once all 4 are used in one session (accepted last-resort residual). Verified:
  `TestSelectDegradePhraseRotation` (skip-already-used, wrap-around, 3-consecutive-degrades stay
  distinct).
- **Scope test (requirement 2)** — `_is_empathy_degradable` (`dialogue.py:806`): `True` for
  `presence_missing`, `exact_repeat`, and any `near_dup_*` reason; `False` for
  `output_isolation_*` (handled by Fix 3's own higher-priority exhaustion branch, checked first —
  `dialogue.py:414` before `dialogue.py:441`, so Fix 2 never sees an isolation violation).
- **Splice/prepend (requirement 2)** — `_degrade_empathy_clause` (`dialogue.py:820`): for
  `presence_missing`, always **prepends** (`f"{phrase}. {assistant_response}"` — no leading clause
  exists on this violation by definition, so there is nothing to replace and the entire original
  response ships as an untouched suffix). For `near_dup_*`/`exact_repeat`, **replaces** via
  `_splice_point`: `phrase + assistant_response[end:]` — everything from the original's own
  terminal punctuation onward is a direct slice of the model's last candidate, proven
  byte-identical per-path by
  `TestDegradeEmpathyClauseSplicing::test_{near_dup,exact_repeat}_replaces_leading_clause_byte_identical_remainder`.
  **Fail-safe (requirement 2's "never corrupt content" clause):** if `_splice_point` returns `None`
  at degrade time (no `.`/`!` boundary — a bare-question repeat, or a comma-joined single-sentence
  response whose only terminal punctuation is `?`), the mechanism falls back to prepend instead of
  guessing a boundary; still breaks `exact_repeat`'s byte-identical repetition (the shipped string
  changes) without touching a single character of the original. This fail-safe path is exercised
  against two **real, offline-spot-checked artifact shapes** (not synthetic-only), per CVR-013
  condition 3:
  - `docs/ai/simulation_results/VP-001/VP-001_20260711_223422_conversation.json` turn 5:
    `"지난번에 여쭤보지 못했는데, 과거 정신 건강 관련 진단이나 치료를 받으신 적이 있으신가요?"` —
    comma-joined, single sentence, only `?` terminal punctuation.
  - `docs/ai/simulation_results/VP-002/VP-002_20260711_220528_conversation.json` turn 3:
    `"현재 복용 중인 약이 어떤 종류인지, 그리고 처방받은 약 외에 추가로 드시는 약이 있는지
    알려주시겠어요?"` — same shape, independent second confirmation.
  Both are asserted against `_splice_point` (returns `None`) and `_degrade_empathy_clause` (fails
  safe to prepend, ships the full original byte-identical) in
  `TestSplicePointBoundaryRule`/`TestDegradeEmpathyClauseSplicing`.
- **`run()` wiring (requirement 2/3)** — the exhaustion dispatch (`dialogue.py:413` onward) now has
  3 branches in priority order: `output_isolation_*` (Fix 3, unchanged) → empathy-degradable
  (`dialogue.py:441`, new) → generic `fall_through` (unchanged code, now structurally unreachable
  under every currently-enumerated violation type — kept as a defensive catch-all per requirement
  3's own "on these paths" scoping, documented in-code). On the degrade branch: `retry_reasons`
  still records the exhausted violation (unchanged contract); `exhaustion_degrade` is set to that
  same violation string; `exhaustion_degrade_phrase` records which pool phrase was substituted;
  `fall_through` stays `False`. Verified end-to-end (not just the pure function) for all three
  empathy-degradable violation types: `TestNearDupExhaustionDegradesAtRunLevel`,
  `TestPresenceMissingExhaustionDegradesAtRunLevel` (crisis-adjacent, prepend path),
  `TestExactRepeatExhaustionDegradesAtRunLevel` (both the replace path and the fail-safe-prepend
  path), plus a non-interference regression for Fix 3's own path
  (`TestOutputIsolationExhaustionUnaffectedByFix2`).

### Telemetry (requirement 3 — elevated review flag)

`DialogueOutput` (`apps/ai-server/src/schemas/dialogue.py`) gains `exhaustion_degrade: str | None`
(the violation reason, e.g. `"near_dup_back_to_back"`) and `exhaustion_degrade_phrase: str | None`
(which pool phrase). `fall_through`'s docstring is updated to state the invariant explicitly:
**`fall_through`, `output_isolation_fallback`, and `exhaustion_degrade` are mutually exclusive by
construction** — the exhaustion dispatch is a single `if`/`elif`-shaped chain that `break`s after
exactly one branch runs per turn; `fall_through=True` is retained only as a defensive catch-all for
a hypothetical future violation type not yet routed to either safe-degrade path, and is
unreachable under today's 4 violation types (`output_isolation_*`, `presence_missing`,
`exact_repeat`, `near_dup_*`) — this is a deliberate redefinition-by-scoping, not a broken
guarantee (documented in the field's own description).

Threaded through `F1TurnLog` exactly like the other 6 dialogue-guard fields (same discipline,
`apps/ai-server/src/f1.py`): `dialogue_exhaustion_degrade`/`dialogue_exhaustion_degrade_phrase`
added to the dataclass, the per-turn reset block, the post-dialogue-call assignment, and the
`F1TurnLog(...)` construction call. Verified:
`TestF1TurnLogThreadsExhaustionDegrade` (both the populated case and the safe-defaults-on
non-guard-aware-construction case, mirroring the existing BUG-036/BUG-037 threading tests).

**Elevated-review surface (CVR-013 condition 1 — "an actually-reviewed surface, not a WARNING log
line").** Investigating the existing telemetry (`fall_through`, `output_isolation_fallback`,
`near_dup_detail`, `retry_reasons`) found that **none of it previously reached
`_build_checklist`/`_build_report`'s markdown output** — it only reached the raw `conversation.json`
dump via `asdict(result)`. Rather than ship the new flag into that same gap, `_build_checklist`
(`apps/ai-server/src/f1.py`) now surfaces the FULL dialogue-guard telemetry set (not just the new
field, since they share one underlying cause and the fix is a single, small, additive change): (1)
a session-summary table row — `"Empathy-degrade events (Fix 2 exhaustion) | N건 | sub-rules: ..."`
— giving a validator a one-line, skimmable "does this run need elevated review" signal across many
checklists in a battery; (2) a per-turn conditional line under "Per-Turn Agent Calls" —
`"Dialogue guard: retries=..., reasons=..., fall_through=..., output_isolation_fallback=...,
exhaustion_degrade=..."` (plus the substituted phrase when set) — only emitted when at least one
guard signal fired that turn, mirroring the existing conditional `slot_discards` line's idiom.
Verified: `TestChecklistSurfacesExhaustionDegrade` (populated and zero-degrade cases).

### Pool contents (for quick reference)

| # | Phrase | Register (rubric §6) |
|:--|:--|:--|
| 1 | 이렇게 솔직하게 이야기해 주셔서 감사합니다 | NORMALIZING/thanks-framed |
| 2 | 편하게 마음을 나눠주셔서 감사합니다 | NORMALIZING/thanks-framed |
| 3 | 그런 마음까지 들려주셔서 감사합니다 | NORMALIZING/thanks-framed |
| 4 | 오늘 이야기 함께 나눠주셔서 감사합니다 | NORMALIZING/thanks-framed |

### Test hardening (ADR-030 Decision 5)

- **BUG-036 run()-level wiring** — `tests/repro/test_fix2_exhaustion_degrade.py::
  TestBug036RunLevelWiring`: a compact A-C-A-B history (2 non-adjacent same-family uses split by a
  distinct clause, distinct clause immediately preceding the candidate) driven through `agent.run()`
  end-to-end, isolating exactly the regression class the old exact-string dedup missed
  (`prior_family_count` undercounted to 1 instead of 2). `test_bug_036.py`'s own tests remain
  pure-function-level (unchanged, still valuable for their artifact-fidelity coverage); this new
  test adds the run()-level proof REV-034 flagged as missing.
- **`test_x_list_shows_distinct_phrases_only` upper-bound fix** — `tests/repro/test_bug_036.py`:
  changed `<= 1` to `== 1` (plus a non-vacuousness `len(x_lines) >= 1` guard), so a regression that
  silently empties the X-list is caught rather than passing vacuously.
- **Sub-15-char SI-content collision** — `tests/repro/test_fix2_exhaustion_degrade.py::
  TestSubMinLengthSIContentCollision`: documents (does not change) the existing
  `_MIN_OUTPUT_ISOLATION_LEN=15` boundary — an 8-char SI-content slot value leaking into the
  response is NOT caught (the min-length gate that prevents short-string coincidental collisions
  also, as a side effect, misses short genuine leaks); a ≥15-char SI value at the same shape IS
  caught. A threshold change is out of Fix 2's scope and would need its own review — this test
  exists so any future change to that constant is a deliberate, reviewed decision.
- **Splice-boundary / comma-joined-sentence coverage** — see "Fail-safe" above; 2 real artifacts
  cited and spot-checked offline, satisfying CVR-013 condition 3.

### CF1 disposition (CVR-014 finding, post-implementation fix)

**Finding.** `CVR-014` (clinical-validator, quoted): the 2 fail-safe artifacts §3
originally cited (VP-001 turn 5, VP-002 turn 3) are both single-question shapes
terminated only by `?` — `_splice_point` returns `None` for both, exercising only
the already-safe prepend branch. CVR-014 independently found a DIFFERENT, untested
shape live: `docs/ai/simulation_results/VP-003/
VP-003_20260711_222843_conversation.json` turn 7 (`safety_risk="medium"`) —
`"지난번에 여쭤보지 못했는데, 과거에 정신건강의학과 진료나 진단을 받으신 적이
있는지 궁금합니다. 그리고 혹시 현재 다른 신체질환이나 복용 중인 약이 있는지
여쭤봐도 될까요?"` — a comma-joined psychiatric-history probe terminated by its OWN
`.` before a SECOND, later `?`. Risk as stated: if `near_dup`/`exact_repeat` ever
fires on this shape at exhaustion, the probe content is silently deleted.

**Verified real, not theoretical.** Reproduced against the pre-fix production code
(`apps/ai-server/tests/repro/test_fix2_exhaustion_degrade.py::
TestCF1TwoQuestionShapeNeverDeletesClinicalContent`, `TestCF1ExactRepeatExhaustionAtRunLevel`):
`_splice_point` returns a valid index (the `.`, at offset 52) because it exists
earlier in the string than the trailing `?` — `_leading_clause_boundary`'s rule is
"earliest of `.`/`!`/`?`; `None` only if that earliest one is `?`", so a SECOND,
later `?` after an earlier `.` never suppresses the boundary. The span before that
index is the full first CLINICAL question, not an empathy clause, and pre-fix
`_degrade_empathy_clause` replaced it unconditionally whenever a splice point
existed — with no check that the span it was about to delete actually read as
empathy content. Confirmed reachable via `exact_repeat` end-to-end through
`agent.run()`; `near_dup_*` cannot reach this exact shape in production
(`near_dup_reason` is only computed when `is_empathy` already holds for the
candidate's own leading clause, which this shape never satisfies), so the
`near_dup` coverage in the cited tests is a function-level invariant / defense-in-
depth against a future caller, not a currently-reachable `run()` path.

**Fix.** `_degrade_empathy_clause` (`apps/ai-server/src/agents/dialogue.py`) now
gates the replace branch on `_is_empathy_clause(leading_span)` — the SAME semantic
test the guard itself uses to decide whether a candidate's leading clause is
empathy content in the first place. Replace fires only when `_splice_point` finds a
boundary AND the span before it is empathy content; otherwise (no boundary, or a
boundary whose span fails the empathy test) the mechanism falls back to prepend —
never deletes content in either case. This tightens, not loosens, the hard
constraint stated at the top of this section: the two original fail-safe artifacts
still fail safe via the `None`-boundary branch (unaffected by the new gate); the
CF1 shape now additionally fails safe via the new empathy-test gate. No behavior
change for the two already-tested replace paths (`near_dup`/`exact_repeat` on a
genuinely empathic leading clause), since a candidate's leading clause that already
passed the guard's own `is_empathy` check trivially passes the same test again
here.

**Verification.** 3 new tests
(`TestCF1TwoQuestionShapeNeverDeletesClinicalContent`,
`TestCF1ExactRepeatExhaustionAtRunLevel`) — 2 direct-call invariant tests
(`exact_repeat`, `near_dup_back_to_back`) plus 1 end-to-end `agent.run()` test
driving 3 identical CF1-shaped responses through the `exact_repeat` exhaustion
path — all assert the full probe text ships intact (prepended, never replaced).
Full suite: `ruff check .` clean; `pytest tests/ -q` — 1236 passed, 2 skipped (was
1231 passed, 2 skipped before this fix; +5 new tests, zero regressions).

### Residual, documented (not fixed, out of scope)

- Repeated **question/clinical content** on `exact_repeat` exhaustion (the trailing question itself
  can still repeat verbatim across turns — BUG-028/BUG-033 territory, rubric §5b) — Fix 2 only ever
  touches the leading empathy clause, by the hard constraint itself.
- The pre-existing mid-retry-exception branch (`dialogue.py`, a network/parse failure during a
  retry call, unrelated to budget exhaustion) still ships the last successfully-parsed candidate
  regardless of violation type — unaffected by Fix 2, same as it was for Fix 3 (§2 above).
- `experiments/` scorer exclusion for `exhaustion_degrade`/`output_isolation_fallback`, criterion-D
  telemetry-invariant extension, and the REV-033 criterion-A stem-level clustering backport are
  **pre-battery prerequisites** for the deferred F1–F5 total validation (`ADR-030` Decision 4) —
  explicitly out of this mission's scope; not touched.
