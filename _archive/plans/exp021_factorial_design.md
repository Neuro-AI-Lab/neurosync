# EXP-021 factorial design — isolating the v0→v1 over-endorsement driver (ISS-F2V-028)

> Author: brainstorm | 2026-07-13 | `PLAN-2026-W29-B` step 1c
> Status: **design only — no code, no runs.** Ready for critic pre-registration (`PLAN-2026-W29-B` step 4, `REV-040`).
> Answers the design REV-039 §(3) recommended and CVR-017 Recommendation 2 endorsed: isolate which
> of the three v0→v1 bundled changes drives F3's whole-instrument over-endorsement finding
> (`REV-039`/`CVR-017`, `result.md` `[EXP-020]`).

---

## 0. Provenance and what this design must not re-litigate

`EXP-020` bundled three simultaneous changes when it moved item bank v0 → v1:
item text (bare 2-4 word construct labels → full official sentences), response-anchor presence
(none → a 4-point Pfizer menu), and instruction/timeframe wording (none → the official "지난 2
주일 동안…" preamble). `REV-039` §(3) states this explicitly, byte-verified against
`apps/ai-server/tests/simulation/survey_answer_llm.py:52-178`: *"three variables changed
simultaneously between v0 and v1, confirmed by direct code read, not inference."* The resulting
finding — PHQ-9 totals 18/20 vs. documented 7, GAD-7 total 17/severe vs. documented ~8 — is real
and independently reproduced twice (`experiment-tracker` and `critic`), but **"cannot distinguish
which of the three bundled variables (or their interaction) is responsible"** (`REV-039` §(3)).
`CVR-017` Recommendation 2 and `REV-039` §(3)'s own follow-up sketch both call for exactly the
design below.

This design does **not** re-open: item-8's specific status (already settled — `CVR-017` Q1/`REV-039`
row 6: item 8 is no longer the instrument's outlier, so this design treats item 8 as one of nine
equally-weighted items, not a special case); item-bank v1's content fidelity (CVR-016/CVR-017's
closed charter); GAD-7/AUDIT-C (out of scope per brief — VP-001 PHQ-9 only); or F2 candidate
selection (`VAL-014`/`ISS-F2V-026`, untouched).

---

## 1. Question and hypotheses

**Question:** of item text (F_text), response-anchor presence (F_anchor), and instruction/timeframe
presence (F_instr), which single factor — if any — is the dominant driver of PHQ-9 whole-instrument
over-endorsement in `SurveyAnswerLLM`, holding persona, model, temperature, and item order fixed?

Each hypothesis below is scored against the same response variable (total deviation from documented,
§4) via the same pre-registered decision rule (§4.3). All four are mutually exclusive as *licensed
claims*; more than one may be operative as an unlicensed *interaction* (§4.3 outcome (b)).

| ID | Claim | Prediction | Falsifier |
|:--|:--|:--|:--|
| H1 (F_text dominant) | Item-text richness (v0 bare label vs. v1 full official sentence) is the dominant driver of total-deviation elevation, independent of anchor/instruction presence. | `Effect(F_text)` (§4.3) is the largest-magnitude main effect, exceeds `Effect(F_anchor)` and `Effect(F_instr)` by ≥3 points, and exceeds the noise bound σ (§4.3). | `Effect(F_text)` fails either the margin-over-second-factor test or the noise-bound test. |
| H2 (F_anchor dominant) | Presence of the 4-point response-anchor **menu format** (regardless of item-text length) is the dominant driver — a menu/acquiescence-format effect, the mechanism `REV-039`/`CVR-017` flagged as "plausible, literature-consistent... but unverified." | `Effect(F_anchor)` is the largest-magnitude main effect, clears the same margin+noise-bound test. | Analogous to H1. |
| H3 (F_instr dominant) | Presence of the official timeframe/instruction preamble is the dominant driver (e.g. by cueing "this is an official clinical instrument, answer carefully/inclusively"). | `Effect(F_instr)` is the largest-magnitude main effect, clears the same test. | Analogous to H1. |
| H0 (no dominant factor) | None of the three factors independently dominates at this sample size; the shift is either interaction-driven or not attributable to any single bundled variable given n=1 per non-corner cell. | No main effect clears the margin+noise-bound test; check interaction contrasts next (§4.3 outcome tree). | A main effect unambiguously clears the test (H1/H2/H3 licensed instead). |

**Framing constraint (binding on any report of this experiment):** because F_anchor and F_instr can
only ever test *v1's own* anchor set / instruction text (v0 never shipped either — there is no
independently-sourced "v0 anchor set" to test against), this design isolates *presence/format* of
v1's anchor and instruction machinery from item-text richness — it does not, and cannot, test
whether some *other* anchor or instruction wording would behave differently. State this explicitly
in any downstream citation.

---

## 2. Cells

Full 2×2×2 = 8 cells. Single persona **VP-001**, scale **PHQ-9 only**, one administration per cell
(one administration = 9 item-level `SurveyAnswerLLM` calls, per the brief's own accounting — no
F1/F2 pipeline calls are needed or incurred, see §5).

| Cell | F_text | F_anchor | F_instr | Description | Corresponds to |
|:--:|:--:|:--:|:--:|:--|:--|
| 1 | v0 | off | off | v0 bare label, bare `[0-3]` integer ask, no instruction | **= EXP-019 Cell 1 v0 corner (historical)** |
| 2 | v0 | off | on | v0 bare label + instruction preamble, no anchor menu | new mixed cell |
| 3 | v0 | on | off | v0 bare label + anchor menu, no instruction | new mixed cell |
| 4 | v0 | on | on | v0 bare label + full v1 anchor+instruction scaffolding | new mixed cell |
| 5 | v1 | off | off | v1 full official sentence, bare `[0-3]` integer ask, no anchor/instruction | new mixed cell |
| 6 | v1 | off | on | v1 full sentence + instruction, no anchor menu | new mixed cell |
| 7 | v1 | on | off | v1 full sentence + anchor menu, no instruction | new mixed cell |
| 8 | v1 | on | on | v1 full sentence + anchor menu + instruction (the shipped v1 combination) | **= EXP-020 Cell A v1 corner (historical)** |

### 2.1 Corner cells vs. historical data — replicate or reference only?

**Cell 1 (v0/off/off) ↔ `EXP-019` Cell 1** (`result.md` lines 1306-1329): VP-001 two-session chain,
PHQ-9 v0, responses `[1,1,3,2,1,1,2,2,0]`=13 (session 1) and `[2,1,3,2,1,2,2,2,0]`=15 (session 2).
**Cell 8 (v1/on/on) ↔ `EXP-020` Cell A** (`result.md` lines 1440-1449): VP-001 two-session chain,
PHQ-9 v1, `[2,2,3,2,2,2,3,2,0]`=18 (session 1) and `[3,3,3,2,2,2,3,2,0]`=20 (session 2).

**Ruling: these count as genuine replicates (n=2 each), not merely reference points, subject to one
pre-run comparability check.** Justification, grounded directly in code:

- `SurveyAnswerLLM`'s own module docstring (`survey_answer_llm.py:16-17`): *"A NEW, separate client
  instance per survey administration — no shared `_history` with an in-progress F1 conversation."*
  The `_ask` method (`survey_answer_llm.py:170-186`) builds its message list from
  `self.persona.system_prompt` (the persona's static Section-6 text) plus the per-item prompt only —
  it never reads F1 conversation content. This means EXP-019's/EXP-020's session-1 and session-2
  administrations are **structurally independent draws of the identical prompt**, not two draws
  conditioned on different dialogue histories — the F1 session number is immaterial to what
  `SurveyAnswerLLM` sees.
- Both historical corners were produced by the **unmodified, currently-shipped** `_build_prompt`
  code path: Cell 1 = the `if not item.response_anchors:` branch (`survey_answer_llm.py:150-154`,
  v0's `_PHQ9_ITEMS_V0` items all have `response_anchors=None`); Cell 8 = the anchor-menu branch
  (`survey_answer_llm.py:156-168`) with `scale_name="PHQ-9"` supplying `instruction_ko` via
  `_resolve_instruction` (`survey_answer_llm.py:87-102`) from v1's `_PHQ9_INSTRUCTION_KO_V1`
  (`item_bank.py:246-249`). **No new harness code is needed to reproduce either corner exactly** —
  they are literal instances of what the current code already does.
- Model identity and temperature are hardcoded unconditionally at `survey_answer_llm.py:178`
  (`temperature=0.7`), with no branch on item-bank version — confirmed by `REV-039` §(3) as "not a
  plausible confound."

**Binding pre-run comparability check (experiment-tracker, before pooling):** before treating
historical n=2 as pooled with any new EXP-021 corner replicates, re-verify (a) `VP-001_first_visit_mild.md`
md5 unchanged since EXP-020 (`4534a96a1e913ee2bb85cab0926ae2f6`, per `result.md` EXP-020 Setup);
(b) `LG_K_EXAONE_ENDPOINT_ID`/`LG_K_EXAONE_API_KEY` env values unchanged; (c) `git diff` empty for
`tests/simulation/survey_answer_llm.py`'s `_build_prompt`/`_ask`/`__init__` methods since EXP-020
(the factorial-generalization changes in §5 must not have altered the two corner code paths'
*output*, only added new capability — a byte-identical-output unit test on the two corner
configurations, pre- and post- harness change, is a required qa check, §5). **If any of (a)-(c)
fails, downgrade historical data to reference-only for that corner** and rely solely on new EXP-021
replicates for the noise bound (§4.3); the corner-cell *classification* (which cell each historical
run maps to) still holds regardless.

### 2.2 Budget allocation (~8-12 administrations)

| Tier | Spend | Cumulative administrations | What it buys |
|:--|:--|:--:|:--|
| Tier 0 (mandatory) | 8 base cells, 1 administration each | 8 | Full factorial coverage — one draw per combination |
| Tier 1 (recommended, if 2 more available) | +1 replicate each on Cell 1 and Cell 8 | 10 | Within-battery n=2 per corner (matching, not just referencing, the historical n=2), strengthening the noise-bound estimate (§4.3) with data collected in the same batch/git-HEAD as the mixed cells |
| Tier 2 (ideal, if 4 more available) | +2 replicates each on Cell 1 and Cell 8 | 12 | Within-battery n=3 per corner; pooled n=5 per corner if §2.1's comparability check passes |

Non-corner cells (2-7) are **not** replicated under this budget — n=1 each is a deliberate,
disclosed limitation (see §6), not an oversight. If tracker/orchestrator later judge more budget
available, replicate a non-corner cell before adding a third corner replicate (more informative for
resolving H1 vs H2 vs H3 than tightening an already-anchored corner's noise estimate further).

---

## 3. Constants (code-grounded — every item below is quoted from the file that enforces it)

| Constant | Value / mechanism | Source |
|:--|:--|:--|
| Model | K-EXAONE via `friendli.ai`, `base_url="https://api.friendli.ai/dedicated/v1"`, model id from `LG_K_EXAONE_ENDPOINT_ID` | `survey_answer_llm.py:70,74-75` |
| Temperature | `temperature=0.7` — hardcoded, unconditional, no branch on item-bank version | `survey_answer_llm.py:178` |
| Persona context mechanism | `messages = [{"role": "system", "content": self.persona.system_prompt}, {"role": "user", "content": user_content}]` — one fresh `openai.AsyncOpenAI` client per `SurveyAnswerLLM` instance, no shared history with any F1 conversation | `survey_answer_llm.py:66-81,171-174` |
| Persona | VP-001 only (`docs/ai/personas/VP-001_first_visit_mild.md`), loaded via `tests.simulation.patient_llm.load_persona` — Section 6 system prompt is session-index-invariant (one block, no per-session variant) | `VP-001_first_visit_mild.md:155-188` |
| Item order | Index 1-9, fixed — both `_PHQ9_ITEMS_V0` and `_PHQ9_ITEMS_V1` tuples share the identical index/construct order (흥미·우울감·수면·피로·식욕·자책감·집중력·정신운동·자살), iterated via `for item in entry.items:` | `item_bank.py:158-168,260-307`; `f3.py:235` |
| Response range | `response_min=0, response_max=3` for every PHQ-9 item, both versions | `item_bank.py:146-151,190-196` |
| Retry/clamp mechanics | One re-prompt on unparseable/out-of-range; still-failing → clamp to nearest bound + `logger.warning`; never a silent default. Held identical across all 8 cells — only prompt *content* varies per cell, never this control flow. | `survey_answer_llm.py:107-142` |
| Scoring code | `score_survey("PHQ-9", responses, patient_sex=patient_sex)` inside `administer_survey` — delegates to `_score_phq9`, which consumes only `responses: list[int]` and has zero dependency on which item-bank version produced them | `f3.py:239`; `survey_scorer.py:46-84` |
| Severity bands (unchanged, byte-frozen) | `[(0,4,"minimal"),(5,9,"mild"),(10,14,"moderate"),(15,19,"moderately_severe"),(20,27,"severe")]` | `survey_scorer.py:37-43` |
| Item-bank source-of-truth discipline | `text_ko`/`response_anchors` strings for both v0 and v1 must be **read directly** from `item_bank.get_item_bank_v0("PHQ-9").items` and `item_bank.get_item_bank("PHQ-9").items` respectively — the harness driver MUST NOT hand-retype these strings (transcription-fidelity risk this project has flagged before, `CVR-016` Finding 3) | `item_bank.py:559-585` (existing accessors) |

**What varies, exhaustively:** only the constructed prompt string passed as `user_content` to
`_ask()` — specifically, whether `text_ko` is drawn from the v0 or v1 tuple, whether a
`response_anchors` dict is attached (`None` vs. v1's `_PFIZER_PHQ9_ANCHORS_V1`), and whether an
`instruction_ko` line is prepended (`None` vs. v1's `_PHQ9_INSTRUCTION_KO_V1`). Nothing else in the
pipeline changes cell-to-cell.

---

## 4. Metrics (pre-registerable)

### 4.1 Per-administration metrics

Documented VP-001 PHQ-9 ground truth (`VP-001_first_visit_mild.md:81-94`): items
`[1,1,2,1,1,0,1,0,0]`, total **7**.

| Metric | Definition |
|:--|:--|
| Response vector | `v = [v_1..v_9]`, each `v_i ∈ [0,3]` |
| Per-item signed deviation | `d_i = v_i − doc_i` where `doc = [1,1,2,1,1,0,1,0,0]` |
| Per-item absolute deviation | `|d_i|` |
| Total score | `S = Σv_i` |
| Total deviation (primary response variable) | `D = S − 7` (signed — directionally meaningful given every prior finding in this program is over-endorsement, never under) |
| Mismatch count | count of `i` where `|d_i| > 1` (outside the ±1 band — the same convention used throughout `f3_quick_dev_plan.md` §8 / `CVR-015` / `REV-037` / `REV-039`, kept identical for cross-battery comparability) |
| Severity band | bucketed from `S` via `_PHQ9_SEVERITY` (§3) |
| Band-shift | `band_index(S) − band_index(7)`, where band_index runs 0(minimal)…4(severe); documented total 7 sits in band 1 (mild) |

### 4.2 Per-cell aggregate metrics

For each of the 8 cells, compute the cell mean of `D` across that cell's own replicates (n=1 for
cells 2-7 under Tier 0; n=2-3 for cells 1/8 depending on tier). **Cell means, not pooled
observations, are the unit of the factorial contrast (§4.3)** — this keeps the design a balanced
2×2×2 regardless of unequal replicate counts at the two corners.

### 4.3 Main-effect contrast and the dominant-factor decision rule

For each factor `F ∈ {F_text, F_anchor, F_instr}`:

```
Effect(F) = mean_over_4_cells(cell_mean_D | F = ON) − mean_over_4_cells(cell_mean_D | F = OFF)
```

where "4 cells" at each level means the 4 cells sharing that factor setting, each cell's own
replicate-averaged `D` weighted equally (not weighted by n) — the standard balanced 2³ factorial
main-effect contrast.

Two-way and three-way interaction contrasts, standard factorial formulas (needed for the outcome
tree below):

```
Interaction(A,B) = [mean(A=on,B=on) − mean(A=on,B=off)] − [mean(A=off,B=on) − mean(A=off,B=off)]
```
each inner mean averaged over the third factor's two levels (2 cells each); the three-way
interaction is the analogous alternating sum over all 8 cell means.

**Noise bound σ:** the observed within-corner-cell replicate range (max−min of total score `S`,
not `D`) at Cell 1 and Cell 8, using whichever data set (historical, new, or pooled) §2.1's
comparability check licenses. **Historical floor (usable if 0 new corner replicates are run):**
Cell 1 range = |15−13| = 2; Cell 8 range = |20−18| = 2 → σ = max(2,2) = 2, **disclosed explicitly as
a historical reference floor, not a value measured this battery**, and flagged as a likely
*undercount* of true replicate variance (n=2 ranges systematically underestimate population range).
If Tier 1/2 replicates are run, recompute σ from the larger (historical+new pooled, or new-only)
range at each corner and use `σ = max(range_corner1, range_corner8)`.

**Pre-stated margin:** `margin_m = 3` points on the `D`/total-score scale — chosen because it is
roughly half of the smallest whole-instrument shift this program has already treated as clinically
material (v0→v1's own 5-7 point total-score jump, `REV-039`/`CVR-017`), and because a single PHQ-9
item swing is worth up to 3 points — requiring the top factor to beat the second by more than one
full item's possible range sets a defensible, pre-committed bar rather than an post-hoc one.

**Decision rule, applied in this order:**

1. Rank `|Effect(F_text)|, |Effect(F_anchor)|, |Effect(F_instr)|` descending: `E₍₁₎ ≥ E₍₂₎ ≥ E₍₃₎`.
2. **Dominant-factor claim licensed IFF** `(E₍₁₎ − E₍₂₎) ≥ margin_m` **AND** `E₍₁₎ > σ`. If both hold,
   the top-ranked factor's hypothesis (H1/H2/H3, §1) is licensed as "supported at this n" — **never**
   as "confirmed" or "the mechanism" (see §6).
3. **If rule 2 fails:** compute all four interaction contrasts (three 2-way + one 3-way). If the
   largest-magnitude interaction contrast clears the same test (`≥ margin_m` above the next-largest
   contrast among {main effects, interactions} **AND** `> σ`), report outcome **"interaction-driven"**
   — name the specific interacting factors, do not claim a single dominant factor.
4. **If neither rule 2 nor rule 3's interaction test clears:** report outcome **"no dominant factor /
   inconclusive"** — explicitly state this is the statistically expected outcome given n=1 for 6 of
   8 cells, not a failure of the design (§6).

No discretion is exercised at run time beyond arithmetic — every threshold is stated here, before
any cell runs.

---

## 5. Harness requirements

**Binding constraint (repeated from the brief, non-negotiable): harness/`tests/simulation/` side
only. ZERO production changes.** Files that MUST NOT be touched by this experiment:
`apps/ai-server/src/f3.py`, `apps/ai-server/src/scoring/item_bank.py`,
`apps/ai-server/src/scoring/survey_scorer.py`, `apps/ai-server/src/continuous_test.py`,
`apps/ai-server/src/f2.py`, `apps/ai-server/src/f1.py`, `src/agents`, `src/schemas`, `src/routes`.
qa's step-4 gate check is a `git diff --name-only` sweep against exactly this path list, the same
discipline already established for EXP-019 (`REV-037` HPI-isolation methodology precedent) and
EXP-020 (`ADR-033`(6)).

### 5.1 A pre-existing production seam this design reuses, not invents

`f3.administer_survey(scale_name, answer_fn, *, item_bank: Mapping[ScaleName, ItemBankEntry] | None
= None, ...)` (`f3.py:206-240`) and `f3.resolve_outcome(..., *, item_bank: ... | None = None)`
(`f3.py:150-179`) **already accept an `item_bank` override** — an existing test seam, not a new
capability. This means the EXP-021 driver can bypass the full `continuous_test.py` F1→F2→F3 chain
entirely and call `f3.administer_survey("PHQ-9", answer_fn, item_bank={"PHQ-9": <cell's hybrid
entry>})` directly — **no F1 dialogue turns, no F2 RAG calls needed or incurred**, consistent with
the brief's "one administration = 9 item-level answer-LLM calls" framing. This is a materially
cheaper and cleaner design than routing every cell through the full chain, and it removes F1/F2 as a
confound entirely (SurveyAnswerLLM's context is persona-system-prompt-only regardless, §3, so
nothing is lost by skipping F1/F2).

### 5.2 New harness work required

1. **Additive constructor extension on `SurveyAnswerLLM`** (`tests/simulation/survey_answer_llm.py`
   — already a harness-only file per its own module docstring, line 1: `"HARNESS ONLY, never
   src/"`). Currently, `instruction_ko` is resolved *only* via `scale_name` → `get_item_bank(scale_name).instruction_ko`
   (`_resolve_instruction`, lines 87-102), which is hardcoded to the module-level v1 `ITEM_BANK` —
   this cannot express "instruction ON, but text/anchors are a custom hybrid," which the factorial
   needs. Add an explicit override parameter (e.g. `instruction_ko_override: str | None | _UNSET =
   _UNSET`, sentinel-typed so "not passed" still falls back to the existing `scale_name`-based
   resolution — fully backward-compatible with every existing v0/v1 caller) that takes precedence
   when supplied. This is the only change to an existing method signature; everything else is new,
   additive code.
2. **Prompt-construction generalization.** `_build_prompt`'s current branch (`if not
   item.response_anchors: <bare ask> else: <anchor menu, with an optional instruction line>`,
   lines 144-168) structurally couples "instruction visible" to "anchor menu visible" — under the
   *current* code, F_instr=ON with F_anchor=OFF is not producible. The factorial needs these
   independent. Functional (non-binding) sketch for developer:
   ```
   def _build_prompt_factorial(text_ko, response_min, response_max, anchors, instruction) -> str:
       lines = []
       if instruction:
           lines.append(instruction)
       if anchors:
           anchor_text = " / ".join(f"{v}: {label}" for v, label in sorted(anchors.items()))
           lines.append(f"문항: {text_ko}")
           lines.append(f"응답 척도: {anchor_text}")
           lines.append(f"위 응답 척도 중 당신의 상태를 가장 잘 나타내는 숫자 하나만 답하세요 ({response_min}-{response_max}).")
       else:
           lines.append(
               f"다음 항목에 대해 지난 2주간 당신의 상태를 가장 잘 나타내는 숫자를 "
               f"{response_min}-{response_max} 사이에서 하나만 답하세요: {text_ko}"
           )
       return "\n".join(lines)
   ```
   Required qa check: with `anchors=None, instruction=None` this must reproduce Cell 1's byte-exact
   prompt (the current v0 bare-ask branch); with `anchors=<Pfizer set>, instruction=<PHQ9 instruction>`
   it must reproduce Cell 8's byte-exact prompt (the current v1 branch) — a golden-string unit test
   for both corners is the qa mutation-check target, not just "the code runs."
3. **Hybrid item-bank builder** (new module or function under `tests/simulation/`): for each of the 8
   cells, build a `tuple[ScaleItem, ...]` by pairing, per index 1-9, the `text_ko` from
   `get_item_bank_v0("PHQ-9")` or `get_item_bank("PHQ-9")` (per F_text) with `response_anchors=None`
   or the v1 anchor dict extracted from the same `get_item_bank("PHQ-9")` items (per F_anchor) —
   never hand-retyped (§3). Wrap into an `ItemBankEntry` (the existing frozen dataclass,
   `item_bank.py:110-117`) with a descriptive `version`/`provenance` string encoding the cell's three
   factor levels (e.g. `"exp021-cell5-v1text-noanchor-noinstr"`), and `populated=True`.
4. **Thin CLI/driver script**, `experiments/EXP-021/run_factorial_cell.py` (experiment-specific,
   following the `experiments/EXP-020/isolation_grep.py` precedent of an experiment-scoped script
   living under its own `experiments/EXP-0NN/` directory) — imports only from `tests.simulation.*`
   and calls `src.f3.administer_survey`/`src.scoring.survey_scorer.score_survey`, the same
   harness→production import direction `continuous_test.py` already establishes, never reversed.
   Args: `--cell {1..8}`, `--replicate-index N`, `--persona VP-001` (fixed default), `--out
   experiments/EXP-021/runs/<label>/`.
5. **Structural labeling (ADR-033(6) precedent, binding).** `ADR-033` decision 6 requires forced-mode
   F3 evidence to be "loudly labeled... in the ledger and every artifact," implemented as a
   first-class `administration_mode` field (never inferable only from a CLI invocation or run.log).
   EXP-021 bypasses the production ledger entirely (§5.1), so its equivalent is a `cell_config.json`
   sidecar written per run, containing at minimum: `{"cell": 5, "text_source": "v1", "anchors":
   false, "instruction": false, "replicate_index": 0, "persona_id": "VP-001", "model": "<endpoint
   id>", "temperature": 0.7}` — alongside the raw `responses.json`/`score_result.json`. No downstream
   consumer of an EXP-021 artifact may infer factor levels from directory naming alone.
6. **Artifact location.** All artifacts under `experiments/EXP-021/runs/<cell_label>/`, one
   subdirectory per (cell, replicate) pair, e.g. `runs/cell1_v0_off_off_rep0/`,
   `runs/cell1_v0_off_off_rep1/` for a Tier-1/2 replicate.

### 5.3 qa gate scope (for step 4a of whatever plan dispatches this)

- `git diff --name-only` clean against the production path list above.
- Golden-string byte-identity unit tests: generalized prompt builder reproduces Cell 1's and Cell
  8's exact current-code output (§5.2 item 2).
- Hybrid item-bank builder unit tests: for both F_text levels, the extracted `text_ko`/anchor
  strings match `get_item_bank_v0`/`get_item_bank`'s own values exactly (no transcription drift).
- Retry/clamp logic mutation-check: confirm it fires identically regardless of which cell's prompt
  is in play (i.e., the change did not accidentally alter `answer()`'s control flow, only
  `_build_prompt`).

---

## 6. Interpretation limits

- **n=1 per non-corner cell (6 of 8) at temperature 0.7 is exploratory, not confirmatory.** A single
  stochastic draw cannot separate a true main effect from within-cell sampling noise for those six
  cells — only Cells 1 and 8 carry any noise-bound estimate at all (§4.3), and even that estimate
  (historical range=2, or a slightly larger Tier-1/2 in-battery range) is itself a low-n estimate of
  the true population spread. The dominant-factor rule (§4.3) is deliberately conservative
  (margin AND noise-bound, both must clear) precisely because of this; **"no dominant factor /
  inconclusive" should be treated as the modal, expected outcome of this battery, not a failed
  experiment.** If a clean single-dominant-factor result does occur, report it as
  hypothesis-generating for a larger-n follow-up (`REV-039` §(3): "≥4-5 independent personas per
  condition" before attributing directional weight to any one variable) — never as a settled
  mechanism claim.
- **Isolates structurally, does not add statistical power.** This design's advance over `EXP-020` is
  that each of the 8 cells has one unambiguous combination of factor levels (unlike EXP-020, which
  bundled all three inside one v0-vs-v1 comparison) — that is real, load-bearing progress on the
  *design* axis. It is a separate claim from statistical power, which this battery does not
  materially improve for the 6 non-corner cells. State both properties together in any report; do
  not let "isolated by design" imply "resolved with confidence."
- **Single persona, VP-001 only.** No cell in this design uses any other persona. Findings do not
  generalize to other documented severities/personas without replication — the same caveat `CVR-017`
  and `REV-039` already applied to `EXP-020`'s whole-battery finding.
- **Mechanism claims stay UNVERIFIED unless the design itself isolates them (REV-039 §(4) row 10,
  echoed here).** This design isolates the three *named* factors (text/anchor/instruction) from
  each other structurally — but it cannot isolate any variable this design did not think to name
  (e.g., prompt length in raw character count, independent of which of the three named factors
  produced that length; response-format habituation across the 9-item sequence; or an unmeasured
  confound in how K-EXAONE was fine-tuned/aligned). A licensed H1/H2/H3 finding is evidence *for*
  that named factor over the other two named factors, at this n — not proof that no other unnamed
  variable is responsible.
- **A fix recommendation from this experiment may target ONLY the harness, never production**
  (pre-committed, matching `PLAN-2026-W29-B` step 9's own gate: "T3 harness-side fix ONLY if CV+critic
  license"). Even a clean, well-powered H1/H2/H3 result licenses at most a `SurveyAnswerLLM`
  prompt-construction adjustment as a *simulator-fidelity* fix — it says nothing about whether item
  bank v1's *content* (the CVR-016/CVR-017-gated production data in `item_bank.py`) is itself
  correct or should change. Conflating "the simulator over-endorses under v1's prompt format" with
  "v1's item text is wrong" is exactly the error `REV-039`/`CVR-017` already warned against for the
  narrower item-8 case; this design must not reintroduce it at the whole-instrument scale.
- **The documented persona ground truth is itself a construct-validity assumption, not an
  independently clinically validated target.** `VP-001_first_visit_mild.md`'s per-item table (total
  7) is a project-authored expected-score table, not a real patient's verified PHQ-9 result. Every
  deviation metric in §4 measures distance from *that documented table*, i.e. evidence about
  `SurveyAnswerLLM`'s behavior relative to the persona-authoring intent — not evidence about the real
  PHQ-9 instrument's clinical accuracy.

---

**Linked:** `PLAN-2026-W29-B` (step 1c), `REV-039` §(3)/§(4) row 10, `CVR-017` Q1/Q2/Recommendation
2, `REV-038` (bundled-change qualifier precedent), `ADR-033` decision 6 (structural-labeling
precedent), `EXP-019` Cell 1, `EXP-020` Cell A, `ISS-F2V-028`, `item_bank.py`, `survey_answer_llm.py`,
`f3.py`, `survey_scorer.py`, `VP-001_first_visit_mild.md`.
