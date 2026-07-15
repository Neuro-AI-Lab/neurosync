---
name: root-docs-gitignored
description: The four root orchestration docs + CLAUDE.md/.claude are gitignored repo-wide — never expect them in commits/PRs
metadata:
  type: project
---

The four root docs (`result.md`, `discussion.md`, `error.md`, `version.md`) plus `CLAUDE.md`, `.claude/`, `.mcp.json` are covered by `.gitignore` (lines ~84-87) and have **never existed in this repo's git history** — confirmed by filemanager during PLAN-2026-W28-F (2026-07-09) via `git check-ignore -v` + `git show HEAD:<path>`. This is intentional, repo-wide, predating any recent mission: these are **local orchestration state**, not version-controlled product.

**Why:** the git-tracked deliverables are actual project artifacts under `docs/ai/`, `apps/ai-server/`, code, etc. The entry-based meta-docs (PLAN/ADR/STATE/EXP/BUG/VAL/DR) live on disk for coordination but are not shipped.

**How to apply:** When briefing filemanager to commit a mission, do NOT list `discussion.md`/`error.md`/`result.md`/`version.md` in the commit set and do NOT expect a BUG/PLAN/STATE entry to appear in a PR diff — they are correct on disk but untracked by design. Committable doc deliverables are things like `docs/ai/**` (specs, DR reports, checklist, PRD). If a mission's record (e.g. a filed BUG) needs to be visible in the PR, put it in the PR *body* text (filemanager already does this), not by expecting the gitignored file to be committed. Never instruct a `git add -f` on these without an explicit user decision to change the tracking policy.
