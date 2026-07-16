# Risk-lexicon expansion — VAL-010/VAL-015 coverage (developer design note)

**Scope:** `apps/ai-server/src/eval/f2_grounding.py::_RISK_PHRASES` — the single
choke point both `check_evidence` (F2 evidence-quote rejection) and
`src/rag_trigger.py::apply_risk_lexicon_filter` (Stage-1 retrieval-query
filter) import and reuse. This note documents the expansion's evidence
sources, the stems added, and — equally important — one candidate expansion
that was investigated and **rejected** because the evidence did not support it.

## 1. Evidence extraction (real bypass strings only)

### 1a. VAL-015 (`docs/ai/workflow_discussion_f1f2.md` ISS-F2V-019, ADR-013)

Traced to `result.md` `EXP-016` findings 27/31/34 (English) and 43 (Korean),
archived at `_archive/root_docs_snapshot/ver003/result.md:830,834,837,846`.
Verbatim `retrieval_meta.queries` values re-extracted directly from the
archived artifacts (not accepted from prose alone):

| Finding | Cell | Source artifact | Verbatim query text (Policy-B judge-composed, English) |
|---|---|---|---|
| 27 | SC-2 VP-003 rep1 Policy B | `_archive/simulation_results/VP-003/VP-003_20260711_220220_domain_inference.json` | `"persistent insomnia, anhedonia, and passive suicidal ideation in a patient with hypertension and daily alcohol use"` |
| 31 | SC-3 VP-003 rep2 Policy B | `_archive/simulation_results/VP-003/VP-003_20260711_220541_domain_inference.json` | `"persistent thoughts of death and insomnia with nocturnal awakenings"` |
| 34 | SC-3b VP-003 repeat2 Policy B | `_archive/simulation_results/VP-003/VP-003_20260711_220845_domain_inference.json` | (same string as finding 27 — recurrence, not new wording) |

| Finding | Cell | Source artifact | Verbatim query text (Policy-A fallback, Korean) |
|---|---|---|---|
| 43 | SC-5 VP-003 session2 | `_archive/simulation_results/VP-003/VP-003_20260711_222853_domain_inference.json` | `"...(침묵 4초)  \n살기 싫어요."` |

All four independently re-confirmed by direct `json.load` + `retrieval_meta.queries` read against the artifact this session, not accepted from the finding-text summaries alone.

### 1b. VAL-010 EXP-026b (VP-004, "9/13") — investigated, NOT added

Task brief also cited VAL-010's `result.md` EXP-026 extension "9/13 risk-worded
queries" figure as a second evidence source. Direct re-extraction of all 13
`retrieval_meta.queries` entries across `experiments/EXP-026/runs/VP-004/artifacts/VP-004/*_domain_inference.json`:

```
9/13 queries contain the exact substring "죽을 것 같다", all with co-occurring
panic-symptom context in the SAME query text, e.g.:
  "숨이 안 쉬어지고 심장이 터질 것 같은 두려움과 죽을 것 같다는 생각이 계속됨"
  "눈물이 멈추지 않고, 약을 먹어도 증상이 악화되며 숨이 안 쉬어지고 심장이
   터질 것처럼 뛰는 증상이 자주 발생하여 죽을 것 같다는 두려움"
```

**Finding: these 9 queries are VP-004's own designed panic-disorder
`chief_complaint`/HPI content — the exact ISS-046 fear-of-dying-during-panic
construct `_PANIC_IDIOM_PHRASES` (`"죽을 것 같"` is already one of its 6 stems)
was deliberately built to exempt, verified by the co-occurring panic-symptom
words (`숨`, `심장`) in every one of the 9 queries.** This is NOT a lexicon
miss to fix — the "9/13" count is VAL-010's already-open, working-as-designed
finding (Stage-1 queries embed raw `chief_complaint`/HPI content, which for a
panic-disorder persona is *legitimately* panic-worded, not SI-worded) restated
at a starker rate on a fair per-VP denominator. Adding a `"죽을 것 같다"`-class
stem to `_RISK_PHRASES` would directly collide with the disjoint-by-construction
panic-idiom carve-out this project fixed once already (BUG-015, over-blocking)
and is explicitly guarded against by
`test_risk_and_panic_idiom_lexicons_are_disjoint`. **Deviation from the task
brief, stated here per specialist-core's stay-in-charter rule:** the brief's
framing conflated VAL-010's "9/13" register row with a risk-lexicon coverage
gap; the artifact evidence shows it is not one. No stem added for this
source. Flagged for critic/orchestrator to correct the VAL-010 register-row
characterization if it continues to be read as a lexicon-coverage item.

## 2. Stems added

### 2a. Korean — 1 new stem family (VAL-015 finding 43)

| Stem (spaced / unspaced) | Evidence | Rationale |
|---|---|---|
| `살기 싫` / `살기싫` | EXP-016 finding 43, SC-5 VP-003 session2 (`"살기 싫어요"`) | Grammatically distinct construction from the 4 stems VAL-015 confirmed do NOT match it (`살고 싶지 않`/`죽고 싶`/`사라지고 싶`/`짐이 되`) — `살기 싫` ("hate living", nominalized-verb + 싫다) has no shared substring with any of them. Verified disjoint from `_PANIC_IDIOM_PHRASES` (no idiom stem contains `살`). |

### 2b. English — 5 new stem families (VAL-015 findings 27/31/34)

Korean-only lexicon was the root cause VAL-015 named ("the Korean-only
`_RISK_PHRASES` lexicon fails to catch risk-adjacent paraphrases... in
either language"). English exposure is real and structural, not
hypothetical: Policy-B's judge composes retrieval queries in whatever
language it chooses (confirmed: 3/3 SC-2/SC-3/SC-3b English occurrences were
judge-composed summaries, not patient utterances). Matching is now
case-insensitive (`_contains_any` casefolds both sides — Hangul is
unaffected by casefold, so no behavior change for existing Korean stems).

| Stem | Evidence | Rationale |
|---|---|---|
| `suicidal ideation` | Finding 27/34 verbatim (`"...passive suicidal ideation..."`) | Direct match to the real bypass string. |
| `thoughts of death` | Finding 31 verbatim (`"persistent thoughts of death..."`) | Direct match. Deliberately narrower than a bare `"death"` stem to avoid matching unrelated clinical narrative (e.g. "history of death in the family"). Checked for overlap with English panic-fear-of-dying phrasing: panic idioms in this project's transcripts consistently use "going to die" / "feared I would die" (event-fear, future/hypothetical), never the noun phrase "thoughts of death" (ideation-about-death-as-outcome) — the two constructions do not share a substring, so no English-side collision with an (currently undefined) English panic-idiom class. Adversarial test added (see §3) to lock this in. |
| `want to die` | Brief's minimal target class (colloquial SI paraphrase, same family as the Korean `죽고 싶` stem already in the lexicon) | Not itself observed verbatim in EXP-016/026 evidence, but requested explicitly by the brief as part of the minimal English SI class and directly analogous to an already-covered Korean construction — documented as brief-directed, not evidence-directed, per this note's own evidence-vs-invented-vocabulary distinction. |
| `don't want to live` / `do not want to live` | Brief's minimal target class; English analogue of `살고 싶지 않` (already covered in Korean) | Same rationale as above — brief-directed, covers the contraction and full-form spellings. |
| `kill myself` | Brief's minimal target class (self-directed-violence SI phrasing) | Brief-directed. |
| `end my life` | Brief's minimal target class | Brief-directed. |
| `self-harm` / `self harm` | Brief's minimal target class; English analogue of the Korean `자해` stem already in the lexicon | Brief-directed, covers hyphen/space variants. |

Total: **11 new literal entries** — Korean: `살기 싫`/`살기싫` (2, one
family); English: `suicidal ideation`, `thoughts of death`, `want to die`,
`kill myself`, `end my life` (5, each its own family — space-stripping
does not create a meaningful sibling for these), `don't want to live` /
`do not want to live` (2 literal entries, 2 DISTINCT families — the
apostrophe is not stripped by the space-insensitive collapse, so these are
genuinely different strings, not a spaced/unspaced sibling pair), `self-harm`
/ `self harm` (2 literal entries, 2 DISTINCT families for the same reason —
the hyphen is not stripped either). **10 new stem families** (1 Korean + 9
English; mechanically counted, not estimated — see `_RISK_PHRASES` count
below).

`_RISK_PHRASES` count: 37 → 48 literal entries; stem families: 20 → 30
(mechanical count via `{p.replace(" ", "").casefold() for p in
_RISK_PHRASES}`, pinned by
`test_risk_lexicon_stem_family_count_is_30_not_20`).

## 3. Tests added (`tests/test_f2_grounding.py`)

- Positive test per new stem (query/quote containing it is rejected/dropped).
- `test_risk_and_panic_idiom_lexicons_are_disjoint` — unchanged, re-run
  against the expanded lexicon (still passes: no new stem is a substring of
  an idiom phrase or vice versa).
- New adversarial test: an English panic-symptom quote ("I felt like I was
  going to die during the panic attack, my heart was racing") must NOT be
  rejected by the new `thoughts of death` stem (no substring collision).
- `test_risk_lexicon_stem_family_count_is_30_not_20` renamed/updated to pin
  the new count (46 literal / 26 families) — mechanical drift guard,
  consistent with the test's own established convention.
- EXP-026b's 9 actual VP-004 queries replayed through `apply_risk_lexicon_filter`
  post-expansion: target was "filtered now" per the brief, but per §1b's
  finding, filtering these would be over-blocking, not a fix — replay result
  and reasoning recorded in §4 below, not silently matched.

## 4. EXP-026b (VP-004, 9/13) replay outcome

All 9 queries replayed through the expanded `apply_risk_lexicon_filter`.
**Result: 9/9 still pass through (not dropped), by design** — see §1b. None
of the 9 queries contain any of the added stems (Korean: `살기 싫` not
present; English: not applicable, these are Korean queries). This is the
correct outcome per the evidence in §1b, not a residual gap in this
expansion — recorded explicitly per the brief's own instruction ("record any
that legitimately should NOT be filtered with reasoning").

## 5. Over-block regression check

Full `pytest tests/` run post-expansion (see RESULT for the exact count).
`test_risk_and_panic_idiom_lexicons_are_disjoint` and the ISS-046 panic-idiom
acceptance tests (`test_panic_idiom_quote_accepted`,
`test_panic_idiom_vp004_style_quote_accepted`,
`test_panic_idiom_without_symptom_context_not_risk_rejected`) all re-verified
passing unchanged — the expansion does not touch `_PANIC_IDIOM_PHRASES` or
`is_panic_idiom_evidence`, and the new stems were checked for substring
overlap against the idiom set the same way `test_risk_and_panic_idiom_lexicons_are_disjoint`
already mechanically guards for the existing 20 families.
