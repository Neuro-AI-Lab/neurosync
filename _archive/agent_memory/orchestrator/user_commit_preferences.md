---
name: user-commit-preferences
description: Commit-message rules the user has mandated — NO attribution trailers, ever
metadata:
  type: feedback
---

- **NEVER add attribution trailers to commits or PR bodies** — no "Generated with oh-my-agent", no "Co-Authored-By: First Fluke <...>". **Why:** user explicitly complained (2026-07-08); a commit-msg hook now strips them, but they must not be written in the first place. All earlier mission briefs that mandated the trailer are OBSOLETE. **How to apply:** every filemanager commit/PR brief must state "trailer 금지"; if an old brief template is reused, strip the trailer section.
- Commit messages still reference doc IDs (DR-NNN etc.) per CLAUDE.md; that convention is unchanged.
- redis is fully removed from the project (PR #35) — never reintroduce mentions in docs/briefs. (2026-07-08)
