# Design note: "AI 예상질환" (AI-predicted disease) entity — structural HPI isolation

**Status:** design proposal only, no code. Written for PLAN-2026-W28-H Track B (`discussion.md`).
**Author:** brainstorm | **Date:** 2026-07-09
**Rules on final calls:** critic rules on the regulatory red-line adequacy and the
similarity-vs-probability label (this note recommends, does not decide).

## 0. What already exists (verified by reading code, not assumed)

- `SlotData` (`apps/ai-server/src/schemas/handoff.py:11-33`) is a closed Pydantic `BaseModel`
  with a fixed, explicitly-named field list (chief_complaint, history_of_present_illness, ...).
  It has **no** dynamic/dict-typed slot bucket and no field for disease predictions.
- The *only* production writer of `SlotData` is `Orchestrator._build_handoff_input()`
  (`apps/ai-server/src/agents/orchestrator.py:459-514`), which constructs it by explicit
  keyword arguments read from `state.slot_data` (a dict populated by `ClinicalSlotAgent`
  only). There is no code path today that reads any `DomainInferenceOutput`/F2 field into
  this function.
- `HandoffGeneratorAgent._build_user_content(inp: HandoffInput)` (`agents/handoff_generator.py:24`)
  is the only place that turns clinical data into the prompt string fed to the report-writing
  LLM. It serializes `inp.slots.model_dump(exclude_none=True)` — i.e. **only fields declared on
  `HandoffInput`/`SlotData` can ever appear in that prompt.**
  `DomainInferenceOutput` (F2) is never imported by `handoff_generator.py`, `clinical_slot.py`,
  or `dialogue.py` (`grep` confirmed 7 files reference `domain_inference`/`DomainInferenceAgent`,
  none of them are the clinical-slot or handoff modules).
- `DomainInferenceAgent`/F2 itself is **standalone** — not wired into `orchestrator.py`'s
  11-state machine (`docs/ai/agents/14_domain_inference.md`, G-D-F2 gate, unmet). It only
  runs through the `f2.py` verification harness or the isolated `POST /ai/domain/infer` route.

Net: the AI-predicted-disease entity is genuinely greenfield. There is currently **zero**
plumbing connecting anything F2-shaped to `SlotData`/HPI. The design goal is to add the new
entity while preserving that zero — permanently, not just today.

## 1. Where the entity lives

New, standalone Pydantic module: `apps/ai-server/src/schemas/ai_predicted_disease.py`
(name chosen to avoid collision with `domain_inference.py`'s `DomainCandidate`, which is a
different, already-governed object — region/department inference, not disease-level).

```python
class AIPredictedDiseaseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disease_name: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)   # NOT "probability" — see §3
    source_type: Literal["rag_disease_chunk"]
    source_id: str            # rag.disease row/chunk id — whitelist-checked like DomainEvidence
    evidence_quote: str | None = None   # optional grounding text, same whitelist discipline

class AIPredictedDiseaseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_diagnostic: Literal[False] = False        # sentinel; qa asserts this literal never changes
    label: Literal["ai_generated_non_diagnostic_decision_support"] = \
        "ai_generated_non_diagnostic_decision_support"
    mode: Literal["experimental_unpopulated", "rag_live"]
    candidates: list[AIPredictedDiseaseCandidate] = Field(default_factory=list, max_length=5)
    disclaimer_ko: str        # fixed constant, not model-generated
    retrieval_meta: RetrievalMeta   # reuse domain_inference's honest-mode-reporting type
    reason_summary: str = ""
```

`AIPredictedDiseaseOutput`/`AIPredictedDiseaseCandidate` share **no base class, no field, and
no inheritance relationship** with `SlotData`, `HandoffInput`, `HandoffOutput`,
`ClinicalSlotOutput`, or `DomainCandidate`. They are not a 13th clinical slot, not added to
`ALL_SLOT_KEYS`/`_KEY_ALIASES` in `clinical_slot.py` (`agents/clinical_slot.py:169-174` —
qa's leak-proof test must assert no AI-disease key name is ever present in that alias table),
and not appended to `domain_candidates`/`department_candidates` in F2's output.

At the artifact/API layer it attaches as a **sibling top-level key**, never nested inside the
clinical report object:
- `f2.py` harness (now): add `ai_predicted_disease: dict` as a sibling top-level key in the
  saved JSON artifact (`_build_artifact`, `apps/ai-server/src/f2.py:307-365`), next to but
  never merged into `domain_candidates`.
- Future production response (post G-D-F2, out of this mission's scope): a sibling key on the
  API response envelope, e.g. `{"handoff": {...12-section...}, "ai_predicted_diseases": {...}}`,
  assembled at the route/orchestrator layer strictly *after* `HandoffGeneratorAgent.run()`
  returns — never passed into it.

## 2. The structural HPI-separation mechanism

**Name it precisely: disjoint-schema + closed-prompt-context invariant, enforced at three
independent layers, each individually sufficient.**

1. **Type layer.** `SlotData`/`HandoffInput`/`ClinicalSlotOutput` gain `model_config =
   ConfigDict(extra="forbid")` (currently they inherit Pydantic's default `extra="ignore"`,
   which *silently drops* unknown kwargs rather than rejecting them — a weaker guarantee than
   it looks like). With `extra="forbid"`, any future code that mistakenly tries to pass an
   AI-disease value into one of these constructors raises a `ValidationError` immediately,
   instead of the value being silently discarded (today's default) or, worse, silently
   accepted if a field happened to exist. This converts "a developer must remember not to"
   into "the constructor will crash if they try."
2. **Call-graph layer.** No function in the codebase may import `ai_predicted_disease.py`
   *and* also construct/mutate `SlotData`, `HandoffInput`, or `ClinicalSlotOutput`. This is
   the qa-testable invariant: an import-graph or grep-based adversarial test asserting
   `agents/handoff_generator.py`, `agents/clinical_slot.py`, `agents/dialogue.py`, and
   `agents/orchestrator.py::_build_handoff_input` never import or reference the new module,
   and that the new module never imports `schemas/handoff.py` or `schemas/clinical_slot.py`.
3. **LLM-prompt layer — the one that actually matters, and the one with a documented failure
   precedent in this codebase.** `_build_user_content(inp: HandoffInput)` can only ever
   serialize fields declared on `HandoffInput`. Because that schema has no AI-disease field
   (layer 1) and cannot be smuggled one via kwargs (`extra="forbid"`), **the report-writing
   LLM is structurally incapable of ever seeing AI-disease content when it drafts HPI or
   `clinical_assessment` prose.** This is the load-bearing design choice: isolation is not
   achieved by a prompt instruction telling the LLM "don't put AI-disease output in HPI" —
   there is no such instruction anywhere, because there is no channel for the data to reach
   that prompt in the first place.

**Why layer 3 is written this way, not as a prompt rule:** this project already ran the
"prompt instruction alone enforces a separation rule" experiment once, on a structurally
identical problem — F2 v1's absolute rule 2 ("risk expressions must not be used as domain-
confidence evidence") was present in the prompt text throughout, yet was violated live in
2/8 `EXP-004` runs (VAL-006, REV-008, `ADR-014`). The project's own adopted fix was a
**code-level filter** (`f2_grounding._RISK_PHRASES`, `ADR-014`), not a stronger prompt. HPI
separation is the same failure class (an LLM-reachable channel plus a text rule saying "don't
use it that way") and should not repeat the mistake: the fix here is that the channel does not
exist, not that a rule says not to use it.

**Full argument for critic:** contamination is impossible by construction because (a) the two
object graphs share no type, so a `.model_dump()`/serialization of one cannot structurally
contain the other's fields; (b) no function reads both, so no merge/write path exists to author
accidentally; (c) the LLM that authors HPI prose is never given the data as context, so it
cannot paraphrase or summarize it into HPI even adversarially. (a)+(b) are static/testable at
commit time; (c) is the actual regulatory-relevant guarantee and is the one qa's adversarial
test suite should weight most heavily (e.g., a fixture where `AIPredictedDiseaseOutput` data is
injected into `state` alongside a real session, then assert the resulting `report_markdown`
contains none of the disease names/scores — a live-behavior test, not just a type check).

## 3. Labeling: similarity score vs. calibrated probability — recommendation

**Recommend: label as `similarity_score` ("유사도 점수"), not `probability`/`확률`/`가능성(%)`.
Critic makes the final ruling; this is a recommendation with cited grounding.**

- RAG cosine-similarity scores are well documented as *not* calibrated probabilities: raw
  cosine similarity from embedding models suffers from anisotropy (embeddings cluster in a
  narrow cone), so absolute values lack a consistent probabilistic interpretation across
  models/datasets, and a fixed threshold (e.g. 0.8) carries no stable semantic meaning without
  a separate calibration step (mean-centering/whitening, a learned calibration layer, or a
  cross-encoder reranker) — none of which this project's F2 pipeline currently implements
  (source basis: aggregated web survey of current practitioner/technical literature on
  embedding-similarity calibration, 2026-07-09; no single peer-reviewed paper is the anchor
  here — flag as `UNVERIFIED-as-single-citation`, treat as engineering consensus rather than
  one attributable claim).
- Do not compute or display a softmax-style normalization across the top-5 (which would
  visually imply a probability distribution summing to 100%) — keep each `similarity_score`
  independent and bounded [0,1], described as a retrieval-relevance signal.
- Keep this score provenance-distinct from `DomainCandidate.confidence` (`schemas/
  domain_inference.py:44`), which is LLM self-reported, not a code-computed similarity value —
  conflating the two under one word ("confidence") would blur two different epistemic
  categories (vector-search distance vs. LLM judgment). The disease entity's score should come
  from the deterministic RAG retrieval step only, not from an LLM-authored confidence number.
- The FDA's Clinical Decision Support Software guidance (Jan 2026 update, non-binding in this
  Korean-regulatory context but a useful structural analogy) frames its fourth "non-device
  CDS" criterion as: the tool must let the clinician "independently review the basis for the
  recommendation" rather than rely on it primarily
  ([FDA CDS guidance FAQ](https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software-frequently-asked-questions-faqs);
  [Frier Levitt summary](https://www.frierlevitt.com/articles/fda-clinical-decision-support-software-guidance/)).
  A raw, honestly-labeled `similarity_score` plus its `evidence_quote`/`source_id` supports
  independent review; a number framed as "probability" or "%" invites the clinician to treat
  it as a pre-computed diagnostic judgment, undermining exactly that criterion. This is offered
  as a structural analogy for the labeling decision, not as a claim that Korean regulation
  mirrors FDA's framework — critic should weigh domestic (Korean) regulatory language
  ("AI가 진단하면 안된다") as primary and this only as informative precedent.

## 4. Sequencing

**Now (this mission, Track B item (b), parallel/order-independent, low-risk plumbing):**
build the schema (`ai_predicted_disease.py`), the disjoint-namespace wiring (`f2.py` artifact
sibling key), the type-layer/call-graph-layer invariants (§2.1–2), and hand qa the adversarial
test spec (§2, esp. the live-behavior HPI-leak test). Do **not** wire a live RAG query against
`rag.disease` yet — the container ships with `mode="experimental_unpopulated"`, empty
`candidates`, and an honest `reason_summary` (e.g. "RAG-arm EXPERIMENTAL pending ADR-016
lift — AI-disease container not yet live-populated"). This mirrors the project's own
established honesty-of-degraded-mode pattern (`RetrievalMeta.mode` always reports reality,
`ADR-014`/REV-006 condition 6) rather than inventing a new convention.

**Gated (future, blocked on RAG-arm certification):** live auto-population — i.e. flipping
`mode` to `"rag_live"` and actually populating `candidates` from a real Stage-1 `rag.disease`
retrieval for live patient sessions — is gated on RAG-arm certification, currently
**UNCERTIFIED per `ADR-016`** (2/3 conditions met, VP-003 RAG clean re-verification unmet,
tracked as `BUG-019`, no partial/per-persona certification licensed per `REV-012` §4). This is
not an extra precaution layered on top — the AI-disease entity's only named value source is
"F2 RAG top-5 disease+score" (brief, verbatim), so gating its live population on RAG-arm
certification is gating it on the certification of its own sole data source. There is no
independent certification track for the entity that doesn't reduce to RAG-arm certification.

**Explicit recommendation departing from the F2 precedent:** F2's `domain_inference` has a
legitimate, already-certified `llm_only` fallback arm (`ADR-015` (1)) for when RAG retrieval is
unavailable. The AI-disease entity should **not** get an equivalent `llm_only` fallback — its
entire value proposition is a RAG-grounded similarity score; an LLM guessing disease names
without retrieval grounding is not a degraded version of the same product, it is a different
(and more diagnosis-flavored, higher-risk) product. If RAG is unavailable, the entity should
report empty/`experimental_unpopulated`, not fall back to an ungrounded LLM guess. Flagging
this now because developer may otherwise default to copying F2's rag/llm_only dual-mode
pattern by habit.

**Production-wiring scope note:** `DomainInferenceAgent`/F2 itself is not wired into
`orchestrator.py`'s production chat path yet (G-D-F2 gate unmet). Until that happens, there is
no live orchestrator-path signal for the AI-disease entity to attach to either — for this
mission it exists only in the `f2.py` verification-harness artifact and in schema/test form.
The §2 invariants are written so that when G-D-F2 wiring eventually happens, the isolation
guarantee holds without requiring any additional future engineering discipline (no new
prompt-rule needs to be remembered — the schemas simply don't have the field).

## Caveats

- This note is a design proposal; it has not been reviewed by critic (regulatory red-line
  ruling, similarity-vs-probability ruling) or implemented/tested by developer/qa.
- The embedding-calibration claim in §3 is grounded in aggregated current technical-literature
  consensus (web search, 2026-07-09), not a single peer-reviewed citation — flagged
  `UNVERIFIED-as-single-citation` per the no-invented-citations rule; treat as engineering
  consensus, not an attributable research result.
- The FDA CDS-guidance analogy in §3 is explicitly non-binding for this Korean-regulatory
  project; offered as structural precedent only, not as the applicable law.
