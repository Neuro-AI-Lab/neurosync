# Task 1 Issue Tracker

> GitHub-style issue management. Each issue has a unique ID, status (open/closed), severity, and audit trail.

## Status Legend

| Status | Meaning |
|---|---|
| `OPEN` | Active issue, not yet resolved |
| `CLOSED` | Resolved and verified |
| `WONTFIX` | Acknowledged but intentionally not fixed |

## Severity Legend

| Severity | Meaning |
|---|---|
| `critical` | Blocks production. Safety risk or data loss. |
| `major` | Significant functionality broken. Workaround may exist. |
| `minor` | Cosmetic or non-blocking. Quality degradation. |
| `info` | Not a bug. Enhancement request or tracking item. |

---

## Summary Dashboard

| Status | Count |
|---|---|
| **OPEN** | 2 |
| **CLOSED** | 16 |
| **Total** | 18 |

---

## CLOSED Issues

### ISS-001: JSON echo loop in Patient LLM simulation — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | critical |
| **Found** | RPT-006 (2026-06-19) |
| **Fixed** | RPT-006 Run 3 (2026-06-19) |
| **Commit** | `8dec0ca` |
| **Component** | `tests/simulation/patient_llm.py`, `tests/simulation/runner.py` |

**Description:** Patient LLM echoed the clinical agent's JSON raw output instead of responding naturally. Dialogue degraded to a single repeated turn.

**Root cause:** Two bugs compounded:
1. `patient_llm.py`: Role mapping inverted — patient output stored as `user`, counselor input as `assistant`. LLM mimicked the counselor role.
2. `runner.py`: Dialogue agent's JSON response (`{"assistant_response": "..."}`) passed to Patient LLM without extracting the `assistant_response` field.

**Fix:**
1. Corrected role mapping: patient output = `assistant`, counselor input = `user`.
2. Added `_extract_natural_response()` in runner.py to strip JSON wrappers.

**Verification:** VP-001 turn 1-2 natural dialogue confirmed. VP-003 3-turn natural escalation to crisis.

---

### ISS-002: DialogueLLMResponse import scoping error — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Found** | RPT-007 (2026-06-19) |
| **Fixed** | RPT-007 (2026-06-19) |
| **Commit** | `ec65d41` |
| **Component** | `tests/simulation/runner.py` |

**Description:** `DialogueLLMResponse` was imported inside a `try` block, making it inaccessible in the `except` fallback branch. Simulation crashed at turn 6+ with `cannot access local variable 'DialogueLLMResponse'`.

**Root cause:** Lazy import (`from src.schemas.dialogue import DialogueLLMResponse`) placed after the `try:` line. Python scoping rules prevent access in the `except` clause if the `try` block fails before the import executes.

**Fix:** Moved import to the function's top-level scope before the `try/except`.

**Verification:** VP-001 runs to 10 turns without error. VP-003 runs to 3 turns (crisis).

---

### ISS-003: Korean conjugation keyword miss — "손목을 그었어요" — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | critical |
| **Found** | RPT-010 (2026-06-24) |
| **Fixed** | RPT-010 (2026-06-24) |
| **Commit** | `dab34d1` |
| **Component** | `src/agents/safety_classifier.py` |

**Description:** "손목을 그었어요" (I cut my wrist — past tense) was NOT detected by the keyword rule engine. The keyword list had "손목을 긋" (dictionary form) but Korean past tense changes "긋" → "그었". Space-stripping produced "손목을그었어요" which didn't match "손목을긋".

**Root cause:** Keyword dictionary only covered dictionary form (긋), not conjugated forms (그었, 긋고, 그을).

**Fix:** Added "손목을 그" and "손목을그" as additional keyword variants covering all conjugations starting with "그".

**Verification:** `test_safety_keyword_recall.py` — "손목을 그었어요" → critical. 13/13 critical keywords pass.

**Impact:** Before fix, a patient saying "손목을 그었어요" would NOT trigger crisis protocol. This is a **safety-critical miss** for self-harm detection.

---

### ISS-004: Word insertion keyword miss — "약을 많이 먹었어요" — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | critical |
| **Found** | RPT-010 (2026-06-24) |
| **Fixed** | RPT-010 (2026-06-24) |
| **Commit** | `dab34d1` |
| **Component** | `src/agents/safety_classifier.py` |

**Description:** "약을 많이 먹었어요" (I took a lot of pills) was NOT detected. The keyword "약을 먹" expects adjacent characters, but "많이" was inserted between "약을" and "먹었어요".

**Root cause:** Space-stripping produced "약을많이먹었어요" which doesn't contain substring "약을먹".

**Fix:** Added "약을 많이 먹" and "약을많이먹" as additional keyword variants.

**Verification:** `test_safety_keyword_recall.py` — "약을 많이 먹었어요" → critical. 13/13 critical keywords pass.

**Impact:** Before fix, a potential overdose report would be missed. **Safety-critical.**

---

### ISS-005: RiskLevel StrEnum alphabetical comparison — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Found** | RPT-010 (2026-06-24) |
| **Fixed** | RPT-010 (2026-06-24) |
| **Commit** | `dab34d1` |
| **Component** | `tests/test_safety_keyword_recall.py` |

**Description:** Test code used `level >= RiskLevel.high` to check if risk was at least "high". But `RiskLevel` is a `StrEnum`, so Python compares alphabetically: `"critical" < "high"` (c < h). This caused the recall rate test to report 32% instead of 100%.

**Root cause:** `StrEnum` comparison is lexicographic, not ordinal by severity. `critical` sorts before `high` alphabetically.

**Fix:** Created `_risk_ge()` helper using the existing `_RISK_ORDER` dict for ordinal comparison.

**Verification:** Recall rate test now correctly reports 100%.

**Note:** This bug was in TEST code only, not production safety_classifier. Production code uses `_RISK_ORDER` correctly since initial implementation.

---

### ISS-006: ClinicalSlot schema in wrong location — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | minor |
| **Found** | RPT-008 (2026-06-24) |
| **Fixed** | RPT-008 (2026-06-24) |
| **Commit** | `595cfc0` |
| **Component** | `src/agents/clinical_slot.py` → `src/schemas/clinical_slot.py` |

**Description:** `ClinicalSlotInput` and `ClinicalSlotOutput` were defined inline in `agents/clinical_slot.py`. Project convention requires all Pydantic schemas in `src/schemas/`.

**Root cause:** Initial implementation placed schemas inline for convenience.

**Fix:** Created `schemas/clinical_slot.py`, removed inline classes, updated imports in agent and runner.

**Verification:** All imports OK, 89/89 tests pass.

---

### ISS-007: Checklist dependency overstatement — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | minor |
| **Found** | RPT-008 (2026-06-24) |
| **Fixed** | RPT-008 (2026-06-24) |
| **Commit** | `595cfc0` |
| **Component** | `docs/ai/checklist_task1.md` |

**Description:** Three VER items and one DEV item were marked DONE but their listed dependencies were still TODO. The dependencies were overstated — the tests ran against the inline pipeline, which didn't require the Orchestrator.

**Root cause:** Checklist was authored with the future Orchestrator-based architecture in mind, but verification proceeded against the simpler inline pipeline.

**Fix:** Corrected dependency columns to reflect actual test scope.

**Verification:** Checklist audit confirmed all `[x]` items have met dependencies.

---

## OPEN Issues

### ISS-008: VP-001 CTRS 3 overfitting for mild cases — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | minor |
| **Opened** | RPT-007 (2026-06-19) |
| **Component** | Safety LLM classification |
| **Related** | T1-F1-DEV-009 (safety prompt fix — **done**), T1-F1-VER-005 (re-simulation — **pending**) |

**Description:** VP-001 (mild anxiety, expected CTRS 5) consistently gets CTRS 3 (medium/acute) from the LLM path. Expressions like "가슴이 답답해요", "불안해요" trigger medium even without any risk indicators.

**Status:** Safety prompt was updated in Sprint 2 (context-dependent rules added). **Re-simulation not yet run** to verify the fix.

**Next action:** Re-run VP-001 simulation with updated prompts → verify CTRS 4-5.

---

### ISS-009: Dialogue question repetition pattern — `OPEN`

| Field | Value |
|---|---|
| **Severity** | minor |
| **Opened** | RPT-007 (2026-06-19) |
| **Component** | Dialogue prompt + missing slot injection |
| **Related** | T1-F1-DEV-010 (dialogue prompt fix — **done**), T1-F1-VER-005 (re-simulation — **pending**) |

**Description:** VP-001 dialogue turns 3+ show repetitive question patterns. The AI keeps asking variations of the same question instead of progressing through different slot domains.

**Status:** Dialogue prompt was updated in Sprint 2 (repetition avoidance rules + question diversity guide). Chat route slot context now injects both filled AND missing slots. **Re-simulation not yet run.**

**Next action:** Re-run VP-001 simulation → verify question diversity across 10+ turns.

---

### ISS-010: Orchestrator state machine not implemented — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Opened** | Sprint 1 (2026-06-18) |
| **Fixed** | Sprint 6 (2026-06-18) |
| **Component** | `src/agents/orchestrator.py` |
| **Blocks** | T1-F1-DEV-006, T1-F3-DEV-005, T1-F5-DEV-005, T1-F0-VER-001, T1-F0-VER-002 |
| **Related** | T1-F0-DEV-001 |

**Description:** No Orchestrator agent exists. The full pipeline (SafetyGate → ContextRetrieval → Dialogue → SlotExtraction → HandoffReady) runs inline in `routes/chat.py` or manually in the simulation runner.

**Fix:** Implemented `OrchestratorAgent` with 11-state state machine (input_received → safety_gate → context_retrieval → dialogue_loop → slot_extraction → handoff_generation → evidence_verification → handoff_delivery + crisis_flow, completed, error). Rule-based routing (no LLM). Crisis CTRS 1-2 triggers immediate crisis_flow with level-specific messages. Slot coverage threshold (0.7) gates dialogue→extraction transition. Safety timeout defaults to CTRS 2 (safe-side). 23 unit tests pass.

**Verification:** 23/23 tests pass (state transitions, crisis flow, slot coverage gating, session serialization, audit trail).

---

### ISS-011: STT/OCR adapters not implemented — `OPEN`

| Field | Value |
|---|---|
| **Severity** | major |
| **Opened** | Sprint 1 (2026-06-18) |
| **Component** | `src/adapters/stt_adapter.py`, `src/adapters/ocr_adapter.py` (do not exist) |
| **Blocks** | T1-F1-DEV-003/004/007/008, T1-F1-VER-004 |
| **Related** | T1-F1-DEV-002 (InputNormalizer), T1-F1-DEV-003 (STT), T1-F1-DEV-004 (OCR) |

**Description:** Voice input (STT) and document upload (OCR) pipelines have no adapter implementations. Routes `/ai/stt/transcribe` and `/ai/ocr/parse` are not registered.

**Dependency:** STT requires SKT A.X API key (placeholder in .env). OCR requires Upstage Document Parse (key available).

**Workaround:** All testing uses text-only input.

**Next action:** Implement adapters when vendor contracts are finalized.

---

### ISS-012: VP-002/VP-004 revisit simulations not executed — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | info |
| **Opened** | Sprint 1 (2026-06-18) |
| **Component** | Simulation framework |
| **Blocks** | T1-F4-VER-001/002, T1-F5-VER-002/004 |
| **Related** | T1-F4-DEV-001 (TemporalSummaryAgent — not implemented) |

**Description:** VP-002 (revisit mild) and VP-004 (revisit severe) have persona files with full longitudinal data (prior handoff, medication records, prior scores) but have never been simulated. These require TemporalSummaryAgent to compare current vs. prior state.

**Workaround:** None. Revisit scenarios cannot be tested until F4 is implemented.

**Next action:** Implement TemporalSummaryAgent → run VP-002/VP-004 simulations.

---

### ISS-013: Medication keyword false positive for revisit patients — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Opened** | RPT-015 (2026-06-24) |
| **Component** | `src/agents/safety_classifier.py` — `_CRITICAL_KEYWORDS` |
| **Blocks** | All revisit patient simulations where medication is mentioned |

**Description:** VP-002 (mild revisit, taking Escitalopram 10mg) triggered crisis at turn 1. The Patient LLM's opening naturally mentioned current medication, which contains "약을 먹" — a keyword in `_CRITICAL_KEYWORDS` intended to detect overdose ("약을 많이 먹었어요").

**Root cause:** The keyword "약을 먹" is too broad. It matches both:
- "약을 먹었어요" (I took a lot of pills — overdose, CRITICAL) 
- "약을 먹고 있어요" (I'm taking medication — compliance, NOT dangerous)

The space-stripped variant "약을먹" also catches "약을먹고있어요".

**Impact:** Every revisit patient who mentions current medication → false critical → crisis protocol at turn 1 → blocks the entire dialogue.

**Proposed fix options:**
1. **Remove "약을 먹" from CRITICAL, keep "약을 많이 먹" only** — simplest, but may miss some overdose patterns
2. **Add negative context patterns** — if followed by "고 있" or "는 중" → downgrade to none
3. **Move "약을 먹" to MEDIUM** — still flags but doesn't trigger crisis

**Recommended:** Option 1 (remove "약을 먹", keep "약을 많이 먹" and "약물 과다" patterns). The LLM classifier will catch nuanced overdose expressions that simple keywords miss.

---

### ISS-016: Temporal overall direction too strict for "improved" — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Found** | RPT-020 longitudinal evaluation (2026-06-25) |
| **Fixed** | RPT-020 (2026-06-25) |
| **Component** | `src/agents/temporal_summary.py` |

**Description:** VP-002 (이준호, improving) returned `unchanged` overall direction despite 2 of 3 domains being `improved` (PHQ-9 improved, GAD-7 unchanged, CTRS improved). The voting logic required ALL domains to be `improved` for an overall `improved` result — `all([improved, unchanged, improved])` → False → unchanged.

**Root cause:** `all(d == improved for d in directions)` is too strict. A patient improving in 2/3 domains should be classified as improving.

**Fix:** Changed to majority vote: `improved_count > len(directions) / 2` → improved. Still preserves "worsened takes priority" safety rule.

**Impact:** Revisit patients with clinically significant improvement in most domains would be reported as "unchanged" — **underreporting improvement, may affect treatment continuation decisions**.

**Verification:** VP-002 now correctly returns `improved`. VP-004 (all worsened) unaffected. Mixed 1-improved-2-unchanged correctly returns `unchanged`.

---

### ISS-014: Temporal all-unknown → false "improved" direction — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Found** | RPT-020 stress testing (2026-06-25) |
| **Fixed** | RPT-020 (2026-06-25) |
| **Component** | `src/agents/temporal_summary.py` |

**Description:** When all domain trends (PHQ-9, GAD-7, CTRS) are `unknown` (no scale data provided), the overall direction was incorrectly reported as `improved` instead of `unknown`.

**Root cause:** Python's `all()` returns `True` for empty iterables. The voting logic filtered out `unknown` directions, then `all(d == improved for d in [])` → `True` → `improved`.

**Fix:** Added `if not directions: overall = unknown` check before the majority vote.

**Impact:** Revisit patients with no prior/current scale data would incorrectly show "improved" status in handoff reports. **Clinically misleading.**

---

### ISS-015: Floating-point sentiment polarity comparison — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | minor |
| **Found** | RPT-020 stress testing (2026-06-25) |
| **Fixed** | RPT-020 (2026-06-25) |
| **Component** | `src/agents/temporal_summary.py` |

**Description:** Sentiment polarity delta comparison `delta > 0.3` was affected by floating-point precision. `0.1 - (-0.2) = 0.30000000000000004 > 0.3` → incorrectly classified as `improved` instead of `unchanged`.

**Root cause:** IEEE 754 floating-point arithmetic. `0.1 + 0.2 ≠ 0.3` in binary.

**Fix:** Added `round(delta, 10)` to eliminate spurious precision bits before threshold comparison.

---

### ISS-017: InputNormalizer missing 4 HIGH-tier safety keywords — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Found** | RPT-022 audit (2026-06-30) |
| **Fixed** | RPT-022 (2026-06-30) |
| **Component** | `src/agents/input_normalizer.py` |

**Description:** `_SAFETY_EXPRESSIONS` frozenset was missing 4 HIGH-tier keywords from SafetyClassifier: "죽고" (suicidal), "해치고 싶" (harm to others), "때리고 싶" (violence), "죽이고 싶" (homicidal). These could be silently removed during STT normalization without triggering the safety preservation check.

**Fix:** Added all 4 missing keywords plus tier comments to `_SAFETY_EXPRESSIONS`.

**Impact:** Harm-to-others expressions and a suicidal variant could be lost during input normalization. **Safety-critical.**

---

### ISS-018: HandoffInput.SlotData missing 4 clinical fields — `CLOSED`

| Field | Value |
|---|---|
| **Severity** | major |
| **Found** | RPT-022 audit (2026-06-30) |
| **Fixed** | RPT-022 (2026-06-30) |
| **Component** | `src/schemas/handoff.py`, `src/agents/orchestrator.py` |

**Description:** `HandoffInput.SlotData` was missing 4 fields that exist in `ALL_SLOT_KEYS`: `history_of_present_illness`, `psychosocial_context`, `substance_use`, `energy`. The orchestrator's `_build_handoff_input()` silently dropped these collected slot values when building the handoff report input.

**Fix:** Added all 4 missing fields to `SlotData`. Updated `_build_handoff_input()` to populate them.

**Impact:** Handoff reports would be missing present illness history, psychosocial context, substance use, and energy level data even when collected. **Clinical data loss.**

---

## Issue Statistics

### By Severity

| Severity | Open | Closed | Total |
|---|---|---|---|
| critical | 0 | 3 | 3 |
| major | 1 | 3 | 4 |
| minor | 1 | 2 | 3 |
| info | 0 | 3 | 3 |
| **Total** | **2** | **11** | **13** |

### By Component

| Component | Open | Closed | Total |
|---|---|---|---|
| Safety classifier | 0 | 2 | 2 |
| Simulation framework | 1 | 2 | 3 |
| Dialogue/prompts | 2 | 0 | 2 |
| Orchestrator | 0 | 1 | 1 |
| STT/OCR | 1 | 0 | 1 |
| Schemas/conventions | 0 | 2 | 2 |
| Checklist process | 0 | 1 | 1 |

### Timeline

| Date | Opened | Closed | Cumulative Open |
|---|---|---|---|
| 2026-06-18 | 3 (ISS-010,011,012) | 0 | 3 |
| 2026-06-19 | 2 (ISS-001,002) + 2 (ISS-008,009) | 2 (ISS-001,002) | 5 |
| 2026-06-24 | 3 (ISS-003,004,005) + 2 (ISS-006,007) | 5 (ISS-003~007) | 5 |

### Resolution Time

| Issue | Opened | Closed | Resolution |
|---|---|---|---|
| ISS-001 | 2026-06-19 02:34 | 2026-06-19 02:59 | **25 min** |
| ISS-002 | 2026-06-19 13:08 | 2026-06-19 13:09 | **1 min** |
| ISS-003 | 2026-06-24 | 2026-06-24 | **same session** |
| ISS-004 | 2026-06-24 | 2026-06-24 | **same session** |
| ISS-005 | 2026-06-24 | 2026-06-24 | **same session** |
| ISS-006 | 2026-06-24 | 2026-06-24 | **same session** |
| ISS-007 | 2026-06-24 | 2026-06-24 | **same session** |
