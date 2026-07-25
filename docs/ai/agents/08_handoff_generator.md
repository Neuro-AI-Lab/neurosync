# Agent 08: Handoff Report Writer Agent

> **번호 재부여 2026-07-20 (wave-6, 사용자 directive):** 구 Agent 10(`10_handoff_generator.md`).
> old→new 전체 매핑은 `docs/ai/agent_collaboration_f1f5.md`의 번호 체계 표를 참조.

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `08` |
| **Agent Name** | `HandoffGeneratorAgent` |
| **역할** | 의료진용 사전 문진 handoff report 생성 |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |

## 목적

사전 문진 과정에서 수집된 모든 정보를 종합하여 의료진이 진료에 즉시 활용할 수 있는 구조화된 handoff report를 생성한다. 모든 주장(claim)에는 반드시 evidence 인용을 포함한다. **진단적 단정을 하지 않으며**, **치료 지시를 하지 않는다**.

## Report 12개 섹션

PRD Section 6.3 기준 12-section 구조. 모든 필수 섹션은 반드시 존재해야 하며, 데이터가 없는 경우 "해당 정보 없음"으로 포함한다.

| 번호 | 섹션명 | 설명 | 필수 여부 |
|---|---|---|---|
| 1 | 사용자 기본정보 | 환자 가명 ID, 나이, 성별, 평가 일시 | 필수 |
| 2 | 입력 source 요약 | 자율 대화, 구조화 문진, STT, OCR, 진료기록, 이전 handoff 등 사용된 source 목록 | 필수 |
| 3 | 현재 주요 호소 | chief_complaint + 주요 증상 표현 | 필수 |
| 4 | 정신건강 영역 후보 | domain_candidates (confidence, evidence 포함). 진단 아님 disclaimer 필수 | 필수 |
| 5 | CTRS 기반 위험도 평가 | CTRS level, 위험 근거, 자살/자해/타해/폭력성/환각/공황/물질사용/기능손상 | 필수 |
| 6 | 시행된 구조화 문진 결과 | 척도명, 점수, severity, 시행 일시, 위험 문항 양성 여부 | 조건부 (설문 시행 시 필수) |
| 7 | 기록 기반 근거 | OCR/진료기록/처방기록에서 추출한 진단명, 처방약, 진료과, 검사 결과 | 조건부 (기록 존재 시 필수) |
| 8 | 대화 기반 근거 | 주요 사용자 발화 + **발화별 sentiment 태그** (SentimentAnalyzer(10) 출력), 반복 표현, 정서 변화 흐름, 기능 손상 표현 (원문 인용) | 필수 |
| 9 | 종단적 상태 변화 | 이전 대비 호전/악화/유지, 새로운 증상, 재발 신호, CTRS 변화 | 조건부 (재진 시 필수, 초진 시 "해당 없음") |
| 10 | AI 판단의 한계 | 진단 아님 고지, OCR/STT 오류 가능성, RAG 근거 제한 가능성, 전문가 검토 필요 | 필수 |
| 11 | 권장 다음 조치 | 자가관리, 재평가, 전문가 상담, 정신건강의학과 상담 고려, 위기지원 안내 | 필수 |
| 12 | Evidence Registry | 모든 evidence_id와 source의 매핑 테이블 | 필수 |

### Section Completeness Tracking

출력 스키마에 `section_completeness` 필드를 포함하여 12개 섹션 각각의 포함 여부를 추적한다:

```json
{
  "section_completeness": {
    "section_01_patient_info": true,
    "section_02_input_sources": true,
    "section_03_chief_complaint": true,
    "section_04_domain_candidates": true,
    "section_05_risk_assessment": true,
    "section_06_survey_results": false,
    "section_07_record_evidence": false,
    "section_08_dialogue_evidence": true,
    "section_09_longitudinal": false,
    "section_10_limitations": true,
    "section_11_recommendations": true,
    "section_12_evidence_registry": true
  }
}
```

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `patient_profile` | `object` | 환자 기본 정보 |
| `session_metadata` | `object` | 세션 정보 (일시, 입력 채널, 소요 시간) |
| `clinical_slots` | `object` | ClinicalSlotAgent 추출 결과 |
| `safety_classification` | `object` | SafetyClassifierAgent 결과 |
| `scale_scores` | `object \| null` | 구조화 척도 점수 (rule-based 계산 결과) |
| `temporal_summary` | `object` | TemporalSummaryAgent 출력 |
| `retrieved_context` | `array<object>` | TemporalRetrieverAgent 검색 결과 |
| `dialogue_transcript` | `array<object>` | 대화 전문 |
| `ocr_results` | `array<object> \| null` | OCR 추출 결과 |

## 출력

```json
{
  "report_id": "handoff_20260618_001",
  "session_id": "sess_20260618_001",
  "patient_id": "pt_12345",
  "generated_at": "2026-06-18T14:36:00+09:00",
  "model_used": "upstage-solar-pro-3",
  "sections": {
    "s01_patient_info": {
      "patient_id": "pt_12345",
      "age": 34,
      "sex": "M",
      "visit_type": "재진"
    },
    "s02_assessment_datetime": {
      "start": "2026-06-18T14:25:00+09:00",
      "end": "2026-06-18T14:35:00+09:00",
      "duration_minutes": 10
    },
    "s03_input_sources": {
      "channels": [
        { "type": "text_chat", "turns": 12, "reliability": "high" },
        { "type": "ocr_document", "count": 1, "avg_confidence": 0.89, "reliability": "medium-high" }
      ]
    },
    "s04_chief_complaint": {
      "summary": "2개월간 지속된 우울감과 불면 [ev_msg_001]",
      "evidence": [
        { "id": "ev_msg_001", "source_type": "message", "source_ref": "dialogue_turn_3", "text": "두 달 전부터 계속 우울해요" }
      ]
    },
    "s05_mental_health_domains": {
      "disclaimer": "아래는 수집된 증상을 기반으로 한 관련 영역 후보이며, 진단이 아닙니다.",
      "candidates": [
        { "domain": "우울 영역", "basis": "지속적 우울감, 수면장애, 식욕감소, 흥미저하 [ev_msg_002][ev_msg_003][ev_msg_004]" },
        { "domain": "불안 영역", "basis": "입면 곤란 동반 [ev_msg_003]" }
      ]
    },
    "s06_ctrs_risk": {
      "ctrs_level": 4,
      "label": "중증/주의",
      "risk_level": "low",
      "basis": "자살/자해 관련 표현 미감지. 위험 키워드 및 LLM 분류 모두 CTRS 5. 과거 위험 이벤트 없음. [ev_risk_001]",
      "evidence": [
        { "id": "ev_risk_001", "source_type": "risk_event", "source_ref": "safety_classifier", "text": "keyword: no match, llm: CTRS 5 (conf 0.92)" }
      ]
    },
    "s07_structured_scales": {
      "scales_administered": [
        { "scale": "PHQ-9", "score": 12, "severity": "moderate", "method": "rule-based", "evidence_id": "ev_scale_001" }
      ]
    },
    "s08_record_based_evidence": {
      "items": [
        { "id": "ev_ocr_001", "source_type": "document_block", "source_ref": "ocr_prescription_001", "content": "에스시탈로프람 10mg 1일 1회 (2026-05-20 처방)", "confidence": 0.95 }
      ]
    },
    "s09_dialogue_based_evidence": {
      "items": [
        { "id": "ev_msg_002", "source_type": "message", "source_ref": "dialogue_turn_3", "content": "계속 우울해요, 아무것도 하기 싫어요" },
        { "id": "ev_msg_003", "source_type": "message", "source_ref": "dialogue_turn_5", "content": "잠들기가 너무 어렵고 자다가도 깨요" },
        { "id": "ev_msg_004", "source_type": "message", "source_ref": "dialogue_turn_7", "content": "밥맛도 없고 3키로 빠졌어요" }
      ]
    },
    "s10_longitudinal_changes": {
      "baseline_date": "2026-05-01",
      "domains": {
        "phq9": { "previous": 16, "current": 12, "direction": "improved" },
        "ctrs": { "previous": 4, "current": 4, "direction": "unchanged" },
        "sleep": { "direction": "improved", "note": "입면 곤란 빈도 감소" }
      }
    },
    "s11_ai_limitations": {
      "low_confidence_items": [
        { "field": "psychosocial_context.occupation", "confidence": 0.55, "note": "간접 언급으로 추정" }
      ],
      "missing_information": ["집중력 변화", "정신운동 변화", "과거 정신과 병력 상세"],
      "known_limitations": [
        "본 보고서는 AI 사전 문진 보조 도구의 출력이며, 의료적 진단이나 치료 결정을 대체하지 않습니다.",
        "구조화 척도 점수는 환자 자가보고 기반 rule-based 계산 결과입니다."
      ]
    },
    "s12_recommended_next_steps": {
      "disclaimer": "아래는 추가 평가를 위한 절차적 제안이며, 치료 지시가 아닙니다.",
      "suggestions": [
        "GAD-7 미시행 — 불안 영역 추가 평가 고려",
        "집중력/정신운동 변화 미확인 — 면담 시 확인 권장",
        "과거 정신과 병력 상세 미수집 — 면담 시 확인 권장"
      ]
    }
  },
  "ctrs_level": 4,
  "evidence_registry": {
    "total_citations": 7,
    "citation_ids": ["ev_msg_001", "ev_msg_002", "ev_msg_003", "ev_msg_004", "ev_scale_001", "ev_ocr_001", "ev_risk_001"]
  },
  "section_completeness": {
    "section_01_patient_info": true,
    "section_02_input_sources": true,
    "section_03_chief_complaint": true,
    "section_04_domain_candidates": true,
    "section_05_risk_assessment": true,
    "section_06_survey_results": true,
    "section_07_record_evidence": true,
    "section_08_dialogue_evidence": true,
    "section_09_longitudinal": true,
    "section_10_limitations": true,
    "section_11_recommendations": true,
    "section_12_evidence_registry": true
  },
  "evidence_count": 7
}
```

## Evidence ID 생성 규칙

Report 내 모든 evidence 인용은 `[ev_{source_type}_{3-digit sequence}]` 형식을 사용한다:

| Source Type | Evidence ID 패턴 | 예시 |
|---|---|---|
| 대화 메시지 | `[ev_msg_NNN]` | `[ev_msg_001]`, `[ev_msg_012]` |
| 구조화 척도 | `[ev_scale_NNN]` | `[ev_scale_001]` |
| OCR 문서 블록 | `[ev_ocr_NNN]` | `[ev_ocr_001]` |
| 위험 이벤트 | `[ev_risk_NNN]` | `[ev_risk_001]` |
| 이전 handoff | `[ev_prior_NNN]` | `[ev_prior_001]` |

**규칙:**
1. 시퀀스 번호는 source_type 내에서 001부터 순차 증가한다.
2. 모든 `[ev_*]` 인용은 반드시 Section 12 Evidence Registry에 대응하는 항목이 있어야 한다.
3. Evidence Registry에 등록되지 않은 ID를 인용하면 EvidenceVerifier가 dangling reference로 reject한다.

## CTRS Level 출력

출력 스키마에 `ctrs_level: int` 필드를 포함한다. CTRS 1-2인 경우 Section 11(권장 다음 조치)에 즉시 대응 관련 내용이 반드시 포함되어야 한다.

## 핵심 동작

1. **Evidence 인용 필수**: 모든 주장(claim)에 `[ev_{source_type}_{NNN}]` 형태의 evidence ID를 인용한다. 인용 없는 주장은 report에 포함하지 않는다.
2. **12개 섹션 완전 생성**: 해당 데이터가 없는 섹션도 "해당 정보 없음"으로 포함한다. 섹션을 생략하지 않는다.
3. **진단적 단정 금지**: "우울증입니다", "불안장애가 의심됩니다" 등의 진단적 표현을 사용하지 않는다. "우울 영역 관련 증상이 수집되었습니다"로 표현한다.
4. **치료 지시 금지**: "약을 처방하세요", "입원이 필요합니다" 등의 치료 지시를 하지 않는다. "추가 평가 고려" 수준으로만 제안한다.
5. **한계 명시**: Section 11에서 AI 판단의 한계를 투명하게 기술한다.
6. **구조화 점수 검증**: PHQ-9/GAD-7 등의 점수가 rule-based로 계산되었는지 확인하고, 계산 방법을 명시한다.
7. **Source 신뢰도 전파**: OCR/STT에서 온 정보의 신뢰도를 report에 반영한다.

## 안전 제약

1. **AI는 진단하지 않는다.** Section 5(정신건강 영역 후보)에 반드시 disclaimer를 포함한다.
2. **치료 지시를 하지 않는다.** Section 12(권장 다음 조치)는 절차적 제안에 한정한다.
3. **Evidence 없는 주장 금지.** 모든 claim은 evidence registry에 등록된 citation이 있어야 한다.
4. **CTRS level과 권장 조치 정합성**: CTRS 1-2인 경우 권장 조치에 즉시 대응 관련 내용이 반드시 포함되어야 한다.
5. **Low-confidence 항목 명시**: confidence < 0.7인 항목은 Section 11에 나열한다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| LLM report 생성 실패 | Secondary → Fallback LLM 시도 |
| 전체 LLM 실패 | 구조화된 slot 데이터를 템플릿에 직접 삽입한 minimal report 생성 |
| Evidence verification 실패 (09번 Agent reject) | 지적 사항 수정 후 재생성 (최대 2회) |
| 필수 섹션 데이터 부재 | 해당 섹션에 "정보 미수집" 표기 후 Section 11에 한계로 기록 |
