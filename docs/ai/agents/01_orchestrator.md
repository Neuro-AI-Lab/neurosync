# Agent 01: Orchestrator Agent

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `01` |
| **Agent Name** | `OrchestratorAgent` |
| **역할** | Task 1 전체 워크플로우 제어 및 에이전트 간 라우팅 |
| **LLM Routing** | fixed / rule-based — **이 에이전트 자체는 LLM을 호출하지 않는다.** 모든 라우팅 결정은 rule-based 상태 머신이다(`agents/orchestrator.py:1-9`). "LLM Routing" 표기는 하위 에이전트 호출 시 그 에이전트들의 라우팅 정책을 가리키는 것이지 Orchestrator 자신의 것이 아니다 |

## 목적

사전 문진(Task 1) 파이프라인의 전체 상태 머신을 관리한다. 환자 입력부터 handoff report 생성까지의 흐름을 제어하고, 각 에이전트의 호출 순서와 결과를 조율한다. **CTRS 1-2 감지 시 즉시 crisis flow를 발동**하며, 모든 다른 단계를 중단한다.

## 상태 머신

### 상태 전이 다이어그램

```
input_received → safety_gate → context_retrieval → dialogue_loop → slot_extraction → handoff_generation → evidence_verification → handoff_delivery
                    │                                    │
                    └─ CTRS 1-2 → crisis_flow (즉시)     └─ slot_coverage < 0.7 → dialogue_loop (반복)
```

### 11개 상태 정의

`schemas/orchestrator.py:14-27` (`SessionStage` enum) 기준. 파이프라인 흐름을 구성하는 8개 상태에 더해, 상태 머신의 종결/분기를 명시적으로 표현하는 3개 상태(`crisis_flow`, `completed`, `error`)가 별도 enum 값으로 존재한다.

| 상태 | 설명 | 다음 상태 | 실패 시 |
|---|---|---|---|
| `input_received` | 입력 수신 및 정규화. STT/OCR 입력 시 InputNormalizer(05) 호출 | `safety_gate` | 입력 validation 실패 → HTTP 422 |
| `safety_gate` | SafetyClassifier(02) 실행. **모든 입력에 대해 필수 실행** | CTRS 1-2 → `crisis_flow`, CTRS 3-5 → `context_retrieval` | timeout → CTRS 2 간주, crisis_flow 발동 |
| `context_retrieval` | TemporalRetriever(08) 호출 + unified_context 조립. Safety와 **병렬 실행 가능** | `dialogue_loop` | retriever 실패 → 현재 세션 정보만으로 진행 |
| `dialogue_loop` | Dialogue(03) 호출. 턴 반복. slot_coverage 모니터링 | slot_coverage >= 0.7 → `slot_extraction`, 환자 종료 요청 → `slot_extraction` | LLM 전체 실패 → 대화 일시 중단 |
| `slot_extraction` | ClinicalSlot(04) 호출. 대화 전체에서 구조화된 slot 추출 | `handoff_generation` | 추출 실패 → 대화 원문으로 handoff 생성 시도 |
| `handoff_generation` | HandoffGenerator(10) 호출. 12-section report 생성 | `evidence_verification` | 생성 실패 → minimal template report 생성 |
| `evidence_verification` | EvidenceVerifier(11) 호출. release gate | passed → `handoff_delivery`, regenerate → `handoff_generation` (max 2회), reject → HTTP 422 | verifier 실패 → rule-based 검증만 수행 |
| `handoff_delivery` | report 반환 및 세션 종료 처리 | `completed` (정상 종료 시) | 저장 실패 → 재시도 후 경고 첨부 반환 |
| `crisis_flow` | CTRS 1-2 분기 전용 상태. 아래 "Crisis Flow" 절 참조 | `completed` 또는 `handoff_delivery`(긴급 report 생성 후) | — |
| `completed` | 세션 정상 종료 상태 | (종료) | — |
| `error` | 상태 머신 자체의 처리 불가 오류를 나타내는 종결 상태 | (종료 또는 복구 재시도) | — |

### Crisis Flow (CTRS 1-2 분기)

CTRS 1-2 감지 시 별도 crisis_flow 상태로 전환한다:

1. 대화 즉시 중단 (dialogue_loop 중이면 강제 종료)
2. CTRS level별 위기 대응 메시지 반환 — **정정(BUG-009, open):** 실제 코드(`_CRISIS_MESSAGES`, `agents/orchestrator.py:57-68`)가 반환하는 메시지는 CTRS 1(`EMERGENCY`) "즉시 119 또는 112에 연락해 주세요. 자살예방상담전화 1393도 24시간 운영되고 있습니다", CTRS 2(`HIGH_RISK`) "자살예방상담전화 1393, 정신건강위기상담전화 1577-0199로 연락해 주세요"다. **"109"는 이 프로덕션 경로 어디에도 등장하지 않는다** — `f1.py`/`evidence_verifier.py`(`11_evidence_verifier.md`의 V-07 세부 규칙 참조, CTRS 1: `119|112|응급`, CTRS 2: `109|119|긴급|위기상담`) 등 이미 "109"로 표준화된 다른 위기 대응 표면과 불일치하는, 알려진 미해결 결함이다(BUG-009, `error.md`)
3. Dashboard critical alert 생성
4. Human review 즉시 등록
5. 긴급 handoff report 생성 (수집된 정보 범위 내에서)

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `patient_id` | `string` | 환자 식별자 |
| `session_id` | `string` | 현재 세션 ID |
| `input_type` | `enum` | `text`, `stt_transcript`, `ocr_document` |
| `raw_input` | `string` | 원본 입력 텍스트 |
| `stt_result` | `object \| null` | STT Agent 출력 (해당 시) |
| `ocr_result` | `object \| null` | OCR Agent 출력 (해당 시) |
| `session_state` | `object` | 현재 세션 상태 (이전 턴 정보 포함) |

## 출력

```json
{
  "session_id": "sess_20260618_001",
  "patient_id": "pt_12345",
  "current_stage": "dialogue_loop",
  "next_agent": "03_dialogue",
  "unified_context": {
    "text_inputs": ["..."],
    "stt_transcript": "...",
    "ocr_extracted": { "medications": [], "diagnoses": [] },
    "retrieved_history": []
  },
  "safety_status": {
    "ctrs_level": 4,
    "crisis_triggered": false,
    "last_checked_at": "2026-06-18T14:30:00+09:00"
  },
  "stage_history": [
    { "stage": "safety_gate", "agent": "02_safety_classifier", "result": "pass", "timestamp": "..." }
  ]
}
```

## Unified Context 스키마

Orchestrator는 `context_retrieval` 단계에서 여러 source의 정보를 단일 unified_context로 병합한다. Information Fusion(마스터 계획 Agent 6)은 별도 agent가 아니라 이 로직에 통합되어 있다.

```json
{
  "conversation_summary": "string (현재 세션 대화 요약)",
  "slot_data": {
    "chief_complaint": "string | null",
    "onset": "string | null",
    "duration": "string | null",
    "triggers": "string | null",
    "sleep": "string | null",
    "appetite": "string | null",
    "mood": "string | null",
    "anxiety": "string | null",
    "concentration": "string | null",
    "functional_impairment": "string | null",
    "medication": "string | null",
    "past_psychiatric_history": "string | null",
    "risk_factors": "string | null"
  },
  "stt_transcripts": ["array of normalized STT transcripts"],
  "ocr_blocks": ["array of OCR extracted blocks with confidence"],
  "prior_handoff_summary": "string | null (이전 handoff report 요약)",
  "medical_records": ["array of medical record entries"],
  "medication_records": ["array of medication entries"],
  "current_scale_scores": ["array of current session scale scores"],
  "ctrs_level": 5,
  "risk_events": ["array of risk event records"],
  "source_metadata": [
    {
      "source_type": "dialogue | stt | ocr | medical_record | prior_handoff",
      "timestamp": "ISO 8601",
      "confidence": 0.0
    }
  ]
}
```

**병합 규칙:**
1. 중복 정보는 가장 최신 + 가장 높은 confidence를 우선한다.
2. 충돌 정보는 양쪽을 모두 보존하고 `conflict: true` 플래그를 부여한다.
3. 모든 항목에 source, timestamp, confidence 메타데이터를 보존한다.

## 세션 상태 영속화 (Session State Persistence)

각 상태 전환 시 다음 필드를 영속화하여 장애 복구가 가능하도록 한다:

| 영속화 필드 | 설명 |
|---|---|
| `current_stage` | 현재 상태 머신 단계 |
| `ctrs_level` | 최신 CTRS level |
| `slot_data` | 현재까지 수집된 slot 정보 |
| `conversation_history` | 대화 이력 (최근 N턴) |
| `safety_results` | Safety 분류 결과 이력 |
| `scale_scores` | 현재 세션 척도 점수 |
| `stage_history` | 상태 전환 이력 (audit용) |
| `unified_context` | 조립된 통합 context |
| `error_log` | 발생한 오류 이력 |

## 핵심 동작

1. **입력 통합(Merge)**: STT transcript, OCR 추출 결과, 텍스트 입력을 하나의 unified context로 병합한다.
2. **Safety gate 우선 실행**: 모든 환자 메시지는 SafetyClassifierAgent(02)를 먼저 거친다. 예외 없음.
3. **CTRS 1-2 즉시 대응**: CTRS 1-2 판정 시 dialogue loop를 즉시 중단하고 crisis flow를 발동한다.
   - Crisis flow: 위기 대응 메시지 전달 + 의료진 즉시 알림 + handoff report 긴급 생성
4. **Context retrieval**: TemporalRetrieverAgent(08)를 호출하여 과거 대화, 이전 handoff, PHQ-9/GAD-7 이력을 가져온다.
5. **Dialogue loop 관리**: DialogueAgent(03)의 턴을 관리하며, 충분한 정보 수집 여부를 판단한다.
6. **Slot extraction 트리거**: 대화 종료 또는 충분한 정보 수집 시 ClinicalSlotAgent(04)를 호출한다.
7. **Handoff 생성 및 검증**: HandoffGeneratorAgent(10) 호출 후, EvidenceVerifierAgent(11)로 검증한다.
8. **상태 머신 persist**: 각 stage 전환 시 session_state를 저장하여 장애 복구가 가능하도록 한다.

## 에이전트 호출 순서

| 단계 | 호출 에이전트 | 조건 |
|---|---|---|
| 1 | `05_input_normalizer` | STT/OCR 입력 시 |
| 2 | `02_safety_classifier` | 모든 환자 메시지 (매 턴) |
| 3 | `08_temporal_retriever` | 대화 시작 시 + 필요 시 |
| 4 | `03_dialogue` | 대화 진행 중 |
| 5 | `04_clinical_slot` | 대화 종료 시 |
| 6 | `09_temporal_summary` | handoff 생성 전 |
| 7 | `10_handoff_generator` | slot 추출 완료 후 |
| 8 | `11_evidence_verifier` | handoff 생성 후 (release gate) |

## 안전 제약

1. **AI는 진단하지 않는다.** Orchestrator는 어떤 단계에서도 진단명을 생성하거나 전달하지 않는다.
2. **Safety gate 우회 불가.** 어떤 입력이든 SafetyClassifierAgent를 반드시 거친다.
3. **CTRS 1-2는 모든 기능보다 우선한다.** Crisis flow 발동 시 다른 모든 처리를 즉시 중단한다.
4. **Orchestrator 자신은 LLM을 호출하지 않는다.** 라우팅 결정은 전적으로 rule-based 상태 머신이다(`agents/orchestrator.py:1-9`, `routing/agent_model_registry.yaml`의 `orchestrator: strategy: fixed, adapter: none`). "애매한 상황의 판단 보조"는 하위 에이전트(SafetyClassifier 등)가 개별적으로 수행하는 것이며, Orchestrator 코드 경로 자체에는 LLM 호출이 존재하지 않는다.
5. **구조화 척도 점수(PHQ-9, GAD-7)는 rule-based로 계산한다.** LLM에 점수 계산을 위임하지 않는다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| Safety classifier 무응답 (timeout) | 입력을 CTRS 2로 간주하고 crisis flow 발동. 안전 우선 원칙. |
| LLM primary 무응답 | Secondary(K-EXAONE) → Fallback(A.X K1) 순차 시도 |
| 전체 LLM 무응답 | 대화 일시 중단, "잠시 후 다시 시도해주세요" 메시지 표시, 의료진 알림 |
| Session state 유실 | 마지막 persist 지점부터 복구 시도. 복구 불가 시 새 세션 시작 안내 |
| Agent 간 데이터 불일치 | 로그 기록 후 safety classifier 재실행, 불일치 해소 불가 시 의료진 알림 |

## Timeout 및 Fallback 정책

| Agent | Timeout | Fallback |
|---|---|---|
| SafetyClassifier(02) | 2초 | keyword 결과만 사용. 양쪽 실패 시 CTRS 2 간주 (안전 우선) |
| Dialogue(03) | 5초 | Secondary → Fallback LLM 시도. 전체 실패 시 대화 일시 중단 |
| ClinicalSlot(04) | 5초 | 대화 원문을 비구조화 상태로 handoff에 첨부 |
| TemporalRetriever(08) | 3초 | 과거 맥락 없이 현재 세션 정보만으로 진행 |
| TemporalSummary(09) | 5초 | direction을 모두 "unknown"으로 처리 |
| HandoffGenerator(10) | 30초 | minimal template report 생성 |
| EvidenceVerifier(11) | 10초 | rule-based 검증만 수행 |
