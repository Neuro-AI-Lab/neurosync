---
name: pr-stack-state-drifts
description: The user-brief/handoff-stated git PR-stack and Master state can be stale; filemanager must verify actual PR/branch/Master state via REST before finalizing PR placement
metadata:
  type: project
---

The F2 work ships as a linear stacked-PR chain (feat/f2-rag-remediation → ... → feat/f2-docs-sync). The stated stack state drifts between sessions.

**Why:** In PLAN-2026-W28-K (2026-07-09) the user brief asserted "Master = b735a1f (PR #41 merged), #44–#48 all open, unmerged." filemanager's authoritative REST reads found reality had moved further: Master was actually at 6a333893 (only PR #44 merged, RAG-HTTP deletion), and #45–#48 had merged **branch-to-branch** (not into Master). handoff.json was also stale (still said Master=9d857fe, #41 unmerged). Branch-to-branch stack merges and out-of-band Master merges happen between sessions.

**How to apply:** Trust the user brief for *intent* (which branch to stack on, e.g. "branch off feat/f2-docs-sync"), but have filemanager verify the *actual* branch/PR/Master state via `GET /repos/Neuro-AI-Lab/neurosync/pulls/<n>` and `git/refs` before finalizing PR placement — and surface any discrepancy in the report rather than absorbing it silently. A branch that still exists (even if its PR merged branch-to-branch) is a valid stacking base. Landing the whole stack into Master is a separate PR that may not exist yet. See [[root-docs-gitignored]] for the related fact that the 4 root docs + .claude/ never appear in commits/PRs.
