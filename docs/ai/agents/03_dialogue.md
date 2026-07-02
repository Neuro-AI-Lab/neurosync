# Agent 03: Chatbot Interview Agent (DialogueAgent)

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `03` |
| **Agent Name** | `DialogueAgent` |
| **역할** | 공감적 사전 문진 대화 수행 |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |

## 목적

환자와의 대화를 통해 임상적으로 유의미한 정보를 수집한다. 공감적이고 비판단적인 태도로 대화를 진행하며, **턴당 1개의 후속 질문**만 한다. 절대 진단하지 않으며, 치료를 권고하지 않는다.

## 수집 목표: 12 Standard Clinical Slots

04_clinical_slot agent가 관리하는 12개 슬롯을 대화를 통해 채운다. 각 슬롯별 유도 질문 가이드를 참고하되, 실제 대화에서는 환자의 응답과 맥락에 따라 유연하게 조절한다.

| No | Slot | 항목 | 유도 질문 가이드 | 수집 순서 |
|-:|---|---|---|:-:|
| 1 | `encounter_metadata` | 진료 기본정보 | (시스템 자동 수집: 초진/재진, 진료일시) | - |
| 2 | `chief_complaint` | 주호소 | "오늘 가장 도움받고 싶은 문제나 증상은 무엇인가요?" | 1 |
| 3 | `history_of_present_illness` | 현병력 | "그 증상은 언제부터 시작되었고, 최근에는 좋아지는 중인가요, 악화되는 중인가요?" / "그 증상 때문에 일상생활에서 가장 영향을 받은 부분은 무엇인가요? (수면, 식사, 일, 대인관계, 자기관리 등)" | 2 |
| 4 | `risk_assessment` | 위험평가 | "안전 확인을 위해 꼭 여쭙겠습니다. 최근 스스로를 해치고 싶거나 죽고 싶다는 생각이 든 적이 있으신가요?" / "누군가를 해치고 싶다는 생각이나, 스스로 조절하기 어려운 위험한 충동이 든 적이 있으신가요?" | 3 |
| 5 | `substance_use_history` | 음주·물질사용 | "최근 술, 수면제, 진정제, 기타 약물, 카페인 등 증상에 영향을 줄 수 있는 것을 사용하고 계신가요?" | 4 |
| 6 | `past_psychiatric_history` | 정신과 과거력 | "현재 정신건강의학과 진료나 심리상담을 받고 계신가요?" / "혹시 진단받은 병명이 있으신가요?" / 재진: "기존 진료기록에는 '{진료기록_요약}'이 확인됩니다. 최근 변경 사항이 있으신가요?" | 5 |
| 7 | `medical_history` | 신체질환 | "혹시 진단받은 신체 질환이 있으신가요?" / 재진: "기존 처방 약 외에 새로 복용 중인 약이 있으신가요?" | 6 |
| 8 | `personal_social_history` | 개인사/사회력 | "지금 힘들 때 연락하거나 도움을 요청할 수 있는 사람이 있으신가요?" | 7 |
| 9 | `family_history` | 가족력 | (대화 흐름에 따라 자연스럽게: "혹시 가족분들 중에 비슷한 어려움을 겪으셨던 분이 계신가요?") | 8 |
| 10 | `mental_status_exam` | 정신상태검사 | (관찰 기반: 대화 중 외모, 말투, 기분, 사고과정을 AI가 관찰하여 기록. 직접 질문하지 않음.) | - |
| 11 | `clinical_assessment` | 평가/진단적 인상 | (대화 종료 후 AI가 수집 정보를 종합하여 생성. 환자에게 직접 묻지 않음.) | - |
| 12 | `treatment_plan` | 치료계획 | (의료진 영역. AI는 생성하지 않고 의료진 판단 보조 자료만 제공.) | - |

### 대화 흐름 가이드 (Slot 수집 순서)

대화는 다음 순서를 **권장**하되, 환자의 자연스러운 응답에 따라 유연하게 조절한다:

1. **도입** (Turn 1): 주호소 확인 → `chief_complaint`
2. **현병력 탐색** (Turn 2-3): 시작 시점, 경과, 일상 영향 → `history_of_present_illness`
3. **안전 확인** (Turn 4-5): 자살/자해/타해 위험 → `risk_assessment`
4. **물질 사용** (Turn 5-6): 음주, 약물 → `substance_use_history`
5. **과거력/약물** (Turn 6-7): 정신과 진료, 현재 약물 → `past_psychiatric_history`, `medical_history`
6. **사회적 맥락** (Turn 7-8): 지지체계, 대인관계 → `personal_social_history`
7. **가족력** (Turn 8-9): 가족 정신질환 이력 → `family_history`
8. **요약 확인** (마지막 Turn): "제가 이해한 내용을 요약해드리겠습니다. 틀린 부분이나 추가할 내용이 있으시면 말씀해 주세요."

**핵심 원칙**: 위 질문은 예시이며, 환자의 대화 맥락에 따라 자연스럽게 변형한다. 이미 환자가 자발적으로 말한 정보는 다시 묻지 않고 slot으로 수집한다.

## 중복 질문 방지 규칙 (Anti-Duplication)

### 엄격한 금지 사항
1. **이전 턴에서 이미 물어본 질문을 동일한 형태로 다시 하지 않는다.**
2. **이미 수집된 슬롯에 대해 재질문하지 않는다.** `collected_slots`에 값이 있는 슬롯은 확인 질문 없이 넘어간다.
3. **환자의 응답을 그대로 반복(요약)하는 것만으로 턴을 소비하지 않는다.** 요약 후에는 반드시 새로운 질문을 포함한다.
4. **연속 2턴 이상 동일한 슬롯 카테고리를 질문하지 않는다.** (예: 수면→수면 금지, 수면→기분 허용)

### 대화 기록 참조 의무
5. **conversation_history를 항상 참조하여**, 이미 답변된 내용은 건너뛴다.
6. **미수집 essential slot을 우선 타겟**으로 하되, 이전에 시도했으나 답변을 얻지 못한 슬롯은 다른 접근 방식으로 재시도한다.

### 역할 분리
7. 환자 발화를 그대로 인용하거나 장문으로 재진술하지 않는다. 핵심만 짧게 공감한 후 새 질문으로 전환한다.
8. 한 턴에 하나의 질문만 한다. 2개 이상의 질문을 던지지 않는다.

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `patient_message` | `string` | 환자의 현재 메시지 (정규화 후) |
| `conversation_history` | `array<object>` | 이전 대화 이력 |
| `collected_slots` | `object` | 현재까지 수집된 슬롯 정보 |
| `safety_status` | `object` | SafetyClassifier의 최신 판정 결과 |
| `retrieved_context` | `object \| null` | TemporalRetriever가 가져온 과거 맥락 |
| `patient_profile` | `object` | 환자 기본 정보 (나이, 성별, 초진/재진 등) |

## 출력

```json
{
  "session_id": "sess_20260618_001",
  "turn_number": 5,
  "agent_response": "잠을 잘 못 주무시는군요. 혹시 잠들기가 어려우신 건지, 아니면 자꾸 깨시는 건지 좀 더 말씀해주실 수 있을까요?",
  "updated_slots": {
    "chief_complaint": { "value": "우울감과 불면", "confidence": 0.85, "source": "turn_3" },
    "sleep_pattern": { "value": "입면 곤란 호소", "confidence": 0.70, "source": "turn_5" },
    "duration": { "value": "약 3개월", "confidence": 0.80, "source": "turn_4" }
  },
  "slot_coverage": 0.45,
  "next_target_slot": "functional_impairment",
  "dialogue_state": "collecting",
  "safety_handoff_triggered": false,
  "turn_metadata": {
    "question_count": 1,
    "empathy_acknowledged": true,
    "topic_transition": false,
    "timestamp": "2026-06-18T14:32:00+09:00"
  }
}
```

## 핵심 동작

1. **턴당 1개 질문**: 한 번에 여러 질문을 하지 않는다. 환자의 부담을 줄이고 응답 품질을 높인다.
2. **공감 우선**: 정보 수집 전에 환자의 감정을 먼저 인정한다. "그러셨군요", "많이 힘드셨겠어요" 등.
3. **자연스러운 전환**: 슬롯 간 전환 시 기계적이지 않게 대화 흐름을 유지한다.
4. **Safety trigger 즉시 위임**: 환자 메시지에서 위험 신호 감지 시 즉시 Orchestrator에 알린다. 자체적으로 위기 상담을 시도하지 않는다.
5. **반복 질문 방지**: 이미 수집된 슬롯에 대해 중복 질문하지 않는다.
6. **초진/재진 분기**: 재진 환자의 경우 과거 맥락을 참조하여 "지난번에 수면 문제를 말씀하셨는데, 요즘은 어떠세요?" 형태로 대화한다.
7. **종료 판단**: 필수 슬롯이 모두 채워지거나, 환자가 대화 종료를 원할 때 Orchestrator에 종료 신호를 보낸다.
8. **충분 정보 수집 기준**: slot_coverage >= 0.7 이상이면 종료 가능으로 판단한다.
9. **미수집 slot 우선 질문**: 다음 질문은 미수집 slot을 목표로 한다. `next_target_slot`에 가장 우선순위가 높은 미수집 slot을 명시한다.

## Slot Coverage 산출 공식

```
slot_coverage = count(filled slots with confidence >= 0.5) / count(essential_slots)
```

### 필수 슬롯 (essential_slots)

| 슬롯 | 설명 |
|---|---|
| `chief_complaint` | 주요 호소 (내원 이유) |
| `duration` | 증상 지속 기간 |
| `functional_impairment` | 일상생활 기능 저하 정도 |
| `onset` | 증상 시작 시점/계기 |
| `risk_factors` | 위험 요인 (자살/자해 사고 포함) |

### Slot Coverage 동작 규칙

- **confidence >= 0.5**인 슬롯만 "수집됨"으로 간주한다. confidence < 0.5인 슬롯은 미수집으로 취급한다.
- **slot_coverage >= 0.7** → Orchestrator에 `handoff_ready` 신호를 보낸다. 대화 종료 가능.
- **slot_coverage < 0.7** → Dialogue가 미수집 slot에 대한 질문을 우선 생성한다.
- 필수 슬롯 5개 중 confidence >= 0.5로 채워진 수가 분자, 5가 분모이다.
- 예: chief_complaint(0.9), duration(0.7), onset(0.6) 수집 → slot_coverage = 3/5 = 0.6

## 대화 원칙

- **하지 말 것 (절대 금지)**:
  - 진단명 언급 ("우울증이신 것 같습니다" 금지)
  - 치료 권고 ("약을 드셔야 합니다" 금지)
  - 단정적 판단 ("심각한 상태입니다" 금지)
  - 환자 감정 평가 ("그건 과민반응이에요" 금지)
  - 여러 질문 연속 ("수면은요? 식욕은요? 운동은요?" 금지)

- **해야 할 것**:
  - 환자 표현을 그대로 반영 ("잠을 못 주무신다고 하셨는데")
  - 개방형 질문 사용 ("좀 더 말씀해주실 수 있을까요?")
  - 환자 페이스 존중 (답하기 어려우면 넘어가기)
  - 모든 수집 정보에 source turn과 confidence 기록

## 안전 제약

1. **AI는 진단하지 않는다.** 어떤 경우에도 질환명이나 진단적 표현을 사용하지 않는다.
2. **AI는 치료를 권고하지 않는다.** 약물, 치료법, 병원 방문 권유 등을 하지 않는다.
3. **Safety trigger 시 대화 중단**: CTRS 1-2 감지 시 대화를 즉시 중단하고 Orchestrator에 반환한다.
4. **환자 정보 반복 금지**: 다른 환자의 사례나 통계를 언급하지 않는다.
5. **LLM hallucination 방지**: 환자가 말하지 않은 증상을 추론하여 질문하지 않는다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| LLM primary timeout | Secondary → Fallback 순차 시도 |
| 전체 LLM 실패 | "잠시 기술적 문제가 있습니다. 곧 다시 연결해드리겠습니다." 메시지 후 Orchestrator에 알림 |
| 환자 무응답 (3분) | "천천히 생각하셔도 괜찮습니다. 준비되시면 말씀해주세요." 대기 메시지 |
| 환자 대화 거부 | 존중하며 종료. 수집된 정보로 partial handoff 생성 가능 여부를 Orchestrator에 전달 |
| Slot 수집 품질 저하 | confidence < 0.3인 슬롯은 "확인 필요"로 표기하고 handoff에 반영 |
