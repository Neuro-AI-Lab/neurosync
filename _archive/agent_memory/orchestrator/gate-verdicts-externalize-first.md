---
name: gate-verdicts-externalize-first
description: Append gate verdicts (qa/critic/CVR) to discussion.md IMMEDIATELY on receipt, BEFORE dispatching any stage that depends on them — specialists verify the doc, not the orchestrator's context
metadata:
  type: feedback
---

Gate verdicts must be externalized to discussion.md the moment they arrive, before the dependent
dispatch goes out.

**Why:** During PLAN-2026-W28-Q (2026-07-11) this omission bit twice in one wave: (1) REV-024
filed a blocking-scoped finding that the qa W4 gate record was missing from discussion.md (the
verdict lived only in the orchestrator's context); (2) the experiment-tracker's first EXP-015
certification dispatch HALTED because it grepped discussion.md for a gate record naming the fix
commit and found none — the qa micro-gate had passed synchronously minutes earlier but was not yet
appended. The halt was correct specialist behavior (verify, don't trust the handoff); the cost was
a full dispatch round-trip.

**How to apply:** Treat every received gate RESULT (qa GATE:PASS/FAIL, critic verdict, CVR verdict)
as a write-before-dispatch obligation: append the status block naming the exact commit sha and
verdict to discussion.md in the same turn the RESULT arrives, then dispatch the dependent stage.
Batching gate records "for the next fold" is the anti-pattern — downstream specialists (correctly)
launch only on recorded gates. Related: [[git-state-volatility]].

THIRD occurrence (same session, W28-Q W6-end): the qa symlink-audit PASS was received but deferred
"to the W6-end batched append" — the critic's independent W6-end check ran first, found no record,
and BLOCKED arming on it. Batching even within the same phase is the same bug: any verdict another
agent might check for must be on disk before that agent can plausibly run. Record on receipt,
zero exceptions — including "small" audits and verdicts whose dependent step seems far away.
