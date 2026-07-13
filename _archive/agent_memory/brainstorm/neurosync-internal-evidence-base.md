---
name: neurosync-internal-evidence-base
description: For neurosync F1/F2 engineering-validation-design tasks, ground designs in the project's own EXP/REV/BUG/VAL chain in discussion.md/result.md/error.md — papers/ is thin (one design note) and external lit search is rarely load-bearing here.
metadata:
  type: project
---

As of 2026-07-10, `papers/` holds only `papers/notes/ai-predicted-disease-hpi-isolation-design.md`
(no PDFs tracked — `.gitignore` excludes `papers/` globally per STATE-2026-07-09-C, a known
policy-hygiene gap noted but not yet resolved). This project's actual grounding evidence for F1/F2
pipeline design work lives almost entirely in its own accumulated discussion.md/result.md/error.md
history: EXP-002 through EXP-013 (live-run evidence), REV-004/007/008/009/010/011/012/013/016/017/
018/019/020/021 (critic rulings, many superseding earlier ones — always read the *latest* status
update on a VAL/finding, not just its origin entry), and the BUG-011/VAL-001/VAL-010/BUG-020/BUG-021/
VAL-012 open-defect set (all still open as of 2026-07-10, all directly relevant to F1-side dialogue/
STT/OCR/multi-session design).

**Why:** unlike a typical brainstorm task (external-literature-grounded hypothesis), this project's
core validation-design work is an internal-evidence engineering discipline — the "prior work" that
matters is the project's own audit trail (specific file:line citations, specific artifact SHA256s),
not published papers. A brainstorm session here should read discussion.md's tail (recent PLAN/REV/ADR
entries) and error.md's open BUG/VAL rows before reaching for WebSearch/lit_search.

**How to apply:** for any new F1/F2/continuous-scenario design brief, first `grep`/read the relevant
EXP/REV/BUG/VAL chain (they cross-reference each other via **Linked:** fields — follow them) rather
than starting from a literature search. Reserve lit_search/WebSearch for genuinely external questions
(e.g. clinical-questionnaire validity, FDA CDS-guidance framing — REV-013 §4 already flagged the FDA
analogy in the AI-disease design note as "non-binding structural precedent, not applicable law").
