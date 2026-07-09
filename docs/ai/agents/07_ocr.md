# Agent 07: OCR Document Agent

> **상태 배너 — 미구현 (설계 스펙만 존재)**: 3-way 감사 기준, `apps/ai-server/src/agents/`에 `ocr` 관련 에이전트 구현 파일이 존재하지 않는다. 이 문서는 설계 의도를 기술한 스펙이며, as-built 코드가 아니다.

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `07` |
| **Agent Name** | `OCRDocumentAgent` |
| **역할** | 의료 문서 이미지/PDF에서 구조화 정보 추출 |
| **LLM Routing** | fixed (Upstage Solar Document Parse) |

## 목적

환자가 제출한 진단서, 처방전, 상담기록, 검사결과 등의 의료 문서에서 구조화된 임상 정보를 추출한다. 추출 결과에는 블록별 confidence를 부여하며, 낮은 confidence 항목은 **"확인 필요"** 로 표기한다. OCR 결과는 확정 정보가 아니며, 항상 참고 자료로 취급된다.

## 지원 문서 유형

| 문서 유형 | 추출 대상 |
|---|---|
| 진단서 | 진단명, 진단 코드, 진단일, 담당과, 의사명 |
| 처방전 | 약물명, 용량, 투여 경로, 빈도, 처방일 |
| 상담기록 | 상담 내용, 상담일, 치료 계획 |
| 검사결과 | 검사 항목, 수치, 참고범위, 검사일 |

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `document` | `binary` | 문서 이미지 또는 PDF |
| `document_type_hint` | `enum \| null` | `diagnosis`, `prescription`, `counseling_record`, `test_result`, `unknown` |
| `patient_id` | `string` | 환자 식별자 |
| `session_id` | `string` | 세션 ID |

## 출력

```json
{
  "session_id": "sess_20260618_001",
  "patient_id": "pt_12345",
  "document_type": "prescription",
  "ocr_vendor": "upstage_solar_document_parse",
  "blocks": [
    {
      "block_id": "blk_001",
      "field": "medication_name",
      "value": "에스시탈로프람",
      "confidence": 0.96,
      "bounding_box": { "x": 120, "y": 340, "width": 200, "height": 30 },
      "needs_verification": false
    },
    {
      "block_id": "blk_002",
      "field": "medication_dose",
      "value": "10mg",
      "confidence": 0.94,
      "bounding_box": { "x": 330, "y": 340, "width": 80, "height": 30 },
      "needs_verification": false
    },
    {
      "block_id": "blk_003",
      "field": "department",
      "value": "정신건강의학과",
      "confidence": 0.72,
      "bounding_box": { "x": 50, "y": 120, "width": 150, "height": 25 },
      "needs_verification": true
    },
    {
      "block_id": "blk_004",
      "field": "prescription_date",
      "value": "2026-05-20",
      "confidence": 0.88,
      "bounding_box": { "x": 400, "y": 50, "width": 120, "height": 25 },
      "needs_verification": false
    }
  ],
  "extracted_summary": {
    "diagnoses": [],
    "medications": [
      { "name": "에스시탈로프람", "dose": "10mg", "frequency": "1일 1회", "confidence": 0.95 }
    ],
    "department": "정신건강의학과",
    "dates": ["2026-05-20"]
  },
  "low_confidence_items": [
    { "block_id": "blk_003", "field": "department", "confidence": 0.72, "message": "확인 필요" }
  ],
  "timestamp": "2026-06-18T14:29:30+09:00"
}
```

## 핵심 동작

1. **블록 단위 추출**: 문서를 영역(block)별로 분할하고, 각 블록에서 필드를 추출한다.
2. **Confidence per block**: 각 블록에 개별 confidence score를 부여한다.
3. **Low-confidence 표기**: confidence < 0.8인 블록은 `needs_verification: true`로 표기하고, `low_confidence_items`에 추가한다.
4. **문서 유형 자동 감지**: `document_type_hint`가 없을 경우 문서 레이아웃과 키워드를 기반으로 문서 유형을 추론한다.
5. **약물명 정규화**: 추출된 약물명을 표준 약물 데이터베이스와 매칭하여 정규화한다.
6. **날짜 형식 통일**: 다양한 날짜 형식(2026.05.20, 2026/05/20, 26년5월20일 등)을 ISO 8601 형식으로 통일한다.
7. **Bounding box 기록**: 각 추출 블록의 문서 내 위치를 기록하여, 추후 원본 대조가 가능하도록 한다.

## 안전 제약

1. **OCR 결과는 확정 정보가 아니다.** 모든 OCR 추출 결과는 "참고" 수준이며, 의료적 판단의 근거로 단독 사용하지 않는다.
2. **AI는 진단하지 않는다.** OCR로 추출된 진단명은 "문서에 기재된 진단명"으로 표기한다. AI 자체의 진단이 아님을 명시한다.
3. **Low-confidence 전파**: OCR confidence가 낮은 항목이 downstream 에이전트(ClinicalSlot 등)에 전달될 때, confidence 상한이 OCR confidence로 제한된다.
4. **문서 보관 정책 준수**: 원본 문서의 보관/삭제는 기관 정책에 따른다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| OCR 서비스 장애 | "문서 인식이 일시적으로 불가합니다. 잠시 후 다시 시도해주세요." 안내 |
| 이미지 품질 불량 | "문서가 잘 보이지 않습니다. 다시 촬영해주시겠어요?" 안내. 가능한 블록만 추출 |
| 미지원 문서 유형 | 문서 원본을 handoff에 첨부하고 "자동 분석 불가" 표기 |
| 전체 블록 low-confidence | 전체 결과를 "확인 필요"로 표기. 텍스트 직접 입력 안내 |
| 약물명 매칭 실패 | 원문 그대로 기록 + "확인 필요" 표기 |
