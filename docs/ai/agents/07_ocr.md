# Agent 07: OCR Document Agent

> **상태 배너 — 구현됨 (PR #38 통합, `feat/f1-stt-ocr-integration`@`5bdd379f6eed9f340a9878edd02bbc0f073fd04a`, 2026-07-10)**: `agents/ocr.py`(`OCRAgent`) + `adapters/solar_document_parse.py`(`SolarDocumentParseAdapter`) + 라우트 `POST /ai/ocr/parse`(`routes/ocr.py`, `main.py`에 마운트됨)가 존재한다. as-built와 이 문서의 델타:
>
> - **인증 없음 (VAL-012, `error.md`, major, open, non-blocking).** STT와 동일한 무인증 posture — 유료 벤더 API(Upstage Document Parse)를 프록시하는 multipart 라우트, 비용/DoS 노출. 부분 완화: 50MB 크기 상한(초과 시 413). Content-Type 검사는 관대함. 벤더 자격증명(`UPSTAGE_API_KEY`)은 이 프로젝트가 Solar Pro3(대화 LLM)에도 이미 사용 중이므로 STT의 `SKT_A_X_API_KEY`와 달리 현재 이 환경에서 등록돼 있다 — 즉 `dependencies.get_ocr_agent()`의 fail-fast(`RuntimeError`) 경로는 이 프로젝트의 현재 `.env` 상태에서는 발현되지 않는다(발현 조건 자체는 STT와 동일한 코드 패턴).
> - **OCR 라이브 경로도 이 통합 미션에서 벤더 호출까지 수반한 검증은 수행되지 않았다.** `continuous_test.py`의 F1→F2 스모크는 STT/OCR을 항상 끈 상태로만 실행된다(`ocr_documents` 미전달). "인증"/"통과"/"검증됨" 등의 표현은 OCR 경로(agent/adapter/route)에 사용하지 않는다.
> - **Confidence는 벤더 네이티브 값이 아니라 합성값이다.** Upstage Document Parse는 요소별(per-element) confidence를 제공하지 않는다(agent 자체 docstring) — `agents/ocr.py::_synthesize_confidence()`가 Upstage 요소 카테고리(table/heading/paragraph=0.92, caption/footer/header=0.82, figure/chart/equation=0.60, 기타=0.70)를 기준으로 근사값을 만든다. 아래 "출력" 예시의 `confidence: 0.96` 같은 구체값은 예시일 뿐, 벤더가 직접 준 신뢰도가 아니다.
> - **4-tier confidence gate 임계값이 as-built 기준으로 다르다.** 코드 상수는 `CONFIDENCE_HIGH=0.9`(정상)/`CONFIDENCE_LOW=0.7`(info)/`CONFIDENCE_VERIFY=0.5`(verify, 미만이면 retry+값 null화)이며, 호출자가 넘기는 `confidence_threshold`(기본 0.7)는 legacy override로 mid-range 값에만 추가로 영향을 준다 — 아래 "핵심 동작" 절의 "confidence < 0.8" 단일 임계값 서술은 근사 요약이며 정확한 as-built 로직은 위 4-tier다.
> - **`document_type` 리터럴 값이 문서 표와 다르다.** as-built enum은 `diagnosis`/`prescription`/`consultation`/`lab_result`/`unknown`이다 — 이 문서의 "지원 문서 유형" 절이 사용하는 "상담기록"/"검사결과"는 개념적으로는 각각 `consultation`/`lab_result`에 대응하지만, 코드 필드명 자체는 다르다.

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
