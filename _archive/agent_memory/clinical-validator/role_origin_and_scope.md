---
name: role-origin-and-scope
description: How and why the clinical-validator role was created (PLAN-2026-W28-O, 2026-07-10) and how it fits alongside qa/critic
metadata:
  type: project
---

The `clinical-validator` role was created mid-mission on 2026-07-10 by explicit user directive inside
`PLAN-2026-W28-O` (verbatim, Korean): "시나리오 검증을 하면서 QA 시 실제 임상 보조 기술로서 타당한지
(빈약한 부분 등) 검증 해야 하므로, implementation QA와 sub agent specialist 분리하여 진행하라." — the
user wants implementation correctness (qa) and clinical adequacy of the system as a real
clinical-assistance technology reviewed by a fully separate specialist, never merged.

**Why:** the project (neurosync) is validating an F1 (dialogue/intake) → F2 (RAG domain/disease
inference) pipeline for Korean psychiatric pre-consultation intake against synthetic virtual-patient
personas (DATASET-002/003, VP-001~009). Prior to this directive, only `qa` (implementation) and
`critic` (research/experimental validity — leakage, metrics, certification) reviewed the system;
there was no lens dedicated to "is this actually clinically adequate as an assistive tool," and the
user judged that gap needed a standing, separate role, not a folded-in section of an existing review.

**How to apply:** every scenario-validation wave in this project runs three separate, never-merged
verdicts: qa (code/contract/CI), clinical-validator (dialogue-as-intake, slot sufficiency, risk
under/over-triage, RAG top-5 face-validity, questionnaire-linkage appropriateness), critic (research
validity). A `blocking` CVR finding gates a scenario class like a blocking REV. See
[[cvr-001-plan-review-findings]] for the first review and the severity-calibration judgment call made
there. See [[repo-artifact-map]] for where the clinically relevant code/data actually lives.
