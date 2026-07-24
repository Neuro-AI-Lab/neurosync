# F1~F5 데이터 카탈로그 — 핸드오프 리포트 편성 기준

> 목적: F1~F5가 **실제로 저장/산출하는 데이터**를 전수 정리하고, 각 항목이 핸드오프
> 리포트에 들어갈 가치를 등급화하여 **최대한 컴팩트한 리포트 내용을 확정**하기 위한 기준 문서.
> 모든 필드명·타입은 `apps/ai-server/src/schemas/*` 실제 스키마에서 추출(추정 없음).

## 데이터 흐름

```
F1 대화형 문진  → *_conversation.json      (슬롯·CTRS·정서·위험·turn 로그)
F2 도메인 추론  → *_domain_inference.json  (진료과/도메인 후보 + ai_predicted_disease)
F3 설문 시행    → *_survey.json (+ _scale_scores.json)  (척도 문항·점수·심각도)
F4 종단 분석    → *_temporal.json (+ 차트 PNG)  (세션별 시계열·추세·경과·불일치)
F5 인계 조립    → *_handoff.md / _handoff.pdf / _handoff_fhir.json  (A0~A8 + B 종단)
```

## 편성 등급 표기

| 등급 | 의미 | 리포트 처리 |
|---|---|---|
| ★ | **핵심** — 인계 판단에 직접 필요 | 본문 상단, 항상 표시 |
| ○ | **보조** — 맥락/근거 보강 | 본문 하위 또는 접기 |
| · | **부록** — 참고·비진단·상세 | 부록으로 이동 |
| — | **생략** — 내부/텔레메트리/디버그 | 리포트 미노출 |

---

## F1 — 대화형 문진 (`*_conversation.json`, 스키마 `F1Result`)

### 세션 메타 · 위험
| 필드 | 타입 | 의미 | 등급 |
|---|---|---|---|
| `session_id` / `persona_id` / `persona_name` | str | 세션·환자 식별 | ★ |
| `session_index` | int | 종단 회차 번호 | ★ |
| `simulated_date` | str | 세션 날짜 | ★ |
| `model` / `prompt_version` | str | 사용 LLM·프롬프트 버전 | — (문서정보) |
| `session_ctrs` | int(1–5) | 세션 최종 위기단계 | ★ |
| `risk_floor` | int\|None | 전 turn 중 최악 CTRS | ★ |
| `crisis_triggered` / `crisis_turn` | bool / int\|None | 위기 발생 여부·turn | ★ |
| `probe_events` | list[dict] | CTRS3+자살/자해 시 안전탐침 응답 | ★ |
| `nearby_psychiatric` | list[dict] | 위기 시 인근 정신과 시설(HIRA) | ○ |
| `slot_coverage` | float | 12슬롯 채움률 | ○ |
| `grounded_coverage` | float | 8슬롯 근거기반 채움률 | ○ |
| `is_revisit` | bool | 재진 여부 | ○ |
| `prior_handoff` / `carried_slot_provenance` | str / dict | 직전 세션 이월 채널·출처 | · |
| `phr_summary` | dict | 세션 시작 시 로드된 PHR 요약 | ○ |
| `ocr_documents` / `stt_transcripts` | list[dict] | OCR/STT 입력 메타 | · |
| `total_turns` | int | 대화 turn 수 | · |
| `prompts_degraded` / `errors` | bool / list | 폴백·오류 텔레메트리 | — |

### 12 임상 슬롯 (`final_slots`) — **핸드오프 본문의 뼈대**
8개 **QUESTIONABLE_SLOT_KEYS**(채움률 분모) + 관찰 슬롯:

| 슬롯 키 | 라벨 | 등급 |
|---|---|---|
| `chief_complaint` | 주호소 | ★ |
| `history_of_present_illness` | 현병력 | ★ |
| `risk_assessment` | 위험평가 | ★ |
| `past_psychiatric_history` | 정신과 과거력 | ○ |
| `substance_use_history` | 음주·물질사용 | ○ |
| `medical_history` | 신체질환/신경학 | ○ |
| `personal_social_history` | 개인사/사회력 | ○ |
| `family_history` | 가족력 | ○ |
| `mental_status_exam` (관찰 슬롯, 8분모 밖) | 정신상태검사(텍스트) | ○ |

### 정서 (`session_sentiment` = `SentimentSessionOutput`)
| 필드 | 타입 | 의미 | 등급 |
|---|---|---|---|
| `dominant_emotions` | list[str] | 세션 주요 감정 | ○ |
| `signal_strength` | str(none/mild/moderate/strong) | 위험신호 강도 | ○ |
| `emotional_shift_detected` / `shift_description` | bool / str | 정서 궤적 변화 | ○ |
| `polarity_trajectory` / `per_utterance_tags` | list | turn별 극성/태그 | · |
| `emotion_distribution` / `repeated_patterns` | dict / list | 감정 분포·반복 패턴 | · |

### `turns` (`F1TurnLog` 리스트) — **전량 내부/디버그**
`patient_message`·`agent_response`·`safety_*`·`slot_updates`·`latency_ms`·`dialogue_retry_*`·
`normalizer_meta` 등 40+ 필드. → **위험 발화 인용**과 **세션별 슬롯 변화**만 상위(F5/F4)에서
집계해 사용, turn 원본은 리포트 **생략(—)**.

---

## F2 — 도메인 추론 (`*_domain_inference.json`)

### `DomainInferenceOutput`
| 필드 | 타입 | 의미 | 등급 |
|---|---|---|---|
| `department_candidates[]` (`department`,`reason`,`domain_ref`) | list | **권장 진료과 + 사유** | ★ |
| `domain_candidates[]` (`domain`,`confidence`,`evidence[]`,`recommended_surveys`) | list | 정신건강 도메인 후보(≤3) | ○ |
| `summary` | str | 추론 요약 | ○ |
| `additional_questions` | list\|None | 추가 확인 질문 | · |
| `retrieval_meta` (`mode`,`chunks_returned`,`chunk_ids`,`queries`) | obj | RAG 검색 메타 | · |
| `finish_reason`/`usage`/`raw_response`/`validation_errors` | — | LLM 텔레메트리 | — |

> `confidence`는 **확률 아님**(REV-013). 축·문구에서 "적합도(참고용)"로만 노출.

### `AIPredictedDiseaseOutput` (같은 JSON 형제 키 `ai_predicted_disease`)
| 필드 | 타입 | 의미 | 등급 |
|---|---|---|---|
| `candidates[]` (`disease`,`similarity_score`,`source_id`,`quote`) | list(≤5) | 질환 유사도 후보 | · (부록) |
| `recommended_questionnaire` | str\|None | 고려 척도 | ★ |
| `recommendation_caveat` | str\|None | 구성타당도 주의(예: PHQ-9 조증 맹점) | ○ |
| `mode` | rag_live/experimental_unpopulated | 산출 방식 | · |
| `disclaimer` / `is_diagnostic(False)` / `reason_summary` | — | 비진단 프레이밍 | · |

> `similarity_score`는 **확률·가능성·진단 아님**. 부록에 "질환 유사도(참고·비진단)"로만.

---

## F3 — 설문 시행 (`*_survey.json`, 스키마 `SurveyResultOutput`)

| 필드 | 타입 | 의미 | 등급 |
|---|---|---|---|
| `outcome` | administered / no_questionnaire_indicated / item_bank_unpopulated | 시행 결과 | ★ |
| `scale_name` | PHQ-9/GAD-7/AUDIT-C… \|None | 척도명 | ★ |
| `score_result.total_score` / `max_score` / `severity` | int/int/str | **총점·최대·심각도** | ★ |
| `score_result.critical_item_positive` | bool | PHQ-9 9번(자살) 양성 | ★ |
| `safety_referral` | bool | 안전 경로 트리거 | ★ |
| `responses[]` | list[int] | 문항별 원점수 | ○ |
| `score_result.subscale_scores` / `critical_items` | dict / list | 하위척도·критical 항목 | ○ |
| `score_result.interpretation` / `recommended_action` | str | 해석·권고 문구 | ○ |
| `administration_mode` | natural/forced/safety_net/si_supplement | 척도 선택 경위 | ○ |
| `threshold_caveat` | str\|None | AUDIT-C 한국 기준·GAD-7 출처 주의 | ○ |
| `audit_c_international_threshold` (`source`,`*_threshold`,`crossed`) | obj\|None | 국제 컷오프(Bush 1998) | · |
| `item_bank_version` / `item_bank_provenance` | str\|None | 문항은행 버전·출처 | · |
| `recommendation_provenance` (F2 통과) | obj | 추천 근거 출처 | · |
| `answer_mode`/`scenario_pack_id`/`arc_mode` | — | 하네스 메타 | — |
| `is_diagnostic(False)` / `disclaimer` | — | 비진단 | · |

---

## F4 — 종단 분석 (`*_temporal.json`, 스키마 `LongitudinalAnalysisOutput`)

### 상위 요약
| 필드 | 타입 | 의미 | 등급 |
|---|---|---|---|
| `n_sessions` / `session_span_days` | int | 세션 수·기간 | ★ |
| `overall_direction` | improved/worsened/unchanged/unknown | **전체 방향** | ★ |
| `course_shape` | gradual_improvement / relapse_after_partial_improvement / worsening_sustained / crisis_episode … | 경과 형태 | ★ |
| `concordance_flag` | concordant/discordant/unknown | 척도-CTRS-정서 일치 여부 | ★ |
| `crisis_f3_gaps[]` | list[str] | 고위험인데 설문 미시행 세션 | ★ |
| `trend_verdicts[]` (`dimension`,`direction`,`basis`,`n_comparable_points`,`evidence[]`) | list | 지표별 추세 결론+근거 | ○ |
| `arc_mode` / `generated_at` / `disclaimer` / `is_diagnostic` | — | 메타·비진단 | · |

### 세션별 시계열 (차트 소스) — 각 point에 `session_index`,`simulated_date`
| 시리즈 | 핵심 값 필드 | 등급 |
|---|---|---|
| `scale_series{scale:[ScaleSeriesPoint]}` | `administered`,`total_score`,`max_score`,`severity`,`critical_item_positive`,`subscale_scores` | ★ (차트/척도변화) |
| `ctrs_series[CTRSSeriesPoint]` | `session_ctrs`,`crisis_triggered`,`probe_event_count`,`risk_floor` | ★ |
| `slot_fill_series[SlotFillPoint]` | `filled_count`,`total_questionable(=8)`,`newly_filled`,`newly_missing`,`mental_status_exam_observed` | ○ (충족도) |
| `sentiment_series[SentimentSeriesPoint]` | `mean_polarity`,`dominant_emotions`,`signal_strength`,`risk_signal_count`,`emotional_shift_detected` | ○ (보조) |
| `disease_candidate_series[…]` | `disease`,`similarity_score`,`rank` | · (부록) |
| `domain_candidate_series[…]` | `domain`,`confidence` | · (부록) |

---

## F5 — 인계 리포트 (`*_handoff.md/.pdf/_fhir.json`, 스키마 `HandoffReportOutput`)

F5는 F1~F4를 **조립**한 결과라 카탈로그의 소비처. 섹션별 소스·등급:

| 섹션 | 필드(요약) | 소스 | 등급 |
|---|---|---|---|
| `a0_header` | persona·session_index·date·session_ctrs·risk_level·crisis_* | F1 | ★ |
| `a1_chief_complaint` / `a2_hpi` | `present`,`text` (최신 세션) | F1 슬롯 | ★ |
| `slot_overview.rows[]` | 12슬롯 best-available: `latest_value`,`source_session_index`,`change_history[]` | F1(전세션) | ★ 값 / ○ 이력 |
| `a3_risk_safety` | `session_ctrs`,`risk_floor`,`crisis_*`,`longitudinal_risk_signals[]`,`staleness_pointer`,`trend_concordance_flag` | F1+F3+F4 | ★ |
| `a4_mental_status` | `raw_text` + `domain_checklist[]`(11 MSE 도메인, 대개 평가불가) | F1 | ○ (대부분 관찰불가) |
| `a5_questionnaires` | `scale_name`,`total_score`,`severity`,`critical_item_positive`,`administering_session_index`,`is_stale_*`,`gap_disclosure`,각종 caveat | F3(+F4 gap) | ★ 점수 / ○ caveat |
| `a6_ai_predicted_disease` | `candidates[]`(rank·tie),`recommended_questionnaire`,`recommendation_caveat` | F2 | · 후보(부록) / ★ 추천척도 |
| `a7_recommendations` | `department_candidates[]`,`recommended_questionnaire`,`medication_note` | F2 | ★ |
| `a8_narrative` | 이번 미션 **비활성**(`narrative_enabled=False`) | — | — |
| `b_longitudinal` | `analysis`(F4 전체) + `chart_filenames` + 민감도/gap 주석 | F4 | ★ 방향/경과 / · 후보시리즈 |

부록성 하위구조: `LongitudinalRiskSignal`(세션별 자살문항/의뢰), `StalenessPointer`(당해 미시행 시
최근 채점 세션 포인터), `ChartReferences`(4개 PNG 파일명), 다수 `*_caveat`(ceiling/threshold/
non_validated). → **caveat류는 해당 수치 옆 1줄**로만, 별도 블록 금지.

---

## 공통 참조

### CTRS 1–5 (위기단계, `schemas/common.py`)
| 값 | 위험 | 명칭 | 의미 |
|---|---|---|---|
| 1 | critical | 초응급 | 자살시도·자해·타해·과량복용 진행 |
| 2 | high | 고위험 | 구체적 자살계획·수단 보유 |
| 3 | medium | 급성기 | 급성 환각/망상·공황·중증 악화 (자살/자해 시 안전탐침) |
| 4 | low | 준안정 | 지속 우울/불안·기능저하 |
| 5 | none | 안정기 | 임박 위험 없음 |

(리포트 차트: 1 하단 → 5 상단, 낮을수록 위험.)

### 척도 심각도 밴드
- **PHQ-9** (0–27): 0–4 정상 / 5–9 경도 / 10–14 중등도 / 15–19 중등–중증 / 20–27 중증. 9번=자살문항.
- **GAD-7** (0–21): 0–4 정상 / 5–9 경도 / 10–14 중등도 / 15–21 중증.
- **AUDIT-C** (0–12): 국제 컷오프 남 4·여 3(Bush 1998); 한국 기준 threshold_caveat 참조.

---

## 컴팩트 편성 제안 (요약)

**본문 핵심(★)만으로 구성 가능한 최소 리포트:**
1. **헤더** — 환자·회차·날짜·현재 CTRS·위험수준·위기여부 (F1 a0)
2. **위험·안전** — 현재 위험평가 + 자살문항/의뢰 세션 신호 + concordance + (당해 미시행 시) staleness 1줄 (F1/F3/F4 a3)
3. **주호소·현병력** + **슬롯 스냅샷**(12슬롯 최신값, 변화 있는 슬롯만 이력) (F1 a1/a2/slot_overview)
4. **최신 설문** — 척도·총점·심각도·자살문항 (+ caveat 1줄) (F3 a5)
5. **종단 요약** — 전체 방향·경과형태·척도 변화 from→to + 차트 FIG.01/02 (F4 b)
6. **권장 진료·척도** (F2 a7)

**부록(·)으로 밀 것:** 질환 유사도 후보/순위, 도메인·진료과 적합도 시계열, 슬롯 전체 이력,
정서/충족도 상세, 각종 caveat 원문.

**생략(—):** turn 로그, LLM 텔레메트리(usage/finish_reason/retry), 정규화 메타, 프롬프트/모델 버전(문서정보 각주로만).
