---
name: brainstorm-selfaudit-incomplete
description: brainstorm's own "echo risk found" lists in design docs are not exhaustive — always independently grep the source prompt file for realistic-looking values, and verify quantitative repetition/count claims by grep rather than trusting the doc's stated counts.
metadata:
  type: feedback
---

When reviewing a brainstorm design doc that includes a self-conducted echo-risk audit (e.g.
"P7 예시=오염원" table listing which prompt examples need placeholder-ification), do not treat
that table as exhaustive. In `prompt_redesign_v3.md` (REV-002, 2026-07-07) brainstorm correctly
flagged 4 realistic-value locations in `handoff_generator/v1.system.md` but missed 3 more in the
same file: a per-utterance sentiment table containing a fabricated-looking suicidal-ideation quote
with an evidence ID (§8), a longitudinal-change table with concrete score deltas (§9), and a
registry example using a real hospital name "서울대병원" (§12). All three were found by simply
reading the full source file end-to-end and scanning for "does this look like real patient data",
not by trusting brainstorm's own itemized list.

Separately, brainstorm's quantitative claim "이 문구가 §3·§4·§7·§8 등 8회 이상 반복된다" (used to
justify a ~10% token-budget cut) did not hold up: grep found the literal phrase only 3 times, in
§3/§5/§7, not §3/§4/§7/§8. Any specific count/location claim used to justify a budget target should
be independently grepped before accepting it as the basis for a "how much can we cut" number.

**Why:** DR-001 (the project's own worst incident) was caused by exactly this class of oversight —
a realistic-looking example value in a prompt got echoed into fabricated patient output. A design
doc whose explicit purpose is to prevent DR-001 recurrence is the highest-stakes place for the
critic to do a full independent re-scan of the source files, not just review the subset of examples
the author already flagged.

**How to apply:** For any future prompt-redesign or prompt-content review, read the *entire*
current prompt file(s) being replaced (not just the excerpts quoted in the design doc) and
grep for realistic-looking clinical values (diagnosis codes, drug names+dosages, hospital names,
suicidal-ideation-adjacent quotes, numeric scale scores) independently of the author's own
flagged list. Also grep-verify any specific repetition-count or occurrence-count claim used to
justify a token/line budget target.
