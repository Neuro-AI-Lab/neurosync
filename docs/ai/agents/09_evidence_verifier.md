# Agent 09: QA & Consistency Checker Agent

> **번호 재부여 2026-07-20 (wave-6, 사용자 directive):** 구 Agent 11(`11_evidence_verifier.md`). 구번호 원본 파일은 2026-07-27 사용자 directive로 파기 — 스펙 번호 재정립: 01–11 = `apps/ai-server/prompts/` 최종 구성과 1:1.
> old→new 전체 매핑은 `docs/ai/agent_collaboration_f1f5.md`의 번호 체계 표를 참조.

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `09` |
| **Agent Name** | `EvidenceVerifierAgent` |
| **역할** | Handoff report 품질 검증 및 release gate |
| **LLM Routing** | **100% rule-based — 실제로는 LLM을 전혀 호출하지 않는다.** `agents/evidence_verifier.py`에는 router/adapter/prompt_loader 참조가 없다(정규식/패턴 매칭 기반). `agent_model_registry.yaml`은 `benchmarked`로 등록해 두었으나 코드 현실과 어긋난 등록 상태다(알려진 드리프트, 별도 BUG 예정 — 본 미션 범위에서 registry는 수정하지 않음) |

## 목적

HandoffGeneratorAgent(08)가 생성한 report를 배포 전에 검증한다. 모든 검증 항목을 통과해야만 report가 의료진에게 전달된다. 위반 사항 발견 시 **reject하고 재생성을 요청**하며, 최대 2회 재시도 후에도 통과하지 못하면 의료진에게 경고와 함께 전달한다. 이 에이전트가 **release gate** 역할을 수행한다.

## 구현 상태 (2026-07-20)

검증은 현재 **code-only**다: `agents/evidence_verifier.py`에는 모듈 어디에도 `PromptLoader`,
`ModelRouter`, adapter 참조가 없다 — 모든 체크는 report markdown에 대한 regex/pattern 매칭이며,
agent 전체 소스를 직접 읽어 확인했다. `docs/ai/prompts/evidence_verifier/v1.system.md`에 system
prompt 파일이 디스크에 존재하지만, **런타임에는 소비되지 않는다** — `evidence_verifier.py`의 어떤
코드 경로도 이를 로드하거나 참조하지 않는다. 프롬프트 디렉터리의 존재를 이 에이전트가 LLM을
호출한다는 근거로 읽어서는 안 된다 — 실제로는 호출하지 않는다.

12개 스펙 체크 중 6개가 구현되어 있다: `_check_unsupported_claims`, `_check_diagnosis_
violations`, `_check_treatment_violations`, `_check_section_completeness`,
`_check_ctrs_action_alignment`, `_check_dangling_references`(모두 regex/pattern 기반, LLM
미사용). V-04, V-06, V-10, V-11, V-12는 미구현이다 — 구현/미구현 전체 breakdown은 아래 항목별
표 참조(기존 "검증 항목" 절의 내용과 동일하며, 여기서는 날짜가 명시된 요약으로만 재기술).

## 검증 항목 (Validation Checklist) — 스펙 대비 구현 현황

실제 구현(`agents/evidence_verifier.py`)은 아래 6개 체크 함수만 존재한다: `_check_unsupported_claims`, `_check_diagnosis_violations`, `_check_treatment_violations`, `_check_section_completeness`, `_check_ctrs_action_alignment`, `_check_dangling_references`(각각 정규식/패턴 매칭, LLM 미사용). V-01..V-12 12개 항목 중 **V-04, V-06, V-10, V-11, V-12는 미구현**이다.

| 번호 | 검증 항목 | 심각도 | 설명 | 구현 상태 |
|---|---|---|---|---|
| V-01 | Evidence citation 완전성 | CRITICAL | 모든 claim에 `[ev_*]` 인용이 있는가 | 구현(`_check_unsupported_claims`) |
| V-02 | 진단적 단정 부재 | CRITICAL | 진단명을 단정하는 표현이 없는가 | 구현(`_check_diagnosis_violations`) |
| V-03 | 치료 지시 부재 | CRITICAL | 치료를 지시하는 표현이 없는가 | 구현(`_check_treatment_violations`) |
| V-04 | 구조화 점수 정확성 | CRITICAL | PHQ-9/GAD-7 등의 점수가 rule-based 계산 결과와 일치하는가 | **미구현** |
| V-05 | CTRS-조치 정합성 | CRITICAL | CTRS level과 권장 조치가 정합한가 (CTRS 1-2 → 즉시 대응 포함) | 구현(`_check_ctrs_action_alignment`) |
| V-06 | OCR/STT low-confidence 표기 | HIGH | OCR/STT confidence < 0.8 항목이 한계 섹션에 명시되어 있는가 | **미구현** |
| V-07 | 누락 위험 신호 + CTRS 일관성 | CRITICAL | Safety classifier가 감지한 위험 신호가 report에 반영되어 있는가. **CTRS level이 위험 지표와 일치하는가** (아래 세부 규칙 참조) | 부분 구현(`_check_ctrs_action_alignment`) |
| V-08 | 12개 섹션 완전성 | HIGH | 모든 섹션이 존재하는가 (데이터 없는 섹션도 "정보 없음"으로 포함) | 구현(`_check_section_completeness`) |
| V-09 | Evidence registry 정합성 | HIGH | report 내 인용된 evidence ID가 모두 registry에 존재하는가 | 구현(`_check_dangling_references`) |
| V-10 | Disclaimer 존재 | HIGH | Section 5, 11, 12에 disclaimer가 포함되어 있는가 | **미구현** |
| V-11 | 종단 비교 근거 충분성 | MEDIUM | 종단 비교에서 "unknown" 아닌 판정에 근거가 있는가 | **미구현** |
| V-12 | 시제/표현 일관성 | LOW | 보고서 내 시제와 표현이 일관적인가 | **미구현** |

## V-07 CTRS 일관성 검증 세부 규칙 — 스펙 대비 구현 현황

**정정:** V-07은 개념상 "CTRS level이 관련 위험 지표와 폭넓게 일관적인지" 교차 검증하는 취지이나, 실제 구현 함수 `_check_ctrs_action_alignment(report: str, ctrs_level: int)`(`agents/evidence_verifier.py:302-337`)은 **report 텍스트와 ctrs_level 정수만 입력받는다.** PHQ-9 점수, safety classifier의 위험 카테고리/`crisis_triggered` 플래그, 자살 계획·수단 언급 여부, 자살시도 진행 여부는 이 함수의 인자에 없고 코드 어디에도 그 값을 참조하는 로직이 없다 — 아래 6개 행 중 실제로 구현된 것은 **마지막 행(섹션 11 키워드 존재 검사)뿐**이며, 이는 위 "검증 항목" 표의 V-07 "부분 구현" 표기와 일치한다.

| 조건 | 최소 CTRS | 불일치 시 | 구현 상태 |
|---|---|---|---|
| PHQ-9 Q9 >= 1 (자살 사고 문항 양성) | CTRS 3 이하 | CTRS 4-5이면 FAIL | **미구현** (design-intent only — PHQ-9 점수가 함수 입력에 없음) |
| Active suicidal ideation (능동적 자살 사고) 감지됨 | CTRS 2 이하 | CTRS 3-5이면 FAIL | **미구현** (design-intent only — safety classifier 카테고리가 함수 입력에 없음) |
| 구체적 자살 계획/수단 언급 | CTRS 2 이하 | CTRS 3-5이면 FAIL | **미구현** (design-intent only) |
| 자살시도 진행 중 또는 직후 | CTRS 1 | CTRS 2-5이면 FAIL | **미구현** (design-intent only) |
| Safety classifier가 crisis_triggered = true 반환 | CTRS 1-2 | CTRS 3-5이면 FAIL | **미구현** (design-intent only — `crisis_triggered` 플래그가 함수 입력에 없음) |
| 섹션 11(권장 조치)에 CTRS별 필수 키워드 미포함 | CTRS 1: `119\|112\|응급`, CTRS 2: `109\|119\|긴급\|위기상담`, CTRS 3: `정신건강의학과\|109\|위기` | 미포함 시 FAIL | **구현** (`_check_ctrs_action_alignment`) — CTRS 1/2 미포함은 `severity=error`, CTRS 3 미포함은 `severity=warning` |

**FAIL 판정 시:** 위 마지막 행(구현된 유일한 체크)만 실제로 report를 reject/regenerate로 이끈다. CTRS 1/2 미포함은 `error`로 기록되어 즉시 reject(CRITICAL 위반) 대상이다. CTRS 3 미포함은 `warning`으로 기록되며, 단독으로는 reject를 유발하지 않고 다른 warning과 합산해 3건 이상일 때만 regenerate를 유발한다(`run()`의 `error_count`/`warning_count` 판정, `agents/evidence_verifier.py:133-142`) — 위 "검증 항목" 표의 V-07 CRITICAL 표기는 이 체크가 개념적으로 속한 심각도 분류이며, CTRS 3 행의 코드 레벨 `severity=warning`과는 별개다. 나머지 5개 행(미구현)은 FAIL 판정 자체가 발생하지 않는다 — 해당 조건이 코드에서 평가되지 않기 때문이다.

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `handoff_report` | `object` | HandoffGeneratorAgent가 생성한 report |
| `clinical_slots` | `object` | ClinicalSlotAgent 원본 출력 (점수 검증용) |
| `safety_classification` | `object` | SafetyClassifierAgent 원본 결과 |
| `scale_scores_rule_based` | `object \| null` | Rule-based 계산된 척도 점수 원본 |
| `ocr_results` | `array<object> \| null` | OCR 원본 결과 (confidence 검증용) |
| `retry_count` | `integer` | 현재 재시도 횟수 (0, 1, 2) |

## 출력

```json
{
  "report_id": "handoff_20260618_001",
  "verification_result": "PASS",
  "retry_count": 0,
  "checks": [
    {
      "check_id": "V-01",
      "name": "Evidence citation 완전성",
      "severity": "CRITICAL",
      "result": "PASS",
      "details": "7개 claim, 7개 citation 확인"
    },
    {
      "check_id": "V-02",
      "name": "진단적 단정 부재",
      "severity": "CRITICAL",
      "result": "PASS",
      "details": "진단적 단정 표현 미발견"
    },
    {
      "check_id": "V-03",
      "name": "치료 지시 부재",
      "severity": "CRITICAL",
      "result": "PASS",
      "details": "치료 지시 표현 미발견"
    },
    {
      "check_id": "V-04",
      "name": "구조화 점수 정확성",
      "severity": "CRITICAL",
      "result": "PASS",
      "details": "PHQ-9 report 12점 = rule-based 12점 일치"
    },
    {
      "check_id": "V-05",
      "name": "CTRS-조치 정합성",
      "severity": "CRITICAL",
      "result": "PASS",
      "details": "CTRS 4, 권장 조치에 즉시 대응 불필요"
    },
    {
      "check_id": "V-06",
      "name": "OCR/STT low-confidence 표기",
      "severity": "HIGH",
      "result": "PASS",
      "details": "OCR confidence < 0.8 항목 1건, Section 11에 표기 확인"
    },
    {
      "check_id": "V-07",
      "name": "누락 위험 신호",
      "severity": "CRITICAL",
      "result": "PASS",
      "details": "Safety classifier 결과와 report CTRS 섹션 일치"
    },
    {
      "check_id": "V-08",
      "name": "12개 섹션 완전성",
      "severity": "HIGH",
      "result": "PASS",
      "details": "12개 섹션 모두 존재"
    },
    {
      "check_id": "V-09",
      "name": "Evidence registry 정합성",
      "severity": "HIGH",
      "result": "PASS",
      "details": "인용된 7개 ID 모두 registry에 존재"
    },
    {
      "check_id": "V-10",
      "name": "Disclaimer 존재",
      "severity": "HIGH",
      "result": "PASS",
      "details": "Section 5, 11, 12 disclaimer 확인"
    },
    {
      "check_id": "V-11",
      "name": "종단 비교 근거 충분성",
      "severity": "MEDIUM",
      "result": "PASS",
      "details": "improved/unchanged 판정 모두 evidence 포함"
    },
    {
      "check_id": "V-12",
      "name": "시제/표현 일관성",
      "severity": "LOW",
      "result": "PASS",
      "details": "일관성 확인"
    }
  ],
  "critical_violations": 0,
  "high_violations": 0,
  "medium_violations": 0,
  "low_violations": 0,
  "action": "RELEASE",
  "timestamp": "2026-06-18T14:36:30+09:00"
}
```

### Reject 시 출력 예시

```json
{
  "report_id": "handoff_20260618_001",
  "verification_result": "FAIL",
  "retry_count": 1,
  "checks": [
    {
      "check_id": "V-02",
      "name": "진단적 단정 부재",
      "severity": "CRITICAL",
      "result": "FAIL",
      "details": "Section 5에서 '주요우울장애가 의심됩니다' 표현 발견. 진단적 단정 금지 위반.",
      "location": "sections.s05_mental_health_domains.candidates[0].basis",
      "suggested_fix": "'우울 영역 관련 증상이 수집되었습니다'로 변경"
    }
  ],
  "critical_violations": 1,
  "action": "REJECT_AND_REGENERATE",
  "rejection_instructions": [
    "Section 5의 '주요우울장애가 의심됩니다'를 '우울 영역 관련 증상이 수집되었습니다'로 수정"
  ],
  "timestamp": "2026-06-18T14:36:30+09:00"
}
```

## 핵심 동작

1. **부분 구현 검증**: 스펙상 12개 검증 항목 중 6개 체크 함수가 V-01/02/03/05/07/08/09(7개 항목 — `_check_ctrs_action_alignment` 하나가 V-05와 V-07을 함께 커버)를 수행한다. V-04/06/10/11/12는 미구현이다(위 "검증 항목" 표 참조).
2. **CRITICAL 위반 시 즉시 reject**: CRITICAL 심각도 항목이 하나라도 FAIL이면 report를 reject한다.
3. **Reject → 재생성 루프**: reject 시 violation 상세와 수정 지시를 HandoffGeneratorAgent에 전달한다. 최대 2회 재시도.
4. **3회 실패 시 경고 배포**: 2회 재시도 후에도 CRITICAL 위반이 남아있으면, 경고 메시지를 첨부하여 의료진에게 전달한다. report를 차단하지는 않는다 (의료진 판단 우선).
5. **점수 교차 검증 — 미구현(V-04)**: report 내 구조화 척도 점수를 rule-based 계산 원본과 대조하는 로직은 설계 의도이나 현재 구현되어 있지 않다.
6. **진단/치료 표현 패턴 탐지**: 금지 표현 패턴 사전 기반 정규식 매칭으로 report 텍스트를 스캔한다(LLM 미사용).
7. **Evidence trace**: report 내 모든 `[ev_*]` ID가 evidence registry에 존재하고, 원본 데이터와 일치하는지 검증한다.

## 금지 표현 패턴 (예시)

| 카테고리 | 패턴 예시 |
|---|---|
| 진단적 단정 | `~장애`, `~증`, `~병`, `의심됩니다`, `진단`, `확진` |
| 치료 지시 | `처방`, `투약`, `입원`, `~해야 합니다`, `~하세요`, `권고합니다` |
| 과도한 확신 | `확실히`, `분명히`, `틀림없이` |

- 문맥 의존적 예외(예: "이전 진단서에 우울증이 기재되어 있었습니다"는 허용)의 판별 방식은 정규식/패턴 매칭 로직의 세부 구현에 달려 있으며, LLM 기반 판별이 아니다(위 "LLM Routing" 상태 참조).

## 안전 제약

1. **Release gate 역할**: 이 에이전트를 통과하지 않은 report는 의료진에게 전달되지 않는다.
2. **CRITICAL 위반 무시 금지**: CRITICAL 위반은 어떤 경우에도 무시할 수 없다. 3회 실패 시에도 경고를 첨부한다.
3. **자동 수정 금지**: Verifier는 report를 직접 수정하지 않는다. 수정은 HandoffGeneratorAgent가 수행한다.
4. **검증 로그 보존**: 모든 검증 결과(PASS/FAIL)를 로그에 저장한다. 추후 감사(audit)에 활용한다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| 3회 연속 CRITICAL 실패 | Report에 상세 경고를 첨부하여 의료진에게 전달. 차단하지 않음 |

**정정:** 이 에이전트는 LLM을 호출하지 않으므로 "LLM 검증 실패"/"전체 LLM 실패"/"검증 timeout"(LLM 응답 대기 관련) 행은 as-built 상태에 존재하지 않는다(과거 버전 문서의 서술 제거). V-04/06/10/11/12의 미구현은 "실패"가 아니라 해당 체크가 애초에 수행되지 않는 상태이며, 그 항목들은 결과에 나타나지 않는다.
