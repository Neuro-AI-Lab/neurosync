# `_archive/` — pre-validation-program development history

**Status:** W1 wave 1 complete (2026-07-11) — `simulation_results/` populated. `plans/`,
`reports/`, `legacy_code/`, `agent_memory/`, `root_docs_snapshot/` remain scaffold-only
(deferred to W6-end per `PLAN-2026-W28-Q` W0 status (c)).

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
| `plans/` | Superseded planning docs / PLAN entries not needed by validators |
| `reports/` | Prior DR/REPORT-style development reports |
| `simulation_results/` | **Populated 2026-07-11.** Legacy `docs/ai/simulation_results/` artifacts + old `experiments/EXP-*` runs. See manifest below. |
| `legacy_code/` | Old/unused source code superseded by the current F1/F2 implementation — scaffold only, deferred to W6-end |
| `agent_memory/` | Quarantined `.claude/agent-memory/*` (Phase 2 only — memoryless validation specialists) — scaffold only |
| `root_docs_snapshot/` | Pre-reset snapshot of `result.md`/`discussion.md`/`error.md` taken at the `VER-00X` version transition — scaffold only |
| `plans/`, `reports/` | Superseded planning/report docs — scaffold only, deferred to W6-end per `PLAN-2026-W28-Q` W0 status (c) |

`plans/`, `reports/`, `legacy_code/`, `agent_memory/`, `root_docs_snapshot/` currently hold
only a `.gitkeep` placeholder each. `simulation_results/` is populated (this wave). Remaining
content moves land at the `ADR-023` Phase 2 boundary (agent-memory quarantine, root-docs
snapshot) and the W6-end prior-plans/reports/legacy-code sweep, per
`docs/ai/workflow_checklist_f1f2.md`.

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
