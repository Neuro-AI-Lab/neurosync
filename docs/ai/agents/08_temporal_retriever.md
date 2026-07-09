# Agent 08: Clinical Context RAG Agent (TemporalRetrieverAgent)

> **상태 배너**: 에이전트 미구현 — F2 범위는 domain_inference(14)로 대체(superseded-for-F2, PRD v2.4). 본 스펙은 F4(종단 검색) 재배치 대기. `apps/ai-server/src/agents/`에 `temporal_retriever` 구현 파일이 존재하지 않는다.

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `08` |
| **Agent Name** | `TemporalRetrieverAgent` |
| **역할** | 임상 맥락 검색 (Retrieval-Augmented Generation) |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |

## 목적

pgvector 기반 semantic search를 통해 환자의 과거 임상 맥락을 검색한다. 대화 맥락 제공과 handoff report 생성 두 가지 용도로 사용된다. 검색 결과는 복합 점수(semantic similarity + recency + risk relevance + doc confidence - stale penalty)로 랭킹된다.

## 검색 대상 소스

| 소스 | 설명 | 저장 위치 |
|---|---|---|
| 과거 대화 | 이전 세션 대화 이력 | `conversations` 테이블 |
| 이전 handoff report | 과거 생성된 handoff 보고서 | `handoff_reports` 테이블 |
| PHQ-9/GAD-7 이력 | 과거 구조화 척도 점수 | `scale_scores` 테이블 |
| OCR 문서 블록 | OCR로 추출된 문서 정보 | `ocr_blocks` 테이블 |
| 위험 이벤트 | 과거 CTRS 1-3 이벤트 기록 | `risk_events` 테이블 |

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `query` | `string` | 검색 쿼리 (대화 맥락 또는 임상 질문) |
| `patient_id` | `string` | 환자 식별자 |
| `retrieval_purpose` | `enum` | `dialogue_context`, `handoff_generation` |
| `top_k` | `integer` | 반환할 최대 결과 수 (기본값: 10) |
| `time_range` | `object \| null` | 검색 시간 범위 제한 |
| `source_filter` | `array<string> \| null` | 소스 유형 필터 |

## 출력

```json
{
  "session_id": "sess_20260618_001",
  "patient_id": "pt_12345",
  "retrieval_purpose": "handoff_generation",
  "query": "우울 증상 이력 및 약물 복용 현황",
  "results": [
    {
      "rank": 1,
      "source_type": "handoff_report",
      "source_id": "handoff_20260501_001",
      "content": "2026-05-01 handoff: 주호소 우울감, PHQ-9 14점, 에스시탈로프람 10mg 복용 중",
      "scores": {
        "semantic_similarity": 0.89,
        "recency": 0.75,
        "risk_relevance": 0.60,
        "doc_confidence": 1.0,
        "stale_penalty": 0.05,
        "composite": 0.84
      },
      "timestamp": "2026-05-01T10:00:00+09:00",
      "metadata": {
        "ctrs_level_at_time": 4,
        "phq9_score": 14
      }
    },
    {
      "rank": 2,
      "source_type": "scale_score",
      "source_id": "phq9_20260401",
      "content": "PHQ-9: 16점 (moderately severe). 수면 3, 식욕 2, 에너지 2, 흥미 3, 집중 2, 자해 0",
      "scores": {
        "semantic_similarity": 0.82,
        "recency": 0.60,
        "risk_relevance": 0.50,
        "doc_confidence": 1.0,
        "stale_penalty": 0.10,
        "composite": 0.73
      },
      "timestamp": "2026-04-01T09:30:00+09:00",
      "metadata": {
        "scale_type": "PHQ-9",
        "total_score": 16
      }
    },
    {
      "rank": 3,
      "source_type": "ocr_block",
      "source_id": "ocr_blk_20260520_003",
      "content": "처방전: 에스시탈로프람 10mg 1일 1회",
      "scores": {
        "semantic_similarity": 0.78,
        "recency": 0.80,
        "risk_relevance": 0.30,
        "doc_confidence": 0.95,
        "stale_penalty": 0.02,
        "composite": 0.72
      },
      "timestamp": "2026-05-20T00:00:00+09:00",
      "metadata": {
        "ocr_confidence": 0.95,
        "document_type": "prescription"
      }
    }
  ],
  "total_candidates": 47,
  "timestamp": "2026-06-18T14:31:00+09:00"
}
```

## Composite Scoring 공식

```
composite = 0.40 * semantic_similarity
          + 0.25 * recency
          + 0.15 * risk_relevance
          + 0.10 * doc_confidence
          - 0.10 * stale_penalty
```

| 가중치 | 기본값 | 설명 |
|---|---|---|
| `w1` (semantic_similarity) | **0.40** | 쿼리와의 의미적 유사도 (cosine similarity) |
| `w2` (recency) | **0.25** | 최신성 (exponential decay) |
| `w3` (risk_relevance) | **0.15** | 위험 이벤트 관련도 |
| `w4` (doc_confidence) | **0.10** | 문서/소스 신뢰도 (OCR confidence 등) |
| `w5` (stale_penalty) | **0.10** | 오래된 정보 감점 |

### 각 요소 산출 방법

- `semantic_similarity`: pgvector cosine similarity (0.0~1.0)
- `recency`: `exp(-lambda * days_since)` (lambda 조정 가능, 기본 0.01)
- `risk_relevance`: CTRS 1-3 이벤트 관련 문서에 가산점 (CTRS 1 → 1.0, CTRS 2 → 0.8, CTRS 3 → 0.5, 기타 → 0.0)
- `doc_confidence`: 소스 자체의 신뢰도 (대화=1.0, rule-based 점수=1.0, OCR=해당 block confidence, STT=transcript confidence)
- `stale_penalty`: 6개월 이상 된 정보에 추가 감점 (0.0~0.3, days 기반 linear 증가)

## Domain Candidates 출력 형식

TemporalRetriever는 검색 결과를 기반으로 정신건강 영역 후보, 진료과 후보, 추가 확인 질문, 권장 설문 도구를 출력한다:

```json
{
  "domain_candidates": [
    {
      "domain": "anxiety | depression | alcohol | substance | trauma | sleep | psychosis | other",
      "confidence": 0.82,
      "evidence": ["불안 호소", "수면 저하", "긴장감 표현"],
      "recommended_surveys": ["GAD-7", "PHQ-4", "WHO-5"]
    }
  ],
  "department_candidates": [
    {
      "department": "정신건강의학과",
      "reason": "불안 및 수면 문제가 지속됨"
    }
  ],
  "additional_questions": ["최근 2주 동안 흥미나 의욕이 줄었나요?"],
  "rag_sources": [
    {
      "source_id": "string",
      "title": "string",
      "relevance_score": 0.0
    }
  ]
}
```

**초기 구현:** RAG 검색 없이 TemporalRetriever가 LLM으로 직접 영역 후보를 추론하는 fallback 모드를 우선 구현한다. Knowledge base 구축 후 RAG 파이프라인을 활성화한다.

## Knowledge Base 검색 사양 (Placeholder)

> DB 정보(vector store, embedding model, knowledge base) 확정 후 상세 설계를 업데이트한다.

- **Vector Store**: pgvector (PostgreSQL 확장)
- **Embedding Model**: 미정 (후보: Upstage Solar Embedding, OpenAI text-embedding-3, KoSimCSE)
- **Knowledge Base 내용**: 정신건강 영역 정의, 영역별 증상 매핑, 권장 문진 도구 매핑, 진료과 매핑 규칙
- **검색 방식**: query embedding → pgvector cosine similarity → top-K retrieval → LLM reranking

## 핵심 동작

1. **Dual-purpose 검색**: 대화 맥락 제공(dialogue_context)과 handoff 생성(handoff_generation) 두 가지 용도로 다른 가중치를 적용한다.
2. **Embedding 생성**: 쿼리를 embedding vector로 변환하여 pgvector에서 cosine similarity 검색을 수행한다.
3. **Composite ranking**: 단순 semantic similarity가 아닌, 복합 점수로 결과를 랭킹한다.
4. **Source type 필터링**: 용도에 따라 특정 소스만 검색할 수 있다 (예: handoff 생성 시 risk_events 우선).
5. **Time range 제한**: 필요 시 검색 시간 범위를 제한할 수 있다.
6. **OCR confidence 전파**: OCR에서 온 블록은 해당 confidence가 doc_confidence로 반영된다.
7. **LLM reranking (선택)**: 초기 검색 결과를 LLM이 재랭킹하여 relevance를 높일 수 있다.

## 안전 제약

1. **환자 격리**: 검색은 항상 `patient_id`로 필터링된다. 타 환자의 데이터가 검색 결과에 포함되어서는 안 된다.
2. **위험 이벤트 우선**: CTRS 1-3 이력이 있는 환자의 경우, 해당 위험 이벤트가 검색 결과 상위에 노출되도록 `risk_relevance` 가중치를 높인다.
3. **Stale data 경고**: 6개월 이상 된 정보가 주요 결과에 포함될 경우 "오래된 정보" 경고를 함께 전달한다.
4. **Source 추적**: 모든 검색 결과에 source_type, source_id, timestamp를 포함하여 추적 가능성을 보장한다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| pgvector 연결 실패 | 재시도 (최대 3회). 실패 시 과거 맥락 없이 진행, handoff에 "과거 이력 조회 불가" 표기 |
| Embedding 생성 실패 | LLM fallback 순서대로 시도. 전체 실패 시 keyword-based 검색으로 전환 |
| 검색 결과 0건 | 정상 케이스 (초진 등). 빈 결과 반환, 대화/handoff는 현재 세션 정보만으로 진행 |
| 검색 지연 (>3초) | timeout 후 top-k를 줄여 재시도. 실패 시 캐시된 최근 결과 사용 |
