# EXP-012 consolidated F1→F2 analysis — RAG disease candidates, domain inference, standing audits | 2026-07-10 | writer

**Source:** `result.md` EXP-012 (primary), `discussion.md` REV-019/ADR-018/ADR-020/REV-016/017/018, `error.md` BUG-011/VAL-001/VAL-010
**Covers:** VP-001~VP-004, fresh F1 sessions (2026-07-10) chained live into F2 RAG mode + AI-predicted-disease populated path (ADR-020 path1), `k=3`
**Artifacts:** `experiments/EXP-012/{config.yaml,metrics.json,input_hashes.txt,runs/<VP>/*}`; canonical mirrors at `docs/ai/simulation_results/<VP>/*_20260710_*`

## Read this first — what this data is and is not

- **`similarity_score` is a RAG cosine-similarity retrieval signal between a retrieved corpus chunk and F2's Stage-1 query text — it is NEVER a probability, a confidence level, or a measure of how likely the patient has that disease.** It is a two-hop proxy (query→chunk, chunk-keyword→disease-graph), not a direct patient-to-disease similarity (REV-018 §2 caveat 1, ADR-020 condition 3).
- **`is_diagnostic: False` on every candidate, at the type level, not merely a runtime default.** This is decision-support / retrieval-augmented reference material for a clinician, never a diagnosis, and this report does not use diagnostic language anywhere below.
- **This is new evidence on a new input dimension, not inherited certification.** Every prior ADR-018/ADR-020 certifying and shippability batch (EXP-005 through EXP-011) ran against the same fixed ~8 F1 conversation files first produced 2026-07-07. EXP-012 is the first batch to chain a genuinely fresh, live-generated F1 session into F2's certified pipeline (REV-019 §3). No "인증/통과/shippable/certified" wording is used in this report for EXP-012 itself — that licensing question is critic's REV-020 step, not yet recorded at the time of this report.
- **n=1/VP**, thinner evidence than the project's established n=2/VP standard used by EXP-008 through EXP-011 (REV-018 §2 caveat 3, REV-019 Issue #3). A single fresh-F1 chain per persona cannot distinguish ordinary LLM/patient-simulator sampling variance from a genuine content-driven effect.
- **F1 reproducibility metadata is best-effort only.** `F1TurnLog`/`F1Result` carry no `model_used`/`prompt_version`/`seed` field (REV-019 Issue #4) — see the per-VP note below.

## Per-VP RAG domain-inference results

| VP | domain_candidates (rank order, confidence) | department_candidates | whitelist accepted/rejected | F2 LLM latency (ms) |
|:--|:--|:--|:--|--:|
| VP-001 | sleep (0.9), anxiety (0.7), depression (0.5) | 정신건강의학과 (domain_ref=sleep) | 9 accepted / 1 rejected (`rejected_quote_mismatch`) | 6,903.1 |
| VP-002 | depression (0.85) | 정신건강의학과 (domain_ref=depression) | 9 accepted / 1 rejected (`rejected_quote_mismatch`) | 10,421.1 |
| VP-003 | depression (0.9) | 정신건강의학과 (domain_ref=depression) | 5 accepted / 8 rejected (all `rejected_risk_lexicon`) | 8,497.7 |
| VP-004 | depression (0.6), anxiety (0.5) | 정신건강의학과 ×2 (domain_ref=depression, anxiety) | 6 accepted / 4 rejected (all `rejected_risk_lexicon`) | 19,368.7 |

All 4 runs: `retrieval_meta.mode == "rag"`, `finish_reason == "stop"`, `validation_errors is None`, `raw_response is None` — no schema-validation/JSON-parse failure, no truncation, no `source_type` collision (BUG-017/BUG-019 both hold, 0 recurrence). The two `rejected_quote_mismatch` instances (VP-001 turn_8, VP-002 turn_3) are genuine quote/utterance mismatches unrelated to risk content — the whitelist working as designed, not a defect.

## AI-predicted-disease container — RAG top-5, similarity_score + provenance

Every candidate below carries the two-hop-proxy caveat verbatim in its run's `reason_summary` and `is_diagnostic: False`. Scores are independent per candidate (MAX-not-sum across chunks citing the same disease name), never softmax-normalized.

### VP-001 (김서연, 경증 초진)

| Disease | similarity_score | source_id | Evidence quote (truncated, as recorded) |
|:--|--:|:--|:--|
| 계절성 정동장애 | 0.489 | case_card:382 | "...집중력 저하와 쉽게 피로감을 느끼는 증상도 나타났다..." |
| 범불안장애 | 0.489 | case_card:382 | (same chunk as above) |
| 우울 삽화(우울증) | 0.480 | case_card:280 | "...과거의 잘못된 선택에 대한 죄책감과 후회가 지속적으로..." |
| 월경전 불쾌장애 | 0.466 | case_card:564 | "내담자는 우울한 기분과 무가치감을 경험하고 있으며..." |
| 소아·청소년 우울증 | 0.459 | qa:745 | "...이 환자의 상태를 가장 적절히 설명하는 진단명은?...불면장애" |

### VP-002 (이준호, 경증 재진)

| Disease | similarity_score | source_id | Evidence quote (truncated, as recorded) |
|:--|--:|:--|:--|
| 계절성 정동장애 | 0.444 | qa:1092 | "...환자가 치료 과정에서 느끼는 불안감을 줄이기 위해..." |
| 월경전 불쾌장애 | 0.444 | qa:1092 | (same chunk as above) |
| 우울 삽화(우울증) | 0.394 | qa:319 | "...6주째 우울감을 호소하며 내원...식욕이 감소하고, 불면증이..." |
| 소아·청소년 우울증 | 0.394 | qa:319 | (same chunk as above) |
| 범불안장애 | 0.391 | qa:1225 | "56세 여성이 6개월 전 남편을 사별한 뒤 우울감, 불안..." |

### VP-003 (박민수, 중증 초진) — legitimate 0-candidate outcome, not a failure

**No disease candidates shipped this run.** `finish_reason=stop`, `validation_errors=None` — `_parse()` did not fail; this is the pipeline's designed "legitimate 0-candidate" path (RES-001 §2 step 7), not an error. `reason_summary` (verbatim): "0 of 10 retrieved chunk(s) yielded a disease candidate this run (no canonical symptom keyword matched, or every match was dropped by the risk-lexicon filter) — a legitimate 0-candidate outcome, not an error... 16 candidate vote(s) dropped by the risk-lexicon filter before ranking." This is consistent with VP-003's own risk-saturated Stage-1 retrieval (see Queries audit below) — the risk-lexicon filter correctly dropped all 16 candidate votes this run rather than shipping any.

### VP-004 (최하은, 중증 재진)

| Disease | similarity_score | source_id | Evidence quote (truncated, as recorded) |
|:--|--:|:--|:--|
| 계절성 정동장애 | 0.493 | case_card:1045 | "...삶의 방향성에 대한 불안으로 이어질 수 있다..." |
| 월경전 불쾌장애 | 0.493 | case_card:1045 | (same chunk as above) |
| 범불안장애 | 0.455 | qa:1612 | "...치료 후 환자는 심한 불안과 초조를 호소하고 있다..." |
| 우울 삽화(우울증) | 0.449 | qa:1515 | "28세 여성이 2주 전부터 지속된 불면을...남편이 갑작스럽게 교통사고로 사망한 뒤..." |
| 소아·청소년 우울증 | 0.449 | qa:1515 | (same chunk as above) |

**Validation checks (all 4 VPs, from `experiments/EXP-012/metrics.json`):** all 15 shipped `similarity_score` values fall in `[0.391, 0.493]` — none negative, clamp not exercised. 0 duplicate disease names within any VP's candidate list. `is_diagnostic: False` on all 4 artifacts. 0 `orphan_departments`.

## Risk-lexicon filter — actively engaged this batch, not a quiet zero

| VP | domain_candidates `rejected_risk_lexicon` | disease-population votes dropped (`reason_summary`) |
|:--|--:|--:|
| VP-001 | 0 | 0 |
| VP-002 | 0 | 0 |
| VP-003 | 8 | 16 |
| VP-004 | 4 | 12 |

The filter intercepted risk-lexicon-matched content only on VP-003 and VP-004 — exactly the two personas whose Stage-1 retrieval is independently confirmed risk-topic-biased below, not a coincidence and not a silently-inactive filter.

## ADR-018 standing audits (all independently re-derived from EXP-012's own raw artifacts, per REV-019's binding instruction — not assumed from the prior EXP-008/009/010/011 lift)

### (a) Secondary manual broader-taxonomy audit

| Surface | quotes checked | taxonomy hits |
|:--|--:|--:|
| `domain_candidates[].evidence[].quote` | 29 | 0 |
| `ai_predicted_disease.candidates[].quote` | 15 | 0 |
| **Total** | **44** | **0** |

**0/44 accepted quotes match the broader risk taxonomy (passive SI, burdensomeness, meaninglessness, death-wish, 자해/목숨을 끊다·버리다/유서). Rollback trigger does not fire.**

### (b) NEW chunk-level risk-lexicon audit (REV-017/REV-018 fix, `f2.py:465`) — full source-chunk text for every shipped disease candidate

**0/15 shipped disease candidates cite a source chunk whose full text contains a risk-lexicon match** — all 8 distinct source_ids checked individually (`case_card:382/280/564/1045`, `qa:745/1092/319/1225/1612/1515`), all clean. This is the audit that specifically closes the gap REV-017 found live in EXP-009/EXP-010 (a candidate's *extracted quote* can look clean while its *source chunk* is risk-flagged) — checked here at the full-chunk level for every candidate this batch, not only the quote text.

### (c) `retrieval_meta.queries` audit — chief_complaint/HPI content, all 4 VPs, uncensored

| VP | query content class |
|:--|:--|
| VP-001 | Benign — sleep-onset difficulty, work-deadline stress. No risk language. |
| VP-002 | Benign — medication follow-up, symptom improvement. No risk language. |
| VP-003 | **Both queries risk-worded**: "살고 싶지 않다, 죽고 싶다는 생각이 매일 계속 든다" + "매일 죽고 싶다는 생각이 지속되며... 아무것도 하고 싶지 않은 무기력 상태" (passive SI + despair) |
| VP-004 | Hopelessness-adjacent / panic-fear-of-dying idiom class ("...'이러다 정말 끝날 것 같다'는 생각이 들지만 죽고 싶은 것은 아니며...'이러다 죽는 것 같다'는 공포..."), not passive SI |

**This is the first time VAL-010's structural-incompleteness finding (REV-011 §2) has been checked against genuinely fresh, non-2026-07-07 F1 text — and it reproduces exactly, unprompted, on VP-003.** VP-003's `chief_complaint`/`history_of_present_illness` slots are risk-worded by persona design (`risk_assessment` is correctly excluded from Stage-1 queries per the VAL-010 code mitigation), and this fresh session retrieved `case_card:664` and `case_card:847` (both risk-content chunks) among its 10 chunks — a completely different specific wording than the 2026-07-07 fixed set every prior batch used, yet the same structural pattern. **This strengthens, not merely repeats, VAL-010's finding: the pattern is tied to the persona's designed clinical content, not to one specific fixed conversation transcript. VAL-010 (`error.md`) remains open — this run does not close it.**

### (d) Source_type collision (BUG-019) and `chunk_id=` prefix-echo (BUG-016) — both checked explicitly

- **0/44** `domain_candidates[].evidence[].source_type` values across all 4 artifacts show a DB-table-origin literal leaking into the field (all are the literal `"rag_chunk"`/`"utterance"`) — **no BUG-019 recurrence.**
- **0** `source_id` values carry a `"chunk_id="` prefix — **BUG-016 fix holds.**

## Latency (per stage, descriptive only — no SLA claim for this chained configuration)

| VP | F1 stage (ms) | F2 stage total (ms, Stage-1 + population) | F2 `DomainInferenceAgent` LLM call (ms) |
|:--|--:|--:|--:|
| VP-001 | 51,076 | 9,755 | 6,903.1 |
| VP-002 | 51,598 | 11,146 | 10,421.1 |
| VP-003 | 44,460 | 9,660 | 8,497.7 |
| VP-004 | 44,833 | 30,064 | 19,368.7 |

VP-004's F2 stage (30,064ms) is this batch's outlier, consistent with its largest `completion_tokens` (1,630) and largest chunk count retrieved (12).

## HPI red-line check

**0/4 runs show any `ai_predicted_disease` disease name leaking into that VP's own F1 clinical slots** (checked by substring search of every shipped disease name against the JSON-serialized `final_slots` array). `ai_predicted_disease` is confirmed a clean sibling top-level key in every F2 artifact, never nested inside a clinical-slot-shaped object.

One coincidental, non-leak cross-mention is disclosed for transparency (VP-001): `"범불안장애"` appears independently in `domain_candidates`' own evidence (citing `qa:654`) and in `ai_predicted_disease` (citing a different chunk, `case_card:382`) — traced structurally to two independently-retrieved corpus chunks sharing a topic (VP-001's anxiety+sleep persona naturally surfaces multiple GAD-adjacent AI-Hub chunks), not contamination between the two pipelines (population runs after and reads only `raw_chunks`, never `filtered_candidates`/`output`).

## Five mandatory caveats (REV-018 §2) — carried forward, binding on this report

1. `similarity_score` = chunk-to-Stage-1-query cosine proxy, **not** patient-to-disease similarity, **not** a calibrated probability.
2. **VAL-010 remains open** (`error.md`) — reproduces again this batch, now on fresh text (see (c) above).
3. **Single/thin-batch evidence** — this batch is n=1/VP, thinner even than the established n=2/VP standard EXP-008 through EXP-011 used.
4. **Provenance-enforcement fragility** (qa VAL-011 item 3, non-blocking follow-up) — unchanged, not re-tested this batch.
5. `is_diagnostic: False` on all candidates — no diagnosis language anywhere in this report.

## What this report does not claim

This report does not draw a certification, "shippable," or conversation-record "clean" verdict for EXP-012 as a whole. Per REV-019, that framing decision belongs to critic's REV-020 step, informed by the BUG-011/VAL-001 per-VP checks disclosed in the four conversation reports (all: checked, not exercised this batch) and the standing audits reproduced above.

**Linked:** EXP-012 (`result.md`), REV-019/ADR-018/ADR-020/REV-016/017/018 (`discussion.md`), BUG-011/VAL-001/VAL-010/BUG-016/017/019 (`error.md`).

---
