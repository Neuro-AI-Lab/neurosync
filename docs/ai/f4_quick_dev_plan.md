# F4 quick development plan — longitudinal (between-session) state-change analysis

> **Status:** design v1 — pre-implementation. No code changes in this mission; this document is
> `PLAN-2026-W29-D` step 1's deliverable, gating step 2 (critic REV), step 3 (clinical-validator
> CVR), step 4 (ADR dispositioning), then step 5 (implementation).
> **Source of record:** `discussion.md` `PLAN-2026-W29-D`. This file is a condensed, team-visible
> rendering for monitoring, mirroring `docs/ai/f3_quick_dev_plan.md`'s structural pattern.
> **Created:** 2026-07-13 | **Author:** developer, on orchestrator dispatch.

---

## 0. Reading map / verification note

Every file-path and field-path citation below was read directly this session (PRD §5/§2.6/§9.3-
9.5/§1.1/§2.3; agent specs `08_temporal_retriever.md`/`09_temporal_summary.md`/
`13_sentiment_analyzer.md`; `apps/ai-server/src/continuous_test.py` full; `src/f1.py` lines
160-260, 1020-1100, 2170-2370; `src/f3.py` full; `src/agents/temporal_summary.py` full;
`src/schemas/temporal.py` full; `src/agents/sentiment_analyzer.py` full;
`src/services/trend_plotter.py` full; `src/schemas/ai_predicted_disease.py` full;
`src/schemas/survey_result.py` lines 1-140; `src/scoring/item_bank.py` lines 1-180;
`src/scoring/survey_scorer.py` lines 36-65; `src/rag/questionnaire_mapping.py` lines 60-136;
`tests/simulation/patient_llm.py` full; `docs/ai/personas/VP-001_first_visit_mild.md`,
`VP-003_first_visit_severe.md` full; `docs/ai/checklist_task1.md` L105-116/L187-201;
`docs/ai/f3_quick_dev_plan.md` full) — plus **three real, on-disk artifacts** were opened and
their exact keys/values used as ground truth: `VP-001_20260712_204038_conversation.json`,
`VP-001_20260712_204048_domain_inference.json`, `VP-001_20260712_204054_survey.json`, and the
three existing per-VP ledgers (`VP-001`/`VP-003`/`VP-012`). Any claim below not traceable to one of
these is marked `[DESIGN INTENT]` (this mission's own proposal, not yet code) or `UNVERIFIED`.

**Correction to a stale PRD row, verified against code+data, not asserted from the PRD:** PRD
§1.1's agent-mapping table row for `SentimentAnalyzer` still reads "F1(미연동)" (not wired into
F1). This is stale — `src/f1.py:1223,1664` invoke the Mode A per-turn helper
(`_analyze_utterance_sentiment`, which itself calls `SentimentAnalyzerAgent.run()` at
`f1.py:606`) on every patient turn, and `f1.py:1054` invokes the Mode B session-finalize helper
(`_analyze_session_sentiment`, which calls `SentimentAnalyzerAgent.run()` at `f1.py:662`) once at
normal session end. The real
`VP-001_20260712_204038_conversation.json` artifact's `session_sentiment` field is fully populated
(11 turns, `polarity_trajectory`, `dominant_emotions`, `signal_strength`). This design relies on
the verified code+data state, not the PRD table cell; fixing that PRD cell is writer's job, out of
this document's scope, flagged for completeness.

---

## 1. Purpose and scope

### 1.1 As-built F4 (PRD §5) vs this mission

| | As-built (`src/agents/temporal_summary.py`, `POST /ai/temporal/summarize`) | This mission (`src/f4.py`, new) |
|---|---|---|
| Shape | **Pairwise** — one prior session vs one current session, single call | **N-session series** (2 ≤ N, target ≥10) per VP |
| Input source | Caller-assembled `TemporalSummaryInput` (scalars: `current_scales`, `prior_scales`, `current_ctrs`, `prior_ctrs`, `current/prior_sentiment_polarity`, dates) — `src/schemas/temporal.py:41-51` | Explicit `LongitudinalSeriesInput` (§4) built by a harness from the F1/F2/F3 artifact chain |
| Domains covered | PHQ-9, GAD-7, CTRS, sentiment polarity only (`temporal_summary.py:44-66`) | Adds F1 slot-fill evolution, F2 `domain_candidates`/`ai_predicted_disease` similarity trend, F3 per-item/subscale/severity-band transitions, crisis/probe recurrence |
| Caller today | Nothing in F1/F2/F3 production pipelines — only the standalone route (PRD verified fact) | New: `continuous_test.py` F4 stage (harness) |
| Verification status (PRD §5) | "합성 입력 기반 검증 통과... 실제 F1 세션 연쇄 데이터로는 미검증" | This mission's own §7 (약식) — still not a certification |

**What this quick-dev covers:** design + a small validation harness run (2 VPs × ≥10 chained
sessions × ≤6 months) that exercises the NEW `src/f4.py` engine against **real**, not synthetic,
F1→F2→F3 chain output, plus graphs/tables/JSON artifacts and pre-registerable machine checks.

**What this quick-dev does NOT cover (explicit exclusions):**
- Any change to `docs/ai/prompts/dialogue/**` or `docs/ai/prompts/safety/**` (prompt pins untouched
  — binding, `PLAN-2026-W29-D`).
- Reactivating `08_temporal_retriever` (semantic RAG retrieval for dialogue/handoff context) — see
  §4.2's disposition row.
- Wiring F4 into `orchestrator.py`/any live route. `src/f4.py` is architected exactly like
  `f1.py`/`f2.py`/`f3.py`: a standalone module callable by a validation harness, not a route.
- Clinical validation of the arc scripts or of F2's candidate quality (`VAL-014`, open, is
  inherited unresolved — see §5's wording laws and §7's "not claimed" list).
- A full 4-VP battery — 2 VPs only, per the user's explicit "quick" framing and this being a
  design+약식-verification mission, not the full Phase-2 G-A/G-D-F2 program.
- Any `pandas`/`plotly`/`seaborn` dependency — none of these are installed
  (`apps/ai-server/.venv`, verified this session: `pandas`/`plotly` both raise
  `ModuleNotFoundError`; `matplotlib==3.11.0`, `numpy==2.5.1` both import cleanly). All numeric
  work uses stdlib + numpy; all plotting uses matplotlib (`Agg` backend, precedent:
  `trend_plotter.py:153-154`).

---

## 2. Longitudinal scenario design protocol

### 2.1 Arc archetype library

| Archetype | Clinical shape | Tests in F4 |
|---|---|---|
| `gradual_improvement` | Monotonic-ish decline in symptom burden with treatment/self-management engagement | `improved` direction, band de-escalation, slot-fill growth |
| `improvement_with_plateau` | Improvement, a transient stressor-driven wobble mid-arc, then improvement resumes | Non-monotonic trend robustness — F4 must not mis-fire "worsened" on a single-session wobble that reverses |
| `relapse_after_partial_improvement` | Partial improvement, then a scripted stressor triggers reversal back toward (or past) baseline severity, then slow partial recovery | `worsened`-priority override, crisis recurrence, `relapse_signals` |
| `crisis_episode` (not scripted this mission) | Acute single-session crisis spike in an otherwise stable arc | Reserved for a future wider battery — not one of the 2 chosen VPs this mission (see §2.2 justification) |
| `worsening_sustained` (not scripted this mission) | Sustained monotonic decline, no recovery | Reserved for a future wider battery |

Only the first two archetypes' clinical logic is exercised directly by the 2 chosen VPs
(`gradual_improvement` with one built-in plateau = VP-001; `relapse_after_partial_improvement` =
VP-003). `crisis_episode`/`worsening_sustained` are named for completeness of the taxonomy the user
asked for ("종단적 변화 분석을 위한 상태 종류들... 다방면으로") but are out of this mission's
2-VP budget — flagged, not silently dropped.

### 2.2 VP selection and justification

**Chosen: VP-001 (improvement-dominant) and VP-003 (deterioration/crisis-relapse).**

| VP | Baseline (persona file) | Why chosen | Why not the alternative |
|---|---|---|---|
| VP-001 | First-visit, mild, CTRS target 5, no SI at any point, strong protective factors (`docs/ai/personas/VP-001_first_visit_mild.md:54-70`), PHQ-9 expected ~7 | Richest existing real precedent (9-entry ledger, `docs/ai/simulation_results/VP-001/VP-001_session_ledger.json`, verified this session) — lowest execution risk for a first F4 real-data run; clean improvement narrative with a natural in-story plateau (new work project) that exercises non-monotonic trend handling without inventing implausible content | — |
| VP-003 | First-visit, severe/crisis-adjacent, CTRS target 2-3, **passive SI daily** (`chief_complaint`/HPI persona text itself, `VP-003_first_visit_severe.md:44-56`), PHQ-9 expected ~23, Q9 positive | Maximal test of the safety-relevant taxonomy dims (probe events, risk floor, crisis recurrence, safety_referral flips) — the highest-value stress test of F4's `worsened`-priority rule and `relapse_signals`; persona's OWN documented detail ("실업급여... 2개월 후 종료 예정", `VP-003_first_visit_severe.md:75`) supplies a clinically-real, non-invented relapse trigger | VP-012 (alcohol/AUDIT-C) was considered — rejected for this slot because its primary scale (AUDIT-C) is already the designated substance-arc coverage cell in `f3_quick_dev_plan.md` §8 cell 4, and VP-003 gives higher marginal test value for F4's crisis/safety dimensions specifically, which is the taxonomy area the user's directive most explicitly names ("risk crisis 결과") |

Coverage: together the 2 VPs span both ends of PHQ-9 severity (mild↔severe), both crisis states
(never-crisis vs. crisis-adjacent-with-scripted-relapse), and both improvement and
deterioration/relapse directions — satisfying "one improvement-dominant, one
deterioration/crisis-or-relapse" with justified, non-arbitrary picks.

### 2.3 Per-session date/time schedule (11 sessions, ~6 months, both VPs)

**Cadence rationale:** weekly during an acute-engagement phase (early symptom volatility, most
valuable check-in frequency), tapering to biweekly during response-consolidation, tapering to
monthly during maintenance — mirrors standard outpatient follow-up tapering and gives 11 sessions
(≥10, satisfies the user's floor) spanning day 0 to day 183 (~6.0 months, satisfies the "최대 6개월"
ceiling without exceeding it).

| Session | Day offset | Phase | Cadence since prior |
|---|---|---|---|
| 1 | 0 | Intake | — |
| 2 | 7 | Acute engagement | weekly |
| 3 | 14 | Acute engagement | weekly |
| 4 | 21 | Acute engagement | weekly |
| 5 | 35 | Response consolidation | biweekly |
| 6 | 49 | Response consolidation | biweekly |
| 7 | 63 | Response consolidation | biweekly |
| 8 | 91 (~3mo) | Maintenance | monthly |
| 9 | 122 (~4mo) | Maintenance | monthly |
| 10 | 152 (~5mo) | Maintenance | monthly |
| 11 | 183 (~6mo) | Maintenance | monthly |

Base date `[DESIGN INTENT]`: session 1 = the harness run date at execution time (matches
`continuous_test.py`'s existing default, `run_multi_session_chain`'s `resolved_base_date =
base_date or datetime.now().date()`, `continuous_test.py:687`) — not hardcoded into the scenario
pack itself, so the arc table's `day_offset` column (not absolute dates) is the portable,
implementation-facing artifact.

**Harness gap this schedule exposes (flagged, addressed in §9 wave plan):**
`run_multi_session_chain`'s `simulated_date` formula is presently **uniform-interval only**
(`simulated_date = resolved_base_date + timedelta(days=session_interval_days * (session_index -
1))`, `continuous_test.py:690-693`) — it cannot express the weekly→biweekly→monthly taper above.
Implementation needs a new parameter (e.g. `session_offsets_days: list[int] | None`) that, when
supplied, overrides the uniform formula with an explicit per-session offset list. Harness-only
change, zero production impact — scoped in §9.

### 2.4 Per-VP arc content (the actual 11-session scripts)

Both VPs share the day-offset/phase schedule (§2.3). Content below is **design intent**, not a
hard pin (same convention `f3_quick_dev_plan.md` §8 already uses for its own expected-scale
column) — the live patient-LLM's actual utterances, and everything downstream of them
(Safety-classified `session_ctrs`, F3's scored total), will vary; §7.4's acceptance criteria are
written to tolerate that variance. `symptom_targets.PHQ-9`/`CTRS` below are the row's own
`symptom_targets` dict values (§2.5 schema) rendered as a single column for readability; the full
`inter_session_events_ko`/`reveal_guidance_ko` content is one bullet each here (implementation
expands each into the full Korean guideline text, §2.5's template).

**VP-001 — `arc_mode="improvement_plateau"`** (grounded in `VP-001_first_visit_mild.md`'s own
documented trigger — a work deadline, §2.2 — and its documented protective factors; the plateau at
S5 uses a NEW-but-plausible project assignment, never contradicting the persona's stable
IT/UX-designer occupation):

**S1 target correction (ADR-036 item 6 / CVR-020 Condition 2):** S1's PHQ-9 target below is
`~7` — the persona's own documented mild baseline (`VP-001_first_visit_mild.md` §3, item-by-item
sum = 7) — not the `~13` (moderate band) the original draft used, which CVR-020 Finding 2 traced to
`EXP-019`'s own previously-flagged over-triage artifact (CVR-015 Finding 2), not the persona's
canonical value. The rest of the row's targets are re-anchored to taper from this mild baseline.
Separately, and orthogonally: OBSERVED F3 totals in the eventual live battery may still ride the
project's known whole-instrument over-endorsement offset (CVR-019 #1 / `ISS-F2V-028`) regardless of
this corrected design-intent target — any expected-vs-observed divergence in the live run is a
reportable finding for the EXP entry, never grounds to retroactively redefine `PLAN-2026-W29-D`'s
pre-registered acceptance criteria (REV-044 Criterion 1 discipline, §8's own stated policy).

| S | Day | State descriptor (intent) | Inter-session event | PHQ-9 target / CTRS target |
|---|---|---|---|---|
| 1 | 0 | Baseline: deadline stress ongoing, sleep 4-5h, anxious, mild mood dip | (intake — no prior session) | ~7 / 5 |
| 2 | 7 | Deadline met, relief, sleep improving to 5-6h | "project deadline met, small team dinner" | ~6 / 5 |
| 3 | 14 | Continued improvement, resumed one weekend yoga session, appetite normalizing | "resumed 1 yoga session after a 2-week gap" | ~5 / 5 |
| 4 | 21 | Notably better, sleep 6-7h, only occasional residual work worry | "positive performance review at work" | ~4 / 5 |
| 5 | 35 | **Plateau/wobble**: new project assigned, mild anticipatory anxiety returns, sleep slightly disrupted again (not to baseline) | "new project kickoff, tight but manageable timeline" | ~6 (non-monotonic uptick) / 5 |
| 6 | 49 | Adjusting to new project using coping strategies already established (exercise, talking to a colleague) | "used breathing/exercise coping during a stressful week" | ~4 / 5 |
| 7 | 63 | Improvement resumes; new project going well; strong social support reaffirmed | "project milestone met successfully" | ~3 / 5 |
| 8 | 91 | Maintenance phase begins; occasional stress but overall stable | "took a short weekend trip" | ~3 / 5 |
| 9 | 122 | Continues stable; sleep consistently 6-7h with rare exceptions | "one bad-sleep night, otherwise unremarkable month" | ~3 / 5 |
| 10 | 152 | Sustained near-minimal symptom range; functioning well at work | "no major life events this month" | ~2 / 5 |
| 11 | 183 | Consolidated improvement; a minor new deadline handled without symptom recurrence | "minor work deadline, handled it fine this time" | ~3 / 5 |

**VP-003 — `arc_mode="relapse_after_partial_improvement"`** (the S5-S7 relapse trigger is the
persona's OWN documented detail — unemployment-benefit cutoff, `VP-003_first_visit_severe.md:75`,
"2개월 후 종료 예정" — never an invented stressor; the S3/S10 brother-contact events use the
persona's own documented "3개월간 통화 2회" baseline, `VP-003_first_visit_severe.md:72`, spending
those 2 documented calls across the arc rather than inventing new contact):

**S8 addition (ADR-036 item 5 / CVR-020 binding condition 1):** S8 (the first post-relapse-peak
session) gains a NEW inter-session event, additive to the persona's own 2 documented brother-contact
calls (spent at S3/S10 as originally designed) — the patient, prompted by crisis-support information
recalled from an earlier session, contacts his brother first, and the brother facilitates a first
psychiatric-intake contact. This resolves CVR-020 Finding 1 (a crisis-adjacent, daily-passive-SI
patient re-administering a pre-consultation intake tool 10 times over 6 months with zero depicted
connection to actual care would misrepresent this system's own guardian-liaison validation target,
`VP-003_first_visit_severe.md:240`) by SCRIPTING the depicted consequence, rather than relying on a
caveat alone — the continuity-of-care caveat (§7.5) still stays in every report regardless.

| S | Day | State descriptor (intent) | Inter-session event | PHQ-9 target / CTRS target |
|---|---|---|---|---|
| 1 | 0 | Baseline: severe/crisis-adjacent, passive SI daily, deep isolation | (intake — no prior session) | ~23 / 2-3 |
| 2 | 7 | Minimal engagement; slight relief from having spoken about it once; passive SI still daily, marginally less intense per-day | "no contact from anyone" | ~20 / 3 |
| 3 | 14 | Brother made contact once (one of the persona's own documented 2 calls); slight mood lift | "brother called once, brief" | ~18 / 3 |
| 4 | 21 | Applying for jobs half-heartedly; marginal sleep improvement (3h→3.5h) | "sent out a few halfhearted job applications" | ~17 / 3 (partial improvement established) |
| 5 | 35 | Anticipatory dread rising — unemployment benefit clock ticking (1 month left) | "received notice: unemployment benefit ends in ~1 month" | ~19 (early warning uptick) / 3 |
| 6 | 49 | **Relapse trigger**: benefits officially end this week; financial panic; drinking increases further; passive SI intensifies in frequency | "unemployment benefits ended this week" | ~23 (back to/near baseline) / 2 (crisis-adjacent, probe likely re-triggers) |
| 7 | 63 | Acute point sustained; isolation deepens (no job, no income, no contact) | "no job, no income, no contact with anyone this month" | ~24 (arc peak) / 2 |
| 8 | 91 | Minimal stabilization begins; applied for emergency social assistance | "applied for emergency social assistance"; **"prompted by crisis-support information recalled from an earlier session, contacts brother first — brother facilitates a first psychiatric-intake contact"** (new, ADR-036 item 5) | ~20 / 3 |
| 9 | 122 | Slow partial recovery; started a part-time job | "started a part-time job" | ~17 / 3 |
| 10 | 152 | Continued gradual improvement; brother's 2nd documented call/visit occurs | "brother visited once" | ~15 / 3-4 |
| 11 | 183 | Partial, incomplete recovery — occasional (no longer daily) passive SI, marginal functional improvement | "no major setbacks this month" | ~14 / 4 |

Net 6-month shape for VP-003: severe → partial improvement (S2-4) → **scripted relapse** (S5-7,
worsened-priority test case) → gradual partial recovery (S8-11), ending moderate-severe, never
fully resolved — deliberately not a clean improvement story, to stress-test §7.4 acceptance
criterion 1.

### 2.5 Guideline pack schema

`[DESIGN INTENT]` — new dataclass, harness/tests territory (`tests/simulation/scenario_pack.py`,
never `src/`):

```python
@dataclass(frozen=True)
class ScenarioSession:
    session_index: int              # 1-based
    day_offset: int                 # days since session 1, see §2.3
    arc_mode: str                   # e.g. "improvement_plateau" | "relapse_after_partial_improvement"
    phase_label: str                # "acute_engagement" | "response_consolidation" | "maintenance"
    state_descriptor_ko: str        # patient's state AT this date only — mood/sleep/energy/function
    inter_session_events_ko: list[str]   # what happened SINCE the prior session (life events, never clinician actions this system doesn't perform)
    symptom_targets: dict[str, str]      # domain -> qualitative direction, DESIGN INTENT not a hard pin (mirrors f3_quick_dev_plan.md §8's own "design intent, not hard-pinned" convention)
    reveal_guidance_ko: str         # what/how the patient discloses this session, tone
```

`scenario_pack_id = f"{persona_id}_{arc_mode}_s{session_index:02d}"` (e.g.
`"VP-001_improvement_plateau_s05"`) — the provenance tag threaded onto both the artifact and the
ledger entry (§2.7).

**Injected guideline text template** (built by the harness, appended to `persona.system_prompt` —
never a new persona `.md` file, never a `docs/ai/prompts/**` edit):

```
## 세션 시나리오 안내 (개발 검증용, {simulated_date}, 세션 {session_index}/{n_sessions})
- 현재 상태: {state_descriptor_ko}
- 지난 세션 이후 있었던 일: {각 inter_session_events_ko 항목을 불릿으로}
- 이번 세션에서 자연스럽게 드러낼 내용: {reveal_guidance_ko}

주의: 당신은 앞으로 무슨 일이 있을지 알지 못합니다. 오직 지금까지 일어난 일과 현재 상태만을
바탕으로 자연스럽게 답하세요.
```

The final line is the explicit "never the future arc" guard — the pack for session *i* never
contains session *i+1..N*'s content, and the harness only ever renders/injects ONE session's pack
per F1 run (never the whole arc table at once).

### 2.6 Isolation mechanism — options evaluated

| # | Option | How it works | Production diff footprint |
|---|---|---|---|
| A | Extend `prior_handoff`/`system_prompt` seam broadly | New `_run_simulation(..., scenario_guideline: str \| None)` kwarg; guideline text appended to `persona.system_prompt` the same way the existing `prior_handoff` block is (`f1.py:2291-2300`) | Same order of magnitude as C below, but couples the guideline directly into the same code path as the safety-relevant `prior_handoff` narrowing (AVC-02) — higher risk of accidental interaction with that already-hardened seam |
| B | Pure `load_persona` path-mode | Harness renders a full per-session `.md` file (base persona + injected block) under a scratch dir, calls `f1._run_simulation(persona_id=<path>, ...)` — `load_persona`'s existing path-mode seam (`tests/simulation/patient_llm.py:80-89`) loads it directly, **zero f1.py changes** | 0 LOC in `src/`, but the raw path string then flows into `session_id=f"f1_{persona_id}{session_suffix}"` (`f1.py:2339`) and `PERSONA_LOCATIONS.get(persona_id)` (`f1.py:2324`) UNCHANGED — pollutes `session_id`/`patient_id` with a full filesystem path and silently disables the crisis-geo lookup (`PERSONA_LOCATIONS` keyed by short VP-ID, never matches a path) for every scripted session |
| **C (chosen)** | Narrow, dedicated kwarg pair | `_run_simulation` gains **two** small, optional, backward-compatible kwargs: `scenario_guideline: str \| None = None` (appended to `persona.system_prompt` right after the existing `prior_handoff` block, own header, never touches that block's own text) and `scenario_pack_id: str \| None = None` (threaded straight onto the returned `F1Result` post-call, `result.scenario_pack_id = scenario_pack_id` after `f1.py:2337`, since `F1Result` is a plain mutable `@dataclass` — no `F1Pipeline.run_session` signature change needed at all). `persona_id`/`session_id`/`PERSONA_LOCATIONS` lookups stay byte-identical to today | **Smallest of the three**: +1 optional `F1Result` field (default `None`, `.get()`-fallback pattern already established for `session_index`/`simulated_date`, `f1.py:2186-2196`), +2 optional `_run_simulation` kwargs, +1 conditional ~6-line system_prompt append block, +1 one-line post-call assignment. Zero change to `F1Pipeline.run_session`, zero change to any prompt file, zero change to `session_id`/geo-lookup behavior |

**Decision: Option C.** It is a narrower version of the two options the brief names (a refinement
of "extend the seam", stopping short of full path-mode's session-bookkeeping pollution) and follows
the exact precedent this codebase already set for harness-serving optional kwargs
(`session_index`/`simulated_date`, added in `PLAN-2026-W28-Q` W2, same `.get()`-default-for-old-
artifacts pattern). It requires editing `src/f1.py` — **not** zero-footprint — but the footprint is
small, additive-only, defaults preserve every existing caller's exact behavior, and it does not
touch any file under `docs/ai/prompts/**` (persona `.md` files are data, not the prompt-pin set the
binding constraint protects — `persona.system_prompt` is already runtime-mutated today for
`prior_handoff`, `f1.py:2291-2300`, without objection). This satisfies "verification-external":
the scenario PACK CONTENT and the arc TABLE live entirely in `tests/simulation/scenario_pack.py`
(harness/tests territory) — only the two narrow injection kwargs live in `src/f1.py`, and they are
inert (`None`) for every non-scripted caller, including the live 4VP battery and any future
production reuse of `_run_simulation`.

**Line-anchor correction (REV-044 minor 5, tightened at implementation):** the
`result.scenario_pack_id = scenario_pack_id` post-call assignment lands after
`pipeline.run_session(...)` **closes at `f1.py:2355`** (that multi-line call opens at `f1.py:2337`)
and **before `save_f1_result(result)` at `f1.py:2357`** — not literally "after 2337" as the original
draft imprecisely stated.

### 2.7 Structural provenance

- **Artifact:** `F1Result.scenario_pack_id: str | None = None` (new field, §2.6 option C) —
  appears in the saved `conversation.json` automatically (`save_f1_result` uses
  `json.dumps(asdict(result), ...)`, `f1.py:1795` — any new dataclass field is captured for free,
  no serializer change needed).
- **Ledger:** the harness's existing `ledger_entry` dict construction
  (`run_multi_session_chain`, `continuous_test.py:761-777`, and
  `_build_single_session_ledger_entry`, `continuous_test.py:926-967`) gains two new top-level keys,
  `"scenario_pack_id"` and `"arc_mode"`, read straight off the F1Result (`f1_result.scenario_pack_id`)
  — never re-derived, never guessed. `None`/absent for every natural (non-scripted) session, so
  re-ingesting the 3 existing real ledgers (VP-001/003/012, all natural, verified this session)
  never breaks — a missing key degrades to `None`, exactly the `.get(...)`-default discipline this
  file already uses throughout (e.g. `data.get("f3", {}).get(...)` patterns).
- **F4's own consumption rule:** `src/f4.py`'s `SessionRecord` (§4) carries `scenario_pack_id`/
  `arc_mode` straight through into `LongitudinalAnalysisOutput` (§5) as **metadata only** — the
  analysis engine itself computes identically whether a session is scripted or natural; the tag
  exists purely so nobody downstream (F5, a future report reader) can mistake scripted-validation
  output for live clinical data.

---

## 3. State taxonomy for longitudinal analysis

One dimension per row. `source` is the exact artifact field path (verified against real data this
session unless marked `[DESIGN INTENT]`).

| # | Dimension | Source (artifact.field) | Per-session value type | Derived trend metric(s) |
|---|---|---|---|---|
| F1-1 | Slot fill (12-slot) | ledger `final_slots` (dict, top-level, verified real) / ledger `missing_slots` (list of the 8 questionable keys, `src/grounding.py::QUESTIONABLE_SLOT_KEYS`) | `dict[str,str]` filled + `list[str]` missing | filled-count delta session→session; filled-count slope/time (numpy `polyfit`, degree 1); newly-filled/newly-missing set diffs (never re-fabricated content, only presence/absence) |
| F1-2 | Slot **content** delta (incl. `risk_assessment`) | same `final_slots` dict, per-key string value | `str \| None` per key | verbatim value change detection (string inequality only — F4 never re-interprets clinical meaning of a slot's prose, consistent with `temporal_summary.py`'s own "never guess" discipline) |
| F1-3 | `session_ctrs` | F1 conversation.json top-level `session_ctrs` (int, verified real: `4` in the sample read) | `int` (1=highest risk .. 5=stable) | pairwise `worsened`/`improved`/`unchanged` via `TemporalSummaryAgent._compare_ctrs` (reused, §6.1), plus min-CTRS-ever-reached across the series |
| F1-4 | `crisis_triggered`/`crisis_turn` | conversation.json top-level (verified real: `false`/`null` in the sample; schema always present, `F1Result` dataclass default `False`/`None`, `f1.py:234-235`) | `bool`/`int\|None` | crisis-recurrence count (sessions with `crisis_triggered=true`); longest consecutive-crisis run length |
| F1-5 | `probe_events` | conversation.json top-level (list of dict, `type` ∈ {`trigger`,`escalation`,`deescalation`,`progress`,`si_screen`,`si_screen_result`}, verified real: 1 `si_screen` event in the sample) | `list[dict]` | per-session probe-event count; type-sequence across the arc (e.g. repeated `escalation` without `deescalation` = a relapse_signal candidate) |
| F1-6 | `risk_floor` | conversation.json top-level (`int \| None`, verified real: `null` when never latched) | `int \| None` | latch-persistence (does a latched floor carry into the next session's baseline framing — no: `f1.py:1025-1026`'s own comment states "risk_assessment is grounded only via probe/SI-screen in THIS session... every session re-screens"; F4 records but never assumes carry-over) |
| F1-7 | `session_sentiment` (Mode B) | conversation.json top-level (`dict`, verified real: populated for a normally-completed session; **verified EMPTY (`{}`) for a crisis-early-exit session** — `f1.py:1062-1071`'s `_finalize()` sync fallback comment: "Sync fallback for early-exit paths — skips Mode B sentiment") | `dict` or `{}` | see F1-8 fallback |
| F1-8 | Per-turn sentiment (Mode A) | conversation.json `turns[].sentiment` (dict, verified real: `{polarity, arousal, emotions, evidence_phrase, risk_signal}` per turn) | `dict` per turn, always present when `turns` is non-empty | F4's own derived per-session `mean_polarity = mean(turns[].sentiment.polarity)` — used as the PRIMARY session-level sentiment scalar (not `session_sentiment`) precisely because F1-7 can be empty on a crisis-early-exit session while F1-8 is not; pairwise trend via `TemporalSummaryAgent._compare_sentiment` (reused, §6.1) |
| F2-1 | `domain_candidates` (per-domain) | domain_inference.json top-level `domain_candidates[].{domain, confidence, evidence}` (verified real: e.g. `{"domain":"sleep","confidence":0.6,...}`) | `list[dict]`, ≤3 candidates/session (schema cap) | per-domain confidence trend across sessions (for domains that recur); domain-set stability (does the top domain repeat) — never relabeled "probability," matches schema's own field name |
| F2-2 | `ai_predicted_disease` top-5 set + `similarity_score` | domain_inference.json top-level `ai_predicted_disease.candidates[].{disease, similarity_score, source_id, quote}` (verified real: 5 candidates, scores 0.447–0.492) | `list[dict]`, ≤5/session, or `[]` when `mode="experimental_unpopulated"` | **similarity TREND, never probability** (binding wording law, §5) — per-disease `similarity_score` slope across the sessions in which that disease NAME recurs (numpy `polyfit`); top-5-set Jaccard stability between consecutive sessions; explicit `mode` tracking (`experimental_unpopulated` sessions contribute 0 candidates honestly, never treated as a data gap to fill) |
| F2-3 | `recommended_questionnaire`/`recommendation_caveat` changes | domain_inference.json `ai_predicted_disease.{recommended_questionnaire, recommendation_caveat}` (verified real: `"PHQ-9"` + a caveat string) | `str \| None` | scale-recommendation-switch events (session *i* recommends a different scale than session *i-1* — informational only, never re-adjudicated) |
| F3-1 | Per-item response vector | ledger `f3.responses` (list[int], verified real: 9-length list for PHQ-9) | `list[int]` | per-item delta where the SAME scale repeats across sessions (item indices are stable within one scale); flags a scale SWITCH (different `scale_name`) as non-comparable at the item level, only at the total/severity level |
| F3-2 | `total_score`/`max_score` | ledger `f3.total_score`/`f3.max_score` (verified real: `13`/`27`) | `int \| None` | pairwise `improved`/`worsened`/`unchanged` via `TemporalSummaryAgent._compare_scale` (reused, §6.1) — but ONLY between sessions administering the SAME scale (a PHQ-9→GAD-7 scale switch is recorded, never diffed as if comparable) |
| F3-3 | `severity` band | ledger `f3.severity` (verified real: `"moderate"`) | `str \| None` (PHQ-9 bands: minimal/mild/moderate/moderately_severe/severe, `survey_scorer.py:40-46`) | band-transition sequence + count of transitions; a same-scale two-step-or-more jump flagged as a notable event regardless of the raw delta |
| F3-4 | `critical_item_positive` (`safety_referral`) | ledger `f3.safety_referral` (bool, verified real: `false`) | `bool` | positive-flip events (false→true) tracked as a standalone crisis-relevant series, cross-referenced against F1-4/F1-5 same-session |
| F3-5 | `subscale_scores` | ledger `f3.subscale_scores` (dict, verified real: `{}` for PHQ-9/AUDIT-C — only populated for scales with subscales) | `dict[str,int]` | per-subscale delta, same-scale-only rule as F3-2 |
| F3-6 | `outcome`/`administration_mode` | ledger `f3.outcome` ∈ {`administered`,`no_questionnaire_indicated`,`item_bank_unpopulated`}; `f3.administration_mode` ∈ {`natural`,`forced`} (verified real for `outcome`; `administration_mode` confirmed present on newer artifacts via `src/f3.py:277-279`, absent — defaults `"natural"` — on the pre-`ADR-033` sample read) | `str` | non-`administered` sessions contribute 0 score points to F3-2/F3-3/F3-5 **honestly** (see missing-data handling below); `administration_mode="forced"` sessions are excluded from any "F2-linkage" trend claim (continuous_test.py:73, `f3_quick_dev_plan.md` binding rule — this mission's own validation cells never use `--force-questionnaire`, but F4 must still respect the field if a future dataset does) |

### 3.1 Handling missing data honestly (evidence-필수 principle, applied to every dimension above)

| Case | F4 behavior |
|---|---|
| F3-skipped session (`outcome != "administered"`) | Scale-series point recorded with `total_score=None`, `administered=False` — never imputed, never dropped from the series (the session still contributes to F1/F2/sentiment series) |
| F2 zero-candidate session (`mode="experimental_unpopulated"`, `candidates=[]`) | Disease/domain series points for that session are empty lists, recorded as a legitimate honest outcome (mirrors `f2.py`'s own "0 candidates is not an error" convention, `PRD §3.9`) — never back-filled from a neighboring session |
| Older ledger entries lacking `"f3"` (pre-`PLAN-2026-W28-V`) | `ledger_entry.get("f3")` is `None` — F4 treats the whole F3 dimension group as `unknown` for that session only, other dimensions unaffected |
| `session_sentiment` empty (crisis early-exit, F1-7) | Fall back to F1-8's per-turn mean — **not** an "unknown" case as long as ≥1 turn exists (turn 0 always logs, per PRD §2.5 rule 1) |
| Fewer than 2 valid sessions for a given dimension | That dimension's trend verdict is `unknown` (never a guessed direction) — same rule `temporal_summary.py`'s own `is_first_visit` branch already enforces at the pairwise level (`temporal_summary.py:30-40`), generalized to "fewer than 2 comparable points" for the N-session case |
| A scale switches mid-arc (PHQ-9 → GAD-7 recommended in a later session) | Each scale gets its OWN sub-series (§4's `scale_series: dict[str, list[...]]`, keyed by scale name) — never diffed cross-scale |

---

## 4. Architecture — production/harness split

```
PRODUCTION                                    HARNESS
src/f4.py (NEW, zero LLM calls)               continuous_test.py F4 stage (NEW)
───────────────────────────────               ───────────────────────────────
  analyze_longitudinal_series(                   run_f4_stage(ctx) / a standalone
    LongitudinalSeriesInput                       CLI entry (mirrors run_f1/f2/f3_stage):
  ) -> LongitudinalAnalysisOutput                  1. read <VP>_session_ledger.json
        │  - NEVER reads the ledger file             (harness artifact, REV-044
        │  - NEVER reads a conversation.json/         Criterion 6 rule, corrected from
        │    domain_inference.json/survey.json         mis-cited REV-022 per REV-046
        │    path itself — the harness has              Issue 6 / ADR-037 — production
        │    already resolved+loaded them               never touches it)
        │                                             2. FOR EACH entry: resolve
        │                                                conversation_path/
        │                                                domain_inference_path pointers,
        │  - pure function over the explicit            open those JSON files, pull the
        │    dataclass the harness built                 dims from §3's table
        │  - 100% deterministic rule-based           3. build one SessionRecord per
        │    (numpy arithmetic only, no LLM,             ledger entry (§4.1)
        │    no randomness, no I/O beyond            4. call src.f4.analyze_longitudinal_
        │    §5's own save function)                     series(LongitudinalSeriesInput(...))
        ▼                                          5. call src.f4.save_f4_result(...)
  save_f4_result(output, output_dir)              6. plot generation (via
    -> <vp_id>_<ts>_temporal.json                     src.services.trend_plotter, §5)
    -> <vp_id>_<ts>_temporal_report.md            7. print PASS/WARN report, same
    -> PNG charts (§5)                                convention as F1-F3 stages
```

**Correction note:** the ledger-isolation citation above was corrected per `REV-046` Issue 6 /
`ADR-037` (2026-07-14) — the rule's actual originating authority is `REV-044` Criterion 6 (confirmed
in `f4.py`'s own docstring); `REV-022` was an unrelated RAG trigger-policy entry, mis-cited here and
propagated unchanged into `f5_quick_dev_plan.md` before both were fixed.

### 4.1 `SessionRecord` — the harness→production contract

`[DESIGN INTENT]`, new dataclass in `src/f4.py` (the production module owns its own input type, same
pattern `f3.py`'s `SurveyRecommendation` uses):

```python
@dataclass(frozen=True)
class SessionRecord:
    session_index: int
    simulated_date: str
    scenario_pack_id: str | None
    arc_mode: str | None
    final_slots: dict[str, str]
    missing_slots: list[str]
    session_ctrs: int | None
    crisis_triggered: bool
    crisis_turn: int | None
    probe_events: list[dict]
    risk_floor: int | None
    turn_sentiment_polarities: list[float]   # F1-8, always derivable when turns exist
    turn_risk_signal_count: int              # ADR-036 item 9 / CVR-020 Rec 2: count of turns[].sentiment.risk_signal==True this session
    session_sentiment_summary: dict | None   # F1-7, may be {} / None
    domain_candidates: list[dict]            # F2-1
    ai_predicted_disease: dict | None        # F2-2/F2-3
    f3: dict | None                          # F3-1..6, the ledger's own "f3" sub-object as-is

@dataclass(frozen=True)
class LongitudinalSeriesInput:
    vp_id: str
    sessions: tuple[SessionRecord, ...]   # caller-sorted by session_index; f4.py validates monotonicity, raises loudly if not
```

`analyze_longitudinal_series` never opens a file, never imports `json`/`pathlib` for I/O, never
imports anything from `src.continuous_test` or `tests/` — the same "production imports nothing
from the harness" discipline `f3.py`'s own module docstring states for itself
(`f3.py:14-16`, "This module imports NOTHING from `tests/`"). At implementation, `save_f4_result`
(§5.1) was placed in a NEW sibling module, `src/services/f4_report.py`, rather than inside
`src/f4.py` itself — a deliberate tightening of Criterion 6 (REV-044) so a whole-file check for
direct filesystem access on `src/f4.py` returns 0 hits with zero ambiguity; `analyze_longitudinal_
series` remains the single source of truth for every number either module reports.

### 4.2 Reuse-vs-new per module

| Module | Decision | One-line rationale |
|---|---|---|
| `agents/temporal_summary.py` + `schemas/temporal.py` | **REUSE unmodified, called pairwise-iteratively** | Its `_compare_scale`/`_compare_ctrs`/`_compare_sentiment` are plain `@staticmethod`s (`temporal_summary.py:115,140,172`) — importable and callable N-1 times across consecutive session pairs without touching the class, its route, or its existing tests; it does NOT natively support N-session series, F1 slot-fill, or F2/F3-specific dims, so `f4.py` writes NEW aggregation/comparison code for those, never forking or duplicating the pairwise logic itself |
| `agents/sentiment_analyzer.py` | **REUSE persisted Mode-B/Mode-A output only, zero new calls** | F4 reads `session_sentiment`/`turns[].sentiment` already written to disk by F1 — `f4.py` never imports `SentimentAnalyzerAgent`, never calls an LLM, matching the "F4 analysis engine 100% deterministic/zero LLM" constraint |
| `src/services/trend_plotter.py` | **REUSE `generate_trend_plot` unmodified for chart 1; EXTEND with a 5th optional panel (slot-fill) for chart 5; ADD 2 new sibling functions for charts 3-4 (similarity-per-disease is multi-series, doesn't fit the existing one-value-per-date `_draw_panel` abstraction)** | See §5.2 for the exact chart-by-chart breakdown and the extension's footprint |
| `schemas/ai_predicted_disease.py` | **REUSE unmodified as the INPUT parsing model** | F4 re-validates each session's `ai_predicted_disease` dict against the existing `AIPredictedDiseaseOutput`/`AIPredictedDiseaseCandidate` Pydantic models (cheap correctness check, zero schema change) before extracting `similarity_score`/`disease`; F4's OWN output uses a NEW schema (`schemas/longitudinal.py`, below) — never widens or repurposes this module (preserves its REV-013 §3 standalone-by-design invariant) |
| `08_temporal_retriever` | **STAYS PARKED, out of F4-quick scope** | Semantic RAG retrieval for dialogue-context/handoff-generation (its own doc's stated purpose, `08_temporal_retriever.md:14-16`) is a different concern from F4's structured-field trend analysis; its designed DB tables (`conversations`/`handoff_reports`/`scale_scores`/`ocr_blocks`/`risk_events`) do not exist in this repo's actual persistence (JSON artifacts on disk, not those tables) — reactivation is a separate future mission with its own DB-schema work, not a quick-dev item |
| `schemas/survey_result.py` / `scoring/survey_scorer.py` / `scoring/item_bank.py` | **REUSE unmodified as read-only INPUT sources** | F4 never rescoring/reinterpreting — same "compute once, never re-derive downstream" discipline `f3.py`'s own docstring states for itself |
| F2 persistence | **NOT NEEDED — confirmed already consumable** | Verified directly this session: `ai_predicted_disease` (candidates+`similarity_score`+`recommended_questionnaire`) AND `domain_candidates` are BOTH present, per-session, in the real `VP-001_20260712_204048_domain_inference.json` artifact; the ledger already carries a `domain_inference_path` pointer per entry (verified real, top-level key). Zero new F2-side plumbing required |

### 4.3 New schema module

`[DESIGN INTENT]` `src/schemas/longitudinal.py` — standalone, same discipline as
`schemas/survey_result.py`/`schemas/ai_predicted_disease.py` (never imports `handoff.py`/
`domain_inference.py`/`SlotData`, `is_diagnostic: Literal[False]` fixed at the type level):

**Schema additions per `ADR-036` item 9 (CVR-020 Recs 1-4), as actually implemented — folded into
this block rather than left as a stale pre-review draft:**

```python
class SlotFillPoint(BaseModel):
    session_index: int; simulated_date: str
    filled_count: int; total_questionable: int          # out of len(QUESTIONABLE_SLOT_KEYS) == 8
    newly_filled: list[str] = []; newly_missing: list[str] = []
    mental_status_exam_observed: bool = False            # ADR-036 item 9 / CVR-020 Rec 1

class ScaleSeriesPoint(BaseModel):
    session_index: int; simulated_date: str
    scale_name: str | None; administered: bool
    total_score: int | None = None; max_score: int | None = None; severity: str | None = None
    critical_item_positive: bool | None = None; subscale_scores: dict[str, int] = {}

class CTRSSeriesPoint(BaseModel):
    session_index: int; simulated_date: str
    session_ctrs: int | None; crisis_triggered: bool; probe_event_count: int
    risk_floor: int | None

class SentimentSeriesPoint(BaseModel):
    session_index: int; simulated_date: str
    mean_polarity: float | None; dominant_emotions: list[str] = []
    source: Literal["mode_a_derived", "mode_b"]
    risk_signal_count: int = 0                           # ADR-036 item 9 / CVR-020 Rec 2 (Mode A)
    signal_strength: str | None = None                    # ADR-036 item 9 / CVR-020 Rec 2 (Mode B)
    emotional_shift_detected: bool | None = None           # ADR-036 item 9 / CVR-020 Rec 2 (Mode B)

class DiseaseCandidateSeriesPoint(BaseModel):
    session_index: int; simulated_date: str
    disease: str; similarity_score: float; rank: int    # rank = 1-based position in that session's top-5

class DomainCandidateSeriesPoint(BaseModel):
    session_index: int; simulated_date: str
    domain: str; confidence: float

class TrendVerdict(BaseModel):
    dimension: str                                        # e.g. "phq9_total" | "session_ctrs" | "sentiment"
    direction: Literal["improved", "worsened", "unchanged", "unknown"]
    basis: str                                             # code-fixed disclosure string (Criterion 0/0b) — never "pairwise_majority" alone
    n_comparable_points: int
    evidence: list[str]                                    # never empty when direction != "unknown" (evidence-필수)

class LongitudinalAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vp_id: str; arc_mode: str | None; n_sessions: int
    session_span_days: int | None
    slot_fill_series: list[SlotFillPoint] = []
    scale_series: dict[str, list[ScaleSeriesPoint]] = {}    # keyed by scale_name actually seen
    ctrs_series: list[CTRSSeriesPoint] = []
    sentiment_series: list[SentimentSeriesPoint] = []
    disease_candidate_series: list[DiseaseCandidateSeriesPoint] = []
    domain_candidate_series: list[DomainCandidateSeriesPoint] = []
    trend_verdicts: list[TrendVerdict] = []
    overall_direction: Literal["improved", "worsened", "unchanged", "unknown"]
    course_shape: Literal[                                  # ADR-036 item 9 / CVR-020 Rec 3
        "gradual_improvement", "improvement_with_plateau", "relapse_after_partial_improvement",
        "worsening_sustained", "crisis_episode", "unknown",
    ] = "unknown"
    concordance_flag: Literal["concordant", "discordant", "unknown"] = "unknown"  # ADR-036 item 9 / CVR-020 Rec 4
    crisis_f3_gaps: list[str] = []                          # CVR-020 binding condition 3 machinery
    is_diagnostic: Literal[False] = False
    disclaimer: str = LONGITUDINAL_DISCLAIMER_KO         # new constant, same discipline as AI_PREDICTED_DISEASE_DISCLAIMER_KO
    generated_at: str
```

---

## 5. Analysis outputs spec

### 5.1 JSON + markdown

| Artifact | Naming (mirrors f1/f2/f3 convention) | Contents |
|---|---|---|
| Machine-readable full series | `<VP>_<ts>_temporal.json` | `LongitudinalAnalysisOutput.model_dump()` verbatim — this is what a future F5 consumes |
| Human-readable tables | `<VP>_<ts>_temporal_report.md` | One markdown table per dimension group (slot-fill, scale totals per scale, CTRS/crisis/probe, sentiment, domain candidates, disease-similarity), plus a `## Trend verdicts` summary table and the disclaimer block |
| PNG charts | see §5.2 | landing directory: `docs/ai/simulation_results/<VP>/` (same dir as every other F1-F3 artifact for that VP — no new directory) |

### 5.2 Charts (exact list)

| # | Chart | Data | Module decision (from §4.2) | Filename |
|---|---|---|---|---|
| 1 | Scale totals + CTRS + sentiment, multi-panel over simulated dates | `scale_series` (per administered scale) + `ctrs_series.session_ctrs` + `sentiment_series.mean_polarity` | REUSE `generate_trend_plot` unmodified — build one `TrendDataPoint` per session (`phq9`/`gad7` populated only for sessions administering that scale, `None` otherwise — the function already handles sparse series, verified: `_draw_panel`'s `valid_pairs` filter skips `None`, `trend_plotter.py:278-280`) | `<VP>_<ts>_temporal_scales_ctrs_sentiment.png` |
| 2 | CTRS/risk over time, dedicated single-panel zoom | `ctrs_series` | Already covered by chart 1's CTRS panel; this row exists for the user's explicit "risk crisis 결과" callout — if chart 1's density makes CTRS hard to read with 11 points, a dedicated single-panel is the SAME `generate_trend_plot` call with only `ctrs` populated (reuse, zero new code, just a second invocation) | `<VP>_<ts>_temporal_ctrs_zoom.png` |
| 3 | Per-disease similarity trend | `disease_candidate_series`, grouped by `disease` name, only diseases appearing in ≥2 sessions plotted as lines | NEW function `generate_similarity_trend_plot` in `trend_plotter.py` — one line per recurring disease name, x=simulated_date, y=`similarity_score` (0-1), **y-axis label = "similarity score (RAG cosine-similarity signal)" — never "probability"/"confidence"** (binding, §5.3); reuses `_parse_date`/Korean-font setup, new panel-drawing logic since this is fundamentally N-series-per-date, not 1 | `<VP>_<ts>_temporal_disease_similarity.png` |
| 4 | Domain-candidate confidence trend | `domain_candidate_series`, grouped by `domain` | NEW function `generate_domain_trend_plot`, same shape/reuse rationale as #3 (kept as a separate function since domains use the schema's own `confidence` field name, never conflated with `similarity_score`) | `<VP>_<ts>_temporal_domain_confidence.png` |
| 5 | Slot-fill count over time | `slot_fill_series.filled_count` (0-12) | EXTEND `trend_plotter.py`: add `slot_fill_count: int \| None = None` to `TrendDataPoint` (+1 field) and one `if has_slot_fill: panels.append(...)` clause to `_render_plot` (+1 clause, mirrors the existing `has_sentiment` clause exactly, `trend_plotter.py:182,197-200`) — smallest-footprint option since it reuses `_draw_panel`/zones/axis code unchanged (`zones=[]`, `y_min=0`, `y_max=12`, same pattern as the sentiment panel's `y_min=-1.0`) | Folded into chart 1's multi-panel figure (no separate file) unless density requires a zoom (same fallback pattern as chart 2) |

### 5.3 Wording laws (binding, applied to every artifact in §5.1)

1. `similarity_score` (F2-2/chart 3) is **never** labeled "probability"/"confidence"/"가능성" —
   axis labels, JSON field descriptions, and markdown table headers all say "similarity"/"유사도".
   Inherited directly from `AIPredictedDiseaseCandidate.similarity_score`'s own binding rule
   (`ai_predicted_disease.py:113-124`, REV-013 §4).
2. `is_diagnostic: Literal[False]` + the disclaimer text are carried on
   `LongitudinalAnalysisOutput` (§4.3) — same discipline as `ai_predicted_disease.py`/
   `survey_result.py`.
3. F3-derived content in the markdown report carries F3's own **non-validated conversational
   administration caveat** forward — every `scale_series` table row citing a scale in
   `_SEVERITY_CAVEATS` (AUDIT-C, GAD-7, `f3.py:92-95`) reprojects that scale's `threshold_caveat`
   verbatim, and the report's F3 section states item bank `provenance` per scale (never presents a
   v0/v1 score without its own sourcing/validation caveat).
4. **Evidence-필수:** any `TrendVerdict` with `direction != "unknown"` MUST have a non-empty
   `evidence` list; any dimension with fewer than 2 comparable points MUST be `"unknown"` — never a
   fabricated direction. This is machine-checked, not merely a writing convention (§7's pre-
   registered checks).
5. **Open, inherited caveat:** any report section touching `ai_predicted_disease`/disease-
   similarity content (chart 3, F2-2) inherits `VAL-014` (open, `error.md` — RAG candidate
   face-validity, poor cross-VP differentiation, implausible candidates in ≥12/14 prior runs) —
   the F4 report's own text must not imply the disease candidates are clinically validated just
   because a TREND is computed over them; a trend over noisy inputs is still noisy.

---

## 6. Clinical agent orchestration and workflow

### 6.1 Generation time vs analysis time

| Phase | What runs | LLM calls |
|---|---|---|
| Generation (per session) | F1 (Safety, ClinicalSlot, Dialogue, InputNormalizer, SentimentAnalyzer Mode A, PatientLLM) → F2 (DomainInferenceAgent Stage 2) → F3 (SurveyAnswerLLM per item, if administered) | Yes — see §7.3 budget |
| Analysis (once per VP, after all sessions) | `src/f4.py::analyze_longitudinal_series` only | **Zero** — pure rule-based/numpy, per the binding constraint |

`temporal_summary.py`'s pairwise comparators (§4.2) are also zero-LLM (verified: no
`ModelRouter`/`PromptLoader`/adapter import anywhere in `temporal_summary.py`, matching its own
agent-spec's corrected LLM Routing line, `09_temporal_summary.md:10`).

### 6.2 F4 trigger policy

- **Minimum to run:** ≥2 ledger entries for a VP (matches `temporal_summary.py`'s own
  `is_first_visit` guard generalized — 1 session has nothing to compare).
- **Full value:** ≥10 sessions (per the user's own floor) — below that, `trend_verdicts` remain
  populated but `n_comparable_points` will be visibly small in the artifact, an honest signal to a
  reader rather than a suppressed warning.
- Never auto-triggered inside F1/F2/F3 — always an explicit harness stage invocation (§4), same
  "no silent scope creep into production" posture as F2/F3.

### 6.3 STAGE_REGISTRY fit

`continuous_test.py`'s `Stage("F4", False, None, note="F4 not yet implemented — no src/f4.py in
this repo.")` (`continuous_test.py:803`) becomes `Stage("F4", True, run_f4_stage)` the moment
`src/f4.py` ships — exactly the extension seam its own docstring describes
(`continuous_test.py:238-243`, "append a `Stage(...)` entry... the moment `fN.py` ships"). Unlike
F1-F3's per-session stages, F4 is **NOT per-session** — it runs once, after the LAST session in a
multi-session chain (`run_multi_session_chain`'s loop), reading the now-complete ledger. This is a
new invocation SHAPE (post-loop, not in-loop) that the wave plan (§9) scopes explicitly.

### 6.4 PRD §9.3-9.5 fit

- §9.3's 3-session summary protocol is superseded in shape (not content) by this mission's
  11-session schedule (§2.3) — the underlying "accumulate a VP dataset across chained sessions"
  principle is identical, just deeper.
- §9.4's `f4.py` row ("종단 데이터셋(t1..tN) → SentimentAnalyzer(세션별) → TemporalSummary →
  temporal.json") is implemented as designed here, with the correction that SentimentAnalyzer is
  consumed **persisted**, not re-invoked (§4.2) — the PRD row's phrasing is compatible with either
  reading; this design makes the zero-new-LLM-call choice explicit.
- §9.5's `fe2e.py`/`f5.py --full-chain` integration (Section 9/Section 12 of a handoff) is
  explicitly NOT built this mission — `LongitudinalAnalysisOutput` is designed to be F5-consumable
  (§4.3) but F5 itself is untouched.

### 6.5 HPI red line

`LongitudinalAnalysisOutput` is structured data for a future F5, never injected into any
clinician-authored narrative slot. Same isolation discipline `AIPredictedDiseaseOutput` and
`SurveyResultOutput` already carry (standalone schema modules, no shared base class with
`SlotData`/`HandoffInput`) — `schemas/longitudinal.py` (§4.3) must never import
`schemas/handoff.py`, and vice versa. This is a **design requirement for the implementation
dispatch**, not yet qa-verified (that verification — an adversarial isolation test suite mirroring
`tests/test_hpi_isolation.py`/`tests/test_f3_hpi_isolation.py` — is scoped in §9's test wave).

---

## 7. Validation design (약식) and budget

### 7.1 Cells

2 VPs × 11 sessions (§2.3) = 22 session-cells, each F1→F2→F3 chained with a scenario pack (§2)
and a simulated date, followed by ONE F4 analysis run per VP (2 total, not per-session).

| VP | Sessions | Arc mode | Expected scale (design intent, not hard-pinned) |
|---|---|---|---|
| VP-001 | 1-11 | `improvement_plateau` | PHQ-9 (mood-classified, matches real precedent) throughout, unless a session's F2 top candidate shifts to `anxiety`→GAD-7 (unpopulated in v0-only classification reachability — reachable in v1 item bank, `item_bank.py` confirms PHQ-4/GAD-7 populated — recorded either way, never forced) |
| VP-003 | 1-11 | `relapse_after_partial_improvement` | PHQ-9 (severe-band, Q9 positive at baseline and at the S6/S7 relapse peak) |

### 7.2 Machine checks (pre-registerable, for critic in step 2)

| Check | Method |
|---|---|
| Series completeness vs ledger | For each VP, `len(LongitudinalAnalysisOutput.slot_fill_series) == number of ledger entries for that VP` — no session silently dropped |
| Trend-math recompute independence | qa (step 8, per `PLAN-2026-W29-D`) independently recomputes each `TrendVerdict` from the RAW ledger+artifact fields (never from `temporal.json` itself) and diffs against the shipped verdict — any mismatch is a BUG, not a note |
| Date monotonicity | `simulated_date` strictly increasing across `session_index` 1..N in both the ledger and every series in the output |
| Schema validation | `LongitudinalAnalysisOutput.model_validate(json.load(...))` round-trips without error; `extra="forbid"` catches any stray key |
| No fabricated points | Every point in every series traces to a specific artifact file + field path (§3's table) — qa greps the artifact for the exact value before accepting a plotted point |
| Crisis-session handling | At least one VP-003 session is expected (design intent) to hit `crisis_triggered=true` (the S6 relapse peak, §2's arc narrative) — verify F4 does not crash and correctly records `session_sentiment` fallback to Mode-A-derived (§3.1) for that session |

### 7.3 Explicit call/budget estimate

Per-session-cell breakdown, `[ESTIMATE — code-path call-counted, not a live measurement]` except
where cited as verified:

| Stage | LLM calls | Basis |
|---|---|---|
| F1 (11 logged turns incl. turn 0) | ~74 (turn0: dialogue-opening+safety+slot+sentiment = 4; each of 10 subsequent turns: normalizer+safety+slot+dialogue+sentiment+post_safety = 6 clinical calls + 1 patient-LLM call = 7, so 4 + 10×7 = 74) | Call sites verified in code: `f1.py:606,662,688,1108,1159,1173,1223,1315,1498,1573,1664,1676`. Wall-clock anchor: the real `VP-001_20260712_204038_conversation.json` run took 96s wall-clock (`started_at` 20:39:02 → `ended_at` 20:40:38) for an equivalent 11-turn session — VERIFIED |
| F2 | 1 (Stage 2 only; Stage 1 is DB-only, no LLM, `PRD §3.2`) | Wall-clock: 9,279.8ms — VERIFIED (`VP-001_..._domain_inference.json.repro.latency_ms`) |
| F3 (PHQ-9 administered) | 9 (one per item, `SurveyAnswerLLM`, `f3_quick_dev_plan.md` §7.1) | Wall-clock not captured in the read sample (no aggregate latency field on `survey.json`) — `[ESTIMATE]` ~2-5s/item |
| F3 (AUDIT-C administered) | 3 | Same basis |
| F3 (skipped: `no_questionnaire_indicated`/`item_bank_unpopulated`) | 0 | `f3.py:151-180`, confirmed no LLM call on either skip path |

**Totals (worst case, every cell administers a 9-item scale):**
- LLM calls: (74 + 1 + 9) × 22 session-cells = 84 × 22 = **1,848 calls**
- Wall clock (sequential, this harness's own execution model — no concurrency):
  (96s F1 + 10s F2 + ~30s F3 est.) ≈ 136s/cell × 22 ≈ **~2,992s ≈ ~50 minutes** for the full
  generation phase (both VPs, all 22 sessions). F4 analysis itself: seconds (zero LLM, pure
  numpy/rule-based).
- This is an upper bound — VP-003's relapse-peak sessions (S6/S7) may crisis-early-exit with fewer
  turns (fewer F1 calls), and any `no_questionnaire_indicated`/`item_bank_unpopulated` F3 outcome
  reduces the F3 line to 0.

### 7.4 Proposed acceptance criteria (for critic pre-registration, step 2)

1. **Direction verdict matches arc design per majority rule** — VP-001's overall `TrendVerdict`
   across the 11-session arc reads `improved` (allowing the S5 plateau to NOT flip the majority);
   VP-003's overall reads `worsened` or a documented non-monotonic pattern that explicitly surfaces
   the S6 relapse in `relapse_signals`-equivalent evidence — a clean `improved` verdict for VP-003
   would be a FAILED check, not a pass.
2. **Band transitions consistent with per-session F3 records** — every `severity` value in
   `scale_series` matches `survey_scorer.py`'s own published bands applied to that session's raw
   `total_score`, independently recomputed by qa (§7.2), never trusted from the artifact alone.
3. **No fabricated points in plot series** — every plotted (date, value) pair traces to a specific
   artifact + field (§7.2).
4. **Crisis dims non-silently degrade** — the S6/S7 (or wherever crisis actually lands, live
   behavior may differ from the design-intent table) session(s)' `session_sentiment` empty-dict
   case is correctly handled via the F1-8 fallback (§3.1), never crashes, never silently reports
   `sentiment: unknown` when Mode-A data exists.

### 7.5 What is NOT claimed

- No clinical validation of the arc scripts' realism beyond the persona-grounding cited in §2.2 —
  this is a technical pipeline exercise, not a clinical-adequacy study (that gate is
  clinical-validator's, `PLAN-2026-W29-D` step 3/10, `CVR-` entries, never merged with this
  document's own verdicts).
- No efficacy claim of any kind — F4 measures DATA-FIELD change direction, never treatment
  effectiveness, and never diagnoses (`is_diagnostic: Literal[False]`).
- No certification of F2's disease-candidate quality — `VAL-014` stays open and is explicitly
  inherited (§5.3 item 5).
- No claim that 2 VPs × 1 run each generalizes — this is a **single-batch** (n=1 arc per VP)
  약식 exercise, same "single-batch evidence" honesty standard the project already applies
  elsewhere (e.g. `PRD §3.9`'s Mandatory caveat 3 for `EXP-011`).
- **No stable-arc / false-positive-rate coverage this mission (REV-044 Issue 3 / ADR-036 item 2,
  accepted explicitly).** Both scripted arcs are net-directional (VP-001 improving,
  VP-003 relapsing-then-partially-recovering) — neither VP-001 nor VP-003 exercises a genuinely
  stable/no-significant-net-change patient, so this battery structurally cannot demonstrate F4's
  false-positive rate on a stable series (i.e., that F4 correctly reports `unchanged`/does not
  mis-fire a direction when nothing clinically changed). No 3rd VP or stable-arc cell was added
  this mission (budget: +11 sessions ≈ +50% cost for a quick-dev battery) — the `crisis_episode`/
  `worsening_sustained`/stable-arc taxonomy cells (§2.1) remain reserved for a future wider battery.
  MAY/MUST-NOT wording-table row 4 (REV-044) is binding on every report citing this mission's
  results: MAY say F4 correctly handled the crisis-session fallback and the non-monotonic wobble
  (S5, VP-001) without mis-firing; MUST NOT say F4's behavior on a genuinely stable/no-change
  patient was tested this mission.

---

## 8. Gaps → user questions

None found that block this design. Two items are flagged as **implementation-time decisions
already resolved by this design** (not gaps needing a user answer), stated here for
transparency:

1. Whether F4-quick uses a 3rd/4th VP or a different cadence — resolved by this document's own
   justified picks (§2.2/§2.3); revisit only if the user wants a wider battery.
2. Whether `08_temporal_retriever` should be reactivated alongside F4 — resolved as "stays parked"
   (§4.2) with a stated rationale; revisit only if the user explicitly wants semantic
   retrieval-over-history as a separate future feature.

If, during implementation (step 5), the live scripted sessions do not converge to anything close
to the design-intent CTRS/PHQ-9 targets in §2 (e.g. VP-003's scripted relapse never actually drops
CTRS, because the patient-LLM under scenario-guideline steering behaves differently than
design-intent assumed), that is an **implementation-time finding to report**, not a reason to
retroactively edit this design doc's arc table — the arc table states design intent, and §7.4's
acceptance criteria are written to tolerate and surface that divergence honestly rather than
requiring a hard pin.

---

## 9. Implementation wave plan

| Wave | Scope | Files | Done when |
|---|---|---|---|
| 1 | `src/f4.py` production module + `src/schemas/longitudinal.py` | new `src/f4.py`, new `src/schemas/longitudinal.py` | `analyze_longitudinal_series` runs on a hand-built synthetic `LongitudinalSeriesInput` (toy 3-session fixture) and produces a schema-valid `LongitudinalAnalysisOutput`; zero LLM/file I/O inside the analysis function (grep-verified: no `open(`/adapter import) |
| 2 | `src/f1.py` narrow isolation seam (§2.6 option C) | `src/f1.py` (2 kwargs + 1 field + 1 append block + 1 assignment + `.get()` fallback) | Existing F1 test suite green with zero new failures; a new smoke test proves a non-`None` `scenario_guideline` reaches `persona.system_prompt` and `scenario_pack_id` reaches the saved `conversation.json` |
| 3 | `tests/simulation/scenario_pack.py` — arc tables (§2.3/§2.4/§2.5) for VP-001 + VP-003 | new file, tests/ territory | Both arc tables importable, 11 entries each, `scenario_pack_id` uniqueness enforced at import time (fail-fast, mirrors `item_bank.py`'s own `validate_item_bank_completeness` pattern) |
| 4 | `continuous_test.py`: variable-cadence `session_offsets_days`, scenario-pack threading through `run_multi_session_chain`, new F4 post-loop stage | `continuous_test.py` | `--sessions 11` run with an explicit offsets list produces the exact day-offset dates from §2.3; F4 stage runs once after the loop and writes `temporal.json`/`_report.md`/PNGs; `STAGE_REGISTRY`'s F4 entry flips to `implemented=True` |
| 5 | `trend_plotter.py` extension (chart 5 slot-fill panel) + 2 new sibling functions (charts 3-4) | `src/services/trend_plotter.py` | Existing `test_trend_plotter.py` green unmodified; new tests for `generate_similarity_trend_plot`/`generate_domain_trend_plot`/the extended `TrendDataPoint.slot_fill_count` field, each on toy data |
| 6 | Tests: unit + mutation targets for trend math, HPI-isolation adversarial suite for `schemas/longitudinal.py` | new `tests/test_f4.py`, `tests/test_f4_hpi_isolation.py`, extend `tests/test_continuous_test.py` for the new STAGE_REGISTRY shape | qa mutation-checks the band-transition/slope/majority-vote logic (flip a threshold, confirm the test catches it) per this project's existing "non-vacuous" mutation-verification discipline (`REV-013` §3 precedent) |
| 7 | Live battery: 2 VPs × 11 sessions, F1→F2→F3→F4 chained | none (experiment-tracker territory) | All 22 session-cells run or explicitly SKIPPED with a reason; 2 `temporal.json` + reports + PNGs saved under `docs/ai/simulation_results/<VP>/` |

---

## Self-check (fabrication audit)

Every field path, function name, and line-number citation in this document was verified against an
opened file or a real on-disk artifact this session (§0 lists exactly which). No number in §7.3 is
presented as measured beyond what is explicitly marked "VERIFIED" (F1 wall-clock 96s, F2 latency
9,279.8ms) — the rest is explicitly labeled `[ESTIMATE]`. No arc-table clinical detail was invented
without persona-file grounding (VP-001's plateau uses the persona's own "새 프로젝트" pattern
consistent with its documented deadline-stress trigger; VP-003's relapse uses the persona's own
documented unemployment-benefit end date, `VP-003_first_visit_severe.md:75`).

**Linked:** `PLAN-2026-W29-D`. Reviewed repo artifacts (all read this session, no fabricated
paths/line numbers): see §0.
