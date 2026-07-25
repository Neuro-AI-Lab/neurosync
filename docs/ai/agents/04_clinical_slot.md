# Agent 04: Clinical Slot Extraction Agent

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `04` |
| **Agent Name** | `ClinicalSlotAgent` |
| **역할** | 자유 텍스트에서 구조화된 임상 슬롯 추출 |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |
| **프롬프트 pin** | v3 (`agents/clinical_slot.py:53` `PROMPT_VERSION`) |

## 목적

대화 내용, STT transcript, OCR 추출 텍스트 등의 비정형 텍스트에서 구조화된 임상 정보를 JSON 형태로 추출한다. **실제 구현의 추출 결과는 슬롯 키 → flat 문자열 값(`dict[str, str]`)이며, 슬롯별 source/confidence/evidence 서브필드는 이 에이전트의 출력 스키마(`schemas/clinical_slot.py`)에 존재하지 않는다** — 아래 "출력" 절 참조. Evidence 인용(`[ev_*]`) 조립은 별도 단계(HandoffGenerator(08))의 책임이다.

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

### AI 예상질환 엔티티와의 관계 (별개 필드, 병합 금지)

**"AI 예상질환"(AI-predicted-disease) 엔티티는 이 12개 슬롯에 포함되지 않는다.** F2(`DomainInferenceAgent`, Agent 11)가 산출하는 별도의 비진단·비임상 필드(`AIPredictedDiseaseOutput`, `similarity_score` 라벨링, `is_diagnostic=Literal[False]`)이며, 이 에이전트(04)의 출력이나 `HandoffInput`/`SlotData`의 어떤 typed field에도 병합되지 않는다 — `f2.py`는 이를 기존 F2 출력에 병합하지 않고 sibling key로 배선한다. qa의 9-테스트 adversarial suite(`tests/test_hpi_isolation.py`)가 `AgentInput.extra`/`state.conversation_history` 두 채널을 포함해 이 격리를 확인했다(`REV-013` §3 조건 1 충족, mutation-checked). 이 격리 주장은 정확히 이 9개 테스트가 커버하는 범위로 한정된다. 상세: `docs/ai/agents/11_domain_inference.md` "AI 예상질환 엔티티" 절, `docs/ai/development_report.md` DR-010 §3.

### Essential Slots (Coverage 계산 대상)

| Slot | 우선순위 |
|---|---|
| `chief_complaint` | 1 (최우선) |
| `history_of_present_illness` | 2 |
| `risk_assessment` | 3 |
| `mental_status_exam` | 4 |
| `clinical_assessment` | 5 |

## 입력 (`ClinicalSlotInput`, `schemas/clinical_slot.py`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `conversation_history` | `list[dict[str, str]]` | 전체 대화 `[{role, content}, ...]` |
| `current_slots` | `dict[str, Any]` | 이미 수집된 슬롯 값 (병합/컨텍스트용) |

## 출력 (`ClinicalSlotOutput`, `schemas/clinical_slot.py`)

실제 추출 결과는 **12개 슬롯 키 → flat 문자열 값의 단일 dict**다. 중첩 구조, 슬롯별 `confidence`, 슬롯별 `evidence` 서브필드는 이 스키마에 존재하지 않는다.

```json
{
  "model_used": "solar-pro3",
  "prompt_version": "v3",
  "latency_ms": 0.0,
  "reason_summary": "Extracted 5/12 slots",
  "extracted_slots": {
    "chief_complaint": "<환자 표현 원문 요약 (placeholder)>",
    "history_of_present_illness": "<발생 시점/기간/경과 요약 (placeholder)>",
    "risk_assessment": "<위험평가 관련 서술 (placeholder)>",
    "mental_status_exam": "<정신상태검사 서술 (placeholder)>",
    "clinical_assessment": "<평가/진단적 인상 서술 (placeholder)>"
  },
  "filled_slots": ["chief_complaint", "history_of_present_illness", "risk_assessment", "mental_status_exam", "clinical_assessment"],
  "missing_slots": ["encounter_metadata", "past_psychiatric_history", "medical_history", "personal_social_history", "family_history", "substance_use_history", "treatment_plan"],
  "essential_filled": ["chief_complaint", "history_of_present_illness", "risk_assessment", "mental_status_exam", "clinical_assessment"],
  "essential_missing": [],
  "slot_coverage": 0.42
}
```

값이 없는 슬롯은 `extracted_slots`에 키 자체가 없다(null 값으로 채우지 않는다) — `missing_slots`/`essential_missing` 목록이 결측 여부를 나타낸다.

## Evidence ID 형식 — 이 에이전트에는 미구현

**과거 버전 문서는 이 에이전트가 `[ev_{source_type}_{NNN}]` 형식의 evidence ID를 슬롯마다 부여한다고 기술했으나, `ClinicalSlotAgent`/`ClinicalSlotOutput`에는 해당 필드나 로직이 존재하지 않는다.** `[ev_msg_NNN]` 형식의 evidence citation은 `schemas/common.py`의 `EvidencePacket`을 통해 HandoffGenerator(08) 단계에서 별도로 조립된다. 대화 turn 원문에서 evidence를 재구성해야 하는 downstream 소비자는 이 에이전트가 아니라 HandoffGenerator의 evidence 조립 로직을 참조해야 한다.

## 핵심 동작

1. **Flat 문자열 추출**: 슬롯 값은 문자열 하나로 추출된다. Evidence 인용/citation은 이 에이전트의 출력에 포함되지 않는다(위 "Evidence ID 형식" 절 참조).
2. **미확인 슬롯은 키 자체를 생략**: 값을 확인하지 못한 슬롯은 `extracted_slots`에 키를 넣지 않는다(`null` 값으로 채우지 않음). `missing_slots`가 결측 목록을 별도로 제공한다.
3. **Coverage 산출**: `slot_coverage = len(filled) / 12`. Essential 5개 슬롯에 대해서는 `essential_filled`/`essential_missing`을 별도로 계산한다.
4. **기존 슬롯은 프롬프트 컨텍스트로만 전달**: `current_slots`에 값이 있는 슬롯 이름은 "이미 수집됨" 안내로 LLM 프롬프트에 주입되어, LLM이 변경분에 집중하도록 유도한다 — 이 에이전트 코드 자체가 이전 결과와 이번 결과를 dict 레벨에서 병합하지는 않는다.
5. **Key alias 매핑**: LLM이 표준 키가 아닌 변형 키(`substance_use`, `psychosocial_context`, `risk_factors`, `protective_factors`)로 응답하면 표준 12-key 중 하나로 매핑한다(`agents/clinical_slot.py:169-174`).

## 구조화 척도 점수 참조 (Survey Scoring)

구조화 설문(PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C)의 점수 계산은 **rule-based module** (`apps/ai-server/src/scoring/survey_scorer.py`)에서 수행한다. ClinicalSlotAgent는 점수 계산을 수행하지 않으며, 설문 응답 데이터를 slot으로 추출하는 역할만 담당한다.

### PHQ-9 Q9 Safety Flag 규칙

**PHQ-9 문항 9 (자살 사고) >= 1 → Safety 전달 필수**

Survey Scoring module에서 `critical_item_positive: true`가 반환되면, Orchestrator가 SafetyClassifier(02)를 재실행(safety re-evaluation)하여 CTRS level을 재평가한다. PHQ-9 Q9 >= 1은 최소 CTRS 3에 해당한다.

## 안전 제약

1. **AI는 진단하지 않는다.** 슬롯에 진단명을 기입하지 않는다. "우울증"이 아닌 "우울감 호소"로 기록한다.
2. **증상 추론 금지**: 환자가 직접 언급하지 않은 증상을 추론하여 슬롯에 기입하지 않는다.
3. **OCR/STT 신뢰도 전파 — 미구현**: `ClinicalSlotOutput`에는 confidence 필드 자체가 없어 source별 confidence 상한 로직은 이 에이전트에 구현되어 있지 않다(설계 의도로 문서에 남겨두되, 코드 반영 여부는 별도 확인 필요).
4. **구조화 척도 점수는 rule-based**: PHQ-9, GAD-7 등의 점수 계산이 필요한 경우 LLM이 아닌 rule-based 로직으로 수행한다.
5. **PHQ-9 Q9 safety flag**: PHQ-9 문항 9 >= 1 시 반드시 Safety/Risk Triage로 전달한다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| LLM 호출 실패 | `model_used="none"`, `missing_slots`=전체 12개, `essential_missing`=essential 5개로 반환 (재시도/fallback 로직은 이 에이전트 코드에는 없음) |
| LLM JSON 파싱 실패 | 빈 `dict`로 처리 → 사실상 모든 슬롯이 missing으로 반환 |
| LLM 응답 값 타입 불일치(문자열/`{value:...}` 외) | 해당 슬롯을 건너뛰고 로그만 남김(`agents/clinical_slot.py:162-166`) |
