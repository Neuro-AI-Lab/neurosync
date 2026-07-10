# Agent 05: Input Normalizer Agent

> **상태 배너 — live-as-of-this-merge, 그러나 correction 기능은 확인된 no-op (BUG-020)**: PR #38 통합 머지(`feat/f1-stt-ocr-integration`@`5bdd379f6eed9f340a9878edd02bbc0f073fd04a`, 2026-07-10) 이후 `InputNormalizerAgent`는 더 이상 dead code가 아니다 — `f1.py`가 STT/OCR 여부와 무관하게 **모든 환자 입력**을 이 agent에 먼저 통과시킨 뒤 Safety/Dialogue로 넘긴다(`f1.py:398-399,505-531,910-911`; `01_orchestrator.md`의 "STT/OCR 입력 시 InputNormalizer(05) 호출" 기술이 처음으로 as-built와 일치하게 됨). **그러나 이 활성화가 기능 정상화를 의미하지 않는다.** 아래 ISS-039 프롬프트/스키마 불일치는 라이브 배치(`result.md` EXP-013)에서 실측 확인됐다: 실제 교정(correction)이 시도된 경우 **14/14(100%)가 스키마 검증 실패로 `_safe_fallback()`에 귀결**되어 원문이 그대로 반환된다(`error.md` BUG-020, open, major). Fail-safe 자체는 검증됨 — 관측된 모든 사례에서 위험 표현을 포함한 원문이 그대로(verbatim) 보존됐다. 수정 미적용 상태이며, PR #38 병합의 merge-gating 조건은 아니다(critic ruling (d), REV-021) — "activation"을 "정상 동작"으로 오독하지 말 것. **"인증"/"통과"/"검증됨" 등의 표현은 이 correction 기능에 사용하지 않는다.**

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `05` |
| **Agent Name** | `InputNormalizerAgent` |
| **역할** | STT 전사 오류 및 오타 교정, 구어체/방언 정규화 |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |
| **프롬프트 pin** | v1 (`agents/input_normalizer.py:43`) |

## 목적

STT transcript와 텍스트 입력의 전사 오류, 오타, 구어체/방언 표현을 정규화한다. **원래 의미를 절대 변경하지 않으며**, 임상적으로 유의미한 내용을 보존한다. 모든 변경 사항은 change log에 기록한다.

**ISS-039 — 프롬프트/스키마 불일치(구체화)**: v1 시스템 프롬프트(`docs/ai/prompts/input_normalizer/v1.system.md`)와 실제 출력 스키마(`schemas/input_normalizer.py` `NormalizationChange`)가 아래와 같이 서로 다른 계약을 지시한다:

| 항목 | 프롬프트가 지시하는 형식 | 스키마가 요구하는 형식 |
|---|---|---|
| `type` 값 집합 | 7종 (`stt_misrecognition`, `ocr_misrecognition`, `typo_correction`, `dialect_correction`, `colloquial_normalization`, `filler_removal`, `sentence_completion`) | `Literal` 5종 (`stt_error`, `colloquial`, `dialect`, `typo`, `spacing`) |
| 변경 후 값 필드명 | `corrected` | `normalized` |
| `position` 타입 | `int` (단일 오프셋) | `dict[str, int]` (`{start, end}`) |
| `confidence`/`applied` 필드 | 각 변경 항목에 포함 | 스키마에 필드 자체가 없음 |

코드(`agents/input_normalizer.py:134-141`)는 LLM 응답의 `normalized`/`position`(dict) 키를 읽어 `NormalizationChange`를 구성한다. 프롬프트가 지시한 대로 LLM이 `type`에 7종 중 스키마에 없는 값(예: `stt_misrecognition`)을 출력하면 `Literal` 필드 검증이 실패하고, `position`에 `int`를 출력하면 `dict[str, int]` 필드 검증이 실패한다 — 둘 중 하나만 어긋나도 `NormalizationChange(...)` 생성이 `pydantic.ValidationError`를 던지고, 이는 `run()`의 바깥쪽 `try/except`(`:77-81`)에 잡혀 `_safe_fallback()`으로 떨어진다(원문을 그대로 반환, `changes: []`). 즉 현재 프롬프트/스키마 조합에서는 LLM이 프롬프트 지시를 충실히 따를수록 오히려 폴백 경로로 빠질 가능성이 높다.

**라이브 실측 (BUG-020, `result.md` EXP-013, 2026-07-10):** PR #38 통합으로 이 경로가 처음 라이브 실행됐다. Method A(세이프티 매트릭스 배치, 79회 호출) — 9/79가 위 시그니처로 폴백. Method B(교정을 강제하도록 설계된 6개 텍스트의 통제 드라이버) — 교정이 필요한 5/5가 전부 폴백, 이미 깨끗한 1개 대조 텍스트만 정상 성공. **합산: 교정을 시도한 14/14(100%) 호출이 전부 폴백** — 나머지 71건은 LLM이 "교정 불필요"로 판단해 애초에 스키마 충돌 지점에 도달하지 않은 경우다. 위험 표현 포함 케이스(`"죽고싶다는 생각이 자꾸 들어여 맨날"`)도 폴백됐으나 `risk_expressions_preserved=true`, `normalized_text == raw_text` verbatim으로 fail-safe는 유지됐다.

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `raw_text` | `string` | 원본 텍스트 (STT transcript 또는 사용자 입력) |
| `input_type` | `enum` | `stt_transcript`, `user_text` |
| `dialect_hint` | `string \| null` | 방언 힌트 (예: `경상`, `전라`, `충청`) |

## 출력

아래 예시는 **스키마(`NormalizationChange`)가 요구하는 목표 형태**다. 위 ISS-039 불일치가 살아있는 동안, LLM이 프롬프트 지시(7-값 `type`/`corrected`/int `position`)를 그대로 따르면 이 형태로 정상 도달하지 못하고 `_safe_fallback()`(원문 그대로, `changes: []`)으로 떨어질 가능성이 높다.

```json
{
  "normalized_text": "두 달 전부터 우울하고 잠을 못 자요. 약도 안 먹고 있어요.",
  "original_text": "두달 전부텉 우울하구 잠을 몬자요. 약두 안먹구 이써요.",
  "input_type": "stt_transcript",
  "changes": [
    {
      "original": "전부텉",
      "normalized": "전부터",
      "type": "stt_error",
      "position": { "start": 4, "end": 7 }
    },
    {
      "original": "우울하구",
      "normalized": "우울하고",
      "type": "colloquial",
      "position": { "start": 8, "end": 12 }
    },
    {
      "original": "몬자요",
      "normalized": "못 자요",
      "type": "stt_error",
      "position": { "start": 16, "end": 19 }
    },
    {
      "original": "약두",
      "normalized": "약도",
      "type": "colloquial",
      "position": { "start": 21, "end": 23 }
    },
    {
      "original": "안먹구",
      "normalized": "안 먹고",
      "type": "colloquial",
      "position": { "start": 24, "end": 27 }
    },
    {
      "original": "이써요",
      "normalized": "있어요",
      "type": "stt_error",
      "position": { "start": 28, "end": 31 }
    }
  ],
  "change_count": 6,
  "clinical_content_preserved": true,
  "timestamp": "2026-06-18T14:29:50+09:00"
}
```

## 핵심 동작

1. **STT 전사 오류 교정**: 음소 유사 오류 (예: "전부텉" → "전부터"), 띄어쓰기 오류, 동음이의어 오류를 교정한다.
2. **구어체 정규화**: 일상 구어체 표현을 표준어로 변환한다 (예: "우울하구" → "우울하고", "몬" → "못").
3. **방언 처리**: 지역 방언 표현을 표준어로 변환한다 (예: "머리가 지끈지끈허다" → "머리가 지끈지끈하다").
4. **의미 보존 원칙**: 교정 시 임상적 의미가 변경되어서는 안 된다. 의미가 불확실한 경우 원문을 유지한다.
5. **Change log 기록**: 모든 변경 사항을 `changes` 배열에 기록한다 (원본, 변환 결과, 변환 유형, 위치).
6. **위험 키워드 보존**: 자살/자해 관련 표현은 정규화하되, Safety classifier가 감지할 수 있도록 의미를 정확히 보존한다.

## 정규화 유형

| 유형 | 설명 | 예시 |
|---|---|---|
| `stt_error` | STT 전사 오류 | "몬자요" → "못 자요" |
| `colloquial` | 구어체 표현 | "~구" → "~고", "~써" → "~어" |
| `dialect` | 방언 표현 | "아프다카이" → "아프다고" |
| `typo` | 단순 오타 | "우울증" → "우울증" (오타 교정) |
| `spacing` | 띄어쓰기 | "안먹고" → "안 먹고" |

## 임상 의미 보존 원칙

정규화 과정에서 임상적 의미를 반드시 보존해야 한다. 다음 항목은 절대 변경하거나 제거하지 않는다:

| 보존 대상 | 예시 | 이유 |
|---|---|---|
| 증상 표현 | "불안하다", "잠을 못 잔다", "의욕이 없다" | 임상 slot 추출의 핵심 입력 |
| 약물명 | "에스시탈로프람", "렉사프로" | 처방 이력 확인 필수 |
| 수치 정보 | "3키로 빠졌다", "2주 전부터" | 기간/정도의 정량적 정보 |
| 위험 표현 | "죽고 싶다", "사라지고 싶다", "다 끝내고 싶다" | Safety classifier 감지 대상 |
| 보호요인 표현 | "가족이 있다", "치료 의지가 있다" | CTRS 평가의 보호요인 |

### Safety-Critical 표현 보존 규칙

다음 표현은 정규화 과정에서 **절대 제거되거나 의미가 약화되어서는 안 된다**:

- "죽고 싶다" → 절대 정규화하여 제거하지 않음
- "사라지고 싶다" → 유지
- "내가 없으면 다 편할 텐데" → 유지
- "힘들어서 못 살겠다" → 유지
- "다 끝내고 싶다" → 유지
- "약을 한 움큼 먹었다" → 유지 (약물 과다복용 가능성)

STT 전사 오류로 인해 위험 표현이 왜곡된 경우(예: "죽고싶다" → "죽고십다"), 원래 의미를 복원하는 방향으로 정규화한다.

## Change Log 기록 요구사항

모든 정규화 변경은 `changes` 배열에 기록해야 하며, 각 항목에 다음을 포함한다:
- `original`: 변경 전 텍스트
- `normalized`: 변경 후 텍스트
- `type`: 변경 유형 (`stt_error`, `colloquial`, `dialect`, `typo`, `spacing`)
- `position`: 원문 내 위치 (`start`, `end`)

이 change log는 감사(audit) 추적 및 정규화 품질 평가에 사용된다.

## 안전 제약

1. **임상 내용 변경 금지**: 증상 표현, 약물명, 수치 정보 등 임상적으로 유의미한 내용을 변경하지 않는다.
2. **위험 신호 보존**: 자살/자해/타해 관련 표현의 의미를 정확히 보존한다. 오정규화로 위험 키워드가 소실되어서는 안 된다. "죽고 싶다"는 절대 정규화하여 제거하지 않는다.
3. **불확실 시 원문 유지**: 정규화 결과가 불확실한 경우 원문을 그대로 유지한다.
4. **원문 항상 보존**: `original_text`에 원문을 반드시 저장한다. 정규화 후에도 원문 참조가 가능해야 한다.
5. **Safety-critical 표현 우선**: 위험 표현의 STT 오류 교정은 의미 복원 방향으로 수행한다. 의미가 불확실하면 원문 유지.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| LLM 정규화 실패 | 원문을 그대로 다음 단계에 전달 (정규화 skip) |
| LLM primary timeout | Secondary → Fallback 시도 |
| 전체 LLM 실패 | 원문 그대로 전달. 정규화 없이도 파이프라인은 동작해야 한다 |
| 의미 불확실 교정 | 해당 부분만 원문 유지, change log에 "skipped_uncertain" 기록 |
