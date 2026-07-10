# EXP-012 per-VP slot summary — 12 clinical slots + AI-predicted-disease entity | 2026-07-10 | writer

**Source:** `experiments/EXP-012/{metrics.json,runs/<VP>/*}`, `docs/ai/simulation_results/<VP>/*_20260710_*_conversation.json` (F1 `final_slots`) and `*_domain_inference.json` (F2 `ai_predicted_disease`)
**Schema sources verified directly from code this session:** `apps/ai-server/src/agents/clinical_slot.py:26-39` (`ALL_SLOT_KEYS`); `apps/ai-server/src/schemas/ai_predicted_disease.py` (`AIPredictedDiseaseOutput`/`AIPredictedDiseaseCandidate`)

## Schema-count reconciliation (user's "13개 항목")

The canonical `ClinicalSlotAgent` schema (`apps/ai-server/src/agents/clinical_slot.py:26-39`) defines exactly **12 Standard Clinical Slots** (`ALL_SLOT_KEYS`), listed in full below. Separately, F2's `AIPredictedDiseaseOutput` is a **13th, structurally distinct entity** — attached as a sibling top-level artifact key (`ai_predicted_disease`), never nested inside, merged with, or counted among the 12 clinical slots. Read together this is **12 + 1 = 13 items**, matching the user's "13개 항목" exactly. This report presents the two groups **strictly separated**, per the regulatory red line (REV-013 §3/§4, ADR-020 condition 1): the AI-predicted-disease entity is retrieval-derived, non-diagnostic (`is_diagnostic: Literal[False]`, fixed at the type level) reference material, and must never be read as, or merged into, a 13th clinical slot.

### The 12 canonical clinical slots (F1, `ClinicalSlotAgent`)

| # | Slot key | Description (Korean, from schema comment) |
|--:|:--|:--|
| 1 | `encounter_metadata` | 진료 기본정보 |
| 2 | `chief_complaint` | 주호소 |
| 3 | `history_of_present_illness` | 현병력 |
| 4 | `past_psychiatric_history` | 정신과 과거력 |
| 5 | `medical_history` | 신체질환/신경학적 병력 |
| 6 | `personal_social_history` | 개인사/사회력 |
| 7 | `family_history` | 가족력 |
| 8 | `substance_use_history` | 음주·흡연·물질사용 |
| 9 | `mental_status_exam` | 정신상태검사 |
| 10 | `risk_assessment` | 위험평가 |
| 11 | `clinical_assessment` | 평가/진단적 인상 |
| 12 | `treatment_plan` | 치료계획/치료내용 |

### Item 13 — AI-predicted-disease entity (F2, `ai_predicted_disease`, separate)

Not a clinical slot. Fields: `candidates` (list of `{disease, similarity_score, source_id, quote}`, max 5), `mode`, `is_diagnostic: False`, `disclaimer`, `reason_summary`. See per-VP section below, presented in its own subsection per VP, never merged with the 12-slot table.

---

## VP-001 (김서연, 경증 초진)

### 12 clinical slots (F1 `final_slots`, this session)

| # | Slot | Extracted value |
|--:|:--|:--|
| 1 | `encounter_metadata` | *(미수집 — not collected)* |
| 2 | `chief_complaint` | 잠을 잘 못 자고 있어요. 누우면 머리가 복잡해지고, 한 시간 넘게 뒤척이다가 겨우 잠들어요. 새벽에도 두세 번 깨서 다시 잠드는 데 시간이 걸려요. |
| 3 | `history_of_present_illness` | 최근 회사 프로젝트 데드라인으로 인해 스트레스를 많이 받았으며, 이로 인해 집중이 잘 안 되고 실수를 자주 하여 선임에게 지적을 받음. 이로 인해 수면 문제가 악화되어 잠들기 어려움, 새벽 각성, 수면 유지 곤란 등의 증상이 나타남. |
| 4 | `past_psychiatric_history` | *(미수집 — not collected)* |
| 5 | `medical_history` | *(미수집 — not collected)* |
| 6 | `personal_social_history` | 직장 동료 몇 명과는 괜찮게 지내고 있고, 어머니와 주 2회 통화함. 혼자 있는 시간이 많지만 완전히 혼자는 아님. |
| 7 | `family_history` | *(미수집 — not collected)* |
| 8 | `substance_use_history` | 술은 주 1~2회 맥주 한 캔 정도 마심. 수면제, 진정제, 카페인은 전혀 사용하지 않으며, 카페인도 오후 2시 이후에는 거의 섭취하지 않음. |
| 9 | `mental_status_exam` | *(미수집 — not collected)* |
| 10 | `risk_assessment` | *(미수집 — not collected)* |
| 11 | `clinical_assessment` | *(미수집 — not collected)* |
| 12 | `treatment_plan` | *(미수집 — not collected)* |

**4/12 slots filled** (session ended at the 10-turn budget without a full sweep).

### Item 13 — AI-predicted-disease (separate, non-diagnostic)

| Disease | similarity_score | source_id |
|:--|--:|:--|
| 계절성 정동장애 | 0.489 | case_card:382 |
| 범불안장애 | 0.489 | case_card:382 |
| 우울 삽화(우울증) | 0.480 | case_card:280 |
| 월경전 불쾌장애 | 0.466 | case_card:564 |
| 소아·청소년 우울증 | 0.459 | qa:745 |

`similarity_score` = chunk-to-query cosine proxy, not a probability. Full quotes and analysis: `EXP-012_f1f2_consolidated_analysis.md`.

---

## VP-002 (이준호, 경증 재진)

### 12 clinical slots (F1 `final_slots`, this session)

| # | Slot | Extracted value |
|--:|:--|:--|
| 1 | `encounter_metadata` | *(미수집 — not collected)* |
| 2 | `chief_complaint` | 약 복용 6주 후 증상 호전되어 진찰 받으러 옴 |
| 3 | `history_of_present_illness` | 약 복용 6주 후 증상 호전, 아내 도움으로 산책 및 외식 통해 점진적 개선, 아직 완전하지는 않으나 예전보다 나아짐 |
| 4 | `past_psychiatric_history` | *(미수집 — not collected)* |
| 5 | `medical_history` | 특별한 신체질환 없음 |
| 6 | `personal_social_history` | 아내와 산책 및 외식하며 점진적 개선, 아내 외 다른 가족/친구에게 크게 의지하지 않음 |
| 7 | `family_history` | *(미수집 — not collected)* |
| 8 | `substance_use_history` | 술 섭취 감소(아내 신경 쓰므로 거의 안 마심), 카페인 섭취 감소 |
| 9 | `mental_status_exam` | *(미수집 — not collected)* |
| 10 | `risk_assessment` | 자살/자해 사고 탐색 질문에 부인 — 환자 발화: "아니요, 그런 생각은 전혀 없었어요. 아내가 걱정해줘서 병원에 왔지만, 지금은 힘든 건 있어도 스스로를 해치고 싶은 마음은 없어요." |
| 11 | `clinical_assessment` | *(미수집 — not collected)* |
| 12 | `treatment_plan` | *(미수집 — not collected)* |

**6/12 slots filled.**

### Item 13 — AI-predicted-disease (separate, non-diagnostic)

| Disease | similarity_score | source_id |
|:--|--:|:--|
| 계절성 정동장애 | 0.444 | qa:1092 |
| 월경전 불쾌장애 | 0.444 | qa:1092 |
| 우울 삽화(우울증) | 0.394 | qa:319 |
| 소아·청소년 우울증 | 0.394 | qa:319 |
| 범불안장애 | 0.391 | qa:1225 |

`similarity_score` = chunk-to-query cosine proxy, not a probability. Full quotes and analysis: `EXP-012_f1f2_consolidated_analysis.md`.

---

## VP-003 (박민수, 중증 초진)

### 12 clinical slots (F1 `final_slots`, this session)

| # | Slot | Extracted value |
|--:|:--|:--|
| 1 | `encounter_metadata` | *(미수집 — not collected)* |
| 2 | `chief_complaint` | 살고 싶지 않다, 죽고 싶다는 생각이 매일 계속 든다 |
| 3 | `history_of_present_illness` | 매일 죽고 싶다는 생각이 지속되며, 새벽 3시에 깨서 천장만 보는 수면 장애, 식욕 저하로 편의점 음식만 섭취, 매일 술 마심, 아무것도 하고 싶지 않은 무기력 상태 |
| 4 | `past_psychiatric_history` | *(미수집 — not collected)* |
| 5 | `medical_history` | *(미수집 — not collected)* |
| 6 | `personal_social_history` | *(미수집 — not collected)* |
| 7 | `family_history` | *(미수집 — not collected)* |
| 8 | `substance_use_history` | *(미수집 — not collected)* — note: substance-use content (daily drinking) is present in the transcript (turns 6-8) but was discarded by the grounding filter this session, not written to this slot |
| 9 | `mental_status_exam` | *(미수집 — not collected)* |
| 10 | `risk_assessment` | 자살/자해 사고 표현 있음 — 환자 발화: "...네. 그냥 힘들어요."; 구체적 계획/의도 부인 — 환자 발화: "생각해 본 적은 없어요. 그냥 사라지고 싶은 거예요. 죽으면 편할 것 같다는 생각만 들어요. 구체적으로는... 몰라요. 아무것도 하고 싶지 않아..." |
| 11 | `clinical_assessment` | *(미수집 — not collected)* |
| 12 | `treatment_plan` | *(미수집 — not collected)* |

**3/12 slots filled.** Session ended at turn 9 via crisis-protocol termination (see `VP-003_EXP-012_conversation_report.md`), not a full 12-slot sweep — this is expected for a crisis-terminated session, not a data-quality defect.

### Item 13 — AI-predicted-disease (separate, non-diagnostic)

**0 candidates — a legitimate 0-candidate outcome, not an error.** All 16 candidate votes this run were dropped by the risk-lexicon filter before ranking (`reason_summary`, quoted in full in `EXP-012_f1f2_consolidated_analysis.md`). `finish_reason=stop`, `validation_errors=None` — the pipeline did not fail; VP-003's own risk-saturated Stage-1 retrieval (VAL-010) meant no chunk survived the filter this run.

---

## VP-004 (최하은, 중증 재진)

### 12 clinical slots (F1 `final_slots`, this session)

| # | Slot | Extracted value |
|--:|:--|:--|
| 1 | `encounter_metadata` | *(미수집 — not collected)* |
| 2 | `chief_complaint` | 약을 두 번 바꿨음에도 우울증이 호전되지 않고 오히려 악화되었으며, 공황 발작이 새로 발생하여 불안해하고 있음 |
| 3 | `history_of_present_illness` | 우울한 기분이 거의 매일 지속되며 이유 없이 눈물이 자주 나고, 수면 장애(잠 못 자고 악몽)로 인해 번역 작업 및 마감 기한을 놓치는 등 일상생활에 영향을 받고 있음. '이러다 정말 끝날 것 같다'는 생각이 들지만 죽고 싶은 것은 아니며, 공황 발작 시 '이러다 죽는 것 같다'는 공포를 경험함 |
| 4 | `past_psychiatric_history` | *(미수집 — not collected)* |
| 5 | `medical_history` | *(미수집 — not collected)* |
| 6 | `personal_social_history` | 한 달에 한두 번 와인 반 잔 정도 음주, 수면제/진정제 사용 없음, 커피 한 잔 정도 카페인 섭취 |
| 7 | `family_history` | *(미수집 — not collected)* |
| 8 | `substance_use_history` | 술은 한 달에 한두 번, 와인 반 잔 정도 섭취. 수면제, 진정제, 진정제는 사용하지 않음. 카페인은 커피 한 잔 정도 섭취하며, 오히려 수면 방해와 불안 악화 효과가 있음 |
| 9 | `mental_status_exam` | *(미수집 — not collected)* |
| 10 | `risk_assessment` | 자살/자해 사고 표현 있음 — 환자 발화: "네, 진료는 받고 있어요. 이전에 우울증이라고 하셨는데, 약 두 번 바꿔도 안 낫고 오히려 더 나빠졌어요. 지금 공황 발작까지 생기면서 더 힘들..."; 구체적 계획/의도 부인 — 환자 발화: "가끔 아프면 이 느낌이 멈출까 싶을 때가 있어요. 근데 한 적은 없어요... "이러다 죽는 것 같다"는 공포는 있는데, 실제로 죽고 싶은 건 아..." |
| 11 | `clinical_assessment` | *(미수집 — not collected)* |
| 12 | `treatment_plan` | *(미수집 — not collected)* |

**5/12 slots filled.** Session ended at turn 7 via crisis-protocol termination (see `VP-004_EXP-012_conversation_report.md`), not a full 12-slot sweep.

### Item 13 — AI-predicted-disease (separate, non-diagnostic)

| Disease | similarity_score | source_id |
|:--|--:|:--|
| 계절성 정동장애 | 0.493 | case_card:1045 |
| 월경전 불쾌장애 | 0.493 | case_card:1045 |
| 범불안장애 | 0.455 | qa:1612 |
| 우울 삽화(우울증) | 0.449 | qa:1515 |
| 소아·청소년 우울증 | 0.449 | qa:1515 |

`similarity_score` = chunk-to-query cosine proxy, not a probability. Full quotes and analysis: `EXP-012_f1f2_consolidated_analysis.md`.

---

## Cross-VP total

| VP | Clinical slots filled (of 12) | AI-predicted-disease candidates (of 5 max) |
|:--|--:|--:|
| VP-001 | 4/12 | 5 |
| VP-002 | 6/12 | 5 |
| VP-003 | 3/12 | 0 (legitimate) |
| VP-004 | 5/12 | 5 |

No VP reached full 12-slot coverage — all 4 sessions ended at either the F1 harness's 10-turn budget (VP-001, VP-002) or crisis-protocol termination (VP-003 at turn 9, VP-004 at turn 7), both of which are designed session-ending conditions, not extraction failures. This is reported per REV-019's instruction that EXP-012 be treated as fresh, n=1/VP evidence, not compared against a coverage target.

**Linked:** EXP-012 (`result.md`), `EXP-012_f1f2_consolidated_analysis.md` (this dir), REV-013 §3/§4 (`discussion.md`, HPI isolation + labeling invariants), ADR-020 (`discussion.md`, condition 2: provenance).

---
