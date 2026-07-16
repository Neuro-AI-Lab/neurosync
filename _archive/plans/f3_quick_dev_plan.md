# F3 quick development plan — F2-driven questionnaire administration

> **Status:** design v1 — pre-implementation. No code changes in this mission; this document is the deliverable of `PLAN-2026-W28-V` step 2, gating step 3 (writer PRD/checklist edit) and step 4 (critic pre-implementation review).
> **Source of record:** `discussion.md` `PLAN-2026-W28-V`, `ADR-031`. This file is a condensed, team-visible rendering for monitoring; `discussion.md` remains authoritative.
> **Created:** 2026-07-12 | **Author:** developer, on orchestrator dispatch.

## 0. Redefinition and scope note

**This F3 supersedes `PRD_task1_v2.md` §4 (line ~440's "기능 1-3 (F3)").** The original design was a stateful *survey planner*: PHQ-4 screening gates PHQ-9/GAD-7 subscale-triggered follow-on, drinking language triggers AUDIT-C, CTRS 1–2 stops the battery, and a documented "PHQ-9 item 9 → Safety re-evaluation trigger" (T1-F3-VER-004). That planner is **not this F3** — it already exists, live, as `OrchestratorAgent.plan_surveys` / `OrchestratorAgent.score_and_check_safety` (`src/agents/orchestrator.py:592,638`), wired into the production 11-state chat flow via `src/routes/chat.py`, and regression-covered by `tests/test_survey_safety_integration.py`. **That code path is untouched by this mission** — see §9.

The user's redefinition (`ADR-031`) is a **second, separate administration path**: F3 administers exactly the one questionnaire F2 already recommended (`ai_predicted_disease.recommended_questionnaire`, one scale, no planner logic, no subscale escalation, no safety re-evaluation wiring), the VP-simulator LLM answers by selecting scores in persona (mirroring F1's `patient_input_fn` pattern), and results land in the per-VP session ledger for future F5 consumption. It is architected the same way `f1.py`/`f2.py` are: a standalone module invocable by the `continuous_test.py` validation harness, not a route, not wired into `orchestrator.py`.

Writer's PRD edit (step 3) should state this coexistence explicitly rather than replacing §4's planner description — the two are parallel survey-administration mechanisms serving different call sites (live chat vs. offline/F2-driven).

## 1. Architecture — production vs. harness

```
PRODUCTION (src/f3.py — zero LLM calls, zero tests/ imports)
─────────────────────────────────────────────────────────────
  caller (future patient-UI route, or a CLI replay of pre-collected
  answers, or continuous_test.py's harness stage)
        │
        ▼
  src/f3.py :: administer_survey(scale_name, answer_fn, item_bank, patient_sex=...)
        │  - resolves item bank entry for scale_name (src/scoring/item_bank.py, NEW)
        │  - if entry.populated is False → returns outcome="item_bank_unpopulated",
        │    0 items administered, LOUD log warning — never improvises text
        │  - else: iterates entry.items in order, calls
        │    `response = await answer_fn(item)` per item (mirrors f1.py's
        │    `patient_input_fn: Callable[[str], Awaitable[str]]` seam,
        │    f1.py:889) — answer_fn is the ONLY variability point; f3.py
        │    has no knowledge of "llm" vs "expected" vs "real UI"
        │  - calls src.scoring.survey_scorer.score_survey() — REUSE,
        │    unmodified, no rescoring/reinterpretation
        ▼
  src/f3.py :: save_f3_result() — own saver, same naming convention as
  save_f1_result/save_f2_result: docs/ai/simulation_results/<vp_id>/
  <vp_id>_<ts>_survey.json (full artifact) + <vp_id>_<ts>_scale_scores.json
  (ScaleScore-shaped projection, see §5)

HARNESS (src/continuous_test.py — orchestrates, never scores)
─────────────────────────────────────────────────────────────
  F1 stage → F2 stage (ctx.domain_inference_path set, f2.py unchanged)
                │
                ▼
        NEW F3 stage (run_f3_stage, added to STAGE_REGISTRY)
          - reads ctx.domain_inference_path → ai_predicted_disease.
            recommended_questionnaire / recommendation_caveat / top candidate
          - recommended_questionnaire is None → StageResult "skip",
            detail "no-questionnaire-indicated" — calls src.f3 with 0 items
            (or skips the call entirely; both are "did not administer",
            recorded, never a forced scale pick)
          - else builds an answer_fn:
              --answer-mode llm (default)     → SurveyAnswerLLM (NEW,
                                                 tests/simulation/, K-EXAONE,
                                                 in-persona score selection)
              --answer-mode expected (fallback)→ expected_answer_fn (NEW,
                                                 tests/simulation/, reads the
                                                 persona's documented expected
                                                 per-item scores, zero LLM)
          - calls src.f3.administer_survey(...) with that answer_fn
          - appends ONE ledger record (§5) to the existing per-VP session
            ledger — ledger writing stays a HARNESS-ONLY responsibility
            (REV-022 standing rule); src/f3.py never touches the ledger file
```

Both `SurveyAnswerLLM` and `expected_answer_fn` live under `tests/simulation/` (or `src/continuous_test.py` itself for the thin orchestration glue) — never under `src/`. `src/f3.py` imports nothing from `tests/`; the harness imports `src.f3` (same direction `continuous_test.py` already imports `src.f1`/`src.f2`).

## 2. Item bank

### 2.1 Confirmed gap

Verbatim instrument item text and response anchors are **absent repo-wide** for all 5 scales (`SUPPORTED_SCALES` = PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C). Only partial *construct labels* exist, sourced from persona markdown:

| Scale | Source | Coverage |
|---|---|---|
| PHQ-9 | `docs/ai/personas/VP-001_first_visit_mild.md:81-95`, `VP-003_first_visit_severe.md:104-118`, `VP-012_first_visit_alcohol.md:101-115` | 9/9 abbreviated Korean construct labels + persona-specific expected scores (not generalizable item text) |
| AUDIT-C | `VP-012_first_visit_alcohol.md:101-122` | 3/3 abbreviated Korean construct labels + expected scores |
| GAD-7, PHQ-4, WHO-5 | — | 0 items; nothing beyond aggregate expected-total lines |

**Disclosure (`REV-036` minor 5):** these three are not a symmetric trio "awaiting user material" — `CLASSIFICATION_TO_SCALE` (`questionnaire_mapping.py:68-136`) maps zero classification keys to PHQ-4 or WHO-5, so both remain **permanently unreachable** by the F2→F3 trigger (§3) independent of item-bank population; only GAD-7 (via `"anxiety"`) is a live-reachable outcome once its item bank is populated.

Response anchors (e.g. PHQ-9's standard "전혀 아니다 / 며칠 동안 / 일주일 이상 / 거의 매일" 0–3 wording) are also absent — this project does not have a source for them any more than it has item stems. Treating the well-known English PHQ-9/GAD-7 anchor wording as "close enough" would itself be fabrication (translation + clinical-wording judgment, not something in this repo).

### 2.2 v0 item bank design (data module, not implemented this dispatch)

New file `src/scoring/item_bank.py`, structurally paired with `survey_scorer.py` (same `ScaleName` Literal import, no cross-import the other direction):

```python
@dataclass(frozen=True)
class ScaleItem:
    index: int                    # 1-based
    text_ko: str                  # construct label or verbatim item text
    response_min: int             # from survey_scorer's own validated ranges
    response_max: int
    response_anchors: dict[int, str] | None  # None in v0 — anchor wording absent repo-wide

@dataclass(frozen=True)
class ItemBankEntry:
    scale_name: ScaleName
    version: str                  # "v0"
    provenance: str               # "construct-labels-v0, persona-file-sourced, non-validated"
                                   # or "unpopulated-v0" for GAD-7/PHQ-4/WHO-5
    items: tuple[ScaleItem, ...]  # empty tuple = unpopulated
    populated: bool                # True iff len(items) == scale's expected item count
                                    # (9/7/4/5/3, matching survey_scorer's own len() checks)
                                    # AND provenance is non-empty AND text_ko non-empty per item

ITEM_BANK: dict[ScaleName, ItemBankEntry] = {...}  # registry, one entry per SUPPORTED_SCALES member

def get_item_bank(scale_name: ScaleName) -> ItemBankEntry: ...
def validate_item_bank_completeness() -> None:
    """Fail-fast module-level assertion (mirrors questionnaire_mapping.py's own
    pattern): ITEM_BANK's key set == SUPPORTED_SCALES exactly (registry
    completeness — a missing KEY is a bug; an unpopulated v0 entry is not)."""
```

**v0 content:** PHQ-9 and AUDIT-C entries get `items` populated from the persona-file construct labels above (`text_ko` = the abbreviated Korean label, e.g. `"1. 흥미/즐거움 감소"`; `response_min`/`response_max` = the ranges `survey_scorer.py` already validates, 0–3 for PHQ-9, 0–4 for AUDIT-C items — this is scoring-engine range metadata already in the repo, not new clinical text). `response_anchors = None` for every item in v0, deliberately — no anchor wording exists to populate it with, and the simulator (§7) is designed around a bare `[min, max]` integer ask precisely because anchor phrases aren't available. `populated = True` for these two, `provenance = "construct-labels-v0, persona-file-sourced, non-validated"`. GAD-7/PHQ-4/WHO-5 entries get `items = ()`, `populated = False`, `provenance = "unpopulated-v0"`.

### 2.3 The exact user question (blocking a v1 item bank, non-blocking for v0 dev/validation)

> Clinical instrument item text (PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C stems + response anchors) does not exist anywhere in this repo. To move past v0 (construct-labels-only, PHQ-9/AUDIT-C, non-validated), we need one of: (a) team-authored Korean-standard versions of the item text — drafted, then routed through `clinical-validator` content review before being marked v1/validated; or (b) the user supplies validated Korean item text/anchors directly (a licensed translation of the official instruments, or an existing internal source). Which do you want, or is v0 (construct labels, dev-phase only) sufficient for this quick-development mission's validation, with v1 deferred to the future F1–F5 total validation?

This mission proceeds on v0 regardless of the answer's timing — the answer only gates whether a v1 item bank gets built in this dispatch or a later one.

## 3. F2 → F3 trigger flow

Input: an F2 artifact (`<vp_id>_<ts>_domain_inference.json`, path from `ctx.domain_inference_path` in the harness, or an explicit `--domain-inference <path>` CLI arg for standalone `src/f3.py` runs) — read-only, never mutated.

```
recommended_questionnaire = artifact["ai_predicted_disease"]["recommended_questionnaire"]

if recommended_questionnaire is None:
    outcome = "no_questionnaire_indicated"     # 7 of 9 classifications, or 0 candidates —
    administered = 0 items                     # NEVER force-pick a SUPPORTED_SCALES member
elif not get_item_bank(recommended_questionnaire).populated:
    outcome = "item_bank_unpopulated"           # GAD-7 / PHQ-4 / WHO-5 in v0
    administered = 0 items                      # LOUD (warning log + artifact-recorded), never silent
    detail = "SKIPPED-item-bank-unpopulated"
else:
    outcome = "administered"
    administered = get_item_bank(recommended_questionnaire).items, iterated in order
```

`recommendation_caveat` and the top candidate's `disease`/`similarity_score` are carried through into the F3 artifact's provenance block (§4) regardless of outcome — this is passthrough of an already-schema-validated field, not new judgment.

**Cross-reference (`ADR-032`(3)):** `ai_predicted_disease.candidates[0]` — the field this trigger reads — is the same field `error.md`'s `VAL-014` (RAG candidate face-validity — poor cross-VP differentiation) flags open; this trigger, and §8's selection-fidelity check, adjudicate only whether F3 correctly relays F2's output AS-GIVEN, never `VAL-014` itself.

## 4. F3 production artifact schema

New `<vp_id>_<ts>_survey.json`, written by `save_f3_result()` alongside a `<vp_id>_<ts>_survey.md` report (mirrors `f2.py`'s `_build_report`/`save_f2_result` pair). New schema module `src/schemas/survey_result.py`, `extra="forbid"`, `is_diagnostic: Literal[False]` fixed at the type level (same discipline as `AIPredictedDiseaseOutput`):

```json
{
  "vp_id": "VP-001", "session_id": "...", "timestamp": "2026-07-12T...",
  "outcome": "administered | no_questionnaire_indicated | item_bank_unpopulated",
  "scale_name": "PHQ-9 | null",
  "item_bank_version": "v0 | null", "item_bank_provenance": "... | null",
  "responses": [1, 1, 2, 1, 1, 0, 1, 0, 0],
  "score_result": {
    "total_score": 7, "max_score": 27, "severity": "mild",
    "critical_item_positive": false, "critical_items": [],
    "subscale_scores": {}, "interpretation": "PHQ-9 7점: mild",
    "recommended_action": "watchful_waiting"
  },
  "recommendation_provenance": {
    "domain_inference_path": "docs/ai/simulation_results/VP-001/VP-001_..._domain_inference.json",
    "top_candidate_disease": "...", "top_candidate_similarity_score": 0.xx,
    "recommendation_caveat": "... | null"
  },
  "answer_mode": "llm | expected | null",
  "is_diagnostic": false,
  "disclaimer": "<constant string, non-diagnostic framing, same discipline as AI_PREDICTED_DISEASE_DISCLAIMER_KO>"
}
```

`score_result` is `ScoreResult`'s own fields verbatim (`dataclasses.asdict`), never recomputed or reinterpreted by this schema layer — same "never invented at the schema layer" discipline `ai_predicted_disease.py` documents for its own derived fields.

## 5. Ledger record schema (harness) — F5 consumption

Per constraint, the harness's F3 stage adds an `"f3"` sub-object to the **existing** per-session ledger entry (`<OUTPUT_DIR>/<persona_id>/<persona_id>_session_ledger.json`, `_append_ledger_entry`) — sibling to the current `conversation_path`/`domain_inference_path` keys, not a new file. `session_index`/`simulated_date`/`written_at` already exist at the entry's top level and are not duplicated inside `"f3"`.

```json
"f3": {
  "outcome": "administered", "scale_name": "PHQ-9",
  "item_bank_version": "v0", "item_bank_provenance": "construct-labels-v0, persona-file-sourced, non-validated",
  "responses": [1, 1, 2, 1, 1, 0, 1, 0, 0],
  "total_score": 7, "max_score": 27, "severity": "mild",
  "subscale_scores": {}, "safety_referral": false,
  "answer_mode": "llm",
  "recommendation_provenance": {
    "domain_inference_path": "...", "top_candidate_disease": "...",
    "recommendation_caveat": null
  },
  "survey_artifact_path": "docs/ai/simulation_results/VP-001/VP-001_..._survey.json",
  "scale_scores_path": "docs/ai/simulation_results/VP-001/VP-001_..._scale_scores.json"
}
```

`safety_referral` = `score_result.critical_item_positive` (PHQ-9 Q9 ≥ 1 only; every other scale's field is always `false`) — recorded prominently as its own top-level boolean inside `"f3"` precisely so an F5 report generator can surface it without parsing `interpretation` prose. This is a **record**, not a trigger: nothing here calls `OrchestratorAgent.score_and_check_safety` or any safety route.

**Rationale (F5 consumption):** F5 (not built) will need, per VP per session: which scale was recommended and why (provenance), what was actually asked (item bank version — so F5 can flag "v0, non-validated" in its own output rather than presenting a score with false authority), what was answered, the deterministic total/severity, and the safety flag — all without re-deriving anything, matching this repo's "compute once, pass structured data forward" convention (`ScaleScore` already exists for exactly this purpose one hop earlier, F3→F2).

### 5.1 Mapping down to `handoff.ScaleScore`

`handoff.ScaleScore` (`src/schemas/handoff.py:36-49`) is intentionally smaller: `scale_name: str`, `total_score: int`, `severity: str = ""`. `save_f3_result()` derives a **second** file, `<vp_id>_<ts>_scale_scores.json` — a bare JSON list, exactly the shape `f2.py::_load_scale_scores` already parses (`[ScaleScore.model_validate(d) for d in raw]`, `f2.py:152-163`):

```json
[{"scale_name": "PHQ-9", "total_score": 7, "severity": "mild"}]
```

Only written when `outcome == "administered"` (the other two outcomes write nothing here; `_load_scale_scores` already treats a missing/absent path as "no F3 scores, skip" — no new handling needed on the F2 side). Writing this projection from `src/f3.py` itself (not the harness) means any future real caller of `src/f3.py` — not only `continuous_test.py` — gets the F2-seam file for free, consistent with `validation_plan_f1f2_continuous.md`'s "product design precedes validation design" invariant.

## 6. `continuous_test.py` integration

1. `STAGE_REGISTRY`: replace the `Stage("F3", False, None, ...)` stub with `Stage("F3", True, run_f3_stage)`, positioned after F2, before F4's stub. `run_f3_stage(ctx)` follows §3's flow, reads `ctx.domain_inference_path`, writes two new `ChainContext` fields (`ctx.f3_survey_path`, `ctx.f3_scale_scores_path`).
2. `ChainContext` gains: `f3_survey_path: Path | None = None`, `f3_scale_scores_path: Path | None = None`, `answer_mode: str = "llm"` (CLI `--answer-mode {llm,expected}`, default `llm`).
3. `run_multi_session_chain`: insert the F3 stage call between the existing `f2_result` append and the `ledger_entry` dict construction (`continuous_test.py:440-467`); add the `"f3"` sub-object (§5) to `ledger_entry` before `_append_ledger_entry(ledger_path, ledger_entry)`.
4. **Session chaining gap, flagged not fixed:** today `f2_ctx.scale_scores_path` inside `run_multi_session_chain`'s loop is the single static `--scale-scores` CLI value for every session — session N's own F3 output never feeds session N+1's F2 call automatically. Closing this needs the loop to prefer `prev_session_f3_scale_scores_path` (set after session N's F3 stage) over the static CLI arg from session 2 onward. This is a small, precisely-scoped harness-side change item for the implementation dispatch (`PLAN-2026-W28-V` step 5) — noted here so it isn't silently assumed to already work.
5. **Single-session ledger gap, flagged not fixed:** `run_chain` (the `--sessions 1` default path) currently writes **no** ledger entry at all — only `run_multi_session_chain` does. Since the validation design (§8) needs ledger records for VP-003 and VP-012 (both single-session), `run_chain` needs an equivalent `_append_ledger_entry` call after the chain completes (`session_index=1`, mirroring `run_multi_session_chain`'s entry shape, `is_revisit=False`). Also scoped to step 5, harness-side only.

## 7. Simulator score-selection design

### 7.1 LLM mode (default) — `SurveyAnswerLLM`, new sibling to `patient_llm.py`

Lives in `tests/simulation/survey_answer_llm.py` (harness/tests territory, never `src/`). Reuses `load_persona`/`PatientPersona` (persona Section 6 as system prompt, same K-EXAONE client construction as `PatientLLM` — **vendor correction: PatientLLM/this new class run on K-EXAONE via `friendli.ai`, `LG_K_EXAONE_API_KEY`/`LG_K_EXAONE_ENDPOINT_ID`, temperature 0.7** — not Upstage; `UPSTAGE_API_KEY` is used elsewhere for embeddings only). A **new, separate** client instance per survey administration (no shared `_history` with an in-progress F1 conversation — item Q&A is a distinct interaction, not a dialogue turn).

Per item: one-shot prompt = persona system prompt + `"다음 항목에 대해 지난 2주간 당신의 상태를 가장 잘 나타내는 숫자를 [min]-[max] 사이에서 하나만 답하세요: {item.text_ko}"` (bare integer ask — no anchor phrases offered, per §2.2). Response parsing: strict first-standalone-integer regex; out-of-range or unparseable → **one** re-prompt ("숫자 하나만, {min}-{max} 범위 내로만 답하세요"); still failing → clamp to the nearest valid bound **and log a WARNING** (never silently default to 0 — mirrors this codebase's "honest on failure" convention, e.g. `f2.py`'s explicit 0-candidate reason logging). The clamp/retry event is recorded on the F3 artifact (`answer_mode` stays `"llm"`; a per-item `clamped: bool` flag is a reasonable schema addition for the implementation step, not designed further here).

### 7.2 Expected mode (fallback) — `expected_answer_fn`

Deterministic, zero LLM. Also `tests/simulation/`, reads the persona markdown's own "### {SCALE} 예상 항목별 점수" table (regex-based, same extraction idiom `patient_llm.py` already uses for Section 6/5) and returns the documented expected score for the matching item index. Falls back loudly (raises, does not guess) if a persona has no such table for the requested scale — this is the intended behavior for any VP without a documented item-level table (today: only VP-001/VP-003/VP-012 have PHQ-9 tables; only VP-012 has an AUDIT-C table). This mode is the pre-registered fallback if the user declines LLM administration over unvalidated construct labels (§2.3) — it needs no item bank *content* beyond what's already in personas, only the item bank's `index`/`response_min`/`response_max` metadata to validate the parsed value lands in range.

## 8. Validation design

Live `F1 → F2 → F3` via `continuous_test.py`, budget 8 session-level cells (within the ~10–15 target, leaving headroom for a retry).

| # | Cell | Expected scale (design intent, not hard-pinned) | Purpose |
|---|---|---|---|
| 1 | VP-001, session 1 | PHQ-9 (mood) — *or* GAD-7 if F2's top candidate ranks anxiety-classified this run (VP-001's presentation is mixed anxiety/mood) | Base cell: correct scale selection, full PHQ-9 administration (or the GAD-7-unpopulated-skip path, live) |
| 2 | VP-001, session 2 (revisit, `--sessions 2`) | Same as session 1 | Proves **two distinct per-session ledger `"f3"` records** for one VP |
| 3 | VP-003, session 1 | PHQ-9 (mood; Q9 expected = 2, positive) | Crisis-adjacent: `safety_referral` recorded prominently; HPI isolation holds; no dialogue/safety prompt touched |
| 4 | VP-012, session 1 | AUDIT-C (substance is VP-012's designed primary diagnosis, so the top candidate is expected to classify as `substance`) | AUDIT-C sex-based threshold (VP-012 male → threshold 4); PHQ-9 comorbid score is documented but **not** administered (F2 recommends only the top-ranked candidate's scale) |
| 5–8 | Repeat 1–4 in `--answer-mode expected` | same | Cross-check LLM-mode totals against the deterministic expected-mode path; confirms both `answer_fn` implementations against the same persona tables |

**GAD-7 cell: explicitly `SKIPPED-awaiting-user-material`.** No dedicated live cell is scheduled for GAD-7 — the item bank has 0 populated items in v0 (§2.1) and no VP is designed to reliably surface GAD-7 as F2's *top*-ranked recommendation. If cell 1 (VP-001) organically surfaces GAD-7 as the top candidate on a given run, that instance becomes an incidental, live proof of the `item_bank_unpopulated` skip path — checked, not separately budgeted.

**Precedent, informational (`REV-036` minor 6):** `result.md`'s live W7b table shows 6/6 populated-mode rows across VP-001/002/003(rep2)/004(rep1) resolving `recommended_questionnaire=PHQ-9`, 0/6 to GAD-7, even where `domain_candidates`' coarser top domain was `anxiety` — cells 1/2/5/6's PHQ-9-vs-GAD-7 non-determinism is empirically low-risk for landing on the intended `administered` path, not merely a theoretical toss-up.

### Checks and pass criteria (apply per administered cell unless noted)

| Check | Pass criterion |
|---|---|
| Correct questionnaire selected | `recommended_questionnaire` in the F3 artifact's `recommendation_provenance` matches `CLASSIFICATION_TO_SCALE[top_candidate.classification]` for whatever F2 actually top-ranked (not a hardcoded VP→scale assumption) |
| All populated items administered | `len(responses) == len(get_item_bank(scale).items)` (9/PHQ-9, 3/AUDIT-C); 0 for the two skip outcomes |
| Score range validity | every response ∈ `[item.response_min, item.response_max]`; `score_survey()` raises nothing (a raise is a fail, not a warn) |
| Code-computed totals correct | artifact `score_result.total_score == sum(responses)`, hand-verified against the persona's documented per-item table for `expected`-mode cells; for `llm`-mode cells, verified equal to `sum(responses)` from the artifact itself (LLM-mode responses are not expected to match the persona table exactly — only in-range and internally consistent) |
| Severity band correct | matches `survey_scorer.py`'s own published bands (PHQ-9 5/10/15/20; AUDIT-C threshold 4 male/unknown, 3 female) applied to the artifact's own total — recomputed independently by the validator from the raw `responses`, not trusted from `score_result` alone |
| Ledger record complete | `"f3"` sub-object present with all §5 fields non-null for `outcome="administered"`; present with `outcome` + null score fields for the two skip outcomes (never absent) |
| Simulator answers persona-consistent | `llm`-mode responses fall within ±1 of the persona's documented expected per-item score for VP-001/VP-003/VP-012's PHQ-9 items and VP-012's AUDIT-C items (the only VPs/scales with documented anchors); a wider gap is flagged, not auto-failed (LLM sampling variance) |
| Clinical-note/HPI isolation holds | `grep` the F3 artifact and the same-session F2/F1 artifacts confirms no F3 field value appears inside `slots.history_of_present_illness`, `slots.chief_complaint`, or any other narrative `SlotData` string field (`src/schemas/handoff.py:11-32`) |
| No safety-wiring touch | `git diff` for the mission shows zero changes to `src/agents/orchestrator.py`, `src/routes/chat.py`, `docs/ai/prompts/safety/**`, `docs/ai/prompts/dialogue/**` |

## 9. Out of scope (this dispatch and this plan)

- **Safety re-evaluation wiring.** `OrchestratorAgent.plan_surveys`/`score_and_check_safety` (`src/agents/orchestrator.py:592,638`), `src/routes/chat.py`, `tests/test_survey_safety_integration.py` — the live chat flow's existing, separate survey mechanism (§0). F3's `safety_referral` field is a **record**, never a trigger. **Forward-looking note (`REV-036` minor 7):** this record-only design is correctly scoped for this harness-only, offline-executed DEV mission (F1's live SafetyClassifier already owns real-time crisis handling; F3 runs post-hoc) — but safety wiring is a **prerequisite**, not merely a deferred nicety, before any future live-patient-facing route reuses this same "record only" pattern.
- **GAD-7/PHQ-4/WHO-5 item content.** Blocked on the user question in §2.3; v0 ships unpopulated for these three by design.
- **PRD_task1_v2.md / checklist_task1.md / workflow_checklist edits.** Writer's deliverable, `PLAN-2026-W28-V` step 3.
- **Any `src/`/`tests/` code change.** This document is design only; implementation is step 5.
- **Running anything LLM-backed.** No pipeline calls made producing this plan.
- **F4/F5.** F3's artifact/ledger schema is designed *for* F5 consumption (§5) but F5 itself is not touched, built, or stubbed here.
- **Item bank v1 (validated instrument text).** Pending the user's answer in §2.3.
- **`patient_sex` sourcing for AUDIT-C.** No dialogue slot carries patient sex today (only `ocr.py`'s `patient_gender`, populated solely from OCR document summaries, `f1.py:355,2021`). VP-012 is documented male, so `threshold=4` applies whether `patient_sex` resolves to `"male"` or defaults to `"unknown"` — this dispatch's validation cells are unaffected, but a future female-presenting VP would need a real sex source wired into `src/f3.py`'s caller. Flagged, not designed further here.

---

**Linked:** `PLAN-2026-W28-V`, `ADR-031`. Reviewed repo artifacts (all read this session, no fabricated paths/line numbers): `src/rag/questionnaire_mapping.py`, `src/schemas/ai_predicted_disease.py`, `src/scoring/survey_scorer.py`, `src/schemas/handoff.py`, `src/schemas/survey.py`, `src/routes/survey.py`, `src/f2.py` (lines 152-163, 540-583, 900-968), `src/f1.py` (line 889, 1777-1782), `src/continuous_test.py` (full), `tests/simulation/patient_llm.py`, `docs/ai/personas/VP-001_first_visit_mild.md`, `VP-003_first_visit_severe.md`, `VP-012_first_visit_alcohol.md`, `docs/ai/PRD_task1_v2.md` (§4), `src/agents/orchestrator.py` (lines 592, 638), `tests/test_survey_safety_integration.py`.
