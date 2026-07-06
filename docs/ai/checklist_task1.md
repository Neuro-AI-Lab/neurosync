# Task 1 개발/검증 체크리스트 (v2)

> AI 기반 사전문진 Handoff Report 생성 (기능 1-1 ~ 1-5)
> **Version**: v2.0 | **Date**: 2026-07-06
> **기준 문서**: `PRD_task1_v2.md` | **작업 보고**: `development_report.md` (감사 근거: DR-001)
> 이전 버전 체크리스트/이슈/리포트는 `docs/ai/backups/` 참조.

## ID 형식 및 상태

`T1-Fn-{TYPE}-{SEQ}` — ID는 v1에서 승계하며 전역적으로 증가한다 (재사용 금지).

| 상태 | 의미 |
|---|---|
| `[ ]` | TODO |
| `[~]` | IN_PROGRESS / 부분 완료 |
| `[x]` | DONE (증거 유효) |
| `[!]` | BLOCKED / **REGRESSED** (완료였으나 회귀·증거 무효화) |

## v1 → v2 상태 조정 내역 (2026-07-06 통합 감사 반영)

2026-07-06 3-agent 통합 감사(QA 코드 감사, Critic 검증 타당성 감사, 아키텍처 갭 분석 — `development_report.md` DR-001)에 따라 v1의 `[x]` 중 다수가 조정되었다. 핵심 사유:

1. **서버 부팅 불가** (ISS-024): `orchestrator.py:41`이 삭제된 `trend_plotter`를 import → `src.main` import 실패, 전체 라우트 다운.
2. **머지 회귀** (ISS-025/026): ISS-020 fix(scale_scores/risk_events 인계)가 후속 머지에서 소실, ISS-019 fail-closed가 부분 소실(LLM 전면 장애 시 fail-open 실증됨).
3. **Slot 날조** (ISS-027): clinical_slot 프롬프트 예시가 slot 값으로 verbatim 유입 — 07-03 F1 "pass" 근거 무효화.
4. **격리 테스트** (ISS-033): keyword recall, survey scoring, orchestrator, 12-section 테스트가 `_backup/tests_old/`로 이동되어 활성 스위트에 부재 — 다수 `[x]`의 회귀 방어선 상실.

---

## Phase 1 — 상태 (감사 반영)

### F0: 공통/Orchestrator (T1-F0-*)

| ID | Type | 항목 | 상태 | 근거/비고 |
|---|---|---|---|---|
| T1-F0-DEV-001 | DEV | Orchestrator state machine 구현 (11-state) | [x] | Stage 0 복구로 부팅 정상화 (ISS-024 해결), 23 unit test 활성 green |
| T1-F0-DEV-002 | DEV | CTRS <-> RiskLevel 매핑 enum 구현 | [x] | RPT-001 |
| T1-F0-DEV-003 | DEV | agent_model_registry.yaml 전체 agent 등록 확인 | [x] | 13 agent 키 확인 |
| T1-F0-DEV-004 | DEV | PromptLoader 경로 설정 및 검증 | [x] | RPT-008 |
| T1-F0-CFG-001 | CFG | Docker Compose AI server 개발 환경 확인 | [ ] | - |
| T1-F0-CFG-002 | CFG | shared-contracts 패키지 동기화 | [ ] | - |
| T1-F0-DOC-001 | DOC | PRD_task1 작성 | [x] | v2: `PRD_task1_v2.md` |
| T1-F0-DOC-002 | DOC | checklist_task1 작성 | [x] | 본 문서 (v2) |
| T1-F0-DOC-003 | DOC | 가상 환자 Persona VP-001~VP-004 작성 | [x] | - |
| T1-F0-DOC-004 | DOC | Patient LLM 시뮬레이션 사양서 작성 | [x] | spec ↔ f1.py 불일치 다수 (drift 목록 DR-001) — 갱신 필요 |
| T1-F0-VER-001 | VER | Orchestrator 전체 파이프라인 e2e 테스트 | [~] | Stage 0 후 mocked-level e2e 테스트 복원 green. 실데이터 재검증은 T1-F0-VER-003 |
| T1-F0-VER-002 | VER | 전체 VP 4명 통합 시뮬레이션 | [!] | 07-03 런 evidence 무효화 (ISS-027 slot 날조) — G-F 이후 재실행 |

### F1: 자율 대화 기반 문진 (T1-F1-*)

| ID | Type | 항목 | 상태 | 근거/비고 |
|---|---|---|---|---|
| T1-F1-DEV-001 | DEV | SafetyClassifierAgent CTRS 5단계 매핑 | [x] | RPT-002 |
| T1-F1-DEV-002 | DEV | InputNormalizerAgent 구현 | [~] | 코드 존재하나 **어디서도 호출되지 않는 dead code** + 프롬프트↔스키마 drift (ISS-039) |
| T1-F1-DEV-003 | DEV | STT Agent + SKT A.X adapter 구현 | [!] | 벤더 계약 대기 (ISS-011) |
| T1-F1-DEV-004 | DEV | OCR Agent + Upstage Document Parse adapter 구현 | [ ] | ISS-011 |
| T1-F1-DEV-005 | DEV | DialogueAgent slot coverage tracking | [x] | 역할 분리 후 f1.py가 coverage 전담 |
| T1-F1-DEV-006 | DEV | /ai/chat/respond Orchestrator 연동 리팩토링 | [~] | 부팅 정상화(Stage 0). slot 누적 불능(ISS-029)은 T1-F0-DEV-006에서 해결 |
| T1-F1-DEV-007 | DEV | POST /ai/stt/transcribe 라우트 | [!] | T1-F1-DEV-003 선행 |
| T1-F1-DEV-008 | DEV | POST /ai/ocr/parse 라우트 | [ ] | T1-F1-DEV-004 선행 |
| T1-F1-DEV-009 | DEV | safety_classifier prompt 고도화 | [x] | 07-03 v1 58줄. 간접표현 하한표 방향 모호성은 T1-F1-DEV-017에서 함께 수정 |
| T1-F1-DEV-010 | DEV | dialogue prompt 고도화 | [x] | 07-03 v1 54줄 |
| T1-F1-DEV-011 | DEV | SentimentAnalyzerAgent 구현 (Mode A/B) | [x] | RPT-011. 단 f1.py 미연동 (T1-F1-DEV-014) |
| T1-F1-DEV-012 | DEV | SentimentAnalyzer schema 정의 | [x] | RPT-011 |
| T1-F1-DEV-013 | DEV | SentimentAnalyzer prompt v1 | [x] | RPT-005 |
| T1-F1-VER-001 | VER | VP-001 자율 대화 시뮬레이션 (초진 경증) | [!] | 07-03 evidence 무효화 (slot 날조, CTRS 4 vs spec 5) — G-F 후 재실행 |
| T1-F1-VER-002 | VER | VP-003 자율 대화 시뮬레이션 (crisis) | [x] | 위기 감지+109/119+즉시종료는 2회 재현으로 유효. slot 값은 무효 (재검증은 VER-014) |
| T1-F1-VER-003 | VER | Safety gate CTRS 1-2 crisis bypass 통합 테스트 | [x] | VP-003 pipeline 레벨 재현 |
| T1-F1-VER-004 | VER | STT->InputNormalizer 정규화 정확도 | [!] | T1-F1-DEV-003 선행 |
| T1-F1-VER-005 | VER | Slot coverage convergence (15턴 내 0.7) | [!] | 07-03 "3턴 내 0.8"은 날조 fill의 산물 (ISS-027/034). coverage 재정의(DEV-019) 후 재측정 |
| T1-F1-VER-006 | VER | 위기 키워드 recall >= 95% 회귀 테스트 | [x] | Stage 0에서 활성 복원, 40 tests green (ISS-038 칼로리 오탐 케이스 포함) |
| T1-F1-VER-007 | VER | SentimentAnalyzer per-utterance 정확도 | [x] | RPT-018 |
| T1-F1-VER-008 | VER | SentimentAnalyzer session-level 정합성 | [x] | RPT-018 |

### F2: RAG 기반 정신건강 영역 추론 (T1-F2-*) — 미착수 (정직하게 [ ] 유지됨)

| ID | Type | 항목 | 상태 | 비고 |
|---|---|---|---|---|
| T1-F2-DEV-001 | DEV | TemporalRetrieverAgent 구현 (LLM-only 모드 우선) | [ ] | agent/schema 파일 자체가 없음. 프롬프트만 존재 (orphan) |
| T1-F2-DEV-002 | DEV | pgvector embedding 저장/검색 모듈 | [ ] | DB 확정 대기 |
| T1-F2-DEV-003 | DEV | POST /ai/temporal/retrieve 라우트 | [ ] | - |
| T1-F2-DEV-004 | DEV | RAG scoring formula | [ ] | - |
| T1-F2-CFG-001 | CFG | pgvector extension (placeholder) | [ ] | - |
| T1-F2-VER-001 | VER | VP-002 재진 데이터 retrieval 테스트 | [ ] | 종단 데이터셋 필요 (T1-F1-VER-009) |
| T1-F2-VER-002 | VER | VP-004 재진 데이터 retrieval 테스트 | [ ] | 상동 |
| T1-F2-VER-003 | VER | 초진 empty retrieval 테스트 | [ ] | - |
| T1-F2-VER-004 | VER | Retrieval ranking 품질 검증 | [ ] | - |

### F3: 구조화된 사전문진 설문 (T1-F3-*)

| ID | Type | 항목 | 상태 | 근거/비고 |
|---|---|---|---|---|
| T1-F3-DEV-001 | DEV | ClinicalSlotAgent 구현 (12 Standard Slots) | [~] | 구현 존재하나 **프롬프트 예시 echo 날조 결함** (ISS-027) — DEV-017로 수정 |
| T1-F3-DEV-002 | DEV | POST /ai/slots/extract 라우트 | [x] | 단 safety gate 없이 원문 수용 (DR-001 참고) |
| T1-F3-DEV-003 | DEV | Rule-based scoring engine (5개 척도) | [x] | 39 boundary test — 감사에서 견고성 확인 (positive) |
| T1-F3-DEV-004 | DEV | POST /ai/survey/score 라우트 | [x] | PHQ-9 Q9 → safety_referral 동작 확인 |
| T1-F3-DEV-005 | DEV | Survey Planner 로직 Orchestrator 통합 | [!] | `plan_surveys`/`score_and_check_safety` **호출자 0 — dead code** (ISS-029 연관) |
| T1-F3-VER-001 | VER | PHQ-9 scoring unit test | [x] | Stage 0에서 활성 복원 green |
| T1-F3-VER-002 | VER | GAD-7 scoring unit test | [x] | 상동 |
| T1-F3-VER-003 | VER | VP별 slot extraction 정확도 비교 | [!] | RPT-018 실제 내용은 키 멤버십/산술 검증 — **정확도 측정 아님** (항목명 과대). VER-013으로 대체 수행 |
| T1-F3-VER-004 | VER | 자살 문항 양성 시 Safety 연동 테스트 | [~] | 로직 단위검증은 됐으나 소비자가 dead code — 통합 레벨 재검증 필요 |

### F4: 종단적 상태 추론 (T1-F4-*)

| ID | Type | 항목 | 상태 | 근거/비고 |
|---|---|---|---|---|
| T1-F4-DEV-001 | DEV | TemporalSummaryAgent 구현 | [x] | rule-engine (LLM 아님 — 프롬프트 문서와 drift, DR-001). ISS-014/015/016 수정 반영 |
| T1-F4-DEV-002 | DEV | POST /ai/temporal/summarize 라우트 | [x] | 단 prior 데이터 공급자가 시스템에 없음 (F2 미구현) |
| T1-F4-DEV-003 | DEV | Direction classification (majority vote) | [x] | RPT-014/020 |
| T1-F4-DEV-004 | DEV | Plot-ready time-series 생성 | [x] | Stage 0에서 trend_plotter 복원, 테스트 green |
| T1-F4-VER-001 | VER | VP-002 종단 비교 (호전) | [~] | 합성 수치 unit test만. 실데이터 재검증 = VER-005 |
| T1-F4-VER-002 | VER | VP-004 종단 비교 (악화) | [~] | 상동. "새 증상 감지"는 현 rule 엔진으로 불가 (RPT-021 자인) |
| T1-F4-VER-003 | VER | 초진 "unknown" 반환 | [x] | RPT-014 |
| T1-F4-VER-004 | VER | 모순 감지 테스트 | [x] | RPT-016. 테스트 격리 — 복원 필요 |

### F5: Handoff Report 생성 (T1-F5-*)

| ID | Type | 항목 | 상태 | 근거/비고 |
|---|---|---|---|---|
| T1-F5-DEV-001 | DEV | 12-section 템플릿 강화 | [x] | RPT-009 |
| T1-F5-DEV-002 | DEV | Evidence registry 완전성 강화 | [x] | RPT-009 |
| T1-F5-DEV-003 | DEV | CTRS-action 일관성 검증 | [!] | 구현됐으나 **호출자가 ctrs_level을 전달하지 않아 dead code** (ISS-030) |
| T1-F5-DEV-004 | DEV | PDF/JSON 듀얼 출력 | [!] | `report_renderer.py` 삭제(58db676) — **producer 부재, 회귀** |
| T1-F5-DEV-005 | DEV | /ai/handoff/generate 전체 파이프라인 연동 | [~] | 라우트 유효. 단 orchestrator 경로는 ISS-025(scale/risk 소실)+ISS-028(slot 9종 drop) |
| T1-F5-VER-001 | VER | VP-001 handoff 생성 + 검증 | [~] | 합성 slot 입력. 실데이터 재검증 = VER-007/008 |
| T1-F5-VER-002 | VER | VP-002 handoff (종단 포함) | [~] | 상동 |
| T1-F5-VER-003 | VER | VP-003 handoff (고위험) | [~] | 상동 |
| T1-F5-VER-004 | VER | VP-004 handoff (악화) | [~] | 상동 |
| T1-F5-VER-005 | VER | 12-section 완전성 자동 검증 | [x] | Stage 0에서 test_handoff_sections 복원 green |
| T1-F5-VER-006 | VER | Evidence citation 100% coverage | [x] | Stage 0에서 test_evidence_coverage 복원 green |

---

## Phase 2 — Stage 0 긴급 복구 (Gate G-0) — **완료 (2026-07-06, QA gate APPROVE-WITH-NOTES, DR-002)**

| ID | Type | 항목 | 상태 | 해결 이슈 |
|---|---|---|---|---|
| T1-F0-DEV-008 | DEV | 서버 부팅 복구: `trend_plotter` 복원 | [x] | ISS-024. `import src.main` OK, test_trend_plotter green |
| T1-F0-DEV-009 | DEV | ISS-020 fix 재적용: `_build_handoff_input`에 scale_scores/risk_events 인계 | [x] | ISS-025. 회귀 테스트 2/2 green, fix 브랜치와 line-identical |
| T1-F1-DEV-016 | DEV | Safety fail-closed 재수정 (`_fail_closed_result`, pre-adapter try/except, `_max_risk` ordinal 병합) + 회귀 테스트 6건 + ISS-038 칼로 키워드 anchoring | [x] | ISS-026/038. QA 독립 probe로 outage fail-closed 실증 |
| T1-F0-DEV-010 | DEV | 격리 테스트 복원: 22/23 파일 복원(12-slot 스키마 적응), pytest-timeout 설치+활성화 | [x] | ISS-033. 전체 354 passed. test_report_renderer만 잔류(대상 미복원, 소비자 0) |
| T1-F3-DEV-007 | DEV | ISS-042 수정: `routes/slots.py` dangling `safety_flag` 참조 제거 + 라우트 회귀 테스트 (QA gate 발견, 기존 결함 — 성공 응답이 500) | [x] | ISS-042. red-then-green 검증, 전체 356 passed |

## Phase 2 — F1 grounding 재검증 (Gate G-F)

| ID | Type | 항목 | 상태 | 해결 이슈 |
|---|---|---|---|---|
| T1-F1-DEV-017 | DEV | clinical_slot 프롬프트 재작성: 예시 값을 합성 placeholder로 교체, "묻고 답하지 않은 슬롯은 null" 강제, 1턴 대화 회귀 테스트 (chief_complaint/HPI 외 fill 0 assert) | [ ] | ISS-027 |
| T1-F1-DEV-018 | DEV | risk_assessment 무결성 규칙: Safety 출력 또는 SI 문답에서만 채움. ungrounded 상태로 세션 종료 금지, 비위기 세션에서 SI 질문 필수 assert | [ ] | ISS-027 |
| T1-F1-DEV-019 | DEV | Coverage 재정의: grounded-slot / 질문 가능 8-slot 기준 병행 보고, 0턴 세션 = 0% | [ ] | ISS-034 |
| T1-F1-VER-014 | VER | Slot grounding 자동 감사: 모든 slot 값에 지지 발화 span 요구, 07-03 런 4건 소급 판정(날조 슬롯 수 공표) | [ ] | ISS-027 |
| T1-F1-VER-010 | VER | 재현성: VP당 n>=3 반복 런, coverage/CTRS/turns/날조율 분산 보고 | [ ] | G2 |
| T1-F1-VER-011 | VER | 장기 세션: 조기 종료 비활성 10턴+ 런, 반복 루프·피로도 검증 | [ ] | G3 |

## Phase 2 — Safety 심층 + 경로 통일 (Gate G-B, G-C)

| ID | Type | 항목 | 상태 | 해결 이슈 |
|---|---|---|---|---|
| T1-F1-DEV-022 | DEV | **Safety Probe 모드** (ISS-035 다면 개선 L1-L2): CTRS 3 + {suicidal_ideation, self_harm} category 감지 시 round-robin 슬롯 질문을 중단하고 구조화 안전 탐문(빈도/계획/수단/의도/보호요인) 질문을 강제 주입. 세션 위험 latch(risk floor = CTRS 3) 설정 | [ ] | ISS-035 |
| T1-F1-DEV-023 | DEV | Safety Probe 승급/유지 규칙 (L2-L3): 탐문 응답에 Safety 재분류 실행 — 계획/수단/의도 노출 시 CTRS 2 승급→위기 프로토콜, 부인 시 grounded `risk_assessment` 기록(+109 안내 문구 삽입) 후 문진 지속. 탐문 전 handoff-ready 종료 금지 | [ ] | ISS-035, ISS-027 연계 |
| T1-F1-VER-012 | VER | Safety 시나리오 매트릭스 (파이프라인 레벨, 스크립트 환자): 중간 턴 위기 전환, 부정 문맥, 간접·masked 표현, **CTRS3+자해사고 → probe 발동·승급·비승급 3분기**, 복약 순응 오탐 0 | [ ] | G4, ISS-035 |
| T1-F0-DOC-005 | DOC | ISS-035 정책 문서화: `_simulation_spec.md` §4.4 조건부 위기 대응을 Safety Probe 프로토콜로 재정의 + safety prompt 간접표현 CTRS 하한표 방향 모호성 수정("N단계 이하(고위험 방향)") | [ ] | ISS-035, ISS-041 일부 |
| T1-F1-DEV-020 | DEV | 위기 핫라인 상수 통일 (109/119/112): orchestrator.py·f1.py·verifier·테스트·문서 | [ ] | ISS-032 |
| T1-F0-DEV-005 | DEV | `SlotData`(handoff)를 canonical 12-slot으로 정합화 (S1) | [ ] | ISS-028 |
| T1-F0-DEV-006 | DEV | orchestrator.py slot 키 canonical 통일 + dialogue loop 내 ClinicalSlot 매 턴 호출 (S2) | [ ] | ISS-028/029 |
| T1-F0-DEV-007 | DEV | f1.py ↔ orchestrator.py coverage·종료조건·안전 실패 처리 단일화 (S4) — 단일 프로덕션 경로 결정 | [ ] | G8 |
| T1-F5-DEV-007 | DEV | EvidenceVerifier에 ctrs_level 전달 + 발화-보고서 일치(Check 8) 구현 + **CTRS 3 보고서에 "24-48시간 내 정신건강의학과 평가 권고" 문구 필수 검증** (ISS-035 L4) — slot 날조 탐지선 | [ ] | ISS-030, ISS-027/035 방어 |
| T1-F1-DEV-021 | DEV | followup handoff 생성기 수정: min-CTRS fallback 제거(위기 세션 CTRS 5 오기록), 12-section 표준 형식, 산출물 디스크 저장 | [ ] | ISS-036 |

## Phase 2 — 종단 프로토콜 + 기능별 파이프라인 (Gate G-A, G-D)

| ID | Type | 항목 | 상태 | 선행 조건 |
|---|---|---|---|---|
| T1-F1-DEV-014 | DEV | SentimentAnalyzer f1.py 루프 연동 (턴별 Mode A + 세션 Mode B, sentiment.json 저장) | [ ] | G-F |
| T1-F1-DEV-015 | DEV | 종단 세션 러너: S1→Q1→S2→Q2→S3 자동 실행, VP별 종단 데이터셋 축적 | [ ] | T1-F1-DEV-014, DEV-021 |
| T1-F1-VER-009 | VER | Follow-up 시뮬레이션: 4VP S2/S3 — prior 참조 정확성, 약물 조정 문답, delta 중심 질문 검증 | [ ] | T1-F1-DEV-015 |
| T1-F1-VER-013 | VER | Slot faithfulness: persona ground truth 대비 정량 평가 (필수 slot 정확도 >= 0.8) | [ ] | T1-F1-VER-009 |
| T1-F3-DEV-006 | DEV | `f3.py` 파이프라인: F1 산출물 → 척도 선택 rule → PatientLLM 문항 응답(또는 --mode expected) → 채점 → Q9 양성 시 Safety 재평가. survey.json 저장 | [ ] | G-0 |
| T1-F3-VER-005 | VER | 실 F1 세션 기반 설문 선택 적합성 + Q9 연동 E2E | [ ] | T1-F3-DEV-006 |
| T1-F3-VER-006 | VER | PHQ-4 subscale / WHO-5 변환 / AUDIT-C cut-off boundary 테스트 활성 스위트 확인 | [ ] | T1-F0-DEV-010 |
| T1-F4-DEV-005 | DEV | `f4.py` 파이프라인: 종단 데이터셋(t1..tN) → sentiment 집계 → TemporalSummary → temporal.json | [ ] | T1-F1-DEV-015 |
| T1-F4-VER-005 | VER | 실 종단 데이터 direction: VP-002 improved / VP-004 worsened / 초진 unknown | [ ] | T1-F4-DEV-005 |
| T1-F4-VER-006 | VER | plot_data 실데이터 무결성 (점수 출처 추적) | [ ] | T1-F4-VER-005 |
| T1-F5-DEV-006 | DEV | `f5.py` 파이프라인: 12-slot→SlotData 매핑, risk_events 추출(CTRS<=3 턴), verifier 루프, handoff.md/json 저장. f1 --followup-from이 이 산출물을 우선 소비 | [ ] | T1-F0-DEV-005 |
| T1-F5-VER-007 | VER | 실데이터 handoff: Section 9 종단 변화 = F4 출력 일치 | [ ] | T1-F5-DEV-006, T1-F4-VER-005 |
| T1-F5-VER-008 | VER | Evidence 원문 추적성: Section 12 registry ↔ 대화 원문 자동 대조 | [ ] | T1-F5-DEV-006 |
| T1-F2-DEV-005 | DEV | `f2.py` 파이프라인 (T1-F2-DEV-001 구현 후) | [ ] | T1-F2-DEV-001 |

## Phase 2 — 통합 (Gate G-E)

| ID | Type | 항목 | 상태 | 선행 조건 |
|---|---|---|---|---|
| T1-F0-VER-003 | VER | 통합 E2E: F1→F3→F4→F5 전 체인, 4VP, EvidenceVerifier passed, 날조 0건 | [ ] | G-D 전체 |
| T1-F0-VER-004 | VER | QA/Critic 통합 감사 이슈(ISS-024~040) 전건 소거 확인 | [ ] | 전 Stage |

---

## 요약 통계

| 구분 | Phase 1 | Phase 2 신규 | 합계 |
|---|---|---|---|
| DEV | 35 | 20 | 55 |
| VER | 28 | 16 | 44 |
| CFG | 3 | 0 | 3 |
| DOC | 4 | 1 | 5 |
| **계** | **70** | **37** | **107** |

Phase 1 상태 분포 (Stage 0 완료 후): `[x]` 32 · `[~]` 12 · `[!]` 9 · `[ ]` 17
**Gate 순서: ~~G-0(긴급 복구)~~ 완료(2026-07-06) → G-F(grounding 재검증) ← 다음 → G-A/B/C → G-D → G-E. G-F 전에는 어떤 신규 "pass" 주장도 금지.**
