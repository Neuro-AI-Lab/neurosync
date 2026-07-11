# `_archive/` — pre-validation-program development history

**Status:** scaffold only (Phase 1, W0). No content has been moved here yet.

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
| `simulation_results/` | Legacy `docs/ai/simulation_results/` artifacts (268+ files across VP-001..004, safety_matrix, retro_audit_20260703, etc.) — the 32 input-asset fixtures (22 mp3 + 4 PDF + 6 `tts_scripts/`) are explicitly excluded from this move (they relocate instead to `apps/ai-server/tests/fixtures/` per answer #8a) |
| `legacy_code/` | Old/unused source code superseded by the current F1/F2 implementation |
| `agent_memory/` | Quarantined `.claude/agent-memory/*` (Phase 2 only — memoryless validation specialists) |
| `root_docs_snapshot/` | Pre-reset snapshot of `result.md`/`discussion.md`/`error.md` taken at the `VER-00X` version transition |

Each subdirectory currently holds only a `.gitkeep` placeholder. Content moves are **out of
scope for this build step** and land in W1 (simulation-results archive, prior plans/reports)
and at the `ADR-023` Phase 2 boundary (agent-memory quarantine, root-docs snapshot),
per `docs/ai/workflow_checklist_f1f2.md`.

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
