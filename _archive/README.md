# `_archive/` — pre-validation-program development history

**Status:** W1 wave 1 complete (2026-07-11) — `simulation_results/` populated. Stage F wave 2
complete (2026-07-15, `CLEAN-2026-07-15`) — `plans/`, `reports/`, `legacy_code/` populated;
`simulation_results/` extended with the pre-`EXP-025` accumulation. `agent_memory/`,
`root_docs_snapshot/` remain scaffold-only (still deferred, per `ADR-023` Phase 2 timing).

## What this is

This directory is the landing zone for all F1/F2 development history that predates the
F1–F2 continuous-scenario validation program (`PLAN-2026-W28-Q`) — prior plans, reports,
simulation results, superseded code, agent memory, and root-doc snapshots. It exists to
support **blind validation**: at the `ADR-023` Phase 2 boundary (the W6→W7 wave transition),
validating agents must operate as an external pre-deployment expert would, with no access
to how F1/F2 were built or previously tested (`docs/ai/validation_plan_f1f2_continuous.md`
§7, "Blind-validation protocol").

## Subdirectories

| Path | Intended content |
|:--|:--|
| `plans/` | Superseded planning/design/proposal docs — **populated 2026-07-15 (wave 2)**. Pre-existing: `PRD_task1.md`, `prompt_redesign_v3.md`, `vp_validation_scenarios.md`. Added wave 2: see manifest below. |
| `reports/` | Prior review-scratch / PR-description / DR-style development reports — **populated 2026-07-15 (wave 2)**. Pre-existing: `docs_ai_backups/`, `papers_notes/`, `pr_description_f1_stt_ocr.md`, `pr_description_map_api.md`. Added wave 2: see manifest below. |
| `simulation_results/` | **Populated 2026-07-11 (wave 1)**, extended 2026-07-15 (wave 2). Legacy `docs/ai/simulation_results/` artifacts + old `experiments/EXP-*` runs. See manifests below. |
| `legacy_code/` | Old/unused source code + one-off analysis scripts superseded by the current F1/F2 implementation — **populated 2026-07-15 (wave 2)** with `analysis_scripts/` (new subfolder, one-off DATASET/EXP audit scripts); `ai-server_backup/` pre-existing (scaffold from wave 1) |
| `agent_memory/` | Quarantined `.claude/agent-memory/*` (Phase 2 only — memoryless validation specialists) — scaffold only |
| `root_docs_snapshot/` | Pre-reset snapshot of `result.md`/`discussion.md`/`error.md` taken at the `VER-00X` version transition — populated at each version transition (see `ver003/` and the 2026-07-11 dated files) |

`agent_memory/` remains scaffold-only (`.gitkeep` placeholder) — still deferred to the
`ADR-023` Phase 2 boundary (agent-memory quarantine is a blind-validation-arming action, not a
routine cleanup). `plans/`, `reports/`, `legacy_code/`, `simulation_results/`,
`root_docs_snapshot/` are now populated across wave 1 (2026-07-11) and wave 2 (2026-07-15,
Stage F of the F1-F5 total-validation program, `CLEAN-2026-07-15`).

## Manifest — `simulation_results/` (wave 1, 2026-07-11)

**Source:** `docs/ai/simulation_results/` (git-tracked content, via git-detected renames)
and `experiments/EXP-*` (gitignored, plain filesystem move).
**Destination:** `_archive/simulation_results/`.
**Authority:** `PLAN-2026-W28-Q` W1, user answer #8a (fixture relocation) + directive 4
(archive construction); `ADR-023` Phase 1 (hook stays disarmed).

The 32 input-asset fixtures (22 mp3 + 4 OCR PDF + 6 `tts_scripts/` files) were explicitly
excluded from this move and relocated instead to `apps/ai-server/tests/fixtures/`
(`audio/<VP>/`, `ocr/<VP>/`, `tts_scripts/`) — see that directory and the developer-facing
reference-update list in the corresponding filemanager RESULT for code/test files that
still point at the old fixture paths (not patched here; out of scope for filemanager).

| Subtree | Files moved | Notes |
|:--|--:|:--|
| `VP-001/` | 81 | Run history (checklists, conversations, reports, grounding audits, domain-inference outputs); fixture mp3/PDF excluded |
| `VP-002/` | 53 | Same shape as VP-001 |
| `VP-003/` | 67 | Same shape; includes files referenced by `tests/repro/test_bug_014.py`'s artifact-presence skipif (see suite results) |
| `VP-004/` | 62 | Same shape as VP-001 |
| `backups/` | 48 | Gitignored subtree (`.gitignore` line 91); 12 files were nonetheless git-tracked (`invalidated_20260703/`) pre-move and moved as git-detected renames, the remaining 36 as plain untracked moves |
| `safety_matrix/` | 56 | SM-01..SM-08b report/result pairs |
| `retro_audit_20260703/` | 8 | Retro grounding audits |
| `nearby_smoke/` | 6 | Map/nearby-hospital smoke outputs |
| `tts_scripts/` (leftover) | 0 | All 6 files were fixtures and moved to `apps/ai-server/tests/fixtures/tts_scripts/`; the emptied directory was removed |
| top-level loose files | 3 | `EXP-012_f1f2_consolidated_analysis.md`, `EXP-012_slot_summary.md`, `map_api_v2_verification.md` |
| `experiments/EXP-002`..`EXP-013` | 497 | Old experiment-tracker run dirs (12 dirs; per-dir counts: EXP-002=69, EXP-003=26, EXP-004=27, EXP-005=51, EXP-006=59, EXP-007=15, EXP-008=17, EXP-009=30, EXP-010=84, EXP-011=30, EXP-012=32, EXP-013=57) |
| **Total** | **881** | |

`docs/ai/simulation_results/` and `experiments/` root directories remain present (empty of
legacy content) as the landing zone for new F1/F2 validation-battery artifacts and new
experiment-tracker runs respectively — each carries a short README/is otherwise empty.

## Manifest — Stage F wave 2 (2026-07-15, `CLEAN-2026-07-15`)

**Source:** `analysis/`, `docs/ai/*.md`, `docs/ai/simulation_results/` (all git-tracked, moved
via `git mv`, git-detected renames).
**Destination:** `_archive/legacy_code/analysis_scripts/`, `_archive/plans/`,
`_archive/reports/`, `_archive/simulation_results/<VP>/` and `_archive/simulation_results/safety_matrix/`.
**Authority:** Stage F of the F1-F5 total-validation program
(`docs/ai/f1f5_total_validation_plan.md`), user directive (archive old md/json/py files
unnecessary to F1-F5 functional operation), scan-and-approve two-step: candidate list at
`docs/ai/stage_f_archive_candidates.md`, user-approved with 4 md files (BUG-036/037 3-fix-cycle
scoring reference, live-verification still carried-forward open in `.claude/state/handoff.json`)
and 2 md files (`audit_c_korean_research.md`/`who5_sourcing_retry2.md`, load-bearing for the
living `item_bank_v1_sources.md`) explicitly held back from this wave.

**Classification method:** py — import-graph liveness check (nothing imports these 4 outside
their own already-archived one-off purpose); md — cross-reference against the current living-doc
set (`PRD_task1_v2.md`, `checklist_task1.md`, `workflow_*_f1f2.md`, `item_bank_v1_sources.md`,
`discussion.md`/`result.md`/`error.md`/`version.md`, `.claude/state/handoff.json`), narrative
pointer citation (safe) vs. structural dependency citation (held); json — filename-timestamp
bucketing against `EXP-025`'s logged wall-clock window (`result.md` EXP-025, 2026-07-15
15:46-17:22 KST) — files stamped `_20260715_*` are the current battery, kept in place; earlier
stamps predate `EXP-025` and are this wave's json/artifact candidates.

| Subtree | Files moved | Notes |
|:--|--:|:--|
| `legacy_code/analysis_scripts/` (new) | 4 | `aud_ontology_load_verification.py`, `canary_zero_hit_verification.py`, `rag_corpus_leakage_audit.py` (DATASET-005/006 one-off W6/W7A re-verification scripts, findings condensed into `version.md`'s `DATASET-003-ext`/`DATASET-004-ext`/`DATASET-006`), `w7b_golden_scoring.py` (W7b blind-scorer worksheet, headline MET-3 17/22-top1/18/22-top3 already reported in `result.md`/`workflow_results_f1f2.md`). `analysis/threshold_n_met8_w1_20260711.py` explicitly excluded — still cited by `apps/ai-server/src/rag_trigger.py:100` and `docs/ai/validation_plan_f1f2_continuous.md:412` |
| `plans/` (added) | 4 | `fix_proposal_bug030.md`, `fix_design_bug030_iter2.md` (BUG-030 iteration-1/2 design, both superseded/landed — `d68c8a2`/`266eea1`), `phr_integration_plan.md` (pre-implementation plan for the now-merged PHR feature, `06faa30`..`f4fd234`), `exp021_factorial_design.md` (`ISS-F2V-028` factorial design, ruled inconclusive, raw data in `experiments/EXP-021/`) |
| `reports/` (added) | 4 | `critic_scratch_rev032_bug030iter2.md`, `critic_scratch_rev033_exp018.md` (BUG-030 review scratch, iteration-1/2, absorbed into `workflow_results_f1f2.md`), `pr_description_phr_and_medication.md`, `pr_description_phr_integration.md` (PR-description docs for the already-merged PHR feature, zero external references from any living index doc) |
| `simulation_results/VP-001/` (extended) | 175 | Pre-`EXP-025` accumulation since wave 1 (2026-07-11 through 2026-07-13): W2 dialogue-v3 regression, BUG-030/035/036/037 fix-cycle artifacts, F3/F4/F5 quick-dev live runs |
| `simulation_results/VP-002/` (extended) | 52 | Same window/shape |
| `simulation_results/VP-003/` (extended) | 158 | Same window/shape |
| `simulation_results/VP-004/` (extended) | 66 | Same window/shape |
| `simulation_results/VP-010/` (new) | 22 | W6 persona-introduction through pre-`EXP-025` runs (VP-010 didn't exist at wave 1) |
| `simulation_results/VP-011/` (new) | 16 | Same, W6 introduction |
| `simulation_results/VP-012/` (new) | 41 | Same, W6 introduction |
| `simulation_results/safety_matrix/` (extended) | 94 | Full subtree — no `EXP-025`-era (`_20260715_*`) file exists in `safety_matrix/`, so this is a complete, not partial, sweep of that subtree; source dir removed after empty |
| **Total** | **624** | |

`docs/ai/simulation_results/` retains exactly the `EXP-025` current artifact set post-move: 49
(VP-001) + 39 (VP-002) + 47 (VP-003) + 39 (VP-004) + 39 (VP-010) + 39 (VP-011) + 39 (VP-012) = 291
files, `README.md` unchanged, `safety_matrix/` directory removed (emptied, no current-battery
content exists in that subtree).

## Access control

Once armed, `.claude/hooks/archive_gate.py` (a `PreToolUse` hook, patterned on
`.claude/hooks/experiment_gate.py`) mechanically denies Read/Grep/Glob/Bash/Edit/Write on
any path under `_archive/**` for every agent. This is a **mechanical** block, not a
behavioral instruction — the point is that validating agents cannot see this directory even
if instructed to, by accident or by a compromised prompt.

**The hook is disarmed by default.** It only enforces once the flag file
`.claude/state/blind_active` exists. That flag is absent as of this scaffold (Phase 1,
`ADR-023`) and must remain absent until the orchestrator/critic jointly confirm the W6-end
transcription-verification checklist (`docs/ai/validation_plan_f1f2_continuous.md` §7,
`REV-023` ruling 2 Issue 5) has passed — arming is a Phase 2, W6→W7-boundary action, not a
W0 action.

## Lifting the block

Access is restored only on the user's explicit instruction — removing
`.claude/state/blind_active` disarms the hook immediately (fail-open on flag absence, same
pattern as the flag's creation).

## Provenance

Built by `filemanager` per `PLAN-2026-W28-Q` (W0), `ADR-023` Phase 1, and
`docs/ai/validation_plan_f1f2_continuous.md` §7 mechanism item 1.
