# Agent 04: Clinical Slot Extraction Agent

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `04` |
| **Agent Name** | `ClinicalSlotAgent` |
| **역할** | 자유 텍스트에서 구조화된 임상 슬롯 추출 |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |

## 목적

대화 내용, STT transcript, OCR 추출 텍스트 등의 비정형 텍스트에서 구조화된 임상 정보를 JSON 형태로 추출한다. 추출된 각 슬롯에는 source, confidence, evidence를 반드시 연결한다.

## 슬롯 스키마 (12 Standard Clinical Slots)

정신과 차팅 표준에 맞춘 12개 슬롯. DialogueAgent, HandoffGenerator와 동일 체계를 사용한다.

| No | 슬롯 | 한국어 차팅 항목 | 필수도 | 포함 내용 |
|-:|---|---|:-:|---|
| 1 | `encounter_metadata` | 진료 기본정보 | E | 진료일시, 진료유형, 초진/재진, 정보제공자, 신뢰도 |
| 2 | `chief_complaint` | 주호소 | E | 환자 표현 원문, 가장 힘든 문제, 내원 이유 |
| 3 | `history_of_present_illness` | 현병력 | E | 발생 시점, 기간, 경과, 악화/완화 요인, 심각도, 기능 영향, 관련 증상 |
| 4 | `past_psychiatric_history` | 정신과 과거력 | E | 과거 진단, 외래/상담/입원, 응급실, 자살시도/자해 과거력, 과거 약물반응 |
| 5 | `medical_history` | 신체질환/신경학적 병력 | E | 주요 내과질환, 신경계 병력, 발작, 두부외상, 만성통증, 알레르기 |
| 6 | `personal_social_history` | 개인사/사회력 | E | 성장·교육·직업·학업, 동거, 가족/대인관계, 경제·법적 스트레스, 지지체계 |
| 7 | `family_history` | 가족력 | O/E | 가족 정신질환, 자살, 물질사용, 주요 가족관계 |
| 8 | `substance_use_history` | 음주·흡연·물질사용 | E | 음주, 흡연, 카페인, 수면제/진정제, 대마, 각성제, 사용량·빈도 |
| 9 | `mental_status_exam` | 정신상태검사 | E | 외모/행동, 말, 기분, 정동, 사고과정, 사고내용, 지각, 인지, 병식, 판단력 |
| 10 | `risk_assessment` | 위험평가 | E | 자살사고, 자해, 타해, 명령환청, 조증성 충동, 중독/금단, 학대/폭력, 보호요인 |
| 11 | `clinical_assessment` | 평가/진단적 인상 | E | 요약, 진단적 인상, 감별진단, 위험 formulation, 기능 수준, 임상적 판단 |
| 12 | `treatment_plan` | 치료계획/치료내용 | E | 약물계획, 상담/심리치료, 검사/의뢰, 안전계획, 교육, 추적진료, 응급 안내 |

**E** = Essential (필수), **O/E** = 초진 시 필수에 가까움

### Essential Slots (Coverage 계산 대상)

| Slot | 우선순위 |
|---|---|
| `chief_complaint` | 1 (최우선) |
| `history_of_present_illness` | 2 |
| `risk_assessment` | 3 |
| `mental_status_exam` | 4 |
| `clinical_assessment` | 5 |

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `source_text` | `string` | 추출 대상 텍스트 |
| `source_type` | `enum` | `dialogue_transcript`, `stt_transcript`, `ocr_document` |
| `existing_slots` | `object \| null` | 이전에 추출된 슬롯 (병합용) |
| `dialogue_turns` | `array<object> \| null` | 대화 턴 이력 (turn 번호 추적용) |

## 출력

```json
{
  "session_id": "sess_20260618_001",
  "extraction_timestamp": "2026-06-18T14:35:00+09:00",
  "slots": {
    "chief_complaint": {
      "value": "2개월간 지속된 우울감과 불면",
      "confidence": 0.88,
      "evidence": [
        { "source": "dialogue_turn_3", "text": "두 달 전부터 계속 우울해요" },
        { "source": "dialogue_turn_5", "text": "잠도 잘 못 자요" }
      ]
    },
    "hpi": {
      "value": "2개월 전 직장 스트레스 시작 후 우울감 발생. 수면 장애 동반. 식욕 감소로 3kg 체중 감소.",
      "confidence": 0.82,
      "evidence": [
        { "source": "dialogue_turn_4", "text": "회사에서 힘든 일이 있은 후부터..." },
        { "source": "dialogue_turn_7", "text": "밥맛도 없고 3키로 빠졌어요" }
      ]
    },
    "medications": [
      {
        "name": "에스시탈로프람",
        "dose": "10mg",
        "frequency": "1일 1회",
        "confidence": 0.95,
        "evidence": [{ "source": "ocr_prescription_001", "text": "Escitalopram 10mg qd" }]
      }
    ],
    "symptoms": {
      "sleep": {
        "value": "입면 곤란, 중간 각성",
        "severity": "moderate",
        "confidence": 0.78,
        "evidence": [{ "source": "dialogue_turn_5", "text": "잠들기가 너무 어렵고 자다가도 깨요" }]
      },
      "appetite": {
        "value": "식욕 감소, 체중 3kg 감소",
        "severity": "moderate",
        "confidence": 0.85,
        "evidence": [{ "source": "dialogue_turn_7", "text": "밥맛도 없고 3키로 빠졌어요" }]
      },
      "mood": {
        "value": "지속적 우울감, 흥미 저하",
        "severity": "moderate-severe",
        "confidence": 0.80,
        "evidence": [{ "source": "dialogue_turn_3", "text": "계속 우울해요, 아무것도 하기 싫어요" }]
      },
      "concentration": { "value": null, "severity": null, "confidence": null, "evidence": [] },
      "energy": { "value": "피로감 호소", "severity": "mild", "confidence": 0.65, "evidence": [{ "source": "dialogue_turn_8", "text": "항상 피곤해요" }] },
      "psychomotor": { "value": null, "severity": null, "confidence": null, "evidence": [] }
    },
    "risk_factors": {
      "value": ["직장 스트레스", "사회적 고립"],
      "confidence": 0.72,
      "evidence": [{ "source": "dialogue_turn_9", "text": "친구들도 안 만나게 됐어요" }]
    },
    "psychosocial_context": {
      "occupation": "회사원",
      "family": "1인 가구",
      "stressors": ["업무 과중", "대인관계 갈등"],
      "support_system": "가족 연락 유지",
      "confidence": 0.70,
      "evidence": [
        { "source": "dialogue_turn_4", "text": "회사에서..." },
        { "source": "dialogue_turn_10", "text": "혼자 살고 있어요. 부모님이랑 전화는 해요" }
      ]
    }
  },
  "missing_slots": ["concentration", "psychomotor", "past_history"],
  "model_used": "upstage-solar-pro-3"
}
```

## Evidence ID 형식

모든 evidence 인용은 `[ev_{source_type}_{3-digit sequence}]` 형식을 사용한다:

| Source Type | Evidence ID 패턴 | 예시 |
|---|---|---|
| 대화 메시지 | `[ev_msg_NNN]` | `[ev_msg_001]`, `[ev_msg_012]` |
| 구조화 척도 | `[ev_scale_NNN]` | `[ev_scale_001]` |
| OCR 문서 블록 | `[ev_ocr_NNN]` | `[ev_ocr_001]` |
| 위험 이벤트 | `[ev_risk_NNN]` | `[ev_risk_001]` |
| 이전 handoff | `[ev_prior_NNN]` | `[ev_prior_001]` |

**주의:** 이전 `msg_NNN` 형식이 아닌 `[ev_msg_NNN]` 형식을 사용한다. 대괄호와 `ev_` 접두사를 반드시 포함한다.

## 핵심 동작

1. **Evidence 필수 연결**: 추출된 모든 슬롯 값에는 출처(source)와 원문 인용(text)을 반드시 포함한다. Evidence ID는 `[ev_{source_type}_{NNN}]` 형식이다.
2. **Confidence 산출**: 각 슬롯의 신뢰도를 0.0-1.0으로 표기한다. 단일 출처 < 복수 출처. 간접 표현 < 직접 표현.
3. **Null 허용**: 확인되지 않은 슬롯은 `null`로 남긴다. 추론하여 채우지 않는다.
4. **슬롯 병합**: 기존 추출 결과(`existing_slots`)가 있으면 병합한다. 동일 슬롯에 새로운 evidence가 추가되면 confidence를 재산출한다.
5. **Source type 구분**: dialogue, STT, OCR 등 출처 유형을 명확히 구분하여 기록한다.
6. **임상 용어 정규화**: 환자 표현을 임상 용어로 매핑하되, 원문도 함께 보존한다 (예: "잠을 못 자요" → 임상: "입면 곤란", 원문 보존).

## 구조화 척도 점수 참조 (Survey Scoring)

구조화 설문(PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C)의 점수 계산은 **rule-based module** (`apps/ai-server/src/scoring/survey_scorer.py`)에서 수행한다. ClinicalSlotAgent는 점수 계산을 수행하지 않으며, 설문 응답 데이터를 slot으로 추출하는 역할만 담당한다.

### PHQ-9 Q9 Safety Flag 규칙

**PHQ-9 문항 9 (자살 사고) >= 1 → Safety 전달 필수**

Survey Scoring module에서 `critical_item_positive: true`가 반환되면, Orchestrator가 SafetyClassifier(02)를 재실행(safety re-evaluation)하여 CTRS level을 재평가한다. PHQ-9 Q9 >= 1은 최소 CTRS 3에 해당한다.

## 안전 제약

1. **AI는 진단하지 않는다.** 슬롯에 진단명을 기입하지 않는다. "우울증"이 아닌 "우울감 호소"로 기록한다.
2. **증상 추론 금지**: 환자가 직접 언급하지 않은 증상을 추론하여 슬롯에 기입하지 않는다.
3. **OCR/STT 신뢰도 전파**: OCR 또는 STT에서 온 정보는 해당 source의 confidence를 상한으로 한다.
4. **구조화 척도 점수는 rule-based**: PHQ-9, GAD-7 등의 점수 계산이 필요한 경우 LLM이 아닌 rule-based 로직으로 수행한다.
5. **PHQ-9 Q9 safety flag**: PHQ-9 문항 9 >= 1 시 반드시 Safety/Risk Triage로 전달한다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| LLM 추출 실패 | Secondary → Fallback LLM 시도 |
| 전체 LLM 실패 | 대화 내역 원문을 handoff에 첨부 (비구조화 상태로 전달) |
| 낮은 confidence 다수 | missing_slots에 포함하고, handoff report에 "추가 확인 필요" 표기 |
| 슬롯 간 모순 감지 | 양쪽 evidence를 모두 기록하고 "불일치" 플래그 부착 |
