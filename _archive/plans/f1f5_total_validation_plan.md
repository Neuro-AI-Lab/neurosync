# F1–F5 total-validation program plan

> Status: plan document. Stages A–F per orchestrator/conductor briefing. Companion doc:
> `docs/ai/agent_collaboration_f1f5.md` (per-feature agent composition this program exercises).
> Monitoring surface: this file + `docs/ai/workflow_checklist_f1f2.md` /
> `docs/ai/workflow_results_f1f2.md` (existing per-wave record convention, `DR-015`..`022`
> preamble) + `docs/ai/PRD_task1_v2.md` / `docs/ai/checklist_task1.md` synced at close.

## 1. Cohort

**7 VPs × ≤10 sessions each, ≤6 months simulated span.**

| VP | Arc source | Status |
|:--|:--|:--|
| VP-001 | Reuses the `improvement_plateau` 11-session arc scripted for `EXP-023` (`apps/ai-server/tests/simulation/scenario_pack.py`, `DR-021` §3) | existing, reused |
| VP-003 | Reuses the `relapse_after_partial_improvement` 11-session arc, same source | existing, reused |
| VP-002, VP-004, VP-010, VP-011, VP-012 | 5 new arcs — being designed against each persona's documented baseline (`docs/ai/personas/VP-0NN_*.md`), following `EXP-023`'s cadence-taper protocol (weekly → biweekly → monthly) | new, in design |

Reused arcs are capped at ≤10 sessions for this program even though the source arcs ran 11
(`EXP-023` was day 0–183); the cap is this program's own budget decision, not a reuse-fidelity
claim — session 11 content is simply not replayed here.

## 2. Stages

| Stage | Name | Content |
|:--|:--|:--|
| **A** | 설계 (design) | Arc design for the 5 new VPs (brainstorm/developer), pre-registered acceptance criteria per feature (critic), clinical scenario review (clinical-validator) — mirrors the dual-pre-implementation-gate pattern already used for F3/F4/F5 (`REV-036`/`CVR-015`, `REV-044`/`CVR-020`, `REV-046`/`CVR-023`). |
| **B** | 수집 (collection) | Live F1→F2→F3 session-by-session execution for all 7 VPs, chained via `continuous_test.py`. Blind re-arm is in effect (§4). |
| **C** | F4/F5 (compute) | Deterministic F4 longitudinal pass + F5 hand-off report generation (md/PDF/FHIR) per VP, from the session series collection produced. Zero LLM calls in either stage. Blind re-arm still in effect. |
| **D** | 감사·이슈수집 (audit / issue collection) | Standing audits (§5) run on every live batch; carried-over cells from prior missions (§3) are absorbed here rather than run as a separate wave; new issues are filed (`BUG-`/`VAL-`/`ISS-F2V-`) as found. Blind re-arm still in effect through the end of this stage. |
| **E** | 분석/issue/해결방안 보고 (analysis / issue / remediation report) | Writer synthesizes stage D's findings into a `REPORT-`/`DR-`-equivalent entry: what ran, what passed/failed against pre-registered criteria, every open issue with its ID, and remediation options — never a fix itself (fixes route back through developer/qa under a fresh mission if the evidence licenses one). Three-lens gate (§6) reviews the report before it is treated as final. |
| **F** | 아카이빙 (archiving) | Blind re-arm lifts. Filesystem archiving pass (§7) — separate from, and does not gate, the version-management archival of `result.md`/`discussion.md`/`error.md` into `version.md`, which follows the project's standing version-bump procedure if a version transition is separately triggered. |

## 3. Carried-over cells (absorbed into stage D)

These are pre-existing, not-yet-live-verified obligations from prior missions; this program is
their first live-verification opportunity rather than a dedicated re-run wave:

- **Bugfix live verification set** — SM-01..08b (11 safety-matrix scenarios) + naturalness probes
  (VP-001/VP-003/VP-010, 3 cells) + one SC-5-style crisis-adjacent cell (~4 calls), deferred since
  the combined `BUG-036`/`ADR-030`/`BUG-037` fix cycle (`DR-017` §4: "code-complete, offline-gated,
  NOT live-verified").
- **Narrative condition A** — the F5 narrative-wave adversarial leak-guard extension named in
  `workflow_checklist_f1f2.md`'s F5 finding-4 follow-up (non-exact-match diagnostic-language test
  case) — informational only in this program; the narrative path itself stays descoped
  (`ADR-037`) and is not exercised by stage B/C.
- **`ISS-F2V-026`..`029` observations** — near-tie questionnaire-linkage policy, item-8 elicitation
  artifact, whole-instrument over-endorsement (PHQ-9/GAD-7), and the AUDIT-C v2 scale-ceiling
  instance — all open, all narrowed-not-resolved; this cohort's larger n gives each a further data
  point, not a fix attempt.
- **AUDIT-C second-track / female-threshold live exercise** — `CVR-019` binding conditions 1
  (non-soju-drinking-persona administration exercising the newly-rendered secondary anchor track)
  and 3 (a live female-persona administration exercising the sex-conditional Korean-primary
  threshold branch) — both open, both satisfiable by this cohort if it includes a qualifying
  female persona and a non-soju-drinker arc.
- **OCR SC-6/SC-10** — remain `SKIPPED-awaiting-user-material` (no user-provided OCR fixtures on
  disk beyond the 4 pre-existing 진단서 PDFs, `workflow_checklist_f1f2.md`). Not fabricated; not
  retried in this program unless the user supplies material.

## 4. Blind re-arm (stages B–D)

The project's blind-validation mechanical hook re-arms for the duration of stages B, C, and D:
scenario/persona detail and prior-battery numeric outcomes are kept out of the executing agents'
live context (`_archive/` + hook block pattern, per this project's standing blind-validation
protocol), so that F1→F5 collection and audit run as close to an external, un-primed review as the
harness allows. The hook **lifts at stage F** — archiving and reporting do not need to stay blind,
and stage E's own report synthesis already requires full cross-reference to prior DR/REV/CVR
entries, which is incompatible with a blind context.

## 5. Standing audits (run on every applicable live batch, not one-time gates)

- **`ADR-018` RAG-arm audits** — secondary taxonomy audit (accepted post-cascade evidence quotes
  checked against the broader risk-lexicon taxonomy, must stay at 0/N) and the
  `retrieval_meta.queries` audit (`VAL-010`, open) on every F2 RAG-mode call this cohort makes.
- **HPI isolation** — the `tests/test_hpi_isolation.py` (F2) / `tests/test_f3_hpi_isolation.py`
  (F3) adversarial suites gate any code touched during stage A; live artifacts from stages B/C are
  spot-checked by the stage-D audit for the same two channels (`AgentInput.extra`,
  `conversation_history`) plus the F5-specific narrative-descope check (`f5.py:551-559`'s
  `ValueError` guard, confirmed still firing).
- **Wording discipline** — every MAY/MUST-NOT table this project has pre-registered
  (`REV-012`/`REV-015`/`REV-018`/`REV-037`/`REV-039`/`REV-042`/`REV-045`/`REV-047`) remains binding
  on stage E's report; no "인증"/"검증됨"/"certified" wording for any surface those tables restrict.

## 6. Three-lens gating

Every stage-D finding and the stage-E report pass through the project's standing triple gate,
**reported side by side, never merged into one verdict** (the pattern used throughout `DR-015`..
`DR-022`): qa (implementation correctness — code gate, mutation checks), critic (research
validity — independent re-derivation of every number from raw artifacts, wording-license
adjudication), and clinical-validator (clinical adequacy — CVR entries, a separate concern from
both of the above, per this project's dual-QA convention).

All clinical-adequacy review in this program — every CVR entry, the clinical-validator lens above
included — is **AI-simulated review** performed by the `clinical-validator` agent, not review by a
licensed clinician; every finding, sign-off, and downstream report wording must be phrased
accordingly (CVR-027).

## 7. F5 quality bar

The user's own frame, adopted as this program's F5 acceptance bar: a hand-off report is adequate
if it reads the way **an intern- or nurse-authored hand-off note** would — usable by a receiving
clinician without needing to decode pipeline jargon or infer missing context. This is stricter
than, and supersedes for this program, a bare structural-completeness check (all 12+ sections
present) — `CVR-024`'s open finding that A6's `reason_summary` renders untranslated English
pipeline jargon in a real report is exactly the kind of gap this bar is meant to catch going
forward.

## 8. Stage-F archiving criteria

Candidates for archiving are files **not needed for F1–F5 to operate** — superseded plan/research
docs, stale intermediate `.md`/`.json`/`.py` artifacts whose content has been folded into a
current, authoritative doc (e.g. `development_report.md`, `PRD_task1_v2.md`,
`checklist_task1.md`), or one-off scratch files (`*_scratch_*.md`) from closed missions. Process:
filemanager runs a scan and produces a candidate list (path + reason each is believed obsolete);
**the user confirms the list before any file is moved** — nothing is archived unilaterally. Moved
files land under the project's existing `_archive/` convention (already used for prior root-doc
snapshots, agent-memory notes, and superseded plans), not deleted.

## 9. Report paths

- This plan: `docs/ai/f1f5_total_validation_plan.md`.
- Per-feature collaboration map: `docs/ai/agent_collaboration_f1f5.md`.
- Per-wave execution record: `docs/ai/workflow_checklist_f1f2.md` (gate/status tracker) and
  `docs/ai/workflow_results_f1f2.md` (parked DR-equivalent detail, per its own disclosed
  convention).
- Stage-E synthesis: appended to `docs/ai/development_report.md` as the next `DR-NNN` entry, plus
  a `discussion.md` `STATE-YYYY-MM-DD` entry (orchestrator).
- Doc-drift sync at close: `docs/ai/PRD_task1_v2.md`, `docs/ai/checklist_task1.md`.
