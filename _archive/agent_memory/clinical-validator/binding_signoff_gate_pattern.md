---
name: binding-signoff-gate-pattern
description: A third CVR entry mode — binding parameter finalization/gate ruling (e.g. AUD ontology KO-name sign-off at CVR-006), distinct from artifact review and content authoring
metadata:
  type: project
---

At CVR-006 (2026-07-11), the brief asked clinical-validator not to review an already-shipped
artifact (mode 1, e.g. CVR-001/002/003/004) nor to author new pre-registered instrument content
(mode 2, CVR-005, see [[content-authoring-cvr-pattern]]), but to make a **binding
parameter-finalization ruling** that a plan doc had explicitly deferred to this role: the DRAFT
Korean name of the AUD ontology entry (`ontology.py:346`, `# DRAFT pending CVR sign-off`) plus a
go/no-go on the DB load itself (plan §9: "Clinical-validator review of entry content is REQUIRED
before `ontology.py` ships").

**Pattern:** the verdict vocabulary for this mode differs from the standard
adequate/adequate-with-findings/inadequate scale — the brief specified sign-off /
sign-off-with-conditions / blocking, and the entry must state clearly which named artifact/
parameter is cleared (here: the `rag.disease` 26→27 DB load). Keep the mandated header fields
(Target/Verdict/Linked) and the mandated findings-table/weak-point-register/recommendations
subsections, but insert a `### Rulings` block between the header and the findings table that
directly answers each of the brief's numbered gate questions in order, each explicitly labeled
CONFIRMED/STATED/other — this lets `developer` grep the entry for exactly what to apply without
re-reading the full clinical rationale. Findings-table rows in this mode capture *residual clinical
thinness in the now-finalized content*, not defects that block the ruling — distinguish "this is a
condition of sign-off" from "this is worth watching later" explicitly (CVR-006 had zero of the
former, three of the latter minor findings; verdict was plain `sign-off`, not
`sign-off-with-conditions`).

**Verification technique used, worth reusing:** for a "does the description avoid
reverse-authorship phrasing" ask, do a direct side-by-side of the code's description string against
the cited persona file's own quoted patient-voice lines (not just checking the code comment's
self-report of compliance) — the code comment claiming compliance is not itself evidence; only
reading both source texts independently is.

**Naming-convention find worth reusing:** when ruling on a DRAFT proper-noun/label string, check
sibling entries in the same file for an existing disambiguation convention before treating the
draft as novel — CVR-006 found `alcohol-intoxication`'s pre-existing "알코올 중독(급성)" parenthetical
pattern, which meant the AUD draft's "(의존)" suffix wasn't an ad hoc choice but consistent reuse of
an established in-ontology convention, plus it happened to double as the required scope-disclosure
CVR-002 Finding 6 had asked for. Naming rulings are stronger when grounded in an existing precedent
than in first-principles translation alone.

See [[repo-artifact-map]] for the AUD entry's final field values as ruled at CVR-006 and
[[content-authoring-cvr-pattern]] for the sibling mode-2 pattern.
