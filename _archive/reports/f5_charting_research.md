# F5 charting-convention and FHIR R4 research note

**Author:** brainstorm agent
**Date:** 2026-07-14
**Scope:** grounds the design of F5 — an AI-generated psychiatric pre-consultation intake
hand-off report for the receiving psychiatrist — in real clinical charting conventions and in
FHIR R4. Outward-facing literature/standards research only; no code, no plan, no HYP entries.
**Access date for all web citations below:** 2026-07-14 (fetched or searched on this date).

## Summary table

| # | Area | Key finding | Primary source(s) |
|:--|:--|:--|:--|
| 1a | SOAP note, psychiatric adaptation | Same S/O/A/P skeleton; Objective becomes the MSE; Plan mandates explicit SI/HI/self-harm risk documentation | [icanotes](https://www.icanotes.com/2018/04/25/tips-for-writing-better-mental-health-soap-notes/), [blueprint.ai](https://www.blueprint.ai/blog/psychiatric-soap-note-example-a-practical-guide-for-mental-health-professionals) (vendor sources, corroborated across 4+ independent vendors) |
| 1b | Psychiatric intake/consult note | APA names 9 required initial-evaluation topics incl. quantitative assessment, risk, documentation | [APA Practice Guidelines 3rd ed., Psychiatry Online](https://psychiatryonline.org/doi/10.1176/appi.books.9780890426760.pe02) |
| 1c | SBAR hand-off | Endorsed by Joint Commission/AHRQ/WHO for provider-to-provider handoff; mental-health variant maps Assessment→clinical impressions+risk, Recommendation→next steps | [Springer narrative review](https://link.springer.com/article/10.1186/s40886-018-0073-1), [PMC9798145](https://pmc.ncbi.nlm.nih.gov/articles/PMC9798145/) |
| 1d | MSE canonical elements + text-derivability | StatPearls' 11-domain MSE splits cleanly into observation-dependent (appearance, behavior, motor activity, speech quality, affect) vs. interview-derivable (mood, thought process/content, cognition-by-testing, insight, judgment); empirical LLM evidence confirms this split degrades specifically on behavioral/physiological items | [StatPearls NBK546682](https://www.ncbi.nlm.nih.gov/books/NBK546682/), [ADAPTS, arXiv:2605.03212](https://arxiv.org/pdf/2605.03212) |
| 1e | Psychiatric triage/intake | Triage prioritizes danger-to-self/others and functional-impairment severity, not disease-threat-to-life; validated instruments exist (CRPT) | [PMC4748451](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4748451/) |
| 1f | Korean clinical context | POMR (problem-oriented medical record) is the dominant Korean charting model incl. psychiatry-specific AMC guideline; law mandates detail sufficient to judge treatment appropriateness but a formal enumerated field list was not directly retrieved; HIRA has no distinct psychiatric *documentation-format* standard found | [DBpia abstract](https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE08898045), [의료법 제22조 casenote.kr](https://casenote.kr/%EB%B2%95%EB%A0%B9/%EC%9D%98%EB%A3%8C%EB%B2%95/%EC%A0%9C22%EC%A1%B0) |
| 3a | Composition vs DocumentReference | Composition = authored FHIR-native document, must be Bundle(type=document) first entry, section.entry references other resources; DocumentReference = pointer/index to any binary document | [hl7.org/fhir/R4/composition.html](https://hl7.org/fhir/R4/composition.html) |
| 3b | QuestionnaireResponse + LOINC | PHQ-9 total = 44261-6 (VERIFIED), PHQ-9 panel = 44249-1 (VERIFIED, panel not total), GAD-7 total = 70274-6 (VERIFIED), AUDIT-C total = 75626-2 (VERIFIED) | [loinc.org](https://loinc.org) direct fetches, see §3b table |
| 3d | RiskAssessment | `basis` (evidence refs), `prediction.rationale` (string), `prediction.qualitativeRisk`/`probabilityDecimal` fit CTRS + safety-probe representation | [hl7.org/fhir/R4/riskassessment.html](https://hl7.org/fhir/R4/riskassessment.html) |
| 3f | Non-diagnostic AI-content flagging | **No finalized FHIR standard exists.** DS4P security labels don't address AI/algorithmic authorship; an HL7 Jira proposal (PSS-2579) for AI-content disclosure is open, not yet a standard | [DS4P IG glossary](https://build.fhir.org/ig/HL7/fhir-security-label-ds4p/glossary.html), [HL7 Jira PSS-2579](https://jira.hl7.org/browse/PSS-2579) |

---

## 1. Charting conventions research

### 1a. SOAP note and its psychiatric adaptation

SOAP (Subjective, Objective, Assessment, Plan) is the near-universal outpatient note skeleton.
Multiple independent EHR/scribe-vendor sources (icanotes, blueprint.ai, commure, careclinicmd —
commercial documentation, not peer-reviewed literature, but consistent with each other and with
the academic Korean POMR description in §1f) converge on the same psychiatric adaptation:

- **Subjective (S):** patient-reported mood, sleep, stressors, often verbatim-quoted.
- **Objective (O):** in psychiatry this section is largely *replaced by the Mental Status
  Examination* — appearance, behavior, speech, mood(as observed)/affect, thought process,
  cognition — rather than vitals/physical-exam findings as in general medicine.
- **Assessment (A):** clinician's diagnostic formulation, integrating S+O; commonly anchors
  standardized-instrument scores (e.g., PHQ-9) as quantitative severity evidence.
- **Plan (P):** treatment plan **and** a mandatory structured risk section — presence/absence,
  frequency, plan, means access, intent, protective factors, risk stratification. Sources note
  that a note lacking MSE or risk assessment may not support the billed encounter level under
  CMS 2021 documentation guidance and creates liability exposure.

Source: [SOAP note psychiatric adaptation summary, icanotes](https://www.icanotes.com/2018/04/25/tips-for-writing-better-mental-health-soap-notes/) and [blueprint.ai](https://www.blueprint.ai/blog/psychiatric-soap-note-example-a-practical-guide-for-mental-health-professionals), 2026-07-14. **Caveat:** these are EHR-vendor marketing/blog content, not peer-reviewed guidance; used only for the consensus *structure*, cross-checked against the Korean academic POMR description (§1f) and the APA guideline (§1b), which independently corroborate the S/O/A/P-with-mandatory-risk pattern.

**Applicability to F5:** F5 is explicitly non-diagnostic, so the "Assessment" slot cannot be
populated with a diagnosis by the AI. The S/O structure is directly reusable (F1's chat-derived
chief complaint/HPI as S; F1's crisis events + F3 questionnaire scores + the text-derivable MSE
subset as O), but the "A" slot must be relabeled as an AI-authored *synthesis for clinician
review*, not a diagnostic assessment, and the mandatory-risk-in-Plan convention justifies
promoting risk/safety to its own explicit top-level section rather than burying it in a plan
paragraph.

### 1b. Psychiatric consultation/intake note structure

The **APA Practice Guidelines for the Psychiatric Evaluation of Adults, 3rd edition** — the
closest thing to a US professional-society standard here — organizes the initial evaluation
around nine topics: review of psychiatric symptoms/trauma/treatment history, substance use
assessment, suicide risk assessment, risk of aggressive behavior, cultural factors, medical
health, **quantitative assessment** (i.e., standardized instruments), patient involvement in
treatment decisions, and documentation of the evaluation itself. A companion pocket guide breaks
documentation into: Chief Complaint; HPI; Psychiatric/Substance/Family/Personal-Social/Medical
histories; Review of Systems; Examination including MSE; Review of Available Data; and
Formulation/Diagnostic Impression/Treatment Plan.
Source: [APA Practice Guidelines, Psychiatry Online](https://psychiatryonline.org/doi/10.1176/appi.books.9780890426760.pe02); [AJP summary article](https://www.psychiatryonline.org/doi/10.1176/appi.ajp.2015.1720501), 2026-07-14. Summary basis: search-result synthesis of the guideline's structure and named recommendations, not full-text read of the book chapter.

Independently, general psychiatric-intake-note guidance (multiple vendor sources, cross-checked)
lists the same core sections: Chief Complaint, HPI, Past Psychiatric History (+ hospitalizations,
treatment response, family psychiatric history), substance-use/medical/developmental/social
history, MSE, Assessment (working diagnosis + risk), Plan.
Source: [pmhealthnp.com](https://pmhealthnp.com/the-intake-follow-up-notes/), [icanotes](https://www.icanotes.com/2025/06/20/essential-components-of-a-comprehensive-initial-psychiatric-evaluation-template/), 2026-07-14.

**Applicability to F5:** F1's 12 clinical-intake slots (chief complaint, HPI, risk assessment,
etc.) map directly onto this convention's front half. The APA's explicit "quantitative
assessment" topic directly justifies giving F3's questionnaire results and F2's AI-predicted
candidates named, separately-labeled sections rather than folding them into narrative prose —
consistent with the hard constraint that AI-predicted-disease stays a separate section.

### 1c. SBAR hand-off format

SBAR (Situation, Background, Assessment, Recommendation) is endorsed by the Joint Commission,
AHRQ, IHI, and WHO as a structured provider-to-provider handoff tool, shown in a controlled
before/after study to raise completed-handoff-component rates from near-zero to 67–89% after
training.
Source: [Situation, Background, Assessment, Recommendation (SBAR) — narrative review, Safety in Health/Springer](https://link.springer.com/article/10.1186/s40886-018-0073-1); [PMC9798145 (Sudanese teaching hospital SBAR study)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9798145/); [AHRQ PSNet](https://psnet.ahrq.gov/issue/situation-background-assessment-recommendation-sbar-communication-tool-handoff-health-care), 2026-07-14.

A mental-health-specific adaptation (vendor source, used only for the section-mapping) assigns:
Situation = 1–2 sentence current concern; Background = psychiatric/medical/social history;
Assessment = "clinical impressions, observed behaviors, and identified risks"; Recommendation =
evidence-based next steps.
Quote (≤15 words): *"Summarize clinical impressions, observed behaviors, and identified risks."*
Source: [mentalyc.com/blog/sbar-mental-health](https://www.mentalyc.com/blog/sbar-mental-health), 2026-07-14.

**Applicability to F5:** SBAR's core value for F5 is *not* as the primary section skeleton
(SOAP/psychiatric-intake conventions are richer and better match our available inputs) but as
the justification for a short "situation-first" header/orientation block at the very top of the
report — the psychiatrist should get the one-paragraph situation + immediate risk flag before
reading the full structured body, exactly the failure mode SBAR was designed to prevent
(critical information buried in a long note).

### 1d. Mental Status Examination — canonical elements and text-only derivability

**Canonical element list**, per StatPearls (NIH NCBI Bookshelf, the most authoritative single
source found) and cross-checked against AMBOSS and the Trzepacz & Baker MSE textbook (the latter
known only via secondary citation, not fetched — flagged accordingly):

| Domain | StatPearls definition (paraphrased) | Requires visual/behavioral observation? |
|:--|:--|:--:|
| Appearance | grooming, attire, hygiene, visible marks, apparent-vs-stated age | **Yes — not derivable from text** |
| Behavior | cooperation, distress level, interaction style during interview | **Yes — not derivable from text** |
| Motor activity | psychomotor speed (retardation/agitation), gait, posture, abnormal movements/tremor | **Yes — not derivable from text** |
| Speech | rate, rhythm, volume, tone (paralinguistic qualities, not just word content) | **Yes — not derivable from text** (word choice/coherence is a text-derivable proxy but not equivalent) |
| Affect | clinician's inference of emotional expression from nonverbal cues/facial expression | **Yes — not derivable from text** |
| Mood | patient's self-reported feeling, ideally verbatim-quoted | No — directly derivable from chat text |
| Thought process | organization/logic of expressed thought (linear, tangential, circumstantial, flight of ideas, blocking) | Partially — inferable from text coherence, but conversational-turn artifacts (e.g., interruption, typing lag) can confound a chat transcript in ways a live interview would not |
| Thought content | delusions, obsessions, SI/HI, preoccupations | No — directly derivable from chat text |
| Perceptions | hallucinations/illusions *as reported by the patient* | No, if patient volunteers/answers directly — derivable; but perceptual disturbance the patient does not recognize/report cannot be inferred from text alone |
| Cognition | alertness, orientation, concentration, memory, abstraction — via direct testing/questions | Partially — formal cognitive testing (e.g., serial 7s) can be posed as chat questions, but informal/incidental cognitive impressions clinicians form from live interaction (attention lapses, response latency) are lost |
| Insight | patient's understanding of their own illness | No — inferable from what the patient says about their condition |
| Judgment | soundness of decision-making, via history + scenario questions | No — inferable from patient's described reasoning/choices, with the same caveat as thought process |

Source: [StatPearls, Mental Status Examination, NBK546682](https://www.ncbi.nlm.nih.gov/books/NBK546682/), fetched directly 2026-07-14; [AMBOSS](https://www.amboss.com/us/knowledge/mental-status-examination), 2026-07-14 (search-snippet corroboration only). Trzepacz & Baker (1993) textbook domain list cited only via secondary sources — **Summary basis: secondary citation only, not independently verified.**

**Empirical evidence for the text-derivability split**, not just structural reasoning:

- **ADAPTS** (Vail, Cicconet, Aafjes-van Doorn, Maroney, Aafjes) reports that a text-only
  automated symptom-rating system achieved *"near-human accuracy for semantically explicit
  constructs like suicidality and guilt"* but showed *"persistent bias for symptoms requiring
  behavioral or physiological observation, including psychomotor disturbance."* The paper's own
  stated design response was to **intentionally exclude** psychomotor agitation/retardation and
  observable-anxious-behavior items from automated text-only scoring rather than infer them
  unsupported.
  Source: [ADAPTS, arXiv:2605.03212](https://arxiv.org/pdf/2605.03212), fetched directly 2026-07-14.
- A JMIR mHealth/uHealth chatbot-assessment validity study found high convergent validity between
  chatbot and paper/web self-report on the *same* construct (psychological distress, alcohol
  use), but this validated chatbot **against other self-report modes, not against clinician
  observation** — it does not demonstrate that a chatbot can substitute for the
  observation-dependent MSE domains, only that self-report constructs transfer well across
  self-report *modes*.
  Source: [Schick, Feine, Morana, Maedche, Reininghaus, JMIR mHealth uHealth 2022, PMC9664331](https://pmc.ncbi.nlm.nih.gov/articles/PMC9664331/), fetched directly 2026-07-14.
- Telepsychiatry literature (video, not even text-only) already documents degraded MSE fidelity:
  *"gait and peripheral movements are rarely done"* and *"a full assessment of grooming is
  impossible"* over video — establishing that even richer-than-text remote modalities lose
  observation-dependent domains, a fortiori true for text-only chat.
  Source: [Telepsychiatry: To Be or Not to Be, Psychiatric Times](https://www.psychiatrictimes.com/view/telepsychiatry-to-be-or-not-to-be-that-is-the-question), 2026-07-14 (search-snippet basis).

**Load-bearing conclusion for F5 design:** a text-only chat intake can populate mood, thought
content, insight, and judgment with reasonable fidelity, and thought process/cognition with
caveats; it structurally **cannot** populate appearance, behavior, motor activity, speech
(paralinguistic), or affect (as clinically defined — observed, not self-reported). F5's MSE-like
section must be explicitly labeled as a **partial, text-derived mental status summary**, must
omit or explicitly mark "not assessed — text-only intake" for the five observation-dependent
domains, and must not present mood/thought-content items in a way that visually implies a
completed standard MSE.

### 1e. Psychiatric triage/intake report conventions

Psychiatric triage differs from general medical triage in its sorting criterion: general ED
triage sorts by *threat to life*; psychiatric triage sorts by *danger to self/others and severity
of functional impairment*. A minimum triage assessment typically includes vital signs, brief
medical screen, safety appraisal, and lethality potential, with two gating factors considered
first — medical stability and legal status. Validated instruments exist for this
(Color-Risk Psychiatric Triage, sorting 1–5 risk levels across up to 32 presentation types).
Source: [Validity and reliability of a novel Color-Risk Psychiatric Triage, PMC4748451](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4748451/); general summary via WebSearch of multiple sources including a ScienceDirect review, 2026-07-14. Summary basis: search-result synthesis; PMC4748451 abstract-level, not full-text read.

**Applicability to F5:** this convention supports two design choices — (1) the risk/safety
section should be structurally gated ahead of the narrative sections (triage logic: safety first,
narrative detail second), matching the SBAR "situation-first" recommendation in §1c; (2)
functional-impairment framing (not just symptom checklist) is a recognized triage dimension and
is a reasonable additional field for F1's risk-assessment slot if not already covered, though
this is outside this note's scope to specify.

### 1f. Korean clinical context

**What was found:**

- Korean hospital-charting practice is dominated by the **problem-oriented medical record
  (POMR)**: initial database (C/C, O/S, present-illness chronology, past medical/family history) →
  numbered problem list (active/inactive/resolved/temporary; "r/o" not permitted as a problem
  title until confirmed) → initial assessment & plan (diagnostic/therapeutic/education
  sub-components per problem) → progress notes in SOAP format.
  Source: [의무기록 작성법, moonhani.github.io](https://moonhani.github.io/Writing_Medical_Record/), fetched directly 2026-07-14. This source is general-medicine, not psychiatry-specific — explicitly noted by the source itself.
- A **psychiatry-specific Korean guideline exists**: 손정인, 강시현, 김창윤, "정신과 의무기록
  작성지침 개발 및 적용 후 입원의무기록의 질적 변화 비교 연구" (신경정신의학/Journal of the
  Korean Neuropsychiatric Association), describing the Asan Medical Center's modified-POMR
  psychiatric medical-record guideline developed by a psychiatrist/resident working group,
  2005–2006. Full text was not reached (DBpia paywall); only the abstract-level description is
  used here.
  Source: [DBpia abstract, NODE08898045](https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE08898045), 2026-07-14. **Summary basis: abstract/search-snippet only, not full-text read.**
- **Legal baseline:** 의료법 (Medical Service Act) Article 22 requires medical personnel to
  record "in detail" the patient's main symptoms, diagnosis, and treatment course, with the
  Enforcement Rule (시행규칙) Article 14 delegated to specify exact required fields; falsification
  or backdated alteration is separately prohibited under Article 22(3) with criminal penalties.
  Records must be written in Korean (with foreign-language terms permitted for disease/test/drug
  names) and retained 10 years for the chart itself. **This note was not able to directly fetch
  the enumerated field list in Article 14** (the fetched page redirected to a different article);
  the general "detail sufficient to judge treatment appropriateness" standard is corroborated
  across three independent secondary sources but the literal Article 14 text is UNVERIFIED here.
  Source: [의료법 제22조, casenote.kr](https://casenote.kr/%EB%B2%95%EB%A0%B9/%EC%9D%98%EB%A3%8C%EB%B2%95/%EC%A0%9C22%EC%A1%B0), 2026-07-14; general summary via WebSearch, 2026-07-14.
- A specific psychiatric-institution record-management regulation exists at Korea's National
  Center for Mental Health (국립정신건강센터 의무기록 관리에 관한 규정, most recently amended
  effective 2022-02-24), but this is an internal administrative-management regulation
  (retention/access), not a documentation-content/section-structure standard.
  Source: [law.go.kr admRulLsInfoP.do, admRulSeq=2100000219282](https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2100000219282), 2026-07-14 (search-snippet basis, not fetched directly).

**What was not found — stated plainly:** no HIRA (건강보험심사평가원) document specifically
governing *psychiatric medical-record documentation format/structure* was located in this
session; HIRA materials found concern reimbursement/billing criteria (수가, 급여기준), not
charting conventions. No official KAMC (대한의학회/Korean Academy of Medical Sciences or
Korean Association of Medical Colleges) documentation-content standard was found either — KAMC's
public mandate is medical-education accreditation, not clinical documentation standards; this
absence should not be read as "no such document exists," only that this session's search did not
surface one.
Source: WebSearch of `hira.or.kr`, `kams.or.kr`, `kamc.kr`, 2026-07-14 — no relevant page found among top results.

**Applicability to F5:** the POMR problem-list convention and the psychiatry-specific
AMC/Asan guideline both corroborate the SOAP-with-explicit-risk-section structure independently
derived in §1a/§1b, giving F5's proposed skeleton (§2) a Korean-context anchor, not just a
US-literature one. The legal "detail sufficient to judge appropriateness" and Korean-language
requirement both argue for the F5 report body to be authored/exportable in Korean, with the
non-validated-administration and non-diagnostic caveats stated in Korean as well as English if
the artifact is ever treated as part of the legal medical record (a scope question for the
orchestrator/developer, not resolved here).

---

## 2. Recommended F5 section structure

### 2a. Design principles carried from §1

1. **Situation-first micro-header** (§1c, SBAR) — one short block up top: reason for referral,
   current risk flag, session/report metadata.
2. **SOAP/APA-derived body** (§1a, §1b) — chief complaint → HPI → risk/safety → text-derived MSE
   → questionnaire results, with risk promoted to its own top-level section per the "mandatory
   risk in Plan" convention and APA's named risk-assessment topic.
3. **MSE section explicitly marked partial** (§1d) — only text-derivable domains populated;
   observation-dependent domains explicitly marked not-assessed, never silently omitted (silent
   omission would let a reader assume a normal/unremarkable finding).
4. **AI-predicted-disease decision support kept structurally separate** (hard constraint, also
   independently justified by APA's distinct "quantitative assessment" topic and by the general
   principle in §1a that F5's assessment slot cannot carry an AI-authored diagnosis) — its own
   section, never merged into narrative.
5. **Two-part split — static (current session) + longitudinal (across sessions)** — no single
   charting convention in §1 dictates this exact split (SOAP/APA describe a single encounter),
   but F4's cross-session trend analysis has no natural home inside a single-encounter note
   convention; a distinct longitudinal part is a design choice made here, not literature-derived,
   and should be reviewed by critic/clinical-validator as such.

### 2b. Proposed skeleton

**Part A — static (current-session hand-off)**

| § | Section | Populated from | Convention basis |
|:--|:--|:--|:--|
| A0 | Header / situation micro-summary | report metadata, F1 chief complaint (1 line), current CTRS + risk flag | SBAR situation-first (§1c) |
| A1 | Chief complaint | F1 slot | SOAP-S, APA CC (§1a, §1b) |
| A2 | History of present illness | F1 slot(s) | SOAP-S, APA HPI (§1a, §1b) |
| A3 | Risk / safety assessment | F1 risk-assessment slot + crisis/safety-probe events + current CTRS | SOAP-P mandatory risk section, APA suicide-risk topic, psychiatric-triage safety-first logic (§1a, §1b, §1e) |
| A4 | Mental status summary (partial, text-derived) | F1 conversational content, mapped only to mood/thought-content/thought-process/insight/judgment/cognition-by-testing; appearance/behavior/motor/speech/affect explicitly marked "not assessed — text-only intake" | MSE canonical list + text-derivability analysis (§1d) |
| A5 | Administered questionnaires | F3 (PHQ-9/GAD-7/AUDIT-C, Korean versions) scores + severity bands, each carrying the non-validated-administration caveat ("obtained via AI-administered chat, not validated clinical administration") | APA quantitative-assessment topic (§1b); caveat is a hard constraint from the brief, not literature-derived |
| A6 | AI decision-support: candidate conditions (non-diagnostic) | F2 AI-predicted-disease top-5 similarity list | Kept separate per hard constraint; similarity score explicitly labeled not-a-probability |
| A7 | Recommended department / questionnaires | F2 domain/department candidates + recommended-questionnaire list | Referral/consult-note convention (§1b, §3e) |
| A8 | Clinician-facing synthesis (non-diagnostic) | AI-authored short synthesis of A1–A6 for the psychiatrist's own use; explicitly not a diagnostic assessment or formulation | Adapted from SOAP-A / APA formulation slot, relabeled per §1a's "Applicability" note |

**Part B — longitudinal (cross-session trend)**

| § | Section | Populated from | Convention basis |
|:--|:--|:--|:--|
| B1 | Trend verdicts per scale | F4 trend verdicts, band transitions | No direct single-encounter-note precedent; modeled as a "flowsheet"/trend-table extension, closest to lab-trend or vital-sign trending conventions carried into FHIR (§3c) |
| B2 | CTRS trajectory | F4 CTRS series | as B1 |
| B3 | Event timeline | F1 crisis/safety-probe events across sessions | as B1; also aligned with SBAR "background" (relevant history leading to current situation, §1c) |
| B4 | Discordance flags | F4 discordance flags (e.g., self-report vs. CTRS divergence) | Novel to this system; no charting-convention precedent found — flagged as a design choice, not literature-grounded |
| B5 | Trend charts (PNG) | F4 chart attachments | Supplementary visual attachment, analogous to attaching lab-trend graphs to a chart; no formal charting-convention citation found for this specific practice |

**Explicit non-negotiables carried into the skeleton (from the brief, restated for traceability):**
A6 (AI-predicted-disease) is never merged into A1–A5 or A8; A5's questionnaire numbers always
carry the non-validated-administration caveat; A6's similarity scores are never presented or
labeled as probabilities anywhere in the report.

---

## 3. FHIR R4 mapping research

### 3a. Composition vs. DocumentReference for a file-exported bundle

For a **structured hand-off document with no FHIR server**, the relevant choice is between:

- **Composition + Bundle(type=document):** Composition is "a set of healthcare-related
  information... assembled together into a single logical package," but *"a Composition alone
  does not constitute a document"* — it must be the first entry in a `Bundle` with
  `Bundle.type = "document"`, and *"any other resources referenced from Composition must be
  included as subsequent entries in the Bundle."* `Composition.section.entry` is
  *"a reference to the actual resource from which the narrative in the section is derived"*
  (cardinality 0..*) — unlike CDA, section entries point to separate structured resources
  (Observation, RiskAssessment, etc.) rather than embedding the data inline.
  `Composition.type` is 1..1, bound (preferred) to LOINC document-type codes.
  Source: [hl7.org/fhir/R4/composition.html](https://hl7.org/fhir/R4/composition.html), fetched directly 2026-07-14.
- **DocumentReference:** *"used to index a document, clinical note, and other binary objects to
  make them available to a healthcare system"* — it is a metadata/pointer wrapper for a document
  of any format (including a pre-assembled FHIR document Bundle, a PDF, or a CDA document), not a
  structural container for the clinical content itself.
  Source: [hl7.org/fhir/R4/documentreference.html](https://hl7.org/fhir/R4/documentreference.html), via WebSearch synthesis quoting the R4 spec directly, 2026-07-14.

**Recommendation for F5:** since F5 is authored natively as structured data (F1–F4 outputs) and
exported as a file (no FHIR server round-trip required), the **Composition + Bundle(type=document)**
pattern is the correct fit — it lets each report section reference the actual structured resource
(an Observation for a PHQ-9 score, a RiskAssessment for the safety section, etc.) rather than only
carrying prose. A `DocumentReference` would be appropriate *in addition*, only if/when F5 is later
indexed into an actual clinical document-management system as a pointer to the exported file —
out of scope for the current file-export-only design.

### 3b. QuestionnaireResponse and LOINC codes for instrument results

`QuestionnaireResponse` is *"a structured set of questions and their answers... corresponding to
the structure of the grouping of the questionnaire being responded to,"* distinguished from
`Observation` because *"Observation is used primarily for capturing... 'true' observations,"*
while QuestionnaireResponse is the right resource for the raw item-level answers to PHQ-9/GAD-7/
AUDIT-C. The companion **Structured Data Capture (SDC)** implementation guide defines how to
extract summary-score Observations from a completed QuestionnaireResponse.
Source: [hl7.org/fhir/R4/questionnaireresponse.html](https://hl7.org/fhir/R4/questionnaireresponse.html), via WebSearch synthesis quoting the R4 spec, 2026-07-14.

**LOINC code verification (each fetched directly from loinc.org, 2026-07-14):**

| Code | Long common name | What it actually denotes | Status |
|:--|:--|:--|:--:|
| `44261-6` | Patient Health Questionnaire 9 item (PHQ-9) total score [Reported] | The **summed total score** (0–27), a single Component, not a panel | **VERIFIED** — [loinc.org/44261-6/](https://loinc.org/44261-6/) |
| `44249-1` | PHQ-9 quick depression assessment panel [Reported.PHQ] | The **panel/group of items** (9 items + 1 functional-impairment question), containing 44261-6 as its derived-score member — **not itself a total score** | **VERIFIED** — [loinc.org/44249-1/](https://loinc.org/44249-1/) |
| `70274-6` | Generalized anxiety disorder 7 item (GAD-7) total score [Reported.PHQ] | The GAD-7 **total score** (0–21) | **VERIFIED** — [loinc.org/70274-6](https://loinc.org/70274-6) |
| `75626-2` | Total score [AUDIT-C] | The AUDIT-C **total score** (0–12) | **VERIFIED** — [loinc.org/75626-2](https://loinc.org/75626-2) |

**Correction of the brief's candidate codes:** the brief asked to check "44261-6 vs 44249-1" —
these are **not interchangeable alternates**; 44261-6 is the total score and 44249-1 is the
containing panel. F5's Observation for "PHQ-9 total score" must use **44261-6**; if F5 ever
represents the full item-level QuestionnaireResponse, its `Questionnaire`/`QuestionnaireResponse`
reference should use **44249-1** as the instrument/panel identifier, not as a score.

**Korean-language administration:** LOINC identifies the instrument/construct, and item-level
translations are handled as linguistic variants of the same code rather than separate codes per
language — this is LOINC's general design principle, but this specific claim was **not
independently verified by fetching a LOINC-language-policy page in this session; flagged
UNVERIFIED.** Practical implication if true: F3's Korean-language PHQ-9/GAD-7/AUDIT-C scores can
use the same codes above regardless of administration language; this should be confirmed against
LOINC's language-variant documentation before being relied on in an implementation.

### 3c. Observation for score / CTRS / sentiment series

`Observation.category` (CodeableConcept, **preferred** binding to
`http://terminology.hl7.org/CodeSystem/observation-category`) includes the code **`survey`**
(*"Assessment tool/survey instrument observations (e.g., Apgar Scores, Montreal Cognitive
Assessment (MoCA))"*) — the correct category for PHQ-9/GAD-7/AUDIT-C score Observations and, by
extension, for our proprietary CTRS score. `Observation.code` is 1..1 required, LOINC-bound at
*example* (not required) strength — meaning a proprietary code (no LOINC exists for CTRS) is
permitted, but must use a locally-defined CodeSystem, not an invented LOINC-looking code.
`Observation.effectiveDateTime` (one of four effective[x] options) is *"the time... the observed
value is asserted as being true"* and is the standard mechanism for longitudinal series: repeated
Observation instances sharing the same `code`/`category` but differing `effectiveDateTime`, sorted
chronologically, are how FHIR represents a trend — there is no dedicated "time-series" resource.
`Observation.component` supports multi-part scores (e.g., a CTRS with sub-scores) as a
BackboneElement of repeated code/value[x] pairs. `Observation.note` (Annotation, 0..*) is
available for narrative caveats (e.g., non-validated-administration disclosure) attached to a
specific score.
Source: [hl7.org/fhir/R4/observation.html](https://hl7.org/fhir/R4/observation.html), fetched directly 2026-07-14; category value set via [terminology.hl7.org/CodeSystem/observation-category](https://terminology.hl7.org/3.1.0/CodeSystem-observation-category.html), via WebSearch synthesis, 2026-07-14.

**CTRS code status:** no LOINC code exists for a proprietary "clinical risk score" like CTRS —
**UNVERIFIED/not applicable**, must be represented with a locally-defined CodeSystem URI (e.g.,
an internal `http://neurosync.local/fhir/CodeSystem/ctrs` placeholder), not a borrowed or invented
LOINC code.

### 3d. RiskAssessment for the risk/safety section

`RiskAssessment`'s purpose is *"an assessment of the likely outcome(s) for a patient... as well as
the likelihood of each outcome."* Relevant fields: `basis` (0..*, Reference(Any)) —
*"indicates the source data considered as part of the assessment (for example, FamilyHistory,
Observations, Procedures, Conditions, etc.)"* — fits referencing the CTRS Observation and any
crisis/safety-probe event resources as evidentiary basis; `prediction.outcome` — the possible
outcome being assessed; `prediction.probabilityDecimal` or `.qualitativeRisk` (e.g., low/medium/
high) — the risk-level output; `prediction.rationale` (string) — *"additional information
explaining the basis for the prediction"* — the natural home for the AI's risk-flag reasoning
text; `mitigation` — *"a description of the steps that might be taken to reduce the identified
risk(s)."*
Source: [hl7.org/fhir/R4/riskassessment.html](https://hl7.org/fhir/R4/riskassessment.html), fetched directly 2026-07-14.

**Caveat for F5:** `prediction.probabilityDecimal` must **not** be populated from CTRS or
similarity scores if those scores are not calibrated probabilities (consistent with the hard
constraint that similarity scores are never probabilities) — `qualitativeRisk` (low/medium/high)
or a locally-coded risk band is the safer mapping unless CTRS has been formally validated as a
calibrated probability, which is outside this note's scope to determine.

### 3e. ServiceRequest for department/referral recommendation

`ServiceRequest`'s scope statement: *"A record of a request for service such as diagnostic
investigations, treatments, or operations to be performed."* Relevant fields:
`category` — *"classifies the service for searching, sorting and display"*; `code` — identifies
the specific requested service; `reasonCode` — justification for the request; `performerType` —
*"desired type of performer,"* and `performer` — a `Reference` to `Organization`/
`PractitionerRole`/`HealthcareService`, which is how a department/specialty referral target is
represented (e.g., referencing a "Psychiatry" or "Adolescent Mental Health" `HealthcareService`).
Historically, the separate `ReferralRequest` resource was merged into `ServiceRequest` because
*"their content was nearly identical."*
Source: [hl7.org/fhir/R4/servicerequest.html](https://hl7.org/fhir/R4/servicerequest.html), fetched directly 2026-07-14.

**Applicability:** F2's department/domain-candidate recommendation maps to `ServiceRequest.category`
+ `.performer` (target department/service), with `.reasonCode`/`.reasonReference` pointing back to
the AI-predicted-disease Observation/finding that motivated the recommendation — keeping the
non-diagnostic candidate list (§3f) as the *reason*, not the request's own diagnostic code.

### 3f. Flagging non-diagnostic AI-generated content in FHIR — honest gap report

Three candidate mechanisms were checked; **none is a finalized, adopted standard for this
specific purpose**:

1. **Composition section-code choice** — using a section code/title that itself denotes
   "decision support" or "AI-generated, non-diagnostic" is possible or free-text but is a local
   convention, not a controlled-vocabulary FHIR pattern; no LOINC document-ontology code was
   found meaning specifically "non-diagnostic AI decision support."
2. **Observation.note / Composition.section.text** — both support free-text narrative and are the
   most immediately usable mechanism today: a caveat sentence can be placed in `Observation.note`
   or in the section's narrative `text`, but this is an unenforced convention, not a structured,
   machine-checkable flag.
3. **Security labels (DS4P)** — checked directly: *"there are no explicit statements addressing
   security labels for AI-generated, algorithm-generated, or decision-support content"* in the
   DS4P implementation guide; its closest related concept is generic **Provenance** metadata
   (*"entities, activities, and people involved in producing a piece of data"*), which can record
   *that* an algorithm authored a resource (via `Provenance.agent`/`Provenance.entity` — not
   independently fetched/verified in this session, flagged UNVERIFIED) but has no dedicated
   "non-diagnostic" semantic.
   Source: [DS4P IG glossary](https://build.fhir.org/ig/HL7/fhir-security-label-ds4p/glossary.html), fetched directly 2026-07-14.
4. **Active standards work, not yet adopted:** an open HL7 Jira ticket proposes *"standardized
   ways to access and understand when content in FHIR resources has been generated or modified by
   AI/LLM systems, including mandatory disclosure of AI/ML model use"* — this confirms the gap is
   recognized by HL7 but confirms there is **no shipped standard to point to today**.
   Source: [HL7 Jira PSS-2579](https://jira.hl7.org/browse/PSS-2579), via WebSearch synthesis, 2026-07-14 — **not independently fetched/read in full; ticket existence and quoted framing only, treat as UNVERIFIED beyond the quoted snippet.**

**Honest conclusion:** FHIR provides general-purpose tools (free-text `note`, `Provenance`,
`Composition.section` structure) that *can* be used to carry a non-diagnostic/AI-generated
disclosure, but **there is no dedicated, standardized FHIR flag for "this is AI-generated,
non-diagnostic decision-support content."** Any F5→FHIR mapping that needs this distinction to be
machine-enforced, not just narratively stated, will require a locally-defined
extension/CodeSystem — this is a real standards gap, not an oversight in this research.

---

## 4. FHIR mapping table

| F5 section (§2b) | FHIR resource | Code system + code | Verification status |
|:--|:--|:--|:--|
| Document as a whole | `Bundle` (type=document), first entry `Composition` | `Composition.type` = LOINC `57143-0` "Mental health Referral note" (best fit; imperfect — see note) | **VERIFIED** code exists ([loinc.org/57143-0/](https://loinc.org/57143-0/), fetched 2026-07-14); **fit is a design judgment, not a literal match** — no LOINC document type exists for "AI-generated non-diagnostic pre-consultation intake hand-off." Alternative considered: `34788-0` "Psychiatry Consult note" (VERIFIED, [loinc.org/34788-0/](https://loinc.org/34788-0/)) — rejected as primary choice because it conventionally denotes the *specialist's own* consult note back to a referrer, whereas F5 flows the opposite direction (AI system → psychiatrist) |
| A1 Chief complaint | `Composition.section` (entry → `Observation` or narrative) | section.code = LOINC `10154-3` "Chief complaint Narrative - Reported" | **VERIFIED** ([loinc.org](https://loinc.org), via WebSearch quoting LOINC record, 2026-07-14) |
| A2 HPI | `Composition.section` | section.code = LOINC `10164-2` "History of Present illness Narrative" | **VERIFIED** (via WebSearch quoting LOINC record, 2026-07-14) |
| A3 Risk / safety | `RiskAssessment` (+ `Composition.section` referencing it) | section.code = LOINC `84209-6` "Mental health Outpatient Risk assessment and screening note"; resource = `RiskAssessment.basis`/`.prediction.rationale`/`.prediction.qualitativeRisk` | **VERIFIED** section code ([loinc.org/84209-6/](https://loinc.org/84209-6/), fetched 2026-07-14); **VERIFIED** RiskAssessment fields ([hl7.org/fhir/R4/riskassessment.html](https://hl7.org/fhir/R4/riskassessment.html), fetched 2026-07-14) |
| A4 MSE (partial, text-derived) | `Composition.section` (entry → `Observation`, category=`exam`) | section.code = LOINC `10190-7` "Mental status Narrative"; must carry `Observation.note` stating which domains were not assessed | **VERIFIED** ([loinc.org/10190-7](https://loinc.org/10190-7), fetched 2026-07-14) — **caveat: this code was designed for a complete clinician-observed MSE; using it for a partial text-derived version without a visible completeness caveat would misrepresent the section**, so the `.note` disclosure is not optional |
| A5 Questionnaires (PHQ-9/GAD-7/AUDIT-C) | `QuestionnaireResponse` (item-level) + `Observation` (total score), category=`survey` | PHQ-9 total = `44261-6`; PHQ-9 panel/instrument ref = `44249-1`; GAD-7 total = `70274-6`; AUDIT-C total = `75626-2`; each carries `Observation.note` with the non-validated-administration caveat | All four **VERIFIED** by direct loinc.org fetch, 2026-07-14 (see §3b table) |
| A6 AI-predicted-disease (non-diagnostic) | `Observation` (category=`survey` or `exam`, `component` per candidate) — **preferred over `ClinicalImpression`** | No LOINC/SNOMED code applies to a proprietary similarity-ranking output; use a locally-defined CodeSystem per candidate-list item; `Observation.note` must state "not a diagnosis, not a probability" | **N/A/UNVERIFIED** — no applicable standard code exists; `ClinicalImpression.finding` was evaluated as the semantically closer resource but is **Maturity Level 0 / Trial Use** in R4 with **no numeric probability/score sub-field** ([hl7.org/fhir/R4/clinicalimpression.html](http://hl7.org/fhir/R4/clinicalimpression.html), fetched 2026-07-14) — `Observation` is recommended instead as the more implementation-mature fit, at the cost of a less semantically precise resource type |
| A7 Department/questionnaire recommendation | `ServiceRequest` | `ServiceRequest.category` (department/domain), `.performer` (target service/department), `.reasonReference` → A6 Observation | **VERIFIED** field definitions ([hl7.org/fhir/R4/servicerequest.html](https://hl7.org/fhir/R4/servicerequest.html), fetched 2026-07-14); no single LOINC/SNOMED code set was verified for "recommended-questionnaire" as a distinct concept — **UNVERIFIED**, would need a local extension or `ServiceRequest.code` from a locally curated list of instrument-order codes |
| A8 Clinician-facing synthesis (non-diagnostic) | `Composition.section` narrative only, **no coded resource entry** | section.code = LOINC `51847-2` "Evaluation + Plan note" (used only for its narrative/summary framing; must not carry a diagnosis code) | **VERIFIED** code exists (via WebSearch quoting LOINC record, 2026-07-14) — **applicability caveat: this LOINC concept conventionally implies clinician-authored diagnostic assessment; using it for an AI-authored non-diagnostic synthesis requires an explicit disclaimer in the section narrative, same gap as §3f** |
| B1–B3 Longitudinal trend/CTRS/event timeline | Repeated `Observation` instances, same `code`+`category`, differing `effectiveDateTime`; CTRS = proprietary code | category=`survey`; CTRS code = local CodeSystem (no LOINC exists) | Mechanism **VERIFIED** ([hl7.org/fhir/R4/observation.html](https://hl7.org/fhir/R4/observation.html), fetched 2026-07-14); CTRS-specific code **UNVERIFIED/not applicable — must be locally defined** |
| B4 Discordance flags | `Observation` (derived/flag), `Observation.interpretation` or `.note` | No standard code found for "discordance flag" as a concept | **UNVERIFIED/not applicable** — novel to this system, no external standard located |
| B5 Trend charts (PNG) | `Media` resource (referenced from `Composition.section.entry`) or plain file attachment outside FHIR scope | N/A | **Not researched in this session** — flagged as an open item, see below |
| Non-diagnostic disclosure (cross-cutting) | No dedicated resource; best available = `Composition.section.text` narrative + `Provenance` (algorithm authorship) | N/A | **No standard exists** — see §3f; this is the most significant open gap in the whole mapping |

**Notes on the table as a whole:** every LOINC code above except the two flagged N/A/UNVERIFIED
(CTRS, discordance flags) was independently confirmed either by direct `WebFetch` of the
`loinc.org` page or by a `WebSearch` result that quoted the LOINC record's own long-common-name
text verbatim — both fetched/searched 2026-07-14, cited inline. The `Media` resource for B5 (PNG
chart attachment) was not researched in this session and should not be treated as recommended
without a follow-up check.

---

## Open items for the next stage (not this note's job to resolve)

- `Media` resource (or an equivalent file-attachment pattern) for the F4 PNG trend charts was not
  researched — flagged, not resolved.
- The Article 14 (의료법 시행규칙) enumerated field list was not directly retrieved; only the
  general Article 22 "sufficient detail" standard is sourced.
- The "LOINC codes are language-agnostic across translations" claim (§3b) needs a direct citation
  to LOINC's own linguistic-variant documentation before being relied on.
- No HIRA- or KAMC-specific psychiatric documentation-*format* standard was found; this gap is
  reported, not filled by inference.
- The two-part static/longitudinal split (§2a point 5) and the B4 discordance-flag section are
  design choices without a direct charting-convention precedent and should be flagged to
  clinical-validator for clinical-adequacy review, not treated as literature-grounded.
