# F1–F5 total-validation program — final report

> **Scope:** stages A–E of the F1–F5 total-validation program (plan archived at
> `_archive/plans/f1f5_total_validation_plan.md`, wave-4, `version.md` CLEAN-2026-07-16;
> `discussion.md` REV-002 cites the plan's §3/§5/§7 as its adjudication-criteria source — this
> report is the living successor surface).
> **Sources:** `result.md` EXP-025 + `docs/ai/workflow_results_f1f2.md` `[exp-025]` closeout (raw
> 7-VP evidence); `discussion.md` REV-001 (orchestration-quality adjudication), REV-002
> (Stage-D authoritative evidence review), CVR-027 (arc-gate), CVR-028 (Stage-D clinical
> adequacy); `error.md` BUG-031, BUG-020.
> **Wording discipline:** every wording choice below follows REV-002 §6's binding MAY/MUST-NOT
> table. No surface in this report is described as "인증" ("certified") or "검증됨" ("validated").
> This document states what the EXP-025 cohort evidences and what it does not — nothing more.

## 1. Executive summary

The F1→F2→F3 chain ran cleanly across all 7 validation personas (VP-001, VP-002, VP-003,
VP-004, VP-010, VP-011, VP-012): 72/72 scripted sessions completed with `exit_code=0` and 0
fatal failures, no vendor rate-limit or circuit-breaker trips, 2-concurrent execution held for
the whole ~1h36m run (EXP-025). Mechanically, the pipeline is reliable end to end.

Clinically, the cohort is not uniformly adequate. Clinical-validator's Stage-D review
(CVR-028) rules the hand-off report for VP-003 — the cohort's single highest-acuity persona —
**inadequate for its acuity class**: 5 of 11 sessions triggered a crisis flag, yet 0 of 11
sessions administered any questionnaire, so the receiving clinician gets no quantified severity
trend for the patient most likely to need one. This is a blocking clinical finding, not a new
one — CVR-028 confirms it as a live recurrence of a previously-flagged defect (CVR-022 binding
condition 3).

Independent critic re-derivation (REV-002) checked EXP-025's own numbers against raw artifacts
for 2 fully re-derived VPs and found 0 discrepancies; REV-002 also separately adjudicated the
quality of the orchestration-system evidence scan that fed this program (REV-001), which
confirmed 6/6 sampled code-level claims and flagged 5 issues, each dual-ranked for present-day
(local/demo) severity and production-deployment severity.

Issue counts across the three review lenses, by severity (see §3 for the full register):

| Severity | Count | Source |
|:--|--:|:--|
| Blocking (clinical, this cohort) | 1 (VP-003 acuity class) | CVR-028 Finding 1 |
| Blocking (production-only, code) | 2 | REV-001 Issues 1 & 5 |
| Major | ~13 (some overlapping across lenses, see §3) | REV-002 §5, CVR-028, error.md |
| Minor | ~6 | REV-002 §5, error.md |
| Still-pending/not-covered cells | 5 (2 of which structurally cannot close this cohort) | REV-002 §4 |

No surface in this program is described as validated, certified, or deployment-ready anywhere
below (REV-002 §6 row 1, binding).

## 2. 분석 (analysis)

### 2.1 Per-feature behavior across the 7-VP cohort

All numbers below are from EXP-025's 7-VP summary table and standing-audit extraction
(`result.md` EXP-025, cross-checked for VP-002/VP-004 by REV-002 §1's independent
re-derivation, 0 discrepancies found).

| VP | Arc | Sessions | F2 mode | F3 administered | Crisis hits / triggered sessions | F4 direction / course_shape / concordance |
|:--|:--|--:|:--|:--|:--|:--|
| VP-001 | improvement_plateau | 11 | 11/11 rag | PHQ-9 x11 | 4 / 0 | improved / relapse_after_partial_improvement (mislabel, §2.3) / concordant |
| VP-002 | treatment_response_setback | 10 | 10/10 rag | PHQ-9 x10 | 8 / 0 | worsened / unknown / discordant |
| VP-003 | relapse_after_partial_improvement | 11 | 0/11 rag (all llm_only) | **0/11** | 17 / 5 | worsened / unknown / discordant |
| VP-004 | fluctuating_panic_recurrence | 10 | 10/10 rag | PHQ-9 x10 | 54 / 1 | worsened / improvement_with_plateau / discordant |
| VP-010 | stable_minimizing_slow_disclosure | 10 | 10/10 rag | PHQ-9 x10 | 2 / 0 | worsened / improvement_with_plateau / discordant |
| VP-011 | somatic_persistent_late_mood_disclosure | 10 | 9/10 rag | PHQ-9 x10 | 2 / 0 | improved / unknown / concordant |
| VP-012 | aud_escalation_contemplation | 10 | 9/10 rag | PHQ-9 x8 + AUDIT-C x2 | 13 / 0 | improved / improvement_with_plateau / concordant |
| **Total** | | **72** | **61/72 rag** | **61 administered, 11 gaps** | **100 / 6** | |

Standing-audit numbers (all 72 sessions, EXP-025): 129 retrieval queries logged, 2/129 contain
risk-lexicon terms (both VP-004); F2 `validation_errors` non-empty on 10/72 sessions (32 total
field errors); `InputNormalizer` `literal_error` fires 202 times across all 7 VPs (pre-existing,
non-fatal, never halts a chain); 0 rate-limit/circuit-breaker trips.

F1 (intake) and F2 (RAG domain inference) behaved as designed for 6 of 7 VPs — the one
exception, VP-003, never entered RAG mode across all 11 sessions despite `db_preflight=ok`
every time (§2.2). F3 (questionnaire administration) fired correctly whenever F2 recommended a
scale, with one systematic gap: VP-012's AUDIT-C did not trigger until sessions 7–8, six
sessions after `alcohol` first appeared as an F2 domain candidate (session 1). F4/F5
(longitudinal compute + hand-off report) ran on all 7 VPs with no LLM calls, per design; their
output quality is the subject of §2.3–§2.4 and the clinical review in §3.

### 2.2 Orchestration-quality verdict (REV-001)

REV-001 is critic's blind adjudication of a separate developer evidence scan of the F1–F5
orchestration system (`orchestration_review_evidence.md`). Re-checking the scan's own code
citations against the live code, 6 of 6 sampled claims held or were found to understate the
issue (worse for the doc's own conservatism, not for the code): a fail-open `handoff_ready=True`
path, an absent illegal-transition guard, an unsigned client-side session round-trip, an
un-threaded `request_id`, no adapter-level LLM timeout, and RAG DB session scoping — this last
item REV-001 closed outright as correctly-scoped, resolving one of REV-001's own open items in
the doc's favor.

REV-001 dual-ranks every issue for present-day severity (local validation/demo use) and
production-deployment severity, never merging the two:

| Issue | Now (local/demo) | Production |
|:--|:--|:--|
| `handoff_ready=True` with no `handoff_report` field reachable on the wire | major | **blocking** |
| No illegal-transition/idempotency guard on `current_stage` | minor | major-not-blocking |
| No server-side session store / signed round-trip | minor | major-not-blocking |
| `request_id` not threaded past the route layer | minor | minor-to-major |
| No client-level LLM adapter timeout (10-min SDK default) | major | **blocking** |

Net: 5 issues found (2 production-blocking, 2 major at demo severity, 1 minor pair), against 6
confirmed/strengthened positive findings — REV-001 characterizes this as "strong" evidentiary
discipline (numeric/citation accuracy held 6/6 under independent re-derivation) alongside a
genuine, non-trivial "weak" side (2 blocking-for-production defects on the safety-critical and
hand-off paths specifically). Both sides are reported side by side per this project's
never-merge-verdicts convention.

### 2.3 Agent-collaboration observations

The program exercised the project's standard three-lens gate through Stage D: qa filed the
implementation-level defects (BUG-031, BUG-020, both below); critic independently re-derived
EXP-025's own numbers and adjudicated wording license (REV-002); clinical-validator scored
per-VP hand-off adequacy against the intern/nurse-authored bar (CVR-028). All three lenses were
reported without merging verdicts, per project convention — CVR-028 explicitly discloses partial
overlap with REV-002 (both independently flag VP-003 starvation, VP-004's S6 non-escalation, the
VP-002 direction discordance, and the HIRA-key/crisis-fallback gap) as legitimate cross-lane
corroboration from different angles, not a merged conclusion.

### 2.4 3-lens reconciliation — two items where the code-defect hypothesis did not hold

Two raw findings in EXP-025's own data (`workflow_results_f1f2.md`) initially looked like
candidate code defects and were carried into REV-002 §5 as root-cause **hypotheses**, flagged
for qa to root-cause:

- **F4 `course_shape` mislabel (VP-001):** VP-001's F4 output reports
  `course_shape=relapse_after_partial_improvement` — which is VP-003's arc name, not VP-001's
  own `improvement_plateau`. REV-002 §5's initial hypothesis was a shared static string or an
  off-by-one VP index inside F4's course-shape classifier (a code bug).
- **VP-010 metric split:** `slot_coverage` sits flat at 0.6 across all 10 sessions while
  `grounded_coverage` rises 0.375→0.875 over the same sessions — two fields both labeled
  "coverage" moving independently. REV-002 §5's initial framing was a silent divergence between
  two coverage metrics computed over different denominators, filed as a dashboard-trust risk for
  qa to clarify.

Per this report's brief, qa's own hand-derivation of these two items reaches a different
conclusion than the initial code-defect hypothesis in both cases, reclassifying them out of the
code-bug category:

- (a) the `course_shape` finding is reclassified as **simulator arc-fidelity drift**, not a
  classifier indexing bug: VP-001's actual longitudinal PHQ-9 series is read as genuinely
  matching a relapse-after-partial-improvement shape rather than the arc's own designed plateau
  — i.e., the classifier may be reporting the shape it actually observed in the data, and the
  drift is in the simulated patient trajectory versus its own design intent, not in the labeling
  code.
- (b) the `slot_coverage`/`grounded_coverage` split is reclassified as a **documentation gap**,
  not a metric-computation defect: the two fields are two intentionally distinct, differently-
  denominated coverage measures that were never documented as such, so their divergence reads as
  a bug only in the absence of a definitions note.

**Traceability caveat (this report, flagged honestly):** at the time of writing, neither
reclassification (a) nor (b) has its own qa entry in `error.md` or a status-update row in
`discussion.md` independent of this report — REV-002 §5's two rows still stand as open,
qa-owned, code-hypothesis items in the current record. This report carries the reclassification
forward as directed, but the traceable, citable qa root-cause record for both items should be
filed before either is treated as closed to the code-defect hypothesis in any future report. See
the Issue register (§3, rows "F4 course_shape" and "VP-010 metric split") and the RESULT block at
the end of this deliverable.

## 3. Issue register

Consolidated from REV-002 §5 (critic's 12-row register), qa's post-adjudication updates
(BUG-031 filed new; the two reclassifications in §2.4), CVR-028's additional clinical findings,
and the standing process/taxonomy gaps flagged this program.

| ID | Issue | Evidence | Severity (now/production) | Root cause | 해결방안 | Owner lane |
|:--|:--|:--|:--|:--|:--|:--|
| REG-1 | VP-003 starvation — 0/11 F3 administered, `mode=llm_only` all 11 sessions despite `db_preflight=ok` | EXP-025, `workflow_results_f1f2.md` VP-003 detail | major/major (clinical: **blocking**, CVR-028 F1) | F2's RAG-mode entry condition not diagnosed (empty chief_complaint/HPI slots or an embedding error is suspected, not confirmed) | Instrument F2's RAG-fallback branch to log *why* it fell back; separately, add a crisis-triggered safety-net questionnaire path independent of F2 success (CVR-028 recommendation, highest priority) | qa (instrumentation) + developer (safety-net path) |
| REG-2 | F4 `course_shape` mislabel (VP-001) | EXP-025, `workflow_results_f1f2.md` | major/major → reclassified simulator arc-fidelity drift (§2.4a), not confirmed a code bug | Initial hypothesis: shared static string/VP-index bug in F4's classifier. Reclassified hypothesis (qa, not yet independently filed): the classifier may be reporting VP-001's actually-observed relapse-shaped trajectory, not mislabeling it | File the qa root-cause record independently in `error.md`/`discussion.md`; if arc-fidelity drift is confirmed, the fix is a simulator-arc-design question, not a code fix | qa (root-cause record) → design decision |
| REG-3 | VP-010 metric split (`slot_coverage` flat 0.6 vs. rising `grounded_coverage`) | EXP-025 | minor/major → reclassified documentation gap (§2.4b), not confirmed a metric-computation defect | Two coverage metrics computed over different denominators, never documented as distinct | Document both metrics' definitions distinctly; no code change indicated unless qa's reclassification is itself overturned | qa (doc) |
| REG-4 | F2 `validation_errors` — new error class, 10/72 sessions, 32 errors, atomic-drop of `domain_candidates` | error.md BUG-031, REV-002 §5 | major/major | Confirmed: `DomainInferenceAgent._parse` validates the entire LLM response as one Pydantic model; one field failure (chiefly `domain="panic"`, an out-of-enum literal) drops *all* candidates in that session, not just the offending one | Per-item validation instead of atomic whole-response validation; add `"panic"` to the domain enum (or map to `"anxiety"` pre-validation) | qa/developer (BUG-031) |
| REG-5 | InputNormalizer `literal_error`, 202 occurrences across all 7 VPs | error.md BUG-020 | minor/minor | Standing, pre-existing, non-fatal — not introduced this mission | Track as a standing metric; no action required this cycle (accepted) | design decision (accepted) |
| REG-6 | Risk-worded queries reaching retrieval (VP-004, 2/129) | REV-002 §2 | major/blocking-if-external | `retrieval_meta.queries` embeds raw `chief_complaint` text including risk phrases | Strip/redact risk-lexicon spans before query construction | qa fix (**reproduction of already-open VAL-010**, not a new finding — REV-002 §6 row 2, binding) |
| REG-7 | HIRA key absence — every VP-003 crisis (5/5) fell back to static crisis text, not live nearby-hospital lookup | REV-002 §5, `workflow_results_f1f2.md` VP-003 detail | major/blocking | `HIRA_SERVICE_KEY` absent from `.env` | User must supply `HIRA_SERVICE_KEY` (already requested, "PENDING USER" per handoff.json) | user decision |
| REG-8 | REV-001 production-blocking pair — `handoff_report` unreachable on the wire; no LLM adapter timeout | REV-001 Issues 1 & 5 | blocking (production) / major-visible (demo) | See REV-001 §2.2 above | Add `handoff_report` field to `DialogueOutput`; add `timeout=` to the 3 `AsyncOpenAI()` constructions | qa/developer fix |
| REG-9 | `f3.py:141` unvalidated F2→F3 artifact read | REV-002 §1 (confirmed this review, closing REV-001's own open item) | minor (read-only, no crash observed) | `load_recommendation` uses `.get()` on raw JSON, no `model_validate()` | Add schema validation at the F2→F3 boundary read site | qa fix |
| REG-10 | Cross-app "1393" legacy reference | REV-002 §5 (unverified whether stale — flagged **needs fresh repo-wide grep**) | minor (unverified) | Possible second occurrence outside the already-fixed `orchestrator.py` file, or a stale docket carry-forward | qa: grep full repo for "1393" outside the fixed file before citing this as open or closed | qa (needs re-scoping first) |
| REG-11 | `error.md` carry-forward visibility gap | REV-002 §2 | major (process) | VER-003 archival chose handoff.json-pointer carry-forward over `error.md` rows for VAL-010/014/016, with no ADR on record for the deviation | Restore `error.md` rows for VAL-010/014/016, or write an ADR documenting the deviation | design decision (orchestrator) |
| REG-12 | `panic` domain value not in the F2 domain enum | error.md BUG-031 (root cause 1) | major/major (same underlying defect as REG-4, listed separately per the brief's taxonomy framing) | The domain `Literal` enum has no `"panic"` value and no `panic`→`anxiety` synonym mapping — VP-004's `fluctuating_panic_recurrence` arc naturally elicits this LLM output, driving 5 of 10 BUG-031 errors this VP | Same fix as REG-4 (add `"panic"` to the enum or pre-validation map it) | qa/developer (folds into BUG-031) |
| REG-13 | VP-010 risk-label mislabel — "SI expressed" label contradicted by its own cited denial quote | CVR-028 Finding 4 | major/report-integrity | Risk-assessment slot label persists "자살/자해 사고 표현 있음" from S3–S10 even where the current-session quoted evidence is an explicit denial | Audit risk-assessment categorical labels against their own cited quote text across the full cohort — the VP-010 instance may not be isolated | developer/clinical-validator |
| REG-14 | VP-004 near-ceiling caveat gap + a flat-score "worsened" mislabel | CVR-028 Finding 3 | major | Over-endorsement caveat attached only to the two true-ceiling (27/27) rows, not the eight near-ceiling (26/27) rows; a 26→26 (+0) change is labeled "악화" (worsened) in the trend table | Extend the over-endorsement caveat to near-ceiling scores; do not label a +0 change as directional worsening | developer/clinical-validator |
| REG-15 | VP-002 headline-body contradiction | CVR-028 Finding 7 | minor-major | Headline reads "no notable concerns" while the report's own trend section computes `전체 방향=악화` (worsened) three paragraphs later, driven by F4's known worsened-priority tie-break | Reconcile headline generation with the trend-section output before both ship in the same report | developer (F4/F5) |
| REG-16 | VP-011 designed-disclosure not evidenced in the exported artifact | CVR-028 Finding 5 | major | The scripted late-mood-disclosure reveal (designed not reachable before session 7) is not evidenced anywhere in the exported hand-off report; the S10 quote is an explicit somatic-only denial | Verify future reveal/disclosure-design personas against the *exported* hand-off artifact, not just the underlying dialogue | brainstorm/clinical-validator (scenario design) |
| REG-17 | Panic not in the domain taxonomy enum (naming distinct from REG-12: this is the taxonomy-completeness framing, not the code-fix framing) | error.md BUG-031, REV-002 §5 | major/major | Same underlying gap as REG-4/REG-12 — flagged separately because it is a taxonomy-design question (should "panic" exist as its own domain, distinct from anxiety) as well as a code fix | Taxonomy decision: is panic a first-class domain or an anxiety subtype — resolve before the enum fix ships | design decision (developer + brainstorm) |
| REG-18 | REV-001 pair, deferred (duplicate cross-reference) | REV-001, REV-002 §5 | blocking (production) | See REG-8 | See REG-8 — listed once in REG-8, cross-referenced here per the brief's explicit register requirement | qa/developer |

Two carried-over cells with an honest not-satisfied disposition (AUDIT-C female-threshold,
AUDIT-C non-soju track) are **not** listed as issue-register rows — they are structural
non-coverage, not defects, and are reported in §5.

## 4. 해결방안 우선순위 로드맵 (remediation priority roadmap)

**P0 — clinical-blocking, address before any real-patient use:**
- Implement a crisis-triggered safety-net questionnaire path (PHQ-9 item 9 at minimum) for
  VP-003-class sessions where `crisis_triggered=True` fires but F2's own recommendation path
  fails — independent of F2's RAG/questionnaire-recommendation success (REG-1, CVR-028 Finding
  1, highest clinical priority).
- BUG-031 fix: per-candidate F2 validation instead of atomic whole-response validation, plus the
  `panic` domain-enum gap (REG-4/REG-12/REG-17).
- REV-001's production-blocking pair: `handoff_report` wire-contract gap and missing LLM adapter
  timeouts (REG-8/REG-18) — both are cheap, well-scoped fixes REV-001 itself rates as no reason
  to defer even locally once noticed.

**P1 — major, next development cycle:**
- Simulator over-endorsement program: the whole-instrument answer-LLM over-endorsement pattern
  carried from prior missions (ISS-F2V-028/029 lineage) remains open and unmitigated; this
  cohort adds no new factorial evidence but does not contradict it.
- VP-010 risk-label fix (REG-13) and a cohort-wide audit of categorical-label-vs-quote
  consistency.
- Near-ceiling PHQ-9 caveat extension (REG-14).
- F4 headline/trend tie-break consistency fix (REG-15) and VP-011 reveal-artifact verification
  discipline for future scenario design (REG-16).
- VP-012 AUDIT-C trigger lag (6-session gap between candidate-domain detection and
  questionnaire recommendation) — not separately registered above but visible in §2.1; consider
  an intake-time AUDIT/CAGE trigger keyed off domain-candidate presence.

**P2 — doc/metric clarifications, low urgency:**
- File the qa root-cause records for the two §2.4 reclassifications (course_shape,
  slot_coverage/grounded_coverage) so they carry independent traceability.
- `f3.py:141` schema validation at the F2→F3 read boundary (REG-9).
- `request_id` threading (REV-001 Issue 4) and `InputNormalizer` standing-metric tracking
  (REG-5).
- Cross-app "1393" fresh grep before citing as open/closed either way (REG-10).
- `HIRA_SERVICE_KEY` — pending the user's own decision on provisioning (REG-7).

## 5. 미충족/보류 셀 (unmet / pending cells — honest disclosure, no closure claim)

Per REV-002 §4, this cohort does **not** close every carried-over cell from prior missions.
Reported here plainly, with no wording implying otherwise (REV-002 §6 row 3, binding):

- **AUDIT-C female-threshold** (CVR-019 binding condition 3): **not satisfied.** 3 female
  personas exist in this cohort (VP-001, VP-004, VP-011), but F2 never recommended AUDIT-C for
  any of them — only VP-012 (male) received it. The sex-conditional Korean-primary threshold
  branch was not exercised.
- **AUDIT-C non-soju track** (CVR-019 binding condition 1): **not satisfied.** Only VP-012
  administered AUDIT-C, and VP-012 is a scripted soju drinker (`VP-012_first_visit_alcohol.md`).
  The secondary (non-soju) anchor track was never exercised.
- **Bugfix live-verification set** (SM-01..08b, naturalness probes, SC-5-style crisis-adjacent
  cell): **still pending.** No SM-/probe/SC-5 artifacts exist under `experiments/EXP-025/` — the
  plan itself frames stage D as this set's first live-verification opportunity; Stage B ran only
  the 7-VP F1→F2→F3 chain.
- **OCR SC-6/SC-10:** correctly **SKIPPED-awaiting-user-material** — no user-provided OCR
  fixtures exist beyond the 4 pre-existing files, consistent with the plan's own instruction, not
  a gap in execution.
- **STT live cells:** exercised only where the 7-VP chain itself required them; no separate
  live-battery re-verification was run this stage.
- **Narrative condition A:** correctly **not exercised** — the narrative hand-off path stays
  descoped per ADR-037, an explicit design decision, not a gap.
- **VP-011's designed late-disclosure reveal:** design-intent-not-evidenced (REG-16) — not
  distinguishable from these artifacts whether the reveal fired in the underlying dialogue and
  was never captured into a slot, or never fired at all.

## 6. Verdict

Per REV-002 §6's binding wording table:

- This report **may** state: 7/7 VPs, 72/72 sessions, 0 fatal failures (re-confirmed
  independently by REV-002 §1 for 2 fully re-derived VPs). It **must not** describe any F1–F5
  surface as "validated" or "certified."
- The VP-004 risk-worded-query finding (2/129) **is** a reproduction of the already-open VAL-010
  finding, not a new discovery — reported as such here, not presented as first-observed.
- The AUDIT-C carried-over cells are stated as **still pending** (§5) — this cohort's design
  (no non-soju persona, no AUDIT-C-triggering female persona) structurally could not close them;
  "VP-012 administered AUDIT-C twice" does not satisfy either binding condition.
- `f3.py:141`'s lack of `model_validate()` is stated as **confirmed** (REV-002 closed REV-001's
  own open item on this), not carried forward as unverified.
- The HIRA crisis-fallback degradation is reported as a real, observed clinical-adjacent
  degradation (it fired in all 5/5 crisis sessions this cohort's crisis path activated this run)
  — not characterized as hypothetical or low-probability.
- `error.md`'s current 0-row state is noted as a process/visibility gap requiring orchestrator
  disposition (REG-11) — it is not evidence that no BUG/VAL is open; VAL-010/014/016 are open
  per `.claude/state/handoff.json`.

**What this cohort evidences:** the F1→F2→F3 orchestration pipeline is mechanically reliable
across a diverse 7-persona, 72-session cohort (0 fatal failures, 0 vendor-side trips); the
orchestration-system code review underlying this program's design (REV-001) holds up under
independent re-verification (6/6 sampled claims confirmed); a specific, previously-flagged
clinical gap (crisis-heavy patients receiving no quantified questionnaire data) reproduces live
and is confirmed not resolved (CVR-028 Finding 1, blocking).

**What this cohort does not show:** it does not show that the F2 domain-inference schema
fragility (BUG-031), the simulator over-endorsement pattern, or the AUDIT-C carried-over gaps
are fixed, mitigated, or even fully characterized — all remain open per the register in §3 and
the disclosure in §5. It does not license any deployment-readiness claim for any of the F1–F5
surfaces this program touched.

---

*Report prepared by writer, synthesizing EXP-025, REV-001, REV-002, CVR-028, BUG-031, BUG-020.
No new numbers were generated in this document; every figure traces to one of the cited entries.*
