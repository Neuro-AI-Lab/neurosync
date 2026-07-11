# F1–F2 continuous-scenario validation — issues and solutions log

> **Purpose:** one entry per issue encountered during program execution, paired with its solution. Issues anticipated by `PLAN-2026-W28-P` answer #7 — "new issues are expected to surface during validation," disclosed as an expected outcome of the F1-wide review framing, not a plan defect (`docs/ai/validation_plan_f1f2_continuous.md` §1, §3, §9 answer #7) — land here first, as an `ISS-F2V-NNN` row, before being formally filed as a `BUG-`/`VAL-`/`CVR-`/`REV-` entry in the appropriate root doc and cross-referenced back.
> **Monitoring surface:** this doc is part of the user's primary monitoring surface (plan §2 invariant 6) and SURVIVES the blind-state reset (plan §7 survival whitelist) — a scope extended to this doc by the user's 2026-07-11 mid-execution directive (`discussion.md` `PLAN-2026-W28-Q`, "Status (2026-07-11, mid-execution user directive — folded immediately)": same directive-6 monitoring-doc category as the other two docs).
> **ID scheme:** `ISS-F2V-NNN`, numbered from `ISS-F2V-001`, its own namespace — distinct from the codebase's pre-existing inline `ISS-NNN` comment tags (e.g. `ISS-026`, `ISS-043` in `apps/ai-server/src/` and `apps/ai-server/tests/`), which track code-level regression fixes and are not part of this program's doc-ID space.
> **Status vocabulary:** open (unresolved) · resolved (fix applied and verified) · deferred (acknowledged, fix scheduled for a later wave).
> **Owning gate:** one of qa / clinical-validator / critic / orchestrator — whichever gate is responsible for verifying the solution.
> **Companion docs:** `docs/ai/validation_plan_f1f2_continuous.md` (plan v1.2 — full program detail), `docs/ai/workflow_checklist_f1f2.md` (stage × status at-a-glance), `docs/ai/workflow_results_f1f2.md` (per-workflow results log).
> **Status:** 22 issues filed as of 2026-07-11 (`ISS-F2V-001` W0, open — user decision pending; `ISS-F2V-002` W1, resolved at W4 — `REV-024` ratified the widened §6 allowlist table; `ISS-F2V-003`/`004` W1, resolved (fixed `d666a2c`, verified qa W2 gate); `ISS-F2V-005` W2, resolved (fix `4be9818`, verified live in `EXP-014` r2); `ISS-F2V-006` W2, deferred (future safety-v4-scope candidate); `ISS-F2V-007` W4, open — user action pending (SKT key rotation); `ISS-F2V-008` W4, **resolved** — latency fix `325daa4`, verified by qa micro-gate + `REV-025`; `ISS-F2V-009` W4/Gate-0, **open-monitored through battery** — investigation COMPLETE, `BUG-028` filed (new mechanism), disposition is a pre-registered W7 truncation-rate protocol, W7b proceeds; `ISS-F2V-010` W5, open-deferred — `CVR-003` Finding 5 margin-gate deferral, owned by critic at W8; `ISS-F2V-011` W6, **resolved-by-redesign** — VP-002/VP-004 structurally chain-ineligible for live multi-session runs, SC-4/SC-5/SC-8 reassigned to VP-001/VP-003, disclosed; `ISS-F2V-012` W7a/SC-15, open — `AVC-05` finding: `grounding.py`'s containment guard is scoped to `ClinicalSlotAgent`'s 12 slots only; `BUG-029` filed, `REV-028` ruled it BLOCKING, overridden by `ADR-026`; `ISS-F2V-013` W7b, open — dialogue-v3 empathy-phrase repetition at scale (`BUG-030`); `ISS-F2V-014` W7b, open — F2 Pydantic schema fragility, ~5 runs (`BUG-031`); `ISS-F2V-015` W7b, open — SC-8 overwrite drops carried context, no reconciliation (`BUG-032`); `ISS-F2V-016` W7b, open — MPD/somatic probing-depth failures, VP-010+VP-011 (`BUG-033`); `ISS-F2V-017` W7b, open — VP-012 AUD-register safety over-triage (`BUG-034`); `ISS-F2V-018` W7b, open — RAG differentiation/plausibility, PMDD-for-male (`VAL-014`); `ISS-F2V-019` W7b, open — shared risk-lexicon paraphrase-evasion, English + Korean, live (`VAL-015`); `ISS-F2V-020` W7b, open — modality injection turn-index off-by-one (minor, no BUG id yet); `ISS-F2V-021` W7b, open — organic hotline mentions without crisis flag (minor, no BUG id yet); `ISS-F2V-022` W7b, open — `BUG-022` guard's own W7 re-verification not evidenced in this mission's whitelisted sources, `AVC-16` flag).
> **Last updated:** 2026-07-11 (W7b/W8 doc-fold — `ISS-F2V-013` through `ISS-F2V-022` filed for the W7b main-matrix findings (dialogue-v3 empathy repetition, F2 Pydantic fragility, SC-8 overwrite, MPD/somatic probing-depth failures, VP-012 over-triage, RAG face-validity, shared paraphrase-evasion, modality off-by-one, organic hotline mentions, `BUG-022` re-verification gap), plus the clinical-validator weak-point register (8 items, `CVR-009`); cross-referenced to `BUG-030`..`BUG-034`, `VAL-014`/`VAL-015`, `CVR-009`, `REV-030`, all status open).

## Summary table

| ID | Found (wave/scenario) | Issue | Evidence | Solution (proposed/applied) | Status | Owning gate |
|:--|:--|:--|:--|:--|:--|:--|
| ISS-F2V-001 | W0 | PR #42 HIRA/Kakao crisis-guidance path unvalidated; scope decision needed | `ADR-024`; `PLAN-2026-W28-Q` W0 status (qa scan) | Applied: unaugmented path validated, keys stay absent; proposed: schedule an augmented-path scenario class later (user decision) | open | orchestrator |
| ISS-F2V-002 | W1 / `AVC-01` | Plan §6 per-agent allowlist table textually narrower than shipped `BUG-022` guard's `APPROVED_FIELDS` (4 of 7 models) | `error.md` `BUG-022` status update item 3; `PLAN-2026-W28-Q` W1-COMPLETE Disposition (b) | Applied: `REV-024` ruling 2 RATIFIED the widening; §6 table replaced with the ratified widened table, verbatim, incl. the new `RagTriggerJudgeInput` row (writer, this fold) | resolved | critic |
| ISS-F2V-003 | W1 | `InputNormalizerAgent` loses `prompts_degraded=True` on a compound (prompt-missing + downstream-parse) failure | `error.md` `BUG-023` | Applied: `_normalize`'s local flag threaded out to `run()`'s outer exception handler (fixed `d666a2c`, verified qa W2 gate) | resolved | qa |
| ISS-F2V-004 | W1 | `smoke_stt_skt.py` results-save crashes post-archive relocation (no `mkdir(parents=True)`) | `error.md` `BUG-024` | Applied: `vp_dir.mkdir(parents=True, exist_ok=True)` added before the results write (fixed `d666a2c`, verified qa W2 gate) | resolved | qa |
| ISS-F2V-005 | W2 / `EXP-014` | SM-06 dialogue-v3 repetition regression — mid-conversation question repeated verbatim, tripping the repetition guard before the mandatory SI screen | `error.md` `BUG-025`; `result.md` `EXP-014` (r1 FAIL, bisection, r2 PASS) | Applied: prompt conditional-scoping (v3 pin superseded `2440f29b...`→`d8870e5d...4325`) + retry-hint fix (`missing_questionable_slots()`); verified live in r2 (12/12 turns) | resolved | qa |
| ISS-F2V-006 | W2 / `EXP-014` | SM-08b pre-existing safety v2/ADR-010-rule-5 calibration gap surfaced as its own tracked item (byte-identical vs `EXP-013`) | `error.md` `BUG-026`; `result.md` `EXP-014` (r1/r2 byte-compare) | Disclosed known limitation this program; future safety-v4-scope candidate — safety prompt stays pinned v2 | deferred | orchestrator |
| ISS-F2V-007 | W4 | Real `SKT_A_X_API_KEY` value printed into a subagent tool-call transcript during W4 post-commit verification | `error.md` `BUG-027` | Containment verified clean on disk/commits (all mechanical checks `exit=1`); key rotation recommended, user's discretion | open — user action | orchestrator |
| ISS-F2V-008 | W4 / Gate 0 | `RagTriggerJudgeOutput.latency_ms` computed but silently dropped from `decide_policy_b`'s persisted `judge_output` dict — no artifact-level latency data for Policy B | `discussion.md` `REV-024` ruling 4, Issue 3 | Applied: `"latency_ms": judge_output.latency_ms` added to the persisted dict (commit `325daa4`) + fixture updated; qa micro-gate verified statically, `REV-025` criterion 5 confirmed it functions live on both `EXP-015` cert runs (1,102.09 ms / 2,285.25 ms persisted) | resolved | qa |
| ISS-F2V-009 | W4 / Gate 0 (`EXP-015` cert run) | VP-003's live F1 certification run terminated early at turn 9 — the DialogueAgent exact-repeat guard fired twice (turns 8–9) under live, adaptive-`PatientLLM` conditions; possible `BUG-004`/`BUG-025`-class recurrence in a test surface distinct from the scripted `SM-01..08b` matrix. `EXP-015`'s own report also mis-attributed the resulting `Errors: 2` to InputNormalizer and undercounted its parse-failure WARNINGs (2 cited vs. 3 actual) | `discussion.md` `REV-025` "Finding" section + Issues #1/#2; `apps/ai-server/src/f1.py:1656-1662`; `experiments/EXP-015/runs/cert/VP-003/f1_stdout.log` | **Applied — investigation COMPLETE:** qa filed `BUG-028` (major, open) — a **new mechanism**, not a `BUG-025` recurrence (the corrected retry-hint fires correctly and names the right slots; the underlying LLM twice returns its own immediately-prior response verbatim after stalled patient input). Disposition ADOPTED: PROCEED with a pre-registered W7 truncation-rate protocol (items a–d transcribed into `docs/ai/validation_plan_f1f2_continuous.md` Appendix D); `BUG-028` stays open through the battery, W8 disposition informed by observed rates | open-monitored through battery | qa |
| ISS-F2V-010 | W5 / `CVR-003` | `recommended_questionnaire` is derived from `candidates[0]` only, with no minimum-score or minimum-margin gate anywhere in `_aggregate_disease_candidates` — inherits `CVR-001` Finding 2's already-documented near-tied/low-differentiation top-5 problem one level downstream; a specific screening-scale recommendation can hinge on a clinically insignificant score gap | `discussion.md` `CVR-003` Finding 5, weak-point register item 14 | Deferred, per the orchestrator's `CVR-003`-folded disposition (quoted): "inventing a threshold mid-program without empirical basis would violate plan-first discipline; W7's MET-4 data will show whether near-tied top-5 sets actually destabilize the recommendation, and W8 may recommend a gate empirically" — this finding + rationale must appear in any W8 wording about the field (`AVC-18` lens) | open — deferred | critic |
| ISS-F2V-011 | W6 / `DATASET-004-ext` | VP-002's and VP-004's static patient-simulator prompts hardcode revisit framing unconditionally, structurally conflicting with `continuous_test.py`'s system-side rule (session-index 1 = always first-visit) — the two personas cannot be chained live via `continuous_test.py --sessions N`, unlike VP-001/VP-003 | `discussion.md` `DATASET-004-ext` (chain-eligibility finding); `apps/ai-server/src/f1.py:2197-2198`; `apps/ai-server/src/continuous_test.py:399-408`; `VP-002_revisit_mild.md:322`, `VP-004_revisit_severe.md:385` | Applied — reassigned SC-4 and SC-8 to VP-001, SC-5 to VP-003 (the two structurally chain-eligible personas); VP-002/VP-004 exclusion disclosed explicitly in `docs/ai/golden_labels_f1f2.md` Part B; W8 persona-diversity wording-discipline caveat pre-registered (any SC-4/5/8 report must not claim validation "across the persona set" — only VP-001/VP-003, both first-visit, are exercised) | resolved-by-redesign | critic |
| ISS-F2V-012 | W7a / SC-15 (`AVC-05`) | `grounding.py`'s containment guard is scoped to `ClinicalSlotAgent`'s 12 slots only; `DialogueAgent`/`InputNormalizer`/`Safety`/`Sentiment` raw completions are unguarded, and `DialogueAgent`'s output is the one that reaches the shipped transcript unfiltered — this wave's clean containment (3/4 positive reps, 0 hits outside `run.log`) happened only because the echo landed on the guarded surface | `result.md` `EXP-016`, "Results — SC-15 re-run" section; `apps/ai-server/src/grounding.py:255-260` | Proposed, not yet applied — `BUG-029` filed (qa, major, guard-scope gap); `REV-028` ruled the underlying `AVC-05` finding BLOCKING, overridden by `ADR-026` to let W7b proceed under a per-run echo-watch; no code change has extended `grounding.py`'s coverage to the other four agents | open | qa + critic |
| ISS-F2V-013 | W7b / SC-1, SC-12, SC-4/5/8, SC-7/11/9 (`AVC-05` / Tier-2 echo-watch) | `dialogue` v3's 3 licensed example empathy phrases are reused verbatim at scale, in direct, repeated violation of the same prompt's own explicit anti-repetition rule; reaches the shipped patient-facing transcript directly, not caught by any code-level guard | `result.md` `EXP-016` findings 14/20/48/59; SC-1 AVC-05 per-chain reuse table; SC-12/SC-4/SC-5/SC-8/SC-7/SC-11/SC-9 Tier-2 tables | Proposed, not yet applied — filed as `BUG-030` (qa). No code change made to `dialogue` v3's prompt or to any empathy-phrase-selection mechanism this wave | open | qa |
| ISS-F2V-014 | W7b / SC-1, SC-3, SC-4/5/8, SC-9 (F2 Pydantic validation, MET-6 check 3) | F2's `domain_inference` Pydantic validation failed on ~5 independent runs across the battery (SC-1 2/8, SC-3 1/16, SC-4/5/8 1/6, SC-9 1/2) — malformed evidence JSON keys and an out-of-enum `domain="panic"` value recur; each failure drops the whole `domain_candidates` list to empty, `ai_predicted_disease` unaffected in every case | `result.md` `EXP-016` findings 15/32/47/56; SC-1/SC-3/SC-4/SC-9 F2 contract-assertion tables | Proposed, not yet applied — filed as `BUG-031` (qa). The recurring "panic" out-of-enum value (3 of ~5 failures) suggests a systematic domain-enum/model-vocabulary gap, disclosed as a pattern, not diagnosed further | open | qa |
| ISS-F2V-015 | W7b / SC-8 (multi-session answer-revision/overwrite) | session2's `chief_complaint`/HPI were overwritten, not merged, with the carried session1 values on the very first substantive turn of session2 — dropped specific carried detail and the carried "불안감" (anxiety) characterization entirely; `f1.py`'s merge logic performs a plain overwrite with no diff/reconciliation step and no patient-facing confirmation | `result.md` `EXP-016`, "Results — SC-8" overwrite-outcome table; findings 44/45/46 | Proposed, not yet applied — filed as `BUG-032` (qa); clinical-validator (`CVR-009`) rates the underlying behavior MAJOR (no reconciliation mechanism) | open | qa + clinical-validator |
| ISS-F2V-016 | W7b / SC-12 (VP-010 MPD instrument; VP-011 somatic-differentiator probes) | VP-010's Minimization-Probing Depth instrument scored 0/2 reps reaching Tier-3 disclosure on any of 3 domains — no numeric/frequency follow-up ever matched the persona's own Tier-3 exemplars; clinical-validator's own read (`CVR-009`) separately finds VP-011's somatic-differentiator probes never fire, the same underlying dialogue-depth limitation on a distinct instrument | `result.md` `EXP-016` finding 24 (VP-010 half); `CVR-009` (VP-011 half — not independently visible in `EXP-016`'s own raw data) | Proposed, not yet applied — filed as `BUG-033` (qa); clinical-validator (`CVR-009`) rates both instrument failures MAJOR, disclosed as one shared dialogue-quality limitation, not two independent defects | open | qa + clinical-validator |
| ISS-F2V-017 | W7b / SC-12 (VP-012 rep2) | `crisis_triggered=True` fired at turn 9 despite VP-012's ground truth and every dialogue tier specifying SI/self-harm as unconditionally negative; traced to `SafetyClassifier` flagging pure alcohol-control language (`safety_categories=['suicidal_ideation','self_harm','distress']`) — reads as a false positive keyed on loss-of-control phrasing shared between the AUD and SI risk registers; `safety_classifier` v2 stays pinned, unmodified | `result.md` `EXP-016`, "Results — SC-12" VP-012 rep2 crisis-flag subsection; finding 21 | Proposed, not yet applied — filed as `BUG-034` (qa); clinical-validator (`CVR-009`) rates this MAJOR calibration. Fixing requires a `safety_classifier` prompt change, out of this program's licensed scope, consistent with the disclosed `BUG-026` calibration-gap lineage | open | qa + clinical-validator |
| ISS-F2V-018 | W7b / SC-1, SC-12 (`ai_predicted_disease` face-validity) | RAG top-5 differentiation and age/sex plausibility flagged MAJOR and escalating by clinical-validator (`CVR-009`) — "월경전 불쾌장애" (PMDD) recurs for male personas on 6/14 sessions checked, and a pediatric/adolescent-classified entry recurs for adult personas across multiple sessions; visible raw in `EXP-016`'s own candidate tables, reported there as observational fact only (no face-validity verdict, out of experiment-tracker's charter) | `result.md` `EXP-016` "Results — SC-1"/"Results — SC-12" `domain_candidates`/`ai_predicted_disease` tables; `CVR-009` (the face-validity verdict, incl. the 6/14 count) | Proposed, not yet applied — filed as `VAL-014` (critic/clinical-validator). No RAG corpus or ranking change made this wave; first raised narrower at `CVR-001` (`EXP-012` read), now confirmed at larger scale in W7b | open | clinical-validator + critic |
| ISS-F2V-019 | W7b / SC-2, SC-3, SC-3b (English); SC-5 (Korean) | the Korean-only `_RISK_PHRASES` lexicon fails to catch risk-adjacent paraphrases in either language when they do not match a literal stem — 3 English occurrences (SC-2 VP-003 rep1 B, SC-3 VP-003 rep2 B, SC-3b VP-003 repeat 2 B) and 1 Korean occurrence (SC-5 session2, "살기 싫어요", a construction distinct from all 4 existing stems) each reached live retrieval undetected. Shared by both RAG-trigger policy arms — the W8 Policy A/B adjudication does not resolve or remediate this finding | `result.md` `EXP-016` findings 27/31/34 (English), 43 (Korean); "Results — SC-2"/"SC-3"/"SC-3b"/"SC-5" MET-8 subsections | Proposed, not yet applied — filed as `VAL-015` (critic). `REV-030` restates this as a binding caveat on the "Policy A adopted" wording — adoption must not be read as immunity to this shared, open gap | open | critic |
| ISS-F2V-020 | W7b / SC-7, SC-11, SC-9 (modality provenance) | a reproducible off-by-one exists between `InjectionCue.turn_index` and F1's own persisted turn numbering for mid-dialogue (`turn_index≥1`) injections — composer index K lands at persisted `turn=K+1`, not `turn=K`; does NOT apply at `turn_index=0`. The module's own `verify_provenance_against_conversation()` helper reproducibly reports a false mismatch for every `K≥1` case as a direct consequence | `result.md` `EXP-016` finding 51, "Results — SC-7/SC-11" off-by-one subsection | Proposed, not yet applied. No BUG/VAL id supplied for this finding in this pass's routing; tracked here pending formal filing | open | qa |
| ISS-F2V-021 | W7b / SC-9 (VP-004), SC-11 (VP-003) | the `DialogueAgent` organically inserted "자살예방상담전화 109" into an ordinary empathetic response in 2 separate runs despite `crisis_triggered=False` in both — free-generated dialogue text, distinct from the formal crisis-substitution template, with no accompanying safety flag or early-return | `result.md` `EXP-016` finding 55, "Results — SC-9"/"Results — SC-7/SC-11" sections | Proposed, not yet applied. No BUG/VAL id supplied for this finding in this pass's routing; tracked here pending formal filing/disposition (qa/critic attention per `EXP-016`'s own routing note) | open | qa + critic |
| ISS-F2V-022 | W7b (retrospective) — `BUG-022`'s own W7 re-verification | `BUG-022`'s `APPROVED_FIELDS` schema-field guard (standing `AVC-01` protection, active since W1) has no independent W7-cycle re-verification recorded in this blind-execution mission's own whitelisted sources — `result.md` `EXP-016` does not report re-running the guard's own test suite or re-diffing `APPROVED_FIELDS` during W7a/W7b; flagged, not confirmed broken (may reflect out-of-scope-for-a-blind-tracker-role rather than a skipped check) | `result.md` `EXP-016` (no re-verification recorded); `workflow_results_f1f2.md`'s `w1-prereq-fixes-archive`/`w4-policy-ab-implementation` entries (the guard's prior verification record) | Proposed — flagged under the `AVC-16` drift-audit lens per this pass's brief; recommend a qa micro-gate re-confirming the guard suite still passes and `APPROVED_FIELDS` is unchanged before any report treats W7's `AVC-01` protection as continuously verified through the full battery | open | qa |

## Entry template

Copy this block for each issue found; do not leave placeholder content — every field must trace to a source (a file path, a wave/scenario/audit-class ID, or a doc entry ID). Append the filled-in block below this template, then add a matching row to the summary table above.

```markdown
## [ISS-F2V-NNN] short title | YYYY-MM-DD

**Found:** <wave, e.g. W1> / <SC-NN or AVC-NN, if scenario- or audit-class-specific>

**Issue:** <what went wrong, plain description>

**Evidence:** <path or entry ID — every claim traceable>

**Solution:** <proposed or applied fix; state which>

**Status:** open | resolved | deferred

**Owning gate:** qa | clinical-validator | critic | orchestrator

**Cross-refs:** <BUG-NNN / VAL-NNN / CVR-NNN / REV-NNN once formally filed — "none yet" if not yet filed>

---
```

## [ISS-F2V-001] PR #42 HIRA/Kakao crisis-guidance path unvalidated; scope decision needed | 2026-07-11

**Found:** W0 (qa PR #42 overlap scan)

**Issue:** PR #42 (merge `c85b3e1`, branch `add/map-api`) adds HIRA/Kakao-sourced nearby-facility guidance appended to `f1.py`'s crisis responses on turns ≥ 1, when `patient_lat`/`patient_lng` resolve and HIRA/Kakao credentials exist. If those credentials were provisioned mid-program, crisis-turn response text would silently change for VP-001..004 — a behavior change the plan's own cells are not designed to detect, since it would happen invisibly between otherwise-comparable runs.

**Evidence:** `discussion.md` `ADR-024`; `discussion.md` `PLAN-2026-W28-Q` W0 status (qa PR #42 overlap scan) — confirms `f1.py` interacts (+165/-2 lines: `PERSONA_LOCATIONS` for VP-001..004, `F1Result.{nearby_psychiatric,patient_lat,patient_lng}`, `_fetch_crisis_facilities()` hooked into both crisis branches; turn-0 crisis text unchanged by design) but is currently live-inert (`HIRA_SERVICE_KEY`/Kakao keys absent from `.env`; live-checked `_fetch_crisis_facilities(37.58,126.88)` → `nearby_text=''`).

**Solution:** Applied — this program validates the unaugmented crisis-text path only; HIRA/Kakao keys stay absent from `.env` for the program's duration, with a qa name-only preflight assert added alongside the `AVC-17` prompt-SHA256 pin check (`ADR-024`). Proposed, not yet decided: whether to provision the credentials and validate the augmented path as its own scenario class later, with its own crisis-text assertions — a user decision, not self-resolved.

**Status:** open (user decision pending)

**Owning gate:** orchestrator

**Cross-refs:** `ADR-024`

---

## [ISS-F2V-002] Plan §6 allowlist table textually narrower than shipped W1 guard's `APPROVED_FIELDS` | 2026-07-11

**Found:** W1 / `AVC-01` (static info-flow allowlist check)

**Issue:** qa's W1 gate cross-check found the ratified per-agent static info-flow allowlist table (`docs/ai/validation_plan_f1f2_continuous.md` §6, `REV-023` ruling 1b, "transcribed verbatim") is textually narrower than the shipped `retrieve_grounding()` schema-field guard's `APPROVED_FIELDS` for 4 of its 7 instrumented models: `InputNormalizerInput`, `SentimentUtteranceInput`, `SentimentSessionInput`, `DomainInferenceInput`. Every additional licensed field is non-persona-derived (`F1Result` session-state or Stage-1 RAG-corpus output); the guard's core protection — the four forbidden columns (`class`, `phq9_score`, `gad7_score`, `flag_suicidal`) asserted absent on all 7 models — is unaffected. This is a documentation-precision gap between the table's terse phrasing and the guard's necessarily more literal field-set translation, not a functional leakage risk.

**Evidence:** `error.md` `BUG-022` status update item 3 (qa, 2026-07-11); `discussion.md` `PLAN-2026-W28-Q` W1-COMPLETE status, Disposition (b).

**Solution:** Applied — `REV-024` ruling 2 independently re-read `tests/repro/test_bug_022.py`'s `APPROVED_FIELDS` against the four flagged schemas and RATIFIED WIDENING (every extra field is non-persona-derived — a current-turn call parameter, an already-licensed upstream agent's own prior output, or `F1Result` session-scoped state; never a `rag.session_insights` ground-truth column or a raw persona-file value). Narrowing the guard to the table's literal pre-widening text would have stripped genuinely-needed fields for no leakage benefit. `docs/ai/validation_plan_f1f2_continuous.md` §6's per-agent allowlist table is replaced with the ratified widened table, transcribed verbatim, including the new `RagTriggerJudgeInput` row (writer, this fold).

**Status:** resolved (2026-07-11, closes on the §6 transcription pass)

**Owning gate:** critic

**Cross-refs:** `BUG-022`, `REV-023` ruling 1b, `REV-024` ruling 2

---

## [ISS-F2V-003] `BUG-023` — `InputNormalizerAgent` loses `prompts_degraded` on compound failure | 2026-07-11

**Found:** W1 (qa, found while verifying `BUG-021`'s closure)

**Issue:** `InputNormalizerAgent._normalize`'s local `prompts_degraded=True` (set when the prompt file is missing) is discarded when a downstream `json.loads` failure also occurs on the same call — the exception propagates out of `_normalize` to `run()`'s outer catch-all, which rebuilds a fresh fallback response with no `prompts_degraded` kwarg (defaults `False`). Requires a compound failure (prompt-missing AND downstream parse failure) to trigger; a clean prompt load or a degraded-prompt-with-successful-downstream-call are both unaffected.

**Evidence:** `error.md` `BUG-023` (filed 2026-07-11, qa, minor, open).

**Solution:** Applied — `_normalize`'s local `prompts_degraded` value is now threaded out to `run()`'s outer exception handler: the downstream `json.loads` failure is caught locally inside `_normalize` and returns `self._safe_fallback(inp, ..., prompts_degraded=prompts_degraded)`, mirroring the existing safety-expression-loss call already present at `input_normalizer.py:151-152`. Fixed in commit `d666a2c`; verified in the W2 qa gate (`error.md` `BUG-023` resolution: `tests/repro/test_bug_023.py` 3/3 passed, part of the default `887 passed, 2 skipped` suite count at that gate).

**Status:** resolved

**Owning gate:** qa

**Cross-refs:** `BUG-023`, `BUG-021`

---

## [ISS-F2V-004] `BUG-024` — `smoke_stt_skt.py` results-save crashes post-W1 archive relocation | 2026-07-11

**Found:** W1 (qa, exposed by the fixture/archive relocation commit `f478719`)

**Issue:** `tests/smoke_stt_skt.py`'s results-save step writes to a per-VP subdirectory under `docs/ai/simulation_results/` with no prior `mkdir(parents=True, exist_ok=True)` call. Before W1's archive move, that directory happened to already exist (created incidentally by other tooling), masking the gap; after the move it no longer pre-exists by default, so a standalone run of the script now crashes with `FileNotFoundError` at the save step. Manual devtool only — not part of `uv run pytest`/CI collection; no safety/clinical-data-handling impact.

**Evidence:** `error.md` `BUG-024` (filed 2026-07-11, qa, minor, open).

**Solution:** Applied — `vp_dir.mkdir(parents=True, exist_ok=True)` added immediately before the results write, mirroring `f1.py`'s own `save_f1_result` convention (`f1.py:1590`). Fixed in commit `d666a2c`; verified in the W2 qa gate (`error.md` `BUG-024` resolution: `tests/repro/test_bug_024.py` 2/2 passed, part of the default `887 passed, 2 skipped` suite count at that gate).

**Status:** resolved

**Owning gate:** qa

**Cross-refs:** `BUG-024`

---

## [ISS-F2V-005] `BUG-025` — SM-06 dialogue-v3 repetition regression | 2026-07-11

**Found:** W2 / `EXP-014` (bundled `SM-01..08b` regression, r1)

**Issue:** `SM-06` passed cleanly in `EXP-002` and `EXP-013` (12/12 turns, mandatory SI screen reached) but stopped at turn 7/12 in `EXP-014` r1 — the AI asked the byte-identical substance-use question twice in a row after the patient had already answered it, tripping the pipeline's pre-existing (unmodified) repetition guard (`f1.py:1655-1665`) before the mandatory SI screen was reached. Live bisection (1 call, isolated worktree at pre-dialogue-v3 commit `247922e`) reproduced a clean 12/12-turn pass; mechanical elimination of the other 4 W2 candidate changes (`BUG-011`, `BUG-021`, `is_revisit`, narrowed carry — none of their code paths entered in this scenario) left dialogue v3 as the sole causally-attributed cause.

**Evidence:** `error.md` `BUG-025` (filed 2026-07-11, qa, major); `result.md` `EXP-014` (r1 primary matrix + bisection); `result.md` `EXP-014` r2 status update (fix verification).

**Solution:** Applied — developer diagnosed two candidate mechanisms in `d3e524d`'s dialogue v3 change: (a) turn 0 now makes a real `DialogueAgent.run()` LLM call under the v3 prompt for every session (previously a hardcoded static string), and (b) `PROMPT_VERSION="v3"` governed every call for the whole session, not just turn 0. Fix (`4be9818`): the always-on turn-0/revisit rule sections were condensed into one paragraph that states its own conditional scope explicitly (new v3 pin `d8870e5dda81dffde9099a2e606e9656b7aeb8f897dbdd41f25705efbdc84325`, supersedes `2440f29b63315d3613b8726b982d612479d97b7be8e4a796c0a5f80e947e1e0b`); the in-agent retry hint was corrected to call `missing_questionable_slots()` instead of `_ESSENTIAL_SLOTS`-only. The repetition guard itself was left untouched (`git diff d666a2c..4be9818 -- apps/ai-server/src/f1.py` empty, per `ADR-025`'s hard constraint). Verified live: `EXP-014` r2 shows `SM-06` `all_passed=true`, 12/12 turns, `si_screen_asked=true`, `risk_assessment_grounded=true`.

**Status:** resolved

**Owning gate:** qa

**Cross-refs:** `BUG-025`, `ADR-025`, `EXP-014`

---

## [ISS-F2V-006] `BUG-026` — SM-08b pre-existing safety v2 calibration gap tracked standalone | 2026-07-11

**Found:** W2 / `EXP-014` (SM-08b non-pass, r1 and r2, byte-compared against `EXP-013`)

**Issue:** the currently-pinned `safety_classifier` v2 prompt does not implement `ADR-010` rule 5's immediate-CTRS-2-on-anchor-phrase policy — `SM-08b`'s burden-ideation anchor phrase is instead floored at CTRS 3/graduated-probe. This reproduces byte-for-byte across three independent live runs (`EXP-013` 2026-07-10, `EXP-014` r1 and r2 2026-07-11), predates all five W2 changes, and is unrelated to the `BUG-025` fix (dialogue subsystem only).

**Evidence:** `error.md` `BUG-026` (filed 2026-07-11, qa, major, open); `result.md` `EXP-014` r1 (temporal-precedence argument, no bisection needed) and r2 (byte-compare against r1 and `EXP-013`, all 5 checks + `total_turns` identical).

**Solution:** Disclosed known limitation for the remainder of this program — not fixed this wave, and explicitly out of `ADR-025`'s post-fix re-run scope (documented pre-existing issue, not a blocker). Fixing it requires a `safety_classifier` prompt change, which is outside this program's licensed scope (safety pinned v2). Tracked as future safety-v4-scope work, per `BUG-010`'s own proposed-fix scope and `ADR-012` item 3's lineage. Carried as a disclosed known limitation on every `SM-08b`-class result through W7/W8.

**Status:** deferred

**Owning gate:** orchestrator

**Cross-refs:** `BUG-026`, `ADR-012` item 3

---

## [ISS-F2V-007] `BUG-027` — real `SKT_A_X_API_KEY` value printed into a subagent tool-call transcript during W4 post-commit verification | 2026-07-11

**Found:** W4 (developer, self-disclosed during post-commit verification of `91c04f5`)

**Issue:** developer's own post-commit read-only verification command printed the real `SKT_A_X_API_KEY` credential value into its subagent tool-call transcript — a violation of the project's standing rule that secrets are never printed or committed, even transiently, even in a read-only verification command.

**Evidence:** `error.md` `BUG-027` (filed 2026-07-11, qa, major — process/security, not critical, because containment is clean); `discussion.md` `PLAN-2026-W28-Q` W4 status, "SECURITY INCIDENT (self-caught, disclosed)".

**Solution:** Containment verified clean — this is confirmation, not remediation of the exposure itself (the transcript surface is outside repo/tooling control). qa's independent mechanical check, the value itself never echoed at any point in the check: key line present exactly once in `apps/ai-server/.env` (gitignored, untracked); `grep -rqF` for the value across the worktree excluding `.git`/`.env` → `exit=1`; `git grep -qF` across all 10 commits `c85b3e1..91c04f5` on this branch → `exit=1`; targeted `experiments/` and `docs/` checks → `exit=1` both. No file, commit, or repo-tracked artifact carries the value. **Recommended: SKT A.X competition key rotation, at the user's discretion** (key expires 2026-11-23) — a user action item; no agent can self-remediate (no vendor-console access from this project's tooling).

**Status:** open — user action pending (rotation)

**Owning gate:** orchestrator

**Cross-refs:** `BUG-027`

---

## [ISS-F2V-008] `judge_output.latency_ms` computed but dropped before persistence — Gate 0's "latency recorded" criterion unevaluable | 2026-07-11

**Found:** W4 / Gate 0 pre-registration (`REV-024` ruling 4, Issue 3)

**Issue:** `RagTriggerJudgeAgent.run()` correctly computes real per-call `latency_ms` (genuine `time.perf_counter()` deltas, not a placeholder), but `decide_policy_b`'s persisted `judge_output` dict (`apps/ai-server/src/rag_trigger.py:313-320`) silently drops it — the only place Gate 0's output is ever recorded therefore carries no per-call judge latency. This is load-bearing, not cosmetic: Criterion 3 of the pre-registered A/B adjudication rule (`docs/ai/validation_plan_f1f2_continuous.md` §5) needs real per-call judge latency from the W4 certification batch to fix its `THRESHOLD_3`, and as shipped the batch cannot supply that number to any artifact-based downstream measurement.

**Evidence:** `discussion.md` `REV-024` ruling 4 / Issues table row 3 (`src/agents/rag_trigger_judge.py:130,177,201,209` — computed — vs. `apps/ai-server/src/rag_trigger.py:313-320` — dropped; `tests/test_rag_trigger.py:363-375`'s expected-dict fixture also lacks a `latency_ms` key, so the test currently encodes the gap rather than catching it).

**Solution:** Applied (developer, commit `325daa4`): `"latency_ms": judge_output.latency_ms"` added to `decide_policy_b`'s persisted `judge_output` dict (`apps/ai-server/src/rag_trigger.py:323`); `test_judge_io_persisted_in_judge_output`'s fixture updated to assert its presence. qa's micro-gate on `325daa4` independently reproduced the fix (pre-fix file swap → post-fix test fails → restored, tree clean). Live confirmation followed in the `EXP-015` certification batch: `REV-025` ruling 1 criterion 5 confirms `judge_output.latency_ms` present and non-null on both cert runs (1,102.09 ms VP-003, 2,285.25 ms VP-001) — the fix functions on a real call, not just by static/test read. Gate 0's "latency recorded" pass criterion is now evaluable and PASSED.

**Status:** resolved (2026-07-11 — code fix + qa micro-gate + live confirmation via `REV-025`)

**Owning gate:** qa

**Cross-refs:** `REV-024`, `REV-025`, `EXP-015`

---

## [ISS-F2V-009] VP-003 live repetition-guard trip found in the Gate-0 certification run — possible BUG-004/BUG-025-class recurrence | 2026-07-11

**Found:** W4 / Gate 0 certification (`EXP-015` cert batch, VP-003 run; surfaced by `REV-025`'s independent artifact re-read, not by the tracker's own report)

**Issue:** VP-003's live, first-visit F1 certification session terminated early at turn 9 of a planned 10. Tracing `result.errors.append` (the sole writer of `f1.py`'s `Errors:` count) shows the DialogueAgent's exact-repeat guard fired twice — turn 8 (`count=1`) then turn 9 (`count=2`, "Agent repeated 2+ times — stopping") — under live, adaptive-`PatientLLM` conditions, a test surface distinct from the fixed scripted `SM-01..08b` matrix (which passed clean post-`4be9818`, `ISS-F2V-005`). Five `"DialogueAgent repeated — retrying with stronger hint"` events preceded the stop (turns 4–9), and the patient-simulator's own utterance text was byte-identical across turns 6–9; whether the proximate driver is patient-simulator stall or an independent DialogueAgent defect is not determinable from the log alone. Separately, `EXP-015`'s own report mis-attributed the resulting `Errors: 2` to `InputNormalizer` parse failures (a pre-existing, unrelated `BUG-020` symptom) instead of the repetition guard, and undercounted VP-003's InputNormalizer WARNINGs (2 cited vs. 3 actual — the third, at `f1_stdout.log:58`, has a distinct raw-JSON-decode signature not covered by `BUG-020`'s specific diagnosis).

**Evidence:** `discussion.md` `REV-025` "Finding — EXP-015's own report undercounts and mis-attributes VP-003's F1 anomalies" section + Issues #1/#2 (major, non-blocking to Gate-0); `apps/ai-server/src/f1.py:1656-1662` (repetition guard); `experiments/EXP-015/runs/cert/VP-003/f1_stdout.log:34,58,86,94,111,128,158,165,176,183-184`; `experiments/EXP-015/metrics.json` `f1_errors_note` (the mis-attributed text).

**Solution:** Proposed, in flight — routed to qa (per `REV-025`'s recommended routing, in parallel with, not blocking, W7/W8 adjudication prep): investigate the VP-003 repetition-guard trip as a possible live recurrence of `BUG-004`/`BUG-025`-class dialogue-repetition behavior under adaptive-`PatientLLM` conditions (a test surface the scripted SM matrix does not exercise); file a new BUG or an addendum to `BUG-025` as the evidence warrants; correct `EXP-015`'s `metrics.json` `f1_errors_note` to name the repetition guard, not InputNormalizer, as the actual cause, and correct the BUG-021-check section's WARNING count (3, not 2) with line 58's distinct signature disclosed. Does not gate Gate-0's PASS verdict or reopen any Appendix C criterion (none examine `InputNormalizerAgent` or DialogueAgent repetition behavior) — but per `REV-025`'s own verdict, **must be resolved or formally dispositioned before W7b**: an undiagnosed early-termination mechanism could corrupt SC-1 baselines if it recurs during the main blind battery.

**Status update (2026-07-11, investigation COMPLETE):** qa's investigation concluded and filed `BUG-028` (`error.md`, major, open) — turn-by-turn artifact tracing (`f1_stdout.log`, `conversation.json`) confirms `BUG-025`'s own fix is unmodified and firing correctly (5/5 internal retry triggers, correct hint slots each time); the defect is a **new mechanism**, not a `BUG-025` recurrence — the underlying LLM twice returned its own immediately-prior response verbatim (turns 8 and 9) after 3–4 consecutive turns of stalled, byte-identical patient input, tripping `f1.py`'s outer exact-repeat guard and truncating the session at turn 9/10. The mandatory SI/`risk_assessment` screen was already grounded before the truncation in this case; the `EXP-015`-report mis-attribution/undercount this issue originally flagged is independently corroborated and corrected in `BUG-028`'s own entry (`error.md`). **Disposition ADOPTED (qa recommendation, orchestrator pre-registration, recorded before any W7 run):** PROCEED — W7b runs under a pre-registered truncation-rate protocol (per-session repetition-guard/early-termination capture; truncation-flagged MET-1 numbers never silently pooled; SC-1 baseline states the observed truncation rate; a ≥3-of-8 SC-1 CHECKPOINT pause rule, explicitly an operational checkpoint, not a validity threshold), transcribed verbatim into `docs/ai/validation_plan_f1f2_continuous.md` Appendix D. `BUG-028` stays open through the battery; W8's disposition is informed by the observed rates.

**Status:** open-monitored through battery (investigation complete; `BUG-028` stays open per its own pre-registered disposition through the W7/W8 battery)

**Owning gate:** qa

**Cross-refs:** `REV-025`, `BUG-025`, `BUG-004`, `BUG-028`

---

## [ISS-F2V-010] `CVR-003` Finding 5 — no minimum-score/margin gate on `recommended_questionnaire`'s top-1 derivation, deferred as a disclosed limitation | 2026-07-11

**Found:** W5 / `CVR-003` (disease→questionnaire static-mapping content review)

**Issue:** `f2.py`'s `recommended_questionnaire` derivation reads only `candidates[0]` — `_aggregate_disease_candidates` sorts and truncates to the top-5 but never filters by score value, so no minimum-score or minimum-margin gate exists anywhere in the path. `CVR-001` Finding 2 already documented, from live `EXP-012` output, that top-5 candidate sets for clinically distinct VPs are near-identical with score gaps as small as 0.489 vs. 0.480 — differences well within what a single differently-worded turn could flip. Tying a specific screening-scale recommendation to whichever candidate happens to rank #1 by a margin this thin means the recommendation inherits the same face-validity fragility `CVR-001` already flagged for the candidate list, one level downstream: the same patient, re-run or phrased slightly differently, could plausibly receive a different `recommended_questionnaire` value (or `None`) purely from ranking noise, not a genuine change in clinical picture.

**Evidence:** `discussion.md` `CVR-003` Finding 5 (`f2.py:453-514`/`:562-564`, direct read); weak-point register item 14 (cumulative, prioritized); cross-references `CVR-001` Finding 2's already-open register item 2.

**Solution:** Deferred, per the orchestrator's `CVR-003`-folded disposition (`discussion.md` `PLAN-2026-W28-Q`, "CVR-003 folded" status), quoted verbatim: "inventing a threshold mid-program without empirical basis would violate plan-first discipline; W7's MET-4 data will show whether near-tied top-5 sets actually destabilize the recommendation, and W8 may recommend a gate empirically (this finding + rationale must appear in any W8 wording about the field — AVC-18 lens)." Not fixed this wave; not a shipping blocker (`CVR-003`'s own verdict — 0 blocking findings) — `recommended_questionnaire` ships into the battery per `CVR-003`'s disposition, with this deferral disclosed as a standing limitation on any report that presents the field's value.

**Status:** open — deferred

**Owning gate:** critic (at W8, per the `CVR-003` disposition's own scheduling — evaluated alongside `CVR-001` Finding 2's own W8 face-validity check)

**Cross-refs:** `CVR-003`, `CVR-001` (Finding 2 lineage)

---

## [ISS-F2V-011] VP-002/VP-004 structurally chain-ineligible for live multi-session runs | 2026-07-11

**Found:** W6 / `DATASET-004-ext` (golden reveal-partition spec authoring, `data`)

**Issue:** Not all 4 of VP-001..004 are structurally suitable for `continuous_test.py`'s live `--persona VP-00X --sessions N` chaining mechanism, which reuses ONE persona's ONE static system prompt across every session in the chain. `f1.py:2197-2198` — the SYSTEM always treats `session_index=1` (no `--followup-from`) as `is_revisit=False`, regardless of the persona file's own `visit_type` metadata; independently traced at `continuous_test.py:399-408`, `followup_from` is unset for every session-index-1 call in any chain attempt, confirming this is structural for every possible chain, not a narrow edge case. But VP-002's and VP-004's static Patient LLM simulation prompts hardcode revisit framing **unconditionally**: VP-002 — "오늘은 약 복용 후 경과를 확인받기 위한 재진 사전문진입니다" (`VP-002_revisit_mild.md:322`); VP-004 — "오늘은 재진 사전문진입니다" (`VP-004_revisit_severe.md:385`). Chaining VP-002 or VP-004 fresh (session 1, no `--followup-from`) would produce an internally contradictory session: the SYSTEM's own greeting/dialogue framing treats it as first-visit, while the PATIENT simulator insists this is already a revisit. VP-001 and VP-003, by contrast, both state unconditional first-visit framing with no revisit claim anywhere in their static prompts, and chain cleanly.

**Evidence:** `discussion.md` `DATASET-004-ext` ("Chain-eligibility finding" section); `apps/ai-server/src/f1.py:2197-2198`; `apps/ai-server/src/continuous_test.py:399-408`; `docs/ai/personas/VP-002_revisit_mild.md:322`; `docs/ai/personas/VP-004_revisit_severe.md:385`.

**Solution:** Applied — `DATASET-004-ext` designates VP-001 and VP-003 as the SC-4/SC-5/SC-8 chain-relevant personas; VP-002/VP-004 are excluded from live `continuous_test.py` chaining by this structural finding (SC-4 and SC-8 → VP-001, SC-5 → VP-003). `REV-026` ruling 2 independently re-verified the finding at every cited line and RATIFIED the exclusion. The exclusion and its consequence (only 2 of 7 personas exercise multi-session chaining, both first-visit) are disclosed explicitly in `docs/ai/golden_labels_f1f2.md` Part B, with a binding W8 wording-discipline caveat: any W7b/W8 report characterizing SC-4/SC-5/SC-8 results as validating induction/re-probe/revision behavior "across the persona set" overclaims. A future VP-002/VP-004-based chain (e.g. treating their existing baked prior-visit backstory as an implicit "session 1") would need either an explicit `session_index=2`-first-call convention or a persona-prompt conditional on session index — a code-design question, out of `data`'s or this issue's charter, not decided here.

**Status:** resolved-by-redesign (the reveal-partition spec was redesigned around the two chain-eligible personas rather than attempting to chain all four; the underlying structural conflict in VP-002/VP-004's static prompts is not itself "fixed," and is not a defect requiring a fix — it is a persona-design property, disclosed and worked around)

**Owning gate:** critic (`REV-026` ruling 2, independent re-verification and ratification)

**Cross-refs:** `DATASET-004-ext`, `REV-026`

---

## [ISS-F2V-012] SC-15 AVC-05 finding — grounding.py's containment guard is scoped to ClinicalSlotAgent only | 2026-07-11

**Found:** W7a / SC-15 (`AVC-05` prompt-echo mutation probe)

**Issue:** SC-15's adversarial single-turn probe produced a verbatim echo of `clinical_slot` v3's own JSON output-format example strings in the raw `ClinicalSlotAgent` completion on 3/4 reps (`vp001_rep2`, `vp003_rep1`, `vp003_rep2`). The existing `apps/ai-server/src/grounding.py:255-260` guard (`evaluate_slot_grounding()`, which discards any slot value containing a literal `<`/`>` character) caught and discarded both echoed values before they reached `slot_updates`/`cumulative_slots`/`final_slots` in all 3 affected reps — grepping the same strings against each rep's `conversation.json`, `checklist.md`, and `report.md` returns 0 hits; the echo is confined to the transient raw-completion layer captured only in `run.log`. But this containment is a property of where the echo happened to land, not a general property of the pipeline: the guard is scoped to `ClinicalSlotAgent`'s 12 clinical slots only. `DialogueAgent`, `InputNormalizer`, `Safety`, and `Sentiment` raw completions pass through no equivalent check, and `DialogueAgent`'s output is the one agent output that reaches the shipped conversation transcript unfiltered. An equivalent prompt-echo on one of those four unguarded surfaces would not necessarily be caught the same way.

**Evidence:** `result.md` `EXP-016`, "Results — SC-15 re-run (2026-07-11, seam unblocked, HEAD `3d6c4978`) — POSITIVE AVC-05 FINDING, STOP-THE-LINE" section (hit-strings table, containment verification, cross-check against SC-13's 0/7 hits); `apps/ai-server/src/grounding.py:255-260`; `apps/ai-server/src/agents/clinical_slot.py:49-50` (the guard's own "T1-F1-DEV-017" prior-incident lineage comment).

**Solution:** Proposed, not yet applied. `BUG-029` filed (qa, major) documenting the guard's scope gap as a mechanical finding. `REV-028` (critic) ruled the underlying `AVC-05` finding **BLOCKING** — per plan §6's unconditional Block=Y rule on any positive `AVC-05` hit, plan §5's stop-the-line pre-registration, and a "live output" != "shipped output" reading (the echo occurred and was only caught after the fact, not prevented at the point of generation). `ADR-026` overrides the block to let W7b proceed, conditioned on a per-run echo-watch: any shipped-output echo observed during W7b halts the wave immediately. No code change has yet extended `grounding.py`'s (or an equivalent) coverage to `DialogueAgent`/`InputNormalizer`/`Safety`/`Sentiment`.

**Status:** open

**Owning gate:** qa + critic (joint — `BUG-029`'s mechanical guard-scope finding is qa's; `REV-028`'s blocking verdict and its `ADR-026` override are critic's/orchestrator's)

**Cross-refs:** `BUG-029`, `REV-028`, `ADR-026`

---

## [ISS-F2V-013] Dialogue-v3 empathy-phrase repetition, pervasive at scale | 2026-07-11

**Found:** W7b / SC-1, SC-12, SC-4/SC-5/SC-8, SC-7/SC-11/SC-9 (`AVC-05` / Tier-2 echo-watch)

**Issue:** `dialogue` v3's own 3 licensed example empathy phrases are reused verbatim at scale across the W7b battery, in direct, repeated violation of the same prompt's own explicit anti-repetition rule ("같은 공감 표현을 2턴 연속 사용하지 마세요" / "매 턴 다른 표현을 사용한다"). Observed in SC-1 (6/8 chains, 6/8 including direct consecutive-turn reuse — `result.md` `EXP-016` finding 14), SC-12 (6/6 sessions, logged under that sub-run's own Tier-2 convention — finding 20), SC-4/SC-5/SC-8 (5/6 sessions — finding 48), and SC-7/SC-11/SC-9 (4/7 sessions — finding 59). The reuse reaches the shipped, patient-facing transcript directly (`agent_response`), not a raw-completion layer caught by any code-level guard.

**Evidence:** `result.md` `EXP-016`, "Results — SC-1" `AVC-05` per-chain reuse table and findings 14/20/48/59; SC-12/SC-4/SC-5/SC-8/SC-7/SC-11/SC-9 Tier-2 echo-watch tables.

**Solution:** Proposed, not yet applied. Filed as `BUG-030` (qa). No code change has been made to `dialogue` v3's prompt or to any repetition-selection mechanism for empathy phrasing this wave.

**Status:** open

**Owning gate:** qa

**Cross-refs:** `BUG-030`, `CVR-009` (naturalness/badgering read), `REV-030`

---

## [ISS-F2V-014] F2 Pydantic schema fragility, ~5 recurring runs | 2026-07-11

**Found:** W7b / SC-1, SC-3, SC-4/SC-5/SC-8, SC-9 (F2 Pydantic validation, MET-6 contract check 3)

**Issue:** F2's `domain_inference` Pydantic validation failed on ~5 independent runs across the W7b battery — SC-1 2/8 (VP-003 rep2 malformed evidence JSON key; VP-004 rep2 out-of-enum `domain="panic"`), SC-3 1/16 (VP-004 rep1 Policy B, same out-of-enum "panic" value), SC-4/SC-5/SC-8 1/6 (SC-4 session2, malformed evidence JSON, same class as SC-1), SC-9 1/2 (VP-004, same out-of-enum "panic" value). Each failure drops the whole `domain_candidates` list to empty under Pydantic's atomic list validation; `ai_predicted_disease` (a separate code path) stays unaffected in every case.

**Evidence:** `result.md` `EXP-016` findings 15/32/47/56; SC-1/SC-3/SC-4/SC-9 F2 contract-assertion tables.

**Solution:** Proposed, not yet applied. Filed as `BUG-031` (qa). The recurring "panic" out-of-enum value (3 of the ~5 failures) suggests a systematic gap between the `domain` enum and the model's own vocabulary, not independent random failures — disclosed as a pattern, not diagnosed further (root cause is developer's charter).

**Status:** open

**Owning gate:** qa

**Cross-refs:** `BUG-031`

---

## [ISS-F2V-015] SC-8 overwrite drops carried context, no reconciliation | 2026-07-11

**Found:** W7b / SC-8 (multi-session answer-revision/overwrite, VP-001)

**Issue:** session2's `chief_complaint`/`history_of_present_illness` were overwritten, not merged, with the carried session1 values on the very first substantive turn of session2 — dropping specific carried detail (sleep-onset latency ~1hr, 2-3x nighttime awakenings) and dropping the carried "불안감" (anxiety) characterization entirely, replaced by "전반적 기분 상태는 괜찮음" (overall mood fine) — a content loss/inconsistency never explicitly walked back by the patient on the record. `f1.py`'s merge logic (`filled_slots[key] = value`) performs a plain overwrite on any freshly-grounded extraction for an already-filled key, with no diff/reconciliation step and no patient-facing confirmation of what changed.

**Evidence:** `result.md` `EXP-016`, "Results — SC-8" overwrite-outcome table; findings 44/45/46.

**Solution:** Proposed, not yet applied. Filed as `BUG-032` (qa); clinical-validator (`CVR-009`) rates the underlying behavior MAJOR (no reconciliation mechanism exists at any layer).

**Status:** open

**Owning gate:** qa + clinical-validator

**Cross-refs:** `BUG-032`, `CVR-009`

---

## [ISS-F2V-016] Dialogue probing-depth failures — VP-010 MPD and VP-011 somatic probes never escalate | 2026-07-11

**Found:** W7b / SC-12 (VP-010 Minimization-Probing Depth instrument; VP-011 somatic-differentiator probes)

**Issue:** VP-010's Minimization-Probing Depth (MPD) instrument scored 0/2 reps reaching Tier-3 ground-truth disclosure on any of its 3 domains (mood/sleep/interest) — the dialogue never asked a numeric/frequency-specific follow-up matching the persona's own Tier-3 exemplars; rep2 cycles a small set of intake questions repeatedly without ever probing sleep or interest at all. Separately, clinical-validator's own read (`CVR-009`) finds VP-011's somatic-differentiator probes never fire across its sessions — a distinct instrument, the same underlying dialogue-depth limitation.

**Evidence:** `result.md` `EXP-016` finding 24 (VP-010 MPD raw observation, the only half independently visible in this mission's whitelisted execution data); `CVR-009` (the VP-011 somatic-probe finding).

**Solution:** Proposed, not yet applied. Filed as `BUG-033` (qa). Clinical-validator (`CVR-009`) rates both instrument failures MAJOR; the underlying cause (the dialogue agent does not escalate probing depth on either the minimization or the somatic-differentiation dimension) is disclosed as one shared dialogue-quality limitation, not two independent defects.

**Status:** open

**Owning gate:** qa + clinical-validator

**Cross-refs:** `BUG-033`, `CVR-009`

---

## [ISS-F2V-017] VP-012 AUD-register safety over-triage — crisis false positive, calibration concern | 2026-07-11

**Found:** W7b / SC-12 (VP-012 rep2)

**Issue:** `crisis_triggered=True` fired at turn 9, despite VP-012's ground truth and every dialogue tier specifying SI/self-harm as unconditionally negative and the persona's own simulation prompt explicitly forbidding SI-lexicon phrases. Traced directly in the artifact: `SafetyClassifier` flagged `safety_categories=['suicidal_ideation','self_harm','distress']` at `safety_risk=medium` on turn-8 patient content that is pure alcohol-control language ("한 번 마시면 멈추기가 어렵고..."); the `DialogueAgent`'s own plan-probing follow-up and the patient's turn-9 reply (still pure alcohol-cessation-failure language, no SI content) were then read as `safety_crisis=True`. Reads as a `SafetyClassifier` false positive keyed on loss-of-control/"의지로 안 되는" phrasing shared between the alcohol-use-disorder and SI risk registers.

**Evidence:** `result.md` `EXP-016`, "Results — SC-12" VP-012 rep2 crisis-flag subsection; finding 21.

**Solution:** Proposed, not yet applied. Filed as `BUG-034` (qa); clinical-validator (`CVR-009`) rates this MAJOR calibration. Fixing requires a `safety_classifier` prompt change, out of this program's licensed scope (safety pinned v2) — consistent with the disclosed `BUG-026` calibration-gap lineage already on record.

**Status:** open

**Owning gate:** qa + clinical-validator

**Cross-refs:** `BUG-034`, `CVR-009`, `BUG-026` (lineage)

---

## [ISS-F2V-018] RAG differentiation/plausibility — PMDD-for-male and pediatric-for-adult recurrence | 2026-07-11

**Found:** W7b / SC-1, SC-12 (`ai_predicted_disease` face-validity)

**Issue:** clinical-validator's face-validity review (`CVR-009`) flags RAG top-5 differentiation and age/sex plausibility as MAJOR and escalating — "월경전 불쾌장애" (premenstrual dysphoric disorder) recurs in `ai_predicted_disease` candidate sets for male personas on 6 of 14 sessions checked, and a pediatric/adolescent-classified entry ("소아·청소년 우울증") recurs for adult personas across multiple sessions. Both patterns are visible raw in `result.md`'s own per-chain candidate tables (SC-1 VP-001/VP-002/VP-004, SC-12 VP-010/VP-011/VP-012 all list one or both entries among their top-5), reported there as observational fact only, without a face-validity verdict (out of experiment-tracker's charter).

**Evidence:** `result.md` `EXP-016` "Results — SC-1"/"Results — SC-12" `domain_candidates`/`ai_predicted_disease` tables (observational only); `CVR-009` (the face-validity verdict itself, including the 6/14 PMDD-for-male count).

**Solution:** Proposed, not yet applied. Filed as `VAL-014` (critic/clinical-validator). No RAG corpus or ranking change has been made this wave; disclosed as an open, escalating finding — first raised in narrower form at `CVR-001` (`EXP-012` read), now confirmed at larger scale in W7b.

**Status:** open

**Owning gate:** clinical-validator + critic

**Cross-refs:** `VAL-014`, `CVR-009`, `CVR-001` (lineage)

---

## [ISS-F2V-019] Shared risk-lexicon paraphrase-evasion — English and Korean, both reach live retrieval | 2026-07-11

**Found:** W7b / SC-2, SC-3, SC-3b (English); SC-5 (Korean)

**Issue:** the Korean-only `_RISK_PHRASES` lexicon fails to catch risk-adjacent paraphrases in either language when they do not match a literal stem. English occurrences: SC-2 VP-003 rep1 Policy B ("passive suicidal ideation..."), SC-3 VP-003 rep2 Policy B ("persistent thoughts of death..."), SC-3b VP-003 repeat 2 Policy B (same query as the SC-2 occurrence, same underlying F1 input) — all reached live retrieval, undetected. Korean occurrence: SC-5 session2's shipped Policy-A fallback query contained "살기 싫어요" ("don't want to live") — a grammatical construction distinct from all 4 existing stems ("살고 싶지 않"/"죽고 싶"/"사라지고 싶"/"짐이 되") — also reaching live retrieval undetected. This gap is **shared by both RAG-trigger policy arms** (Policy A's fallback and Policy B's judge-composed query both pass through the identical lexicon filter) — the W8 Policy A/B adjudication does not resolve or remediate this finding.

**Evidence:** `result.md` `EXP-016` findings 27/31/34 (English) and 43 (Korean); "Results — SC-2"/"SC-3"/"SC-3b"/"SC-5" MET-8 subsections.

**Solution:** Proposed, not yet applied. Filed as `VAL-015` (critic). `REV-030` restates this as a binding caveat on the "Policy A adopted" wording — Policy A's own adoption must not be read as immunity to this shared, open gap.

**Status:** open

**Owning gate:** critic

**Cross-refs:** `VAL-015`, `REV-030`, `BUG-014`/`VAL-009` (lineage — the pre-existing stem-family paraphrase-coverage limitation this finding layers on top of)

---

## [ISS-F2V-020] Modality injection turn-index off-by-one | 2026-07-11

**Found:** W7b / SC-7, SC-11, SC-9 (modality provenance, `AVC-15`)

**Issue:** a reproducible off-by-one exists between `InjectionCue.turn_index` and F1's own persisted `conversation.json` turn numbering for mid-dialogue (`turn_index≥1`) injections — composer index K lands in persisted `turn=K+1`, not `turn=K` as the module's own docstring claims; confirmed this does NOT apply at `turn_index=0` (lands directly in persisted `turn=0`). `injection_protocol.py`'s own `verify_provenance_against_conversation()` helper reproducibly reports a false mismatch for every `K≥1` case as a direct consequence.

**Evidence:** `result.md` `EXP-016` finding 51, "Results — SC-7/SC-11" off-by-one subsection.

**Solution:** Proposed, not yet applied. No BUG/VAL id was supplied for this finding in this pass's routing; tracked here pending formal filing.

**Status:** open

**Owning gate:** qa

**Cross-refs:** none yet

---

## [ISS-F2V-021] Organic "109" hotline mentions without a crisis flag | 2026-07-11

**Found:** W7b / SC-9 (VP-004), SC-11 (VP-003)

**Issue:** the `DialogueAgent` organically inserted "자살예방상담전화 109" into an ordinary empathetic response in 2 separate runs (SC-9 VP-004 turn 5; SC-11 VP-003, 7/10 turns) despite `crisis_triggered=False` in both — free-generated dialogue text, distinct from the formal crisis-substitution template, with no accompanying safety flag or early-return.

**Evidence:** `result.md` `EXP-016` finding 55, "Results — SC-9"/"Results — SC-7/SC-11" sections.

**Solution:** Proposed, not yet applied. No BUG/VAL id was supplied for this finding in this pass's routing; tracked here pending formal filing/disposition (qa/critic attention, per `EXP-016`'s own routing note).

**Status:** open

**Owning gate:** qa + critic

**Cross-refs:** none yet

---

## [ISS-F2V-022] `BUG-022` guard's own W7 re-verification not evidenced (AVC-16 flag) | 2026-07-11

**Found:** W7b (retrospective — the standing `BUG-022`/`AVC-01` field-allowlist guard's own W7 re-verification)

**Issue:** `BUG-022`'s `APPROVED_FIELDS` schema-field guard (the standing `AVC-01` static info-flow protection, active since W1) has no independent W7-cycle re-verification recorded in this blind-execution mission's own whitelisted sources — `result.md` `EXP-016` does not report re-running the guard's own test suite or re-diffing `APPROVED_FIELDS` against the 7-model allowlist during W7a/W7b. This is flagged, not confirmed broken: the guard is a standing pytest-suite fixture (not a per-run behavioral check this program's SC-classes exercise directly), so its absence from `EXP-016`'s own reporting may simply reflect that it was out of scope for a blind-execution tracker role, not that it was skipped.

**Evidence:** `result.md` `EXP-016` (no `BUG-022`/`APPROVED_FIELDS` re-verification recorded anywhere in this entry); `docs/ai/workflow_results_f1f2.md`'s `w1-prereq-fixes-archive`/`w4-policy-ab-implementation` entries (the guard's prior verification record, for contrast).

**Solution:** Proposed. Flagged under the `AVC-16` drift-audit lens per this pass's brief; recommend a qa micro-gate re-confirming `BUG-022`'s guard suite still passes and `APPROVED_FIELDS` is unchanged, before any downstream report treats W7's `AVC-01` protection as continuously verified through the full battery.

**Status:** open

**Owning gate:** qa

**Cross-refs:** `BUG-022` (lineage)

---

## Weak-point register (clinical-validator, `CVR-009`) — 8 items, W7b/W8

> Consolidated register of clinical-adequacy weak points raised by clinical-validator across the W7b battery, cross-referenced to their `ISS-F2V-`/`BUG-`/`VAL-` filing. Severity as rated by `CVR-009`; this register does not itself carry a pass/fail verdict — see `docs/ai/workflow_results_f1f2.md` `w8-adjudication-disposition` for the program-level disposition.

| # | Weak point | Severity | Cross-ref |
|:--:|:--|:--|:--|
| 1 | Bald question repetition (naturalness AND badgering — one root cause: the dialogue agent re-asks near-identical questions without tracking what was already asked/denied) | MAJOR | `ISS-F2V-013` (`BUG-030`), SC-5 item V (`w8-adjudication-disposition`) |
| 2 | RAG differentiation + age/sex plausibility (escalating) | MAJOR | `ISS-F2V-018` (`VAL-014`) |
| 3 | VP-011 somatic-differentiator probes never fire | MAJOR | `ISS-F2V-016` (`BUG-033`) |
| 4 | VP-010 minimization never reaches Tier-3 | MAJOR | `ISS-F2V-016` (`BUG-033`) |
| 5 | SC-8 overwrite has no reconciliation mechanism | MAJOR | `ISS-F2V-015` (`BUG-032`) |
| 6 | VP-012 AUD-register over-triage (calibration) | MAJOR | `ISS-F2V-017` (`BUG-034`) |
| 7 | Empathy-phrase collapse at scale | MAJOR | `ISS-F2V-013` (`BUG-030`) |
| 8 | Organic hotline mentions unflagged | minor | `ISS-F2V-021` |

Items 1 and 7 share a single underlying root cause (the dialogue agent's repetitive-question/repetitive-phrase behavior) but are registered separately because item 1 is a badgering/patient-safety-adjacent concern (SC-5 item V) while item 7 is a naturalness/prompt-compliance concern (`BUG-030`) — `CVR-009` scores them as two distinct findings against two distinct instruments.

---

## Skipped — awaiting user material

Validation cells whose required material is absent are skipped, never fabricated, and marked `SKIPPED-awaiting-user-material` here, in the checklist, and in the results log (`discussion.md` `PLAN-2026-W28-Q`, "Status (2026-07-11, mid-execution user directive — folded immediately)" — this wording supersedes the plan's earlier `BLOCKED-awaiting-user-fixtures` phrasing). Each skipped cell is designed to run standalone later, once the user delivers the missing material, without re-running the rest of the battery — the table below records exactly what that requires.

Currently known: the two OCR fixture types specified in `docs/ai/validation_plan_f1f2_continuous.md` §10, requested from the user but not yet delivered.

| Cell | Missing material | Required inputs/state to run standalone later |
|:--|:--|:--|
| SC-6 — OCR-contradicts-speech (prescription vs. reported medication non-adherence) | Scanned-PDF prescription/dispensing-record fixture (plan §10 fixture (i)): a new genre (the existing 4 fixtures are 진단서-only), scanned image (not digital-text); must name Escitalopram 20mg (VP-004's active prescription, `VP-004_revisit_severe.md:278-279`) or Alprazolam 0.25mg PRN, with a dispensing/refill date implying active use; 1 page, Korean, de-identified per the existing convention; count 2 (n≥2 floor, 1 acceptable if the user limits scope) | Fixture delivered to `docs/ai/simulation_results/<VP>/`, then git-mv'd into `apps/ai-server/tests/fixtures/` (post-W1 move, plan §9 answer #8a); W3 injection composer (`patient_input_fn` seam, STT/OCR arbitrary-turn injection protocol, plan §3) built; VP-004 persona artifacts (the paired scenario cell's grounding persona, plan §10) available |
| SC-10 — OCR document carrying risk-lexicon content | Scanned-PDF clinical referral letter or discharge summary fixture (plan §10 fixture (ii)) with an embedded first-person patient quote register (환자는 '...'라고 표현함); risk content drawn only from the established 20-stem-family taxonomy (`_RISK_PHRASES`; 37 literal entries / 20 stem families, mechanically verified per `REV-025` ruling 3 — supersedes the earlier "15-stem" citation), 1–2 stem families per document, no new stems invented; 1–2 pages, Korean, de-identified per the existing convention; count 2 | Fixture delivered to `docs/ai/simulation_results/<VP>/`, then git-mv'd into `apps/ai-server/tests/fixtures/` (post-W1 move, plan §9 answer #8a); W3 injection composer built; persona artifacts of SC-10's paired scenario cell (VP assignment not yet fixed beyond n=1–2 in plan §5) available |

---
