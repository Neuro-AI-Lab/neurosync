---
name: git-state-volatility
description: User merges PRs mid-session (re-verify remote state per dispatch); root docs gitignored; /tmp worktree pipeline for integration missions; DR-append PR collisions; PROMPTS_BASE_DIR silent-fallback trap (BUG-021)
metadata:
  type: project
---

Two git facts that changed orchestration decisions on 2026-07-10 (PLAN-2026-W28-L):

1. The user (GitHub: DrNeuroAI) actively merges/opens PRs while a session is running — PR #49 was
   merged and PR #50 opened by the user within minutes, mid-session, making the conductor brief's
   git-state section stale before the first filemanager dispatch landed. Recurred 2026-07-10
   (PLAN-2026-W28-M): ALL four target PRs (#48–#51) were merged before the first dispatch landed;
   the "verify, then adapt + explicit fallback" brief format made filemanager halt cleanly and
   return facts instead of executing a stale plan — the pattern works, keep it.
   **Why:** the user works in parallel with the agent team on the same repo.
   **How to apply:** every filemanager brief that creates/uses branches or PRs must start with
   `git fetch origin` + fresh remote verification, and briefs should state expected state as
   "verify, then adapt" (with an explicit fallback rule) rather than as fact. Never assume a PR
   from an earlier STATE entry is still open/unmerged. Useful trick from W28-M: new branches
   pointing at EXISTING commits (git branch <name> <sha> + push refspec, no checkout) give clean
   per-issue PR diffs with zero rewrite risk when content is stranded on a merged lineage.

2. The four root docs (result.md, discussion.md, error.md, version.md) and CLAUDE.md are
   **gitignored** in this repo (.gitignore lines ~83-87) — they live only in the working tree.
   **Why:** project convention; doc history is carried by version.md content, not git.
   **How to apply:** branch switches never endanger root-doc edits (no stash gymnastics needed);
   conversely, root docs can never be committed/pushed — "commit the docs" briefs must target
   `docs/ai/*` files only, and doc durability depends on the single working tree (be careful with
   worktree-isolated agents that expect root docs present).

3. Lessons from PLAN-2026-W28-N execution (2026-07-10, PR #38 integration → PR #55):
   - **Persistent /tmp worktree pipeline works well:** one worktree (`/tmp/wt-...`) created at W1
     and reused across developer→qa→experiment-tracker waves keeps the user's tree fully untouched
     despite their mid-session branch switching. Copy `apps/ai-server/.env` into it (gitignored,
     needed by uv-run app/tests); doc entries still go to MAIN-tree root docs (absolute paths).
   - **safety_matrix writes artifacts into `docs/ai/simulation_results/` of the CWD tree** —
     untracked noise in a worktree; ensure the tracker duplicates artifacts to main-tree
     `experiments/EXP-NNN/` before anyone removes the worktree (removal then needs `--force`).
   - **Stacked open PRs that each append to `docs/ai/development_report.md`'s tail collide:**
     whichever merges second gets an append-append conflict. Either accept + disclose (trivial:
     keep both DR entries in ID order) or refresh the second branch after the first merges.
   - Env defect to watch: explicit-but-wrong relative `PROMPTS_BASE_DIR` in `.env` silently puts
     ALL agents on generic fallback prompts (BUG-021, critical, pre-exists on Master) — corrupted
     EXP-013's first run mimicking a safety regression. Until fixed, any experiment brief should
     tell the tracker to verify prompt loading has zero "prompt not found" warnings.

4. Sandbox quirk (2026-07-10, PLAN-2026-W28-O, PR #56 amendment): the rename syscall is blocked in
   agent sandboxes even with dangerouslyDisableSandbox — `mv`/`git mv` report ENOENT while
   `stat`/`cp`/`rm` work on the same path.
   **How to apply:** filemanager briefs doing file moves should mention the workaround:
   `cp` + `rm` + `git add -A` (git re-detects clean R100 renames; verify with sha256).

5. Mid-mission binding directives from this user (2026-07-10, W28-O) to honor by default in future
   plans: (a) gaps in user-requested features (missing API keys, fixtures, clinical mappings)
   become explicit USER QUESTIONS — never design around them unilaterally; (b) production code
   stays harness-agnostic — validation lives in an external protocol layer, product design
   precedes validation design (ISS-029 extended); (c) three separate review lenses: qa
   (implementation), clinical-validator (CVR entries, clinical adequacy — agent added 2026-07-10),
   critic (research validity) — verdicts side-by-side, blocking CVR gates like a blocking REV.

6. Blind-validation protocol + surviving-doc transcription rule (2026-07-10, W28-P / ADR-023):
   the F1–F2 validation program runs its W7/W8 execution BLIND — `_archive/` + `archive_gate.py`
   PreToolUse deny + VER version transition + agent-memory quarantine, ARMED at the W6→W7 boundary
   (two-phase per ADR-023; implementation waves keep context). Validators read ONLY the blindness
   manifest: validation plan doc, 2 workflow monitoring docs, raw data, production code, api specs.
   **Why:** user directive — validators must act as external pre-deployment experts ("이제까지
   개발/검증 내용은 모두 없다고 생각하고").
   **How to apply:** (a) anything a blind wave needs MUST be transcribed into a surviving doc
   before Phase 2 — discussion.md carry-forward does NOT rescue it (off the whitelist); a W6-end
   transcription-verification checklist (orchestrator+critic) gates arming (REV-023 Issue 5,
   blocking-scoped). (b) THIS memory directory is itself quarantined at Phase 2 — do not rely on
   it during blind waves. (c) Mid-mission user directives arriving while background agents run:
   record immediately as PLAN status blocks, reconcile agent RESULTs at fold time (worked twice).
