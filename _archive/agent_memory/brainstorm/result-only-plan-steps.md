---
name: result-only-plan-steps
description: When a brief explicitly says "no HYP entry, deliver in RESULT block", skip discussion.md writes for that mission — check the governing PLAN's step table first.
metadata:
  type: feedback
---

Some brainstorm briefs are DESIGN-OPTIONS contributions to a plan-only orchestrator mission, not
hypothesis-formulation missions. Example: PLAN-2026-W28-O step 2d (2026-07-10) — orchestrator's own
mission table marked brainstorm's row "Options with tradeoffs, RESULT-only", alongside data (2c) and
experiment-tracker (3) also marked RESULT-only. In these cases the orchestrator folds every
specialist's RESULT into its own step-4 synthesis (a single folded plan entry) rather than each
specialist writing standalone discussion.md entries — writing HYP/RES anyway would create duplicate,
premature IDs before critic's own pre-registered adjudication rule (e.g. REV-022) exists.

**Why:** the orchestrator explicitly wants condensed design options it can fold into ONE plan entry
for user approval, not N scattered specialist entries the user has to cross-reference.

**How to apply:** before defaulting to "brainstorm always writes discussion.md", check (a) the
brief's own explicit doc-write instruction line, and (b) the governing PLAN entry's step table (found
at the tail of discussion.md) for a "RESULT-only" marker on your row. If both say result-only, do not
touch discussion.md — put everything in the final RESULT block, condensed but complete (findings +
tradeoffs), since the orchestrator's synthesis step is the only place this content will otherwise
persist until a later HYP-filing mission.
