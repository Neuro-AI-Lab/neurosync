# `_archive/` — pre-validation-program development history

**Status:** W1 wave 1 complete (2026-07-11) — `simulation_results/` populated. Stage F wave 2
complete (2026-07-15, `CLEAN-2026-07-15`) — `plans/`, `reports/`, `legacy_code/` populated;
`simulation_results/` extended with the pre-`EXP-025` accumulation. Wave 3 complete
(2026-07-16, `CLEAN-2026-07-16`) — `legacy_code/devtools/` (new subfolder) +
`reports/stale_test_output/` (new subfolder) populated; one `plans/` addition
(`stage_f_archive_candidates.md`, itself now historical). Wave 4 complete (2026-07-16,
`CLEAN-2026-07-16` wave-4 entry) — 6 more `plans/` + 6 more `reports/` (12 docs, wave-3
citation-keeps-alive rulings overridden per user directive, all citing living surfaces
pointer-rewritten) + `experiments/` (new top-level subfolder, `EXP-014`..`EXP-024`, 544
files). `docs/ai` top-level `.md` count now 15. `agent_memory/`, `root_docs_snapshot/`
remain scaffold-only (still deferred, per `ADR-023` Phase 2 timing).

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
| `plans/` | Superseded planning/design/proposal docs — **populated 2026-07-15 (wave 2)**, extended 2026-07-16 (wave 3: 1 file) and 2026-07-16 (wave 4: 6 files). Pre-existing: `PRD_task1.md`, `prompt_redesign_v3.md`, `vp_validation_scenarios.md`. See manifests below. |
| `reports/` | Prior review-scratch / PR-description / DR-style development reports — **populated 2026-07-15 (wave 2)**, extended 2026-07-16 (wave 3: `stale_test_output/`) and 2026-07-16 (wave 4: 6 files). Pre-existing: `docs_ai_backups/`, `papers_notes/`, `pr_description_f1_stt_ocr.md`, `pr_description_map_api.md`. See manifests below. |
| `simulation_results/` | **Populated 2026-07-11 (wave 1)**, extended 2026-07-15 (wave 2). Legacy `docs/ai/simulation_results/` artifacts + old `experiments/EXP-*` runs. See manifests below. |
| `legacy_code/` | Old/unused source code + one-off analysis scripts superseded by the current F1/F2 implementation — **populated 2026-07-15 (wave 2)** with `analysis_scripts/` (new subfolder, one-off DATASET/EXP audit scripts); `ai-server_backup/` pre-existing (scaffold from wave 1); `devtools/` added wave 3 |
| `experiments/` | Old `experiments/EXP-NNN` run directories superseded by the current battery — **new subfolder, populated 2026-07-16 (wave 4)**: `EXP-014`..`EXP-024` (11 dirs, 544 files); `experiments/` at repo root now retains only `EXP-025`/`026`/`027` |
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

## Manifest — wave 3 (2026-07-16, `CLEAN-2026-07-16`)

**Source:** `apps/ai-server/tests/{smoke_ocr_upstage.py,smoke_stt_skt.py,verify_stt_to_f1.py,
repro/test_bug_024.py,output/*.png}`, `docs/ai/stage_f_archive_candidates.md` (all git-tracked,
moved via `git mv`).
**Destination:** `_archive/legacy_code/devtools/` (new subfolder), `_archive/reports/stale_test_output/`
(new subfolder), `_archive/plans/`.
**Authority:** user directive (WAVE-3 strict archive sweep) — "docs/ai 와 docs/experiments,
apps/ai-server 에서 F1-F5 전체 동작중 사용하지 않는 파일들은 모두 아카이빙 해야한다."
**Criterion:** operational necessity — reachable from the F1-F5 entrypoint import graph, or
exercised by a CI-collected test, or structurally cited (by exact path/section number) from a
currently-open or held living doc.

| Subtree | Moved | Reason |
|:--|--:|:--|
| `legacy_code/devtools/` (new) | 4 | `smoke_ocr_upstage.py`, `smoke_stt_skt.py`, `verify_stt_to_f1.py` — standalone vendor-API manual devtools, 0 pytest collection each (`def test_\|class Test` grep confirms 0/0/0), 0 imports from any kept module, invoked only by hand against live credentials. `tests/repro/test_bug_024.py` moved together with `smoke_stt_skt.py` — its only purpose is a source-level regression check against that file (`_SCRIPT_PATH` read); moving one without the other would break the test. `_SCRIPT_PATH`'s `parents[1]` was corrected to `parents[0]` for the new flat layout (path-only fix, zero logic change). |
| `reports/stale_test_output/` (new) | 6 | `tests/output/{vp002_longterm,vp002_snapshot,vp002_trend,vp004_3visit_trend,vp004_longterm,vp004_trend}.png` — git-tracked debug chart images, last touched 2026-07-06 (pre-`EXP-025`), zero references from any current test or code (current `test_trend_plotter.py`/`test_f4_report.py` write to `tmp_path` fixtures, not this directory). |
| `plans/` (added) | 1 | `stage_f_archive_candidates.md` — wave-2's own scan-candidate list, now a closed historical artifact of a completed sweep; zero references from any living surface post-move (verified). |

**Held back after verification (checked, NOT moved — evidence found of live operational necessity):**

| File | Why held |
|:--|:--|
| `apps/ai-server/src/rag_chat.py` | Brief's own candidate list flagged this as "archive if unreachable/standalone demo," but `docs/dev-environment.md` (never-move, onboarding doc) names it in present tense as one of exactly two direct-DB-access call sites in the current architecture ("`retrieve_domain_chunks`... 와 `src/rag_chat.py`의 `retrieve_grounding()` 호출이 각각 `get_sessionmaker()`로 직접 DB 세션을 연다"); `src/main.py`'s own docstring cites it the same way. Initially moved, then reverted after this check. |
| `docs/ai/f5_charting_research.md` | Brief's candidate list flagged this as absorbed research background, but `docs/ai/f5_checklist.md` (never-move) has 3 currently-**open** (`[ ]`) checklist rows (T1-F5-DEV-014, T1-F5-DOC-003, T1-F5-DOC-004) pointing at specific unresolved sections (§1f, §3b) of this file, and `docs/ai/f5_quick_dev_plan.md` (never-move, structurally cited by section number in live code) traces its own §2.2 design directly to this file's subsections. Initially moved, then reverted after this check. |
| `docs/ai/{f3,f4,f5}_quick_dev_plan.md` | Brief listed these as "completed-mission plan docs" to archive. Verification found dozens of *structural* (not narrative) citations by section number in currently-live production code and tests — `src/f3.py`, `src/f4.py`, `src/f5.py`, `src/services/{f4_report,f5_report,trend_plotter}.py`, `src/schemas/{survey_result,longitudinal,handoff_report}.py`, `src/agents/handoff_generator.py`, `src/continuous_test.py`, `src/f1.py`, `src/f2.py`, and ~10 test files all cite specific `§N` sections as their design spec. Per this project's own wave-2 classification method ("narrative pointer citation safe vs. structural dependency citation held"), these are held. |
| `docs/ai/f1f5_total_validation_plan.md` | Brief suggested archiving with a report pointer-line. `discussion.md`'s currently **open** `REV-002` (critic, status: open) cites this plan's §3/§5/§7 by section as the authoritative pass/fail criteria source it is actively adjudicating against — archiving mid-review would break an open review's evidentiary basis. Held. |
| `experiments/EXP-014` through `EXP-024` (11 dirs) | Brief suggested archiving everything older than EXP-025/026. Verification found `docs/ai/workflow_results_f1f2.md` and `docs/ai/workflow_discussion_f1f2.md` (both never-move, the project's living evidence log) cite exact `experiments/EXP-0NN/runs/...` subpaths for **every one** of EXP-014 through EXP-023 as their evidence trail (several rows still "never merged"/open findings); `.claude/state/handoff.json` additionally cites `experiments/EXP-024/runs/{vp001,vp003}_r{1,2,3}/` as live evidence for the currently-open `VAL-016`. None of EXP-014..024 were moved. |
| `apps/ai-server/src/data/build_efficacy_cache.py` | Zero imports, zero pytest collection — meets the mechanical bar, but it is the live regeneration script for `hira_efficacy_cache.json`, a data file actively consumed by `src/agents/patient_history.py` (kept, operational). Not a one-off analysis script; a reusable maintenance tool for a still-used cache. Flagged for the user rather than moved (uncertain — see filemanager RESULT). |
| `apps/ai-server/scripts/build_korean_fonts.py` | Zero pytest collection and not imported, but `src/services/f5_report.py` cites it by name in three places (docstring + two runtime error messages) as the regeneration procedure for the Korean font assets F5's PDF renderer loads at runtime. Load-bearing operational tooling — kept. |
| `apps/ai-server/src/eval/grounding_audit.py` | Only referenced by its own test file, but that test (`tests/test_grounding_audit.py`) is a real, currently-passing regression suite for a production audit tool (T1-F1-VER-014) tied to a real historical fabrication incident (2026-07-03). Operational QA tooling, not a dead script — kept. |
| `docs/ai/PRD_task1.md`, `docs/ai/vp_validation_scenarios.md`, `docs/ai/prompt_redesign_v3.md` | Brief listed these as candidates; verification found they were already moved to `_archive/plans/` in wave 2 (`CLEAN-2026-07-15`). No action needed — `docs/ai/golden_labels_f1f2.md:17` still cites `docs/ai/PRD_task1.md:474` by path, a **pre-existing dangling reference from wave 2**, not introduced by this wave; out of this wave's scope to fix (flagged for the user/writer). |

**Pointer-fixed (living surfaces, 1 file):** `docs/ai/workflow_discussion_f1f2.md` — 2 historical
(resolved-bug, past-tense) mentions of `tests/smoke_stt_skt.py` / `tests/repro/test_bug_024.py`
annotated with their new `_archive/legacy_code/devtools/` location (comment-text only, zero
narrative-meaning change).

**Not evaluated (out of this wave's named scope):** `docs/experiments` — does not exist as a
directory anywhere in the repo (verified via `find`); user's phrasing likely referred to the
existing `docs/ai/simulation_results/` (in scope, checked, current `EXP-025` set left untouched)
or the repo-root `experiments/` (in scope, checked, see EXP-014..024 held-back entry above).

### Verification (wave 3)

| Check | Result |
|:--|:--|
| `pytest --collect-only -q` | 2117 tests collected, 0 errors (down from 2119 pre-sweep — exactly the 2 tests in the relocated `test_bug_024.py`) |
| `pytest -q` (full suite) | **2115 passed, 2 skipped**, 92.83s |
| `ruff check .` | All checks passed |
| `python -c "import src.main"` | OK |
| Reference grep (every moved-file basename, living surfaces only) | 0 residual hits after the 1-file pointer-fix pass; `rag_chat.py`/`f5_charting_research.md` reverted after their held-back references surfaced |

## Manifest — wave 4 (2026-07-16, `CLEAN-2026-07-16` wave-4 entry)

**Trigger:** user directive (WAVE-4 AGGRESSIVE SWEEP) — "지금 너무나 많은 누적 md file, json file들이
있다. 가장 최근에 F1-F5 구현 및 검증에 사용하지 않은 old version들은 다 archiving 해야한다." **This directive
explicitly overrides the wave-3 citation-keeps-alive rulings**: docs held back in wave 3 for being
cited by a living surface are archived here regardless, with every citation rewritten to the new
archive-path pointer (comment/doc-text only; one path-constant fix, see below, is the sole
exception and is itself zero-logic).

**Source:** `docs/ai/*.md` (12 files, git-tracked, moved via `git mv`), `experiments/EXP-014`..`EXP-024`
(gitignored, plain filesystem `mv`).
**Destination:** `_archive/plans/`, `_archive/reports/`, `_archive/experiments/`.

| Subtree | Moved | Reason |
|:--|--:|:--|
| `plans/` (added, 6) | `f3_quick_dev_plan.md`, `f4_quick_dev_plan.md`, `f5_quick_dev_plan.md` (features shipped, `ADR-031`/`ADR-036`/`ADR-037` all implemented and merged), `validation_plan_f1f2_continuous.md` (superseded by the F1–F5 total-validation program), `f1f5_total_validation_plan.md` (superseded by `f1f5_total_validation_report.md`, stages A-E complete), `fix_design_exhaustion_bug037.md` (Fix 1/2/3 design doc, code-complete — BUG-036/037 live-verification still open but this is the design record, not the verification evidence itself) |
| `reports/` (added, 6) | `f5_charting_research.md` (research absorbed into the shipped F5 renderer), `rubric_bug030_acceptance.md`, `cv_scratch_cvr013.md`, `critic_scratch_rev034_fixcycle.md` (BUG-030/036/037 fix-cycle scoring/review scratch — offline-gated, code-complete), `audit_c_korean_research.md`, `who5_sourcing_retry2.md` (AUDIT-C/WHO-5 sourcing research, content already condensed into the living `item_bank_v1_sources.md`) |
| `experiments/` (added, 11 dirs / 544 files) | `EXP-014`..`EXP-024` — superseded by the `EXP-025`/`026`/`027` post-archive validation battery; `experiments/` now retains exactly `EXP-025`/`026`/`027` |

**Pointer-rewrite pass (67 living files, 164 citation-string substitutions, zero logic changes
except one path-constant):**

| Surface class | Files | Notes |
|:--|--:|:--|
| `apps/ai-server/src/**`, `apps/ai-server/tests/**` (.py) | 50 | Comment/docstring `docs/ai/<file>.md` citations rewritten to `_archive/{plans,reports}/<file>.md`. `tests/test_item_bank.py`'s `_AUDIT_C_RESEARCH_NOTE_PATH` constant (a real `Path(__file__)`-joined runtime read, not a comment — the test byte-verifies `item_bank.py` against this file's content) was separately hand-edited from `"docs"/"ai"/"audit_c_korean_research.md"` to `"_archive"/"reports"/"audit_c_korean_research.md"` — path-only, same pattern as wave-3's `_SCRIPT_PATH` fix, zero logic change, verified by the full suite still passing at 2118+2. |
| `docs/ai/{PRD_task1_v2,checklist_task1,f4_checklist,f5_checklist,f1f5_total_validation_report,item_bank_v1_sources}.md` | 6 | Living index/spec/checklist docs — every citation rewritten. `item_bank_v1_sources.md` alone carried 28 of the 164 substitutions (its AUDIT-C provenance narrative cites `audit_c_korean_research.md` by `§`-section throughout). `f1f5_total_validation_report.md` additionally got a one-line "(plan archived at ...)" pointer per the brief, since `discussion.md` `REV-002` cites the plan's §3/§5/§7 as its adjudication-criteria source. |
| `docs/ai/personas/{VP-010,VP-011,VP-012}*.md` + `_canary_audit/` copies | 6 | Persona-authoring provenance line ("Authored per `validation_plan_f1f2_continuous.md` v1.2 §9") rewritten in both the live persona and its canary-audit snapshot (the latter is itself live-loaded at runtime by `run_injected_session.py --persona`, not a static historical copy). |
| `docs/ai/prompts/dialogue/{v3,v4}.system.md` | 2 | Living prompt-version-history notes, rewritten. |
| `docs/ai/simulation_results/README.md` | 1 | Rewritten. |

**Left as-is (append-only historical logs — one header/pointer note added instead of rewriting
every embedded citation, consistent with the project's existing convention for `EXP-0NN`
path references):** `docs/ai/workflow_results_f1f2.md` (30 citations untouched, 1 new header
note), `docs/ai/workflow_discussion_f1f2.md` (10 untouched, 1 new header note),
`docs/ai/workflow_checklist_f1f2.md` (11 untouched, 1 new header note, not explicitly requested
by the brief but added for consistency/traceability), `docs/ai/development_report.md` (11
untouched, 1 new header note, same reasoning — this doc is self-labeled "append-only" in its own
header), `docs/ai/simulation_results/VP-012/VP-012_20260715_171159_temporal_report.md` (1
untouched — a dated experiment artifact, out of scope).

**KEEP, verified against the brief (not moved, with reason):**

| File | Reason |
|:--|:--|
| `docs/ai/psychotropic_classification.md` | Runtime-referenced — `src/data/psychotropic_classification.py`, `src/schemas/phr.py`, `src/agents/patient_history.py`, `src/adapters/hira_drug_efficacy.py`, `tests/test_phr_reader.py` all cite it structurally, not narratively. |
| `docs/ai/agent_collaboration_f1f5.md`, `docs/ai/orchestration_review_evidence.md` | Produced by and cited within the current (kept) `f1f5_total_validation_plan.md`/`f1f5_total_validation_report.md` pair — living cross-references, not archive candidates. |
| `docs/ai/lexicon_expansion_val010.md` | Current safety-filter provenance, authored this cycle (`REV-003`), used in the most recent validation — passes the "most recent" criterion explicitly. |
| `docs/ai/{golden_labels_f1f2,PRD_task1_v2,checklist_task1,item_bank_v1_sources,development_report,workflow_checklist_f1f2,workflow_discussion_f1f2,workflow_results_f1f2,f4_checklist,f5_checklist,f1f5_total_validation_report}.md` | Living index/spec/checklist/append-only-log surfaces per the brief's KEEP list, re-verified still current. |

**BUG-036/BUG-037 scoring-reference note (brief's error.md instruction — deviation, see below):**
the brief asked for a status line on `error.md`'s BUG-036/BUG-037 entries pointing at the new
archive paths for `rubric_bug030_acceptance.md`/`fix_design_exhaustion_bug037.md`/
`cv_scratch_cvr013.md`/`critic_scratch_rev034_fixcycle.md`. `error.md` (current version) does not
contain BUG-036/BUG-037 entries — they were archived into a prior `version.md` `VER-NNN`
transition; the only live carry-forward pointer is `.claude/state/handoff.json`'s open-items list
("BUG-036/037 live 검증"). **filemanager does not have write authority over `error.md`** (owned by
qa/critic per `CLAUDE.md`) even under this user directive, so no edit was made there — this note
here, plus the `version.md` CLEAN-2026-07-16 wave-4 entry, is the retrievable pointer for whichever
agent (qa/critic) next reopens BUG-036/037 live-verification and needs to append that status line
to `error.md` itself. New location of the 4 scoring-reference docs: `_archive/reports/{rubric_bug030_acceptance,cv_scratch_cvr013,critic_scratch_rev034_fixcycle}.md`,
`_archive/plans/fix_design_exhaustion_bug037.md`.

### Verification (wave 4)

| Check | Result |
|:--|:--|
| `pytest --collect-only -q` | 2120 tests collected, 0 errors (unchanged from pre-sweep — comment/path-only edits, no test added/removed) |
| `pytest -q` (full suite) | **2118 passed, 2 skipped**, 91.21s — identical to the pre-sweep baseline |
| `ruff check src/ tests/` | All checks passed |
| `python -c "import src.main"` | OK |
| Reference grep (every one of the 12 moved-file basenames, across every `.md`/`.py` in the repo) | 0 residual hits outside `_archive/**` (archive-internal, expected) and the 5 explicitly-scoped append-only logs listed above (each now carrying a wave-4 pointer note) |
| `docs/ai` top-level `.md` count | 15 (target ≈15 per the brief's KEEP list, exact match) |

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
