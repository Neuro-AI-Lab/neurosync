# Agent 09: Longitudinal State Tracking Agent (TemporalSummaryAgent)

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `09` |
| **Agent Name** | `TemporalSummaryAgent` |
| **역할** | 종단적 상태 변화 추적 및 비교 분석. SentimentAnalyzer(13) 출력을 소비하여 sentiment 추이 시각화 데이터 생성 |
| **LLM Routing** | **100% rule-based — 실제로는 LLM을 전혀 호출하지 않는다.** `agents/temporal_summary.py`에는 router/adapter/prompt_loader 참조가 전혀 없다. `agent_model_registry.yaml`은 이 에이전트를 `benchmarked`로 등록해 두었으나 이는 코드 현실과 어긋난 등록 상태다(알려진 드리프트, 별도 BUG 예정 — 본 미션 범위에서는 registry 파일 자체를 수정하지 않는다). 출력의 `prompt_version: "v1"`은 프롬프트가 실제로 로드되지 않는 cosmetic 라벨이다 |

## 목적

환자의 현재 상태를 과거 기록(baseline)과 비교하여 임상 도메인별 변화 방향을 분류한다. 근거 불충분 시 반드시 "unknown"으로 표기하며, 추측하지 않는다. Handoff report의 "종단적 상태 변화" 섹션의 데이터를 생성한다. **비교/분류 로직은 전량 rule-based다** — "정성적 비교에만 LLM을 사용한다"는 아래 "핵심 동작" 절의 과거 서술은 as-built 상태와 다르다(코드에 LLM 호출 경로 자체가 없음).

## 추적 도메인

| 도메인 | 비교 대상 | 변화 분류 |
|---|---|---|
| PHQ-9 점수 | 이전 점수 vs 현재 점수 | improved / worsened / unchanged / unknown |
| GAD-7 점수 | 이전 점수 vs 현재 점수 | improved / worsened / unchanged / unknown |
| CTRS 위험도 | 이전 CTRS level vs 현재 | improved / worsened / unchanged / unknown |
| 증상 패턴 | 이전 증상 목록 vs 현재 | improved / worsened / unchanged / new_symptom / unknown |
| 약물 변화 | 이전 처방 vs 현재 처방 | added / removed / dose_changed / unchanged / unknown |
| 기능 수준 | 이전 기능 저하 정도 vs 현재 | improved / worsened / unchanged / unknown |

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `patient_id` | `string` | 환자 식별자 |
| `current_state` | `object` | 현재 세션에서 추출된 임상 정보 (ClinicalSlotAgent 출력) |
| `historical_data` | `array<object>` | TemporalRetrieverAgent가 가져온 과거 기록 |
| `current_scales` | `object \| null` | 현재 세션 구조화 척도 점수 (있을 경우) |
| `current_safety` | `object` | 현재 세션 SafetyClassifier 결과 |
| `current_sentiment` | `object \| null` | 현재 세션 SentimentAnalyzer(13) session-level 출력 |
| `prior_sentiments` | `array<object> \| null` | 이전 세션들의 session-level sentiment 요약 (있을 경우) |

## 출력

```json
{
  "session_id": "sess_20260618_001",
  "patient_id": "pt_12345",
  "comparison_baseline": {
    "date": "2026-05-01",
    "source": "handoff_20260501_001"
  },
  "domains": {
    "phq9": {
      "previous": { "score": 16, "date": "2026-04-01", "severity": "moderately_severe" },
      "current": { "score": 12, "date": "2026-06-18", "severity": "moderate" },
      "direction": "improved",
      "delta": -4,
      "confidence": 0.95,
      "evidence": "PHQ-9 점수 16 → 12 (4점 감소)"
    },
    "gad7": {
      "previous": null,
      "current": null,
      "direction": "unknown",
      "delta": null,
      "confidence": null,
      "evidence": "GAD-7 이전/현재 기록 없음"
    },
    "ctrs_level": {
      "previous": { "level": 4, "date": "2026-05-01" },
      "current": { "level": 4, "date": "2026-06-18" },
      "direction": "unchanged",
      "confidence": 0.90,
      "evidence": "CTRS 4 유지"
    },
    "symptoms": {
      "sleep": { "direction": "improved", "confidence": 0.75, "evidence": "입면 곤란 지속되나 빈도 감소 호소" },
      "appetite": { "direction": "improved", "confidence": 0.70, "evidence": "식욕 회복 중, 체중 감소 멈춤" },
      "mood": { "direction": "improved", "confidence": 0.65, "evidence": "우울감 빈도 감소 호소" },
      "concentration": { "direction": "unknown", "confidence": null, "evidence": "이전 기록 및 현재 보고 없음" },
      "energy": { "direction": "unchanged", "confidence": 0.60, "evidence": "피로감 지속" },
      "new_symptoms": []
    },
    "medications": {
      "changes": [
        {
          "medication": "에스시탈로프람",
          "change_type": "unchanged",
          "previous_dose": "10mg",
          "current_dose": "10mg",
          "confidence": 0.90
        }
      ]
    }
  },
  "overall_trajectory": "partially_improved",
  "plot_data": {
    "phq9_trend": [
      { "date": "2026-04-01", "score": 16 },
      { "date": "2026-06-18", "score": 12 }
    ],
    "ctrs_trend": [
      { "date": "2026-05-01", "level": 4 },
      { "date": "2026-06-18", "level": 4 }
    ]
  },
  "sentiment_trend": {
    "current_session": { "dominant_emotions": ["anxiety", "sadness"], "polarity": -0.65, "signal_strength": "moderate" },
    "previous_session": { "dominant_emotions": ["sadness"], "polarity": -0.45, "signal_strength": "mild" },
    "direction": "worsened",
    "note": "SentimentAnalyzer(13) session-level 출력 기반"
  },
  "timestamp": "2026-06-18T14:34:00+09:00"
}
```

## 핵심 동작

1. **도메인별 비교**: 각 임상 도메인을 독립적으로 비교한다. 한 도메인의 판정이 다른 도메인에 영향을 주지 않는다.
2. **Unknown 적극 사용**: 비교할 이전 데이터가 없거나, 현재 데이터가 불충분하면 반드시 `"unknown"`으로 분류한다. 추측하지 않는다.
3. **전량 rule-based**: PHQ-9/GAD-7 점수 차이 계산과 severity 분류뿐 아니라 증상/약물 등 정성적 비교 판정까지 모두 rule-based로 수행한다. 이 에이전트는 LLM을 호출하지 않는다(위 "개요" 상태 참조).
4. **Evidence 필수 기재**: 모든 변화 판정에 근거 텍스트를 포함한다.
5. **Plot-ready data 생성**: 시각화 가능한 시계열 데이터를 별도로 생성한다 (예: PHQ-9 추이 차트용).
6. **Baseline 명시**: 비교 기준이 된 과거 기록의 날짜와 출처를 명시한다.
7. **New symptom 감지**: 이전에 없었던 새로운 증상이 현재 보고되면 `"new_symptom"`으로 분류한다.

## 변화 방향 판정 기준

| Direction | PHQ-9/GAD-7 기준 | 증상 기준 |
|---|---|---|
| `improved` | 점수 5점 이상 감소 또는 severity 한 단계 하락 | 환자가 호전 보고 + 객관적 근거 |
| `worsened` | 점수 5점 이상 증가 또는 severity 한 단계 상승 | 환자가 악화 보고 또는 새 위험 신호 |
| `unchanged` | 점수 변화 5점 미만 | 유의미한 변화 없음 |
| `unknown` | 이전 또는 현재 점수 없음 | 비교 데이터 불충분 |

### Direction 판정 구체 예시 (PHQ-9/GAD-7)

- PHQ-9: 16 → 10 (6점 감소) → `improved` (severity: moderately_severe → moderate)
- GAD-7: 8 → 12 (4점 증가) → `unchanged` (5점 미만 변화)
- GAD-7: 8 → 15 (7점 증가) → `worsened` (severity: mild → severe)
- PHQ-9: 이전 없음 → 현재 15 → `unknown`

### "Unknown" 판정 조건

다음 조건 중 하나라도 해당하면 반드시 `"unknown"`으로 분류한다. 추측하지 않는다:

| 조건 | 설명 |
|---|---|
| 이전 데이터 없음 | 초진 환자이거나 해당 도메인의 이전 기록이 존재하지 않는 경우 |
| 데이터 간격 > 6개월 | 이전 기록과 현재 평가 사이 간격이 6개월을 초과하는 경우 |
| Confidence < 0.5 | 이전 또는 현재 데이터의 confidence가 0.5 미만인 경우 |
| 충돌 데이터 | 이전/현재 데이터 간 모순이 있어 방향 판정이 불가능한 경우 |

## Plot-Ready JSON 출력 형식

Frontend에서 시계열 그래프 렌더링에 직접 사용 가능한 구조로 출력한다:

```json
{
  "plot_data": [
    {
      "date": "2026-04-01",
      "PHQ-9": 16,
      "GAD-7": null,
      "WHO-5": null,
      "ctrs_level": 4,
      "events": []
    },
    {
      "date": "2026-05-01",
      "PHQ-9": 14,
      "GAD-7": 8,
      "WHO-5": null,
      "ctrs_level": 4,
      "events": ["외래 진료"]
    },
    {
      "date": "2026-06-18",
      "PHQ-9": 12,
      "GAD-7": 7,
      "WHO-5": 15,
      "ctrs_level": 4,
      "sentiment_polarity": -0.45,
      "dominant_emotion": "anxiety",
      "events": []
    }
  ]
}
```

**규칙:**
- 날짜순 정렬 (오래된 순 → 최신 순)
- 해당 시점에 시행되지 않은 척도는 `null`
- `ctrs_level`은 숫자가 낮을수록 위험도가 높음을 frontend에서 명시해야 함
- `events`에는 해당 시점의 주요 이벤트(외래 진료, 약물 변경, 위기 이벤트 등)를 포함

## 안전 제약

1. **추측 금지**: 데이터가 부족하면 반드시 `"unknown"`. 임상적 추론을 통한 gap filling을 하지 않는다.
2. **AI는 진단하지 않는다.** "호전"과 "악화"는 데이터 변화 방향의 기술이지, 진단적 판단이 아니다.
3. **위험도 악화 즉시 알림**: CTRS level이 악화 방향이면 Orchestrator에 즉시 알린다.
4. **구조화 점수 rule-based 필수**: PHQ-9/GAD-7 severity 분류와 점수 비교는 LLM이 아닌 정해진 기준표(rule)로 수행한다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| 과거 데이터 없음 (초진) | 모든 도메인 `"unknown"`. 종단 비교 섹션에 "초진 환자, 비교 기준 없음" 표기 |
| 데이터 불일치 | 양쪽 데이터를 모두 기록하고 "불일치 확인 필요" 플래그 부착 |

**정정:** 이 에이전트는 LLM을 호출하지 않으므로 "LLM 비교 실패"/"LLM primary timeout" 같은 LLM 장애 대응 경로는 as-built 상태에 존재하지 않는다(과거 버전 문서의 서술 제거).
