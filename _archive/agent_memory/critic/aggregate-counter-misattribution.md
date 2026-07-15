---
name: aggregate-counter-misattribution
description: Tracker entries can attribute a nearby aggregate counter (e.g. "Errors: N") to a disclosed defect without tracing which code path actually populates it — always check.
metadata:
  type: project
---

2026-07-11 (REV-025, EXP-015 Gate-0 review): experiment-tracker's EXP-015 "RESUMED" status
update disclosed VP-003's F1 run hit 2 (actually 3, undercounted) `InputNormalizerAgent`
parse-failure WARNINGs (BUG-020, already-open), then separately noted "F1's own summary line
reports `Errors: 2` for VP-003 ... consistent with this" — implying the F1 pipeline's
`Errors: N` counter was populated by those InputNormalizer failures. Independently tracing
`result.errors.append(...)` call sites in `f1.py` showed `InputNormalizerAgent`'s exception
path never touches `result.errors` at all (it's caught internally and only logged as a
WARNING); the actual and only writer this run was the dialogue-repetition guard
(`f1.py:1658`, `"Agent repetition at turn {turn} (count={repeat_count})"`), which fired twice
and terminated the F1 session early at turn 9 — a session-ending anomaly unrelated to, and
far more consequential than, the disclosed InputNormalizer defect, and one this project has
prior open/fixed BUGs for (BUG-004, BUG-025/SM-06) under a different test surface (scripted
matrix vs. live adaptive-patient chain).

**Why:** A plausible-sounding causal narrative ("here's a known defect" + "here's an error
count nearby") reads as consistent even when the two facts are unrelated. The juxtaposition in
the tracker's own prose was enough to make the wrong attribution look verified without anyone
having traced the counter's actual population site.

**How to apply:** Whenever a tracker/developer/qa entry cites an aggregate counter (an "Errors:
N", "warnings: N", pass/fail tally, etc.) and attributes it — explicitly or by proximity — to a
specific named defect, grep the counter's actual write/append site in the source before
accepting the attribution. This is cheap (one grep) and has twice now (see also
[recurring-prompt-only-enforcement-gap](recurring_prompt_only_enforcement_gap.md) for a related
"don't take the summary table on faith" pattern) surfaced a second, undisclosed, more severe
anomaly hiding behind a disclosed, already-triaged one.
