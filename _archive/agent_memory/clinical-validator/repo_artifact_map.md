---
name: repo-artifact-map
description: Where to find the clinically relevant code/data for future clinical-validator reviews (12 slots, RAG ontology, questionnaire scales, VP personas, golden labels)
metadata:
  type: reference
---

Verified paths as of 2026-07-10 (CVR-001). Re-verify before relying on these in a future session —
this project moves fast (multiple PLAN/ADR cycles per day).

- **12 canonical clinical slots:** `apps/ai-server/src/agents/clinical_slot.py:26-39`
  (`ALL_SLOT_KEYS`) — encounter_metadata, chief_complaint, history_of_present_illness,
  past_psychiatric_history, medical_history, personal_social_history, family_history,
  substance_use_history, mental_status_exam, risk_assessment, clinical_assessment, treatment_plan.
  `ESSENTIAL_SLOT_KEYS` (line 41) = chief_complaint, history_of_present_illness, risk_assessment,
  mental_status_exam, clinical_assessment. No dedicated protective-factors or medication-adherence
  slot exists (flagged CVR-001 Finding 9).
- **RAG disease ontology (26 diseases, Ada-derived):** `apps/ai-server/src/rag/ontology.py:171-`
  (`DISEASES` dict, slug → (English, Korean, KCD code, classification, summary)). Only acute
  alcohol-intoxication/alcohol-withdrawal exist under `substance`; no chronic AUD/dependence entry
  (CVR-001 Finding 3). Has `depression-in-childhood-or-adolescence` (pediatric-only) as a distinct
  entry from `depressive-episode` — watch for this surfacing for adult VPs (CVR-001 Finding 2).
- **Supported questionnaire scales:** `apps/ai-server/src/scoring/survey_scorer.py:17`
  (`ScaleName = Literal["PHQ-9","GAD-7","PHQ-4","WHO-5","AUDIT-C"]`) — 5 scales, cannot construct-
  validly cover OCD/PTSD/psychosis/ADHD-classified ontology entries (CVR-001 Finding 7).
- **8-value domain enum:** `docs/ai/PRD_task1.md:474` — anxiety, depression, alcohol, substance,
  trauma, sleep, psychosis, other.
- **VP personas:** `docs/ai/personas/VP-001..004_*.md` (DATASET-003, `discussion.md` ~line 740) —
  hand-authored, 2x2 초진/재진 x 경증/중증 matrix, no minimizing-non-crisis or somatic-presenting
  archetype among them (CVR-001 Finding 1). VP-006~009 = DATASET-002, separate batch.
  Risk fields (자살/자해/타해 사고) are tracked per-persona in a 위험 평가 table; harm-to-others
  (타해) has zero positive representation across all 4 (CVR-001 Finding 6).
- **Golden domain labels:** DATASET-004, `discussion.md` ~line 1001 — multi-label per VP, blind-
  authored from persona files only, pre-registered before F2 existed.
- **ADR-018 standing risk-lexicon taxonomy:** 15 stems, all self-harm/SI (passive SI, burdensomeness,
  meaninglessness, death-wish, self-harm phrasing) — 0 harm-to-others stems (see EXP-012, `result.md`
  ~line 1736, "Secondary manual broader-taxonomy audit"). This taxonomy also gates the proposed A5
  RAG query filter (PLAN-2026-W28-O), so the SI-only scope is a compounding gap, not isolated.
- **Best single artifact for "what does a real dialogue/slot/RAG-top-5 output actually look like":**
  EXP-012, `result.md` ~line 1622 — fresh F1→F2 batch, VP-001~004, includes full domain_candidates +
  ai_predicted_disease top-5 tables with similarity_score + source quotes.
- **PLAN-2026-W28-O folded program plan v1:** `discussion.md` ~line 3109-3227 (Goal, 3 binding user
  directives, sections A 구현설계/B 검증설계/C sequencing/D user-question gaps). This is the standing
  program plan clinical-validator reviews are chained off (step 5a in its own step table).

**Added at CVR-002 (2026-07-10, v1.2 re-review) — re-verify paths before reuse, this project moves fast:**

- **Team-visible plan doc (v1.2):** `docs/ai/validation_plan_f1f2_continuous.md` — condensed rendering
  of `discussion.md`'s `PLAN-2026-W28-O`/`PLAN-2026-W28-P`/`CVR-001`/`REV-022`/`ADR-023`; this file plus
  the two workflow docs below are the ones that **survive** the blind-validation-protocol archival
  (`ADR-023` Phase 2, W6→W7 boundary) — anything only in `discussion.md` prose is at risk of being lost
  to blind W7/W8 validators unless transcribed here first (CVR-002 Finding 4 — a general pattern to
  check for in any future plan-stage re-review of a project with a similar blind/archive protocol).
- **Workflow checklist:** `docs/ai/workflow_checklist_f1f2.md` — essence-only stage×status table; also
  survives archival. Useful for a fast check of "did an adopted CV recommendation actually get a wave
  assigned to it" (at CVR-002, W8's row did not name clinical-validator as an owner despite an adopted
  W8 face-validity-check remedy from CVR-001 — caught by comparing this doc against the discussion.md
  disposition text, not by reading either alone).
- **New personas (design-stage only, not yet authored as files):** VP-010 (minimizing/non-crisis),
  VP-011 (somatic-masks-mood), VP-012 (chronic AUD) — design lives in `validation_plan_f1f2_continuous.md`
  §9, not yet at `docs/ai/personas/VP-01{0,1,2}_*.md` (only VP-001~004 exist there as of CVR-002).
- **AUD ontology entry — content SIGNED OFF at CVR-006 (2026-07-11), DB load cleared:** slug
  `alcohol-use-disorder`, KO name FINALIZED "알코올 사용장애(의존)" (the `# DRAFT pending CVR
  sign-off` marker at `ontology.py:346` is stale as of CVR-006 — developer applies the removal, not
  yet re-verified in a later session), KCD F10.2, classification `substance`,
  `DISEASE_SYMPTOMS["alcohol-use-disorder"] == ["craving", "perceived_loss_of_control"]` (confirmed,
  `ontology.py:559`; `sleep_disturbance` deliberately excluded, confirmed defensible — reasoning at
  `:543-558`). Entry tuple + comment at `ontology.py:337-351`; neighbors: `alcohol-intoxication`
  (`:323-329`, KO "알코올 중독(급성)" — precedent for the parenthetical-disambiguation naming
  convention CVR-006 reused), `alcohol-withdrawal` (`:330-336`, F10.3; flags `:534-542` incl.
  `craving` and `sleep_disturbance`), `borderline-personality-disorder` flags include
  `perceived_loss_of_control` (`:524`). Re-verify line numbers before reuse — this file moves.
  If a future session finds the DRAFT marker still present or the DB still at 26 diseases, that is a
  live regression against CVR-006's binding ruling, not a re-open of the content question itself.

**Added at CVR-004 (2026-07-11, W6 persona content sign-off) — re-verify paths before reuse:**

- **CTRS (Crisis Triage Rating Scale) enum:** `apps/ai-server/src/schemas/common.py:20-30`
  (`CTRSLevel(IntEnum)`, based on 국립정신건강센터 field-response guideline). 1=EMERGENCY, 2=HIGH_RISK,
  3=ACUTE, 4=MODERATE ("지속적 우울·불안, 기능 손상" — persistent depression/anxiety + functional
  impairment, no acute/crisis features), 5=STABLE. Lower number = more severe. This is the strongest
  available ground truth for adjudicating any persona's "CTRS 예상" claim — prefer citing this docstring
  over inferring severity bands only from sibling-VP precedent (`docs/ai/vp_validation_scenarios.md`).
  `RISK_TO_CTRS`/`CTRS_TO_RISK` dicts on the same file map to/from `RiskLevel`.
- **Risk-lexicon taxonomy, corrected count:** `apps/ai-server/src/eval/f2_grounding.py:88-153`
  (`_RISK_PHRASES`) = **37 literal entries / 20 stem families**, not 15 — the "15-stem" citation was
  project-wide-corrected at REV-024/REV-025 (2026-07-11, mechanically recounted twice independently).
  Any older doc/memory citing "15 stems" is stale. Covers: 자살/자해 core, 손목을 긋/목숨을 끊/유서,
  burdensomeness ("짐이 되"/"부담이 되"), meaninglessness ("사는 게 의미"/"살아서 뭐하"), death-wish
  ("죽으면 편할"/"죽는 게 낫"/"차라리 죽") — all self-harm/SI-oriented, still 0 harm-to-others stems
  (CVR-001 Finding 6, still open as of CVR-004).
- **VP-010/011/012 now exist as full content** (not just design) at `docs/ai/personas/
  VP-010_first_visit_minimizing.md` / `VP-011_first_visit_somatic.md` / `VP-012_first_visit_alcohol.md`.
  Reviewed CVR-004 (2026-07-11): all three adequate-with-findings, 0 blocking, data cleared to author
  golden labels. Established convention confirmed across the whole VP series (VP-001 already does this):
  persona §4 "Expected slot values" tables use granular field names (`sleep_onset`, `mood_duration`,
  `anxiety_trigger`, etc.) that are NOT the actual 12 canonical `ClinicalSlotAgent` Pydantic keys — they
  are golden-label-authoring-convenience fields, presumably aggregated into the real coarse slots
  (`history_of_present_illness` etc.) at scoring time. Don't mistake this for a schema violation when
  reviewing a persona file — it's pre-existing project convention, not a new deviation.
- **Questionnaire mapping (reviewed CVR-003):** `apps/ai-server/src/rag/questionnaire_mapping.py` — 10
  classification→scale rows, no-forced-mismatch discipline, `mood→PHQ-9` has an undisclosed-in-artifact
  mania blind spot (CVR-003 Finding 1, W5 addendum adopted to fix).

**Added at CVR-005 (2026-07-11, pre-W7 content authoring) — re-verify before reuse:**

- **Plan doc structure for pre-registered content:** `docs/ai/validation_plan_f1f2_continuous.md` §8a
  ("Adopted clinical remedies" table, under §8 "Review outcomes") lists remedies ii-vi by title+owner
  only — no rubric text. §9 has the "Assessment-closure conditions" block (VP-010/011/012). The doc's
  "Appendix — blind-survival transcription" (Appendix A: data's N=75 threshold; B: SM
  bisection-on-failure protocol; C: Policy-B Gate-0 certification rule; D: BUG-028 truncation-rate
  protocol) is the established landing pattern for content that must survive the W6→W7 blind-state
  reset — CVR-005's six instruments are intended for a new **Appendix E** here, per its own
  transcription-requirement note. See [[content-authoring-cvr-pattern]] for the entry-format pattern.
- **12-slot Korean glosses** (exact, `apps/ai-server/src/agents/clinical_slot.py:26-39`, inline
  comments): 01 encounter_metadata=진료 기본정보, 02 chief_complaint=주호소, 03
  history_of_present_illness=현병력, 04 past_psychiatric_history=정신과 과거력, 05
  medical_history=신체질환/신경학적 병력 (physical/neuro only, NOT psychiatric medication),
  06 personal_social_history=개인사/사회력, 07 family_history=가족력, 08
  substance_use_history=음주·흡연·물질사용, 09 mental_status_exam=정신상태검사, 10
  risk_assessment=위험평가, 11 clinical_assessment=평가/진단적 인상, 12
  treatment_plan=치료계획/치료내용. CVR-005 pre-declared: protective factors → `risk_assessment`
  primary (personal_social_history secondary/expected-overlap); medication-adherence status →
  `treatment_plan` primary (past_psychiatric_history secondary for the static medication-history
  list; explicitly NOT medical_history, which is physical/neuro-scoped only).
- **VP-010's reveal-tier worked exemplars are domain-limited:** `VP-010_first_visit_minimizing.md` §5
  gives concrete Tier-1/2/3 lines for only 3 domains (mood, sleep, interest) — energy/anxiety have no
  worked exemplars (CVR-004 Finding 3, restated CVR-005 Finding 3). Any metric built on this file's
  raw material (e.g. CVR-005's MPD checklist) is scope-limited to those 3 domains until the file is
  touched up.
