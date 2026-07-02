# F1 Feature Development Status

> Feature: 자율 대화 기반 사전문진 파이프라인 (Autonomous Dialogue-based Pre-consultation Pipeline)
> Last Updated: 2026-07-03

---

## 1. Overview

F1은 가상/실제 환자와의 대화를 통해 12개 표준 임상 슬롯(Standard Clinical Slots)을 수집하는 멀티에이전트 파이프라인이다.

**핵심 특징:**
- Patient LLM(K-EXAONE)과 Clinical Agents(Solar Pro3)의 완전 독립 동작 (information isolation)
- 매 턴 Safety → Slot → Dialogue 순서로 3개 Agent 협업 호출
- 12 Standard Clinical Slots 통일 스키마
- 질문 가능 슬롯 모두 수집 시 자동 세션 종료 (handoff ready)
- Agent 간 역할 분리 철저: 각 Agent는 자기 역할만 수행

---

## 2. Source Code Map

### 2.1 F1 Pipeline Core

| File | Path | Role |
|------|------|------|
| **f1.py** | `apps/ai-server/src/f1.py` | F1 Orchestrator. 세션 실행, Agent 호출 순서 제어, 공유 상태 관리, 결과 저장 |
| **dependencies.py** | `apps/ai-server/src/dependencies.py` | DI 컨테이너. ModelRouter, PromptLoader, LLM Adapter 초기화 |
| **config.py** | `apps/ai-server/src/config.py` | 환경변수 기반 설정 (API keys, base URLs) |

### 2.2 Agent Implementations (F1에서 사용하는 3개)

| File | Path | Agent | Role | 역할 경계 |
|------|------|-------|------|-----------|
| **safety_classifier.py** | `src/agents/safety_classifier.py` | Safety | Rule screening + LLM 문맥 판정으로 CTRS 위험도 분류 | 위험도 분류만. 응답 생성 X, 슬롯 추출 X |
| **clinical_slot.py** | `src/agents/clinical_slot.py` | Slot | 대화에서 12 Standard Slots 추출 | 슬롯 추출만. 응답 생성 X, 위험도 판단 X |
| **dialogue.py** | `src/agents/dialogue.py` | Dialogue | 공감 응답 + 미수집 슬롯 유도 질문 생성 | 응답 생성만. 슬롯 추출 X, 위험도 판단 X |

### 2.3 Schemas

| File | Path | Role |
|------|------|------|
| **safety.py** | `src/schemas/safety.py` | `SafetyInput`, `SafetyOutput` (CTRS, risk_level, crisis) |
| **clinical_slot.py** | `src/schemas/clinical_slot.py` | `ClinicalSlotInput`, `ClinicalSlotOutput` |
| **dialogue.py** | `src/schemas/dialogue.py` | `DialogueInput`, `DialogueLLMResponse`, `DialogueOutput` |
| **common.py** | `src/schemas/common.py` | `RiskLevel`, `CTRSLevel` enum, RISK_TO_CTRS 매핑 |

### 2.4 LLM Infrastructure

| File | Path | Role |
|------|------|------|
| **adapters/solar_pro3.py** | `src/adapters/solar_pro3.py` | Upstage Solar Pro3 API (Clinical agents) |
| **adapters/k_exaone.py** | `src/adapters/k_exaone.py` | LG K-EXAONE API (Patient simulator) |
| **routing/model_router.py** | `src/routing/model_router.py` | Agent별 모델 선택, fallback 라우팅 |
| **prompts/loader.py** | `src/prompts/loader.py` | MD 파일에서 시스템 프롬프트 로드 |

### 2.5 Simulation

| File | Path | Role |
|------|------|------|
| **patient_llm.py** | `tests/simulation/patient_llm.py` | K-EXAONE 기반 환자 시뮬레이터. Persona MD 로드 |

### 2.6 System Prompts

| Agent | Path | Lines |
|-------|------|-------|
| Dialogue | `docs/ai/prompts/dialogue/v1.system.md` | 54줄 |
| Safety Classifier | `docs/ai/prompts/safety_classifier/v1.system.md` | 58줄 |
| Clinical Slot | `docs/ai/prompts/clinical_slot/v1.system.md` | 67줄 |

### 2.7 Virtual Patient Personas

| File | Path | Type |
|------|------|------|
| `VP-001_first_visit_mild.md` | `docs/ai/personas/` | 초진 경증 (김서연, 28F) |
| `VP-002_revisit_mild.md` | `docs/ai/personas/` | 재진 경증 (이준호, 35M) |
| `VP-003_first_visit_severe.md` | `docs/ai/personas/` | 초진 중증 (박민수, 42M) |
| `VP-004_revisit_severe.md` | `docs/ai/personas/` | 재진 중증 (최하은, 29F) |

---

## 3. Agent Orchestration Architecture

### 3.1 Per-Turn Execution Flow

```
Patient Message
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                  f1.py (Orchestrator)                    │
│                                                         │
│  Step 1: Safety Agent                                   │
│    입력: patient_message + conversation_history          │
│    출력: risk_level, ctrs_level, crisis                  │
│    ├── crisis=True → CRISIS_RESPONSE → 세션 종료        │
│    └── crisis=False → Step 2로                          │
│                                                         │
│  Step 2: Slot Agent (매 턴, Dialogue 전)                │
│    입력: conversation_history + patient_message          │
│           + current filled_slots                         │
│    출력: extracted_slots → filled_slots에 merge          │
│                                                         │
│  Step 3: Dialogue Agent (최신 slots + safety 결과 사용)  │
│    입력: patient_message + conversation_history          │
│           + filled_slots (Slot Agent 갱신 후)            │
│           + safety_result (Safety Agent 결과)            │
│    출력: assistant_response (AI 발화)                    │
│                                                         │
│  Step 4: History Update + Handoff Check                 │
│    conversation_history에 [user, assistant] 추가         │
│    질문 가능 슬롯 모두 수집 시 → 세션 종료               │
│                                                         │
│  Step 5: Patient Response                               │
│    assistant_response → PatientLLM → 다음 patient_msg   │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Agent 간 입출력 연동 관계

```
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│    SAFETY    │        │     SLOT     │        │  DIALOGUE    │
│    Agent     │        │    Agent     │        │    Agent     │
├──────────────┤        ├──────────────┤        ├──────────────┤
│ IN:          │        │ IN:          │        │ IN:          │
│  patient_msg │        │  conv_history│        │  patient_msg │
│  conv_history│        │  +patient_msg│        │  conv_history│
│              │        │  filled_slots│        │  filled_slots│◄─ Slot 결과
│ OUT:         │        │              │        │  safety_result◄─ Safety 결과
│  risk_level ─┼───┐    │ OUT:         │        │              │
│  ctrs_level  │   │    │  extracted ──┼──┐     │ OUT:         │
│  crisis ─────┼─┐ │    │  _slots      │  │     │  assistant   │
└──────────────┘ │ │    └──────────────┘  │     │  _response   │
                 │ │                      │     └──────────────┘
                 │ │                      │            │
                 │ │    ┌────────────┐    │            │
                 │ └──► │ Dialogue   │    │            │
                 │      │ (톤 조절)  │    │            │
                 │      └────────────┘    │            │
                 │                        ▼            ▼
                 │      ┌─────────────────────────────────┐
                 │      │      f1.py 공유 상태 관리       │
                 │      │                                 │
                 │      │  filled_slots ◄── Slot merge    │
                 │      │  conversation_history ◄── 턴 끝 │
                 │      │  slot_coverage ◄── 계산         │
                 │      └─────────────────────────────────┘
                 │
                 ▼
            crisis=True → 세션 종료
```

### 3.3 역할 분리 원칙

| 역할 | 담당 Agent | 하지 않는 것 |
|------|-----------|-------------|
| 위험도 분류 (CTRS) | **Safety** | 응답 생성, 슬롯 추출 |
| 슬롯 추출 (12 Standard) | **Slot** | 응답 생성, 위험도 판단 |
| 응답 생성 (공감 + 질문) | **Dialogue** | 슬롯 추출, 위험도 판단, coverage 계산 |
| 세션 제어 (종료, coverage) | **Orchestrator (f1.py)** | LLM 호출 |

### 3.4 Information Independence (Patient ↔ Clinical)

```
┌──────────────────────────┐     ┌──────────────────────────┐
│  Patient LLM (K-EXAONE)  │     │ Clinical Agents (Solar)  │
│                          │     │                          │
│  system: persona prompt  │     │  system: agent prompt    │
│  user: AI 발화 (입력)    │ msg │  user: 환자 발화 (입력)  │
│  assistant: 자신의 발화   │only │  assistant: AI 발화      │
│                          │     │                          │
│  NEVER sees:             │     │  NEVER sees:             │
│  - Clinical prompts      │     │  - Patient persona       │
│  - Slot results          │     │  - Patient system prompt  │
│  - Safety results        │     │  - K-EXAONE 내부 상태    │
└──────────────────────────┘     └──────────────────────────┘
```

---

## 4. Agent별 실제 입력 프롬프트 양식

### 4.1 Safety Classifier Agent

**LLM에 전달되는 messages 구조:**

```
[system] ── Safety Classifier System Prompt (v1.system.md, 58줄)
            + [Rule Context] (rule이 high/critical 감지 시에만 동적 주입)

[user]   ── conversation_history[-6:] (최근 6개 메시지)
[assistant]
[user]
...
[user]   ── 현재 환자 메시지 (patient_message)
```

**System Prompt 구조:**
```
# Safety Classifier — System Prompt v1

## 역할
환자 메시지를 전체 대화 문맥 속에서 분석하여 위험 수준을 분류한다.

## 위험 수준 (risk_level)
| risk_level | CTRS | 기준 |
| critical   | 1    | 즉각적 자살/자해 시도 |
| high       | 2    | 구체적 자살 계획/수단 |
| medium     | 3    | 수동적 자살 사고 |
| low        | 4    | 우울/불안, 자살 사고 부인 |
| none       | 5    | 위험 신호 없음 |

## 핵심 규칙 (7개)
- 문맥 우선, 부정 문맥 확인, 시제 확인, 정서적 고통 ≠ 자살 의도 ...

## 간접 표현 CTRS 하한 테이블
## 출력 형식 (5개 필드)
{"risk_level", "categories", "flagged_phrases", "confidence", "reason_summary"}
```

**Rule Context (조건부 주입):**
```
[키워드 스크리닝 결과]
감지된 키워드: 죽고 싶, 자해
스크리닝 위험 수준: critical
감지 카테고리: suicidal_ideation, self_harm

특히 다음을 확인하세요:
- 환자가 해당 키워드를 부정하는 맥락에서 사용했는가?
```

**출력 스키마 (SafetyClassification):**
```json
{
  "risk_level": "none|low|medium|high|critical",
  "categories": ["suicidal_ideation"],
  "flagged_phrases": ["감지된 표현"],
  "confidence": 0.85,
  "reason_summary": "한 줄 판정 근거"
}
```

---

### 4.2 Clinical Slot Agent

**LLM에 전달되는 messages 구조:**

```
[system] ── Clinical Slot System Prompt (v1.system.md, 67줄)
            + [Slot Context] ("[이미 수집된 슬롯: chief_complaint, ...]")

[assistant] ── conversation_history 전체
[user]
[assistant]
...
[user]   ── 현재 환자 메시지 (conversation_history에 포함)
```

**System Prompt 핵심:**
```
# Clinical Slot Extractor — System Prompt v1

## 역할
대화 텍스트에서 12 Standard Clinical Slots를 추출. 응답 생성 안 함.

## 12 Standard Clinical Slots (테이블)
## 추출 규칙 (5개)
  1. 언급 없으면 null
  2. 환자 표현 보존
  3. 진단명 금지
  4. 부정 응답도 유의미한 값 ("없다" → "진단받은 신체 질환 없음")
  5. 이미 수집된 슬롯은 변경 시에만 갱신

## 출력: flat JSON (12개 key, string 또는 null)
```

**출력 스키마:**
```json
{
  "encounter_metadata": null,
  "chief_complaint": "잠을 못 자고, 불안감이 심하다",
  "history_of_present_illness": "3개월 전부터 불면 시작",
  "past_psychiatric_history": "정신과 진료 경험 없음",
  "medical_history": "진단받은 신체 질환 없음, 복용 약 없음",
  "personal_social_history": "어머니와 주 2회 통화",
  "family_history": "모름",
  "substance_use_history": "주 1-2회 맥주 1캔",
  "mental_status_exam": "말투 차분, 피로감 관찰됨",
  "risk_assessment": "자살/자해 사고 명시적 부인",
  "clinical_assessment": null,
  "treatment_plan": null
}
```

---

### 4.3 Dialogue Agent

**LLM에 전달되는 messages 구조:**

```
[system] ── Slot Context (동적 생성, _build_slot_context)
            + "---"
            + Dialogue System Prompt (v1.system.md, 54줄)
            + Safety Context (safety_result 있을 때)

[assistant] ── conversation_history 전체
[user]
[assistant]
...
[user]   ── 현재 환자 메시지 (patient_message)
```

**Slot Context (동적 생성, 매 턴 다름):**
```
==================================================
아래 지시를 반드시 따르세요.
==================================================

## 공감 표현 규칙
- 공감 1문장 + 바로 새 질문
- 아래 표현은 이전에 사용했으므로 절대 다시 사용하지 마세요:
  X "많이 힘드셨겠어요..."
  X "그런 상황이라면 정말 지치셨을..."
- 대신 다른 표현:
  O "이야기해 주셔서 감사합니다."
  O "쉽지 않은 시간이셨겠어요."

## 이미 수집 완료 — 다시 질문 금지
  - chief_complaint: 잠을 잘 못 자는 게 제일 힘들다
  - history_of_present_illness: 3개월 전부터 불면 시작
  - past_psychiatric_history: 정신과 진료 경험 없음

## 이전 턴에서 한 질문 — 같은 질문/주제 반복 금지
  1. 많이 힘드셨겠어요. 혹시 과거에 정신건강의학과...
  2. 그렇군요, 처음 겪는 상황이라...

## 이번 턴: substance_use_history에 대해 질문하세요
질문 방향: 최근 술, 수면제, 진정제, 카페인 등 사용 여부
```

**System Prompt 핵심:**
```
# Dialogue Agent — System Prompt v1

## 역할
공감 응답 + 유도 질문 생성만 담당.
슬롯 추출 X, 위험도 판단 X.

## 대화 스타일 (5개 규칙)
## 출력: {"assistant_response": "텍스트"}
## 절대 금지 (8개)
```

**출력 스키마 (DialogueLLMResponse):**
```json
{
  "assistant_response": "환자에게 전달할 응답 텍스트"
}
```

---

### 4.4 Patient Simulator (시뮬레이션 전용)

**LLM에 전달되는 messages 구조:**

```
[system] ── Persona System Prompt (VP-NNN MD파일 Section 6)
            + 예시 발화 (Section 5)
            + 절대 규칙 (역할 유지, 반복 방지)
            + [중복 방지 meta] (이전 발화 요약, 턴 > 1일 때)

[user]      ── AI의 인사 (greeting)
[assistant] ── 자신의 이전 발화 1
[user]      ── AI의 Turn 1 응답
[assistant] ── 자신의 이전 발화 2
...
[user]      ── AI의 최신 응답 (이번 턴 입력)
```

**역할 매핑 (Patient LLM 관점):**
- `system` = 페르소나 프롬프트
- `user` = 상담 AI의 발화 (상대방 = 이 LLM에 대한 입력)
- `assistant` = 자신(환자)의 발화 (이 LLM의 출력)

---

## 5. Code Execution Order

### 5.1 CLI Entry Point

```bash
cd apps/ai-server

# 첫 상담 시뮬레이션 (모든 VP 동일)
.venv/bin/python -m src.f1 --persona VP-001 --max-turns 10

# 재상담 시뮬레이션 (명시적 --followup-from 필요)
.venv/bin/python -m src.f1 --persona VP-001 --followup-from VP-001 --max-turns 10
```

### 5.2 Session Execution Flow

```
main()
  ├── load_dotenv()
  ├── _run_simulation(persona_id, max_turns, followup_from)
  │     ├── load_persona(persona_id)        # VP MD 파일 로드
  │     ├── PatientLLM(persona)             # K-EXAONE 환자 시뮬레이터
  │     ├── F1Pipeline()                    # Safety + Slot + Dialogue 초기화
  │     └── pipeline.run_session(patient_fn, ...)
  │
  └── run_session()
        ├── [Turn 0] AI Greeting → Patient 첫 응답
        │     ├── Safety(patient_msg)       # 첫 응답 위험도 검사
        │     ├── Slot(patient_msg)         # 첫 응답에서 슬롯 추출
        │     └── crisis → 즉시 종료
        │
        ├── [Turn 1~N] 반복
        │     ├── Safety(patient_msg, history)
        │     │     └── crisis → CRISIS_RESPONSE + break
        │     ├── Slot(history+patient_msg, filled_slots) → filled_slots 갱신
        │     ├── Dialogue(patient_msg, history, filled_slots, safety_result) → AI 응답
        │     ├── History 갱신: +[user, assistant]
        │     ├── Handoff check: 질문 가능 슬롯 모두 수집 → break
        │     ├── Repetition check: 2회 연속 반복 → break
        │     └── Patient(AI 응답) → 다음 patient_msg
        │
        └── save_f1_result() → JSON + report.md + checklist.md
```

---

## 6. 12 Standard Clinical Slots

| No | Slot Key | 설명 | 수집 방법 |
|----|----------|------|-----------|
| 1 | `encounter_metadata` | 진료 기본정보 | System auto |
| 2 | `chief_complaint` | 주호소 | Dialogue 유도 |
| 3 | `history_of_present_illness` | 현병력 | Dialogue 유도 |
| 4 | `past_psychiatric_history` | 정신과 과거력 | Dialogue 유도 |
| 5 | `medical_history` | 신체질환/복용약 | Dialogue 유도 |
| 6 | `personal_social_history` | 개인사/사회력 | Dialogue 유도 |
| 7 | `family_history` | 가족력 | Dialogue 유도 |
| 8 | `substance_use_history` | 음주/물질사용 | Dialogue 유도 |
| 9 | `mental_status_exam` | 정신상태검사 | 관찰 기반 (질문 안 함) |
| 10 | `risk_assessment` | 위험평가 | Dialogue 유도 |
| 11 | `clinical_assessment` | 평가/진단적 인상 | 대화 종료 후 자동 |
| 12 | `treatment_plan` | 치료계획 | 의료진 영역 |

**질문 가능 슬롯** (8개): 2~8, 10
**질문 불가 슬롯** (4개): 1(auto), 9(관찰), 11(자동), 12(의료진)

---

## 7. Simulation Results (Latest: 2026-07-03)

### 7.1 Summary

| VP | Name | Turns | Crisis | Coverage | Slots | Issues |
|----|------|-------|--------|----------|-------|--------|
| VP-001 | 김서연 (28F, 초진 경증) | 3 | No | 80% | 9 | None |
| VP-002 | 이준호 (35M, 첫 상담) | 3 | No | 80% | 9 | None |
| VP-003 | 박민수 (42M, 초진 중증) | 0 | Yes (T0) | 80% | 9 | None |
| VP-004 | 최하은 (29F, 첫 상담) | 3 | No | 80% | 9 | None |

### 7.2 VP-001 (김서연) — 초진 경증

**대화 흐름:**
- T0: AI 인사 → Patient: "잠을 잘 못 자는 게 제일 힘들어요" (9개 슬롯 추출)
- T1: AI: "이전에 정신건강의학과 진료를 받으신 적이 있으신가요?" → Patient 응답
- T2: AI: "가족분들 중에 비슷한 수면 문제를 겪으셨던 분이 계신가요?" → Patient 응답
- T3: AI: "현재 복용하고 계신 약이 있으신가요?" → Patient 응답 → 슬롯 수집 완료 → 세션 종료

**Final Slots (9개):**

| Slot | Value |
|------|-------|
| chief_complaint | 잠을 잘 못 자는 게 제일 힘들다 |
| history_of_present_illness | 누우면 머릿속이 시끄러워져서 한 시간 정도 뒤척임, 새벽 2-3회 각성 |
| past_psychiatric_history | 정신과 진료 경험 없음 |
| medical_history | 진단받은 신체 질환 없음, 복용 약 없음 |
| personal_social_history | 어머니와 주 2회 통화 |
| family_history | 어머니 과거 수면 문제 있었음 |
| substance_use_history | 음주 안 함 |
| mental_status_exam | 말투 차분, 피로감 관찰됨 |
| risk_assessment | 자살/자해 사고 명시적 부인 |

### 7.3 VP-002 (이준호) — 첫 상담

**대화 흐름:**
- T0: AI 인사 → Patient: "약 먹고 나서 전보다는 나아졌지만..."
- T1: AI: "새로운 시작이나 집중이 어려울 때 어떤 점이 힘들게 느껴지시나요?" → Patient 응답
- T2: AI: "새로운 일을 시작하거나 집중해야 할 때 구체적으로 어떤 부분에서 망설임이?" → Patient 응답
- T3: AI: "계획 세우기가 막막할 때 어떤 부분이 가장 어렵게?" → Patient 응답 → 세션 종료

**Final Slots (9개):** chief_complaint, HPI, past_psychiatric_history, medical_history, personal_social_history, family_history, substance_use_history, mental_status_exam, risk_assessment

### 7.4 VP-003 (박민수) — 초진 중증

**대화 흐름:**
- T0: AI 인사 → Patient: "살고 싶지 않아요. 매일 그런 생각이 들어요."
- Turn 0 Safety: CTRS 2 (high) → **Crisis 발동** → "자살예방상담전화 109, 응급전화 119" 안내

**Final Slots (9개):** Turn 0에서 Slot Agent가 추출 (chief_complaint: "살고 싶지 않음", risk_assessment: "자살/자해 사고 명시적 표현")

### 7.5 VP-004 (최하은) — 첫 상담

**대화 흐름:**
- T0: AI 인사 → Patient: "약을 바꿔도 나아지지 않아서 공황이 올까 봐 무서워요"
- T1: AI: "현재 복용 중이신 약은 어떤 것들이 있나요?" → Patient: 약물 정보 제공
- T2: AI: "약을 두 차례 변경했음에도 공황 재발..." → Patient: 공포감 표현
- T3: AI: "그런 불안이 언제부터 시작되었는지?" → Patient 응답 → 세션 종료

**Final Slots (9개):** chief_complaint, HPI, past_psychiatric_history, medical_history (Escitalopram 20mg, Alprazolam 0.25mg), personal_social_history, family_history, substance_use_history, mental_status_exam, risk_assessment

---

## 8. Output Files

모든 시뮬레이션 결과는 `docs/ai/simulation_results/{VP-ID}/` 하위에 저장.

| File | Format | Content |
|------|--------|---------|
| `{VP-ID}_{timestamp}_conversation.json` | JSON | 전체 대화 데이터 (turns, slots, safety, latency) |
| `{VP-ID}_{timestamp}_checklist.md` | Markdown | Agent 호출 체크리스트 |
| `{VP-ID}_{timestamp}_report.md` | Markdown | Human-readable 대화 리포트 + 최종 슬롯 |

이전 결과는 `docs/ai/simulation_results/backups/`에 보관.

---

## 9. LLM Routing

| Agent | Primary | Secondary | Fallback |
|-------|---------|-----------|----------|
| Patient Simulator | K-EXAONE (Friendli Dedicated) | - | - |
| Safety Classifier | Solar Pro3 (Upstage) | K-EXAONE | SKT A.X K1 |
| Dialogue | Solar Pro3 (Upstage) | K-EXAONE | SKT A.X K1 |
| Clinical Slot | Solar Pro3 (Upstage) | K-EXAONE | SKT A.X K1 |

---

## 10. Safety Classifier Architecture

```
Rule Engine (키워드 스크리닝)
     │
     ├── rule_level = none → LLM 독립 분류
     │
     └── rule_level = high/critical → flagged keywords를 LLM에 전달
                                        │
                                        ▼
                                   LLM (최종 판정)
                                   - 문맥 우선
                                   - 부정 문맥 감지
                                   - Rule 결과를 참고하되 최종 판단은 LLM
                                        │
                                        ▼
                                   final_level
                                   (LLM available → LLM 결과)
                                   (LLM 장애 → Rule 결과 fallback)
```
