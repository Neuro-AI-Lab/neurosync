# F1–F5 agent-collaboration composition

> **Purpose:** per-feature map of which agents/modules cooperate, in what order, with what
> handoffs, across the five clinical-pipeline features (F1 dialogue intake, F2 domain inference,
> F3 questionnaire administration, F4 longitudinal analysis, F5 hand-off report). Sourced from
> code (`apps/ai-server/src/`), the 14 agent specs (`docs/ai/agents/`), and
> `docs/ai/development_report.md` (`DR-001`..`DR-022`). No invention: every row cites the file or
> DR/ADR/REV/BUG/VAL entry it is drawn from. Validation-harness-only components are marked
> **[harness]**; everything else is production code.

---

## F1 — per-turn dialogue intake (Safety → Slot → Dialogue pipeline)

**Entry point:** `OrchestratorAgent` (`agents/orchestrator.py`, spec `01_orchestrator.md`) — an
11-state rule-based machine, **not an LLM caller itself**. `f1.py` is the validation-harness
mirror of the same state sequence (leaf-agent direct import, bypasses the orchestrator's own
boot/routing surface — DR-001 §7).

| Order | Agent / module | Role | Handoff to |
|:--|:--|:--|:--|
| 0 | `InputNormalizerAgent` (05) | STT/OCR/text normalization on every input (live-as-of PR #38 merge; correction sub-feature confirmed a verified-safe no-op, `BUG-020` open, DR-014 §4) | `SafetyClassifierAgent` |
| 1 | `SafetyClassifierAgent` (02) | Sequential rule-screen → **LLM final arbiter** (not a parallel min-merge); `max`-merge danger-takes-priority applies only in the fail-closed branch. Runs on **every turn**, unconditionally | CTRS 1–2 → `crisis_flow`; CTRS 3–5 → dialogue continues |
| 2 | `TemporalRetriever` (08) | Context assembly, runs in parallel with Safety | `dialogue_loop` (context only; superseded-for-F2, `DomainInferenceAgent`/14 is the live domain-inference path, DR-008 §3) |
| 3 | `DialogueAgent` (03) | Empathic interview, 1 follow-up question/turn, dialogue prompt v4 (natural-empathy generation, no literal example menu — `BUG-030`/`ADR-028`, DR-015) | `ClinicalSlotAgent` once `slot_coverage ≥ 0.7` or patient ends |
| 4 | **Grounding filter** (`src/grounding.py`) + `ClinicalSlotAgent` (04) | Runtime filter merges an extracted slot value only if it passes grounding (evidence-in-transcript); `risk_assessment` extractor-inference path is blocked at the code level, not the prompt level (DR-003 §1). Extraction is flat `dict[str, str]` over 12 canonical slots — no per-slot source/confidence/evidence subfields (`04_clinical_slot.md`) | `HandoffGeneratorAgent` |
| 5 | `HandoffGeneratorAgent` (10) | 12-section LLM report from final slots; every claim carries an `[ev_*]` citation | `EvidenceVerifierAgent` |
| 6 | `EvidenceVerifierAgent` (11) | Release gate, 6/12 checks implemented (`_check_unsupported_claims`, `_check_diagnosis_violations`, `_check_treatment_violations`, `_check_section_completeness`, `_check_ctrs_action_alignment`, `_check_dangling_references` — V-04/06/10/11/12 unimplemented, `11_evidence_verifier.md`). Reject → regenerate (max 2) → deliver-with-warning | session delivery |

**Crisis path (CTRS 1–2 or Safety Probe escalation):** `SafetyClassifierAgent` CTRS 1–2 diverts
the state machine straight to `crisis_flow` — dialogue is force-terminated, a `CRISIS_RESPONSE`
message is substituted, a dashboard alert + human-review flag fire, and an emergency handoff is
generated from whatever slots exist so far (`01_orchestrator.md`). For CTRS 3 + suicidal/self-harm
disclosure, a graduated **Safety Probe** state machine (5 layers: detect → structured C-SSRS-style
probe → escalate-to-CTRS-2-or-maintain-with-grounded-record → data/handoff integrity → scripted-VP
verification) mediates between "ignore" and "hard-stop," jointly owned by `SafetyClassifierAgent`
(detection/latch) and `DialogueAgent`/`ClinicalSlotAgent` (probe question injection, grounded
recording) — designed in DR-002 §1, implemented and safety-matrix-verified in DR-003.

---

## F2 — domain inference (Stage-1 retrieval → DomainInferenceAgent → evidence cascade → AI-predicted-disease)

| Order | Agent / module | Role | Handoff to |
|:--|:--|:--|:--|
| 1 | `f2.py::run_stage1` (code, reuses `src/rag/retrieval.py::retrieve_domain_chunks`) | In-process DB query (`rag.case_card`/`rag.qa`) on `chief_complaint`/HPI/`risk_assessment` slots. **Never HTTP** — the RAG HTTP API is permanently deleted, not merely unmounted (`ADR-017`→`ADR-019`, `src/rag/route.py`/`auth.py` removed from the filesystem, DR-011 §3). Never raises; DB/embedding failure silently degrades to `mode="llm_only"` | `DomainInferenceAgent` |
| 2 | `DomainInferenceAgent` (14, `agents/domain_inference.py`) | Stage-2, single LLM call (ModelRouter primary→fallback), never crashes — parse/schema failure yields empty candidates + `reason_summary` | `f2_grounding.py` |
| 3 | **Evidence whitelist / risk-lexicon cascade** (`src/eval/f2_grounding.py`) | Code-enforced (not prompt-only) source-id whitelist + quote-lexical match + risk-lexicon evidence filter (`_RISK_PHRASES`) — a candidate with zero surviving evidence is dropped whole. `_normalize_source_type_collision` (`BUG-019` fix) coerces a `qa`/`case_card`-table-origin value to `rag_chunk` pre-validation | `f2.py` artifact assembly |
| 4 | `ai_predicted_disease` population (`_build_ai_predicted_disease_populated`/`_collect_chunk_disease_votes`/`_aggregate_disease_candidates`, path1, `ADR-020`) | Deterministic **code-side** function over the same Stage-1 chunks already retrieved (no second LLM/retrieval call) — symptom-keyword match joined against the 26-disease ontology graph, `similarity_score` = the chunk's own retrieval score (never LLM-guessed), top-5, risk-lexicon-checked against **full chunk text** (`f2.py:465`, `BUG-031`-unrelated leak fix, DR-012 §3) | sibling key on the F2 artifact, never merged into `HandoffInput`/clinical slots |
| 5 | `questionnaire_mapping.py` (static disease→scale map) | Reads `ai_predicted_disease.recommended_questionnaire` | F3 trigger |

**Isolation enforcement:** `tests/test_hpi_isolation.py` (9 adversarial tests, `REV-013` §3
condition 1) covers the type layer (`extra="forbid"` — not yet implemented, non-blocking
follow-up), the `AgentInput.extra`/`state.conversation_history` channels, and a live behavioral
check through `HandoffGeneratorAgent.run()` — "structurally isolated" is licensed **scoped to
these 9 tests**, not as a claim that no future code path could ever leak (DR-010 §3).

**Gate sequence (every F2 wave):** critic plan review (`REV-`) → developer implementation → qa
code gate (mutation-checked) → `experiment-tracker` live batch (`EXP-`) → critic evidence review
(`REV-`, independent re-derivation from raw artifacts, never accepted from prose) → orchestrator
(`ADR-`) disposition. RAG-arm certification (`ADR-018`) is standing-conditional on two audits that
run on **every** future RAG-mode batch: the secondary taxonomy audit (0/N accepted quotes may
match the broader risk taxonomy) and the `retrieval_meta.queries` audit (`VAL-010`, open).

---

## F3 — questionnaire administration (F2-triggered, deterministic scoring)

| Order | Agent / module | Role | Handoff to |
|:--|:--|:--|:--|
| 1 | `src/f3.py` (deterministic engine, **zero LLM calls**) | Administers exactly the one scale named by F2's `ai_predicted_disease.recommended_questionnaire` — a separate path from `OrchestratorAgent.plan_surveys`/`score_and_check_safety` | item bank lookup |
| 2 | `src/scoring/item_bank.py` | v0 (construct-labels only, PHQ-9/AUDIT-C, non-validated, persona-file-sourced) superseded by v1 (research-sourced official Korean item text: PHQ-9 Pfizer 한국어판, GAD-7, PHQ-4, AUDIT-C v2 Korean-localized cutoffs male/unknown≥6 female≥5 — `CVR-018`/`ADR-034`; WHO-5 remains an honest 0/5 sourcing gap after 2 documented retries, `who5_sourcing_retry2.md`) | answer harness |
| 3 | `tests/simulation/survey_answer_llm.py` **[harness]** | The VP persona-simulator LLM selects item responses in-persona (`f1.py`'s `patient_input_fn` pattern) — never production code | `src/scoring/survey_scorer.py` |
| 4 | `src/scoring/survey_scorer.py` (deterministic, code, **zero LLM**) | Totals/severity bands computed in code, never by the LLM; item-9 (PHQ-9 SI item) drives a `continuous_test._route_phq9_safety_pathway` consumer seam — invoked-not-triggered across every battery to date, never live-exercised against a documented-positive case (DR-019 §8) | session ledger + F4/F5 |
| 5 | Session ledger (`_append_ledger_entry`, append-only, per-VP-per-session) | Records `outcome` (`administered`/`no_questionnaire_indicated`), scores, provenance | F4 (series input), F5 (Part A/section 6) |

`src/schemas/survey_result.py` is `extra="forbid"`, `is_diagnostic: Literal[False]` fixed at the
type level. A harness-only `--force-questionnaire`/`administration_mode` override (`ADR-033`
decision 6) exists for validation cells that need a scale F2's live selection did not pick; it is
loudly labeled in every artifact and never touches `f2.py`/`f3.py` production behavior.

---

## F4 — longitudinal state-change analysis (zero-LLM, deterministic)

| Order | Agent / module | Role | Handoff to |
|:--|:--|:--|:--|
| 1 | `src/f4.py` (**zero LLM calls anywhere**) | Consumes each persona's F1 (slot/CTRS/risk/crisis/probe/sentiment), F2 (`domain_candidates` + `ai_predicted_disease.similarity_score` trend — trend, never probability), and F3 (item/total/severity-band series) per-session ledger records across N sessions. Aggregation basis: first-vs-last delta + slope sign + band transitions (primary); per-pair comparisons (supplementary). `overall_direction` = N-dimension majority vote with worsened-priority, deliberately including `sentiment` beyond the as-built PRD §5 membership (`ADR-036`, disclosed, outcome-determinative for some series — DR-021 §7 wording table row 2) | `src/schemas/longitudinal.py` |
| 2 | `src/services/f4_report.py` (file I/O, split out so `f4.py` itself has zero `open(` calls) | Writes `temporal.json` | F5 (§9 longitudinal section) |
| 3 | `src/services/trend_plotter.py` | Slot-fill panel + similarity/domain trend charts | `temporal.json`-adjacent chart files, F5 |
| 4 | `continuous_test.py` **[harness]** — variable-cadence scheduling + F4 post-loop stage | Drives the multi-session chain (F1→F2→F3 per session, then one F4 pass); not wired into `OrchestratorAgent`'s production state machine | — |

F4 is entirely a deterministic post-processing pass over already-produced F1/F2/F3 artifacts —
"this battery demonstrates pipeline capability and F4's own arithmetic correctness, not F4's
sensitivity/specificity as a change-detection algorithm" (no non-scripted comparison condition has
ever been run, `REV-044` circularity ruling, DR-021 §9).

---

## F5 — clinical hand-off report (deterministic renderer + gated narrative option)

| Order | Agent / module | Role | Handoff to |
|:--|:--|:--|:--|
| 1 | `src/f5.py` (pure engine, **zero LLM calls, zero file-I/O**) | Assembles sections A0–A8 (static, latest-session) + B1–B5 (longitudinal, all-session/F4-derived) | `src/schemas/handoff_report.py` (`extra="forbid"`, `is_diagnostic: Literal[False]`) |
| 2 | `src/services/f5_report.py` | Exports md / PDF (`reportlab`, 2 SHA256-pinned embedded Noto Sans/Serif CJK KR TrueType fonts as of the `BUG-044`/`ADR-038` fix — the earlier non-embedded-CID-font PDFs are historically affected and not re-cited as legible) / FHIR R4 document Bundle (file-export-only, **structural self-checks only, never a `$validate` conformance claim**) | consumer (clinician / EHR import) |
| 3 | `continuous_test.py --f5-from-artifacts` **[harness]** replay CLI | Regenerates a report from already-produced F1–F4 artifacts, no new LLM/DB calls | — |
| optional, gated | Narrative agent v3 (`HandoffGeneratorAgent`, A8 section) | **Descoped this mission** (`ADR-037`) — feature flag hardcoded `False`, `f5.py:551-559` raises `ValueError` if `narrative_enabled=True`. Blocked on a v3 prompt redesign resolving the v2 prompt's mandatory-12-section-report behavior colliding with hard red line #1 (AI-predicted-disease isolation — a channel none of the existing HPI leak-tests were built to catch, `REV-046`), plus a fresh REV/CVR before any future wave | — (not exercised) |

F5's production path is the **deterministic renderer** above — distinct from `HandoffGeneratorAgent`
(10)'s LLM-authored 12-section report used inside F1's own per-turn pipeline; F5 synthesizes across
F1–F4, not a replacement for F1's own handoff step.

---

## Collaboration gaps / observations

Known seams across the five features, each pointing to its tracked issue:

- **Item-9 (F3 SI-positive) ↔ CTRS/crisis (F1) non-coupling.** No same-session reconciliation
  mechanism exists between F3's item-9-positive/`safety_referral` output and F1's
  `session_ctrs`/`crisis_triggered` signal — `EXP-023` showed 3/11 VP-001 item-9-positive sessions
  all with flat CTRS and no crisis flag, and nothing in the shipped output co-displays the two
  (`CVR-022` binding condition 2, DR-021 §8).
- **F2 `llm_only` fallback starves F3.** When F2's Stage-1 retrieval degrades to `mode="llm_only"`
  (silent on DB/embedding failure by design), `ai_predicted_disease.recommended_questionnaire`
  goes empty and F3 resolves to `no_questionnaire_indicated` — VP-003 hit this in 10/11 sessions of
  the `EXP-023` longitudinal arc, and the gaps are **inversely correlated with patient acuity**
  (the same risk-adjacent dialogue content that makes quantified tracking most valuable is what
  trips the F2 Stage-1 query-exclusion gate, `VAL-010`; `CVR-022` finding 3, DR-021 §8).
- **`VAL-016` silent-drop ambiguity in F5.** F5's A7 section renders "정보 없음 (권장 진료과 없음)"
  for a case where F2's LLM call actually produced 3 well-reasoned department candidates that were
  silently discarded by the already-open `BUG-031` (atomic Pydantic validation collapsing the whole
  `DomainInferenceLLMResponse` on any single nested-field error) — F5's rendering is faithful to its
  already-corrupted input, not a fabrication, but indistinguishable from "the model found nothing"
  without inspecting upstream artifacts (open, major, DR-022 §4).
- **Cross-feature over-endorsement propagation.** `ISS-F2V-028` (whole-instrument answer-LLM
  over-endorsement, PHQ-9/GAD-7 v1) and `ISS-F2V-029` (AUDIT-C v2 scale-ceiling instance) are F3
  answering-harness findings, but their inflated totals propagate untouched into F4's series
  aggregation and F5's rendered scores — neither downstream feature currently flags or discounts a
  score it consumes as potentially over-endorsed.
- **F1 crisis-path defects, not exercised by most batteries.** `BUG-009` (production hotline
  mismatch: `orchestrator.py` emits 1393/1577-0199, while `f1.py`/`EvidenceVerifierAgent` expect
  109/119) and `BUG-011` (turn-0 crisis early-return fails to substitute `CRISIS_RESPONSE`) and
  `VAL-001` (`_has_plan_disclosure()` clause-split misread) all remain **open** — every recent
  battery (`EXP-012`, `EXP-013`) explicitly checked and reported them "not exercised this batch,"
  which is not evidence of a fix.
- **F4's default ledger path has no scenario scoping.** `_run_f4_analysis` consumes a persona's
  entire session ledger with no scenario-pack filter — without the harness's `--out` workaround, a
  new F4 battery would silently blend historical sessions from unrelated prior runs into its series
  (Key Finding 1, DR-021 §6/§7 wording table row 8; a `--fresh-ledger`/scenario-scoped-filter fix
  is licensed but not yet built).
- **F2's `extra="forbid"` defense-in-depth gap.** The AI-predicted-disease isolation design's own
  layer-1 type invariant (`ConfigDict(extra="forbid")` on `SlotData`/`HandoffInput`/
  `ClinicalSlotOutput`) is not implemented — non-blocking (the 9 `tests/test_hpi_isolation.py`
  tests pass without it), but flagged against unrelated future accidental-kwarg bugs (DR-010 §3).
