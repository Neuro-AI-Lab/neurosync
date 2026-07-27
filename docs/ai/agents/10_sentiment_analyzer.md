# Agent 10: Sentiment Analyzer Agent

> **번호 재부여 2026-07-20 (wave-6, 사용자 directive):** 구 Agent 13(`13_sentiment_analyzer.md`). 구번호 원본 파일은 2026-07-27 사용자 directive로 파기 — 스펙 번호 재정립: 01–11 = `apps/ai-server/prompts/` 최종 구성과 1:1.
> old→new 전체 매핑은 `docs/ai/agent_collaboration_f1f5.md`의 번호 체계 표를 참조.
> 이번 작업에서 이 번호 재부여보다 앞서 존재하던 stale downstream-agent 참조 2건
> (`TemporalSummaryAgent`, `HandoffGeneratorAgent`)도 함께 정정했다 — 아래 inline note 참조.

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `10` |
| **Agent Name** | `SentimentAnalyzerAgent` |
| **역할** | 발화 단위 감정 분석 + 세션 통합 sentiment 리포트 |
| **LLM Routing** | **Mode A(발화 단위)에만 적용.** benchmarked (Primary: Solar Pro 3 / Secondary: K-EXAONE / Fallback: A.X K1), 프롬프트 pin v2(`agents/sentiment_analyzer.py:40`). **Mode B(세션 통합)는 LLM을 전혀 호출하지 않는 순수 rule-based 집계**(Python `Counter`/산술 연산)다 — 아래 "동작 모드" 절 참조 |

## 목적

환자의 **개별 발화마다** 감정 상태를 분석하고, **세션 전체**에 걸친 통합 sentiment 리포트를 생성한다. 이 출력은 두 가지 downstream 소비자에서 사용된다:

1. **F4 종단 분석** (`src/f4.py`) — **정정(wave-5/wave-6):** 과거 `TemporalSummaryAgent`(구 agent 09)가 이 역할을 맡았으나 wave-5에서 retired/archived되었다(스펙 archived, `_archive/legacy_code/agent_inventory_wave5/09_temporal_summary.md`). 비교 연산자(`_compare_scale`/`_compare_ctrs`/`_compare_sentiment`)는 `src/temporal_compare.py`로 이관되어 F4(`src/f4.py`)가 sentiment 추이 데이터의 유일한 라이브 소비자다. 번호 `09`는 현재 `EvidenceVerifierAgent`(renumbered, 이 문서와 같은 wave-6 renumbering)가 사용 중이므로, 이 자리에 더 이상 sentiment consumer가 있는 것으로 읽어서는 안 된다.
2. **HandoffGeneratorAgent(08)**: 대화 기록 내 발화별 sentiment 태깅 표시

Sentiment 분석은 **보조 정보**이며, 임상 척도(PHQ-9, GAD-7)를 대체하지 않는다.

## 동작 모드

### Mode A: 발화 단위 분석 (per-utterance)

Dialogue 진행 중 매 턴마다 호출되어 해당 발화의 감정을 분류한다.

**입력:**

| 필드 | 타입 | 설명 |
|---|---|---|
| `utterance` | `string` | 환자의 단일 발화 텍스트 |
| `turn_index` | `int` | 대화 내 턴 번호 |
| `conversation_context` | `list[dict]` | 직전 2-3턴 (맥락 파악용) |

**출력:**

```json
{
  "turn_index": 3,
  "emotions": [
    { "label": "anxiety", "intensity": 0.8 },
    { "label": "sadness", "intensity": 0.5 }
  ],
  "polarity": -0.65,
  "arousal": "high",
  "evidence_phrase": "요즘 계속 불안하고 잠을 못 자요",
  "risk_signal": false
}
```

### Mode B: 세션 통합 리포트 (session-level)

세션 종료(또는 handoff 생성 직전) 시 호출되어, 전체 발화의 sentiment를 종합 분석한다. **LLM을 호출하지 않는다** — Mode A 출력들을 입력으로 받아 감정 빈도 집계, polarity 평균, dominant emotion 산출 등을 순수 rule-based 연산(Python `Counter`/산술)으로 수행한다(`agents/sentiment_analyzer.py:140-` `_analyze_session`). 출력의 `prompt_version: "v1"`은 프롬프트가 로드되지 않는 cosmetic 라벨이다.

**입력:**

| 필드 | 타입 | 설명 |
|---|---|---|
| `per_utterance_results` | `list[object]` | Mode A 출력 목록 |
| `conversation_history` | `list[dict]` | 전체 대화 기록 |
| `session_id` | `string` | 세션 식별자 |

**출력:**

```json
{
  "session_id": "sess_20260619_001",
  "dominant_emotions": ["anxiety", "sadness"],
  "emotion_distribution": {
    "anxiety": 0.35,
    "sadness": 0.28,
    "neutral": 0.20,
    "hope": 0.10,
    "anger": 0.07
  },
  "polarity_trajectory": [
    { "turn": 1, "polarity": -0.3 },
    { "turn": 3, "polarity": -0.7 },
    { "turn": 5, "polarity": -0.8 },
    { "turn": 8, "polarity": -0.5 }
  ],
  "signal_strength": "moderate",
  "emotional_shift_detected": true,
  "shift_description": "대화 초반 경도 불안 → 중반 불안 및 슬픔 심화 → 후반 약간 안정",
  "repeated_patterns": ["불안 표현 4회 반복", "수면 관련 호소 3회"],
  "per_utterance_tags": [
    { "turn": 1, "emotions": ["neutral"], "polarity": -0.1 },
    { "turn": 2, "emotions": ["anxiety"], "polarity": -0.5 },
    { "turn": 3, "emotions": ["anxiety", "sadness"], "polarity": -0.7 }
  ],
  "timestamp": "2026-06-19T14:30:00+09:00"
}
```

## 감정 분류 체계

| Label | 한국어 | 설명 |
|---|---|---|
| `anxiety` | 불안 | 걱정, 긴장, 초조, 공포 |
| `sadness` | 슬픔 | 우울, 비탄, 상실감, 눈물 |
| `anger` | 분노 | 짜증, 적대감, 좌절 |
| `despair` | 절망 | 무망감, 무기력, 의미 상실 |
| `fear` | 공포 | 위협감, 회피 |
| `hope` | 희망 | 기대, 의지, 긍정적 기대 |
| `neutral` | 중립 | 감정적 색채 미약 |
| `relief` | 안도 | 완화, 편안함 |

**polarity**: -1.0 (극도 부정) ~ +1.0 (극도 긍정). 0.0 = 중립.
**arousal**: `low` / `medium` / `high` — 감정의 활성도/강도.
**intensity**: 0.0 ~ 1.0 — 개별 감정의 강도.

## Downstream 연동

### → F4 종단 분석 (`src/f4.py`)

**정정(wave-5/wave-6):** 아래 다이어그램은 원래 `TemporalSummaryAgent(09)`를 소비자로 기술했으나, 그 agent shell은 wave-5에서 retired/archived되었고 그 번호(09)는 이 renumbering(wave-6)에서 `EvidenceVerifierAgent`로 재사용되었다. 실제 sentiment-trend 소비자는 F4(`src/f4.py`)다.

```
session_level_sentiment (Mode B output)
  └── polarity_trajectory → F4의 일자별 sentiment 추이 데이터
  └── dominant_emotions → F4 시계열 도메인에 sentiment 도메인 추가
  └── signal_strength → F4의 종단적 sentiment 변화 direction 판정 (majority-vote 입력)
```

F4의 종단 리포트 plot 데이터에 `sentiment_polarity` 필드가 추가된다:

```json
{ "date": "2026-06-19", "PHQ-9": 15, "sentiment_polarity": -0.65, "ctrs_level": 4 }
```

### → HandoffGeneratorAgent(08)

```
per_utterance_tags (Mode B output)
  └── Section 8 (대화 기반 근거)에서 발화별 감정 태그 표시
```

Section 8 예시:

```markdown
| 턴 | 발화 | 감정 태그 | Evidence |
|---|---|---|---|
| 1 | "잠을 못 자서 왔습니다" | 😟 anxiety | [ev_msg_001] |
| 3 | "요즘 죽고 싶다는 생각이..." | 😔 despair, 🚨 risk | [ev_msg_003] |
| 5 | "약을 먹으니 조금 나아졌어요" | 🙂 hope, relief | [ev_msg_005] |
```

## 핵심 동작 규칙

1. **모든 환자 발화에 실행**: assistant 발화는 분석하지 않는다.
2. **risk_signal 연동**: despair intensity ≥ 0.8 또는 위기 관련 감정 패턴 감지 시 `risk_signal: true` 반환. SafetyClassifier의 판단을 대체하지 않으며 보조 신호로만 사용한다.
3. **문화적 맥락 반영**: 한국어 감정 표현의 특성 반영 (간접적 감정 표현, 축소 표현 등).
4. **Polarity trajectory 필수**: 대화 내 감정 변화 흐름을 시계열로 추적한다.
5. **반복 패턴 감지**: 동일 감정/표현이 3회 이상 반복되면 `repeated_patterns`에 기록한다.

## 안전 제약

1. **AI는 진단하지 않는다.** sentiment 결과를 "우울증", "불안장애" 등 진단명으로 표현하지 않는다.
2. **임상 척도를 대체하지 않는다.** sentiment는 보조 정보이며, PHQ-9/GAD-7 rule-based 점수가 우선한다.
3. **CTRS 판정을 대체하지 않는다.** risk_signal은 SafetyClassifier의 보조 신호일 뿐이다.
4. **환자의 감정을 평가하지 않는다.** "부적절한 감정" 같은 표현 금지.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| LLM 호출 실패 | `emotions: [{"label": "unknown", "intensity": 0}]`, `polarity: 0.0` 반환. downstream agent는 sentiment 없이 진행 |
| 발화가 너무 짧음 (< 5자) | `neutral` 반환, confidence 낮게 설정 |
| Mode B 입력 비어있음 | 빈 session report 반환 (`dominant_emotions: []`, `signal_strength: "none"`) |
