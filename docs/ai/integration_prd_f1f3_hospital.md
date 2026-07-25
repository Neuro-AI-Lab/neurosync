# 앱↔백엔드↔ai-server 연동 PRD — Phase 0 (계약/스키마 선행정렬) → F1→F2→F3→병원맵

> **작성:** writer (2026-07-21) | **소유:** orchestrator(계획 승인) — 코드 변경/실험/git ops 없음, 문서만.
> **재료:** 사전분석 3건(재파생 금지, 인용만) — `analysis_app_merge_20260721.md`(계약 불일치 4건),
> `analysis_db_schema_20260721.md`(DB 스키마 총체), `app_wiring_inventory_20260721.md`(18스크린 배선).
> 제품 스펙: `docs/prd/screens/neuro-sync/{01-IA,03-SCREEN-SPEC}.md`, `docs/prd/PRD_neuro-sync.md`.
> 결정/제약 원본: `discussion.md` ADR-040/ADR-044, `error.md` BUG-055/BUG-056,
> `docs/ai/deployment_integration_plan.md` §5(e) 호출 시퀀스.

## 0. 요약표

| 항목 | 내용 |
|---|---|
| 전체 phase 수 | 5 (Phase 0 선행정렬 + Phase 1~4 순차 연동) |
| 스코프 | F1(대화 intake) → F2(domain 라우팅) → F3(문진 plan/score) → 병원 탐색 맵. **F4(종단)/F5(handoff report 본문)는 out-of-scope**(후속 PRD) |
| 현재 배선 현황(18스크린 기준) | 완전 배선 11 · 부분 배선 2 · 계약 불일치(배선됐으나 422/degrade) 2 · 완전 stub(백엔드 호출 0) 3 |
| 계약 불일치(Phase 0 대상) | 4건 — /ai/chat/respond 계약 붕괴, BUG-055(risk_assessment 통로 부재), /ai/survey/score shape, domain enum 8 vs 9 |
| DB 발견(Phase 0 대상) | 2건 — F1[CRITICAL] questionnaire_types CHECK vs load_simulations ALLOWED_SCALES 불일치, F2[MAJOR] 0008→0010 제약 이관 누락 |
| Open BUG(design-scope, 본 PRD는 옵션만 제시) | BUG-055(major, open), BUG-056(major, open, design-scope deferred) |
| 병원맵 현황 | hospitals.tsx 완전 stub(`tel:119`만); ai-server `nearby_facilities` agent는 ADR-040/ADR-041로 완전 폐기·부활 금지; 앱측 사용자주도 아키텍처만 검토 |
| MOCK 기본값 | `apps/mobile/lib/config.ts` MOCK dev 기본 ON — 실연동 전 MOCK=0 전환 필요(모든 phase 공통 전제) |

## 1. 목표 / 비목표

### 목표
- 18개 모바일 화면 전부를 백엔드(`apps/api` `/api/v1/*`) 및 ai-server(`/ai/*`) 대응 기능·DB 테이블에 매핑해 현재 배선 상태(배선됨/미배선/계약불일치)를 단일 근거표로 확정한다.
- 계약/스키마 불일치를 실제 연동(Phase 1~3) 이전에 해소하는 선행정렬(Phase 0)을 설계한다.
- F1(대화)→F2(domain 추론)→F3(문진 정본화)→병원 탐색 맵의 단계적 연동 순서와 각 단계 완료 기준을 정의한다.

### 비목표 (out of scope, 후속 PRD 예고만)
- **F4(종단분석, `/ai/temporal/analyze`)**: `LongitudinalSessionEntry` 누적·`/ai/temporal/analyze` 연동은 본 PRD 범위 밖. 다회차 세션이 확보된 이후 별도 PRD.
- **F5(handoff report 본문, `/ai/handoff/report`)**: `report/detail.tsx`의 실제 리포트 본문 연동(현재 MOCK 하드코딩)은 F4 PRD와 함께 별도 다룸. 본 PRD는 F5의 전제 조건인 BUG-055(risk_assessment 통로)까지만 Phase 0에서 다룬다.
- 코드 수정, 실험 실행, git 커밋/push — 전부 없음.
- `records.tsx`(GET history endpoint 부재), `report/detail.tsx` 본문(MOCK), `settings` 프로필 수정/동의 PATCH, `intake/documents`(Phase 2 OCR) — 이 PRD의 연동 대상 4-phase에 속하지 않는 항목은 매핑 매트릭스에 현황만 기록하고 phase 배정은 "후속"으로 표기.

## 2. 현황 요약 — 3-tier 계층

```
모바일(apps/mobile) --/api/v1/*--> 백엔드(apps/api, BFF/게이트웨이) --/ai/*--> ai-server(apps/ai-server)
```

- 모바일→apps/api hop: 전부 route 매칭됨(불일치 없음, `app_wiring_inventory_20260721.md` §B).
- apps/api↔ai-server hop: 계약 불일치 4건이 여기에 존재(`analysis_app_merge_20260721.md`).
- **MOCK 플래그**: `apps/mobile/lib/config.ts`의 `MOCK`(dev 기본 ON) — ON이면 모든 client fn이 `lib/mock.ts`로 스왑되어 실제 백엔드를 전혀 호출하지 않는다. 실연동에는 `MOCK=0` + `EXPO_PUBLIC_API_BASE_URL`/`EXPO_PUBLIC_WS_BASE_URL` 필요. 이 PRD의 모든 phase는 이 전환을 전제로 한다.

### 배선 집계 (18스크린 기준, `app_wiring_inventory_20260721.md` §A/§B 근거, §3 매트릭스와 동일 4-버킷 체계)

| 상태 | 스크린 수 | 목록 |
|---|---|---|
| 완전 배선(계약 정합·라이브) | 11 | `_layout`(auth), login, register, onboarding(로컬만이나 UI완결), `_layout`(patient), `_layout`(tabs), intake/submit, report/status, emergency, index, `_layout`(root) — 순수 레이아웃/로컬 전용 5개 포함 |
| 부분 배선 | 2 | home(CTA는 실호출, records/last-report 카드는 로컬 mock), settings(음성동의만 실호출, 프로필수정/동의토글은 stub) |
| 계약 불일치(배선됐으나 422/degrade) | 2 | intake/chat(`/ai/chat/respond` 계약 붕괴), intake/survey(`/ai/survey/score` shape 불일치) |
| 완전 stub(백엔드 호출 0) | 3 | hospitals, records, report/detail(MOCK 하드코딩/real 모드는 placeholder) |

## 3. 페이지·UI 매핑 매트릭스 (18스크린 전부)

소스: `app_wiring_inventory_20260721.md` §A(스크린 인벤토리)+§B(client 계층)+§D(부트스트랩), DB 컬럼은 `analysis_db_schema_20260721.md` §"AI↔DB 접점".

| # | Screen path | UI 기능 | ai-server 엔드포인트+계약 | apps/api 라우트/서비스 | DB 테이블·컬럼 | 현재 상태 | 선행 수정 필요 | Phase |
|---|---|---|---|---|---|---|---|---|
| 1 | `app/(auth)/_layout.tsx` | Stack wrapper | 없음 | 없음 | — | 배선됨(순수 레이아웃, 호출 없음이 정상) | 없음 | — |
| 2 | `app/(auth)/login.tsx` | 이메일/PW 로그인 | 없음(직접) | POST `/api/v1/auth/login` | `users` | 배선됨 | 없음 | Phase 0 전제(부트스트랩) |
| 3 | `app/(auth)/register.tsx` | 프로필+동의 회원가입 | 없음(직접) | POST `/api/v1/auth/register` | `users`, `patient_profiles`(PII BYTEA, `is_minor` GENERATED), `consent_snapshots`(voice 포함) | 배선됨 | 없음 | Phase 0 전제 |
| 4 | `app/(auth)/onboarding.tsx` | 4-step 인트로 | 없음 | 없음(`Prefs.setSeenOnboarding()` 로컬) | — | 배선됨(백엔드 호출 자체가 설계상 없음) | 없음 | — |
| 5 | `app/(patient)/_layout.tsx` | auth-gated Stack + emergency modal | 없음 | 없음(`useAuth().status`) | — | 배선됨 | 없음 | — |
| 6 | `app/(patient)/(tabs)/_layout.tsx` | 하단 탭 네비 | 없음 | 없음 | — | 배선됨 | 없음 | — |
| 7 | `app/(patient)/(tabs)/home.tsx` | 대시보드: intake CTA/resume/last-report/emergency | 없음(직접) | POST `/api/v1/sessions`(`createSession`) | `sessions` | 부분 배선(CTA는 실호출, records/last-report 카드는 로컬 mock store) | records 카드용 GET history 라우트 부재(records.tsx와 동일 이슈, 이 PRD 4-phase 범위 밖 — 후속 PRD) | Phase 1 전제(세션 생성) |
| 8 | `app/(patient)/(tabs)/hospitals.tsx` | 병원 찾기 탭 | 없음(ai-server `/ai/nearby/*`는 폐기됨) | 없음 | 없음(facility 테이블 자체가 스키마에 없음) | **완전 stub**(`tel:119`만, map SDK 없음, S-11 Phase 2 FR-012) | §6 병원맵 설계 필요 | Phase 4 |
| 9 | `app/(patient)/(tabs)/records.tsx` | 과거 기록 피드 | 없음 | 없음(GET history 부재) | `questionnaire_results`, `sessions`(연결 가능하나 미노출) | 완전 stub(Zustand 로컬만, dev mock) | GET history 라우트 신설 — **이 PRD 4-phase 범위 밖**, 후속 PRD 예고만 | 후속 |
| 10 | `app/(patient)/(tabs)/settings.tsx` | 프로필(RO)/동의토글/로그아웃 | 없음(직접) | POST `/api/v1/consent/voice`(유일 라이브) | `consent_snapshots` | 부분 배선(음성동의만 실호출, 프로필수정/약관보기=`stub()` alert, risk-notify 토글은 PATCH 부재로 로컬만) | 프로필/동의 PATCH 라우트 — 이 PRD 범위 밖 | 후속 |
| 11 | `app/(patient)/intake/chat.tsx` | 실시간 대화 intake(WS), 위험배너/모달, PTT | `/ai/chat/respond`(DialogueInput/Output), `/ai/slots/extract`, `/ai/domain/infer`(설문탭) | WS `/api/v1/sessions/{id}/chat`; POST `/api/v1/sessions/{id}/domain/infer`; POST `/api/v1/stt/transcribe` | `messages`(암호화), `sessions.clinical_slots`(JSONB), `risk_events` | **계약불일치**(치명) — /ai/chat/respond 계약 붕괴, session_state 왕복 부재, BUG-055(risk_assessment 통로 전무) | Phase 0 §5.1(계약1)+§5.2(BUG-055) 완료 필수 | Phase 1 |
| 12 | `app/(patient)/intake/survey.tsx` | 단일 문진(PHQ-9/GAD-7/AUDIT-C/PHQ-4) | `/ai/survey/score`(SurveyScoreInput), `/ai/survey/plan`(존재하나 미배선) | POST `/api/v1/sessions/{id}/questionnaires` | `questionnaire_results`(type CHECK 비하이픈 4종, uq(session,type)) | **계약불일치** — /ai/survey/score responses shape 불일치→로컬 근사 컷오프 상시 폴백; `/ai/survey/plan` 완전 미배선 | Phase 0 §5.3(계약3) + Phase 3에서 plan 배선 | Phase 3 |
| 13 | `app/(patient)/intake/submit.tsx` | 최종 제출 확인 | 간접(세션 종료 트리거) | POST `/api/v1/sessions/{id}/submit` | `sessions`(status), `handoff_reports`(생성 트리거) | 배선됨(호출 자체는 성공, 다운스트림 F5 본문은 out-of-scope) | 없음(이 PRD 범위) | Phase 1 종료 조건 |
| 14 | `app/(patient)/report/detail.tsx` | 리포트 상세(점수+handoff mini-preview) | `/ai/handoff/report`(F5, out-of-scope) | 없음(GET report-body 미배선) | `handoff_reports`(pdf_url/fhir — F3[ORM 드리프트, 미매핑]) | **완전 stub/MOCK 하드코딩** — MOCK=true 시 가짜 body, real 모드는 placeholder | F5 연동은 이 PRD 범위 밖 — 후속 PRD | 후속(F5) |
| 15 | `app/(patient)/report/status.tsx` | 리포트 생성 상태 폴링 | 간접 | GET `/api/v1/sessions/{id}/report/status`(3s 폴링, 60s 캡) | `handoff_reports`(status: generating/ready/failed) | 배선됨 | 없음 | Phase 1 종료 조건 |
| 16 | `app/(patient)/emergency.tsx` | 위기 모달: 핫라인, alone-status ack | 간접(WS `risk:detected` payload, REST 아님) | PATCH `/api/v1/risk_events/{id}`(`acknowledgeRiskEvent`) | `risk_events`(level/category/ai_evidence/alone_status) | 배선됨 — **정정(clinical-validator finding 2, 2026-07-22):** 이 트리거는 플랫폼측 per-turn `SafetyClassifier` 경로(`/ai/safety/classify`→`risk_events`→WS `risk:detected`; `apps/api/src/api/v1/sessions.py:684-729`, `services/safety.py`, `services/ai_client.py:74-75`)로 **계약1 수정과 무관하게 이미 독립 작동**한다. §5.1 계약1 수정은 별개의 ai-server 오케스트레이터 escalation 경로(`clinical_escalation_required` 등)를 강화할 뿐, emergency.tsx 근본 신호를 좌우하지 않는다. 상세는 §5.1a 참조. | 없음(독립 경로, 계약1과 무관) — 단, ai-server 오케스트레이터측 `clinical_escalation_required` 신호는 §5.1a의 무소비자 gap 참조 | Phase 1 |
| 17 | `app/index.tsx` | auth/onboarding 라우터 splash | 없음 | 없음(`useAuth()`) | — | 배선됨 | 없음 | — |
| 18 | `app/_layout.tsx` | 루트 레이아웃, `hydrate()` | 없음 | 없음(SecureStore 읽기만) | — | 배선됨 | 없음 | — |

**커버리지 확인:** 18/18 스크린 행 존재(누락 0) — `app_wiring_inventory_20260721.md` §A 테이블과 1:1 대응.

## 4. 단계 계획 — 개요

```
Phase 0 (계약·스키마 선행정렬)
    │  완료 기준: 계약4건+DB2건 수정설계 확정 + BUG-055 옵션 결정 대기 종결
    ▼
Phase 1 (F1 대화 intake: chat/slots/safety/STT 왕복)
    │  의존: Phase 0 계약1(/ai/chat/respond) + 계약2(BUG-055) 해소
    ▼
Phase 2 (F2 domain 추론 → 문진 라우팅)
    │  의존: Phase 1 완료(session_state 왕복 확립) + Phase 0 계약4(domain enum)
    ▼
Phase 3 (F3 문진 plan/score 정본화)
    │  의존: Phase 0 계약3(/ai/survey/score shape) + Phase 2(domain→scale 매핑)
    ▼
Phase 4 (병원 탐색 맵)
    │  의존: 없음(독립) — ADR-040/041 준수, 앱측 신규 기능이라 F1-F3와 기술적 의존관계 없음
```

병원맵(Phase 4)은 F1-F3와 데이터 의존이 없어 병렬 착수 가능하나, 리소스 순서상 마지막에 배치(우선순위는 임상 코어 파이프라인 선행).

### Phase 0 — 계약·스키마 선행정렬

**목표:** Phase 1 착수 전 계약 불일치 4건 + DB 발견 2건을 문서·설계 수준에서 정렬하고, BUG-055/BUG-056 처리 방향에 대한 사용자 결정을 확보한다.
**포함 작업:** §5 전체(계약1~4 수정설계, DB F1/F2 수정설계, BUG-055 옵션 제시, BUG-056 design-scope 명시).
**완료 기준(checkable):**
- [ ] 계약1(/ai/chat/respond) 수정안 확정(§5.1) — 백엔드 `ChatRequest`/`ChatResponse`를 ai-server `DialogueInput`/`DialogueOutput` 계약에 맞추거나, 어댑터 계층 신설 여부 결정.
- [ ] BUG-055 처리 방향 사용자 결정(§5.2 옵션 A/B 중 선택 또는 대안).
- [ ] 계약3(/ai/survey/score shape) 수정안 확정(§5.3).
- [ ] 계약4(domain enum 8 vs 9) 수정안 확정(§5.4).
- [ ] DB F1(questionnaire CHECK vs load_simulations) 수정안 확정 및 오프라인 재적재 절차 문서화(§5.5).
- [ ] DB F2(0008→0010 제약 이관) 재확인 절차 문서화(§5.6).
- [ ] BUG-056 design-scope 명시(수정 없음, Phase 1 QA 관찰 항목으로만 등록, §5.7).
**검증 방법:** 아래 §5.1의 422 재현 절차(재현만, 실행은 Phase 1). 코드 변경 없는 단계이므로 "검증"은 설계 문서의 내적 일관성 확인(계약 변경안이 실제 스키마 파일 경로·필드명과 grep으로 일치하는지)에 한정.
**담당 코드영역:** `packages/shared-contracts`(계약 스키마), `apps/ai-server/src/schemas/`, `apps/api/alembic/`(DB 마이그레이션 설계, 실행은 Phase 1 이후).
**의존성:** 없음(선행 단계).

### Phase 1 — F1 대화 intake (chat/slots/safety/STT 왕복)

**목표:** 계약1(/ai/chat/respond) 수정 완료를 전제로, 모바일 WS 대화(`intake/chat.tsx`)가 실제 ai-server dialogue+safety+slot 파이프라인과 왕복하도록 배선한다.
**포함 작업:**
- `deployment_integration_plan.md` §5(e) "매 턴" 시퀀스 구현: `/ai/chat/respond` + `/ai/slots/extract` 동시 호출, `session_state` 왕복, `filled_slots`(dict) 전달.
- BUG-055 결정안(§5.2) 반영 — risk_assessment 포워딩 경로 확립.
- STT 왕복(`/api/v1/stt/transcribe`) 확인(이미 배선됨, 회귀 확인만).
- `emergency.tsx`의 WS `risk:detected` 트리거 회귀 확인 — **정정(§5.1a):** 이 트리거는 플랫폼측 `SafetyClassifier` 경로로 계약1 수정과 무관하게 이미 독립 작동하므로 "안정화 대기"가 아니라 회귀 확인 항목이다. 계약1 수정은 별도의 ai-server 오케스트레이터 escalation 신호(`clinical_escalation_required` 등)를 왕복시키는 데만 관련된다(§5.1a 무소비자 gap 참조).
**완료 기준(checkable):**
- [ ] 실 세션에서 `session_state`가 턴마다 왕복하여 `asked_slot_counts`/`risk_screening_incomplete`/`clinical_escalation_required`/`handoff_delivered` 필드가 플랫폼(백엔드 DB)까지 도달(스모크 로그로 확인).
- [ ] `POST /ai/chat/respond` 422 발생률 0(왕복 스모크 N회 연속).
- [ ] BUG-055 결정 반영된 risk_assessment가 `sessions.clinical_slots` 또는 신설 필드에 저장됨을 확인.
**검증 방법:** 왕복 스모크(1세션 다중턴, 매 턴 실제 호출 후 session_state 필드 존재 확인) + 422 재현 셀(§5.1) 재실행하여 0건 확인.
**담당 코드영역:** `apps/api/src/services/chat.py`, `apps/api/src/api/v1/sessions.py`(WS 핸들러), `packages/shared-contracts`(ChatRequest/Response), `apps/ai-server/src/routes/chat.py`(수정 불필요 — 계약 정합화는 백엔드 측 우선).
**의존성:** Phase 0 계약1+계약2(BUG-055) 완료.

### Phase 2 — F2 domain 추론 → 문진 라우팅

**목표:** `/ai/domain/infer` 결과를 신뢰도 컷(0.35)과 domain enum 정합(계약4 해소 전제)으로 `/intake/survey`의 척도 선택에 반영한다.
**포함 작업:**
- 계약4(domain enum 8 vs 9, panic) 반영 — `apps/api/src/services/domain_routing.py`의 화이트리스트 갱신 또는 ai-server 9종을 8종으로 문서 정렬.
- `apps/mobile/lib/domain.ts`의 `inferDomainInstrument()` 화이트리스트도 동일 정합.
**완료 기준(checkable):**
- [ ] panic 후보 발생 시 검증 실패→PHQ4 강제폴백이 아니라 의도된 라우팅(AUDITC/PHQ9/GAD7/PHQ4 중 정합 결과) 확인.
- [ ] domain enum 스키마(백엔드 계약 vs ai-server) grep 일치 확인(8=8 또는 9=9로 통일).
**검증 방법:** VP-004류 panic-표현 세션 재현 시나리오(과거 arc 재사용 가능, `analysis_app_merge_20260721.md` 계약4 각주 "VP-004 arc 재발 예상" 참조)로 라우팅 결과 확인.
**담당 코드영역:** `apps/api/src/services/domain_routing.py`, `packages/shared-contracts`(DomainCandidate), `apps/mobile/lib/domain.ts`.
**의존성:** Phase 1 완료(session_state 확립으로 domain/infer 호출 시점의 대화 컨텍스트가 온전해야 함) + Phase 0 계약4.

### Phase 3 — F3 문진 plan/score 정본화

**목표:** `/ai/survey/plan` 배선(현재 완전 미배선) + `/ai/survey/score`(계약3 해소) 배선으로 로컬 근사 컷오프 폴백을 제거하고 ai-server 정본 채점기를 정식 사용한다.
**포함 작업:**
- 계약3(§5.3) 반영 후 `apps/api/src/services/questionnaire.py`의 `score_with_ai` 경로가 실제로 200을 받도록 확인.
- `/ai/survey/plan` 호출 지점 신설(현재 apps/api 어디서도 미호출) — Phase 2의 domain 추론 결과(`ai_predicted_disease.recommended_questionnaire`)를 `/ai/survey/plan` 입력으로 연결.
**완료 기준(checkable):**
- [ ] `/ai/survey/score` 응답이 AUDIT-C 한국 절사점·PHQ-9 item9 SI flag를 포함해 200으로 반환(로컬 폴백 미사용 확인 — 로그에 `local fallback` 카운트 0).
- [ ] `/ai/survey/plan`이 최소 1개 실 세션에서 호출되어 `scale`/`administration_mode`/`si_supplement`/`items`를 반환.
**검증 방법:** 4종 문진(PHQ9/GAD7/AUDITC/PHQ4) 각 1건씩 실제 응답 세트로 스코어링 스모크, 422 재현 셀(§5.3) 재실행 0건 확인.
**담당 코드영역:** `apps/api/src/services/questionnaire.py`, `packages/shared-contracts`(SurveyScoreInput/Request), `apps/ai-server/src/schemas/survey.py`(변경 불필요).
**의존성:** Phase 0 계약3 + Phase 2(척도 추천 입력 확보).

### Phase 4 — 병원 탐색 맵

**목표:** `hospitals.tsx`(완전 stub)를 사용자주도 병원 탐색 기능으로 전환한다. §6 상세.
**포함 작업:** §6의 옵션 A/B 중 선택안 구현 설계(코드는 이 PRD 범위 밖 — 설계만).
**완료 기준(checkable):**
- [ ] 옵션 선택 완료(사용자 결정, §9).
- [ ] 선택안의 키 관리/CORS/rate-limit 방안 문서화.
- [ ] ADR-040/041 준수 확인 — ai-server `nearby_facilities` agent 재도입 없음(코드 grep으로 재확인).
**검증 방법:** 선택안 프로토타입(옵션 A면 apps/api 신규 라우트 스모크, 옵션 B면 모바일 직접호출 CORS 스모크) — 실행은 후속 구현 단계.
**담당 코드영역:** 옵션 A: `apps/api/src/api/v1/`(신규 라우트) + `apps/api/src/services/`. 옵션 B: `apps/mobile/lib/`(신규 client) + `apps/mobile/app/(patient)/(tabs)/hospitals.tsx`.
**의존성:** 없음(F1-F3와 독립) — 병렬 착수 가능하나 우선순위상 마지막.

## 5. Phase 0 상세 — 계약 불일치 4건 + DB 발견 2건 + BUG-055 + BUG-056

### 5.1(계약1) `/ai/chat/respond` 계약 붕괴

**근거:** `analysis_app_merge_20260721.md` 발견 1. 백엔드 `ChatRequest{session_id,messages[],grounding}`(`packages/shared-contracts`[^w6a] `contracts/chat.py:103-114`, `extra=forbid`) vs ai-server `DialogueInput{user_message 필수}`(`schemas/dialogue.py:32`, `routes/chat.py:87-93`). 응답도 `ChatResponse{reply,progress,latency_ms}` vs `DialogueOutput{assistant_response,...}` 비호환. `extra=forbid`이므로 필드명 불일치는 즉시 422로 귀결한다(스키마 강제).

[^w6a]: 이하 본 문서에서 `packages/shared-contracts` 인용은 실제 세그먼트 `packages/shared-contracts/python/src/`를 생략 표기한 것이다(독립 검증 critic 렌즈 발견 #2, 2026-07-22).

**결과:** WS 라이브챗이 상시 422→무응답 degrade. `session_state` 왕복 채널 부재로 `deployment_integration_plan.md` §5(e)가 요구하는 신규 필드(`asked_slot_counts`/`risk_screening_incomplete`/`clinical_escalation_required`/`handoff_delivered`, ADR-044 백스톱 산출물 포함)가 플랫폼에 전혀 도달하지 못한다.

**옵션:**
- (A) `packages/shared-contracts`의 `ChatRequest`/`ChatResponse`를 ai-server `DialogueInput`/`DialogueOutput` 필드명·구조에 맞춰 개정(필드 rename/추가: `user_message`, `session_state`, `filled_slots`, `patient_history_context` 등 수신; 응답측 `assistant_response`, `session_state`, `risk_level`, `requires_human_review` 등 반환 — 응답측 `session_state`는 §4 완료기준·ADR-044가 요구하는 4필드 `asked_slot_counts`/`risk_screening_incomplete`/`clinical_escalation_required`/`handoff_delivered`를 포함해야 함(clinical-validator finding 3, 2026-07-22)). **장점:** ai-server 코드 변경 0, deployment_integration_plan §5(e)의 기존 검증된 시퀀스를 그대로 재사용. **단점:** apps/api의 WS 핸들러·모바일 `ChatResponse` 소비부 동시 변경 필요(파급 범위 큼).
- (B) apps/api에 어댑터 계층 신설 — 기존 `ChatRequest`/`ChatResponse` 계약은 모바일 대상 그대로 유지, `services/chat.py` 내부에서 `DialogueInput`/`DialogueOutput`으로 변환. **장점:** 모바일 계약 불변, 변경 범위가 apps/api 내부로 국한. **단점:** 변환 로직이 이중 유지보수 대상이 되고, `session_state`처럼 모바일이 직접 알 필요 없는 필드도 왕복 보관 책임이 apps/api에 추가된다(현재 apps/api DB 스키마에 `session_state` 저장 컬럼 없음 — 신설 필요, 또는 세션 서버측 캐시 신설).

**권고 방향(설계 관점, 최종 선택은 사용자):** 옵션 B가 모바일 파급을 최소화하나, `session_state`(dict)를 어딘가에 영속해야 하므로 DB 스키마 변경(신규 컬럼 또는 `sessions` 테이블 JSONB 확장)이 필요 — 이는 §5.6(DB F2 이관 절차)과 유사한 마이그레이션 리스크를 다시 발생시킨다. 두 옵션 모두 결정 필요(§9).

**422 재현 검증 셀(재현 절차만 명시, 실행은 Phase 1):**
| 항목 | 내용 |
|---|---|
| 사전조건 | MOCK=0, 실 ai-server 컨테이너 기동, `.env` LLM 키 유효 |
| 절차 | 모바일 `intake/chat.tsx`에서 1턴 메시지 전송 → apps/api WS 핸들러가 `ChatRequest` 그대로 ai-server `POST /ai/chat/respond`에 전달(현재 코드 경로) |
| 기대 결과(수정 전) | ai-server `DialogueInput` 검증 실패(`user_message` 필드 없음, `extra=forbid` 위반 가능) → HTTP 422, WS 상으로는 무응답/degrade 배너 |
| 기대 결과(수정 후, 옵션 A 또는 B 적용) | HTTP 200, `assistant_response` 정상 수신, `session_state` 다음 턴 요청에 포함되어 재전달 |
| 상태 | CONFIRMED-runtime(qa TestClient 오프라인 재현, 2026-07-22) — 백엔드 `ChatRequest`를 그대로 `/ai/chat/respond`에 전달 시 422 `{"loc":["body","user_message"],"msg":"Field required"}` 재현됨 |

### 5.1a 이중 안전경로 정정 및 clinical_escalation_required 무소비자 gap (clinical-validator finding 2, 2026-07-22)

**정정:** §3 매트릭스 row-16(`emergency.tsx`)의 기존 서술("근본 신호는 Phase 0 계약1 수정에 의존")은 부정확하다. 실제로는 **두 개의 독립 안전 경로**가 존재한다:

1. **플랫폼측 per-turn `SafetyClassifier` 경로** — `/ai/safety/classify` → `risk_events` 테이블 기록 → WS `risk:detected` emit(`apps/api/src/api/v1/sessions.py:684-729`, `services/safety.py`, `services/ai_client.py:74-75`). 이 경로는 §5.1 계약1(`/ai/chat/respond` 계약 붕괴) 수정 여부와 **무관하게 이미 독립 작동**한다 — `emergency.tsx`(row-16)의 근본 트리거는 이 경로다.
2. **ai-server 오케스트레이터 escalation 경로** — dialogue 세션 상태 내부에서 산출되는 `clinical_escalation_required`/`risk_screening_incomplete`(ADR-044 백스톱 산출물)가 `session_state`를 통해 플랫폼에 왕복해야 도달하는 경로. 이 경로만 §5.1 계약1 수정에 의존한다.

**명명해야 할 gap(fail-silent, BUG-055 수정 후에도 잔존):** ai-server가 산출하는 `clinical_escalation_required`/`risk_screening_incomplete` 신호를 **플랫폼측(apps/api) 소비자가 전무**하다(`grep apps/api` 0건 확인, 2026-07-22). 즉 §5.1 계약1과 §5.2 BUG-055가 모두 수정되어 이 필드들이 `session_state`를 통해 플랫폼에 물리적으로 도달하더라도, apps/api 쪽에 이를 읽어 처리(예: `risk_events` 기록, WS emit, 임상의 알림)하는 코드가 없으면 신호는 여전히 도달할 곳이 없는 채로 소실된다. 이는 §5.1/§5.2 스키마 수정과는 별개의 **downstream consumer 미구현** 문제이며, §8 리스크 및 아래 §9 결정 항목에 후속 작업으로 등재한다.

### 5.2(계약2) BUG-055 실현 — risk_assessment/escalation forwarding 통로 전무

**근거:** `error.md` BUG-055(open, major). `HandoffReportRequest.sessions[].final_slots: dict[str,str]`(`packages/shared-contracts/python/src/contracts/longitudinal.py:87`, `final_slots`는 동일 파일 `LongitudinalSessionEntry`, `longitudinal.py:40`; import는 `apps/ai-server/src/routes/handoff.py:25`)에 `risk_assessment`/`session_state`/`escalation` 필드 부재 + `/ai/slots/extract`는 `risk_assessment`를 설계상 drop(`routes/slots.py:77-81`, BUG-049 fix로 인한 의도된 필터) + 백엔드 `clinical_slots`는 domain 라우팅에만 소비 → ai-server의 위험평가/에스컬레이션 신호가 플랫폼 handoff에 도달할 통로가 전무하다(fail-silent).[^w1]

[^w1]: 정정(독립 검증 critic 렌즈, 2026-07-22): 최초 PRD 초안은 이 근거를 `schemas/domain_inference.py:137`로 인용했으나, 그 라인은 `DomainInferenceInput.final_slots`(F2 `/ai/domain/infer`용 별개 클래스)이며 `HandoffReportRequest`와 무관하다. 실질 결론(`final_slots`가 `dict[str,str]`이라 `risk_assessment` 필드 자체가 스키마상 존재하지 않고, 이로 인해 강제 경로가 없다는 결론)은 `longitudinal.py` 확인으로도 그대로 성립 — 결론은 불변, 근거 인용만 정정.

**옵션(BUG-055 원문 routing note 및 CLAUDE.md 임상안전 원칙 반영):**
- (A) **문서 변경 — 비권장/실격(disqualified for safety-critical fields, clinical-validator finding 2, 2026-07-22)** — `docs/ai/api/`에 "risk_assessment는 `/ai/chat/respond` 응답의 `session_state.slot_data.risk_assessment`에서 가져와 `/ai/handoff/report` 요청의 `final_slots.risk_assessment`로 명시적으로 threading해야 한다"는 계약을 문서화. **장점:** 스키마 변경 없음, 즉시 적용 가능. **실격 사유:** fail-silent 특성이 스키마 레벨에서 강제되지 않는 문서-only 계약이 BUG-055를 애초에 발생시킨 바로 그 메커니즘이다(구현자가 문서를 놓쳐 동일 결함이 이미 한 차례 재발) — 안전-치명 필드(risk_assessment/escalation)에는 이 옵션을 채택하지 않는다.
- (B) **schema/endpoint 변경 — 권고** — `HandoffReportRequest.sessions[].final_slots`(또는 신규 `risk_assessment` 최상위 필드)를 스키마 레벨에서 필수화하거나, `risk_grounded=True`인데 `risk_assessment`가 비어있으면 명시적 오류(422 또는 경고 필드)를 반환하도록 ai-server 측에 fail-loud 검증 추가. **장점:** 임상안전 fail-silent를 fail-loud로 전환 — "질문 자체가 생략된 채 인계"(ADR-044가 이미 유사 원칙을 채택)와 동일한 안전설계 방향. **단점:** ai-server 스키마/라우트 코드 변경 필요(이 PRD 범위 밖의 developer 작업), stateless 원칙(R2) 위반 없이 검증 로직만 추가하는 설계가 필요.

**권고 방향:** ADR-044가 이미 "위험 갭을 침묵 인계하지 않는다"는 임상안전 fail-loud 원칙을 프로덕션 챗 경로에 채택한 전례가 있다 — 동일 원칙을 F5 handoff 경로에도 확장하는 옵션 B를 권고한다. 옵션 A는 안전-치명 필드에는 실격으로 표기(위 근거). 코드 변경 범위 확정은 developer+clinical-validator 검토가 필요한 결정 사항(§9 사용자 결정 대기).

**상태:** CONFIRMED-runtime(qa TestClient 오프라인 재현, 2026-07-22) — `HandoffRequest`에 `escalation`/`risk_assessment`/`session_state`를 주입해 전송 시 pydantic `extra_forbidden` 오류 3건 재현됨(스키마가 이 필드들을 애초에 받지 않음을 실측 확인, fail-silent 통로 부재 결론을 뒷받침).

### 5.3(계약3) `/ai/survey/score` responses shape 불일치

**근거:** `analysis_app_merge_20260721.md` 발견 3. 계약 `responses: list[int]` vs ai-server `SurveyScoreInput.responses: list[SurveyItemResponse{index,value}]`(`schemas/survey.py:10-25`) → 상시 422 → 로컬 근사 컷오프가 상시 사용되어 정본 채점기(AUDIT-C 한국 절사점, PHQ-9 item9 SI flag)가 작동하지 않는다.

**옵션:** (A) 백엔드 계약을 `list[SurveyItemResponse]`로 개정(ai-server 계약 그대로 채택 — 코드 변경 없음, 백엔드/모바일 페이로드 조립부만 `index` 포함하도록 확장). (B) ai-server가 `list[int]`도 허용하도록 완화(정본 스키마 완화, 순서-기반 index 암묵 가정 — 스키마 명확성 저하, 비권고).

**권고 방향:** 옵션 A(백엔드 계약을 ai-server 정본에 맞춤) — ai-server의 `SurveyItemResponse{index,value}` shape가 이미 정본 채점기 요구사항이므로 계약1과 달리 이 항목은 파급 범위가 apps/api 페이로드 조립 로직에 국한되어 상대적으로 단순.

**422 재현 검증 셀:**
| 항목 | 내용 |
|---|---|
| 절차 | `intake/survey.tsx`에서 PHQ-9 9문항 응답 제출 → `submitQuestionnaire`가 `answers`를 `list[int]`로 조립해 `/api/v1/sessions/{id}/questionnaires` 경유 `score_with_ai` 호출 |
| 기대 결과(수정 전) | ai-server `SurveyScoreInput` 검증 실패(shape mismatch) → 422 → `questionnaire.py`의 로컬 컷오프 폴백 경로로 상시 진입(현재 상태) |
| 기대 결과(수정 후) | 200, ai-server 정본 채점 결과(severity, item9 SI flag 등) 수신 |
| 상태 | CONFIRMED-runtime(qa TestClient 오프라인 재현, 2026-07-22) — `responses: list[int]`을 그대로 `/ai/survey/score`에 전달 시 422 `model_attributes_type` 재현됨 |

### 5.4(계약4) domain enum 8 vs 9 (panic)

**근거:** `analysis_app_merge_20260721.md` 발견 4. 계약 `DomainCandidate.domain` 8종 vs ai-server `DomainName` 9종(panic 추가) → panic 후보 발생 시 계약측 검증 실패→클라이언트 폴백(PHQ4)으로 graceful하게 흡수되나, 의도된 라우팅(예: panic→적정 척도)이 무력화된다. 사전분석은 "VP-004 arc 재발 예상"이라 각주.

**옵션:** (A) 계약 8종에 `panic` 추가(ai-server 9종에 정합). (B) ai-server가 panic을 8종 중 하나로 매핑 후 하위호환 유지(정보 손실 발생, 비권고).

**권고 방향:** 옵션 A — enum 확장은 파급이 작고(화이트리스트 상수 1곳 추가) ai-server가 이미 검증된 9종 분류를 갖고 있으므로 계약을 그쪽에 맞추는 것이 일관적.

**상태:** CONFIRMED-runtime(qa TestClient 오프라인 재현, 2026-07-22) — 계약측 `DomainCandidate(domain='panic')` 구성 시 pydantic `ValidationError`(`literal_error`, 계약 8종 vs ai-server 9종) 재현됨.

### 5.5(DB F1, CRITICAL) questionnaire_types CHECK vs load_simulations ALLOWED_SCALES 불일치

**근거:** `analysis_db_schema_20260721.md` 발견 F1. Alembic 0010이 `questionnaire_results.type` CHECK 제약을 비하이픈 4종(PHQ9/GAD7/AUDITC/PHQ4)으로 정의했으나, `load_simulations.py:102`의 `ALLOWED_SCALES`는 하이픈 5종(PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C)을 그대로 INSERT(`:366`)한다 — head DB에서 VP 코퍼스 오프라인 적재 시 CHECK 위반 실패. WHO-5/PHQ-4는 제약에 아예 없음.

**영향 범위:** 런타임 트랜잭션(실제 문진 제출 경로)은 이미 비하이픈 4종으로 정상 동작(§0010 CHECK와 apps/api 애플리케이션 코드가 일치) — 깨지는 것은 **오프라인 RAG 코퍼스 적재(load_simulations)** 뿐이다. 이는 Phase 1~4 실연동 자체를 막지 않으나, session_insights/RAG 코퍼스 갱신이 필요한 시점(F2 검증 데이터 갱신 등)에 실패한다.

**수정 설계:** `load_simulations.py`의 `ALLOWED_SCALES`를 0010의 비하이픈 4종 표기로 정합(하이픈 제거) + WHO-5는 questionnaire_results 대상이 아닌 별도 처리 확인(현재 CHECK 미포함이 의도된 것인지 별도 확인 필요 — UNVERIFIED, 이 PRD는 사전분석 재파생 금지 원칙상 재조사하지 않음, developer 검토 권고).

**검증 방법:** 오프라인 재적재 드라이런(dev DB, head 0010 스키마) → INSERT 실패 0건 확인. 프로덕션 런타임 트랜잭션은 영향 없으므로 별도 회귀 불필요.

### 5.6(DB F2, MAJOR) 0008→0010 제약 이관 누락

**근거:** `analysis_db_schema_20260721.md` 발견 F2. 0008이 기존 행을 하이픈 표기로 UPDATE했는데 0010은 역-UPDATE 없이 비하이픈 CHECK를 바로 부여 → 하이픈 데이터를 보유한 DB에서 0010 upgrade의 `ADD CONSTRAINT`가 실패할 수 있다. 빈 DB에서는 무해. **DGX 실데이터 상태는 UNVERIFIED**(사전분석 명시 그대로 보존).

**수정 설계:** 0010 마이그레이션에 선행 `UPDATE questionnaire_results SET type = REPLACE(type, '-', '')` 스텝 추가(멱등, 이미 비하이픈이면 no-op) 후 `ADD CONSTRAINT`. 단, 이는 alembic 마이그레이션 파일 수정(코드 변경)에 해당하므로 이 PRD는 설계만 제시하고 실행은 developer 담당 후속 작업으로 명시.

**검증 방법:** DGX DB의 실제 `questionnaire_results.type` 값 분포 확인(하이픈 존재 여부, 현재 UNVERIFIED) → 존재 시 위 UPDATE 스텝 필요, 부재 시(빈 DB 또는 이미 비하이픈) 스텝 불필요이나 멱등하므로 포함해도 무해.

### 5.7 BUG-056 — 디자인 스코프 (design-scope deferred)

**근거:** `error.md` BUG-056(open, major, "design-scope deferred to user decision, git FROZEN"). `DialogueAgent`가 raw `filled_slots`(caller 공급, 매 턴 축소 가능)로 steering target을 계산하고, orchestrator의 protected `state.slot_data`(additive-union)와 union하지 않는다 — 이는 F1 대화 품질(steering 정확도)에 국한된 이슈이며 handoff/coverage 게이트 자체는 영향받지 않는다(BUG-056 원문 명시).

**이 PRD에서의 처리:** 코드 수정 대상 아님(design-scope, git FROZEN 상태 유지). Phase 1 완료 기준에는 포함하지 않되, Phase 1 QA 관찰 항목으로만 등록 — Phase 1 왕복 스모크 중 `filled_slots` 축소 패턴이 재현되는지 관찰하고, 재현 시 별도 developer 티켓(이 PRD 범위 밖)으로 라우팅한다.

## 6. 병원 탐색 맵 설계

**전제(ADR-040/041 준수, 절대 준수):** `nearby_facilities` agent, `/ai/nearby/*` 라우트, HIRA/Kakao adapter는 ADR-040(non-LLM service adapter로 재분류, 코드 유지)→ADR-041(코드/route/schema 완전 archived·부활 금지)로 확정 폐기되었다(`app_wiring_inventory_20260721.md` §C: `.pyc` 잔여만 존재, `.py` 소스 없음, `orchestrator.py`/`routes/__init__.py` 미참조, 확인 완료). **본 PRD는 ai-server agent 부활을 어떤 옵션에서도 제안하지 않는다.** 병원 탐색은 앱측 사용자주도(user-initiated) 기능으로만 설계한다.

**아카이브 자산(복원 가능, 참고용):**
- `_archive/legacy_code/agent_inventory_wave6/16_nearby_facilities.md`, `hira_kakao_map_api_usage_guide.md`
- 파이프라인: HIRA `getHospBasisList`(dgsbjtCd=03 정신과 고정) → type-code 필터 → Kakao Local 키워드-카테고리 교차검증 → HIRA `MadmDtlInfoService2.8` 전문의수 검증(count==0 drop) → 정렬(not-verified, distance, -count, name).
- 어댑터 인터페이스: `NearbySearchInput`(session_id, entity_type, lat, lng, radius_km, page_no, num_of_rows, opt name/sido_cd/sggu_cd/subject_code/hospital_type_code) → `Place/Marker/MapPayload`(id, entity_type, name, address, phone, type_code, lat/lng, distance_km, coordinate_source, group, specialist_verified, psychiatry_specialist_count, is_university_hospital_candidate, nullable emergency_available/open_now — **절대 true 기본값 금지**, 안전 필드).
- **HIRA 키 라이브 유효 이력**: `deployment_integration_plan.md` §5(c) — `HIRA_SERVICE_KEY`는 현재도 live 상태이나 PHR 정신과-약물 분류(`src/phr_ingest.py`)에만 scope되며 병원 검색과 무관. 병원 검색용 재사용 시 별도 키 유효기간/쿼터 재확인 필요(UNVERIFIED — 재확인은 이 PRD 범위 밖).

### 옵션 A — 백엔드 프록시(apps/api → HIRA/Kakao)

| 항목 | 내용 |
|---|---|
| 구조 | 모바일 → `POST/GET /api/v1/hospitals/nearby`(신규, apps/api) → 서버측에서 HIRA+Kakao 직접 호출 → 정제된 결과 반환 |
| 키 관리 | HIRA/Kakao 키를 서버 `.env`에만 보관 — 클라이언트 노출 없음(장점) |
| CORS | 해당 없음(서버-서버 호출) |
| rate limit | apps/api에서 자체 캐싱/쿼터 관리 가능(HIRA API 호출 횟수 제어) |
| 오프라인 | 앱은 결과만 받으므로 오프라인 대응은 표준 캐시 전략(마지막 결과 로컬 저장) 적용 가능 |
| 안전 필드 | `emergency_available`/`open_now` nullable 원칙을 서버측에서 강제하기 쉬움(단일 지점 검증) |
| 단점 | apps/api에 신규 외부 API 연동 부담(개발 범위 증가), HIRA/Kakao 응답 지연이 apps/api 응답 지연에 직결 |

### 옵션 B — 앱 직접 호출(모바일 → HIRA/Kakao 직접)

| 항목 | 내용 |
|---|---|
| 구조 | 모바일이 HIRA/Kakao API를 직접 호출 |
| 키 관리 | 클라이언트 번들에 키 포함 위험(리버스엔지니어링 노출) — Kakao는 앱 키를 도메인/패키지 제한으로 완화 가능하나 HIRA는 서버-투-서버 설계가 일반적(공공데이터포털 키 노출 관행상 비권장) |
| CORS | Kakao Local Web API는 CORS 이슈 발생 가능(모바일 네이티브는 CORS 영향 적으나 Expo Web 빌드 시 문제) |
| rate limit | 앱 단위 쿼터 관리 어려움(사용자별 호출 분산, 서버 집계 불가) |
| 오프라인 | 각 클라이언트가 개별 캐싱 구현 필요(일관성 낮음) |
| 안전 필드 | `emergency_available`/`open_now` 검증을 클라이언트마다 반복 구현 필요(안전 원칙 준수 리스크 분산) |
| 단점 | HIRA 키 노출은 공공데이터 API 약관 위반 소지 — 일반적으로 비권장 패턴 |

### 권고

**옵션 A(백엔드 프록시) 권고.** 근거: (1) HIRA 키의 서버-투-서버 관행이 이미 `phr_ingest.py`에서 확립되어 있어 아키텍처 일관성이 높다, (2) `emergency_available`/`open_now` never-true-default 안전 원칙(아카이브 어댑터 인터페이스 명시)을 단일 지점(apps/api)에서 강제하는 것이 클라이언트 분산 구현보다 임상안전 관점에서 안전하다, (3) rate-limit/쿼터 관리가 서버측에서 용이하다. 단, 최종 선택은 §9 사용자 결정 대기.

**hospitals.tsx 현 상태 반영:** 현재 완전 stub(백엔드 호출 0, `tel:119`만, map SDK 참조 없음, S-11 주석 "Demo stub — full search is Phase 2, FR-012"). 옵션 A/B 어느 쪽을 택하든 map SDK(Kakao Map SDK 또는 대체) 도입이 별도로 필요 — 이 PRD는 데이터 연동 설계만 다루고 지도 렌더링 SDK 선택은 범위 밖(후속 논의).

## 7. 검증 전략 (phase별)

| Phase | 검증 방법 | 근거 패턴 |
|---|---|---|
| Phase 0 | 문서 내적 일관성(계약안-스키마 파일 경로/필드명 grep 일치), 422 재현 셀 4건 절차 명세(실행 없음) | 사전분석 CONFIRMED-by-read 방식 준용 |
| Phase 1 | 왕복 스모크(1세션 다중턴, session_state 필드 존재 확인) + 422 재현 셀 재실행 0건 | `deployment_integration_plan.md` §5(e) 시퀀스, EXP-030 왕복 검증 패턴 참조 |
| Phase 2 | VP-004류 panic 시나리오 재현, domain enum grep 일치 | BUG-055/056 트리아지에 쓰인 실 세션 로그 재현 패턴 |
| Phase 3 | 4종 문진 스코어링 스모크(로컬 폴백 카운트 0 확인), plan 호출 1건 이상 | dual-gate(qa 기능검증 + clinical-validator 임상적정성) 패턴, CVR 게이트 참조 |
| Phase 4 | 옵션별 스모크(A: apps/api 신규 라우트 응답 검증, B: CORS/키 노출 점검) | — |

각 phase 완료 후 결과는 critic 검토(REV) 및 clinical-validator 검토(임상안전 관련 항목 — 계약2/BUG-055, 병원맵 안전필드)를 거쳐야 사용자 보고 가능(CLAUDE.md 게이트 규칙).

## 8. 리스크

- **계약1 수정 파급:** 옵션 A/B 어느 쪽이든 WS 핸들러+모바일 소비부 동시 변경이 필요해 Phase 1 착수 지연 가능성.
- **DB F2 UNVERIFIED 상태:** DGX 실데이터의 하이픈 표기 존재 여부가 확인되지 않은 채 마이그레이션 설계를 진행하면, 실행 시점에 예상치 못한 `ADD CONSTRAINT` 실패가 재발할 수 있음.
- **BUG-055 옵션 B(fail-loud) 선택 시:** 정상 세션인데 risk_assessment 필드가 누락되는 엣지케이스(예: 짧은 세션으로 SI 스크린 자체가 도달하지 못한 경우)를 오탐 escalation으로 처리하지 않도록 ADR-044의 `_SI_SCREEN_RESERVE_TURNS` 로직과의 상호작용을 developer+clinical-validator가 함께 검토해야 함(단독 스키마 강제만으로는 임상 오탐 위험).
- **병원맵 옵션 A 채택 시:** HIRA API 쿼터/키 만료 갱신 책임이 apps/api 운영팀으로 이전 — 기존 ai-server 운영 경험(HIRA 키 관리)을 apps/api 팀에 인계하는 절차가 별도 필요.
- **BUG-056 미해결 상태 지속:** Phase 1에서 관찰만 하고 수정하지 않으므로, dialogue steering 품질 저하(재질문 반복 등, VP-010 s5 유형)가 실사용자 세션에서도 재현될 가능성 — 사용자 경험 저하 리스크로 별도 인지 필요.
- **`clinical_escalation_required`/`risk_screening_incomplete` 무소비자 gap(clinical-validator finding 2, §5.1a):** §5.1(계약1) + §5.2(BUG-055)가 모두 수정되어 이 신호들이 `session_state`로 플랫폼에 물리적으로 도달하더라도, apps/api 쪽에 이를 소비하는 코드가 전무(`grep apps/api` 0건)하여 fail-silent gap이 남는다. 별도 후속 작업(downstream consumer 구현)으로 명시적으로 스코프하지 않으면 BUG-055 수정의 실효가 없다.
- **F5(handoff 리포트 렌더링) out-of-scope로 인한 잔여 리스크(clinical-validator finding 4):** 본 PRD는 §5.2에서 risk_assessment가 handoff 요청까지 threading되는 통로만 다루며, `report/detail.tsx`의 실제 리포트 본문 렌더링(F5)은 out-of-scope다(§1 비목표). 따라서 §5.1/§5.2가 모두 해소되어도 "escalation 신호가 실제 임상의 화면에 표시되어 열람 가능한가"는 이 PRD 범위 내에서 완결되지 않는 잔여 리스크로 남는다 — F5 PRD에서 별도 확인 필요.

## 9. 결정 필요 항목

| # | 항목 | 옵션 | 결정 필요 사유 |
|---|---|---|---|
| 1 | 계약1(/ai/chat/respond) 수정 방향 | A(계약 전면 개정) / B(apps/api 어댑터) | 파급 범위·`session_state` 영속 위치가 옵션에 따라 DB 스키마 변경 여부를 좌우 |
| 2 | BUG-055 forwarding 경로 | A(문서화만, 안전-치명 필드에 실격/비권장 — §5.2) / **B(schema/endpoint fail-loud, 권고)** | 임상안전 성격 — A는 BUG-055를 발생시킨 메커니즘 자체이므로 대등 대안이 아님. B 채택 시 세부 구현(422 vs 경고 필드)은 developer+clinical-validator+사용자 공동 결정 사항 |
| 3 | DB F2 마이그레이션 UPDATE 스텝 포함 여부 | 포함 / 제외 | DGX 실데이터 하이픈 표기 존재 여부가 UNVERIFIED — 확인 전 결정 보류 가능 |
| 4 | 병원맵 아키텍처 | A(백엔드 프록시, 권고) / B(앱 직접호출) | 키 관리·안전필드 강제 지점이 옵션에 따라 상이 |
| 5 | BUG-056 처리 시점 | 이번 웨이브 미수정(design-scope 유지) / 별도 스코프로 재상신 | 현재 "git FROZEN" 상태 — 재개 여부는 사용자 결정 |
| 6 | apps/api DGX 배포 위치(filemanager 환경전제 #1, blocking Phase 1) | A(`docker-compose.dgx.yml`에 apps/api+postgres 신규 서비스 추가) / B(별도 host에 독립 배포) | `docker-compose.dgx.yml`은 현재 ai-server만 정의(`infra/deploy/docker-compose.dgx.yml:29` 확인) — apps/api는 자체 `Dockerfile`은 있으나 DGX compose 서비스·런북이 없어 Phase 1 완료기준("session_state가 플랫폼 DB 도달")이 이 결정 없이는 검증 불가 |
| 7 | 병원맵 Kakao 키 발급(filemanager 환경전제 #5, blocking Phase 4) | 신규 발급 / 보류 | Kakao 키 placeholder가 어느 `.env.example`에도 없음(과거 `nearby_facilities` 삭제 시 함께 제거됨) — §6 옵션 A/B 어느 쪽이든 신규 발급 필요 |
| 8 | ENCRYPTION_KEY 공유 SOP(filemanager 환경전제 #3, blocking ops, Phase 1) | 수동 배포 절차 문서화 / 자동화(secret 관리 도구 도입) | `apps/api core/encryption.py` ↔ `apps/ai-server rag/crypto.py`가 동일 AES-256-GCM 키를 전제하나 두 `.env`가 독립 관리되어 공유 메커니즘이 없음 — #6(apps/api 배포 위치) 결정과 연동되어야 함 |

## 9a. Phase 착수 전제 — 환경·배포 (filemanager 환경전제 검증, 2026-07-22)

Phase 0의 계약/스키마 선행정렬과 별개로, 아래 6건은 각 Phase 착수 여부를 물리적으로 좌우하는 환경·배포 전제다. §9의 결정 항목(#6~#8)과 연동한다.

| # | 항목 | 심각도 | 대상 Phase | 내용 | 필요 조치 |
|---|---|---|---|---|---|
| 1 | apps/api DGX 배포 위치 미정의 | blocking | Phase 1 전제 | `docker-compose.dgx.yml`은 ai-server만 정의(postgres·api 서비스 없음, `infra/deploy/docker-compose.dgx.yml:29` 확인). apps/api는 자체 `Dockerfile`이 있으나 DGX compose 서비스·런북이 부재 — Phase 1 완료기준("session_state가 플랫폼 DB 도달")이 이 전제 없이는 검증 불가 | §9 결정 #6(DGX 신규 compose 서비스 vs 별도 host) |
| 2 | WS TLS/reverse-proxy 인프라 부재 | blocking(prod-only) | Phase 1 | production은 `wss://` 강제이나 `infra/`에 TLS terminator가 없음. 로컬 LAN 평문 `ws://`는 현재도 가능 | TLS terminator 설계 + WS idle/handshake 타임아웃 명시 필요(코드 변경은 이 PRD 범위 밖, 설계만) |
| 3 | ENCRYPTION_KEY 공유 SOP 부재 | blocking(ops) | Phase 1 | apps/api `core/encryption.py` ↔ ai-server `rag/crypto.py`가 동일 AES-256-GCM 키를 전제하나 두 `.env`가 독립 관리되어 공유 메커니즘이 없음 | 키 배포 SOP 문서화(#1 apps/api 배포 위치와 연동, §9 결정 #8) |
| 4 | DGX DB 하이픈 데이터 확인 절차 미기재 | gap | Phase 0 | DB-F2(§5.6) 리스크가 실데이터 표기 상태(UNVERIFIED)에 의존 — 확인 절차 자체가 문서에 없었음 | 실행 절차 명시: `SELECT DISTINCT type FROM questionnaire_results;`를 operator DSN 접근권자가 실행 — 실행 담당자·자격증명 특정 필요(§9 결정 #3과 연동) |
| 5 | 병원맵 키 — Kakao blocking / HIRA gap | blocking(Kakao) / gap(HIRA) | Phase 4 | Kakao 키 placeholder가 어느 `.env.example`에도 없음(`nearby_facilities` 삭제 시 함께 제거) → 신규 발급 필요(§9 결정 #7). HIRA 키는 live이나 PHR 약물분류 scope(`src/phr_ingest.py`) — 병원 검색 재사용 시 재검증 필요(§6 기존 서술 유지, 재확인은 이 PRD 범위 밖) | 신규 Kakao 키 발급을 §9 선행 확인 항목으로 등재(완료) |
| 6 | Expo SDK 54 | note+gap | Phase 1-3 | `apps/mobile/package.json`에서 `expo ~54.0.0`/`expo-audio ~1.1.1` 마이그레이션 완료 확인(리스크 아님). 단 `mobile-expo-go-guide.md`는 Mac 로컬 LAN만 문서화 — DGX 대상 실기기 env 절차가 없음 | 가이드 확장 필요(#1 apps/api 배포 위치 선행 필요) |

## 9b. 독립 검증 결과 (2026-07-22)

본 PRD(초안 2026-07-21)는 4개 독립 렌즈로 재검증되었다. 검증된 매트릭스 사실(18/18 스크린 매핑, 계약 4건, DB 발견 2건)은 동결 확인되었고, 아래 발견은 위 §5.1a/§5.2/§8/§9/§9a에 반영되었다. 참조: `discussion.md` REV-007, CVR-047.

| 렌즈 | 담당 | 결과 | 반영 위치 |
|---|---|---|---|
| qa(런타임 재현) | qa | 4/4 CONFIRMED-runtime(오프라인 TestClient) — `/ai/chat/respond` 422, `/ai/survey/score` 422, `DomainCandidate('panic')` ValidationError, `HandoffRequest` extra_forbidden 3건 | §5.1, §5.2, §5.3, §5.4 상태 라벨 |
| critic(사실검증) | critic | 매핑 18/18 확인 + 이슈 2건(BUG-055 근거 오귀속, shared-contracts 경로 세그먼트 누락) — 모두 해소 | §5.2(W1 각주), §5.1(W6a 각주) |
| filemanager(환경전제) | filemanager | 6건(apps/api DGX 배포 미정의, WS TLS 부재, ENCRYPTION_KEY SOP 부재, DB 확인절차 미기재, Kakao 키 부재, Expo SDK 54 가이드 gap) | §9a, §9 결정 #6~#8 |
| clinical-validator(CVR-047) | clinical-validator | adequate-with-findings — finding 1(Option A/B 비대칭화 누락), finding 2(이중 안전경로 오서술 + 무소비자 gap), finding 3(ADR-044 4필드 누락), finding 4(F5 잔여 리스크 미명명) | §5.2/§9 결정 #2(finding 1), §3 row-16/§5.1a(finding 2), §5.1 옵션 A(finding 3), §8(finding 4) |

---
