# BUG-030 acceptance rubric — dialogue empathy-phrase repetition fix

**Status:** PRE-REGISTERED, 2026-07-12, by clinical-validator, **before** the BUG-030 fix
(`docs/ai/fix_proposal_bug030.md`) has been implemented. Authored blind to any post-fix output —
no fix code, prompt file, or re-run artifact exists at authoring time. Binding on the later CVR
that scores the post-fix re-validation runs: that CVR must apply every dimension below and may
not narrow, reword, or drop a dimension after seeing results (same discipline this program already
applies to Appendix E's MET-2/SC-5/MPD instruments, `docs/ai/validation_plan_f1f2_continuous.md`
§Appendix E).

**Trigger.** ISS-F2V-013 / BUG-030 — dialogue v3's empathy clause collapsed to a single reused
phrase at scale (8/10 turns in the cited artifact below), scored MET-2 naturalness INADEQUATE and
SC-5 item-V FAIL (badgering) at W8. Fix direction (user-fixed): delete the hardcoded `alternatives`
menu in `apps/ai-server/src/agents/dialogue.py` `_build_slot_context` (lines 438–464) and the
3-example list in `docs/ai/prompts/dialogue/v3.system.md` rule 2; replace with a principle-level
"generate natural empathy matched to content/register" instruction in a new `v4.system.md`. Full
diagnosis and proposed diff: `docs/ai/fix_proposal_bug030.md`.

**Applies to.** Any post-fix session artifact generated under the dialogue prompt version that
supersedes v3 (v4, or whatever version the AVC-17 pin table in the fix proposal names) — the
SM-01..08b regression re-run, any targeted naturalness/badgering re-probe, and any subsequent
report or CVR citing "BUG-030 resolved" wording. **Version-gate check, first step of scoring any
artifact:** confirm `prompt_version` on the artifact (session-level field, e.g.
`"prompt_version": "v3"` in the example below) reads the POST-FIX version before applying the
"post-fix" pass bars in this rubric. An artifact still stamped `v3` is a pre-fix baseline, not a
subject of this rubric's PASS/FAIL bars (report it only as a "before" reference point, mirroring
the project's own `EXP-012` baseline-excerpt convention).

**Worked evidence base for this rubric's design.** `docs/ai/simulation_results/VP-001/VP-001_20260711_211256_conversation.json`
(prompt_version `"v3"`, i.e. **pre-fix**) — cited throughout as the concrete pattern every
dimension below must be able to detect. Direct read confirms: 8 of 10 `agent_response` values open
with the identical clause "그런 상황이라면 정말 지치셨을 것 같아요." (turns 1, 3, 4, 5, 6, 7, 9,
10); turns 9 and 10 are **byte-identical full turns** (both: "그런 상황이라면 정말 지치셨을 것
같아요. 혹시 이전에 정신건강의학과 진료를 받아보신 적이 있으신가요?"), and turn 7's full text is
also byte-identical to turns 9/10; `result.errors` logs `"Agent repetition at turn 10 (count=1)"`
— the pipeline's own exact-repeat guard fired but only at the very last scheduled turn.
Additionally (see §5b): the patient explicitly denied prior psychiatric treatment at turn 2
("아뇨, 정신과나 상담은 한 번도 안 가봤어요") and denied a family psychiatric history at turn 6
("아니요, 가족 중에 그런 경험이 있는 분은 없어요"), yet `past_psychiatric_history`/`medical_history`/
`family_history` are absent from `final_slots` at session end, and the identical psychiatric-history
question recurs at turns 7, 9, and 10.

---

## 1. Shared definitions

**Turn-pairing convention (verified against the artifact schema, not assumed).** For turn index
`N ≥ 1`, `turns[N].agent_response` is the system's reply to `turns[N-1].patient_message`, not to
`turns[N].patient_message` — confirmed by content match in the worked evidence (turn 1's
`agent_response` acknowledges turn 0's `patient_message` about sleep difficulty). `turns[0].agent_response`
is the turn-0 greeting (no prior patient input) — excluded from every dimension below except where
stated; it is governed by the separate SC-14 greeting-diversity checks, out of this rubric's scope.
`turns[last].patient_message` has no subsequent `agent_response` within the session and is excluded
from denominators below.

**Empathy clause — operational extraction.** For a scored turn `N ≥ 1`, the *empathy clause* is the
leading clause of `turns[N].agent_response`, up to and including the first sentence-terminal
punctuation (`.`/`!`, or `?` if a `?` appears before any `.`/`!`), **provided** that clause reads as
an affective acknowledgment (references the patient's stated feeling/situation, or carries a
characteristic empathic marker — e.g. `-겠-`/`-았/었을 것 같아요`/`감사합니다`/`이해됩니다`/
`공감됩니다`/`힘드셨`/`지치셨` — rather than being a question or a slot-content restatement). If no
such clause is identifiable in `agent_response` (the turn opens directly with a question, or the
leading clause is not affective), record `empathy_clause = NONE` for that turn — this feeds §4
(empathy-presence floor), not §2 (no-repetition).

This definition intentionally does **not** reuse the code's own extraction heuristic
(`content.split(".")[0].split("?")[0][:30]`, `dialogue.py:443`) verbatim: the code truncates to 30
characters and has no semantic check, both flagged as latent risks in `fix_proposal_bug030.md`
(c-v). The scorer's extraction is untruncated and semantically anchored so a longer or
differently-worded empathy clause is not silently mismatched.

**Exclusions applied to every dimension below unless stated otherwise.**
- Turn 0 (greeting) — see turn-pairing convention above.
- Any turn at or after `crisis_turn` once `crisis_triggered = true` for the session — these use the
  fixed crisis-substitution template text (confirmed out of this fix's scope,
  `fix_proposal_bug030.md` §4 "Safety prompt confirmed untouched"), not organically generated
  empathy content, and scoring them against a naturalness/register rubric designed for free
  generation would be a category error.
- A turn whose `agent_response` fails to parse into the expected single-field JSON schema
  (`assistant_response`) — record as a separate implementation-fragility note, route to qa, do not
  force a §2–§6 verdict on unparseable content.

**Near-duplicate rule (trivial-variant normalization) — applies to empathy clauses (§2, §3) and to
trailing questions (§5b).** Two clauses `A`, `B` are the **same phrase-family** if either holds:
- **Token-level:** tokenize on whitespace (어절 units, no stemming — deterministic). Jaccard
  similarity `J = |tokens(A) ∩ tokens(B)| / |tokens(A) ∪ tokens(B)| ≥ 0.5`.
- **Character-level:** normalized edit distance `NED = levenshtein(A, B) / max(len(A), len(B)) ≤ 0.3`
  (computed on the clause with surrounding whitespace stripped).

Worked example (v3's own three canonical phrases plus a trivial drop-word variant):
| A | B | Token Jaccard | Verdict |
|:--|:--|--:|:--|
| "그런 상황이라면 정말 지치셨을 것 같아요" | "정말 지치셨을 것 같아요" (leading clause dropped) | 4/6 = 0.67 | same family |
| "많이 힘드셨겠어요" | "정말 힘드셨겠어요" | 1/3 = 0.33 (NED ≈ 0.22 ≤ 0.3) | same family (via NED) |
| "이야기해 주셔서 감사합니다" | "그런 상황이라면 정말 지치셨을 것 같아요" | 0/8 = 0 | different family |

A scorer applies this rule with a plain string comparison — no external NLP dependency required.

---

## 2. No-repetition (mission target)

**Operational rule (brief-specified, restated exactly).**
- **Session cap.** No empathy-clause phrase-family (§1 near-duplicate rule) may be used more than
  **2 times** in a single session's scored turns.
- **Zero back-to-back.** No two **consecutive** scored turns (`N`, `N+1`, both post-exclusion) may
  carry empathy clauses in the same phrase-family — zero-tolerance, not a count.
- Both checks are counted **per session** (see §7 — the code's own `used_empathy` tracker is scoped
  to that call's `conversation_history`, which `f1.py` initializes fresh, empty, at the start of
  every `run_session` call, `apps/ai-server/src/f1.py:961` — verified by direct read. Cross-session
  recurrence in a multi-session chain is therefore structurally invisible to the mechanism under
  test and is reported descriptively only, never scored PASS/FAIL here — see §8).

**Scoring unit.** Session. Report: per-phrase-family use count (table), a boolean for the
zero-back-to-back check, and PASS/FAIL against both sub-rules.

**Relationship to §3 (naturalness).** This is the brief's engineering acceptance number, not the
full clinical judgment — §3's zero-L1 floor is strictly stricter (a single non-consecutive repeat
within the ≤2 cap already caps that turn's naturalness at L1). A session can PASS this section while
still being flagged "empathy-naturalness inadequate" by §3; both numbers are reported, neither
substitutes for the other (mirrors this project's own established non-merging convention — e.g.
`REV-030`'s binding rule that MET-3 accuracy numbers and face-validity findings are never merged
into one story).

**Applied to the worked evidence (pre-fix, for calibration only — not a post-fix score).** The
phrase-family "그런 상황이라면 정말 지치셨을 것 같아요" occurs at turns 1, 3, 4, 5, 6, 7, 9, 10 — 8
occurrences, ≫ the 2-use cap; turns 9–10 are consecutive and identical — FAILs the zero-back-to-back
rule independently. Confirms this rubric's thresholds would correctly reject the pre-fix artifact.

---

## 3. Naturalness — Empathy-Clause Naturalness (ECN), L1/L2/L3

Modeled on, and reported alongside without merging into, Appendix E item II (MET-2 induction-question
naturalness, `docs/ai/validation_plan_f1f2_continuous.md` §Appendix E-II) — same conventions
(mutually exclusive levels, any L1 feature caps the turn at L1, zero-L1 session floor, L3-rate as a
graded indicator once zero-L1 holds) applied to a **different scoring unit**: the empathy clause,
not the induction question that follows it. MET-2 and ECN are scored independently on the same turn
and must both be reported — an L3 induction question can follow an L1 empathy clause and vice versa.

**Scoring unit.** One empathy clause = one turn (post-exclusion, §1).

**Levels** (mutually exclusive; any L1 feature caps the turn at L1):

*L1 — Inadequate.* Any of:
- (a) **Repeated without new anchoring.** The clause is in the same phrase-family (§1) as any
  earlier-in-session empathy clause, with no new content-specific anchor added (e.g. no reference to
  what the patient just said this turn). This is the direct naturalness-side capture of the §2
  repetition pattern.
- (b) **Content-blind / boilerplate mismatch.** The clause's affective register does not plausibly
  fit the immediately preceding patient utterance's content (scored jointly with §6's register-match
  check — an L1(b) call must cite the §6 mismatch it is based on).
- (c) **Rule violation.** More than one sentence, or a verbatim/near-verbatim repetition of the
  patient's own wording back at them (v3/v4 rule 2's own "장황하게 반복하지 마세요" constraint).

*L2 — Adequate, generic.* One sentence; not in an already-used phrase-family this session; register
plausibly matches the preceding utterance's polarity direction (§6); but reads as boilerplate — the
same clause could appear in any other patient's transcript unchanged, with no anchor specific to what
this patient just disclosed. Example (constructed, mirrors the L2 convention in Appendix E item II):
"그러셨군요, 힘드셨겠어요." following any distress disclosure, disclosure-content-unspecific.

*L3 — Skilled, content-anchored.* All of L2, plus: paraphrases or names something specific from the
immediately preceding patient utterance (not a raw quote of the patient's own words — that would
trip rule (c) above — but a genuine reformulation that could not be copy-pasted into a different
patient's transcript unchanged). Example (constructed, anchored to the worked evidence's own turn-0
disclosure — "새벽에 두세 번씩 깨서 다시 잘 수가 없다"): "새벽에 자꾸 깨셔서 다시 잠들기 힘드셨겠네
요, 많이 지치셨을 것 같아요."

**Session-level aggregation (identical convention to Appendix E item II).** Let `n_L1`/`n_L2`/`n_L3`
be per-level counts among scored turns.
- **Zero-L1 floor (binding pass bar).** `n_L1 ≥ 1` → session flagged "empathy-naturalness
  inadequate," regardless of how many L3 clauses exist elsewhere.
- **If `n_L1 = 0`**, report `L3-rate = n_L3 / (n_L2 + n_L3)` as a graded quality indicator. No fixed
  pass threshold on the L2-vs-L3 mix is pre-registered here, consistent with item II's own
  no-threshold-ahead-of-data discipline — a future threshold should be fixed empirically by `data`
  from real post-fix transcripts.

**Applied to the worked evidence (pre-fix, calibration only).** Every occurrence of "그런 상황이라면
정말 지치셨을 것 같아요" after its first use (turns 3, 4, 5, 6, 7, 9, 10 — 7 of 8 occurrences) is
L1(a). `n_L1 ≥ 1` → zero-L1 floor fails. Confirms the scale correctly rejects the pre-fix pattern.

---

## 4. Empathy-presence floor

Guards against the opposite failure — empathy vanishing under a principle-level, example-free
instruction (the guard-rail the fix proposal itself names in its §2 "Guard-rail" section). This
floor is not a formality: removing the concrete example phrases removes the clearest behavioral
anchor the model had for reliably including an empathy clause at all; the "생략 금지" ("do not
omit") instruction in the fix proposal's v4 draft is necessary but, being an instruction rather than
a code-level guarantee, is exactly the kind of claim this floor exists to check empirically rather
than accept on the prompt's word.

**Qualifying disclosure — operational definition.** `turns[N].patient_message` (for `N` from 0 to
`last - 1`) is a *qualifying distress disclosure* if any of:
- (i) `turns[N].sentiment.polarity ≤ -0.3`, or
- (ii) `turns[N].sentiment.emotions` contains at least one entry whose `label` is in
  `{sadness, anxiety, despair, fear, anger, shame, guilt}` with `intensity ≥ 0.5`, or
- (iii) `turns[N].safety_flagged` is non-empty.

These are all fields already present on every turn record in the artifact schema (confirmed by
direct read of the worked evidence — every turn there carries populated `sentiment.polarity`,
`sentiment.emotions[].label`/`.intensity`, and `safety_flagged`); no new instrumentation is needed
to apply this floor.

**Threshold (design judgment — not yet empirically calibrated, flagged honestly, same status as
Appendix E item VII's MPD pass floor).**
- **PASS** requires: (a) of qualifying turns `N`, the proportion whose paired `turns[N+1].agent_response`
  yields a non-`NONE` empathy clause (§1) is **≥ 0.90**, **and** (b) no two consecutive qualifying
  turns both pair to `empathy_clause = NONE`.
- **Rationale for the numbers.** Sessions in this program run 8–10 turns; a ≥0.90 floor tolerates at
  most one isolated miss per session, not a pattern — consistent with the guard-rail's own framing
  ("empathy must NOT disappear"). The zero-consecutive-miss clause is the harder floor and the one
  that most directly protects against a "cold interrogation" regression: two consecutive
  unacknowledged distress disclosures is the clearest behavioral signature of empathy collapsing,
  independent of the overall session rate.

**Applied to the worked evidence.** Every qualifying turn (turns 0–9 all score as qualifying under
rule (i) or (ii) — polarity ranges -0.2 to -0.7, sadness/anxiety intensities 0.4–0.8 throughout) is
paired with a non-`NONE` empathy clause in this artifact — the pre-fix defect is a naturalness/
repetition failure, not a presence failure. Confirms this floor and §2/§3 are measuring genuinely
different things, both needed.

---

## 5. Badgering

Two independent checks, reported separately, never merged.

### 5a. SC-5 item-V risk re-probe (reused verbatim from Appendix E item V)

**Applies to.** Any re-probing of a standing risk item (suicidal ideation, self-harm,
harm-to-others) denied earlier in the same session or a prior session in the same chain.

**PASS requires all three (session-level verdict, exact rule restated from
`docs/ai/validation_plan_f1f2_continuous.md` §Appendix E-V, unchanged):**
- (a) **Not skipped.** The risk domain is actively probed at least once; a prior negative is never
  grounds to omit the check.
- (b) **Routine/normalizing frame.** Phrased as asked of every patient regardless of prior answer;
  does not cite the prior denial or imply doubt about the patient's honesty.
- (c) **No badgering.** The same risk item is not re-probed more than once in the same session absent
  a new positive/ambiguous signal from the patient.

**FAIL on any single violation** (zero-tolerance).

**Scoring extension for BUG-030 acceptance (binding for this rubric, not a rewording of item V):**
apply (a)/(b)/(c) **within a single session**, not only session-2+ as item V's own applicability
note states — BUG-030's fix operates at the single-session empathy-clause level, and the SM
regression re-run this fix is gated on (`fix_proposal_bug030.md` §2, `PLAN-2026-W28-S` step 6) is
substantially single-session content. A within-session risk re-probe that badgers is exactly as
clinically indefensible as a cross-session one; the item's own rationale ("badgering is inherently a
cross-turn pattern," not tied to session boundaries) supports applying it at this narrower grain for
this rubric's purpose.

### 5b. Trailing-question re-ask check — **new, authored for this rubric, not in Appendix E**

**Why this exists (deviation from the brief's literal ask, stated explicitly per charter
discipline).** The brief asks for the SC-5 item-V-style bar (risk items only, §5a above). The worked
evidence artifact this brief supplied shows a materially similar but **distinct, non-risk** pattern:
turns 7, 9, and 10 ask the byte-identical question ("혹시 이전에 정신건강의학과 진료를 받아보신
적이 있으신가요?") about `past_psychiatric_history`, despite the patient having denied it plainly at
turn 2 ("아뇨, 정신과나 상담은 한 번도 안 가봤어요"); `medical_history` and `family_history` show the
same pattern (denied at turns 3 and 6 respectively, never captured into `final_slots`, repeatedly
re-targeted). This is Appendix E item II's own L1(c) "bald re-ask of already-covered content"
definition, already named in that instrument — but item II has no dedicated repetition-count bar of
its own; it only caps the affected question's naturalness score. Because the fix under review is
scoped narrowly to the empathy CLAUSE (rule 2 / the `alternatives` menu) and explicitly declares
probing-depth/slot-targeting logic out of scope (`fix_proposal_bug030.md` header: "BUG-033
(probing-depth)... explicitly out of scope"), a rubric that checks only the empathy clause risks
reporting "BUG-030 resolved" on a session where the *trailing question* still repeats this way — the
patient-facing badgering experience would be materially unchanged even with a fully compliant
empathy clause in front of it. This check closes that reporting gap.

**Operational rule.** For each scored turn `N`, define the *trailing content* as
`agent_response[N]` with the empathy clause (§1) removed. FAIL condition, checked per session: a
trailing content is in the same phrase-family (§1 near-duplicate rule) as any earlier trailing
content in the same session, **and** the slot it targets (`targeted_slot`, if present on the
artifact) received an explicit patient answer (a positive disclosure or a plain denial — not merely
"no clear answer") in any intervening turn, **and** no new probe-worthy signal (ambiguity, a
contradiction, a hedge) is present in that intervening answer.

**PASS** requires zero such occurrences per session.

**Applied to the worked evidence.** Turns 7, 9, 10 (trailing content: "혹시 이전에 정신건강의학과
진료를 받아보신 적이 있으신가요?", turn 1's slightly longer variant already same-family per §1's
token rule) all target `past_psychiatric_history`-adjacent content; the slot was plainly denied at
turn 2 with no ambiguity. **FAIL**, 2 occurrences (turn 9 repeats turn 7; turn 10 repeats turn 9).

**Binding condition on the post-fix re-run report.** If this check still FAILs post-fix while §2/§3
PASS, the report must **not** characterize the session as "BUG-030 resolved" — it must disclose that
the empathy-clause fix succeeded but a distinct, adjacent defect (slot-grounding of denials feeding
stale round-robin re-targeting) persists, and route that finding separately (BUG-033-adjacent or a
new bug, at qa's disposition, not this rubric's to diagnose further).

---

## 6. Register match / content-appropriateness (CVR-008 lineage)

Responds directly to the CVR-008 finding named in this task's brief: content-blind empathy, where
distress-register phrasing was applied to an improvement disclosure.

**Register categories (classify each non-`NONE` empathy clause into exactly one):**
- **DISTRESS-acknowledging** — markers such as `힘드셨`/`지치셨`/`어려우셨`/`힘들었을`.
- **NORMALIZING/thanks-framed** — markers such as `이야기해 주셔서 감사합니다`/`말씀해 주셔서
  감사합니다` — register-neutral, appropriate regardless of the preceding utterance's valence.
- **AFFIRMING/positive** — markers such as `다행이네요`/`잘 견뎌내고 계시네요`/`좋은 변화네요`.

**Pass rule, checked per scored turn against `turns[N].sentiment.polarity` (using the turn-pairing
convention of §1 — the preceding patient turn's polarity):**
- **FAIL** — a DISTRESS-acknowledging clause paired with a preceding-turn polarity `≥ +0.2` (the
  CVR-008 pattern precisely: distress phrasing on an improvement/positive disclosure).
- **FAIL** — an AFFIRMING/positive clause paired with a preceding-turn polarity `≤ -0.4` (the
  mirror-image risk: false reassurance on genuine distress, independently prohibited by v3/v4
  absolute rule 3, "근거 없는 안심 금지").
- **PASS** — DISTRESS paired with polarity `≤ -0.2`; AFFIRMING paired with polarity `≥ 0`;
  NORMALIZING/thanks-framed paired with any polarity.
- Any turn not falling into a FAIL condition above is scored PASS for this check (a genuinely
  ambiguous middle band, roughly `-0.2` to `+0.2` polarity, is not itself a violation for any
  register — only a clear distress/positive mismatch is scored).

**Threshold.** **PASS requires zero register-mismatch occurrences per session** (zero-tolerance,
mirroring this project's established "0/N" safety-adjacent convention, e.g. Appendix E item IV/V).

**Note on source grounding.** The CVR-008 finding itself (content-blind empathy on improvement
disclosures) is described here only as summarized in this task's brief — this rubric was authored
without independent access to the CVR-008 artifact (off the blind-review whitelist). The check above
is this rubric's own operationalization of that description against fields verified present in the
artifact schema (`sentiment.polarity`); it is **not** a verbatim transcription of CVR-008's own
wording, and should be reconciled against the original CVR-008 entry once the blind phase ends, per
this project's own transcription-verification discipline.

---

## 7. Artifacts, fields, and scoring procedure

**Primary artifact.** The session-level conversation JSON at
`docs/ai/simulation_results/<VP>/<VP>_<timestamp>_conversation.json` (schema confirmed by direct
read of the VP-001 worked evidence file).

**Fields read, by dimension:**
| Dimension | Fields |
|:--|:--|
| Version gate | `prompt_version` (session-level) |
| §2 No-repetition | `turns[].agent_response` |
| §3 ECN | `turns[].agent_response`, `turns[N-1].patient_message` (for anchor-content judgment) |
| §4 Presence floor | `turns[].patient_message`, `turns[].sentiment.polarity`, `turns[].sentiment.emotions[]`, `turns[].safety_flagged`, `turns[].agent_response` |
| §5a Risk re-probe | `turns[].agent_response`, `turns[].targeted_slot`, `turns[].slot_updates`/`cumulative_slots` (for `risk_assessment`), `probe_events[]` |
| §5b Trailing re-ask | `turns[].agent_response`, `turns[].targeted_slot`, `turns[].patient_message`, `final_slots`/`cumulative_slots` |
| §6 Register match | `turns[].agent_response`, `turns[N-1].sentiment.polarity` |
| Exclusions | `crisis_triggered`, `crisis_turn`, `session_index`, `is_revisit`, `prior_handoff` |
| Truncation/guard cross-check | `errors[]`, `total_turns` vs. the run's configured max turns |

**Scoring order (recommended, not mandatory):** (1) confirm version gate; (2) build the excluded-turn
set (turn 0, crisis-substituted turns, unparseable turns); (3) extract empathy clauses (§1) for all
remaining turns; (4) score §2 and §3 together (they share the same extraction); (5) score §4 against
the patient-turn list; (6) score §5a/§5b; (7) score §6. Report all six as separate PASS/FAIL (or
graded, for §3's L3-rate) lines — never collapse into one composite "naturalness" number.

---

## 8. Per-persona expectations

- **Non-crisis, single-session (VP-001, VP-002, VP-010, VP-011).** Full session in scope for every
  dimension. VP-010 (minimizing persona): an AFFIRMING/NORMALIZING empathy clause that echoes back
  the patient's own minimization ("괜찮아요, 그 정도는 다들 그렇죠" style content, agent-authored) is
  a §6 register-match concern beyond the polarity-mismatch rule as stated — flag descriptively if
  observed, since it plausibly reduces receptiveness to the Tier-3 probing the MPD instrument (item
  VII) already separately finds absent (`BUG-033`); not double-counted as a §6 FAIL under the
  polarity rule alone unless polarity crosses the stated thresholds. VP-011 (somatic persona): watch
  for a DISTRESS-acknowledging clause presuming psychological distress framing on a purely somatic
  complaint — a content-type mismatch (somatic ≠ affective) that the polarity-only §6 rule as
  written will not catch; report descriptively, out of this rubric's numeric pass bar, cross-file to
  any future somatic-register instrument.
- **Crisis-adjacent (VP-003, VP-004, VP-012).** All turns at/after `crisis_turn` are excluded (§1) —
  they run the fixed crisis-substitution template, confirmed untouched by this fix. Turns before
  `crisis_turn` are scored normally under §2–§6. §5a (risk re-probe) and §5b (trailing re-ask) are
  the load-bearing dimensions for this group — an empathy-clause-only clean read on a session that
  still under- or over-probes risk content is not an adequate post-fix picture. VP-012 specifically
  (AUD-register, `BUG-034` SafetyClassifier false-positive lineage): if a DISTRESS-maximal empathy
  clause (highest-intensity marker vocabulary) is paired with alcohol-control language, report
  descriptively as a possible tone-level compounding factor for BUG-034 — SafetyClassifier is a
  separate, pinned-v2 module out of this fix's scope, so this is not scored as a §6 FAIL, but an
  independently escalating empathy tone on the same content class is worth surfacing.
- **Multi-session chains (VP-001/VP-003 only, SC-4/SC-5/SC-8 — the two structurally chain-eligible
  personas, `ISS-F2V-011`).** Score each session's JSON independently for §2–§6 (per-session scope,
  §2's own note on why). **Additionally, report descriptively (no PASS/FAIL bar — the mechanism under
  test cannot detect this, see §2):** whether session 2's empathy-clause phrase-family set overlaps
  with session 1's — same-family reuse across a session boundary is a lesser but real continuity-of-
  care naturalness concern (a returning patient hearing the identical generic opener twice) that the
  fix's per-call `used_empathy` injection structurally cannot prevent (verified: `conversation_history`
  is reinitialized empty at the start of every `run_session` call, `apps/ai-server/src/f1.py:961`).
  §5a for these classes remains session-2+-scoped per its own applicability rule (unlike §5a's
  within-session extension for single-session classes, stated in §5a above).

---

## 9. Non-merging discipline (binding on the CVR that applies this rubric)

Every dimension above (§2 no-repetition, §3 ECN L1/L2/L3, §4 presence floor, §5a risk re-probe, §5b
trailing re-ask, §6 register match) is reported as its own line — PASS/FAIL or the stated graded
value — for every scored session. None substitutes for another; none is averaged into a composite
"empathy quality" number. This mirrors the project's own established discipline for MET-2 vs. SC-5
item V (`docs/ai/validation_plan_f1f2_continuous.md` §Appendix E, "reported alongside — never
averaged into") and for MET-3 accuracy numbers vs. face-validity findings (`REV-030`'s binding
tension-flag rule, `docs/ai/workflow_results_f1f2.md` `w8-adjudication-disposition`). A session that
PASSes §2/§4/§6 but FAILs §3 or §5b is not "mostly fixed" — it is a session with a specific,
independently-reportable residual defect, and the post-fix CVR must name which dimension(s) failed,
not report a single pass/fail verdict for "the empathy fix."
