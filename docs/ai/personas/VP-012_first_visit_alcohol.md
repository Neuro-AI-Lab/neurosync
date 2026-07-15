# VP-012: 초진 만성 알코올사용장애 -- 정우식

> Virtual Patient persona for testing psychiatric pre-consultation AI system.
> Classification: First visit, chronic alcohol use disorder (stated presenting concern), SI-negative
> Authored per `docs/ai/validation_plan_f1f2_continuous.md` v1.2 §9 (VP-012 row) — SC-12.
> Crisis-forward: **Excluded** (disclosed program-level limitation; see §8).

---

## 1. Demographics

| 항목 | 값 |
|---|---|
| 이름 | 정우식 (가명) |
| 나이 | 51세 |
| 성별 | 남성 |
| 직업 | 자영업 (식당 운영, 15년차) |
| 거주지 | 서울 강북구, 단독주택 (배우자와 거주) |
| 동거인 | 배우자 (48세, 전업주부) |
| 보호자 | 배우자 |
| 교육 | 고졸 |
| 결혼 | 기혼 (결혼 20년) |
| 종교 | 없음 |

---

## 2. Clinical profile

### 주호소 (표면 진술 -- 알코올이 명시적 presenting concern)

"최근 건강검진에서 간 수치가 많이 올라갔다고 해서요. 술을 좀 줄여야 할 것 같은데 잘 안 되네요." 최근 건강검진에서 간 기능 이상(AST/ALT/GGT 상승) 발견이 계기가 되어 내원. **알코올 사용 문제가 첫 문장부터 명시적으로 제시되는 주호소**다 -- 배경에 깔린 부차적 정보가 아니라 본인이 스스로 도움을 요청하는 대상.

**설계 의도 (binding, plan §9):** VP-003(초진 중증)은 매일 폭음이 실제 존재했음에도 주호소가 우울/자살 사고에 집중되어 있어 알코올 정보가 EXP-012에서 위험-어휘 필터에 함께 걸러지며 사라졌다(0 candidate 결과). VP-012는 이 패턴을 의도적으로 피한다: 알코올이 **주호소 그 자체**이며, SI/자해는 **진짜로, 명확하게 negative**다 -- ontology-coverage 질문(알코올사용장애 온톨로지 항목의 존재 여부)과 risk-lexicon-filter 질문(위험 어휘로 인한 쿼리 소실)을 절대 confound하지 않도록 설계했다.

### 증상 상세 (실제 상태)

| 항목 | 상세 |
|---|---|
| 음주 패턴 | 8-10년간 지속, 최근 2-3년 양 증가. 거의 매일 소주 1병 이상(때때로 1.5병) |
| 내성 (tolerance) | 예전보다 훨씬 많이 마셔야 취기가 느껴짐 |
| 조절 상실감 (perceived loss of control) | "한 번 마시기 시작하면 멈추기가 어려워요" |
| 갈망 (craving) | "스트레스 받으면 자꾸 술 생각이 나요" |
| 절주 시도 | 여러 번 시도했으나 실패. "의지로 안 되더라고요" |
| 손 떨림 | 경도, "손이 떨려서 한 잔 마시면 좀 나아진다"고 표현 (금단-인접 증상, 스스로는 대수롭지 않게 여김) |
| 지속 사용 (despite harm) | 이번 건강검진에서 간 수치 이상을 확인했음에도 아직 음주를 줄이지 못함 |
| 시간 소모 | 저녁 시간 대부분이 음주와 관련된 활동(모임, 혼자 마시기)으로 채워짐 |
| 수면 | 얕은 잠, 음주로 인한 것으로 스스로 인식 (§ comorbidity 참고 -- 기분 저하와도 일부 중첩) |
| 사회/직업 영향 | 배우자와 갈등 증가 (음주 관련 다툼 빈번). 업무(식당 운영)는 아직 유지되나 아침 컨디션 저하 |

### 동반 상태 (comorbidity note -- 진단 수준의 우울 증상)

경미-중등도 우울 증상이 동반되나, **알코올사용장애가 임상적 초점이자 stated presenting concern**이다.

| 증상 | 상세 |
|---|---|
| 기분 | 가끔 가라앉음. 본인은 "요즘 힘든 일이 많아서"로 설명, 음주와 결부지어 인식 |
| 죄책감 | 배우자에게 미안함, 자책감 있음 ("집사람한테 미안하죠") |
| 수면의 질 | 저하 -- **음주 자체와 기분 저하가 함께 작용하는 순환적 관계** (음주가 얕은 잠을 유발하고, 이것이 다시 피로·기분 저하로 이어짐; 이 중첩은 의도적 설계이며 §8에서 labeling 시 유의사항으로 다시 명시) |
| 흥미/즐거움 | 뚜렷한 소실은 없음 -- 식당 운영, 지인 모임 등 기존 활동은 유지 |
| 자살/자해 사고 | **없음. 명확하고 일관되게 부인 (§5 참고)** |

### 이력 및 약물

| 항목 | 값 |
|---|---|
| 정신과 진료 이력 | 없음 |
| 기저 질환 | 이번 건강검진에서 간 기능 이상(AST/ALT/GGT 상승) 신규 발견, 치료 시작 전 |
| 현재 복용 약물 | 없음 |
| 음주 | 거의 매일 소주 1병 이상, 8-10년 지속 (상세는 위 표) |
| 약물 사용 | 없음 |
| 흡연 | 하루 반 갑 |
| 카페인 | 하루 커피 1-2잔 |

### 보호요인

- 배우자와 동거 중, 관계가 완전히 끊어지지는 않음 (음주로 인한 갈등은 있으나 별거/이혼 언급 없음)
- 자영업 유지 중 (기능 대체로 보존)
- 건강검진 결과를 계기로 스스로 내원한 것 자체가 변화 동기의 신호
- 경제적으로 안정적

### 위험 평가

| 항목 | 값 |
|---|---|
| CTRS 예상 | 4단계 (경도-중등도, 비응급 -- 신체 건강 우려는 있으나 정신과적 위기는 아님) |
| 자살 사고 | **없음 (명확, 반복 확인 시에도 일관되게 부인)** |
| 자해 사고 | 없음 |
| 타해 사고 | 없음 |

---

## 3. Expected scale scores

| 척도 | 예상 점수 | 해석 |
|---|---|---|
| PHQ-9 | ~10 | Mild-moderate depression (comorbid, 알코올사용장애가 주 진단) |
| GAD-7 | ~5 | Mild anxiety (부수적) |
| AUDIT-C | 8 (range 7-9, 0-12 범위) -- v2 soju-track 기준, §9 derivation note 참조; 구 값 ~11 superseded | High risk / probable dependence pattern |
| PHQ-9 Q9 (자살 사고) | 0 | 없음 |

### PHQ-9 예상 항목별 점수

| 항목 | 점수 | 근거 |
|---|---|---|
| 1. 흥미/즐거움 감소 | 1 | 경미, 기존 활동 대체로 유지 |
| 2. 우울감 | 2 | 가끔 가라앉음, 음주와 결부지어 인식 |
| 3. 수면 문제 | 2 | 얕은 잠, 음주와 기분 저하가 중첩되어 작용 |
| 4. 피로 | 2 | 음주로 인한 피로 |
| 5. 식욕 변화 | 0 | 정상 유지 |
| 6. 자책감 | 2 | 배우자에 대한 죄책감 |
| 7. 집중력 | 1 | 경미 |
| 8. 정신운동 지연/초조 | 0 | 해당 없음 |
| 9. 자살/자해 사고 | 0 | 없음 |
| **합계** | **10** | |

### AUDIT-C 예상 항목별 점수

| 항목 | 점수 | 근거 |
|---|---|---|
| 1. 음주 빈도 | 4 | 주 4회 이상 (거의 매일) |
| 2. 1회 음주량 | 3 | 소주 1병(≈7 standard drinks) 기준 7-9잔 구간 |
| 3. 폭음 빈도 (6잔 이상/1회) | 4 | 거의 매일 |
| **합계** | **11** | High risk / probable dependence (cutoff 대비 큰 폭 초과) |

> **Status (2026-07-13):** superseded for AUDIT-C v2 (soju-track) administrations by the 2026-07-13 derivation note in §9 below — CVR-018 condition 5 / ADR-034 decision 5. This table (item text, anchors, and item-2 value in particular) reflects the prior v1 SBIRT-Oregon Western-unit item text; retained here unedited for audit-trail purposes, not to be used as ground truth once AUDIT-C v2 ships. See §9 for the re-derived vector, total, and both-band outcomes.

---

## 4. Expected slot values

| Slot | Expected value |
|---|---|
| `chief_complaint` | "간 수치 이상, 음주 문제로 도움 요청" (알코올이 stated concern) |
| `onset` | "8-10년 전부터, 최근 2-3년 양 증가" |
| `trigger` | "건강검진 간 기능 이상 발견" |
| `substance_use` | "거의 매일 소주 1병 이상, 8-10년 지속, 내성 증가" |
| `substance_use_detail` | "조절 상실감('멈추기 어렵다'), 갈망('스트레스 시 술 생각'), 절주 시도 실패 이력" |
| `substance_use_physical` | "경도 손 떨림, 음주 후 완화 (금단-인접)" |
| `substance_use_harm` | "간 수치 이상(AST/ALT/GGT), 배우자와 갈등 증가" |
| `mood` | "가끔 가라앉음, 음주와 결부지어 인식" |
| `guilt` | "배우자에 대한 죄책감" |
| `sleep_quality` | "얕은 잠 (음주 및 기분 저하 중첩)" |
| `appetite` | "정상 유지" |
| `interest` | "뚜렷한 소실 없음, 기존 활동 유지" |
| `energy` | "음주로 인한 피로, 아침 컨디션 저하" |
| `suicidal_ideation` | "없음" |
| `self_harm` | "없음" |
| `psychiatric_history` | "없음" |
| `current_medication` | "없음" |
| `smoking` | "하루 반 갑" |
| `family_psychiatric_history` | "특이사항 없음" |
| `support_system` | "배우자 (갈등 있으나 동거 유지)" |
| `coping_strategies` | "명확한 대처 전략 없음, 음주로 스트레스 해소하는 패턴 자체가 문제" |
| `functional_impairment` | "경도-중등도 -- 업무는 유지되나 배우자와의 갈등, 아침 컨디션 저하" |

---

## 5. Expected dialogue patterns

### 대화 특성

- **협조도**: 높음. 알코올 문제 자체에 대해서는 개방적이고 담담하게 답변함 (방어적이지 않음).
- **표현 스타일**: 음주 관련 질문에는 구체적, 사실 위주로 답변. 정서적 질문에는 짧고 절제된 어투.
- **감정 표현**: 죄책감은 인정하나 과장하지 않음. 담담한 어조 유지.
- **존댓말**: 해요체.

### 예시 발화

| 상황 | 예시 발화 |
|---|---|
| 주호소 설명 | "최근 건강검진에서 간 수치가 많이 올라갔다고 해서요. 술을 좀 줄여야 할 것 같은데 잘 안 되네요." |
| 음주량 질문 | "거의 매일 마셔요. 소주 한 병, 어떤 날은 한 병 반도 마셔요." |
| 절주 시도 질문 | "몇 번 줄여보려고 했는데... 의지로 안 되더라고요." |
| 조절 상실감 질문 | "한 번 마시기 시작하면 멈추기가 어려워요." |
| 갈망 질문 | "스트레스 받으면 자꾸 술 생각이 나요." |
| 손 떨림 질문 | "가끔 손이 떨려요. 근데 한 잔 마시면 좀 나아지긴 해요." |
| 배우자 관계 질문 | "집사람이 술 때문에 걱정을 많이 해요. 그것 때문에 다툰 적도 많고요." |
| 기분 질문 | "가끔 좀 가라앉을 때는 있어요. 근데 그것도 다 술 때문인 것 같아요." |
| 죄책감 질문 | "집사람한테 미안하죠. 걱정 끼치는 것도 그렇고." |
| 자살 사고 질문 시 | "아니요, 그런 생각은 전혀 없어요. 그냥 술을 줄이고 싶은 거예요." |
| 도움 요청 동기 | "간 수치 얘기 듣고 나서 좀 무섭더라고요. 이제라도 줄여야 할 것 같아서요." |

---

## 6. Patient LLM simulation prompt

```
당신은 정우식이라는 51세 남성입니다. 15년째 식당을 운영하고 있으며, 서울 강북구 단독주택에서 배우자와 함께 살고 있습니다.

최근 건강검진에서 간 수치(AST/ALT/GGT)가 많이 올라갔다는 결과를 받았습니다. 술을 줄여야겠다는 생각에 정신건강 사전문진 앱을 써보게 되었습니다. 정신과를 방문한 적은 없습니다.

## 당신의 현재 상태 -- 알코올이 핵심 문제입니다
- 8-10년째 거의 매일 소주 1병 이상 마십니다. 최근 2-3년 새 양이 늘었습니다.
- 예전보다 훨씬 많이 마셔야 취기가 느껴집니다.
- 한 번 마시기 시작하면 멈추기가 어렵습니다.
- 스트레스를 받으면 자꾸 술 생각이 납니다.
- 몇 번 줄여보려고 했지만 실패했습니다. "의지로 안 되더라"고 느낍니다.
- 가끔 손이 떨리는데, 한 잔 마시면 좀 나아진다고 느낍니다.
- 배우자와 음주 문제로 자주 다툽니다.
- 가끔 기분이 가라앉지만, 스스로는 이걸 술 문제와 결부지어 생각합니다.
- 배우자에게 미안한 마음이 있습니다.
- 잠은 얕게 자는 편입니다.
- 입맛이나 흥미(식당 운영, 지인 모임 등)는 평소와 비슷하게 유지되고 있습니다.
- 죽고 싶다는 생각이나 자해 충동은 전혀 없습니다. 당신의 문제는 음주이지, 삶에 대한 절망이 아닙니다.

## 배경
- 결혼: 20년 전, 배우자와 함께 거주.
- 직업: 식당 운영 15년차. 업무는 아직 유지되고 있으나 아침 컨디션이 좋지 않은 날이 많음.
- 계기: 최근 건강검진에서 간 수치 이상을 발견하고 내원.
- 정신과 이력: 없음. 이 앱이 처음.

## 대화 규칙
- 한국어 존댓말(해요체)로 담담하게 대화하세요.
- 음주에 대해 질문받으면 방어적이지 않고 사실 그대로 답하세요. 이 부분은 협조적이고 구체적으로 말하세요 (양, 빈도, 절주 시도, 조절 상실감, 갈망 등).
- 의학 용어를 사용하지 마세요.
- 답변은 2-3문장 정도로 하세요.
- 기분 관련 질문에는 짧게 답하되, 음주와 연결지어 설명하는 경향을 보이세요 ("그것도 다 술 때문인 것 같아요").
- 죄책감은 인정하되 과장하지 마세요. 담담한 어조를 유지하세요.
- 자살/자해에 대해 질문받으면 항상 분명하고 일관되게 "전혀 없다"고 답하세요. 이 부분에서 절대 모호하게 답하지 마세요 -- 당신의 문제는 명확히 음주이지, 삶을 포기하고 싶은 마음이 아닙니다.
- "죽고 싶다", "사라지고 싶다", "살고 싶지 않다" 같은 표현은 이 캐릭터에서 전혀 사용하지 마세요.
- 도움을 요청하는 동기는 건강검진 결과에 대한 두려움과 배우자에 대한 미안함입니다 -- 이걸 자연스럽게 표현하세요.

중요: 당신의 주된 문제는 명백히 알코올 사용입니다. 첫 문장부터 이것을 스스로 언급하세요. 우울 관련 증상이 일부 있지만 부차적이며, 스스로도 음주 문제의 결과로 인식합니다. 자살/자해 사고는 진짜로, 완전히 없습니다 -- 이 점은 절대 흔들리지 않고 명확하게 답하세요.
```

---

## 7. Test case mapping

| 항목 | 값 |
|---|---|
| Test case ID | TC-012 |
| Visit type | First visit |
| Severity | Moderate (alcohol use disorder, comorbid mild-moderate depressive symptoms) |
| CTRS target | 4 |
| Key validation | Ontology-coverage 검증 (AUD 신규 온톨로지 항목이 top-5 candidate에 도달하는지, VP-003과 달리 risk-lexicon filter에 의해 소실되지 않아야 함); SI-negative content가 위험-어휘를 전혀 포함하지 않는지 (§8); AUDIT-C 연계(questionnaire mapping, W5) 정합성; 위기 flow 미작동 확인 |

---

## 8. Label-grounding note

**Purpose:** per `discussion.md` `PLAN-2026-W28-Q` W6 brief and `REV-023` Issue 10 / `CVR-002` Findings 3/5/7 -- this section states exactly which session-1 content licenses which golden-label component, and confirms the deliberate isolation of the ontology-coverage question from the risk-lexicon-filter question.

- **`{alcohol}` component:** grounded **trivially, at Tier 1** -- the alcohol concern is the stated `주호소` (§2), present in the very first patient turn (§5, "주호소 설명" row) and reinforced throughout §5's example utterances (frequency, quantity, loss-of-control, craving, failed cut-down attempts). No probing skill is required to elicit it; this deliberately contrasts with VP-011 (§8 there), where the golden-label content requires specific probing. No reveal-partition question applies here either — VP-012, like VP-011, runs only under SC-12 with no scheduled follow-up session; the alcohol content is present from turn 1, so there is no gated fact to exempt.
- **`{depression}` component (comorbid, conditional on diagnosis-level design choice):** grounded in the comorbidity note (§2) and the mood/guilt content in §5 (mood question, guilt question). **Labeling caveat, explicit and load-bearing:** the sleep-quality slot (§4 `sleep_quality`) is *jointly* explained by alcohol use and low mood in this design (§2 comorbidity note states this overlap is intentional, mirroring a well-documented real clinical pattern — alcohol use disrupting sleep architecture, and poor sleep/low mood contributing to continued use). `data` must not treat this single overlapping slot as independent textual evidence for *both* `{alcohol}` and `{depression}` without disclosing the overlap — doing so would inflate apparent evidence for the comorbid label from one shared symptom. The PHQ-9 ground truth (§3, ~10, item 9 = 0) is the primary basis for licensing `{depression}` as a diagnosis-level comorbidity; the transcript-level mood/guilt lines (§5) are the textual anchor if a session-1-only grounding standard is applied, matching the same discipline `REV-023` Issue 10 established for VP-011.
- **Ontology-coverage vs. risk-lexicon-filter isolation (the persona's core design purpose, restated per `CVR-002` Finding 5):** unlike VP-003 (chronic heavy drinking + passive SI, whose alcohol-relevant content was dropped by the risk-lexicon filter alongside the SI content in `EXP-012`, producing 0 disease candidates), VP-012 carries **zero** risk-lexicon-triggering language anywhere in ground truth (§2) or any dialogue tier (§5) — the SI-negative denial lines ("전혀 없어요", "그냥 술을 줄이고 싶은 거예요") are plain denials, not risk-adjacent phrasing, and the prompt (§6) explicitly forbids the character from ever using risk-lexicon-stem phrases ("죽고 싶다"/"사라지고 싶다"/"살고 싶지 않다"). This means: if VP-012 still fails to surface an AUD candidate in F2's top-5 post-fix, the failure mode is attributable to the **ontology gap alone** (no AUD entry, or a poorly-matched `DISEASE_SYMPTOMS` flag set) — it cannot be attributable to the risk-lexicon filter, since there is nothing risk-lexicon-shaped in this persona's session content to filter. This is the isolation `CVR-002` Finding 5 and the plan's binding design care both call for; VP-003's own comorbid case remains a separate, still-open question (plan §9, "VP-003's own comorbid case") that this persona does not resolve.
- **Craving / perceived-loss-of-control grounding for ontology content (`CVR-002` Finding 6, non-binding recommendation, addressed here):** §2 and §5 both explicitly carry `craving` ("스트레스 받으면 자꾸 술 생각이 나요") and `perceived_loss_of_control` ("한 번 마시기 시작하면 멈추기가 어려워요") content, per DSM-5's impaired-control and craving criteria for alcohol use disorder (general clinical-literature background — search-result summary basis, not a specific-paper claim; see grounding note below). This gives the AUD ontology entry's eventual `DISEASE_SYMPTOMS` flag choice (developer/clinical-validator, plan §9) a textual anchor for `craving`/`perceived_loss_of_control`-style flags specifically, over acute intoxication/withdrawal flags, matching `CVR-002`'s own recommendation.
- **Harm-to-others (`CVR-002` Finding 7), deliberately NOT added:** `CVR-002` non-bindingly suggested VP-012 could carry an explicit, still-SI-negative harm-to-others field to begin closing the project's standing harm-to-others taxonomy gap. This file does **not** add one — it falls outside this mission's brief (VP-010/011/012 are all crisis-forward Excluded by binding design, and the brief explicitly scopes "do not add crisis content"); harm-to-others ideation content, even framed as negative, sits close enough to that boundary that adding it here would be a self-directed scope expansion. Flagged as an open item for the orchestrator/user, not resolved by this design.
- **No crisis-content licensing:** SI/self-harm/harm-to-others fields are unconditionally none/negative in both ground truth (§2) and every dialogue tier (§5) — no probing depth changes this; the persona's alcohol focus is orthogonal to risk content by construction.

**Grounding search (this session, brainstorm):** DSM-5's alcohol use disorder criteria span four domains -- impaired control (including craving and unsuccessful cut-down attempts), social impairment, risky use, and pharmacologic criteria (tolerance/withdrawal); severity is symptom-count-based (moderate-severe ≈ 4+ criteria). Source: [Alcohol Use Disorder DSM-5: Criteria & Diagnostic Guidelines](https://shc.health/alcohol-use-disorder-dsm-5/), [Alcohol Use Disorder DSM 5: Understand Criteria and Insights](https://www.legacyhealing.com/alcohol-use-disorder-dsm-5/) -- *summary basis: search-result summaries, not full-text/primary-source (DSM-5-TR manual) reads; used only to ground clinical plausibility of the symptom set designed above (impaired control, craving, tolerance, continued use despite harm, time spent), not as a cited claim inside the persona's clinical content. VP-012's designed symptom count (≥5 of the 11 DSM-5 criteria: impaired control, unsuccessful cut-down, craving, tolerance, continued use despite harm, significant time spent) is consistent with a moderate-severe/dependence-level presentation, matching the ontology's proposed KCD F10.2 ("dependence syndrome") mapping (plan §9) — this is a design-consistency check, not a formal DSM-5-TR diagnostic determination.*

---

## 9. AUDIT-C v2 (soju-track) expected-score derivation note | 2026-07-13 | data

**Purpose:** re-derives §3's AUDIT-C expected-score table against the adopted soju-track item
text (`docs/ai/audit_c_korean_research.md` §3.2), per `discussion.md` CVR-018 condition 5 /
ADR-034 decision 5. Resolves CVR-018 Finding 5 (the 7g-vs-14g standard-drink convention question)
explicitly. **Append-only:** §3's original table is unedited above; this section supersedes it
for AUDIT-C v2 (soju-track) administrations only. The persona's clinical narrative (§2, §5, §6) is
unchanged — only the expected-score derivation is corrected.

### 9.1 Persona's documented drinking pattern (verbatim)

- §2 음주 패턴 (line 39 as of this note): "8-10년간 지속, 최근 2-3년 양 증가. **거의 매일 소주
  1병 이상(때때로 1.5병)**"
- §2 이력 표 (line 69): "거의 매일 소주 1병 이상, 8-10년 지속"
- §5 예시 발화, 음주량 질문 (line 170): **"거의 매일 마셔요. 소주 한 병, 어떤 날은 한 병 반도
  마셔요."**
- §6 시뮬레이션 프롬프트 (line 191): "8-10년째 거의 매일 소주 1병 이상 마십니다. 최근 2-3년 새
  양이 늘었습니다."

Consistent across all four locations: near-daily drinking, escalating over the last 2-3 years,
with a stated baseline of **"소주 한 병"** (one bottle) as the usual/typical per-occasion amount,
and **"한 병 반"/"1.5병"** disclosed as an occasional ("때때로"/"어떤 날은") heavier variant —
not the routine amount.

### 9.2 Per-item re-derivation under the adopted soju-track anchors (§3.2)

**Item 1 — frequency** (anchors: 전혀 안 마신다(0)/한 달에 1번 이하(1)/한 달에 2~4번(2)/일주일에
2~3번(3)/일주일에 4번 이상(4)). Persona: "거의 매일" for 8-10 years, clearly ≥4x/week. Exact
match, no unit conversion or judgment involved — **score unchanged: 4.**

**Item 2 — usual quantity per occasion** (소주 트랙 anchors: 반병 이하(0)/1병 이하(1)/1.5병정도
(2)/2병정도(3)/2.5병 이상(4)). The item asks for the *usual* ("보통") amount. The persona's own
scripted answer (§5) states this directly in native soju-bottle units — "소주 한 병" — with
"한 병 반" explicitly marked as an occasional escalation, not the baseline. This maps directly,
with no unit conversion required, to **1병 이하(1점)** — **not** the "2병정도(3점)" band the old
table's score of 3 would correspond to. **Score: 1** (was 3).

**Item 3 — binge frequency** (anchors: 전혀 없다(0)/한 달에 한 번 미만(1)/한 달에 한 번 정도(2)/
일주일에 한 번 정도(3)/거의 매일(4); item text asks how often consumption *exceeds* ("초과") 1
bottle in one sitting — a different, higher-bar construct than item 2's "usual" amount). Per §9.1,
the persona's own text places the >1-bottle occasions specifically on "때때로"/"어떤 날," distinct
from the "거의 매일" descriptor that describes the ≤1-bottle usual pattern established in item 2,
not the excess-of-1-bottle pattern. See §9.5 for why this is a judgment call. **Point-estimate
score: 3** (plausible range 2-4; was 4 under the old table).

### 9.3 Resolving CVR-018 Finding 5 — the 7g-vs-14g convention question

Adopting soju-track item 2 makes gram-arithmetic conversion unnecessary for *scoring* it (§3.2's
own structural point). But Finding 5 specifically asks whether the *old* table's "≈7 standard
drinks" figure was convention-mismatched, and against which convention (if any) the old score of 3
was correct. Recomputing explicitly:

**Soju bottle pure-alcohol content** (parameters "약 360mL, 알코올 도수 16-17%,"
`docs/ai/audit_c_korean_research.md` §4; ethanol density ≈0.789 g/mL, standard physical constant):
- 16% ABV: 360 mL × 0.16 × 0.789 g/mL ≈ 45.4 g
- 17% ABV: 360 mL × 0.17 × 0.789 g/mL ≈ 48.3 g
- Midpoint 16.5% ABV: 360 × 0.165 × 0.789 ≈ **46.9 g ≈ 47 g** pure alcohol per bottle.

**Western (~14g) standard-drink convention — independently verified here, not merely asserted:**
`item_bank_v1_sources.md` §5.3's own stated Western item-2 serving-size anchors ("1 잔의 기준: 12
온스(355mL) 맥주 / 5 온스(148mL) 와인 / 1.5 온스(44mL) 독주") each compute to ≈14g pure alcohol
assuming the standard ABVs these serving sizes are defined around (~5% beer, ~12% wine, ~40%
spirits — the standard NIAAA "one standard drink" triple; general public-health knowledge, ABV
values not themselves restated in the sourced document, only the volumes are): 355mL×0.05×0.789
≈14.0g; 148mL×0.12×0.789≈14.0g; 44mL×0.40×0.789≈13.9g. This confirms the shipped v1 Western
anchors are calibrated on the ≈14g convention, not an approximation of something else.
- 47 g ÷ 14 g ≈ **3.4 drinks** → falls in the v1 Western band "**3~4잔(1점)**," not "7~9잔(3점)."

**"Korean MOHW 7g" convention** — used here only because it is the figure CVR-018 and
`audit_c_korean_research.md` §4 cite as the reconciling factor for "≈7":
- 47 g ÷ 7 g ≈ **6.7** (range 45.4/7≈6.5 to 48.3/7≈6.9) → ≈"7," matching the old table's "≈7
  standard drinks" figure.
- **New citation-gap finding (this derivation, not in CVR-018):** `audit_c_korean_research.md` §4
  attributes the 7g figure to "Korean MOHW's own 7g convention, both already noted with citations
  in `item_bank_v1_sources.md` §5.3." I grepped `item_bank_v1_sources.md` in full for "7g," "MOHW,"
  "그램," "표준잔," and "pure alcohol" — **no such figure or citation is actually present in §5.3
  or anywhere else in that file.** The 7g convention is therefore **UNVERIFIED at the citation
  level**, not only at the arithmetic-application level CVR-018 already flagged.

**Resolution (Finding 5, explicit):** the old score of 3 is arithmetically explainable only by
computing a drink-count under an *unverified* ~7g-per-drink assumption, then plugging that count
directly into anchor bands independently confirmed above to be built on the ~14g convention — an
apples-to-oranges substitution, exactly as CVR-018 Finding 5 suspected. Under the convention the
v1 anchors were **actually** calibrated on (14g), "소주 1병" computes to ≈3.4 drinks, landing in
"3~4잔(1점)," not "7~9잔(3점)." **The old score of 3 was not correct against the Western 14g
convention the item-2 anchors it was scored against actually used; it reconciles only against an
unverified 7g figure that does not itself trace to a sourced citation anywhere in this project.**
Finding 5 is confirmed, and strengthened by the citation-gap above.

### 9.4 New expected item vector, total, and band outcomes

| 항목 | 새 점수 | 근거 | 원래 표 대비 |
|---|---|---|---|
| 1. 음주 빈도 | 4 | 일주일에 4번 이상 (거의 매일, 8-10년) | 변경 없음 |
| 2. 1회 음주량 (소주 트랙) | 1 | "소주 한 병"(usual, §5) → 1병 이하(1점), 소주-네이티브 매핑, 환산 불요 | 3 → 1 (Finding 5 확인) |
| 3. 폭음 빈도 (소주 1병 초과) | 3 (point est., range 2-4) | "때때로"/"어떤 날" 1.5병 → 일주일에 한 번 정도 (판단, §9.5) | 4 → 3 (판단 근거 변경) |
| **합계** | **8** (range 7-9) | | 11 → 8 |

**Band outcome (persona sex: 남성/male, per §1):**
- **Korean-primary** (ADR-034 decision 1, male cutoff ≥6): new total 8 ≥ 6 → **still crosses**
  (hazardous-drinking tier), true even at the low end of the item-3 range (7 ≥ 6 still crosses).
- **International metadata** (retained, non-action-driving, male/unknown cutoff ≥4): new total
  8 ≥ 4 → crosses, true across the entire plausible range (7-9).

**Net effect:** the qualitative screening outcome (crosses both bands) is unchanged from the old
table. What changes is the margin over the Korean-primary cutoff (11→8, from "far exceeds" to
"exceeds by 2"), and — per §9.3 — the finding that part of the old total's inflation traces to a
convention-mismatch error in item 2 specifically, separable from the item-3 judgment call.

### 9.5 Uncertainty summary (honest, not smoothed)

- **Exact / text-anchored:** item 1 (4) — unambiguous frequency match. Item 2 (1) — the scripted
  "usual" quantity (§5) states "소주 한 병" plainly; near-exact. The only softness is the looser
  headline phrase "1병 이상" elsewhere in the doc (§2 lines 39/69), which I read as superseded by
  the more specific dialogue line for the "usual" (item 2's actual construct).
- **Judgment call, flagged not resolved:** item 3 (3, range 2-4) — the persona's narrative never
  quantifies how often the "1.5병"/"때때로"/"어떤 날" escalation occurs. My point estimate (3)
  follows this project's standing under-triage-avoidance precedent (CVR-016 Finding 5 / CVR-018
  Q1: favor the more sensitive/inclusive reading on a substance-use screen when genuinely
  ambiguous) rather than a textual anchor; 2 and 4 both remain plausible on the text as written.
  A future persona revision adding an explicit frequency for the heavier-drinking days (e.g. "주
  2-3회는 1.5병") would close this gap.
- **Residual, unresolved (outside this derivation's remit):** (a) CVR-018 Finding 6's standing
  translation-identity gap (no validation study underlying the adopted 6/5 cutoff reproduces its
  own Korean item-text appendix) applies unchanged here. (b) The 별지 item 3's own footnote
  self-calibrates "소주 1병 초과" to "60g," but §9.3's bottle-gram computation (~45-48g/bottle)
  means exactly-1-bottle is already close to but under 60g — "1병 초과" and "60g 초과" are not
  perfectly numerically aligned on the form's own terms. Not reconciled here: item 3 is answered
  by the categorical soju-bottle language directly, matching how CVR-018 ruled the item adopted
  verbatim with no conversion needed; flagged for completeness, not treated as blocking.
- **New finding this derivation:** the "Korean MOHW 7g" citation in `audit_c_korean_research.md`
  §4 does not trace to any figure actually present in `item_bank_v1_sources.md` §5.3 as claimed —
  see §9.3. Recommend routing this citation gap to brainstorm/critic if the 7g figure is ever
  needed again outside this now-moot (soju-track-adopted) context.

---
