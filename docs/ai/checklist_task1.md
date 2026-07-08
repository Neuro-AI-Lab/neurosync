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

### F2: RAG 기반 정신건강 영역/진료과 후보 추론 — DomainInferenceAgent (T1-F2-*) — 구현·llm_only 라이브 배치 완료, risk≠domain 규칙 위반으로 비인증 처분 (설계 확정 2026-07-08, 구현 미션 완료 2026-07-08)

> 사양 근거: `discussion.md` PLAN-2026-W28-C(Step 2 C-1~C-5, Step 3 REV-006, 구현 미션 REV-007/REV-008), ADR-013/ADR-014, 2026-07-08 사용자 승인. PRD: `PRD_task1_v2.md` §3(v2.2). 아래 5개 DEV 항목은 2026-07-08 구현 미션(`development_report.md` DR-006)에서 실제 구현 완료 여부에 따라 상태를 갱신했다 — 상세는 각 행의 근거 인용 참조.

| ID | Type | 항목 | 상태 | 비고 |
|---|---|---|---|---|
| T1-F2-DEV-001 | DEV | **DomainInferenceAgent** 구현 (Stage 2, LLM 1회 호출, strategy=benchmarked: Solar Pro3 1차/K-EXAONE 2차) + I/O 스키마 정의 + 프롬프트 신규 작성(v3 12원칙 적용, placeholder-only) | [x] | PRD §3.1/§3.4/§3.5. **구 TemporalRetrieverAgent 정의는 F4(종단 검색)로 보류 — superseded-for-F2, 삭제 아님**(구 명칭·`/ai/temporal/retrieve`·composite scoring·8-쿼리 플래너는 F4 이관 대상). 구현 완료(2026-07-08): `agents/domain_inference.py`, `schemas/domain_inference.py`, `docs/ai/prompts/domain_inference/v1.system.md`(2382자/74줄, echo-risk audit clean — REV-007). qa GATE:PASS. 근거: DR-006 §1 |
| T1-F2-DEV-002 | DEV | 근거-화이트리스트(evidence whitelist) 런타임 검사 모듈 신규 구현 — `evidence.source_id ∈ 실제 반환 청크 ∪ F1 발화`; rag_chunk evidence는 `chunk_ids` 멤버십뿐 아니라 quote↔청크 본문 어휘 대조 포함(`grounding.py`의 F2판, REV-006 조건 1) | [x] | 구 "pgvector embedding 저장/검색 모듈"은 이미 PR #31로 `rag/retrieval.py`에 구현·병합됨(Master) — 본 항목은 대체 범위(F2 fabrication=0 하드 게이트의 전제 조건). PRD §3.2. 구현 완료: `src/eval/f2_grounding.py` — REV-006 조건 1 genuinely closed(REV-007 Part B #1: rag_chunk evidence 어휘 대조 code-verified). 근거: DR-006 §1 |
| T1-F2-DEV-003 | DEV | `POST /ai/domain/infer` 라우트 신규(registry key `domain_inference`) — 프로덕션 통합(orchestrator.py 연동)은 G-D-F2 게이트로 보류 | [x] | 구 `POST /ai/temporal/retrieve`는 F4 보류(superseded-for-F2). 인증은 이 신규 라우트가 아니라 기존 rag 라우터 대상(T1-F2-SEC-001 참조). PRD §3.6, §9.2. **정정(2026-07-08):** 직전 판정("미착수")은 증거 부족에 따른 오류였다. 직접 확인 결과 `apps/ai-server/src/routes/domain.py`가 존재하며(`POST /ai/domain/infer` 구현, standalone route), `apps/ai-server/src/main.py:24`가 이를 import(`from src.routes.domain import router as domain_router`)하고 `main.py:51`이 `app.include_router(domain_router)`로 등록해 서버 부팅 시 실제로 마운트된다(`main.py:11` 문서화: "POST /ai/domain/infer (F2, standalone — not wired into orchestrator.py)"). 항목 텍스트 자체가 명시하듯 orchestrator.py 11-state machine 프로덕션 연동은 별도 범위(G-D-F2 게이트 보류)이며 본 항목(라우트 신규 구현·등록)의 완료 여부와 무관 — 라우트는 완료. qa GATE:PASS(구현 전체 게이트, 라우트 파일 포함 검증 범위). 근거: `src/routes/domain.py`, `src/main.py:24,51`, `docs/ai/development_report.md` DR-006 §1 |
| T1-F2-DEV-004 | DEV | 오프라인 테스트 5종 구현: 출력 스키마(evidence≥1/후보), 근거-추적성 유닛(fixture accept/reject), 프롬프트 단정문(placeholder/절대규칙/예산/경계지시), `llm_only` 폴백 경로, department-derives-from-domain | [x] | 구 "RAG scoring formula"는 composite scoring/8-쿼리 플래너와 함께 F4 보류. PRD §3.7. 구현 완료: `tests/test_domain_inference.py`, `tests/test_f2_grounding.py`, `tests/test_f2_pipeline.py`, `tests/test_prompt_domain_inference.py`(5종 커버). qa GATE:PASS. 근거: DR-006 §1, REV-007 Part B |
| T1-F2-CFG-001 | CFG | pgvector extension (placeholder) | [ ] | - |
| T1-F2-VER-001 | VER | VP-002 domain/department 후보 라이브 검증 (재진) | [ ] | 골든 라벨(DATASET, multi-label, critic 승인) 대비 n≥2 세션(권장 n≥3), 서술적 보고(비율 주장 아님). 선행: T1-F2-VER-005. PLAN-2026-W28-C C-4, REV-006 조건 2 |
| T1-F2-VER-002 | VER | VP-004 domain/department 후보 라이브 검증 (중증 재진) | [ ] | 상동 + 위험≠도메인 근거 사용 금지 부정 fixture 결과 포함(REV-006 조건 3) |
| T1-F2-VER-003 | VER | VP-001 domain/department 후보 라이브 검증 (초진, 최소 정보) | [ ] | 상동. DB 프리플라이트 실패 시 `llm_only` 런으로 별도 라벨(REV-006 조건 6, ADR-013 (4)) |
| T1-F2-VER-004 | VER | Retrieval ranking 품질 (top-1/top-3 정량 검증) | [ ] | **유예 목표**: "사전 정의 10개 임상 시나리오"가 저장소에 실존하지 않음(grep 0건, REV-006 Summary 긍정 소견 (a)) — 70%/90%는 임상 검토 시나리오셋 확보 또는 관측 ≥12건 누적 전까지 보류. PLAN-2026-W28-C C-4 |

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
| T1-F1-DEV-017 | DEV | clinical_slot 프롬프트 v2 (예시 → placeholder, null 강제, risk 추론 금지) + placeholder-echo 거부 | [x] | ISS-027. `prompts/clinical_slot/v2.system.md`, PROMPT_VERSION=v2, test_prompt_v2 9건 |
| T1-F1-DEV-018 | DEV | **런타임 grounding filter** (`src/grounding.py` + f1.py merge 적용): 추출 slot은 근거 판정 통과 시에만 병합, risk_assessment는 추출기 경로 차단, ungrounded risk 상태 종료 금지 + 필수 SI screen | [x] | ISS-027. QA gate 우회 시도 7건 중 2건 발견 → ISS-044/045로 즉시 수정, 회귀 16건 추가. 445 tests green |
| T1-F1-DEV-019 | DEV | Coverage 재정의: grounded_coverage(질문가능 8-slot) 병행 보고, 0턴=실측 | [x] | ISS-034 |
| T1-F1-VER-014 | VER | Slot grounding 자동 감사 (`src.eval.grounding_audit`) + 07-03 런 4건 소급 판정 | [x] | 소급 확정: 4런 전부 날조 7건, 재계산 cov 0.25. 신규 8런 날조 0. `retro_audit_20260703/` (DR-003) |
| T1-F1-VER-010 | VER | 재현성: VP당 n>=3 반복 런, coverage/CTRS/turns/날조율 분산 보고 | [~] | n=2 완료 (8런, 날조 0). n>=3 확장 + 분산 보고 잔여 |
| T1-F1-VER-011 | VER | 장기 세션: 12턴 런, 반복 루프·피로도 검증 | [~] | 12턴 런 6건에서 반복 <=1 충족. SM-06 r1 종반 반복 루프 1건 (ISS-047) |

## Phase 2 — 프롬프트 아키텍처 v3 (Gate G-F 확장, `docs/ai/prompt_redesign_v3.md` v3.1) — 신규 2026-07-07

> 사양 근거: `discussion.md` PLAN-2026-W28(B1), REV-002(2026-07-07 non-blocking 종결), ADR-006, ADR-007. PRD 요약: `PRD_task1_v2.md` §11.

| ID | Type | 항목 | 상태 | 선행 조건 |
|---|---|---|---|---|
| T1-F1-DEV-024 | DEV | safety_classifier v2 프롬프트: 절대 규칙 5개 압축(ISS-046 관용구 규칙 신규 포함) + v1 핵심 규칙 7개 중 5개 verbatim 보존/2개 표 통합(삭제 0개) + ISS-048/050 신규 앵커 | [x] | `prompt_redesign_v3.md` §2.1. 구현 완료 — BUG-007(캘리브레이션 앵커 무언 삭제) 발견 후 수정, qa GATE:PASS(510 tests). 근거: DR-004 §2/§4, `error.md` BUG-007 |
| T1-F1-DEV-025 | DEV | dialogue v2 프롬프트: 절대 금지 8→6개 통합 + Safety 참고 섹션 5→1줄 축소(P12, 런타임 주입과 중복 제거) | [x] | `prompt_redesign_v3.md` §2.2. 구현 완료, qa GATE:PASS(510 tests). 근거: DR-004 §2 |
| T1-F1-DEV-026 | DEV | clinical_slot v3 프롬프트: 최우선 원칙 5개 hold(내용 불변) + risk_assessment 상호참조 노트는 프롬프트에 포함하지 않음(REV-002 #3 — 오케스트레이션 레벨로 이관, 코드 변경은 본 항목 범위 밖) | [x] | `prompt_redesign_v3.md` §2.3. 구현 완료(0개 규칙 삭제 확인), qa GATE:PASS(510 tests). 근거: DR-004 §2 |
| T1-F1-DEV-027 | DEV | handoff_generator v2 프롬프트: ctrs_level 출력 지시 삭제(ADR-007 옵션A) + P7 placeholder화 7곳(§6/§8/§9/§12) + evidence citation 단일 선언(§3/§5/§7 3회→1회) | [x] | `prompt_redesign_v3.md` §2.4, ADR-007. 구현 완료, qa GATE:PASS(510 tests). 근거: DR-004 §2 |
| T1-F1-DEV-028 | DEV | sentiment_analyzer v2 프롬프트: session 모드 섹션 전체 삭제(LLM 미호출 dead code 확인) + turn_index 예시 필드 제거 + evidence_phrase placeholder화 | [x] | `prompt_redesign_v3.md` §2.5. 구현 완료, qa GATE:PASS(510 tests). 근거: DR-004 §2 |
| T1-F1-VER-015 | VER | 오프라인 프롬프트 검증 테스트: placeholder-only/스키마 키/절대규칙 존재/char 예산/session모드 부재/ISS-050 문구/v1 7개 규칙 존치/citation 단일 선언 8개 단정문 자동 검사 | [x] | T1-F1-DEV-024~028. `tests/test_prompt_v3.py` 8개 단정문 구현·green, qa GATE:PASS. 근거: DR-004 §4, `error.md` BUG-007 |
| T1-F1-VER-016 | VER | 라이브 A/B 검증: Safety Matrix SM-01~06+SM-07a/SM-07b(8개 전건 필수) + VP-001~004 n>=2(n>=3 권장) A/B vs DR-003 베이스라인, 롤백 기준(날조>0/crisis miss/probe miss) 적용 | [~] | T1-F1-VER-015. EXP-002 실행 완료 — SM 매트릭스 9/9, VP-001~004 n=2/VP, §4.4 형식 기준 롤백 미발동(REV-003 non-blocking). 단 VP-003 crisis 재현 1/2은 critic이 **inconclusive**로 판정(VAL-001 harness 결함 개입 가능성 — `f1.py` 절 분리 결함) — "무회귀" 문구 사용 불가. Stage-2에서 VAL-001 수정 후 재실행 시 완결 예정. 근거: DR-004 §3/§4, `result.md` EXP-002, `discussion.md` REV-003 |
| T1-F1-DEV-029 | DEV | safety v3 프롬프트 ISS-049 정책 반영(ADR-010): 수동적 자살사고를 CTRS 3(Safety Probe 경유)에서 high/CTRS 2 즉시 위기 대응으로 상향(ADR-006 대체) — 위험 수준 표 + 간접 표현 CTRS 하한표 2개 행 갱신, 규칙 5 재작성, 부정 문맥(SM-02)/공황 관용구(SM-07a)/ISS-050 규칙 verbatim 보존, 자해-충동-단독(SM-04류)은 CTRS3→probe 유지. pin v2→v3, `_MEDIUM_KEYWORDS` 정합성 검토(테이블 변경 불필요로 판정, 근거는 코드 주석 명시), SM-03 판정(변경 없음), spec/board/checklist 정합 | [!] | **롤백됨 (ADR-012, EXP-003)** — 라이브 재검증(T1-F1-VER-016 계열)에서 SM-04a/SM-04b 프로브 회귀 발견: 자해-충동-단독 발화가 Safety Probe를 우회하고 turn 0에서 즉시 crisis로 상향(ADR-010 scope limit (c) 위반). PROMPT_VERSION pin은 v2로 되돌림; `v3.system.md`는 실패한 후보로 디스크에 보존, v4 재시도 대기. ADR-010 정책 자체는 유효, 구현만 롤백. 근거: `result.md` EXP-003, `discussion.md` ADR-012 |

## Phase 2 — Safety 심층 + 경로 통일 (Gate G-B, G-C)

| ID | Type | 항목 | 상태 | 해결 이슈 |
|---|---|---|---|---|
| T1-F1-DEV-022 | DEV | **Safety Probe 모드** (ISS-035 L1-L2): CTRS 3 + SI/self-harm category → 탐문 강제 주입 (빈도→계획→수단→보호요인), risk_floor latch | [x] | f1.py probe state machine, probe_events/risk_floor/session_ctrs 기록. LLM-free 테스트 12건 |
| T1-F1-DEV-023 | DEV | Safety Probe 승급/유지 (L2-L3): 재분류+lexical 이중 승급, 부인 시 grounded risk 기록 후 지속, cooldown(재발동 상한 2회) | [x] | ISS-043 clause-local 부정 수정 포함 (QA gate 발견 즉시 수정). 파이프라인 레벨 검증은 SM-04a/b 실행 배치 |
| T1-F1-VER-012 | VER | Safety 시나리오 매트릭스 (파이프라인 레벨, 스크립트 환자): 중간 턴 위기 전환, 부정 문맥, 간접·masked 표현, **CTRS3+자해사고 → probe 발동·승급·비승급 3분기**, 복약 순응 오탐 0 | [~] | 2026-07-06 실행: 최종 7/7 통과. SM-06 1회차 flake(ISS-047), 신규 오탐 클래스 ISS-046 발견 — 수정 후 재실행 시 [x] |
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
| T1-F2-DEV-005 | DEV | `f2.py` 검증 파이프라인 구현(f1.py 패턴): 입력 로드 → Stage1 코드검색(실패 시 `mode=llm_only` 강등) → Stage2 DomainInferenceAgent LLM → 근거-화이트리스트 검사(T1-F2-DEV-002) → 산출물(`{VP}_{ts}_domain_inference.json`+report.md) → 콘솔 요약 | [x] | T1-F2-DEV-001, T1-F2-DEV-002, T1-F2-CFG-002. PRD §3.2. 구현 완료: `src/f2.py`. EXP-004 라이브 배치로 실행 확인(8/8 런, llm_only arm). 근거: DR-006 §2, `result.md` EXP-004 |

## Phase 2 — F2 도메인 추론(DomainInferenceAgent) 구현 (PLAN-2026-W28-C 승인, ADR-013) — 구현·llm_only 라이브 배치 완료, risk≠domain 위반으로 비인증 처분(ADR-014) — 2026-07-08

> 사양 근거: `discussion.md` PLAN-2026-W28-C(Step 2 C-1~C-5, Step 3 REV-006, 2026-07-08 승인 상태 업데이트, 구현 미션 REV-007/REV-008), ADR-013/ADR-014, REV-006(구속 조건 1/2/3/4/5/6). PRD: `PRD_task1_v2.md` §3.7, §3.8. 구현 미션 완료 보고: `development_report.md` DR-006.

| ID | Type | 항목 | 상태 | 선행 조건 |
|---|---|---|---|---|
| T1-F2-CFG-002 | CFG | `DATABASE_URL`/`ENCRYPTION_KEY` env 배선 + DB 연결성 프리플라이트(SELECT 1/스모크, 쓰기 없음) | [~] | ADR-013 (4). PLAN-2026-W28-C C-1 — DB 프로브 FAIL 확인됨(`.env`에 `DATABASE_URL` 부재), 구현 착수 선행조건. **부분(2026-07-08):** 프리플라이트 스모크 메커니즘 자체는 구현·검증됨(`SELECT 1`, 10s timeout, 결과 정직 보고 — `experiments/EXP-004/preflight.log`). `DATABASE_URL`/`ENCRYPTION_KEY` env 배선은 여전히 미완(`.env`에 `DATABASE_URL` 키 부재, grep 0건) — RAG arm 차단의 직접 원인. 근거: DR-006 §2 |
| T1-F2-SEC-001 | SEC | rag 라우터(`POST /ai/rag/grounding` 등) env 기반 bearer/API-key 인증 적용 + `rag_chat.py` 하드코딩 공인 IP/환자 UUID → env화 | [x] | VAL-005 옵션(a) 채택, ADR-013 (1). 구현 완료·검증됨: `src/rag/auth.py`(fail-closed 503) + `rag_chat.py` 하드코딩 IP/UUID 제거. `tests/rag/test_route_auth.py` 6 cases, qa GATE:PASS. git 이력 정리(옵션 (b))는 별도 미결(ADR-013(3)). 근거: DR-006 §4 |
| T1-F2-SEC-002 | SEC | `retrieval.py` `_dec()` 복호화 갭 수정: crypto.py decrypt 구현 + `situation_encrypted` 실복호화 적용, `ENCRYPTION_KEY` 부재 시 해당 필드 제외 + 명시 로깅 | [x] | VAL-005 cross-ref (S2), ADR-013 (2). 구현 완료·검증됨: `crypto.py::decrypt_str`(AES-GCM), `retrieval.py::_dec()` 실패 시 필드 제외. `tests/rag/test_crypto.py` 7 cases. 부수 발견: `load_simulations.py`의 사전 존재 결함(BUG-012, situation 필드 평문 기록)은 본 항목 범위 밖(retrieval.py 측은 정상 동작). 근거: DR-006 §4 |
| T1-F2-SEC-003 | SEC | `apps/ai-server/src/rag/` 모킹 기반 유닛 테스트 커버리지 신규 | [x] | VAL-005 cross-ref (S3), ADR-013 (2). 구현 완료: `tests/rag/` 신규 모킹 테스트 26건(이전 0건). 근거: DR-006 §4 |
| T1-F2-VER-005 | VER | 골든 라벨 DATASET 저작(VP-001~004, 다중-라벨 집합 — 예: VP-001={anxiety,sleep}) — persona 전문에서 blind 도출, `rag_chat.py` 비공식 태그 비의존 명시 + critic 승인 | [x] | REV-006 조건(2), PLAN-2026-W28-C C-4 — 라이브 실행(T1-F2-VER-001~003) 선행조건. 완료: DATASET-004 **APPROVED with amendments**(REV-007 Part A, 2026-07-08). 근거: `discussion.md` DATASET-004/REV-007 |
| T1-F2-VER-006 | VER | 라이브 n≥2/VP 배치 실행, `llm_only`/RAG arm 구분 라벨 — DB 프리플라이트 실패 시 RAG-arm 검증 런 중단·보고(silent `llm_only` 강등 금지) + `latency_ms` 캡처·p95 서술 보고(REV-006 조건 5) | [~] | REV-006 조건(6), ADR-013 (4). 선행: T1-F2-CFG-002, T1-F2-VER-005. **부분(2026-07-08, EXP-004):** llm_only arm 완료(VP-001~004 n=2, 8런). RAG arm은 DB 프리플라이트 FAIL(`DATABASE_URL` 미설정)로 **BLOCKED-awaiting-DB**(ADR-013(4)) — 미실행, silent 강등 아님. 근거: `result.md` EXP-004, DR-006 §2 |
| T1-F2-VER-007 | VER | 근거 요약 grounding 감사: utterance→`has_lexical_evidence()` 재사용, rag_chunk→`chunk_ids` 멤버십 + quote↔청크 본문 어휘 대조 — fabrication=0 하드 게이트 | [x] | REV-006 조건(1), PLAN-2026-W28-C C-3/C-4 — 하드 게이트, 위반 시 프롬프트 버전 롤백. **완료(하드 게이트 자체는 충족, 2026-07-08 EXP-004):** fabrication 0/32 evidence entries(정정치, VAL-008), whitelist reject 0건 — 본 항목 고유 범위(evidence 근거성 검사)는 위반 없음. **단, 별도 규칙인 risk≠domain 절대 규칙(prompt rule 2)이 VP-003 2/2 런에서 라이브 위반 확인**(VAL-006/REV-008) — 롤백 트리거 발동, `domain_inference` v1 **비인증** 처분(ADR-014). 근거: `result.md` EXP-004, `error.md` VAL-006/VAL-008, `discussion.md` REV-008/ADR-014 |

## Phase 2 — 통합 (Gate G-E)

| ID | Type | 항목 | 상태 | 선행 조건 |
|---|---|---|---|---|
| T1-F0-VER-003 | VER | 통합 E2E: F1→F3→F4→F5 전 체인, 4VP, EvidenceVerifier passed, 날조 0건 | [ ] | G-D 전체 |
| T1-F0-VER-004 | VER | QA/Critic 통합 감사 이슈(ISS-024~040) 전건 소거 확인 | [ ] | 전 Stage |

---

## 요약 통계

| 구분 | Phase 1 | Phase 2 신규 | 합계 |
|---|---|---|---|
| DEV | 35 | 28 | 63 |
| VER | 28 | 19 | 47 |
| CFG | 3 | 1 | 4 |
| DOC | 4 | 1 | 5 |
| SEC | 0 | 3 | 3 |
| **계** | **70** | **52** | **122** |

Phase 1 상태 분포 (Stage 0 완료 후, 2026-07-07 T1-F1-DEV-029 전환 반영): `[x]` 32 · `[~]` 11 · `[!]` 10 · `[ ]` 17
**Gate 순서: ~~G-0(긴급 복구)~~ 완료(2026-07-06) → G-F(grounding 재검증) ← 다음 → G-A/B/C → G-D → G-D-F2 → G-E. G-F 전에는 어떤 신규 "pass" 주장도 금지. G-D-F2는 추가로 ADR-014에 따라 v2 remediation 통과 전까지 진행 불가(아래 2026-07-08 갱신 참조).**

> **2026-07-08 갱신 (DR-006 반영, F2 구현 미션 완료):** T1-F2-DEV-001/002/004/005·SEC-001~003·VER-005 `[x]`로 전환(구현 완료·qa GATE:PASS 확인, DR-006 §1/§4). T1-F2-DEV-003(신규 프로덕션 라우트)도 `[x]`로 전환 — **정정:** 이전 버전의 "본 미션 범위에 포함되지 않아 `[ ]` 유지" 판정은 증거 부족에 따른 오류였다. 직접 확인 결과 `apps/ai-server/src/routes/domain.py`가 존재하고 `apps/ai-server/src/main.py:24`가 이를 import, `main.py:51`이 `app.include_router(domain_router)`로 등록해 서버 부팅 시 실제 마운트된다(qa GATE:PASS, DR-006 §1). 라우트 신규 구현·등록 자체는 완료이며, orchestrator.py 프로덕션 연동만 항목 텍스트가 명시한 대로 G-D-F2 게이트로 계속 보류된다(범위 밖, 미착수와 다름). T1-F2-CFG-002 `[~]`(프리플라이트 메커니즘은 구현·검증됐으나 `DATABASE_URL`/`ENCRYPTION_KEY` env 배선 자체는 미완 — RAG arm 차단의 직접 원인). T1-F2-VER-006 `[~]`(llm_only arm만 라이브 완료, RAG arm은 BLOCKED-awaiting-DB). T1-F2-VER-007 `[x]`이나 **중요 단서 포함**: fabrication=0 하드 게이트(본 항목 고유 범위)는 충족했으나, 별도의 risk≠domain 절대 규칙(prompt rule 2)이 VP-003 2/2 런에서 라이브 위반이 확인됐다(VAL-006, REV-008) — 롤백 트리거가 발동해 `domain_inference` v1이 **비인증(non-certification)** 처분됐다(ADR-014). **G-D-F2 게이트 진행 및 RAG-arm 활성화는 v2 remediation(코드 강제 risk-lexicon evidence filter + 프롬프트 정교화 + 재검토)이 전체 게이트 체인을 통과할 때까지 불가**(ADR-014 (1)). 본 갱신 어디에도 risk≠domain 규칙에 대해 "통과"/"유지" 표현을 사용하지 않는다. 근거: `docs/ai/development_report.md` DR-006, `discussion.md` REV-007/REV-008/ADR-013/ADR-014, `error.md` VAL-006/VAL-007/VAL-008/BUG-012.

> **2026-07-07 추가 (v2.1, 114→115 items):** ISS-049 정책 최종 반영(ADR-010) — safety_classifier v3 프롬프트 DEV 1건(T1-F1-DEV-029) 신규. 근거: `discussion.md` PLAN-2026-W28-B/ADR-010. 위 표 수치는 이 추가분을 반영한다.

> **2026-07-07 정정 (v2.2, DR-005):** T1-F1-DEV-029 셀이 라이브 검증 실패로 `[~]` → `[!]`로 갱신되었다(ADR-012, `result.md` EXP-003) — 안전 프롬프트 v3의 SM-04a/SM-04b 프로브 회귀로 롤백. 셀은 developer가 갱신했으나 위 상태 분포 문구는 그 시점에 갱신되지 않았던 것을 여기서 정정한다: `[~]` 12→11, `[!]` 9→10 (총계 70·115는 변동 없음 — 상태만 변경, 항목 추가/삭제 없음). 본 미션(PLAN-2026-W28-B)이 건드린 체크리스트 행은 T1-F1-DEV-029 1건뿐임을 확인했으며, 이 미션에서 유래한 다른 카운트 drift는 없다. `[x]`/`[ ]` 값은 이번 정정 대상이 아니며(본 미션과 무관한 이전 시점 값), 별도 재집계가 필요하면 이는 본 항목 범위 밖이다.

> **2026-07-08 추가 (v2.3, 115→122 items):** F2를 DomainInferenceAgent로 재정의(PLAN-2026-W28-C 승인, ADR-013) — 기존 T1-F2-DEV-001~005 및 VER-001~004는 문구만 신 정의 기준으로 갱신(카운트 불변, 상태는 착수 전 `[ ]` 유지). 신규 항목: CFG 1건(T1-F2-CFG-002, DB env 배선/프리플라이트), SEC 3건(T1-F2-SEC-001~003, VAL-005/ADR-013 보안 조치 — 본 문서 최초의 SEC 타입), VER 3건(T1-F2-VER-005~007, 골든라벨 DATASET/라이브 n≥2 배치/grounding 감사). §9.2 게이트 테이블에 G-D-F2 신설(REV-006 조건 4) 반영해 위 Gate 순서 문구에도 추가. 근거: `discussion.md` PLAN-2026-W28-C, REV-006, ADR-013; `PRD_task1_v2.md` §3(v2.2), §9.2. 신규 ID 7종(T1-F2-CFG-002/SEC-001/SEC-002/SEC-003/VER-005/VER-006/VER-007 — CFG 1 + SEC 3 + VER 3)은 grep으로 기존 ID와 충돌 없음을 확인했다.
>
> **부수 정정 (본 항목과 별개, 신규 추가분과 무관):** 표 갱신 과정에서 전 항목을 실제로 행 단위 재계수(grep)한 결과, 기존 "Phase 2 신규" 열의 DEV/VER 분배가 부정확했음을 발견했다 — 기존 표는 DEV 26 / VER 18로 표기했으나 실제 물리적 행 수는 DEV 28 / VER 16이다(두 오차가 서로 상쇄되어 기존 대분류 합계 115는 우연히 정확했다). 본 갱신에서 DEV/VER Phase 2 분배를 실측치(28/16, 본 미션 VER 신규 3건 반영 후 19)로 정정했다 — Phase 1 열과 전체 합계(122)는 실측과 일치하며 이번 정정으로 변하지 않는다. 이 오차의 발생 시점은 특정하지 않는다(본 미션 범위 밖).

> **2026-07-07 추가 (v2, 107→114 items):** 프롬프트 아키텍처 v3(Gate G-F 확장) — DEV 5건(T1-F1-DEV-024~028) + VER 2건(T1-F1-VER-015~016) 신규. 근거: `PRD_task1_v2.md` §11, `docs/ai/prompt_redesign_v3.md` v3.1, `discussion.md` PLAN-2026-W28(B1)/REV-002/ADR-006/ADR-007. 위 표 수치는 이 추가분을 반영한다.
