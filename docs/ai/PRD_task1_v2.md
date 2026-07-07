# Task 1 개발 PRD v2: AI 기반 사전문진 Handoff Report 생성

> **Version**: v2.0
> **Created**: 2026-07-06
> **Status**: Active (supersedes `PRD_task1.md` v1.0 — v1은 참조용으로 보존)
> **Owner**: AI Research 팀
> **Parent Document**: [`docs/AI_master_plan.md`](../AI_master_plan.md)
> **Companion Documents**: `checklist_task1.md` (v2), `development_report.md` (append-only 작업 보고)

---

## 0. 문서 개요

### 0.1 목적

본 문서는 Task 1 (AI 기반 사전문진 Handoff Report 생성)의 PRD v2이다. v1이 **계획 문서**였다면, v2는 다음을 반영한다:

1. **F1 as-built 아키텍처**: 2026-07-03 확정된 F1 파이프라인(`apps/ai-server/src/f1.py`)의 실제 구현 구조 — 3-agent 협업, 12 Standard Clinical Slots, 역할 분리 원칙.
2. **각 기능(F0~F5)의 현재 구현/검증 상태**와 v1 계획 대비 변경 사항.
3. **Phase 2 검증·고도화 방향**: 종단(longitudinal) VP 데이터 기반 검증, 기능별 오케스트레이션 파이프라인(f2~f5), 통합 E2E 검증. 상세 계획은 `development_report.md` 참조.

### 0.2 버전 이력

| 버전 | 날짜 | 변경 사항 |
|------|------|----------|
| v1.0 | 2026-06-18 | 초안. 기능 1-1~1-5 개발/검증 체크리스트, API 명세, Agent 구성 정의 |
| v2.0 | 2026-07-06 | F1 as-built 반영: 12 Standard Clinical Slots 표준화, Safety→Slot→Dialogue 역할 분리 파이프라인, Turn 0 safety, 재상담(follow-up) 모드, 4VP 시뮬레이션 검증 결과. F3/F4/F5 구현 완료 상태 반영. 스키마 통일 결정(§7). Phase 2 검증 전략(§9) 추가 |
| v2.1 | 2026-07-07 | 프롬프트 아키텍처 v3 섹션 추가(§11): Fable-5 역설계 원칙 기반 5개 활성 임상 에이전트 프롬프트 재설계 사양(`docs/ai/prompt_redesign_v3.md` v3.1, REV-002 2026-07-07 non-blocking 종결) + 검증 전략(오프라인 프롬프트 테스트 + Safety Matrix SM-07a/b + VP-001~004 라이브 A/B) 요약 |

### 0.3 v1 대비 핵심 변경 요약

| # | 영역 | v1 계획 | v2 as-built / 결정 |
|---|------|---------|-------------------|
| 1 | Slot 스키마 | 13-field `SlotData` (chief_complaint, onset, duration, triggers, sleep, ...) | **12 Standard Clinical Slots**가 canonical (§2.3). `SlotData`와의 정합화는 Phase 2 항목 |
| 2 | Slot 추출 주체 | Dialogue agent가 응답 생성 + slot 추출 겸임 | **역할 분리**: ClinicalSlot(추출 전담), Dialogue(응답 전담), Safety(분류 전담), f1.py(오케스트레이션 전담) |
| 3 | Agent 호출 순서 | Safety ∥ ContextRetrieval 병렬 → Dialogue → ClinicalSlot(optional batch) | 매 턴 **Safety → Slot → Dialogue** 순차 (Slot을 Dialogue보다 먼저 실행하여 최신 slot 기반 질문 생성) |
| 4 | Turn 0 | 미정의 | AI 인사 → 환자 첫 응답에 대해 **Safety + Slot 즉시 실행**, crisis 시 즉시 종료 |
| 5 | Safety 구조 | rule + LLM dual path (개요 수준) | **C 방식 확정**: Rule engine = 1차 스크리닝(부정 문맥 감지 포함) → LLM = 최종 판정, LLM 장애 시 rule 결과 fail-safe |
| 6 | 세션 종료 | 8-15턴 도달 / crisis / handoff 준비 | 질문 가능 슬롯(8개) 전부 수집 시 **자동 종료(handoff ready)** + 반복 감지(2회 연속) 종료 + crisis 종료 |
| 7 | 재진 처리 | prior handoff 주입(개요) | **명시적 follow-up 모드**: `--followup-from`으로만 활성화. `generate_handoff_from_result()` → prior_handoff + prior_slots 주입. 종단 검증의 기반 |
| 8 | 프롬프트 | 상세 지시 중심 | **간결화 확정**: dialogue 228→54줄, safety 208→58줄, clinical_slot 157→67줄. 하드코딩 금지, PromptLoader 로드 |
| 9 | 검증 방법 | VER 항목 나열 | 4VP × Patient LLM(K-EXAONE) 시뮬레이션 체계 확립. Phase 2: **종단 multi-session 프로토콜** (§9) |

### 0.4 개발 범위 / 제외 범위

v1과 동일 (`apps/ai-server/`, `apps/api/`, `docs/ai/`; Task 0/2/3, Frontend, 인프라 제외).

---

## 1. ID 체계 및 Agent 매핑

ID 형식 `T1-Fn-{TYPE}-{SEQ}` 및 기능 번호(F0~F5)는 v1과 동일하다. **ID는 전역적으로 증가하며 재사용하지 않는다.** v2 체크리스트(`checklist_task1.md`)는 v1 ID를 승계하고 Phase 2 신규 항목을 이어 붙인다.

### 1.1 Agent ↔ 코드 매핑 (as-built)

| Agent | 코드 모듈 | 상태 | 소비 기능 |
|---|---|---|---|
| Orchestrator (state machine) | `agents/orchestrator.py` (11-state) | 구현 완료 | F0, 프로덕션 `/ai/chat/respond` |
| F1 Pipeline Orchestrator | `src/f1.py` (경량, LLM 미호출) | 구현 완료 | F1 시뮬레이션/검증 |
| SafetyClassifier | `agents/safety_classifier.py` | 구현 완료 | F1, F3(위험 문항 연동) |
| Dialogue | `agents/dialogue.py` | 구현 완료 | F1 |
| ClinicalSlot | `agents/clinical_slot.py` | 구현 완료 | F1, F3 |
| InputNormalizer | `agents/input_normalizer.py` | 구현 완료 | F1 (STT/OCR 대기) |
| SentimentAnalyzer | `agents/sentiment_analyzer.py` | 구현 완료 | F1(미연동), F4 |
| TemporalRetriever | 미구현 | **미구현** | F2 |
| TemporalSummary | `agents/temporal_summary.py` | 구현 완료 | F4 |
| HandoffGenerator | `agents/handoff_generator.py` | 구현 완료 | F5 |
| EvidenceVerifier | `agents/evidence_verifier.py` | 구현 완료 | F5 |
| STT adapter | 미구현 (`adapters/stt_adapter.py` 없음) | **미구현** | F1 |
| OCR adapter | 미구현 (`adapters/ocr_adapter.py` 없음) | **미구현** | F1 |

**이중 오케스트레이션 주의:** F1 검증용 `f1.py`와 프로덕션용 `agents/orchestrator.py`(11-state)가 병존한다. 두 경로의 slot 스키마·세션 종료 조건·coverage 기준 정합화는 Phase 2 항목이다 (§7, §9).

---

## 2. 기능 1-1 (F1): 자율 대화 기반 문진 — As-Built

### 2.1 개요

가상/실제 환자와의 자율 대화를 통해 12 Standard Clinical Slots를 수집하는 멀티에이전트 파이프라인. 2026-07-03 4VP 시뮬레이션은 이슈 0건으로 보고되었으나, **2026-07-06 통합 감사(QA/Critic/Architecture, `development_report.md` DR-001)에서 slot 값의 상당수가 프롬프트 예시 echo(날조)로 확인되어 "안정적 slot 수집 통과" 판정은 무효화되었다.** 아키텍처(역할 분리, 위기 대응 흐름)는 유효하며, Phase 2에서 grounding 수정 후 재검증한다.

**핵심 특징:**
- Patient LLM(K-EXAONE)과 Clinical Agents(Solar Pro3)의 완전 정보 격리
- 매 턴 Safety → Slot → Dialogue 3-agent 협업, 역할 분리 철저
- 질문 가능 슬롯 전부 수집 시 자동 세션 종료 (handoff ready)
- 명시적 follow-up 모드로 재상담(종단) 시나리오 지원

### 2.2 확정 아키텍처 (per-turn)

```
Patient Message
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                  f1.py (Orchestrator — LLM 미호출)        │
│                                                         │
│  Step 1: SafetyClassifier                               │
│    Rule 스크리닝(부정 문맥 감지) → LLM 최종 판정          │
│    crisis(CTRS 1-2) → CRISIS_RESPONSE(109/119) → 종료    │
│                                                         │
│  Step 2: ClinicalSlot (매 턴, Dialogue보다 먼저)          │
│    12 Standard Slots만 merge (비표준 키 차단)             │
│                                                         │
│  Step 3: Dialogue (최신 filled_slots + safety 결과 사용)  │
│    공감 1문장 + 미수집 슬롯 유도 질문 1개                  │
│                                                         │
│  Step 4: History 갱신 + Coverage 계산 + 종료 판정         │
│    질문 가능 슬롯 완수 → 종료 / 반복 2회 → 종료           │
└─────────────────────────────────────────────────────────┘
```

**역할 분리 원칙 (위반 시 회귀로 간주):**

| 역할 | 담당 | 금지 사항 |
|------|------|----------|
| 위험도 분류 (CTRS) | SafetyClassifier | 응답 생성, 슬롯 추출 |
| 슬롯 추출 | ClinicalSlot | 응답 생성, 위험도 판단 |
| 응답 생성 | Dialogue | 슬롯 추출, 위험도 판단, coverage 계산 |
| 세션 제어·coverage | f1.py | LLM 호출 |

### 2.3 12 Standard Clinical Slots (canonical 스키마)

| No | Slot Key | 수집 방법 | Essential | 질문 가능 |
|----|----------|-----------|:---:|:---:|
| 1 | `encounter_metadata` | System auto | - | X |
| 2 | `chief_complaint` | Dialogue 유도 | O | O |
| 3 | `history_of_present_illness` | Dialogue 유도 | O | O |
| 4 | `past_psychiatric_history` | Dialogue 유도 | - | O |
| 5 | `medical_history` | Dialogue 유도 | - | O |
| 6 | `personal_social_history` | Dialogue 유도 | - | O |
| 7 | `family_history` | Dialogue 유도 | - | O |
| 8 | `substance_use_history` | Dialogue 유도 | - | O |
| 9 | `mental_status_exam` | 관찰 기반 (질문 금지) | O | X |
| 10 | `risk_assessment` | Dialogue 유도 | O | O |
| 11 | `clinical_assessment` | 대화 종료 후 자동 | - | X |
| 12 | `treatment_plan` | 의료진 영역 | - | X |

- **Coverage** = filled essential slots / 5 (`ESSENTIAL_SLOT_KEYS`). 4VP 검증 시 80% (mental_status_exam은 text-only에서 제한적).
- **추출 규칙**: 언급 없으면 null / 환자 표현 보존 / 진단명 금지 / **부정 응답도 유의미한 값으로 수집** ("없어요" → "진단받은 신체 질환 없음") / 비표준 키는 `_KEY_ALIASES` 매핑 후 `ALL_SLOT_KEYS` 필터로 차단.
- 이 12-slot 스키마가 **canonical**이다. F5 `SlotData` 등 타 스키마와의 정합화는 §7 참조.

### 2.4 Safety 아키텍처 (as-built)

```
Rule Engine (키워드 스크리닝 + 활용형 변형 + 부정 문맥 감지)
     ├── rule_level = none → LLM 독립 분류
     └── rule_level = high/critical → flagged keywords를 LLM에 전달
                                        ▼
                                   LLM 최종 판정 (문맥 우선, 시제 확인,
                                   증상 악화 보고 ≠ 자살 위험)
                                        ▼
                          final = LLM 결과 (LLM 장애 시 Rule 결과 fail-safe)
```

- CTRS 1-2 → crisis protocol: 일반 문진 즉시 중단, 109/119 안내.
- **CTRS 3 + 자살/자해 category → Safety Probe 모드 (v2 신규 설계, ISS-035)**: 즉시 종료 대신 구조화 안전 탐문을 강제 삽입하고, 탐문 응답 재분류 결과에 따라 CTRS 2 승급(위기 종료) 또는 grounded 위험 기록 후 문진 지속. 세션 위험 latch(floor CTRS 3) + handoff 권고 문구 검증 연동. 상세: `development_report.md` DR-002, 체크리스트 T1-F1-DEV-022/023.
- 키워드 사전은 한국어 활용형 변형 포함 (ISS-003/004: "손목을 그었", "약을 많이 먹") 및 복약 순응 표현 오탐 제거 (ISS-013: "약을 먹고 있어요" ≠ 과다복용).
- 위기 키워드 recall 회귀 테스트 유지 (`test_safety_keyword_recall.py`, 13/13 critical).
- 프롬프트 하드코딩 금지 — `PromptLoader`로 `prompts/safety_classifier/v1.system.md` 로드.

### 2.5 세션 수명주기 규칙

1. **Turn 0**: AI 인사 → 환자 첫 응답에 Safety + Slot 즉시 실행. crisis 시 Turn 0 종료.
2. **Crisis**: 어느 턴이든 CTRS 1-2 → `CRISIS_RESPONSE` 반환 + 세션 종료. crisis=True인데 crisis response 없는 케이스 0건이 검증 기준.
3. **자동 종료**: 질문 가능 슬롯 8개 전부 수집 && turn >= 3 → handoff ready 종료. 마지막 턴에서 새 질문 금지(요약 모드).
4. **반복 방지**: 동일 AI 응답 2회 연속 → 세션 종료 + 에러 기록. `_build_slot_context`에 이전 3턴 질문 요약 + 공감 표현 사용 금지 목록 주입.
5. **Safety/Dialogue 실패**: 해당 턴에서 세션 중단 + errors 기록 (fail-closed).

### 2.6 재상담 (Follow-up) 모드 — 종단 데이터 기반

- `--followup-from {VP-ID | conversation.json}`으로만 활성화 (persona의 `visit_type=revisit`만으로는 활성화되지 않음 — 과분류 방지).
- 이전 세션 결과 → `generate_handoff_from_result()` → prior_handoff 텍스트 + prior_slots 주입.
- Patient LLM persona에도 이전 상담 기록을 주입하여 "호전/악화/유지"를 자연스럽게 반영.
- 첫 인사에 이전 주호소 요약 (`_summarize_prior_handoff`) 포함.
- **현재 상태: 구현 완료, 검증 0건.** 종단 검증(F1 follow-up + F4/F5 연계)은 Phase 2 최우선 항목 (§9).

### 2.7 시뮬레이션·산출물 체계

- 실행: `cd apps/ai-server && .venv/bin/python -m src.f1 --persona VP-00N --max-turns 10 [--followup-from VP-00N]`
- 산출물: `docs/ai/simulation_results/{VP-ID}/{VP-ID}_{ts}_conversation.json` + `_report.md` + `_checklist.md`
- Patient LLM: K-EXAONE (`tests/simulation/patient_llm.py`), Clinical: Solar Pro3 (fallback: K-EXAONE → SKT A.X K1)

### 2.8 F1 검증 현황 및 잔여 격차

**2026-07-03 보고 수치 (2026-07-06 감사로 evidence 무효화 — 아래 G0 참조):**

| VP | Turns | Crisis | 보고 Coverage | 감사 후 grounded coverage (추정) |
|----|-------|--------|----------|-------|
| VP-001 (초진 경증) | 3 | No | 80% | ~40% (essential 2/5) |
| VP-002 (첫 상담) | 3 | No | 80% | ~40% |
| VP-003 (초진 중증) | 0 | Yes (T0, CTRS 2) | 80% | 슬롯 근거 2/9 — 0턴 세션이 80%로 보고된 것 자체가 지표 결함 |
| VP-004 (첫 상담) | 3 | No | 80% | ~40% |

유효하게 검증된 것: 위기 감지·109/119 안내·즉시 종료(VP-003 2회 재현), 매 턴 Safety 호출, 비표준 slot 키 0건, 역할 분리 아키텍처.

**격차 목록 (Phase 2 검증 대상, 상세 근거는 development_report.md DR-001):**

| # | 격차 | 심각도 |
|---|------|--------|
| **G0** | **Slot 날조(fabrication)**: clinical_slot 프롬프트 예시 JSON이 최종 slot 값으로 verbatim 유입. VP-003(자살 사고 표현)에 `risk_assessment: "자살/자해 사고 명시적 부인"` 기록 — 안전 치명. 날조 fill이 조기 종료·coverage 80%의 직접 원인 | **critical** |
| G1 | follow-up(재상담) 경로 검증 0건 — 종단 데이터 미수집. followup handoff 생성기 자체 결함 (min-CTRS fallback, 비표준 8-section) | critical |
| G2 | VP당 n=1 단일 런 — 동일 야간 연속 런에서 상반된 risk_assessment 산출 등 불안정성 실증 | major |
| G3 | 3턴 조기 종료 런만 존재 — 장기 세션(10턴+) 품질 미검증 (00:54 VP-004 10턴 런은 4회 반복 루프 포함) | major |
| G4 | 중간 턴 위기 전환, 간접·부정 문맥, CTRS 3+자해사고(VP-004 spec) 파이프라인 수준 검증 없음 | critical |
| G5 | slot 값의 발화 근거(grounding)·persona ground-truth 대비 충실도 정량 평가 없음 | major |
| G6 | STT/OCR 입력 경로 미구현 (ISS-011) | major |
| G7 | SentimentAnalyzer가 f1.py 루프에 미연동 (F4 입력 생성 불가) | minor |
| G8 | 검증된 경로(f1.py) ≠ 프로덕션 경로(orchestrator/chat) — 프로덕션 경로는 현재 부팅 불가·slot 누적 불능·구 핫라인(1393) 사용 | critical |

### 2.9 F1 API 상태

| 경로 | 상태 | 비고 |
|------|------|------|
| `python -m src.f1` (CLI 시뮬레이션) | 운영 중 | 검증 표준 경로 |
| `POST /ai/chat/respond` | 구현 (orchestrator 경유) | f1.py와의 동작 정합성 검증 필요 (§7) |
| `POST /ai/stt/transcribe`, `POST /ai/ocr/parse` | 미구현 | 벤더 계약 대기 (ISS-011) |

---

## 3. 기능 1-2 (F2): RAG 기반 정신건강 영역/진료과 후보 추론

**상태: 미구현 (Task 1 잔여 기능 중 유일한 미착수).**

v1 계획(TemporalRetriever agent, LLM-only fallback 모드 우선, pgvector placeholder)은 유지한다. v2 추가 결정:

1. **LLM-only 모드 우선 구현** — knowledge base/pgvector 확정 전, F1 세션 산출물(12 slots + CTRS)을 unified context로 직접 입력받아 domain/department 후보를 추론.
2. **f2.py 파이프라인**: F1 conversation.json을 입력으로 TemporalRetriever를 호출하고 후보·confidence·evidence를 산출물로 저장하는 검증 파이프라인을 f1.py 패턴으로 구축 (§9.4).
3. 입력 스키마는 §7의 canonical 12-slot을 사용한다 (v1의 unified_context 정의를 12-slot으로 갱신).

API 명세(`POST /ai/temporal/retrieve`)와 검증 항목(T1-F2-VER-001~004)은 v1을 승계한다.

---

## 4. 기능 1-3 (F3): 구조화된 사전문진 설문

**상태: 구현 완료. Scoring unit test 통과. E2E(F1 대화 → 설문 선택 → 채점 → Safety 연동) 검증은 합성 입력 기반 — 실데이터 E2E는 Phase 2.**

- ClinicalSlot agent: F1과 공유 (12 Standard Slots, §2.3). `POST /ai/slots/extract` 운영.
- Survey Scoring: rule-based 모듈 (PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C), LLM 미사용. `POST /ai/survey/score` 운영. Boundary unit test 통과 (T1-F3-VER-001~002).
- Survey Planner: Orchestrator routing에 통합 (PHQ-4 스크리닝 → subscale 기반 PHQ-9/GAD-7 추가, 음주 표현 → AUDIT-C, CTRS 1-2 → 설문 중단).
- 위험 문항 연동: PHQ-9 문항 9 >= 1 → Safety re-evaluation 트리거 (T1-F3-VER-004 통과).

**v2 유의점:** F1 자율 대화는 척도 점수를 생성하지 않는다. 종단 검증(F4)에 필요한 scale_scores는 **F3 설문 실행을 통해서만 생성**되므로, 종단 프로토콜에 VP별 설문 응답 시뮬레이션(persona의 PHQ-9/GAD-7 기준값 사용)을 포함해야 한다 (§9.3).

---

## 5. 기능 1-4 (F4): 종단적 상태 추론

**상태: 구현 완료. 합성 입력 기반 검증 통과 (VP-002 호전 / VP-004 악화 / 초진 unknown / 모순 감지). 실제 F1 세션 연쇄 데이터로는 미검증.**

as-built 반영 사항:
- Direction 판정: **majority vote** (2/3 도메인 개선 → improved), worsened 우선 안전 규칙 유지 (ISS-016 수정).
- all-unknown → `unknown` 반환 (ISS-014 수정: 빈 iterable에 대한 `all()` 함정 제거).
- Sentiment polarity 비교 부동소수점 보정 (ISS-015).
- Plot-ready 시계열 출력 (날짜별 척도 점수 + CTRS + 이벤트).

**Phase 2 핵심**: F1 follow-up 세션 연쇄(§9.3)에서 생성된 **실제** prior/current 데이터(수집 slot 변화, 설문 점수 변화, sentiment 추이)로 direction 판정을 재검증한다. Evidence 필수 원칙(evidence 없는 판정 → unknown) 준수를 EvidenceVerifier 수준에서 확인한다.

---

## 6. 기능 1-5 (F5): Handoff Report 생성

**상태: 구현 완료. 4VP handoff 생성 + EvidenceVerifier 검증 통과 (합성/단일 세션 입력 기반). 12-section 완전성 자동 검증 및 evidence citation coverage 테스트 통과.**

as-built 반영 사항:
- 12-section 템플릿 강제 + `section_completeness` 필드.
- Evidence registry + dangling reference 검증, CTRS-action 일관성 검증.
- 재생성 루프: passed → 반환 / regenerate → 최대 2회 / reject → HTTP 422, 소진 시 `requires_human_review=True`.
- PDF/JSON 듀얼 출력.
- `SlotData` 필드 누락 수정 (ISS-018): history_of_present_illness, psychosocial_context, substance_use, energy 추가.
- Handoff 위험도 = 세션 내 최대 심각도 (risk cap 수정), scale_scores + risk_events 인계 시 데이터 손실 수정 (2026-07 초 merge).

**Phase 2 핵심**: 실제 F1 세션 → (F3 설문) → (F4 종단) → F5 handoff의 **전체 체인 E2E** 검증. Section 9(종단 변화)가 실데이터로 채워지는지, Section 12 evidence가 실제 대화 원문으로 추적되는지 확인 (§9.5).

---

## 7. 스키마 통일 결정 (v2 신규)

**결정: 12 Standard Clinical Slots (§2.3)가 Task 1 전체의 canonical slot 스키마이다.**

근거: F1 검증 통과의 기반 스키마이며, 임상 문진 표준 구조(주호소/현병력/과거력/가족력/사회력/물질사용/MSE/위험평가/평가/계획)와 1:1 대응한다.

파생 조치 (Phase 2 체크리스트 항목으로 관리):

| # | 조치 | 대상 |
|---|------|------|
| S1 | `schemas/handoff.py::SlotData`를 12-slot 기준으로 정합화 (또는 명시적 양방향 매핑 테이블 도입) | F5 |
| S2 | `agents/orchestrator.py` `_build_handoff_input()` 등 프로덕션 경로의 slot 키를 canonical로 통일 | F0 |
| S3 | F2 unified_context, F4 TemporalSummaryInput의 slot 참조를 canonical로 통일 | F2, F4 |
| S4 | f1.py ↔ orchestrator.py의 coverage 기준·세션 종료 조건 단일화 | F0, F1 |

레거시 13-field 키(onset, duration, triggers, sleep, ...)는 12-slot 내 서술 값으로 흡수한다 (예: onset/duration → `history_of_present_illness`).

---

## 8. API 명세 종합표 (v2 상태 반영)

| Method | Path | v1 계획 | v2 상태 |
|--------|------|---------|---------|
| POST | `/ai/chat/respond` | 기존 수정 | 구현 (Orchestrator 연동). f1.py와 정합성 검증 필요 |
| POST | `/ai/safety/classify` | 기존 유지 | 구현 (CTRS 필드 포함) |
| POST | `/ai/stt/transcribe` | 신규 | **미구현** (ISS-011) |
| POST | `/ai/ocr/parse` | 신규 | **미구현** (ISS-011) |
| POST | `/ai/slots/extract` | 신규 | 구현 |
| POST | `/ai/survey/score` | 신규 | 구현 (rule-based) |
| POST | `/ai/temporal/retrieve` | 신규 | **미구현** (F2) |
| POST | `/ai/temporal/summarize` | 신규 | 구현 |
| POST | `/ai/handoff/generate` | 기존 수정 | 구현 (12-section + 검증 루프) |
| POST | `/ai/sentiment/*` | (v1 미정의) | 구현 (utterance/session 모드) |

SLA, Request/Response 스키마 상세는 v1 §2.5, §3.5, §4.5, §5.5, §6.6을 승계한다 (slot 필드는 §7 canonical로 읽는다).

---

## 9. Phase 2 검증 전략 (v2 신규 — 상세는 development_report.md)

### 9.1 원칙

1. **실데이터 연쇄 우선**: 합성 입력 검증(Phase 1)은 필요조건일 뿐이다. Phase 2는 F1 세션 산출물이 F2~F5로 **실제로 흘러가는** 체인을 검증한다.
2. **종단 프로토콜**: 각 VP에 대해 다중 세션(초기 → follow-up ×2)을 실행하여 종단 데이터를 축적하고, 이를 F4/F5/F2 검증의 입력으로 사용한다.
3. **기능별 파이프라인**: f1.py 패턴(CLI 실행, JSON+report+checklist 산출, 재현 가능)을 f2~f5로 확장한다.
4. **정량 기준**: 각 VER 항목은 pass 기준을 수치로 정의한다 (재현성 n>=3, faithfulness 평가, coverage, recall).
5. **다중 관점 QA**: 코드 감사(QA), 검증 타당성 감사(Critic), 아키텍처 정합성 감사를 병행하고 의견을 통합하여 이슈를 확정한다.

### 9.2 검증 게이트

| Gate | 내용 | 통과 조건 |
|------|------|----------|
| **G-0** | **긴급 복구 (Stage 0)** | 서버 부팅 복구(trend_plotter), ISS-020 fix 재적용, safety fail-closed 재수정, 격리 테스트 스위트 복원 — 전체 테스트 green |
| **G-F** | **F1 grounding 재검증** | clinical_slot 프롬프트 grounding 수정 후 slot-근거 자동 감사 통과 (날조 0건), n>=3 재현 |
| G-A | F1 종단 프로토콜 완료 | 4VP × (초기 + follow-up 2회) 세션, slot faithfulness 평가 완료 |
| G-B | Safety 심층 검증 | 중간 턴 위기 전환·부정 문맥·간접 표현·CTRS3+자해 시나리오 파이프라인 레벨 통과 |
| G-C | 스키마 통일 (§7) | S1~S4 완료 + 핫라인 상수 통일 + 회귀 테스트 통과 |
| G-D | 기능별 파이프라인 검증 | f3/f4/f5 파이프라인 실데이터 통과, F2는 구현 후 |
| G-E | 통합 E2E | F1→F3→F4→F5 전 체인, 4VP, EvidenceVerifier passed |

게이트 순서: G-0 → G-F → (G-A ∥ G-B ∥ G-C) → G-D → G-E. **G-0/G-F 통과 전에는 어떤 "pass" 주장도 갱신하지 않는다.**

### 9.3 종단 VP 프로토콜 (요약)

```
세션 S1 (초기):   f1.py --persona VP-00N            → conversation.json + handoff
설문 Q1:         persona 기준값으로 PHQ-9/GAD-7 채점  → scale_scores(t1)
세션 S2 (재상담): f1.py --persona VP-00N --followup-from S1 → 변화 반영 대화
설문 Q2:         변화 반영 응답 채점                  → scale_scores(t2)
세션 S3 (재상담): S2 기반 반복                        → scale_scores(t3)
                          ▼
      VP별 종단 데이터셋: slots(t1..t3), scores(t1..t3), sentiment(t1..t3), handoffs
```

### 9.4 기능별 오케스트레이션 파이프라인 (f1.py 패턴)

| 파이프라인 | 입력 | 호출 체인 | 산출물 |
|-----------|------|----------|--------|
| `f2.py` (구현 후) | F1 conversation.json + slots | context assembly → TemporalRetriever | domain/department 후보 + evidence |
| `f3.py` | F1 slots + persona 설문 기준값 | Survey Planner rule → Scoring → (양성 시) Safety 재평가 | scale_scores JSON + 위험 연동 로그 |
| `f4.py` | 종단 데이터셋 (t1..tN) | SentimentAnalyzer(세션별) → TemporalSummary | direction + evidence + plot_data |
| `f5.py` | F1 slots + F3 scores + F4 summary + risk events | HandoffGenerator → EvidenceVerifier (재생성 루프) | 12-section report + verifier 판정 |

### 9.5 통합 E2E

`fe2e.py` (또는 f5.py의 `--full-chain` 모드): S1~S3 산출물을 순서대로 F3→F4→F5에 공급하고, 최종 handoff의 Section 9(종단 변화)·Section 12(evidence registry)가 실데이터와 일치하는지 자동 대조한다.

---

## 10. CTRS ↔ RiskLevel 매핑

v1 §13과 동일 (구현 완료: `schemas/common.py`의 `CTRSLevel`, `RISK_TO_CTRS`). CTRS는 숫자가 낮을수록 위험. crisis flow는 CTRS 1-2.

---

## 11. 프롬프트 아키텍처 v3

**상태: 설계 확정(brainstorm A1, critic REV-002 2026-07-07 non-blocking 종결). 프롬프트 파일 작성·구현은 Phase 2 developer(Stage C1, `checklist_task1.md` 신규 항목 T1-F1-DEV-024~028) 소관.**

Claude Fable 5 시스템 프롬프트(소비자 chat 배포판, 약 3,800줄)를 역설계해 이 프로젝트의 소형 한국어 LLM(Solar Pro3/K-EXAONE)에 전이 가능한 설계 원칙을 추출하고, 5개 활성 임상 에이전트 프롬프트를 코드 출력 계약(byte-identical)을 유지한 채 재설계하는 작업이다. 전체 사양의 authoritative source는 `docs/ai/prompt_redesign_v3.md`(v3.1)이며, 아래는 PRD 독자를 위한 요약이다(상세 근거·인용은 원문 참조, 여기서는 중복 서술하지 않는다).

### 11.1 원칙 (Fable-5 역설계 — P1~P12 요약)

`prompt_redesign_v3.md` §1이 정의하는 12개 원칙(P1~P12)은 크게 4갈래로 묶인다:

| 갈래 | 해당 원칙 | 요지 |
|---|---|---|
| 경계·계약형 | P1, P2, P3, P8 | 역할 경계를 단독 절대 문장으로 명시, 출력 계약을 프롬프트 최종 섹션으로 통일, 절대 규칙은 5개 이하로 압축, 지시는 번호화된 우선순위(첫 매치에서 정지)로 배치 |
| 근거주의형 | P4, P5, P11 | 근거 없는 서술은 침묵/null 처리("근거 없으면 침묵" — clinical_slot의 기존 null 원칙과 동일 구조), 불확실성은 명시적 라벨로 표기, 출력 전 자체 점검 |
| 오염 방지형 | P7, P12 | 프롬프트 예시는 명백한 placeholder만 사용(DR-001/ISS-027 echo 재발 방지), 런타임 주입 컨텍스트의 구체값을 정적 프롬프트에 하드코딩하지 않음 |
| 톤·포맷형 | P6, P9, P10 | 단정적 확답 대신 계조적(graduated) 언어, 위기 신호 시 정보 제공 대신 우회 대응(기존 Safety Probe 설계와 철학적으로 동일), 장식적 마크다운 최소화 |

각 원칙의 Fable-5 원문 근거(짧은 발췌)·소형 모델 적용 근거·토큰 예산 지침은 `prompt_redesign_v3.md` §1의 P1~P12 세부 항목을 참조한다.

### 11.2 대상 — 5개 활성 임상 에이전트 (현재 → 목표 버전)

| 에이전트 | 현재 | 목표 | 핵심 변경 (상세: `prompt_redesign_v3.md` §2.x) |
|---|---|---|---|
| safety_classifier | v1 | v2 | 절대 규칙 5개로 압축(ISS-046 관용구 규칙 신규) + v1 핵심 규칙 7개 중 5개 verbatim 보존·2개 표 통합(삭제 0개, REV-002 #2 확인) + ISS-048/050 신규 앵커. I/O 계약(5키) 불변 |
| dialogue | v1 | v2 | 절대 금지 8→6개 통합, "Safety 참고 행동" 섹션 5→1줄 축소(P12 — 런타임 `_build_slot_context`/`safety_context` 주입과의 중복 제거). I/O 계약(`assistant_response`) 불변 |
| clinical_slot | v2 | v3 | 최우선 원칙 5개 hold(내용 불변). risk_assessment ↔ SafetyClassifier 상호참조 노트는 프롬프트에 넣지 않음(REV-002 #3 — `ClinicalSlotInput`이 safety 결과를 받지 않아 모델 지시로는 실행 불가; 조정은 오케스트레이션 코드 레벨 사후 처리로 이관, 본 PRD 범위 밖). I/O 계약(12키) 불변 |
| handoff_generator | v1 | v2 | ctrs_level 출력 지시 삭제(ADR-007 옵션A 확정 — dead instruction, `handoff_generator.py`가 `resp.content`를 JSON 파싱 없이 그대로 사용) + P7 placeholder화 7곳(§6/§8/§9/§12) + evidence citation 반복 지시 3회(§3/§5/§7)→1회 통합. I/O 계약(12개 H2 제목 + `[ev_*]` 토큰) 불변 |
| sentiment_analyzer | v1 | v2 | session 모드 섹션 전체 삭제(코드 확인 결과 LLM 미호출 dead prompt, `_analyze_session()`은 순수 Python 집계) + `turn_index` 예시 필드 제거(코드가 덮어씀) + `evidence_phrase` placeholder화. I/O 계약(5키, utterance 모드만) 불변 |

**고아 프롬프트 제외:** `orchestrator`, `temporal_summary`, `evidence_verifier`(런타임 미로드/rule-based), `temporal_retriever`/`stt`/`ocr`/`prompt_eval`(미구현) 8개는 이번 v3 재설계 범위에서 제외되며 상태만 표기한다 — 근거는 `prompt_redesign_v3.md` §3(코드 확인 완료).

### 11.3 검증 전략

**오프라인 프롬프트 테스트 (Stage C1, developer 구현):** 5개 프롬프트 파일에 대해 placeholder-only 예시, 필수 출력 스키마 키 문자열 존재, 절대 규칙 핵심 문구 존재, char 예산 상한, session 모드 섹션 부재(sentiment), ISS-050 재채점 일관성 문구(safety), v1 핵심 규칙 7개 존치(safety), evidence citation 단일 선언(handoff) — 총 8개 단정문을 자동 검사한다(`prompt_redesign_v3.md` §4.1).

**Safety Matrix (라이브, SM-07a/SM-07b 신설):** 기존 SM-01~06(`development_report.md` DR-003에서 7/7 통과 확인)에 더해 ISS-046 관용구 오탐 방지 시나리오 **SM-07a**(공황/응급실 회고, 자살 의도 없음 — `crisis_triggered==false` 기대)와 그 필수 대조군 **SM-07b**(동일 프레이밍 + 실제 자살 의도 병존 — `crisis_triggered==true` 기대, 오버코렉션/false negative 방지)를 신설한다. SM-01~06 + SM-07a + SM-07b **8개 시나리오 전건 필수 통과**(대조군도 "권장"이 아닌 필수).

**VP-001~004 라이브 A/B (DR-003 베이스라인 대비):** DR-003 베이스라인(2026-07-06, commit 9aea999) — fabrication 0/8 VP 런(n=2/VP), Safety Matrix 7/7, Safety Probe 발동률 100%, SI screen 준수율 75%(목표 100% 미달, ISS-047) — 대비 v3 프롬프트로 VP-001~004 각 **최소 n≥2 세션**(n≥3 권장, DR-003과 동일 표본 이상)을 재실행하고 동일 정의로 fabrication count, grounded_coverage, crisis accuracy, probe rate, CTRS calibration(ISS-046/048/050 재발 여부), 섹션별 evidence citation 첨부율을 재측정한다. n≥2 미만 결과로는 "회귀 없음"/"개선" 문구를 사용하지 않는다.

**ISS-049 정책 고지(ADR-010, ADR-012):** 수동적 자살사고 표현을 첫 발화이든 세션 중 어느 시점이든 즉시 CTRS 2/crisis로 라우팅하도록 **사용자 정책은 확정되었다**(ADR-010, "즉시 대응하자" — ADR-006의 잠정 유지 방침을 대체). 단 이 정책의 첫 구현 시도(safety_classifier v3)는 라이브 검증(EXP-003)에서 SM-04a/SM-04b 프로브 회귀로 롤백되어(ADR-012), 현재 라이브 라우팅은 v2 기준(CTRS 3 → Safety Probe 경유)으로 남아 있다 — v4 재설계 대기 중(DR-005). 본 문서 §11.3의 A/B 비교(DR-003 대비 EXP-002)는 v3 이전, ADR-006 치하에서 수행된 과거 비교이며 소급 수정하지 않는다.

**롤백 기준:** 다음 중 하나라도 관찰되면 버전 핀을 이전 프롬프트(v1/v2)로 즉시 되돌리고 정직하게 보고한다 — (1) fabrication count > 0(어느 하나라도), (2) crisis miss(SM-01~06 + SM-07a/SM-07b 8개 전건 중 하나라도 `crisis_triggered` 기대와 불일치), (3) probe miss(CTRS 3 + 자살/자해 category 조건에서 Safety Probe 미발동). 롤백 시 critic이 독립적으로 원인을 재검토하기 전까지 "개선되었다" 문구를 사용하지 않는다.

**범위 caveat:** 위 A/B는 `f1.py` 시뮬레이션 하네스(검증된 경로)에서 실행되며, 세션 위험도 하한(session risk floor)은 `f1.py`에서만 확인되고 `orchestrator.py`/`routes/`에서는 동일 기능이 확인되지 않았다(기존 gap, ISS-029). 결론은 `f1.py`-검증 경로로 범위를 한정하며, 프로덕션 오케스트레이터 경로로 일반화하려면 별도 확인이 선행되어야 한다.

---

## 부록 A. v1 문서와의 관계

- v1(`PRD_task1.md`)은 원 계획과 상세 API/DB 스키마 정의의 참조 문서로 보존한다.
- 충돌 시 **v2가 우선**한다. 특히 slot 스키마(§2.3, §7), F1 아키텍처(§2), 기능 상태(§3~6)는 v2 기준.
- 이슈 이력은 `docs/ai/backups/issues.md`(ISS-001~018), 세부 해결 내역은 `docs/ai/backups/f1_issue_resolution_report.md` 참조.

*End of Document*
