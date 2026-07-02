# PR: feat(ai-server): F1 autonomous dialogue pipeline — multi-agent orchestration

> **Base**: `Master` ← **Branch**: `feat/f1-pipeline-refinement`

---

## Summary

F1 자율 대화 기반 사전문진 파이프라인을 구현합니다. Safety, Slot, Dialogue 3개 Agent가 매 턴 협업하여 12개 표준 임상 슬롯을 수집합니다.

- F1 Pipeline Orchestrator (`f1.py`) — 세션 실행, Agent 호출 순서 제어
- Safety Classifier 재설계 — Rule screening + LLM 문맥 판정 (C-architecture)
- Dialogue Agent 역할 분리 — 응답 생성만 담당 (슬롯 추출/위험도 판단 제거)
- Clinical Slot Agent 정제 — flat 12-key schema, 부정 응답 수집, 비표준 키 차단
- 3개 시스템 프롬프트 간결화 — 593줄 → 179줄 (70% 감소)
- 4VP 시뮬레이션 검증 완료 — 이슈 0건

---

## Changes

### Core Pipeline

| File | Change |
|------|--------|
| `src/f1.py` | **NEW** — F1 orchestrator. Safety→Slot→Dialogue 매 턴 실행, Turn 0 slot 추출, auto session termination, handoff generation, CLI entry point |
| `src/agents/dialogue.py` | **NEW** — 공감 응답 + 유도 질문 생성 전담. `_build_slot_context()`로 매 턴 동적 지시 생성 (수집 완료 슬롯 표시, 타겟 슬롯 지정, 공감 반복 방지, 이전 질문 추적) |
| `src/agents/safety_classifier.py` | **REWRITE** — 하드코딩 프롬프트 제거 → PromptLoader. Rule=1차 스크리닝, LLM=최종 판정. 부정 문맥 감지 |
| `src/agents/clinical_slot.py` | **REWRITE** — flat 12-key output, `_KEY_ALIASES` 비표준→표준 매핑, 부정 응답 수집, `safety_flag` 로직 제거 |

### Schemas

| File | Change |
|------|--------|
| `src/schemas/dialogue.py` | `DialogueLLMResponse`: `slot_updates`/`risk_level` 제거 → `assistant_response`만. `extra="ignore"` |
| `src/schemas/clinical_slot.py` | `safety_flag`/`safety_flag_reason` 필드 제거 |

### System Prompts

| File | Lines | Change |
|------|-------|--------|
| `prompts/dialogue/v1.system.md` | 228→54 | 역할을 응답 생성으로 제한. slot/risk 출력 요구 제거 |
| `prompts/safety_classifier/v1.system.md` | 208→58 | 코드 스키마와 출력 일치. 부정 문맥/증상악화 규칙 추가 |
| `prompts/clinical_slot/v1.system.md` | 157→67 | flat 12-key, 부정 응답 변환 예시 7개. nested 구조 금지 |

### Simulation & Documentation

| File | Description |
|------|-------------|
| `tests/simulation/patient_llm.py` | K-EXAONE 기반 Patient Simulator. VP persona MD 로드 |
| `docs/ai/feature_development_status.md` | F1 기능 개발 현황, Agent 입력 프롬프트 양식, 연동 관계도 |
| `docs/ai/f1_issue_resolution_report.md` | 초기 10건 이슈 → 해결 과정 총정리 |
| `simulation_results/VP-{001~004}/` | 최신 시뮬레이션 결과 (JSON + report + checklist) |

---

## Architecture

### Per-Turn Agent Execution Flow

```
Patient Message
     │
     ▼
  [Step 1] Safety Agent
     │  입력: patient_message + conversation_history
     │  출력: risk_level, ctrs_level, crisis
     │  crisis=True → 109/119 안내 + 세션 종료
     │
     ▼ crisis=False
  [Step 2] Slot Agent (매 턴, Dialogue 전)
     │  입력: conversation_history + patient_message + filled_slots
     │  출력: extracted_slots → filled_slots에 merge (12 standard keys만)
     │
     ▼
  [Step 3] Dialogue Agent (최신 slots + safety 결과 사용)
     │  입력: patient_message + conversation_history
     │        + filled_slots (Slot Agent 갱신 후)
     │        + safety_result (Safety Agent 결과)
     │  출력: assistant_response (AI 발화)
     │
     ▼
  [Step 4] Handoff Check
     질문 가능 슬롯 모두 수집 → 세션 종료
```

### Agent Role Separation

| Agent | Does | Does NOT |
|-------|------|----------|
| **Safety** | CTRS 위험도 분류 | 응답 생성, 슬롯 추출 |
| **Slot** | 12 Standard Slots 추출 | 응답 생성, 위험도 판단 |
| **Dialogue** | 공감 응답 + 유도 질문 | 슬롯 추출, 위험도 판단, coverage 계산 |
| **Orchestrator (f1.py)** | 호출 순서, 공유 상태, coverage, 세션 종료 | LLM 직접 호출 |

---

## Resolved Issues (10건)

### P0 — Safety Critical

| ID | Issue | Resolution |
|----|-------|------------|
| P0-1 | Crisis flag=True인데 crisis response 없음 (VP-004) | Turn 0부터 Safety 호출. crisis 시 109/119 안내 + 즉시 종료 |
| P0-2 | Patient turn마다 Safety 미호출 | 매 턴 강제 호출. 모든 턴에 CTRS 결과 기록 |
| P0-3 | 부정 응답("없어요") 미수집 → risk_assessment 누락 | 프롬프트 부정 응답 예시 7개 + 파싱 로깅 + 12-key 필터 |

### P1 — Dialogue Quality

| ID | Issue | Resolution |
|----|-------|------------|
| P1-1 | 반복 질문 루프 (VP-001: "괜찮으신가요?" 반복) | 슬롯 수집 완료 시 auto 종료 + 이전 질문 추적 + 직전 타겟 재타겟 방지 |
| P1-2 | next_target_slot 미따름 | 실행 순서 변경: Slot→Dialogue (Dialogue가 최신 slots 참조) |
| P1-3 | 세션 종료 직전 질문 던지고 종료 | `all_missing` 비었을 때 요약 모드 전환 |
| P1-4 | VP-002 재상담 자동 주입 | `--followup-from` 명시 시에만 prior_handoff 활성화 |

### P2 — Schema / Report

| ID | Issue | Resolution |
|----|-------|------------|
| P2-1 | 비표준 키 혼입 (VP-002: 11개) | `ALL_SLOT_KEYS` 필터 + 프롬프트 "12개 key 외 사용 금지" |
| P2-2 | Coverage 허위 표시 (100%인데 내부 60%) | orchestrator에서 ESSENTIAL_SLOT_KEYS 기준 계산 |
| P2-3 | Hallucination (표정 관찰, PHQ 점수 삽입) | 프롬프트 간결화 + `_NO_QUESTION_SLOTS`로 관찰 슬롯 질문 차단 |

---

## Test Plan

- [x] VP-001 (초진 경증): 3턴, crisis 없음, coverage 80%, 이슈 0건
- [x] VP-002 (첫 상담): 3턴, crisis 없음, coverage 80%, 이슈 0건
- [x] VP-003 (초진 중증): Turn 0 CTRS 2 crisis 정상 발동, coverage 80%
- [x] VP-004 (첫 상담): 3턴, crisis 없음, coverage 80%, 이슈 0건
- [x] 비표준 슬롯 키: 4VP 모두 0건
- [x] 공감 문구 반복: 최대 2회 (이전 10회)
- [x] 메타 응답 누출 ("지시에 따라 응답하겠습니다"): 0건
- [x] medical_history 부정 응답 수집: 4VP 모두 정상

---

Generated with [oh-my-agent](https://github.com/first-fluke/oh-my-agent)
