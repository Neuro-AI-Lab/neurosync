# Agent 14: Mental-Health Domain Inference Agent (DomainInferenceAgent)

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `14` |
| **Agent Name** | `DomainInferenceAgent` |
| **역할** | RAG 기반 정신건강 영역(domain)/진료과(department) 후보 추론 |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |
| **파이프라인 상태** | Standalone. Orchestrator(01) 11-state 머신에 미연결(`routes/domain.py:1-8`). G-D 게이트가 프로덕션 통합의 전제조건 |
| **인증 상태** | ADR-015 — `llm_only` 경로 인증(조건부), RAG 경로 EXPERIMENTAL (아래 "인증 상태" 절 참조) |

## 목적

수집된 임상 슬롯(F1 `final_slots`)과, 있는 경우 검색된 근거를 바탕으로 정신건강 영역 후보(최대 3개)와 진료과 후보를 제시한다. 환자 대면 응답을 생성하지 않으며 진단을 확정하지 않는다. **위험 관련 표현은 이 에이전트가 산출하는 domain confidence의 근거로 사용되지 않는다** — 위험 판정은 SafetyClassifier(02)의 소관이며, 이 규칙은 프롬프트 문구뿐 아니라 코드 레벨에서도 강제된다(아래 "근거 검증 4계층 방어선" 참조).

이 에이전트는 2단계(Stage) 파이프라인 중 **Stage 2(LLM 1회 호출)만** 담당한다. Stage 1(코드 레벨 검색)은 호출자의 책임이며, 검증 하네스인 `apps/ai-server/src/f2.py`가 두 단계를 조립한다(`domain_inference.py:1-11`).

## 2단계 아키텍처

```
F1 conversation.json (final_slots, turns, session_ctrs, ...)
    │
    ▼
[Stage 1] 코드 레벨 검색 (f2.py::run_stage1, rag/retrieval.py 재사용)
    │   chief_complaint/HPI/risk_assessment 슬롯 → retrieve_domain_chunks()
    │   --no-rag 플래그 / 빈 쿼리 / DB·임베딩 예외 → mode="llm_only"로 강등
    │   (never raises — 상위 호출자에 항상 (mode, chunks) 튜플 반환)
    ▼
[Stage 2] LLM 1회 호출 (DomainInferenceAgent.run, 이 문서의 대상)
    │   ModelRouter: primary → 실패 시 fallback 1단계만 시도
    │   파싱/전송 실패 → 빈 domain_candidates + reason_summary (never crashes)
    ▼
[근거 검증] f2_grounding.filter_domain_candidates (f2.py 하네스 경유 시에만 적용)
    │   source-id 화이트리스트 + quote 어휘 대조 + 위험-어휘 필터
    │   → 거부된 evidence 제거, evidence 0개된 후보는 통째로 탈락
    ▼
산출물 (JSON + report.md, post-cascade 후보 + filter_summary + repro 메타)
```

### Stage 1: 코드 레벨 검색 (`f2.py::run_stage1`)

`retrieve_domain_chunks`(`src/rag/retrieval.py`)를 재사용한다. `chief_complaint`, `history_of_present_illness`, `risk_assessment` 세 슬롯의 값만 쿼리로 사용한다(`f2.py:58` `_STAGE1_QUERY_SLOTS`).

| 조건 | 결과 |
|---|---|
| `--no-rag` 플래그 | 즉시 `mode="llm_only"`, 빈 chunk 목록 |
| 세 쿼리 슬롯이 모두 비어있음 | `mode="llm_only"`, 빈 chunk 목록 |
| DB 연결/임베딩 등 Stage-1 예외 | `mode="llm_only"`로 강등, 예외를 삼키고 로그만 남김 (`f2.py:139-171`) |
| 정상 검색 | `mode="rag"`, `chunk_id` + 본문 텍스트 포함 chunk 목록 |

Stage 1은 **어떤 경우에도 예외를 상위로 전파하지 않는다** — 실패는 항상 `llm_only` 강등으로 흡수된다(`f2.py:142-144` docstring).

### Stage 2: LLM 후보 생성 (`agents/domain_inference.py::DomainInferenceAgent.run`)

ModelRouter로 primary 모델을 호출하고, 실패 시 fallback 1단계를 시도한다(`domain_inference.py:145-249`). 두 시도 모두 실패하거나 응답 JSON 파싱/스키마 검증에 실패하면 **빈 `domain_candidates` + `reason_summary`에 사유를 담아 반환한다 — 절대 크래시하지 않는다**(`domain_inference.py:196-202`, `217-224`, `229-237`).

## 입력 (`DomainInferenceInput`, `schemas/domain_inference.py:105-122`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `final_slots` | `dict[str, str]` | F1 최종 슬롯(12-key, flat) |
| `session_ctrs` | `int (1-5)` | 현재 세션 CTRS level — **참고용, evidence 근거로 사용 금지** |
| `crisis_triggered` | `bool` | Safety 위기 트리거 여부 — 참고용 |
| `crisis_turn` | `int \| null` | 위기 트리거 턴 번호 |
| `is_first_visit` | `bool` | 초진/재진 여부 |
| `turns` | `list[UtteranceTurn]` | F1 환자 발화(turn + patient_message) |
| `prior_handoff` | `string \| null` | 이전 handoff 요약(참고용) |
| `probe_events` | `list[dict]` | Safety probe 이벤트 |
| `scale_scores` | `list[ScaleScore]` | 구조화 척도 점수(1-5) |
| `retrieved_chunks` | `list[RetrievedChunk]` | Stage 1 산출물 — 호출 전 조립되어 전달됨 |
| `retrieval_mode` | `"rag" \| "llm_only"` | Stage 1 결과 모드 |
| `queries` | `list[string]` | Stage 1에 사용된 쿼리 원문 |

## 출력 (`DomainInferenceOutput`, `schemas/domain_inference.py:125-132`)

```json
{
  "session_id": "sess_20260618_001",
  "model_used": "solar-pro3",
  "prompt_version": "v2",
  "latency_ms": 0.0,
  "reason_summary": "domain/department candidates generated",
  "domain_candidates": [
    {
      "domain": "anxiety",
      "confidence": 0.0,
      "evidence": [
        {
          "source_type": "utterance",
          "source_id": "turn_3",
          "quote": "<원문 발화에서 실제로 확인되는 인용>"
        }
      ],
      "recommended_surveys": ["GAD-7"]
    }
  ],
  "department_candidates": [
    { "department": "정신건강의학과", "reason": "<근거 요약>", "domain_ref": "anxiety" }
  ],
  "summary": "<evidence 범위 내 요약>",
  "retrieval_meta": {
    "mode": "llm_only",
    "chunks_returned": 0,
    "chunk_ids": [],
    "queries": ["<Stage 1에 사용된 쿼리>"]
  },
  "additional_questions": ["<추가 확인 질문>"]
}
```

| 필드 | 설명 |
|---|---|
| `domain_candidates` | 최대 3개(`max_length=3`). 각 candidate는 evidence를 최소 1개 가져야 함(`min_length=1`) — "근거 없으면 후보 없음" |
| `domain` | Literal 8종: `anxiety \| depression \| alcohol \| substance \| trauma \| sleep \| psychosis \| other` |
| `department_candidates` | `domain_ref`는 생략되거나 `domain_candidates` 중 실제 존재하는 값이어야 함(고아 참조는 검증 대상) |
| `retrieval_meta` | Stage 1 결과를 항상 정직하게 반영(강등되었으면 `mode="llm_only"`로 보고, 은폐하지 않음) |

## 근거 검증 4계층 방어선

Stage 2의 LLM 출력이 산출물에 반영되기까지 네 겹의 독립적 검증을 거친다:

1. **Pydantic 스키마 경계** — `DomainCandidate.evidence`는 `min_length=1`, `domain_candidates`는 `max_length=3`. 스키마 자체가 "근거 없는 후보"와 "3개 초과 후보"를 원천 차단한다(`schemas/domain_inference.py:40-51, 68, 128`).
2. **`f2_grounding.check_evidence`** — evidence 항목별로 (a) `source_id`가 이번 실행에서 실제로 제공된 chunk_id/turn_id인지(화이트리스트), (b) `quote`가 해당 source의 실제 텍스트에서 어휘적으로 뒷받침되는지, (c) `quote`에 위험-어휘가 포함되어 있지 않은지를 순서대로 검사한다(`f2_grounding.py:227-305`). 위험-어휘 검사는 어휘 대조보다 먼저 수행된다.
3. **거부 캐스케이드 (`filter_domain_candidates`)** — 거부된 evidence 항목은 candidate에서 제거되고, accepted evidence가 0개가 된 candidate는 산출물에서 완전히 탈락한다(`f2_grounding.py:337-398`, ADR-014).
4. **`filter_summary` 감사 델타** — `f2.py` 하네스가 cascade 전/후 candidate 수, 탈락한 domain 목록, 제거된 evidence 수(위험-어휘 사유 별도 집계)를 산출물에 기록한다(`f2.py:250-275`).

**이 4계층은 `src/f2.py` 검증 하네스를 경유할 때만 전부 적용된다.** `POST /ai/domain/infer` 라우트 단독 호출은 계층 1-2만 거치며(스키마 + 라우트 핸들러 예외 처리), 3-4(캐스케이드 + 감사 델타)는 하네스 전용이다 — 아래 "API 라우트" 절 참조.

### 위험-어휘 필터 (`f2_grounding._RISK_PHRASES`, ADR-014 코드 강제)

프롬프트 v1의 절대 규칙 2("위험 표현을 domain confidence의 근거로 사용하지 않는다")가 프롬프트 문구만으로는 라이브에서 지켜지지 않음이 확인되어(VAL-006/REV-008), v2부터 코드 레벨 강제 필터를 추가했다. 자살/자해/죽음-지향 SI-class 다단어 표현을 담은 quote는 소스 정당성이나 어휘적 근거와 무관하게 기계적으로 거부된다.

- `_RISK_PHRASES` 리스트는 `f2_grounding.py:87-152`에 정의되어 있으며, 확인 결과 (스페이스 유무 변형을 포함해) 37개 다단어 stem으로 구성된다.
- 모두 다단어(multi-word) 구성이다 — 단독 명사(예: 과거 버전의 "손목", "목숨")는 무관한 임상 발화를 과잉 거부한 이력이 있어(BUG-015) 제거되었다.
- **공황 관용구 carve-out**: "죽는 줄 알았", "죽을 것 같" 등 공황발작의 죽음-공포 관용구(`_PANIC_IDIOM_PHRASES`, ISS-046/SM-07a)는 위험-어휘 리스트와 **구조적으로 disjoint**하도록 별도 구성되어 있다 — 런타임 예외 처리가 아니라 리스트 자체가 겹치지 않게 설계되어 있으며, `tests/test_f2_grounding.py::test_risk_and_panic_idiom_lexicons_are_disjoint`가 이를 assert한다(`f2_grounding.py:154-176`).

| Verdict | 의미 |
|---|---|
| `accepted` | 통과 |
| `rejected_unknown_source` | source_id가 이번 실행에서 제공되지 않음 |
| `rejected_quote_mismatch` | quote가 source 텍스트에서 어휘적으로 뒷받침되지 않음 |
| `rejected_unknown_source_type` | `rag_chunk`/`utterance` 외 값 |
| `rejected_risk_lexicon` | quote에 위험-어휘 stem 포함 |

## 프롬프트 pin

현재 라이브 pin은 **v2**(`domain_inference.py:41`, `docs/ai/prompts/domain_inference/v2.system.md`). v1은 롤백 대비용으로 디스크에 유지된다. v2 시스템 프롬프트 파일은 문자 수 기준 2,948자로 확인됨(UTF-8 바이트 수 5,004와는 별개 단위 — 파일 크기를 볼 때 혼동 주의).

**절대 규칙 5개**(다른 모든 지시보다 우선, `v2.system.md:23-41`):

| 번호 | 규칙 요지 |
|---|---|
| 1 | 진단하지 않는다 — 영역/진료과는 항상 "후보" |
| 2 | 위험 표현을 domain confidence 근거로 사용하지 않는다(코드 강제 명시, 공황 관용구 예외) |
| 3 | 근거 없는 후보 금지(evidence 최소 1개) |
| 4 | 인용은 실제로 주어진 source_id/quote에서만 |
| 5 | 지정된 출력 필드 외 아무것도 출력하지 않는다 |

## 라우팅

benchmarked (`routing/agent_model_registry.yaml:194-210`) — Primary: `solar-pro3`, Secondary: `k-exaone`, Fallback: `ak-llm`(A.X-K1). 다른 benchmarked 에이전트와 동일한 3-tier 구성이며, 벤치마크를 거쳐 확정된 라우팅이다.

## API 라우트

`POST /ai/domain/infer` (`routes/domain.py:36-60`) — **standalone 라우트다. Orchestrator(01)의 11-state 머신에 연결되어 있지 않다.** 이 라우트는 Stage 2(LLM 후보 생성)만 노출한다 — Stage 1 검색과 근거 화이트리스트 감사(위 4계층 방어선의 3-4단계)는 라우트가 아니라 `src/f2.py` 검증 하네스의 책임이다. **fabrication-0 보장이 필요한 호출자는 이 라우트를 단독으로 사용해서는 안 되며, `f2.py` 하네스를 경유해야 한다**(`routes/domain.py:1-8` 명시).

## 인증 상태 (ADR-015)

REV-010(critic, EXP-005 전수 재감사) 채택 결과, 비인증 범위가 부분적으로 해제되었다:

| 경로 | 상태 | 조건 |
|---|---|---|
| `llm_only` arm | **인증(certified)** | 매 라이브 배치에 대한 상시 수동 taxonomy 감사 필요(어휘 필터는 구조적으로 불완전하다는 전제) |
| RAG arm | **EXPERIMENTAL(비인증 유지)** | 인증 경로: BUG-016/BUG-017 수정 → VP-003 RAG n≥2 클린 재검증 → VAL-010(위험-편향 쿼리) 완화의 상시화 |

이 인증 판정은 ADR-014의 특정 질문(위험≠도메인 규칙 준수 여부)에 국한되며, 그 자체로 프로덕션 통합(orchestrator.py 연동)을 승인하지 않는다 — 프로덕션 통합은 별도 전제조건(스키마 통합, orchestrator.py 배선)에 묶인 G-D 게이트 소관이다.

## 알려진 결함

| ID | 요지 | 심각도 | 상태 |
|---|---|---|---|
| BUG-016 | `domain_inference.py:75,77`의 프롬프트 문구("chunk_id=" 라벨)를 모델이 `source_id`에 그대로 echo하는 경우가 있어, `f2_grounding.py:247-254`의 정확-일치 조회가 실패 → 실제로는 유효한 `rag_chunk` evidence가 `rejected_unknown_source`로 과잉 거부됨. 방향은 보수적(허위 근거 채택이 아닌 정당한 근거의 누락)이며 위험은 evidence가 이 항목 하나뿐인 candidate가 캐스케이드로 통째 탈락할 수 있다는 점 | major | **resolved** — 코드 레벨 정규화(`_normalize_rag_chunk_source_id`) 라이브 확인(n=32, 0/32 과잉거부, `EXP-006`) |
| BUG-017 | RAG 모드 LLM 출력이 파싱/스키마 검증에 실패하는 사례(`domain_inference.py:117-123` 파싱, `:128-143` `_call`) — `max_tokens=1536` 고정값이 RAG 모드의 더 긴 프롬프트에서 절단을 유발했을 가능성이 유력 가설이나, `finish_reason`/`usage`가 로그·출력 스키마 어디에도 기록되지 않아 현재 아티팩트만으로는 확증/반증이 불가능함 | major | 진단된 절단 메커니즘은 해소(`max_tokens` 1536→4096, `finish_reason="length"` 0/16 post-fix) — 실질 증상은 `BUG-019`로 잔존, BUG 자체는 open |
| BUG-019 | `RetrievedChunk.source_type`(DB 테이블 출처: `case_card`/`qa`)와 `DomainEvidence.source_type`(스키마 provenance enum: `rag_chunk`/`utterance`)가 필드명을 공유해, 프롬프트의 청크 나열 형식이 모델에게 이를 시각적으로 혼동시킴 — `qa`-테이블 청크를 인용할 때 간헐적으로 `source_type`에 `qa`/`qa:NNN` 같은 잘못된 값이 채워져 schema validation 실패(`finish_reason=stop`, 절단 아님, `BUG-017`과 별개 메커니즘) | major | **근본원인 진단·수정·코드검증 완료**(`EXP-007` 라이브 진단, `_normalize_source_type_collision`, qa `GATE:PASS`) — 라이브 clean VP-003/VP-001 RAG n=2 재검증 미실시로 **open 유지** |

세 결함 모두 실패 시 빈 출력 또는 evidence 탈락으로 **보수적으로(fabrication 방향이 아닌 방향으로) 저하**되며, 크래시나 허위 근거 채택을 유발하지 않는다(위 "Stage 2" 절의 never-crash 설계와 일치).

## AI 예상질환(AI-predicted-disease) 엔티티 — 별도 컨테이너, sibling key (PLAN-2026-W28-H Track B, 2026-07-09)

이 에이전트(14)의 RAG top-5 disease 후보를 기반으로 하는 새 비진단·비임상 필드다. `f2.py`가 이를 기존 `domain_candidates` 출력에 **병합하지 않고** sibling key로 배선한다 — 즉 F2 산출물에 나란히 존재하는 별개 컨테이너다.

- **스키마:** `AIPredictedDiseaseCandidate`(disease + `similarity_score`) 목록 + `AIPredictedDiseaseOutput`(`is_diagnostic: Literal[False]`, 고정 `disclaimer_ko`).
- **라벨링(`REV-013` §4, binding):** `similarity_score`("유사도 점수") 외 라벨 금지(`probability`/`확률`/`가능성(%)`/`confidence` 전부 금지). top-5 간 softmax 정규화 없음.
- **구조적 격리:** 04(`ClinicalSlotAgent`)의 12개 슬롯이나 `HandoffInput`의 어떤 typed field에도 병합되지 않는다 — qa의 9-테스트 adversarial suite(`tests/test_hpi_isolation.py`)가 `AgentInput.extra`/`state.conversation_history` 두 채널을 포함해 이를 확인했다(`REV-013` §3 조건 1 충족). 상세: `docs/ai/agents/04_clinical_slot.md`.
- **상태:** 컨테이너만 구축됨(`mode="experimental_unpopulated"`) — 라이브 실채움은 이 에이전트의 RAG-arm 인증(아래 "인증 상태" 절)에 게이트된다. RAG arm이 EXPERIMENTAL/UNCERTIFIED로 잔류하는 한 실채움 대상 라이브 데이터가 없다.
- 근거: `discussion.md` PLAN-2026-W28-H Track B, REV-013 §3/§4; `error.md` BUG-019 "Track B" subsection; `development_report.md` DR-010 §3.

## 핵심 동작

1. **2단계 분리**: Stage 1(코드 검색)과 Stage 2(LLM 1회)는 서로 다른 실행 단위다. 이 에이전트 클래스는 Stage 2만 구현한다.
2. **위험≠도메인 이중 강제**: 프롬프트 절대 규칙 2 + 코드 레벨 위험-어휘 필터. 프롬프트 문구 단독 강제는 이전 버전(v1)에서 라이브 위반이 확인되었다(VAL-006/REV-008).
3. **근거 없는 후보 미출력**: 스키마(`min_length=1`) + 캐스케이드(0개 남으면 탈락) 이중 보장.
4. **정직한 강등 보고**: Stage 1이 `llm_only`로 강등되어도 `retrieval_meta.mode`는 실제 값을 그대로 보고한다 — RAG로 위장 보고하지 않는다.
5. **Never-crash 원칙**: Stage 1/Stage 2 모두 실패를 삼키고 명시적 사유와 함께 저하된 출력을 반환한다. 예외를 상위로 전파하지 않는다(라우트 핸들러의 500 응답은 별개 — 에이전트 내부 로직 자체는 크래시하지 않는다는 의미).

## 안전 제약

1. **AI는 진단하지 않는다.** domain/department는 항상 "후보"로만 제시하며 확정 진단을 산출하지 않는다.
2. **위험 표현은 domain evidence로 사용하지 않는다.** 프롬프트 규칙과 코드 레벨 필터(`f2_grounding.check_evidence`) 이중 강제. Safety 판정을 대체하거나 우회하지 않는다.
3. **화이트리스트 미통과 근거는 산출물에 남지 않는다.** source_id/quote가 실제 제공 자료와 일치하지 않으면 거부되고, evidence가 소진된 후보는 산출물에서 제거된다.
4. **standalone 라우트의 한계를 명시한다.** `POST /ai/domain/infer`를 단독 호출하는 경우 캐스케이드/감사 델타가 적용되지 않는다는 점을 호출자에게 알려야 한다.
5. **RAG arm은 EXPERIMENTAL이다.** ADR-015 조건 충족 전까지 RAG 경로의 결과를 인증된 것으로 취급하지 않는다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| Stage 1 DB/임베딩 실패 | `mode="llm_only"`로 강등, 예외를 삼키고 로그만 기록. Stage 2는 정상 진행 |
| Stage 2 LLM primary 실패 | fallback 1단계 시도 |
| Stage 2 primary+fallback 모두 실패 | 빈 `domain_candidates` + `reason_summary`에 사유 기록. 크래시하지 않음 |
| LLM 응답 JSON 파싱/스키마 검증 실패 | 빈 `domain_candidates` + `reason_summary`에 파싱 실패 사유 기록 |
| evidence 화이트리스트 전량 거부 | 해당 candidate가 산출물에서 탈락(다른 candidate에는 영향 없음) |
| 라우트 레벨 미처리 예외 | HTTP 500, "Domain inference failed" (`routes/domain.py:52-54`) |

## 관련 파일

| 파일 | 위치 |
|---|---|
| 에이전트 구현 | `apps/ai-server/src/agents/domain_inference.py` |
| 스키마 | `apps/ai-server/src/schemas/domain_inference.py` |
| 검증 하네스 | `apps/ai-server/src/f2.py` |
| 근거 화이트리스트/위험-어휘 필터 | `apps/ai-server/src/eval/f2_grounding.py` |
| Stage 1 검색 프리미티브 | `apps/ai-server/src/rag/retrieval.py` (`retrieve_domain_chunks`) |
| API 라우트 | `apps/ai-server/src/routes/domain.py` |
| 시스템 프롬프트 | `docs/ai/prompts/domain_inference/v1.system.md`(롤백 대비), `v2.system.md`(라이브) |
| 라우팅 설정 | `apps/ai-server/src/routing/agent_model_registry.yaml` (`domain_inference` 항목) |
| 관련 결정/리뷰 | ADR-014, ADR-015, ADR-016, ADR-017, REV-006/007/008/009/010/011/012/013, VAL-006, VAL-010, BUG-016(resolved), BUG-017(open), BUG-019(open) (`discussion.md`, `error.md`) |
| AI 예상질환 스키마 (Track B) | `apps/ai-server/src/schemas/ai_predicted_disease.py` |
| HPI 격리 adversarial 테스트 (Track B, qa) | `apps/ai-server/tests/test_hpi_isolation.py` |
| continuous_test.py 하네스 (Track C) | `apps/ai-server/src/continuous_test.py` |
