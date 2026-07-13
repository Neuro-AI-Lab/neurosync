# Task 1 개발 PRD: AI 기반 사전문진 Handoff Report 생성

> **Version**: v1.0
> **Created**: 2026-06-18
> **Status**: Active
> **Owner**: AI Research 팀
> **Parent Document**:
> - [`docs/AI_master_plan.md`](../AI_master_plan.md) (마스터 개발 계획 — SSOT)

---

## 0. 문서 개요

### 0.1 목적

본 문서는 NeuroSync 정신건강 사전문진 시스템의 **Task 1: AI 기반 사전문진 Handoff Report 생성**에 대한 개발 PRD이다. 기능 1-1부터 1-5까지의 모든 개발 항목(DEV), 검증 항목(VER), 설정 항목(CFG), 문서화 항목(DOC)을 체크리스트 ID로 관리하며, 각 항목의 구현 명세, API 스펙, 검증 기준을 정의한다.

### 0.2 버전 이력

| 버전 | 날짜 | 변경 사항 |
|------|------|----------|
| v1.0 | 2026-06-18 | 초안 작성. 기능 1-1~1-5 개발/검증 체크리스트, API 명세, Agent 구성 정의 |

### 0.3 개발 범위

본 PRD의 개발 범위는 다음 디렉토리에서만 수행한다:

| 경로 | 역할 |
|------|------|
| `apps/ai-server/` | AI 서버 코드 (agents, routes, schemas, adapters, routing, prompts) |
| `apps/api/` | 백엔드 API 서버 (models, services, schemas) |
| `docs/ai/` | AI 문서 (agent specs, prompts, personas, eval) |

### 0.4 제외 범위

본 PRD는 다음을 다루지 않는다:

- **Task 0**: 회원가입/로그인 및 최초 사용자 Intake (Auth/Profile Agent, Initial Intake Agent)
- **Task 2**: 진료과/병원 정보 제공 (Department Matching Agent, Hospital Search Agent)
- **Task 3**: 위기 관리 알림 (Crisis Notification Agent, Crisis Workflow Agent)
- **Frontend / Mobile App**: UI/UX 구현, React/Flutter 등
- **인프라**: AWS/GCP 배포, CI/CD 파이프라인, 모니터링 인프라 (Datadog, Grafana 등)
- **Common Module 1 (Consent & Privacy)**: 동의 관리 모듈은 Task 0 및 플랫폼 팀 소관

---

## 1. ID 체계

### 1.1 체크리스트 ID 형식

```
T1-Fn-{TYPE}-{SEQ}
```

| 구성요소 | 설명 | 예시 |
|----------|------|------|
| `T1` | Task 1 고정 접두사 | `T1` |
| `Fn` | 기능 번호 (F0~F5) | `F1`, `F3` |
| `TYPE` | 항목 유형 | `DEV`, `VER`, `CFG`, `DOC` |
| `SEQ` | 3자리 zero-padded 순번 | `001`, `012` |

**TYPE 정의:**

| TYPE | 의미 | 예시 |
|------|------|------|
| `DEV` | 개발 항목 (코드 구현, 리팩토링, 모듈 신규 생성) | `T1-F1-DEV-003` |
| `VER` | 검증 항목 (유닛 테스트, 통합 테스트, 시뮬레이션) | `T1-F1-VER-002` |
| `CFG` | 설정 항목 (registry, config, env, prompt 설정) | `T1-F0-CFG-001` |
| `DOC` | 문서 항목 (agent spec 업데이트, API 문서, 운영 가이드) | `T1-F5-DOC-001` |

### 1.2 기능 번호 매핑

| 기능 번호 | 기능명 | 범위 |
|-----------|--------|------|
| `F0` | Orchestrator / 공통 | 전체 파이프라인 제어, 공통 모듈, CTRS 매핑 |
| `F1` | 기능 1-1: 자율 대화 기반 문진 | 대화, 안전, 입력 정규화, STT, OCR |
| `F2` | 기능 1-2: RAG 기반 정신건강 영역/진료과 후보 추론 | TemporalRetriever, RAG pipeline |
| `F3` | 기능 1-3: 구조화된 사전문진 설문 | ClinicalSlot, Survey Scoring |
| `F4` | 기능 1-4: 종단적 상태 추론 | TemporalSummary, 상태 변화 추적 |
| `F5` | 기능 1-5: Handoff Report 생성 | HandoffGenerator, EvidenceVerifier |

### 1.3 Agent 번호 매핑표

마스터 개발 계획의 Agent 번호와 코드베이스의 agent spec / code module 간의 매핑이다. 본 PRD에서 agent를 언급할 때는 **agent spec 번호**를 기준으로 한다.

| Master Plan Agent | Agent Spec (docs/ai/agents/) | Code Module (apps/ai-server/src/) | Registry Key | System Prompt |
|---|---|---|---|---|
| Agent 1. Orchestrator | `01_orchestrator.md` | `agents/` (신규) | `orchestrator` | `prompts/orchestrator/v1.system.md` |
| Agent 5. Safety/Risk Triage | `02_safety_classifier.md` | `agents/safety_classifier.py` | `safety_classifier` | `prompts/safety_classifier/v1.system.md` |
| Agent 2. Chatbot Interview | `03_dialogue.md` | `routes/chat.py` (inline) | `dialogue` | `prompts/dialogue/v1.system.md` |
| Agent 8/9. Survey (Planner+Scoring) | `04_clinical_slot.md` | `agents/` (신규) | `clinical_slot` | `prompts/clinical_slot/v1.system.md` |
| (Input Normalizer) | `05_input_normalizer.md` | `agents/` (신규) | `input_normalizer` | `prompts/input_normalizer/v1.system.md` |
| Agent 4. STT Transcript | `06_stt.md` | `adapters/` (STT adapter) | `stt_agent` | N/A (adapter, not LLM agent) |
| Agent 3. OCR Document | `07_ocr.md` | `adapters/` (OCR adapter) | `ocr_agent` | N/A (adapter, not LLM agent) |
| Agent 6/7. Info Fusion + RAG | `08_temporal_retriever.md` | `agents/` (신규) | `temporal_retriever` | `prompts/temporal_retriever/v1.system.md` |
| Agent 10. Sentiment Analysis | `13_sentiment_analyzer.md` | `agents/` (신규) | `sentiment_analyzer` | `prompts/sentiment_analyzer/v1.system.md` |
| Agent 11. Longitudinal State Tracking | `09_temporal_summary.md` | `agents/` (신규) | `temporal_summary` | `prompts/temporal_summary/v1.system.md` |
| Agent 12. Handoff Report Writer | `10_handoff_generator.md` | `agents/handoff_generator.py` | `handoff_generator` | `prompts/handoff_generator/v1.system.md` |
| Agent 13. QA & Consistency | `11_evidence_verifier.md` | `agents/evidence_verifier.py` | `evidence_verifier` | `prompts/evidence_verifier/v1.system.md` |
| (Prompt Eval) | `12_prompt_eval.md` | N/A (offline) | `prompt_eval` | N/A |

**통합 결정 사항:**

- **Information Fusion (master plan Agent 6)** → Orchestrator(01)의 context assembly 로직에 통합. 별도 agent로 분리하지 않는다. 이유: Information Fusion은 여러 source를 단순 병합하는 역할이며, Orchestrator의 상태 머신 내에서 context_retrieval 단계로 처리하는 것이 latency와 복잡도 측면에서 유리하다.
- **Survey Planner (master plan Agent 8)** → Orchestrator(01)의 routing logic에 통합. 설문 선택 규칙은 rule-based이므로 별도 LLM agent가 불필요하다. Orchestrator가 RAG 결과와 CTRS level에 따라 설문 도구를 선택한다.
- **Survey Scoring (master plan Agent 9)** → standalone rule-based module로 구현. LLM을 사용하지 않으므로 agent spec 불필요. `apps/ai-server/src/scoring/` 디렉토리에 순수 Python 모듈로 구현한다.
- **Sentiment Analysis (master plan Agent 10)** → 독립 agent `SentimentAnalyzerAgent(13)`로 분리. 발화 단위 감정 분석 + 세션 통합 리포트를 수행한다. TemporalSummary(09)는 이 출력을 소비하여 sentiment 추이를 종단적 비교에 반영한다. HandoffGenerator(10)는 대화 기록 내 발화별 sentiment 태그를 표시한다.

---

## 2. 기능 1-1: 자율 대화 기반 문진

### 2.1 개요

사용자와 자연어 기반 자율 대화를 수행하여 주호소, 증상, 위험 신호, 보호 요인, 일상 기능 손상 정보를 수집한다. 모든 입력(텍스트, 음성, 문서 이미지)은 단일 파이프라인으로 수렴하며, Safety Gate가 병렬로 실행되어 위기 상황을 실시간 감지한다.

### 2.2 관련 Agent

| Agent Spec | 역할 | Registry Key |
|------------|------|-------------|
| `01_orchestrator.md` | 전체 flow 제어, 상태 머신 관리 | `orchestrator` |
| `02_safety_classifier.md` | CTRS 기반 위험도 분류 (rule + LLM dual path) | `safety_classifier` |
| `03_dialogue.md` | 자율 대화 수행, slot 추출, 응답 생성 | `dialogue` |
| `05_input_normalizer.md` | STT/OCR 출력 정규화, 의료 용어 매핑 | `input_normalizer` |
| `06_stt.md` | 음성 → 텍스트 변환 (adapter) | `stt_agent` |
| `07_ocr.md` | 문서 이미지 → structured text (adapter) | `ocr_agent` |

### 2.3 Agent 실행 흐름

```
Input (text / audio / image)
  │
  ├── [audio] → STT Adapter(06) → InputNormalizer(05) ──┐
  ├── [image] → OCR Adapter(07) → InputNormalizer(05) ──┤
  └── [text] ───────────────────────────────────────────┘
                                                          │
                                                    normalized_text
                                                          │
                                              ┌───────────┴───────────┐
                                              │                       │
                                    SafetyClassifier(02)      ContextRetrieval
                                       (parallel)             (Orchestrator)
                                              │                       │
                                              ▼                       │
                                    ┌─────────┴─────────┐            │
                                    │                   │            │
                              CTRS 1-2              CTRS 3-5         │
                              (crisis)              (safe)           │
                                    │                   │            │
                                    ▼                   ▼            ▼
                              CrisisFlow         Dialogue(03) ← merged_context
                              (즉시 중단)              │
                                                       ▼
                                               ClinicalSlot(04)
                                               (slot extraction)
```

**핵심 규칙:**
1. SafetyClassifier(02)는 모든 입력에 대해 **항상** 실행된다 (bypass 불가).
2. CTRS 1-2 (critical/high) 감지 시 dialogue를 우회하고 즉시 crisis response를 반환한다.
3. SafetyClassifier와 ContextRetrieval은 **병렬** 실행하여 latency를 최소화한다.
4. STT/OCR 결과는 반드시 InputNormalizer를 거친 후 파이프라인에 진입한다.

### 2.4 개발 체크리스트

| ID | 항목 | 설명 | 관련 파일 | 우선순위 |
|----|------|------|----------|---------|
| `T1-F1-DEV-001` | Orchestrator 상태 머신 구현 | `input_received → safety_gate → context_retrieval → dialogue_loop → slot_extraction → handoff_generation → evidence_verification → handoff_delivery` 상태 전이 구현. CTRS 1-2 시 `crisis_flow` 즉시 분기. | `agents/orchestrator.py` (신규) | P0 |
| `T1-F1-DEV-002` | InputNormalizer agent 구현 | STT transcript 및 OCR parsed text를 정규화. 의료 용어 표준화 (약물명 → 식약처 코드 매핑 시도), 문장 분리, 화자 태깅. confidence score 전파. | `agents/input_normalizer.py` (신규) | P1 |
| `T1-F1-DEV-003` | STT adapter 구현 | `STTAdapter` protocol 구현. Primary: SKT A.dot STT, Fallback: OpenAI Whisper API. `transcribe(audio, lang, prev_context, timeout_s) -> STTResult` 인터페이스. confidence < 0.6 시 재발화 안내 플래그. | `adapters/stt_adapter.py` (신규) | P1 |
| `T1-F1-DEV-004` | OCR adapter 구현 | Upstage Document Parse API 호출. 문서 유형 분류 (진단서/처방전/상담기록/검사결과), 진단명/약물명/용량/날짜 추출, confidence score 부여, structured block 반환. | `adapters/ocr_adapter.py` (신규) | P1 |
| `T1-F1-DEV-005` | Dialogue slot tracking 고도화 | 현재 `DialogueLLMResponse.slot_updates`에서 key-value로 반환하는 구조를 `SlotData` schema와 정합시킴. 수집된 slot과 미수집 slot을 명시적으로 추적하여 Dialogue agent가 미수집 영역에 대한 질문을 우선 생성하도록 prompt 개선. | `schemas/dialogue.py`, `routes/chat.py` | P0 |
| `T1-F1-DEV-006` | Safety CTRS 매핑 통합 | 현재 `RiskLevel` enum (none/low/medium/high/critical)에 CTRS 1-5 매핑 추가. Section 13 참조. `SafetyOutput`에 `ctrs_level: int` 필드 추가. | `schemas/common.py`, `schemas/safety.py` | P0 |
| `T1-F1-DEV-007` | chat route 리팩토링 | 현재 `routes/chat.py`의 inline dialogue 로직을 Orchestrator 기반 flow로 리팩토링. Orchestrator가 safety gate, context retrieval, dialogue 호출을 순차/병렬 제어. | `routes/chat.py`, `agents/orchestrator.py` | P0 |
| `T1-F1-DEV-008` | SafetyClassifier 위기 응답 고도화 | 현재 `_CRISIS_RESPONSE` 하드코딩 → CTRS level별 차등 응답 템플릿 적용 (CTRS 1-2: 119/112 안내 + 대화 중단, CTRS 3: 위기상담 109 + 빠른 진료 권고). 마스터 계획 위기 안내 문구 반영. | `routes/chat.py`, `prompts/safety_classifier/` | P0 |
| `T1-F1-DEV-009` | STT confidence threshold 로직 | confidence >= 0.6: 정상 사용, < 0.6: 재발화 안내, < 0.4: 키보드 폴백 권유. threshold 값은 config에서 관리. | `adapters/stt_adapter.py`, `config.py` | P1 |
| `T1-F1-DEV-010` | OCR 후처리 파이프라인 | OCR 결과 후처리: 진단명 표준화 (KCD-8 매핑 검토), 약물명 dictionary matching, 표/차트 영역 별도 블록 보존, 손글씨 영역 confidence < 0.7 시 확인 필요 플래그. | `agents/input_normalizer.py` | P1 |

### 2.5 API 명세

#### POST /ai/chat/respond (기존, 수정)

기존 dialogue endpoint를 Orchestrator 기반 flow로 리팩토링한다.

**현재 상태:** `routes/chat.py`에서 SafetyClassifier → Dialogue LLM을 inline으로 호출.
**목표 상태:** Orchestrator agent가 전체 flow를 제어하고, route는 Orchestrator에 위임.

**Request Schema:**

```json
{
  "session_id": "string (required)",
  "request_id": "string (optional, auto-generated if null)",
  "user_message": "string (required)",
  "conversation_history": [
    { "role": "user|assistant", "content": "string" }
  ],
  "filled_slots": { "slot_key": "slot_value" },
  "input_type": "text | stt_transcript | ocr_document",
  "stt_result": {
    "transcript": "string",
    "confidence": 0.0,
    "segments": []
  },
  "ocr_result": {
    "document_type": "string",
    "extracted_text": "string",
    "structured_blocks": [],
    "confidence": 0.0
  },
  "safety_result": { "...": "optional, 이전 턴 safety 결과" }
}
```

**Response Schema:**

```json
{
  "model_used": "string",
  "prompt_version": "string",
  "latency_ms": 0.0,
  "reason_summary": "string",
  "assistant_response": "string",
  "slot_updates": { "slot_key": "slot_value" },
  "risk_level": "none | low | medium | high | critical",
  "ctrs_level": 5,
  "requires_human_review": false,
  "all_slots": { "slot_key": "slot_value" },
  "crisis_protocol_activated": false,
  "next_action": "continue_dialogue | transition_to_survey | handoff_ready | crisis_flow"
}
```

**SLA:**
- p95 latency < 2,000ms (safety gate + dialogue LLM 합산)
- Safety gate 단독 p95 < 1,000ms
- Dialogue 단독 p95 < 1,500ms

**Error Codes:**

| HTTP | Code | 설명 |
|------|------|------|
| 500 | `SAFETY_UNAVAILABLE` | Safety classification 실패 (non-negotiable, dialogue 진행 불가) |
| 500 | `DIALOGUE_FAILED` | Dialogue LLM 실패 (primary + fallback 모두 실패) |
| 422 | `INVALID_INPUT` | 입력 validation 실패 |

#### POST /ai/stt/transcribe (신규)

**설명:** 음성 입력을 텍스트로 변환한다. STT adapter를 호출하고 결과를 정규화하여 반환한다.

**Request Schema:**

```json
{
  "session_id": "string (required)",
  "request_id": "string (optional)",
  "audio_url": "string (S3 presigned URL)",
  "audio_format": "wav | mp3 | m4a | webm",
  "language": "ko",
  "previous_context": "string (optional, 직전 대화 문맥)"
}
```

**Response Schema:**

```json
{
  "transcript": "string",
  "confidence": 0.0,
  "segments": [
    {
      "start_ms": 0,
      "end_ms": 0,
      "speaker": "user",
      "text": "string",
      "confidence": 0.0
    }
  ],
  "vendor": "skt-adot | whisper-openai | whisper-local",
  "latency_ms": 0.0,
  "needs_retry": false,
  "fallback_suggestion": "keyboard | retry"
}
```

**SLA:**
- p95 < 2,000ms (Push-to-Talk 모드)
- WER <= 15% (한국어 일반 발화)
- WER <= 20% (의료 도메인)

**Error Codes:**

| HTTP | Code | 설명 |
|------|------|------|
| 500 | `STT_ALL_VENDORS_FAILED` | Primary + Fallback 모두 실패 |
| 422 | `UNSUPPORTED_AUDIO_FORMAT` | 지원하지 않는 오디오 형식 |
| 413 | `AUDIO_TOO_LARGE` | 파일 크기 초과 (limit: 25MB) |

#### POST /ai/ocr/parse (신규)

**설명:** 업로드된 문서 이미지를 OCR로 분석하여 structured data를 반환한다.

**Request Schema:**

```json
{
  "session_id": "string (required)",
  "request_id": "string (optional)",
  "document_url": "string (S3 presigned URL)",
  "document_type_hint": "prescription | diagnosis | consultation | lab_result | unknown",
  "language": "ko"
}
```

**Response Schema:**

```json
{
  "document_type": "prescription | diagnosis | consultation | lab_result | unknown",
  "extracted_text": "string (full text)",
  "structured_blocks": [
    {
      "block_type": "diagnosis | medication | date | department | table | handwriting | text",
      "content": "string",
      "confidence": 0.0,
      "needs_verification": false,
      "position": { "page": 1, "bbox": [0, 0, 100, 100] }
    }
  ],
  "medications": [
    {
      "name": "string",
      "dose": "string",
      "frequency": "string",
      "confidence": 0.0
    }
  ],
  "diagnoses": [
    {
      "term": "string",
      "kcd_code": "string (nullable)",
      "confidence": 0.0
    }
  ],
  "dates": {
    "treatment_date": "string (nullable)",
    "prescription_date": "string (nullable)"
  },
  "overall_confidence": 0.0,
  "vendor": "upstage-document-parse",
  "latency_ms": 0.0
}
```

**SLA:**
- p95 < 10,000ms / 문서
- TEDS >= 95%

**Error Codes:**

| HTTP | Code | 설명 |
|------|------|------|
| 500 | `OCR_VENDOR_FAILED` | Upstage Document Parse API 실패 |
| 422 | `UNSUPPORTED_DOCUMENT` | 지원하지 않는 문서 형식 |
| 413 | `DOCUMENT_TOO_LARGE` | 파일 크기 초과 (limit: 50MB) |

### 2.6 검증 체크리스트

| ID | 항목 | 검증 방법 | Pass 기준 | 관련 VP |
|----|------|----------|-----------|---------|
| `T1-F1-VER-001` | Dialogue 시뮬레이션 (경증 초진) | VP-001 persona로 Patient LLM 시뮬레이션, 8-15턴 대화 생성 | 대화 자연스러움, slot 수집 >= 7/13개 | VP-001 |
| `T1-F1-VER-002` | Dialogue 시뮬레이션 (경증 재진) | VP-002 persona로 시뮬레이션, prior handoff 주입 | 이전 정보 참조 응답 생성, 변화 질문 포함 | VP-002 |
| `T1-F1-VER-003` | 중증 대화 시뮬레이션 | VP-003 persona (자살 사고 포함)로 시뮬레이션 | CTRS 1-2 감지 → crisis flow 발동, 대화 중단 | VP-003 |
| `T1-F1-VER-004` | CTRS crisis bypass 테스트 | high/critical risk_level 입력 시 dialogue 우회 확인 | crisis_protocol_activated=true, 위기 안내 문구 반환 | VP-003 |
| `T1-F1-VER-005` | STT 정규화 정확도 | 의료 한국어 발화 샘플 50건으로 STT → InputNormalizer 파이프라인 테스트 | 의료 용어 정규화율 >= 80%, confidence 전파 정확 | - |
| `T1-F1-VER-006` | OCR 파싱 정확도 | 처방전/진단서 샘플 20건으로 OCR → InputNormalizer 테스트 | 약물명 추출 정확도 >= 85%, 진단명 추출 >= 80% | - |
| `T1-F1-VER-007` | Slot 수집 수렴 테스트 | 15턴 대화 후 slot 수집률 측정 | 필수 slot (chief_complaint, onset, risk_factors) 100% 수집 | VP-001, VP-003 |
| `T1-F1-VER-008` | Safety + Dialogue 병렬 실행 latency | 100회 반복 호출로 p95 latency 측정 | safety + dialogue 합산 p95 < 2,000ms | - |

---

## 3. 기능 1-2: RAG 기반 정신건강 영역/진료과 후보 추론

### 3.1 개요

자율 대화, OCR, STT, 기존 진료기록 등 여러 source에서 수집된 정보를 통합하고, pgvector 기반 RAG 파이프라인으로 정신건강 영역별 지식베이스를 검색하여 정신건강 영역 후보, 진료과 후보, 추가 확인 질문, 권장 구조화 문진 도구를 제안한다.

### 3.2 관련 Agent

| Agent Spec | 역할 | Registry Key |
|------------|------|-------------|
| `08_temporal_retriever.md` | 정보 검색 및 RAG 파이프라인 실행 | `temporal_retriever` |

**통합 결정:** Information Fusion (마스터 계획 Agent 6)은 별도 agent가 아니라 **Orchestrator(01)의 context assembly 로직**에 통합한다. Orchestrator가 각 source (대화, OCR, STT, 진료기록, 이전 handoff)의 출력을 수집하여 unified clinical context를 구성하고, 이를 TemporalRetriever에 전달한다. 이유:

1. Information Fusion은 단순 병합 + 중복 제거 + 충돌 표시 역할이며, LLM 호출이 불필요하다.
2. Orchestrator의 상태 머신에서 `context_retrieval` 단계로 자연스럽게 처리된다.
3. 별도 agent 호출 시 추가 latency 발생하나 실질적 판단 없음.

### 3.3 pgvector 기반 RAG 파이프라인 (Placeholder)

> **이 파이프라인은 placeholder이다. DB 정보(vector store, embedding model, knowledge base) 확정 후 상세 설계를 업데이트한다.**

**아키텍처 개요:**

```
unified_context (from Orchestrator)
  │
  ▼
Embedding (model TBD) → query vector
  │
  ▼
pgvector similarity search (knowledge base)
  │
  ▼
Top-K retrieval + reranking
  │
  ▼
TemporalRetriever(08) LLM: context + retrieved docs → structured output
  │
  ▼
{domain_candidates, department_candidates, recommended_surveys, additional_questions}
```

**초기 구현:** RAG 검색 없이 TemporalRetriever가 LLM으로 직접 영역 후보를 추론하는 fallback 모드를 우선 구현한다. Knowledge base 구축 후 RAG 파이프라인을 활성화한다.

### 3.4 개발 체크리스트

| ID | 항목 | 설명 | 관련 파일 | 우선순위 |
|----|------|------|----------|---------|
| `T1-F2-DEV-001` | TemporalRetriever agent 구현 | unified clinical context를 입력받아 정신건강 영역 후보, 진료과 후보, 추가 확인 질문, 권장 설문 도구를 출력. 초기에는 LLM-only 모드로 구현. | `agents/temporal_retriever.py` (신규) | P0 |
| `T1-F2-DEV-002` | TemporalRetriever schema 정의 | `TemporalRetrieverInput`, `TemporalRetrieverOutput` Pydantic schema 정의. output에 `domain_candidates`, `department_candidates`, `recommended_surveys`, `additional_questions`, `rag_sources` 포함. | `schemas/temporal_retriever.py` (신규) | P0 |
| `T1-F2-DEV-003` | Orchestrator context assembly | Orchestrator 내에서 대화 history, slot data, STT transcript, OCR blocks, prior handoff, 진료기록을 unified clinical context로 병합하는 로직 구현. 중복 제거, 충돌 표시, source/timestamp/confidence 메타데이터 보존. | `agents/orchestrator.py` | P0 |
| `T1-F2-DEV-004` | RAG retrieval stub | pgvector 검색 stub 구현. 실제 vector store 연결 전까지 empty results 반환. interface만 정의하여 추후 plug-in 가능하도록 설계. | `rag/retriever.py` (신규, ai-server 또는 api) | P2 |
| `T1-F2-DEV-005` | TemporalRetriever prompt 작성 | domain candidates 출력을 위한 system prompt 작성. 진단 금지 원칙, evidence 필수 원칙, confidence score 부여 규칙 포함. | `prompts/temporal_retriever/v1.system.md` | P0 |

### 3.5 API 명세

#### POST /ai/temporal/retrieve (신규)

**설명:** unified clinical context를 입력받아 정신건강 영역 후보, 진료과 후보, 추가 확인 질문을 반환한다.

**Request Schema:**

```json
{
  "session_id": "string (required)",
  "request_id": "string (optional)",
  "unified_context": {
    "conversation_summary": "string",
    "slot_data": { "chief_complaint": "...", "onset": "..." },
    "stt_transcripts": [],
    "ocr_blocks": [],
    "prior_handoff_summary": "string (nullable)",
    "medical_records": [],
    "medication_records": [],
    "current_scale_scores": [],
    "ctrs_level": 5,
    "risk_events": []
  },
  "is_first_visit": true
}
```

**Response Schema:**

```json
{
  "model_used": "string",
  "prompt_version": "string",
  "latency_ms": 0.0,
  "domain_candidates": [
    {
      "domain": "anxiety | depression | alcohol | substance | trauma | sleep | psychosis | other",
      "confidence": 0.0,
      "evidence": ["string"],
      "recommended_surveys": ["GAD-7", "PHQ-9"]
    }
  ],
  "department_candidates": [
    {
      "department": "string",
      "reason": "string"
    }
  ],
  "additional_questions": ["string"],
  "rag_sources": [
    {
      "source_id": "string",
      "title": "string",
      "relevance_score": 0.0
    }
  ]
}
```

**SLA:**
- p95 < 3,000ms (LLM-only 모드)
- p95 < 5,000ms (RAG 활성화 시)

**Error Codes:**

| HTTP | Code | 설명 |
|------|------|------|
| 500 | `RETRIEVER_FAILED` | TemporalRetriever LLM 호출 실패 |
| 422 | `EMPTY_CONTEXT` | unified_context가 비어있음 |

### 3.6 검증 체크리스트

| ID | 항목 | 검증 방법 | Pass 기준 | 관련 VP |
|----|------|----------|-----------|---------|
| `T1-F2-VER-001` | VP-002 retrieval 테스트 (재진) | VP-002 경증 재진 context로 TemporalRetriever 호출 | anxiety/depression 영역 중 최소 1개 후보 반환, confidence >= 0.5 | VP-002 |
| `T1-F2-VER-002` | VP-004 retrieval 테스트 (중증 재진) | VP-004 중증 재진 context로 호출 | 위험 관련 영역 후보 반환, CTRS 고려한 진료과 후보 포함 | VP-004 |
| `T1-F2-VER-003` | 초진 empty retrieval 테스트 | 최소 정보 (chief_complaint만 존재)로 호출 | 빈 결과가 아닌 최소 1개 영역 후보 반환, "추가 정보 필요" 플래그 | VP-001 |
| `T1-F2-VER-004` | 영역 후보 ranking 정확도 | 사전 정의된 10개 임상 시나리오로 영역 후보 정확도 측정 | top-1 정확도 >= 70%, top-3 정확도 >= 90% | - |

---

## 4. 기능 1-3: 구조화된 사전문진 설문

### 4.1 개요

자율 대화와 RAG 분석 결과를 바탕으로 적절한 구조화 문진 도구(PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C 등)를 선택하고, 응답을 수집하며, **rule-based logic**으로 점수를 계산한다. LLM은 점수 계산에 사용하지 않는다.

### 4.2 관련 Agent

| Agent Spec | 역할 | Registry Key |
|------------|------|-------------|
| `04_clinical_slot.md` | 대화에서 임상 slot 추출 (LLM 기반) | `clinical_slot` |

**통합 결정:**
- **Survey Planner (마스터 계획 Agent 8)** → Orchestrator(01)의 routing logic에 통합. 설문 선택은 다음의 rule-based 로직으로 결정한다:
  - 모든 사용자: PHQ-4 (초기 스크리닝) + 안전 gate
  - PHQ-4 depression subscale >= 3: PHQ-9 추가
  - PHQ-4 anxiety subscale >= 3: GAD-7 추가
  - 음주 관련 표현: AUDIT-C 추가
  - 전체: WHO-5 (웰빙 지수)
  - CTRS 1-2: 설문 중단, 위기 대응 우선
- **Survey Scoring (마스터 계획 Agent 9)** → standalone rule-based module (`apps/ai-server/src/scoring/`). Agent spec 불필요. 순수 Python 함수로 구현.

### 4.3 설문 도구별 Scoring Rule

| 척도 | 문항수 | 점수 범위 | Severity Cut-off | 위험 문항 |
|------|--------|----------|------------------|----------|
| **PHQ-9** | 9 | 0-27 | 0-4: minimal, 5-9: mild, 10-14: moderate, 15-19: moderately severe, 20-27: severe | 문항 9 (자살 사고) >= 1 → Safety 전달 |
| **GAD-7** | 7 | 0-21 | 0-4: minimal, 5-9: mild, 10-14: moderate, 15-21: severe | 없음 |
| **PHQ-4** | 4 | 0-12 | 0-2: normal, 3-5: mild, 6-8: moderate, 9-12: severe | depression subscale (Q3+Q4), anxiety subscale (Q1+Q2) |
| **WHO-5** | 5 | 0-25 (raw), 0-100 (percentage) | raw <= 13: low wellbeing (추가 평가 필요) | 없음 |
| **AUDIT-C** | 3 | 0-12 | 남: >= 4, 여: >= 3 → 위험 음주 | 없음 |

### 4.4 개발 체크리스트

| ID | 항목 | 설명 | 관련 파일 | 우선순위 |
|----|------|------|----------|---------|
| `T1-F3-DEV-001` | ClinicalSlot agent 구현 | 대화 텍스트에서 `SlotData`의 13개 필드를 LLM으로 추출. 기존 filled_slots와 병합하여 미수집 slot 목록 반환. | `agents/clinical_slot.py` (신규) | P0 |
| `T1-F3-DEV-002` | ClinicalSlot schema 정의 | `ClinicalSlotInput`, `ClinicalSlotOutput` 정의. output에 `extracted_slots`, `missing_slots`, `confidence_per_slot` 포함. | `schemas/clinical_slot.py` (신규) | P0 |
| `T1-F3-DEV-003` | Survey Scoring module 구현 | PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C 각각의 scoring 함수 구현. 입력: 문항별 응답 list, 출력: total_score, severity, critical_items. 모든 계산은 순수 Python, LLM 호출 없음. | `scoring/survey_scorer.py` (신규) | P0 |
| `T1-F3-DEV-004` | Survey Planner routing logic | Orchestrator에 설문 선택 로직 추가. domain_candidates + CTRS level에 따라 적절한 설문 도구 선택. Section 4.2의 rule-based 로직 구현. | `agents/orchestrator.py` | P1 |
| `T1-F3-DEV-005` | ClinicalSlot prompt 작성 | 13개 slot 추출을 위한 system prompt 작성. slot 정의, 추출 규칙, 미수집 판단 기준 명시. | `prompts/clinical_slot/v1.system.md` | P0 |
| `T1-F3-DEV-006` | 위험 문항 Safety 전달 로직 | PHQ-9 문항 9 >= 1, 또는 기타 위험 문항 양성 시 Safety/Risk Triage로 즉시 전달하는 로직. Survey Scoring 출력에서 `critical_item_positive: true` 반환 시 Orchestrator가 safety re-evaluation 트리거. | `scoring/survey_scorer.py`, `agents/orchestrator.py` | P0 |

### 4.5 API 명세

#### POST /ai/slots/extract (신규)

**설명:** 대화 텍스트에서 임상 slot을 추출한다.

**Request Schema:**

```json
{
  "session_id": "string (required)",
  "request_id": "string (optional)",
  "conversation_history": [
    { "role": "user|assistant", "content": "string" }
  ],
  "current_slots": {
    "chief_complaint": "string (nullable)",
    "onset": "string (nullable)",
    "...": "..."
  }
}
```

**Response Schema:**

```json
{
  "model_used": "string",
  "prompt_version": "string",
  "latency_ms": 0.0,
  "extracted_slots": {
    "chief_complaint": "최근 불안과 수면 문제",
    "onset": "2주 전",
    "...": "..."
  },
  "missing_slots": ["medication", "past_psychiatric_history"],
  "confidence_per_slot": {
    "chief_complaint": 0.95,
    "onset": 0.82,
    "...": 0.0
  }
}
```

**SLA:**
- p95 < 2,000ms

#### POST /ai/survey/score (신규, rule-based)

**설명:** 구조화 설문 응답을 rule-based로 채점한다. LLM을 사용하지 않는다.

**Request Schema:**

```json
{
  "session_id": "string (required)",
  "scale_name": "PHQ-9 | GAD-7 | PHQ-4 | WHO-5 | AUDIT-C",
  "responses": [0, 1, 2, 3, 0, 1, 2, 0, 1],
  "patient_sex": "male | female | other (optional, AUDIT-C용)"
}
```

**Response Schema:**

```json
{
  "scale_name": "PHQ-9",
  "total_score": 15,
  "max_score": 27,
  "severity": "moderately_severe",
  "critical_item_positive": false,
  "critical_items": [],
  "subscale_scores": {},
  "interpretation": "우울 증상 추가 평가 필요",
  "recommended_action": "clinician_review"
}
```

**SLA:**
- p95 < 50ms (순수 연산, LLM 없음)

**Error Codes:**

| HTTP | Code | 설명 |
|------|------|------|
| 422 | `INVALID_SCALE` | 지원하지 않는 척도명 |
| 422 | `INVALID_RESPONSE_COUNT` | 문항수와 응답수 불일치 |
| 422 | `RESPONSE_OUT_OF_RANGE` | 응답 값이 해당 척도의 유효 범위 밖 |

### 4.6 검증 체크리스트

| ID | 항목 | 검증 방법 | Pass 기준 | 관련 VP |
|----|------|----------|-----------|---------|
| `T1-F3-VER-001` | PHQ-9 scoring unit test | 모든 severity boundary 값으로 테스트 (0, 4, 5, 9, 10, 14, 15, 19, 20, 27) | 모든 boundary에서 올바른 severity 반환 | - |
| `T1-F3-VER-002` | GAD-7 scoring unit test | 동일 boundary 테스트 (0, 4, 5, 9, 10, 14, 15, 21) | 100% 정확 | - |
| `T1-F3-VER-003` | PHQ-4 subscale test | depression/anxiety subscale 분리 계산 검증 | subscale 합산 정확, severity 정확 | - |
| `T1-F3-VER-004` | WHO-5 / AUDIT-C scoring test | WHO-5 raw → percentage 변환, AUDIT-C 성별별 cut-off 적용 | 100% 정확 | - |
| `T1-F3-VER-005` | Slot extraction 정확도 | VP-001~VP-004 각 persona 대화로 ClinicalSlot 호출, 추출 결과를 golden label과 비교 | 필수 slot 3개 (chief_complaint, onset, risk_factors) F1 >= 0.8 | VP-001~004 |

---

## 5. 기능 1-4: 종단적 상태 추론

### 5.1 개요

이전 대화, 이전 설문 결과, 이전 handoff report, 진료기록, 약처방 기록을 시간순으로 비교하여 사용자의 정신건강 상태 변화를 추적한다. 호전/악화/유지/불명의 방향성을 evidence와 함께 판단하고, 시각화를 위한 plot-ready 시계열 데이터를 생성한다.

### 5.2 관련 Agent

| Agent Spec | 역할 | Registry Key |
|------------|------|-------------|
| `09_temporal_summary.md` | 종단적 상태 변화 추론 (sentiment 추이 그래프 포함) | `temporal_summary` |
| `08_temporal_retriever.md` | 이전 기록 검색 및 시계열 정보 수집 | `temporal_retriever` |
| `13_sentiment_analyzer.md` | 발화 단위 감정 분석 + 세션 통합 sentiment 리포트 | `sentiment_analyzer` |

**역할 분담:**
- **SentimentAnalyzer(13)**: 발화 단위 감정 분석 수행 + 세션 통합 리포트 생성. F1(자율 대화) 중 매 턴마다 실행.
- **TemporalSummary(09)**: SentimentAnalyzer 출력을 **소비**하여 일자/시간별 sentiment 추이를 `plot_data`에 반영. Sentiment를 직접 분석하지 않음.
- **HandoffGenerator(10)**: SentimentAnalyzer의 `per_utterance_tags`를 Section 8(대화 기반 근거)에서 발화별 감정 태그로 표시.

### 5.3 상태 변화 방향 분류

| Direction | 정의 | 판단 기준 |
|-----------|------|----------|
| `improved` | 이전 대비 호전 | 척도 점수 감소, 기능 손상 완화, 위험 신호 감소, 보호 요인 증가 |
| `worsened` | 이전 대비 악화 | 척도 점수 증가, 기능 손상 심화, 새로운 위험 신호, CTRS level 상승 |
| `unchanged` | 유의미한 변화 없음 | 척도 점수 변동 RCI 기준 미달, 증상 패턴 유지 |
| `unknown` | 판단 불가 | 초진 (이전 데이터 없음), 이전 데이터 불충분, 비교 불가 |

**Evidence 필수 원칙:** 모든 direction 판단에는 반드시 evidence가 연결되어야 한다. evidence 없는 direction 판단은 `unknown`으로 처리한다.

### 5.4 개발 체크리스트

| ID | 항목 | 설명 | 관련 파일 | 우선순위 |
|----|------|------|----------|---------|
| `T1-F4-DEV-001` | TemporalSummary agent 구현 | 현재 세션 정보 + 이전 기록을 비교하여 direction 판단. SentimentAnalyzer(13) 출력을 소비하여 sentiment 추이 반영. | `agents/temporal_summary.py` (신규) | P1 |
| `T1-F4-DEV-002` | TemporalSummary schema 정의 | `TemporalSummaryInput` (current_sentiment, prior_sentiments 입력 포함), `TemporalSummaryOutput` (trend_summary, sentiment_trend, plot_data 포함). | `schemas/temporal_summary.py` (신규) | P1 |
| `T1-F4-DEV-003` | Plot-ready 시계열 데이터 생성 | 날짜별 척도 점수, CTRS level, 주요 이벤트를 시계열 JSON으로 출력. Frontend에서 그래프 렌더링에 직접 사용 가능한 구조. CTRS는 숫자가 낮을수록 위험도가 높음을 명시. | `agents/temporal_summary.py` | P1 |
| `T1-F4-DEV-004` | TemporalSummary prompt 작성 | 종단적 비교 규칙, direction 판단 기준, evidence 필수 원칙. SentimentAnalyzer(13) 출력 소비 규칙 포함. 초진 시 "unknown" 반환 명시. | `prompts/temporal_summary/v1.system.md` | P1 |
| `T1-F1-DEV-011` | SentimentAnalyzer agent 구현 | 발화 단위(Mode A) + 세션 통합(Mode B) 이중 모드. per_utterance_tags 생성. | `agents/sentiment_analyzer.py` (신규) | P1 |
| `T1-F1-DEV-012` | SentimentAnalyzer schema 정의 | `SentimentInput`, `SentimentUtteranceOutput`, `SentimentSessionOutput` 정의. | `schemas/sentiment.py` (신규) | P1 |
| `T1-F1-DEV-013` | SentimentAnalyzer prompt 작성 | 감정 분류 체계, utterance/session 모드 규칙, 한국어 감정 표현 주의사항 포함. | `prompts/sentiment_analyzer/v1.system.md` | P1 |

### 5.5 API 명세

#### POST /ai/temporal/summarize (신규)

**설명:** 현재 세션과 이전 기록을 비교하여 종단적 상태 변화를 요약한다.

**Request Schema:**

```json
{
  "session_id": "string (required)",
  "request_id": "string (optional)",
  "current_session": {
    "conversation_summary": "string",
    "slot_data": {},
    "scale_scores": [
      { "scale_name": "PHQ-9", "total_score": 15, "severity": "moderately_severe", "date": "2026-06-18" }
    ],
    "risk_events": [],
    "ctrs_level": 4
  },
  "previous_records": {
    "prior_handoff_summary": "string (nullable)",
    "prior_scale_scores": [
      { "scale_name": "PHQ-9", "total_score": 8, "severity": "mild", "date": "2026-06-01" }
    ],
    "prior_risk_events": [],
    "prior_ctrs_level": 5,
    "conversation_history_summary": "string (nullable)",
    "medication_changes": []
  },
  "is_first_visit": false
}
```

**Response Schema:**

```json
{
  "model_used": "string",
  "prompt_version": "string",
  "latency_ms": 0.0,
  "trend_summary": {
    "overall_direction": "improved | worsened | unchanged | unknown",
    "domain_trends": [
      {
        "domain": "depression",
        "direction": "worsened",
        "evidence": ["PHQ-9 8 → 15", "의욕 저하 재출현"],
        "confidence": 0.85
      }
    ]
  },
  "new_symptoms": ["수면 저하"],
  "relapse_signals": ["의욕 저하 재출현"],
  "sentiment_signals": {
    "dominant_emotions": ["anxiety", "sadness"],
    "signal_strength": "moderate",
    "evidence_utterances": ["요즘 계속 불안합니다"]
  },
  "plot_data": [
    {
      "date": "2026-06-01",
      "PHQ-9": 8,
      "GAD-7": 6,
      "ctrs_level": 5
    },
    {
      "date": "2026-06-18",
      "PHQ-9": 15,
      "GAD-7": 7,
      "ctrs_level": 4
    }
  ]
}
```

**SLA:**
- p95 < 5,000ms

**Error Codes:**

| HTTP | Code | 설명 |
|------|------|------|
| 500 | `SUMMARY_FAILED` | TemporalSummary LLM 호출 실패 |
| 422 | `INSUFFICIENT_DATA` | 현재 세션 데이터 부족 |

### 5.6 검증 체크리스트

| ID | 항목 | 검증 방법 | Pass 기준 | 관련 VP |
|----|------|----------|-----------|---------|
| `T1-F4-VER-001` | VP-002 호전 감지 테스트 | VP-002 (경증 재진, 이전 대비 호전) context로 호출 | overall_direction = "improved", PHQ-9 감소 evidence 포함 | VP-002 |
| `T1-F4-VER-002` | VP-004 악화 감지 테스트 | VP-004 (중증 재진, 악화 + 약물 비순응) context로 호출 | overall_direction = "worsened", 약물 비순응 evidence 포함 | VP-004 |
| `T1-F4-VER-003` | 초진 "unknown" 테스트 | VP-001 (경증 초진, 이전 기록 없음) context로 호출 | overall_direction = "unknown", previous_records가 비어있을 때 정상 처리 | VP-001 |
| `T1-F4-VER-004` | Plot data 구조 검증 | 재진 시나리오에서 plot_data 생성 확인 | 날짜별 점수 정렬, 필수 필드(date, 최소 1개 척도) 존재, JSON parse 가능 | VP-002, VP-004 |

---

## 6. 기능 1-5: Handoff Report 생성

### 6.1 개요

Agent 01~09의 모든 결과를 통합하여 12-section 구조의 전문가/의료진용 handoff report를 생성한다. Evidence registry를 기반으로 모든 주장에 원문 근거를 인용하며, EvidenceVerifier가 생성된 report를 검증하여 hallucination과 근거 누락을 방지한다.

### 6.2 관련 Agent

| Agent Spec | 역할 | Registry Key | 구현 상태 |
|------------|------|-------------|----------|
| `10_handoff_generator.md` | Handoff report Markdown 생성 | `handoff_generator` | **구현 완료** (개선 필요) |
| `11_evidence_verifier.md` | Evidence 무결성 검증, reject/regenerate 판정 | `evidence_verifier` | **구현 완료** (개선 필요) |

### 6.3 12-Section Report Template

마스터 개발 계획 기능 1-5의 Report 구성을 기준으로, handoff report는 다음 12개 섹션으로 구성된다:

| Section # | 섹션명 | 설명 | 필수 여부 |
|-----------|--------|------|----------|
| 1 | 사용자 기본 정보 | 환자 가명 ID, 나이, 성별, 평가 일시 | 필수 |
| 2 | 입력 source 요약 | 자율 대화, 구조화 문진, STT, OCR, 진료기록, 이전 handoff 등 사용된 source 목록 | 필수 |
| 3 | 현재 주요 호소 | chief_complaint + 주요 증상 표현 | 필수 |
| 4 | 정신건강 영역 후보 | domain_candidates (confidence, evidence 포함) | 필수 |
| 5 | CTRS 기반 위험도 평가 | CTRS level, 위험 근거, 자살/자해/타해/폭력성/환각/공황/물질사용/기능손상 | 필수 |
| 6 | 시행된 구조화 문진 결과 | 척도명, 점수, severity, 시행 일시, 위험 문항 양성 여부 | 조건부 (설문 시행 시 필수) |
| 7 | 기록 기반 근거 | OCR/진료기록/처방기록에서 추출한 진단명, 처방약, 진료과, 검사 결과 | 조건부 (기록 존재 시 필수) |
| 8 | 대화 기반 근거 | 주요 사용자 발화, 반복 표현, 정서 변화, 기능 손상 표현 (원문 인용) | 필수 |
| 9 | 종단적 상태 변화 | 이전 대비 호전/악화/유지, 새로운 증상, 재발 신호, CTRS 변화 | 조건부 (재진 시 필수) |
| 10 | AI 판단의 한계 | 진단 아님 고지, OCR/STT 오류 가능성, RAG 근거 제한 가능성, 전문가 검토 필요 | 필수 |
| 11 | 권장 다음 조치 | 자가관리, 재평가, 전문가 상담, 정신건강의학과 상담 고려, 위기지원 안내 | 필수 |
| 12 | Evidence Registry | 모든 evidence_id와 source의 매핑 테이블 | 필수 |

### 6.4 Evidence 검증 루프

```
HandoffGenerator(10)  ──generate──►  report_markdown + evidence_packets
                                              │
                                              ▼
                                    EvidenceVerifier(11)
                                              │
                                    ┌─────────┼─────────┐
                                    │         │         │
                                  passed   regenerate  reject
                                    │         │         │
                                    ▼         ▼         ▼
                                 return    retry      HTTP 422
                                          (max 2회)
```

현재 구현 (`routes/handoff.py`):
- `_MAX_REGENERATE_ATTEMPTS = 2` (최대 2회 재생성)
- `passed` → 즉시 반환
- `reject` → HTTP 422 반환 (issues 목록 포함)
- `regenerate` 소진 → `requires_human_review = True` 플래그 + warning 메시지 추가 후 반환

### 6.5 개발 체크리스트

| ID | 항목 | 설명 | 관련 파일 | 우선순위 |
|----|------|------|----------|---------|
| `T1-F5-DEV-001` | 12-section template 강제 적용 | HandoffGenerator prompt에 12개 섹션 template을 명시적으로 포함. 누락 섹션 시 EvidenceVerifier에서 reject 판정. 현재 prompt가 11개 섹션만 지정하고 있으므로 Section 12 (Evidence Registry) 추가. | `prompts/handoff_generator/v1.system.md` | P0 |
| `T1-F5-DEV-002` | Evidence registry 생성 강화 | HandoffGenerator가 report 내 모든 `[ev_xxx_nnn]` 인용에 대해 `EvidencePacket`을 생성하도록 prompt 및 후처리 로직 개선. dangling reference (인용은 있으나 evidence_packet 없음) 방지. | `agents/handoff_generator.py`, `prompts/handoff_generator/` | P0 |
| `T1-F5-DEV-003` | EvidenceVerifier 검증 규칙 강화 | 현재 rule-based 검증에 추가: (1) 12-section 완전성 체크, (2) evidence_id dangling reference 체크, (3) 진단 확정 표현 감지, (4) CTRS level과 대응 조치 일치 여부. | `agents/evidence_verifier.py` | P0 |
| `T1-F5-DEV-004` | 종단적 변화 섹션 조건부 렌더링 | `is_first_visit = true`일 때 Section 9를 "해당 없음 (초진)" 으로 처리. 재진일 때 TemporalSummary 출력을 Section 9에 반영. | `agents/handoff_generator.py` | P1 |
| `T1-F5-DEV-005` | Handoff report schema 확장 | `HandoffOutput`에 `section_completeness: dict[str, bool]` (12개 섹션별 포함 여부), `evidence_count: int`, `ctrs_level: int` 필드 추가. | `schemas/handoff.py` | P1 |

### 6.6 API 명세

#### POST /ai/handoff/generate (기존, 수정)

**현재 상태:** `routes/handoff.py`에서 HandoffGenerator → EvidenceVerifier 루프가 구현되어 있음.
**수정 사항:** 12-section template 강제, evidence registry 강화, 종단적 변화 섹션 조건부 처리, CTRS level 필드 추가.

**Request Schema** (기존 `HandoffInput` 확장):

```json
{
  "session_id": "string (required)",
  "request_id": "string (optional)",
  "slots": {
    "chief_complaint": "string",
    "onset": "string",
    "duration": "string",
    "triggers": "string",
    "sleep": "string",
    "appetite": "string",
    "mood": "string",
    "anxiety": "string",
    "concentration": "string",
    "functional_impairment": "string",
    "medication": "string",
    "past_psychiatric_history": "string",
    "risk_factors": "string"
  },
  "conversation_history": [{ "role": "string", "content": "string" }],
  "scale_scores": [
    { "scale_name": "PHQ-9", "total_score": 15, "severity": "moderately_severe" }
  ],
  "risk_events": [{ "type": "string", "evidence": "string", "timestamp": "string" }],
  "ocr_documents": [{ "document_type": "string", "content": "string", "confidence": 0.0 }],
  "prior_handoff": "string (nullable, 이전 handoff report markdown)",
  "is_first_visit": true,
  "temporal_summary": {
    "overall_direction": "string (nullable)",
    "domain_trends": [],
    "plot_data": []
  },
  "domain_candidates": [],
  "ctrs_level": 5
}
```

**Response Schema** (기존 `HandoffOutput` 확장):

```json
{
  "model_used": "string",
  "prompt_version": "string",
  "latency_ms": 0.0,
  "reason_summary": "string",
  "report_markdown": "string (12-section Markdown)",
  "evidence_packets": [
    {
      "evidence_id": "ev_msg_001",
      "source_type": "message | scale | document_block | risk_event | prior_handoff",
      "source_ref": "string",
      "content_summary": "string"
    }
  ],
  "missing_slots": ["medication"],
  "risk_level": "none | low | medium | high | critical",
  "ctrs_level": 5,
  "requires_human_review": false,
  "section_completeness": {
    "section_01_patient_info": true,
    "section_02_input_sources": true,
    "section_03_chief_complaint": true,
    "section_04_domain_candidates": true,
    "section_05_risk_assessment": true,
    "section_06_survey_results": true,
    "section_07_record_evidence": false,
    "section_08_dialogue_evidence": true,
    "section_09_longitudinal": false,
    "section_10_limitations": true,
    "section_11_recommendations": true,
    "section_12_evidence_registry": true
  },
  "evidence_count": 12
}
```

**SLA:**
- p95 < 30,000ms (생성 + 검증 + 재생성 1회 포함)

**Error Codes:**

| HTTP | Code | 설명 |
|------|------|------|
| 500 | `HANDOFF_GENERATION_FAILED` | HandoffGenerator LLM 호출 실패 |
| 422 | `EVIDENCE_VERIFICATION_REJECTED` | EvidenceVerifier가 reject 판정 (issues 목록 포함) |

### 6.7 검증 체크리스트

| ID | 항목 | 검증 방법 | Pass 기준 | 관련 VP |
|----|------|----------|-----------|---------|
| `T1-F5-VER-001` | VP-001 handoff 생성 (경증 초진) | VP-001 전체 파이프라인 실행 후 handoff 생성 | 12-section 중 필수 섹션 모두 존재, evidence >= 3개 | VP-001 |
| `T1-F5-VER-002` | VP-002 handoff 생성 (경증 재진) | VP-002 전체 파이프라인 + prior handoff 주입 | Section 9 종단적 변화 포함, direction evidence 존재 | VP-002 |
| `T1-F5-VER-003` | VP-003 handoff 생성 (중증 초진) | VP-003 (자살 사고) 시나리오 | Section 5 CTRS level 정확, 위기 대응 조치 포함 | VP-003 |
| `T1-F5-VER-004` | VP-004 handoff 생성 (중증 재진) | VP-004 (악화 + 약물 비순응) 시나리오 | 악화 direction, 약물 비순응 기록, CTRS 변화 포함 | VP-004 |
| `T1-F5-VER-005` | V-01~V-12 검증 항목 체크 | EvidenceVerifier의 12개 validation rule 각각에 대해 pass/fail 테스트 | 모든 validation rule이 정상 작동 (true positive + true negative) | - |
| `T1-F5-VER-006` | 12-section 완전성 테스트 | 생성된 report의 section_completeness 확인 | 필수 섹션 (1,2,3,4,5,8,10,11,12) 100% 포함, 조건부 섹션은 조건 충족 시 포함 | VP-001~004 |

---

## 7. API 명세 종합표

| Method | Path | Status | 기능 | 관련 Agent | SLA (p95) | 비고 |
|--------|------|--------|------|-----------|-----------|------|
| POST | `/ai/chat/respond` | 기존 수정 | 자율 대화 (safety gate + dialogue) | 01, 02, 03 | < 2,000ms | Orchestrator 기반 리팩토링 |
| POST | `/ai/safety/classify` | 기존 유지 | Safety 단독 분류 | 02 | < 1,000ms | CTRS level 필드 추가 |
| POST | `/ai/stt/transcribe` | **신규** | 음성 → 텍스트 변환 | 06 (adapter) | < 2,000ms | STT adapter 호출 |
| POST | `/ai/ocr/parse` | **신규** | 문서 이미지 → structured text | 07 (adapter) | < 10,000ms | Upstage Document Parse |
| POST | `/ai/slots/extract` | **신규** | 대화에서 임상 slot 추출 | 04 | < 2,000ms | ClinicalSlot agent |
| POST | `/ai/survey/score` | **신규** | 구조화 설문 채점 | N/A (rule-based) | < 50ms | LLM 미사용 |
| POST | `/ai/temporal/retrieve` | **신규** | 정신건강 영역/진료과 후보 추론 | 08 | < 3,000ms | RAG placeholder |
| POST | `/ai/temporal/summarize` | **신규** | 종단적 상태 변화 요약 | 09 | < 5,000ms | 재진 시 활성화 |
| POST | `/ai/handoff/generate` | 기존 수정 | Handoff report 생성 + 검증 | 10, 11 | < 30,000ms | 12-section template 강제 |

**총 endpoint:** 9개 (기존 수정 3, 신규 6)

---

## 8. DB Schema 요구사항 (Placeholder)

> **이 섹션은 placeholder이다. DB 정보 확정 후 업데이트된다.**

### 8.1 현재 정의된 테이블

`apps/api/src/models/` 기준으로 현재 존재하는 모델:

| 테이블 (모델 파일) | 핵심 컬럼 | 용도 |
|-------------------|----------|------|
| `session.py` | session_id, patient_id, status, created_at, ended_at | 대화 세션 관리 |
| `user.py` | user_id, name, birth_year_month, sex, consent_status | 사용자 프로필 |
| `patient_profile.py` | patient_id, user_id, medical_history, medication_list | 환자 임상 프로필 |
| `handoff.py` | handoff_id, session_id, report_markdown, risk_level, created_at | Handoff report 저장 |
| `questionnaire.py` | questionnaire_id, session_id, scale_name, responses, total_score, severity | 설문 결과 저장 |
| `consent.py` | consent_id, user_id, consent_type, version, status, updated_at | 동의 관리 |
| `audit_log.py` | log_id, event_type, actor_id, payload, created_at | 감사 로그 |

### 8.2 추가 필요 테이블

| 테이블명 (예정) | 핵심 컬럼 | 용도 | 우선순위 |
|----------------|----------|------|---------|
| `ocr_blocks` | block_id, session_id, document_type, block_type, content, confidence, position_json | OCR 결과 블록 단위 저장 | P1 |
| `stt_transcripts` | transcript_id, session_id, vendor, transcript_text, confidence, segments_json, audio_url | STT 변환 결과 저장 | P1 |
| `scale_scores_history` | score_id, patient_id, session_id, scale_name, total_score, severity, critical_item_positive, scored_at | 척도 점수 이력 (종단적 비교용) | P0 |
| `risk_events` | event_id, session_id, ctrs_level, risk_level, categories, flagged_phrases, trigger_source, evidence, created_at | 위험 이벤트 기록 | P0 |
| `rag_embeddings` (pgvector) | embedding_id, content_hash, embedding_vector (vector), source_doc_id, chunk_text, metadata_json | RAG 지식베이스 벡터 저장 | P2 |
| `evidence_registry` | evidence_id, session_id, handoff_id, source_type, source_ref, content_summary | Evidence 추적 | P1 |

### 8.3 pgvector 확장

RAG 파이프라인에 필요한 PostgreSQL pgvector 확장:

```sql
-- placeholder: 실제 설정은 DB 팀과 협의 후 결정
CREATE EXTENSION IF NOT EXISTS vector;

-- embedding 차원은 모델 선택 후 결정 (768, 1024, 1536 등)
-- CREATE TABLE rag_embeddings (
--   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   content_hash TEXT NOT NULL,
--   embedding vector(???),  -- 차원 미정
--   source_doc_id TEXT,
--   chunk_text TEXT,
--   metadata JSONB,
--   created_at TIMESTAMPTZ DEFAULT NOW()
-- );
```

---

## 9. Agent 구성 및 실행 규칙

### 9.1 기능별 Agent 실행 순서

#### 기능 1-1: 자율 대화 기반 문진

```
1. [input_type에 따라]
   - audio → STT(06) → InputNormalizer(05)
   - image → OCR(07) → InputNormalizer(05)
   - text → 직접 진입
2. SafetyClassifier(02) [병렬 실행]
3. [CTRS 1-2] → CrisisFlow (종료)
   [CTRS 3-5] → ContextRetrieval (Orchestrator)
4. Dialogue(03) → 응답 생성 + slot 추출
5. ClinicalSlot(04) → slot 정합성 검증 (optional, batch mode)
```

#### 기능 1-2: RAG 기반 추론

```
1. Orchestrator: context assembly (대화 + slot + OCR + STT + 진료기록 통합)
2. TemporalRetriever(08): unified context → domain/department candidates
```

#### 기능 1-3: 구조화 설문

```
1. Orchestrator: Survey Planner logic (domain_candidates + CTRS → 설문 선택)
2. [설문 UI 수행 — frontend 담당]
3. Survey Scoring module: 응답 → 점수 계산 (rule-based)
4. [critical_item_positive] → SafetyClassifier(02) re-evaluation
```

#### 기능 1-4: 종단적 상태 추론

```
1. TemporalRetriever(08): 이전 기록 검색
2. TemporalSummary(09): 현재 vs 이전 비교 → direction + evidence + plot_data
```

#### 기능 1-5: Handoff Report 생성

```
1. HandoffGenerator(10): 전체 결과 통합 → 12-section report 생성
2. EvidenceVerifier(11): evidence 무결성 검증
3. [passed] → 반환
   [regenerate] → HandoffGenerator 재호출 (max 2회)
   [reject] → HTTP 422
```

### 9.2 Agent 입출력 의존성

```
STT(06) ──► InputNormalizer(05) ──┐
OCR(07) ──► InputNormalizer(05) ──┤
                                   ├──► Orchestrator(01) ──┐
Text input ───────────────────────┘                        │
                                                            ├──► SafetyClassifier(02)
                                                            ├──► Dialogue(03) ──► ClinicalSlot(04)
                                                            ├──► TemporalRetriever(08)
                                                            ├──► Survey Scoring (rule-based)
                                                            ├──► TemporalSummary(09)
                                                            └──► HandoffGenerator(10) ──► EvidenceVerifier(11)
```

### 9.3 agent_model_registry.yaml 관리 규칙

현재 `apps/ai-server/src/routing/agent_model_registry.yaml`에서 agent별 model 매핑을 관리한다.

**관리 규칙:**

1. **새 agent 추가 시** 반드시 registry에 entry를 추가한다. strategy는 `benchmarked` (LLM agent) 또는 `fixed` (single-vendor adapter)를 선택한다.
2. **model 변경 시** registry만 수정한다. agent 코드에 model ID를 하드코딩하지 않는다.
3. **환경변수 참조** 형식: `${ENV_VAR_NAME}`. 실행 시 ModelRouter가 resolve한다.
4. **fallback 체인**: primary → secondary → fallback. primary 실패 시 자동 fallback.
5. **offline agent** (prompt_eval): runtime에 호출되지 않음. batch 평가 전용.

**현재 등록된 agent:**

| Registry Key | Strategy | Primary | Secondary | Fallback |
|---|---|---|---|---|
| `orchestrator` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `safety_classifier` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `dialogue` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `clinical_slot` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `input_normalizer` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `temporal_retriever` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `temporal_summary` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `handoff_generator` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `evidence_verifier` | benchmarked | solar-pro3 | k-exaone | ak-llm |
| `stt_agent` | fixed | skt-ak-stt | - | - |
| `ocr_agent` | fixed | solar-document-parse | - | - |
| `prompt_eval` | offline | - | - | - |

### 9.4 Agent 운영 정책

| 정책 항목 | 기본값 | 설명 |
|----------|--------|------|
| **Timeout** | 30s (LLM agent), 10s (STT), 15s (OCR) | 개별 agent 호출 timeout. 초과 시 fallback 또는 에러 반환 |
| **Retry** | 0회 (LLM agent), 1회 (STT/OCR adapter) | LLM agent는 retry하지 않고 fallback model로 전환. adapter는 1회 retry 후 실패 반환 |
| **Safe Default** | safety_classifier: risk_level=high | Safety 실패 시 보수적 기본값. "안전 확인 불가 → 위험 우선" 원칙 |
| **Circuit Breaker** | 5회 연속 실패 시 30s 동안 해당 adapter 차단 | ModelRouter의 fallback_policy에서 관리 |

### 9.5 Prompt 버전 관리 규칙

**파일 위치:** `docs/ai/prompts/{agent_name}/v{N}.system.md`

**버전 관리 규칙:**

1. 모든 prompt는 `docs/ai/prompts/` 디렉토리에 Markdown 파일로 관리한다.
2. 버전 형식: `v1`, `v2`, `v3` (순차 증가, 소수점 없음).
3. **새 버전 생성 시 기존 버전을 삭제하지 않는다.** 이전 버전은 rollback 및 A/B 테스트를 위해 보존한다.
4. 활성 버전은 `agent_model_registry.yaml` 또는 agent 코드의 `_PROMPT_VERSION` 상수에서 지정한다.
5. Prompt 변경 시 반드시 `docs/ai/eval/` 디렉토리에서 이전 버전과 성능 비교 테스트를 수행한다.
6. 변경 이력은 prompt 파일 상단에 changelog로 기록한다.

**현재 prompt 디렉토리 구조:**

```
docs/ai/prompts/
├── clinical_slot/        # ClinicalSlot agent
├── dialogue/             # Dialogue agent
├── evidence_verifier/    # EvidenceVerifier agent
├── handoff_generator/    # HandoffGenerator agent
├── input_normalizer/     # InputNormalizer agent
├── ocr/                  # OCR 후처리 (InputNormalizer에서 사용)
├── orchestrator/         # Orchestrator agent
├── prompt_eval/          # Prompt 평가 (offline)
├── safety_classifier/    # SafetyClassifier agent
├── stt/                  # STT 후처리 (InputNormalizer에서 사용)
├── temporal_retriever/   # TemporalRetriever agent
└── temporal_summary/     # TemporalSummary agent
```

### 9.6 Agent Spec 변경 프로세스

1. `docs/ai/agents/{NN}_{agent_name}.md` 파일 수정.
2. 변경 사항이 입출력 schema에 영향을 주면 `apps/ai-server/src/schemas/` 의 해당 Pydantic 모델 동시 업데이트.
3. Prompt 변경이 필요하면 새 버전 (`v{N+1}.system.md`) 생성.
4. 관련 테스트 (`T1-Fn-VER-*`) 재실행.
5. 변경 사항을 `docs/ai/eval/reports/` 에 기록.

---

## 10. 가상 환자 Persona 및 Patient LLM 시뮬레이션

### 10.1 4 Persona 개요

| Persona ID | 이름 (가명) | 나이/성별 | 방문 유형 | 핵심 특징 | CTRS Level |
|------------|------------|----------|----------|----------|-----------|
| **VP-001** | 김서연 | 28F | 초진 | 경증 불안 + 수면 문제, 직장 스트레스, 보호 요인 존재 | 5 (안정기) |
| **VP-002** | 이준호 | 35M | 재진 | 6주 전 경도 우울로 첫 방문, Escitalopram 10mg 복용 중, 호전 경향 | 5 (안정기) |
| **VP-003** | 박민수 | 42M | 초진 | 중증 우울 + 수동적 자살 사고, 사회적 고립, 폭음, 보호 요인 약함 | 2-3 (고위험~급성기) |
| **VP-004** | 최하은 | 31F | 재진 | 2개월 전 중등도 우울 치료 시작 후 악화, 공황 발작 신규 발생, 약물 3차 변경 | 3 (급성기, 이전 4→3 악화) |

### 10.2 Patient LLM 시뮬레이션 방법

**핵심 원칙:** Clinical agent들은 Patient LLM의 존재를 인지하지 않는다 (독립성 원칙).

**시뮬레이션 구조:**

```
[Patient LLM]                          [Clinical Pipeline]
                                        
persona system prompt                  실제 clinical agent들
  + clinical profile                     (Orchestrator, Safety,
  + conversation style                    Dialogue, ClinicalSlot, etc.)
  + 이전 기록 (재진 시)
       │                                       │
       │◄──────── assistant 응답 ──────────────┤
       │                                       │
       ├──────── user 발화 (시뮬레이션) ───────►│
       │                                       │
     [8-15턴 반복]                        [실제 pipeline 실행]
```

1. **Patient LLM**: persona를 system prompt로 주입한 LLM이 환자 역할을 수행한다. clinical agent와 동일한 LLM 벤더를 사용할 수 있으나, **별도 세션**으로 실행한다.
2. **독립성 원칙**: Dialogue agent, Safety agent 등 clinical agent는 상대가 LLM이라는 사실을 모른다. 실제 환자와 동일하게 처리한다.
3. **대화 종료 조건**: 8-15턴 도달, 또는 crisis flow 발동, 또는 handoff 준비 완료 중 먼저 충족되는 조건.

### 10.3 재진 환자 데이터 구조

재진 환자 (VP-002, VP-004) 시뮬레이션 시 주입하는 이전 데이터:

```json
{
  "prior_handoff": "이전 handoff report markdown (full text)",
  "conversation_history": [
    { "role": "user", "content": "이전 대화 발화", "session_id": "prev_session" }
  ],
  "medication_records": [
    {
      "name": "Escitalopram 10mg",
      "start_date": "2026-06-04",
      "status": "active | discontinued | non_adherent",
      "prescriber_note": "string"
    }
  ],
  "prior_scale_scores": [
    { "scale_name": "PHQ-9", "total_score": 8, "severity": "mild", "date": "2026-06-04" },
    { "scale_name": "GAD-7", "total_score": 12, "severity": "moderate", "date": "2026-06-04" }
  ],
  "prior_ctrs_level": 5,
  "prior_risk_events": []
}
```

### 10.4 Persona 파일 위치

```
docs/ai/personas/
├── VP-001_first_visit_mild.md   # 김서연 28F - 경증 초진 persona
├── VP-002_revisit_mild.md       # 이준호 35M - 경증 재진 persona (종단 데이터 포함)
├── VP-003_first_visit_severe.md # 박민수 42M - 중증 초진 persona (자살 사고)
├── VP-004_revisit_severe.md     # 최하은 31F - 중증 재진 persona (악화, 약물 변경 이력)
└── _simulation_spec.md          # Patient LLM 시뮬레이션 사양
```

각 persona 파일에는 다음이 포함된다:
- **Demographics**: 나이, 성별, 직업, 가족 구성
- **Clinical Profile**: 주호소, 증상, 기간, 기능 손상, 위험 요인, 보호 요인
- **PHQ-9 / GAD-7 예상 응답**: 시뮬레이션 기준값
- **Conversation Style**: 말투, 응답 길이, 감정 표현 패턴, 회피 주제
- **Simulation Notes**: LLM이 일관된 persona를 유지하기 위한 지시사항

---

## 11. RAG 통합 계획 (Placeholder)

> **이 섹션은 placeholder이다. 정보 확정 후 상세 설계를 업데이트한다.**

### 11.1 Vector Store

- **기술**: pgvector (PostgreSQL 확장)
- **장점**: 기존 PostgreSQL 인프라 활용, 별도 벡터 DB 운영 불필요
- **차원**: embedding model 선택 후 결정

### 11.2 Embedding Model (미정)

후보:
- Upstage Solar Embedding
- OpenAI text-embedding-3-small / large
- 한국어 특화 모델 (KoSimCSE, KoBERT 기반)

**선택 기준**: 한국어 의료 도메인 성능, 차원 수, 비용, latency

### 11.3 Knowledge Base (미정)

정신건강 영역별 지식베이스 구축 필요:
- 정신건강 영역 정의 (우울, 불안, 물질사용, 외상, 수면, 정신증 등)
- 영역별 증상 매핑
- 영역별 권장 구조화 문진 도구 매핑
- 진료과 매핑 규칙
- 출처 및 근거 문서

### 11.4 RAG Governance

마스터 개발 계획 Common Module 5 참조:
- 근거 문서 버전 관리
- 오래된 문서 비활성화
- 검색 결과와 최종 판단 분리 저장
- RAG가 반환한 정보는 진단이 아님
- 근거 문서가 없으면 report에 포함하지 않음
- 의료 DB 정보 최신성 검증 필요

---

## 12. Monitoring 문서 작성 규칙

### 12.1 report.md 작성 규칙

**위치:** `docs/ai/eval/reports/` 또는 프로젝트 루트 `report.md`

**원칙:** Append-only. 각 entry는 체크리스트 ID를 참조한다.

**Format:**

```markdown
## [YYYY-MM-DD] T1-Fn-TYPE-NNN | STATUS

**Summary:** 1-2줄 요약
**Details:**
- 작업 내용 또는 테스트 결과
- pass/fail 결과
- 발견된 이슈

---
```

**STATUS 정의:**

| STATUS | 의미 | 사용 시점 |
|--------|------|----------|
| `DONE` | 완료 | 개발 항목 구현 완료, 검증 항목 통과 |
| `BLOCKED` | 차단됨 | 외부 의존성 (DB, API key, 벤더 계약 등)으로 진행 불가 |
| `ISSUE` | 이슈 발견 | 구현 중 문제 발견, 또는 검증 실패 |
| `NOTE` | 참고 사항 | 설계 결정, 변경 사항, 관찰 내용 기록 |

**검증 결과 기록 시 포함 사항:**
- 테스트 실행 일시
- 사용된 VP (해당 시)
- 테스트 결과 요약 (pass/fail, 정량 수치)
- 발견된 이슈 (있을 경우)
- 관련 로그 또는 artifact 경로

### 12.2 version.md 작성 규칙

**위치:** 프로젝트 루트 `version.md`

**원칙:** 주요 마일스톤 달성 시 버전 범프.

**Format:**

```markdown
## vX.Y (YYYY-MM-DD)

**Scope:** 이번 버전에 포함된 기능 범위
**Changes:**
- 변경 사항 1
- 변경 사항 2

**Completed Checklist IDs:**
- T1-F1-DEV-001, T1-F1-DEV-002, ...
- T1-F1-VER-001, T1-F1-VER-002, ...

**Known Issues:**
- 이슈 1
- 이슈 2

---
```

**버전 체계:**

| 버전 범위 | 의미 | 기준 |
|-----------|------|------|
| `v0.1` ~ `v0.9` | 개발 중 | 개별 기능 구현 진행 중 |
| `v1.0` | 기능 1-1~1-5 전체 통합 완료 | 모든 DEV 항목 완료 + 필수 VER 항목 통과 |
| `v1.x` | 버그 수정 및 개선 | 운영 중 발견된 이슈 해결 |

**마일스톤 예시:**

| 버전 | 마일스톤 | 포함 체크리스트 |
|------|---------|----------------|
| `v0.1` | Safety + Dialogue 기본 flow | T1-F0-*, T1-F1-DEV-001~008 |
| `v0.2` | ClinicalSlot + Survey Scoring | T1-F3-DEV-001~006 |
| `v0.3` | TemporalRetriever + Summary | T1-F2-DEV-001~005, T1-F4-DEV-001~004 |
| `v0.4` | Handoff 12-section + Evidence 강화 | T1-F5-DEV-001~005 |
| `v0.5` | STT + OCR adapter 통합 | T1-F1-DEV-003~004, T1-F1-DEV-009~010 |
| `v0.9` | 전체 통합 테스트 통과 | T1-F*-VER-* |
| `v1.0` | Task 1 전체 완료 | 모든 T1-* 항목 |

---

## 13. CTRS ↔ RiskLevel 매핑

### 13.1 현재 코드의 RiskLevel

`apps/ai-server/src/schemas/common.py`:

```python
class RiskLevel(StrEnum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"
```

### 13.2 마스터 계획의 CTRS

마스터 개발 계획에서 사용하는 CTRS (Crisis Triage Rating Scale):
- CTRS 1단계 = 초응급 (가장 위험)
- CTRS 5단계 = 안정기 (가장 안전)

**주의:** CTRS는 숫자가 **낮을수록 위험도가 높다.** 이는 RiskLevel enum의 직관과 반대 방향이므로 매핑에 주의가 필요하다.

### 13.3 매핑 테이블

| CTRS Level | CTRS 분류 | RiskLevel | 시스템 대응 |
|:---:|---|---|---|
| **1** | 초응급 | `critical` | 일반 대화 즉시 중단, 119/112 안내, 보호자/의료진 긴급 알림, 응급실 이송 권고 |
| **2** | 고위험 | `high` | 일반 대화 제한, 109/119/112 안내, dashboard 긴급 alert, human review 즉시 등록 |
| **3** | 급성기 | `medium` | 위기 개입 안내, 빠른 정신건강의학과 평가 권고, 24-48시간 내 follow-up |
| **4** | 중증/주의 | `low` | 외래 진료/상담 권고, 구조화 문진 실시, human review queue 등록 가능 |
| **5** | 안정기 | `none` | 일반 문진 지속, 외래 예약 안내, 자가관리 및 재평가 계획 |

### 13.4 코드 반영 방안

**결정 필요 사항 → `T1-F0-DEV-002`:**

현재 `RiskLevel` enum에 CTRS 매핑을 추가하는 방법으로 두 가지 선택지가 있다:

**Option A: CTRSLevel enum 별도 추가**

```python
class CTRSLevel(IntEnum):
    """Crisis Triage Rating Scale — 1=most urgent, 5=stable."""
    level_1_emergency = 1
    level_2_high_risk = 2
    level_3_acute = 3
    level_4_moderate = 4
    level_5_stable = 5

CTRS_TO_RISK: dict[CTRSLevel, RiskLevel] = {
    CTRSLevel.level_1_emergency: RiskLevel.critical,
    CTRSLevel.level_2_high_risk: RiskLevel.high,
    CTRSLevel.level_3_acute: RiskLevel.medium,
    CTRSLevel.level_4_moderate: RiskLevel.low,
    CTRSLevel.level_5_stable: RiskLevel.none,
}
```

**Option B: RiskLevel enum에 ctrs_level 속성 추가**

기존 `RiskLevel`을 확장하여 `ctrs_level` property를 부여.

**현재 권장:** Option A. 이유:
1. CTRS는 정신과적 응급 분류 체계로, 일반 risk level과 semantic이 다르다.
2. 명시적 매핑 테이블로 두 체계 간 변환을 제어할 수 있다.
3. 향후 CTRS 세부 분류 (예: CTRS 2a/2b) 확장에 유연하다.

### 13.5 공통 개발 체크리스트

| ID | 항목 | 설명 | 관련 파일 | 우선순위 |
|----|------|------|----------|---------|
| `T1-F0-DEV-001` | BaseAgent 상속 구조 검증 | 모든 신규 agent가 `BaseAgent`를 상속하고 `agent_name` property + `run()` method를 구현하는지 확인. 기존 `SafetyClassifierAgent`, `HandoffGeneratorAgent`, `EvidenceVerifierAgent` 패턴 준수. | `agents/base.py` | P0 |
| `T1-F0-DEV-002` | CTRSLevel enum 추가 | `CTRSLevel` IntEnum 정의 + `CTRS_TO_RISK` 매핑 테이블 추가. `SafetyOutput`에 `ctrs_level: int` 필드 추가. | `schemas/common.py`, `schemas/safety.py` | P0 |
| `T1-F0-DEV-003` | 신규 route 등록 | `/ai/stt/transcribe`, `/ai/ocr/parse`, `/ai/slots/extract`, `/ai/survey/score`, `/ai/temporal/retrieve`, `/ai/temporal/summarize` 6개 신규 endpoint를 `main.py`에 등록. | `routes/stt.py`, `routes/ocr.py`, `routes/slots.py`, `routes/survey.py`, `routes/temporal.py` (신규), `main.py` | P0 |
| `T1-F0-CFG-001` | agent_model_registry.yaml 검증 | 모든 agent가 registry에 등록되어 있고 adapter 참조가 유효한지 검증. 신규 agent (orchestrator, clinical_slot, input_normalizer, temporal_retriever, temporal_summary) 확인. | `routing/agent_model_registry.yaml` | P0 |
| `T1-F0-CFG-002` | 환경변수 정리 | 필수 환경변수 목록 정리: `UPSTAGE_API_KEY`, `LG_K_EXAONE_API_KEY`, `LG_K_EXAONE_ENDPOINT_ID`, `SKT_A_X_STT_STREAMING_MODEL` 등. `.env.example` 업데이트. | `.env.example` | P1 |
| `T1-F0-DOC-001` | Agent spec 최신화 | 12개 agent spec 파일이 현재 코드 구현과 일치하는지 검토 및 업데이트. | `docs/ai/agents/` | P1 |

---

## 부록 A. 전체 체크리스트 요약

### 개발 항목 (DEV)

| ID | 기능 | 항목 | 우선순위 |
|----|------|------|---------|
| T1-F0-DEV-001 | 공통 | BaseAgent 상속 구조 검증 | P0 |
| T1-F0-DEV-002 | 공통 | CTRSLevel enum 추가 | P0 |
| T1-F0-DEV-003 | 공통 | 신규 route 등록 (6개) | P0 |
| T1-F1-DEV-001 | F1 | Orchestrator 상태 머신 구현 | P0 |
| T1-F1-DEV-002 | F1 | InputNormalizer agent 구현 | P1 |
| T1-F1-DEV-003 | F1 | STT adapter 구현 | P1 |
| T1-F1-DEV-004 | F1 | OCR adapter 구현 | P1 |
| T1-F1-DEV-005 | F1 | Dialogue slot tracking 고도화 | P0 |
| T1-F1-DEV-006 | F1 | Safety CTRS 매핑 통합 | P0 |
| T1-F1-DEV-007 | F1 | Chat route 리팩토링 | P0 |
| T1-F1-DEV-008 | F1 | SafetyClassifier 위기 응답 고도화 | P0 |
| T1-F1-DEV-009 | F1 | STT confidence threshold 로직 | P1 |
| T1-F1-DEV-010 | F1 | OCR 후처리 파이프라인 | P1 |
| T1-F2-DEV-001 | F2 | TemporalRetriever agent 구현 | P0 |
| T1-F2-DEV-002 | F2 | TemporalRetriever schema 정의 | P0 |
| T1-F2-DEV-003 | F2 | Orchestrator context assembly | P0 |
| T1-F2-DEV-004 | F2 | RAG retrieval stub | P2 |
| T1-F2-DEV-005 | F2 | TemporalRetriever prompt 작성 | P0 |
| T1-F3-DEV-001 | F3 | ClinicalSlot agent 구현 | P0 |
| T1-F3-DEV-002 | F3 | ClinicalSlot schema 정의 | P0 |
| T1-F3-DEV-003 | F3 | Survey Scoring module 구현 | P0 |
| T1-F3-DEV-004 | F3 | Survey Planner routing logic | P1 |
| T1-F3-DEV-005 | F3 | ClinicalSlot prompt 작성 | P0 |
| T1-F3-DEV-006 | F3 | 위험 문항 Safety 전달 로직 | P0 |
| T1-F4-DEV-001 | F4 | TemporalSummary agent 구현 | P1 |
| T1-F4-DEV-002 | F4 | TemporalSummary schema 정의 | P1 |
| T1-F4-DEV-003 | F4 | Plot-ready 시계열 데이터 생성 | P1 |
| T1-F4-DEV-004 | F4 | TemporalSummary prompt 작성 | P1 |
| T1-F5-DEV-001 | F5 | 12-section template 강제 적용 | P0 |
| T1-F5-DEV-002 | F5 | Evidence registry 생성 강화 | P0 |
| T1-F5-DEV-003 | F5 | EvidenceVerifier 검증 규칙 강화 | P0 |
| T1-F5-DEV-004 | F5 | 종단적 변화 섹션 조건부 렌더링 | P1 |
| T1-F5-DEV-005 | F5 | Handoff report schema 확장 | P1 |

**총 DEV 항목:** 33개 (P0: 20개, P1: 11개, P2: 2개)

### 검증 항목 (VER)

| ID | 기능 | 항목 | 관련 VP |
|----|------|------|---------|
| T1-F1-VER-001 | F1 | Dialogue 시뮬레이션 (경증 초진) | VP-001 |
| T1-F1-VER-002 | F1 | Dialogue 시뮬레이션 (경증 재진) | VP-002 |
| T1-F1-VER-003 | F1 | 중증 대화 시뮬레이션 | VP-003 |
| T1-F1-VER-004 | F1 | CTRS crisis bypass 테스트 | VP-003 |
| T1-F1-VER-005 | F1 | STT 정규화 정확도 | - |
| T1-F1-VER-006 | F1 | OCR 파싱 정확도 | - |
| T1-F1-VER-007 | F1 | Slot 수집 수렴 테스트 | VP-001, VP-003 |
| T1-F1-VER-008 | F1 | Safety + Dialogue 병렬 실행 latency | - |
| T1-F2-VER-001 | F2 | VP-002 retrieval 테스트 (재진) | VP-002 |
| T1-F2-VER-002 | F2 | VP-004 retrieval 테스트 (중증 재진) | VP-004 |
| T1-F2-VER-003 | F2 | 초진 empty retrieval 테스트 | VP-001 |
| T1-F2-VER-004 | F2 | 영역 후보 ranking 정확도 | - |
| T1-F3-VER-001 | F3 | PHQ-9 scoring unit test | - |
| T1-F3-VER-002 | F3 | GAD-7 scoring unit test | - |
| T1-F3-VER-003 | F3 | PHQ-4 subscale test | - |
| T1-F3-VER-004 | F3 | WHO-5 / AUDIT-C scoring test | - |
| T1-F3-VER-005 | F3 | Slot extraction 정확도 | VP-001~004 |
| T1-F4-VER-001 | F4 | VP-002 호전 감지 테스트 | VP-002 |
| T1-F4-VER-002 | F4 | VP-004 악화 감지 테스트 | VP-004 |
| T1-F4-VER-003 | F4 | 초진 "unknown" 테스트 | VP-001 |
| T1-F4-VER-004 | F4 | Plot data 구조 검증 | VP-002, VP-004 |
| T1-F5-VER-001 | F5 | VP-001 handoff 생성 (경증 초진) | VP-001 |
| T1-F5-VER-002 | F5 | VP-002 handoff 생성 (경증 재진) | VP-002 |
| T1-F5-VER-003 | F5 | VP-003 handoff 생성 (중증 초진) | VP-003 |
| T1-F5-VER-004 | F5 | VP-004 handoff 생성 (중증 재진) | VP-004 |
| T1-F5-VER-005 | F5 | V-01~V-12 검증 항목 체크 | - |
| T1-F5-VER-006 | F5 | 12-section 완전성 테스트 | VP-001~004 |

**총 VER 항목:** 27개

### 설정 항목 (CFG)

| ID | 항목 |
|----|------|
| T1-F0-CFG-001 | agent_model_registry.yaml 검증 |
| T1-F0-CFG-002 | 환경변수 정리 |

**총 CFG 항목:** 2개

### 문서 항목 (DOC)

| ID | 항목 |
|----|------|
| T1-F0-DOC-001 | Agent spec 최신화 |

**총 DOC 항목:** 1개

---

## 부록 B. 용어 정의

| 용어 | 정의 |
|------|------|
| **CTRS** | Crisis Triage Rating Scale. 정신과적 응급 위험도 분류 체계. 1단계(초응급)~5단계(안정기). |
| **RiskLevel** | 코드베이스에서 사용하는 위험도 enum. none/low/medium/high/critical. |
| **Handoff Report** | AI가 생성한 사전문진 보고서. 전문가/의료진에게 환자 상태를 전달하기 위한 구조화 문서. |
| **Slot** | 임상 문진에서 수집해야 하는 정보 항목 (예: chief_complaint, onset, medication 등). |
| **Evidence Packet** | 하나의 임상 주장과 그 원문 출처를 연결하는 데이터 구조. |
| **Patient LLM** | 가상 환자 persona를 system prompt로 주입하여 환자 역할을 수행하는 LLM 인스턴스. |
| **VP** | Virtual Patient. 가상 환자 persona 식별자 (VP-001 ~ VP-004). |
| **Survey Scoring** | 구조화 설문 (PHQ-9, GAD-7 등)의 rule-based 점수 계산. LLM을 사용하지 않음. |
| **pgvector** | PostgreSQL 벡터 유사도 검색 확장. RAG 파이프라인의 vector store로 사용 예정. |
| **Direction** | 종단적 상태 변화 방향. improved/worsened/unchanged/unknown. |
| **crisis flow** | CTRS 1-2 감지 시 발동되는 위기 대응 흐름. 일반 대화 중단, 위기 안내, 의료진 알림. |

---

*End of Document*
