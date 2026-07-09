# Agent 02: Safety/Risk Classifier Agent

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `02` |
| **Agent Name** | `SafetyClassifierAgent` |
| **역할** | 환자 메시지의 자살/자해/타해/응급 위험도 분류 |
| **LLM Routing** | benchmarked (Primary: Upstage Solar Pro 3 / Secondary: LG K-EXAONE / Fallback: SKT A.X K1) |
| **프롬프트 pin** | v2 (`agents/safety_classifier.py:133` `PROMPT_VERSION`) — v3는 SM-04 계열 과잉-escalation 회귀로 롤백됨(ADR-012), 디스크에는 남아있으나 비활성 |

## 목적

모든 환자 메시지에 대해 위험도를 실시간 분류한다. **순차(sequential) 2단계 구조**(rule screening → LLM 최종 판정)로 동작하며, **LLM이 최종 판정자(final arbiter)** 다 — rule이 high/critical을 감지해도 LLM이 문맥(부정문, 과거형 등)을 근거로 그보다 낮게 하향 조정할 수 있다. **"danger-takes-priority"(더 위험한 쪽 채택 = `max`) 병합은 LLM이 사용 불가능한 fail-closed 분기에서만 적용된다**(`agents/safety_classifier.py:417-443`). CTRS 1-2에 대한 recall >= 95%를 목표로 한다. 이 에이전트는 **매 턴마다** 실행된다.

## 순차 아키텍처 (Rule Screening → LLM 최종 판정)

```
patient_message
    │
    ▼
[Step 1] Keyword Rule Screening (동기, 결정적) ── rule_level 산출
    │
    ▼
[Step 2] LLM Classification ── rule이 high/critical 감지 시 flagged keyword를 LLM에 함께 전달
    │       LLM은 rule 결과를 하향(부정 문맥 등) 또는 확정할 수 있음
    ▼
[Step 3] 최종 판정
    ├─ LLM 사용 가능 → final = LLM 판정 결과 (LLM이 최종 판정자)
    └─ LLM 사용 불가(전체 실패) → final = max(rule_level, LLM 부분결과, fail-closed 기본값 high)
                                    ("danger-takes-priority"는 이 분기에서만 적용)
```

`agents/safety_classifier.py:371-384` (`run()` docstring)이 이 흐름을 그대로 기술한다. 두 경로는 **병렬이 아니라 순차** 실행된다 — rule screening이 먼저 완료된 뒤 그 결과(및 flagged keyword)가 LLM 호출의 입력으로 전달되기 때문이다.

### Path A: Keyword Rules (Aho-Corasick)

| 키워드 패턴 | CTRS 매핑 | 비고 |
|---|---|---|
| `자살`, `죽고싶`, `유서`, `목매`, `투신`, `손목긋` | CTRS 1-2 (초응급/응급) | 즉각 crisis trigger |
| `힘들어서못살`, `희망없어`, `사라지고싶`, `다끝내고싶` | CTRS 3-4 (준응급/일반) | 추가 평가 필요 |
| `약 안먹`, `치료 중단`, `병원 안가` | CTRS 4 (일반) | 치료 순응도 위험 |
| 타해 키워드: `죽여`, `때려`, `해치` | CTRS 2 (응급) | 타해 위험 |

- 키워드 사전은 정규표현식 포함 (예: `죽.*싶`, `살.*싫`)
- 띄어쓰기 변형, 은어, 신조어 패턴 포함
- 사전 업데이트 주기: 월 1회 이상

### Path B: LLM Classification

- 입력: 환자 메시지 전문 + 직전 2턴 대화 context
- 출력: CTRS level (1-5) + confidence score + reasoning
- 문맥적 위험 감지 (키워드에 없는 간접 표현 포착)

### 최종 판정 규칙 — 정정: 병렬 merge가 아니라 "LLM이 최종 판정자"

**과거 버전 문서는 이 절에서 Path A/B를 병렬 실행 후 `min(ctrs)`(danger-takes-priority)로 항상 병합한다고 기술했으나, 실제 구현은 다르다.**

- **LLM 사용 가능 시(정상 경로): LLM 판정이 곧 최종 결과다.** rule이 CTRS 1-2를 감지해도, LLM이 문맥(부정문 "죽고 싶다는 생각은 없어요" 등)을 근거로 그보다 낮게 판정하면 그 낮은 값이 채택된다 — Path A는 그 결과를 덮어쓰지 못한다(`agents/safety_classifier.py:417-428`).
- **`danger-takes-priority`(`max(rule, llm 부분결과, fail-closed 기본값)`) 병합은 LLM을 아예 사용할 수 없는 fail-closed 분기에서만 적용된다**(`:429-443`). 이 분기 밖에서는 "더 위험한 쪽 채택"이 일반 원칙이 아니다.
- Path A(keyword)가 먼저 실행되어 rule_level을 산출하지만, 이는 **LLM 호출의 입력**(flagged phrase + rule_level을 LLM에 컨텍스트로 제공)으로 쓰일 뿐, Path A만으로 조기 확정하지 않는다.

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `patient_message` | `string` | 현재 환자 메시지 (정규화 후) |
| `conversation_context` | `array<string>` | 직전 2턴 대화 이력 |
| `patient_id` | `string` | 환자 식별자 |
| `session_id` | `string` | 세션 ID |

## 출력 (`SafetyOutput`, `schemas/safety.py`)

**정정:** 과거 버전 문서는 이 절에서 `classification`/`paths` 중첩 구조와 `merge_policy` 필드를 가진 예시를 실었으나, 실제 `SafetyOutput`은 **flat 구조**다 — 중첩 서브객체가 없고, `merge_policy` 필드 자체가 스키마에 존재하지 않는다(병합 정책은 위 "최종 판정 규칙" 절의 코드 동작으로만 존재하며, 출력 필드로 노출되지 않는다). 아래는 `SafetyOutput`(`AgentOutput` 상속 4필드 + 자체 10필드, 총 14필드) 그대로의 flat 예시다. 값은 모두 placeholder다.

```json
{
  "risk_level": "high",
  "categories": ["<risk category (placeholder)>"],
  "flagged_phrases": ["<flagged phrase (placeholder)>"],
  "confidence": 0.0,
  "rule_triggered": true,
  "llm_risk_level": "high",
  "rule_risk_level": "high",
  "ctrs_level": 2,
  "requires_human_review": true,
  "crisis_protocol_activated": true,
  "model_used": "solar-pro3",
  "prompt_version": "v2",
  "latency_ms": 0.0,
  "reason_summary": "risk classification completed (rule+LLM)"
}
```

`session_id`/`patient_id`/`timestamp`는 `SafetyOutput`/`AgentOutput`(`agents/base.py`)에 존재하지 않는 필드다 — 세션/환자 식별은 호출자 쪽(Orchestrator)이 `SafetyInput.session_id`로 관리하며, 이 에이전트의 출력 자체에는 포함되지 않는다.

## CTRS 위험도 분류 기준

| CTRS Level | 분류 | RiskLevel 매핑 | 설명 | 대응 |
|---|---|---|---|---|
| 1 | 초응급 | `critical` | 자살/자해 시도 중, 타해 시도, 약물 과다복용, 통제 불가 상태 | 일반 대화 즉시 중단, 119/112 안내, 보호자/의료진 긴급 알림, 응급실 이송 권고 |
| 2 | 고위험 | `high` | 구체적 자살/자해/타해 계획 또는 의도 확인, 수단 보유, 강한 충동, 현실검증력 저하, 급성 정신증 동반 | 일반 대화 제한, 109/119/112 안내, dashboard 긴급 alert, human review 즉시 등록 |
| 3 | 급성기 | `medium` | 환청/망상 급증, 극심한 공황, 심한 불면, 우울 악화, 일상 기능 급격 저하 | 위기 개입 안내, 빠른 전문가 상담 권고, 의료진/상담자 alert, 24-48시간 내 follow-up |
| 4 | 중증/주의 | `low` | 지속적 우울/불안, 기능 손상, 수면/식사 악화, 알코올/약물 사용 증가, 치료 필요성 높음 | 외래 진료/상담 권고, 구조화 문진 실시, human review queue 등록 가능 |
| 5 | 안정기 | `none` | 자발적 치료 의지 있음, 보호요인 존재, 위험 발화 없음, 일상 기능 유지 가능 | 일반 문진 지속, 외래 예약 안내, 자가관리 및 재평가 계획 제공 |

### CTRS ↔ RiskLevel 매핑 규칙

CTRS는 숫자가 **낮을수록 위험도가 높다.** 이는 RiskLevel enum의 직관과 반대 방향이므로 매핑에 주의가 필요하다.

```python
CTRS_TO_RISK = {
    1: "critical",   # 초응급
    2: "high",        # 고위험
    3: "medium",      # 급성기
    4: "low",         # 중증/주의
    5: "none",        # 안정기
}
```

### CTRS Crisis Flow 분기 규칙

- **CTRS 1-2 → 즉시 crisis flow 발동**: dialogue를 우회하고 위기 대응 메시지를 즉시 반환한다. Orchestrator의 모든 다른 단계를 중단한다.
- **CTRS 3 → 위기 개입 병행**: dialogue는 제한적으로 계속하되, 위기 개입 안내를 동시에 제공한다.
- **CTRS 4-5 → 정상 파이프라인 진행**: 일반 대화 및 구조화 문진 수행.

### 간접 표현 → CTRS 매핑 규칙

안전 분류는 직접적 키워드뿐 아니라 간접적 표현도 포착해야 한다. 다음은 최소 CTRS 하한 규칙이다:

| 간접 표현 예시 | 최소 CTRS |
|---|---|
| "내가 없으면 다 편할 텐데" | CTRS 3 (최소) |
| "사라지고 싶다", "다 끝내고 싶다" | CTRS 3 (최소) |
| "힘들어서 못 살겠다", "희망이 없다" | CTRS 3 (최소) |
| "죽고 싶다", "유서를 썼다" | CTRS 2 (최소) |
| 구체적 방법/장소/시간 언급 | CTRS 2 (최소) |
| 자살시도 진행 중, 약물 과다복용 | CTRS 1 (최소) |
| PHQ-9 Q9 >= 1 (자살 사고 문항 양성) | CTRS 3 (최소) |
| Active suicidal ideation (능동적 자살 사고) | CTRS 2 (최소) |

**경계 규칙:** CTRS 분류가 모호한 경우 **더 위험한 쪽(낮은 CTRS)을 선택**한다 (danger-takes-priority).

## 핵심 동작

1. **매 턴 실행**: 환자의 모든 메시지에 대해 예외 없이 실행된다. Orchestrator가 이를 보장한다.
2. **순차 실행**: Path A(keyword rule screening)가 먼저 완료되고, 그 결과(rule_level, flagged keyword)가 Path B(LLM classification) 호출의 입력 컨텍스트로 전달된다. 병렬 실행이 아니다.
3. **LLM이 최종 판정자**: LLM 사용이 가능한 한 최종 CTRS는 LLM 판정 결과다. Path A 결과만으로 조기 확정·반환하지 않는다. `danger-takes-priority`(max 병합)는 LLM을 사용할 수 없는 fail-closed 분기에서만 적용된다.
4. **Escalation 단방향**: 대화 중 CTRS level은 악화 방향으로만 변경된다. 한 번 CTRS 2가 되면 해당 세션에서 CTRS 5로 내려가지 않는다.
5. **Source/timestamp 기록**: 모든 분류 결과에 source(keyword/llm), timestamp, confidence를 기록한다.
6. **LLM reasoning 저장**: LLM의 분류 근거를 handoff report evidence로 활용하기 위해 저장한다.

## 안전 제약

1. **Recall >= 95% for CTRS 1-2.** 위험 신호를 놓치는 것(false negative)이 오탐(false positive)보다 치명적이다.
2. **AI는 진단하지 않는다.** "자살 위험이 있습니다"라고 판정하지 않는다. "자살 관련 표현이 감지되었습니다"로 표현한다.
3. **Timeout 시 안전 기본값**: LLM 응답 없으면 keyword 결과만으로 판정. Keyword도 실패하면 CTRS 2로 간주.
4. **키워드 사전 변조 방지**: 키워드 사전은 서명된 파일로 관리하며, 런타임 변경 불가.
5. **Prompt injection 방어**: 환자 메시지 내 "ignore previous instructions" 등의 패턴을 필터링한다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| LLM timeout (>2초) | Path A(keyword) 결과만으로 판정 |
| LLM primary 실패 | Secondary(K-EXAONE) → Fallback(A.X K1) |
| 전체 LLM 실패 | Keyword 결과만 사용. Keyword도 실패 시 CTRS 2 (안전 기본값) |
| Keyword engine 실패 | LLM 결과만 사용 + 인시던트 로그 |
| 양 경로 모두 실패 | CTRS 2로 간주, crisis flow 발동, 인시던트 즉시 알림 |
