# Stage F — archive-candidate list (scan only, no moves)

> **Status:** SCAN ONLY. No `git mv` has been executed. This list requires user approval before
> any file is moved. Produced per Stage F of the total-validation program
> (`docs/ai/f1f5_total_validation_plan.md`), user directive: archive old md/json/py files
> unnecessary to F1-F5 functional operation, to prevent confusion for future collaborating
> engineers pre-deployment.
> **Method:** liveness determined by import-graph grep (`py`), cross-reference grep against the
> current LIVING doc set + `discussion.md`/`result.md`/`error.md`/`version.md`/`handoff.json`
> (`md`), and filename-timestamp bucketing against `EXP-025`'s wall-clock window
> (`json`/artifacts). Destinations map onto the existing `_archive/` subfolder taxonomy
> (`_archive/README.md`): `plans/`, `reports/`, `legacy_code/`, `simulation_results/`.
> **Git state at scan time:** branch `feat/f1f5-total-validation`, HEAD `91af623db134751e4c3f020bc0a9ba429b149cb8`, worktree has 2 uncommitted modifications (`continuous_test.py`, `test_continuous_test_f4.py` — unrelated to this scan, not touched).

## Counts summary

| Category | Candidates | Destination (proposed) |
|:--|--:|:--|
| py (analysis/ one-off scripts) | 4 | `_archive/legacy_code/analysis_scripts/` |
| md (docs/ai/, superseded mid-mission docs) | 11 | `_archive/plans/` (design/proposal-shaped) or `_archive/reports/` (review/scratch-shaped) — split below |
| json/artifacts (pre-EXP-025 simulation_results) | 490 files across 8 subtrees | `_archive/simulation_results/` (extends the existing wave-1 manifest) |
| **Total files** | **~505** | |

No repo-root strays, no `apps/ai-server` root-script strays, no new `_backup`-pattern directories
outside the existing `_archive/` were found this scan (checked explicitly, see §4).

---

## 1. Python — `analysis/` one-off scripts

| Path | 분류근거 | Destination |
|:--|:--|:--|
| `analysis/aud_ontology_load_verification.py` | Zero references outside `_archive/root_docs_snapshot/discussion_2026-07-11.md` (an already-archived snapshot). One-off DATASET-005-addendum re-verification of the W6 AUD-ontology DB load (`PLAN-2026-W28-Q` W6 close-out, commit `1f47c54`); findings already condensed into `version.md`'s `DATASET-003-ext`/`DATASET-004-ext` archive and `docs/ai/workflow_results_f1f2.md` `w6-personas-golden-canary-ontology`. Served its EXP/DATASET purpose. | `_archive/legacy_code/analysis_scripts/` |
| `analysis/canary_zero_hit_verification.py` | Same pattern — DATASET-006 one-off canary zero-hit check (W6/W7A), findings folded into `workflow_results_f1f2.md` `w7a-micro-batteries` (`AVC-17` pins). Zero live references. | `_archive/legacy_code/analysis_scripts/` |
| `analysis/rag_corpus_leakage_audit.py` | Same pattern — DATASET-005 one-off leakage audit (`PLAN-2026-W28-G` T2-data/W1c). Zero live references. | `_archive/legacy_code/analysis_scripts/` |
| `analysis/w7b_golden_scoring.py` | Zero references anywhere in the repo (not even in the archived snapshot). One-off blind-scorer worksheet for W7b's MET-1/MET-3 (`docs/ai/golden_labels_f1f2.md` scoring rule against `SC-1`/`SC-12`/`SC-3`); result already reported as the headline `MET-3 17/22 top-1, 18/22 top-3` in `result.md` history and `workflow_results_f1f2.md` `w7b-main-matrix` (now archived into `version.md`). | `_archive/legacy_code/analysis_scripts/` |

**DO NOT MOVE:** `analysis/threshold_n_met8_w1_20260711.py` — actively cited by name in a live
production-code comment (`apps/ai-server/src/rag_trigger.py:100`) and in the still-open
`validation_plan_f1f2_continuous.md:412` data-basis line ("Reproducible script:
`analysis/threshold_n_met8_w1_20260711.py`"). Reproducibility artifact, not a scratch script.

No py candidates found under `apps/ai-server/src` or `apps/ai-server/tests`: full import-graph
check (`grep` for every module name against `src/**` and `tests/**`) found every module reachable
— `input_normalizer` is imported live by `f1.py:40/67` (CHECKED per brief instruction, confirmed
wired, not dead code); `continuous_test.py` is the active F1→F2→F3→F4→F5 chaining harness used by
`EXP-025` and has an **open BUG** row pointing at it in `error.md`; `run_injected_session.py` and
`avc12_instrumentation.py` each have a live 1:1 test file. `pytest --collect-only` on
`apps/ai-server` collects **1984 tests, 0 errors** — no test file references a deleted module or
fixture path. The `test_prompt_v2.py`/`test_prompt_v3.py`/`test_dialogue_v3_opening.py` trio,
which might look like dead-version cruft, is intentional: the project's own rollback policy keeps
`v1.system.md`..`v4.system.md` all on disk, and `test_prompt_v2.py`'s docstring explicitly
documents its narrowed, still-valid scope after the runtime-behavior assertions moved to v3's test
file. Not a candidate.

---

## 2. Markdown — `docs/ai/*.md`

### 2a. SUPERSEDED — confident (content absorbed into code + the living log docs)

| Path | 분류근거 | Destination |
|:--|:--|:--|
| `docs/ai/fix_proposal_bug030.md` | BUG-030 iteration-1 proposal; iteration-1 was superseded by iteration-2 (`ADR-029`); content condensed into `workflow_results_f1f2.md`'s `bug030-fix-revalidation`/`bug030-iter2-revalidation` entries. Referenced only by other docs in this same superseded cluster + the log. | `_archive/plans/` |
| `docs/ai/fix_design_bug030_iter2.md` | BUG-030 iteration-2 design, ratified `ADR-029`, landed at `d68c8a2`. Fully absorbed into `workflow_results_f1f2.md` `bug030-iter2-revalidation` narrative. | `_archive/plans/` |
| `docs/ai/critic_scratch_rev032_bug030iter2.md` | `REV-032` pre-implementation review scratch for iter-2; referenced only within this closed cluster. | `_archive/reports/` |
| `docs/ai/critic_scratch_rev033_exp018.md` | `REV-033` post-implementation review scratch for `EXP-018`; single reference (`workflow_results_f1f2.md`, log pointer only). | `_archive/reports/` |
| `docs/ai/pr_description_phr_and_medication.md` | PR-description doc for the already-merged PHR + HIRA-drug-efficacy feature (commits `06faa30`..`f4fd234`, `hira_pharmacy.py`/`hira_drug_efficacy.py`/`patient_history.py` all live and wired). Zero references from any living index doc (`PRD_task1_v2.md`, `checklist_task1.md`, `development_report.md`, `workflow_*`, `discussion.md`/`result.md`/`error.md`/`version.md`) — only self-references within its own 3-doc cluster. | `_archive/reports/` |
| `docs/ai/pr_description_phr_integration.md` | Same PHR PR-description cluster, same zero-external-reference finding. | `_archive/reports/` |
| `docs/ai/phr_integration_plan.md` | Pre-implementation plan for the same, now-merged PHR feature. Zero external references. | `_archive/plans/` |
| `docs/ai/exp021_factorial_design.md` | `ISS-F2V-028` factorial-decomposition design (`PLAN-2026-W29-B` Track 3), ruled "no dominant factor/inconclusive." Referenced only by `checklist_task1.md` T1-F3-DEV-018 (a closed `[x]` row) and the closed `workflow_results_f1f2.md`/`development_report.md` log entries — not by `item_bank_v1_sources.md` or any still-open item. Raw data preserved in `experiments/EXP-021/`. | `_archive/plans/` |
| `docs/ai/rubric_bug030_acceptance.md` | Pre-registered BUG-030 acceptance rubric (§1-9 base + §10/§10.4 iter-2 addenda). **See §5 uncertainty below before moving — flagged, not confident.** | `_archive/plans/` (hold pending §5) |
| `docs/ai/fix_design_exhaustion_bug037.md` | Combined 3-fix-cycle design (`BUG-036` dedup / `ADR-030` exhaustion degrade / `BUG-037` output isolation), landed `5baefb9`/`e833937`. **See §5 uncertainty below — flagged, not confident.** | `_archive/plans/` (hold pending §5) |
| `docs/ai/cv_scratch_cvr013.md` | `CVR-013`/`CVR-014` clinical-adequacy scratch for the same 3-fix cycle. Single reference. **See §5 — flagged.** | `_archive/reports/` (hold pending §5) |
| `docs/ai/critic_scratch_rev034_fixcycle.md` | `REV-034`/`REV-035` critic scratch for the same cycle. Single reference. **See §5 — flagged.** | `_archive/reports/` (hold pending §5) |

### 2b. DO NOT MOVE — living, load-bearing (looked old, is not)

| Path | Reference that keeps it alive |
|:--|:--|
| `docs/ai/orchestration_review_evidence.md` | **Actively under adjudication right now** — `discussion.md` `REV-001` (open, dated today) reviews this exact document. Moving it would break an open review. |
| `docs/ai/audit_c_korean_research.md` | `item_bank_v1_sources.md` (explicit LIVING doc, refcount 22) structurally depends on it — repeated "Full sourcing session: `docs/ai/audit_c_korean_research.md` §1/§3/§3.4" pointers, not narrative-only citations; the adopted AUDIT-C v2 cutoffs (male/unknown≥6, female≥5) trace their justification chain through this file. |
| `docs/ai/who5_sourcing_retry2.md` | Same structural dependency from `item_bank_v1_sources.md` (§4.7, "Pointer: full retry log in..."). The WHO-5 gap this file documents is **still open** (0/5 unpopulated, no fix licensed) — not a closed research question. |
| `docs/ai/golden_labels_f1f2.md` | Cited by `validation_plan_f1f2_continuous.md:654` as the live scoring-rule source for VP-010's MET-1/MET-3 dual-report convention ("per... `docs/ai/golden_labels_f1f2.md`") — an active scoring dependency, not historical narration. |
| `docs/ai/psychotropic_classification.md` | Cited from 3 production source files as the documented reference for the classification logic (`apps/ai-server/src/data/psychotropic_classification.py:15`, `adapters/hira_drug_efficacy.py:24`) — code points at this doc by path in a comment. |
| `docs/ai/f3_quick_dev_plan.md`, `docs/ai/f4_quick_dev_plan.md`, `docs/ai/f5_quick_dev_plan.md`, `docs/ai/f4_checklist.md`, `docs/ai/f5_checklist.md` | All 5 are cited as "설계 원문" (design source of record) by `PRD_task1_v2.md` and/or `checklist_task1.md` for F3/F4/F5 sections still in the living checklist — explicitly named LIVING in the brief. |
| `docs/ai/f5_charting_research.md` | Cited by `f5_checklist.md`/`f5_quick_dev_plan.md` for **unresolved open items** (`T1-F5-DOC-003`/`DOC-004`, `[ ]` unchecked — Media resource research, 의료법 시행규칙 제14조, LOINC language policy) — this is forward-pointing open-work backing, not closed-mission narration. |
| `docs/ai/agent_collaboration_f1f5.md` | Explicit companion doc of `f1f5_total_validation_plan.md` (still-active Stage plan) — "per-feature agent composition this program exercises." |
| `docs/ai/development_report.md`, `docs/ai/checklist_task1.md`, `docs/ai/PRD_task1_v2.md`, `docs/ai/item_bank_v1_sources.md`, `docs/ai/workflow_checklist_f1f2.md`, `docs/ai/workflow_discussion_f1f2.md`, `docs/ai/workflow_results_f1f2.md`, `docs/ai/f1f5_total_validation_plan.md`, `docs/ai/f1f5_total_validation_report.md`, `docs/ai/validation_plan_f1f2_continuous.md` | User-designated LIVING (PRD/checklists/final reports/plan docs) — the canonical monitoring surface this whole scan cross-references against. |

---

## 3. JSON/artifacts — `docs/ai/simulation_results/`

Filename-timestamp bucketing against `EXP-025`'s recorded wall-clock (`result.md` EXP-025:
15:46:25→17:22:14 KST, **2026-07-15**). Files stamped `_20260715_*` are the current `EXP-025`
artifact set (kept); files stamped `_20260711_*`/`_20260712_*`/`_20260713_*` predate `EXP-025` and
belong to the closed W0-W8 / BUG-030 fix-cycle / F3-F4-F5-quick-dev missions, whose conclusions
are already condensed in `version.md`, `docs/ai/workflow_results_f1f2.md`, and
`docs/ai/development_report.md`.

| Subtree | Total files | Pre-EXP-025 (candidate) | EXP-025 current (keep) |
|:--|--:|--:|--:|
| `VP-001/` | 224 | 175 | 49 |
| `VP-002/` | 91 | 52 | 39 |
| `VP-003/` | 205 | 158 | 47 |
| `VP-004/` | 105 | 66 | 39 |
| `VP-010/` | 61 | 22 | 39 |
| `VP-011/` | 55 | 16 | 39 |
| `VP-012/` | 80 | 41 | 39 |
| `safety_matrix/` | 94 | 94 (all pre-EXP-025 — no `_20260715_*` file exists in this subtree) | 0 |
| **Total** | **915** | **624** | **291** |

**Destination:** `_archive/simulation_results/` — the existing populated wave-1 archive already
uses this exact convention (per-VP subtrees + `safety_matrix/`), so this would be a wave-2 sweep
extending the same manifest, not a new taxonomy.

**Caveat (explicit, per brief item 3):** these pre-`EXP-025` artifacts are also preserved in git
history (the `docs/ai/simulation_results/` tree is git-tracked) and, for the wave-1-eligible
subset, already exist under `_archive/simulation_results/` from the 2026-07-11 sweep — this
2026-07-15 wave covers the *new* accumulation since that sweep (W2 dialogue-v3 regression through
the BUG-030/036/037 fix cycles and the F3/F4/F5 quick-dev missions' live artifacts), not a
re-sweep of already-archived content. `docs/ai/simulation_results/README.md` was not modified or
flagged — it is the directory's own usage note, keep in place regardless of sweep outcome.

**mp3/PDF/tts_scripts fixture check:** none found at top level of any VP dir this scan (wave-1
already relocated all 32 input-asset fixtures to `apps/ai-server/tests/fixtures/` per
`_archive/README.md`'s manifest) — confirms brief item 4's "old root-level *.mp3 등 자산은 이동
대상 아님" is moot here; there are none left to move.

---

## 4. Repo-root / docs-root / apps-root strays (checked, none found)

- **Repo root:** no stray `.py` files at repo root; no `*backup*`-named directory outside the
  existing `_archive/` (which itself contains `legacy_code/ai-server_backup/`,
  `reports/docs_ai_backups/`, `simulation_results/backups/` — already-archived, not a new find).
- **`apps/ai-server/` root:** only `.env`, `.env.example`, `.python-version`, `Dockerfile`,
  `README.md`, `pyproject.toml`, `uv.lock` — all live project-config files, no stray scripts.
- **`docs/` root (non-`ai/`):** `AI_master_plan.md`, `PROGRESS.md`, `dev-environment.md`,
  `prd/PRD_neuro-sync.md`, `todo_plan/PLAN_neuro-sync.md` — **out of this scan's scope** (these
  are whole-project/3-person-team onboarding docs, not F1-F5 development-history artifacts) and
  in any case demonstrably live: `PROGRESS.md` was last modified today (2026-07-15) and links the
  other four by relative path. Not evaluated as candidates; flagging only for completeness per
  brief item 4's "docs 루트" instruction.
- **`tools/`:** `seed_demo.py` — a demo-seed script, not F1-F5 development history; out of scope,
  not evaluated as a candidate.

---

## 5. Top uncertainties (need user or orchestrator call before moving)

1. **BUG-036/037 "live 검증" is a standing carried-forward open item** (`.claude/state/handoff.json`:
   `"BUG-031..034, BUG-036/037 live 검증"` in the carry-forward list) — the design/rubric/review
   docs for the 3-fix cycle (`fix_design_exhaustion_bug037.md`, `rubric_bug030_acceptance.md`,
   `cv_scratch_cvr013.md`, `critic_scratch_rev034_fixcycle.md`) are code-complete/offline-gated but
   **not yet live-verified**. If that live verification runs as part of Stage E/F, it will likely
   need `rubric_bug030_acceptance.md` (the scoring instrument) and `fix_design_exhaustion_bug037.md`
   (the mechanism reference) at minimum. Recommend holding these 4 files out of the first archive
   batch until the orchestrator confirms BUG-036/037's live-verification status, rather than
   archiving now and risking a mid-verification retrieval block.
2. **`docs/ai/audit_c_korean_research.md`/`who5_sourcing_retry2.md` look like the same
   "mid-mission research note" shape as the archived cluster but are structurally load-bearing**
   for `item_bank_v1_sources.md` (a user-designated LIVING doc) — flagged DO NOT MOVE above, but
   worth the user's explicit sign-off since they superficially match the brief's own "older
   research notes" pattern.
3. **Destination-folder granularity**: `_archive/`'s existing taxonomy (`plans/`, `reports/`,
   `legacy_code/`) doesn't have an `analysis_scripts/` subfolder yet — this scan proposes creating
   one under `legacy_code/` (closest semantic fit: standalone Python, not doc). Orchestrator/user
   may prefer a flat `_archive/analysis/` sibling instead, matching `simulation_results/`'s
   top-level status. Not decided here — scan only.
4. **`safety_matrix/`'s full 94-file subtree has zero `EXP-025`-era files** — confirmed no F1-F5
   total-validation-program artifact touches this subtree yet, so archiving all 94 is
   unambiguous, but worth flagging since it's a 100% (not partial) sweep of that one subtree.
