---
name: content-authoring-cvr-pattern
description: How to format a CVR entry when the brief asks clinical-validator to author pre-registered assessment content (rubrics/checklists) rather than review an existing artifact — established at CVR-005
metadata:
  type: project
---

Not every CVR entry reviews an already-authored artifact. At CVR-005 (2026-07-11), the orchestrator
brief asked clinical-validator to *author* six directly-usable assessment instruments (MET-2
L1/L2/L3 rubric, a trajectory-awareness sub-check, an SC-6 confrontation-framing checklist, an SC-5
safety-appropriateness bar, a slot-home pre-declaration, and the VP-010 minimization-probing
metric) as pre-registered content — these were adopted remedies (`docs/ai/
validation_plan_f1f2_continuous.md` §8a) that existed only as one-line title+owner rows, with no
actual rubric text anywhere in the project.

**Pattern used, worth reusing:** keep the mandated CVR header fields (Target/Verdict/Linked) and the
mandated `### Clinical findings` table / `### Weak-point register` / `### Recommendations`
subsections exactly as the agent spec defines them, but insert a new block of numbered subsections
*between* the header and the findings table containing the actual instrument content (rubric
levels, checklist pass/fail criteria, worked Korean examples, scoring-unit/aggregation rules). The
`### Clinical findings` table then records *self-critique of the instruments themselves* (uncalibrated
thresholds, cross-owner scoring dependencies, overclaim risk if a convention is misapplied) rather
than findings about a reviewed artifact — this is legitimate; findings don't have to target someone
else's artifact, they can target the adequacy of clinical-validator's own just-authored content.
**Verdict** in this mode means "the content is adequate to serve as the runnable assessment
instrument," not "the system's behavior is adequate" — same three-value scale
(adequate/adequate-with-findings/inadequate), different referent. State the referent explicitly in
the verdict line so a reader doesn't conflate the two modes.

**Why this matters going forward:** this project has a recurring structural risk — `discussion.md`
does not survive its own blind-validation W6→W7 reset (`ADR-023`), so *any* content authored only in
a discussion.md entry (including this one) needs an explicit transcription instruction to `writer`
naming the exact target location (a plan-doc Appendix, following the precedent of Appendices A-D in
`docs/ai/validation_plan_f1f2_continuous.md`). Always add a named "Transcription requirement" note
near the top of a content-authoring CVR entry stating who (writer), what (verbatim-faithful, item by
item), where (name the target section/Appendix letter), and when (before which named boundary/gate).
Do not assume the standard version-management carry-forward mechanism rescues this — `REV-023`
ruling 2 already established carry-forward does not apply when the destination doc itself is off the
blind-validator whitelist. See [[repo-artifact-map]] for the plan doc's Appendix/§8a structure.
