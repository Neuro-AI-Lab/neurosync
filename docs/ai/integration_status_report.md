# DB·앱·기능 백엔드 연동 현황 종합 보고서

> **작성:** writer | **날짜:** 2026-07-25 | **범위:** 문서화만 — 코드 수정·실험·git 커밋·라이브 API 호출 없음.
> **근거 원칙:** 모든 수치·주장은 기존 기록(EXP/BUG/CVR/REV/STATE/ADR ID 또는 filemanager 실측 RESULT)을 인용한다. 기록에서 확인되지 않는 항목은 `UNVERIFIED`로 표기하며 창작하지 않는다.
> **불가침:** `docs/ai/agent_collaboration_f1f5.md`(사용자 병행 세션)는 읽기만 했고 본 보고서는 그 내용을 재파생하지 않는다.

## 0. 요약표

| 항목 | 현황 | 출처 |
|---|---|---|
| F1-F3(대화/도메인 라우팅/문진) 연동 | Phase 0-3 전 커밋 배선 완료, cross-phase 결합 재검증 완료 | STATE-2026-07-22b/c/d/e, STATE-2026-07-23 |
| F5(handoff 리포트) 파이프라인 | 계약 정합 + 라이브 정상화(BUG-066/067/068 해소) | STATE-2026-07-23f |
| 18-screen 라이브 재검증 최종 판정 | working 16 · not-wired-by-design 2(hospitals·records) · **screen-level defect 0** | EXP-031 results.md §7(FINAL) |
| F5 내러티브 내용 신뢰성(fabrication) | BUG-069/070 fixed-live-verified, BUG-071(fail-open) open/deferred | error.md BUG-069/070/071, STATE-2026-07-23g |
| F5 임상 사용 판정 | conditional-yes, Blocking: NO | CVR-054 |
| 로컬 커밋 | `feat/agent-inventory-cleanup` HEAD `735021f`, Master 대비 **17 ahead / 0 behind** | filemanager 실측 RESULT(2026-07-25) |
| Push/PR | **전량 미push**(원격 브랜치 참조 자체 없음), PR #72 상태 **UNVERIFIED-from-git** | filemanager 실측 RESULT |
| DB 마이그레이션 | alembic 0001→0012 체인, fresh-DB 무패치 부트스트랩 실증 | error.md BUG-065, EXP-031 results.md §0(재검증) |
| DGX 배포 | 런북(§6) 문서화 완료, **실행/집행은 미착수** | deployment_integration_plan.md §6 |
| 오픈 BUG(주요/미소) | BUG-053·054·055·056·058 open(major, BUG-058은 pre-existing·orthogonal) · BUG-071 open(minor, verifier fail-open) | error.md |

---

## 1. 요약

`feat/agent-inventory-cleanup` 브랜치는 F1(대화 intake)→F2(도메인 라우팅)→F3(문진 plan/score)→F5(handoff 리포트) 전 구간이 계약 정합·라이브 배선까지 완료된 상태이며, 18개 모바일 화면에 대한 라이브 재검증 최종 판정은 **결함 0건**(working 16 · 설계상 not-wired 2)이다(EXP-031 results.md §7 FINAL). F5 리포트의 내러티브 날조(BUG-069) 문제는 이중 방어(프롬프트 규율 + evidence_verifier 정합 체크)로 해소되어 clinical-validator가 임상 사용을 **conditional-yes**로 판정했으나(CVR-054), 검증기 fail-open 잔여 결함(BUG-071)과 apps/api 측 gender/시각 정보 미전달은 아직 열려 있다. filemanager의 2026-07-25 실측에 따르면 로컬 커밋 17개가 Master 대비 전량 **push되지 않은 상태**이며, PR #72의 실제 상태는 git 로그만으로 확인 불가능해 `UNVERIFIED`로 남겨둔다.

---

## 2. 계층별 현황

### (a) 앱(모바일)

18개 스크린 전체가 매핑되어 있으며(`docs/ai/integration_prd_f1f3_hospital.md` §3, 18/18 커버리지 확인), 최초 라이브 재검증(EXP-031 results.md §1, 1회차)과 커밋된 수정 웨이브 이후 재검증(§7 FINAL, 2회차)의 판정은 다음과 같다.

| 판정 | 스크린 수 | 목록 | 출처 |
|---|---|---|---|
| working | 16 | S01-07, S10-18(F5 report/detail 포함 — BUG-066 폐쇄로 degraded→working 상향) | EXP-031 results.md §7(FINAL) |
| not-wired(설계상 정상) | 2 | S08(hospitals, `tel:119`만) · S09(records, 로컬 mock) | EXP-031 results.md §7 |
| screen-level defect | 0 | — | EXP-031 results.md §7 |
| 부속: F2 domain/infer | degraded(비차단) | apps/api 4.5s 클라이언트 timeout < ai-server RAG 지연 ~5.5s → graceful fallback(200) — apps/api 자체 결함 아님, 근인 미확정 | STATE-2026-07-23f, EXP-031 results.md §4(재검증) |

- **MOCK 폴백:** `apps/mobile/lib/config.ts`의 `MOCK` 플래그가 dev 기본 ON — 라이브 재검증은 `MOCK=0` 실연동 전제로 수행됨(`docs/ai/integration_prd_f1f3_hospital.md` §2).
- **웹 dev-preview 폴백:** `apps/mobile/lib/{secure-store,prefs}.ts`의 웹 `localStorage` 폴백은 코드 확인으로 정성적 정확성만 검증되었고, 실제 웹 렌더 실행(headless)은 시간 예산상 미실행(EXP-031 results.md Open items 2, 재검증 §6 open item 5).
- **F5 리포트 화면(report/detail.tsx):** BUG-066/067/068 폐쇄 이후 클리니션 `GET /report`가 `status="ready"` + 실 12-section 내러티브를 반환하도록 정상화됨(EXP-031 results.md 재검증 §4).

### (b) apps/api 백엔드

3-tier BFF 구조(모바일 → `/api/v1/*` → ai-server `/ai/*`)로, F1-F3 전 구간이 실배선되어 있다.

| 기능 | 상태 | 근거 |
|---|---|---|
| F1 chat WS + `session_state` DB 영속 | 완료 — `Session.session_state`(JSONB)+`Session.clinical_escalation_required`(Boolean) 컬럼, 매 턴 영속, WS 재연결 시 seed 복원 | STATE-2026-07-22c |
| Safety 이중 게이트 + crisis wire | 완료 — apps/api 자체 턴단위 SafetyClassifier(pre-gate) + ai-server 오케스트레이터 2차 history-aware crisis 신호가 wire 소실되던 blocking 결함(BUG-060)을 발견·수정, `risk:detected`/RiskEvent 생성/escalation 전 경로 end-to-end 복원 | STATE-2026-07-23, CVR-051 |
| F2 라우팅(panic→GAD-7, substance→AUDIT-C) | 완료·임상 정당성 확인 — panic→GAD-7은 PHQ-4 폴백보다 임상적으로 우월(CVR-049), substance→AUDIT-C 매핑 갭도 정렬(CVR-050) | STATE-2026-07-22d, CVR-049/050 |
| F3 plan/score 정본화 + proxy caveat 채널 | 완료 — `/ai/survey/plan` 배선(scale/administration_mode/si_supplement/items 반환), 4종 문진(PHQ9/GAD7/AUDITC/PHQ4) AI-success 스모크(mutation-kill로 non-tautology 증명) 5건 pass, proxy caveat이 `audit_logs`에 영속(clinician-facing 화면 미독출은 잔여 gap) | STATE-2026-07-22e, CVR-050 finding 2 |
| 리포트 상태머신 | 정상화 — `generating`→`ready`/`failed` 전이, 90s 타임아웃 예산이 evidence_verifier 3-attempt 루프(~48s 관측)를 흡수 | error.md BUG-068 |

### (c) DB

- alembic 체인은 `0001→...→0012`로 구성되며, **fresh-DB 무패치 부트스트랩이 실증**되었다 — 별도 throwaway pgserver에서 `alembic upgrade head` 단독 실행으로 전 체인 성공(BUG-065 완료 기준 충족, error.md BUG-065). `0001`의 `is_minor` GENERATED 컬럼(비-immutable `CURRENT_DATE`) 문제를 GENERATED 제거 + 앱 계산(`auth.py::_is_minor`)으로 해소.
- `0009a`(하이픈→비하이픈 questionnaire_type 백필) 마이그레이션이 `0010` 앞에 삽입되었고, DGX 실 DB는 probe 결과 하이픈 데이터가 존재해 이 백필이 실제로 필요한 것으로 확인됨(ADR-046 #7).
- `0012`가 `risk_events.status` varchar(32)+CHECK 확장, `messages.role` CHECK에 `'assistant'` additive 추가.
- **데모/DGX 이원 상태:** 데모 스택은 별도 throwaway pgserver(`experiments/EXP-031/pgdata_fresh_rerun/`, fresh·무패치 head 0012)에서 가동 중이며, DGX 프로덕션 DB는 이 커밋들이 실제로 적용되지 않은 상태다(`docs/ai/deployment_integration_plan.md` §6 런북은 작성되었으나 실행은 별도 운영자 단계로 명시).
- **RAG corpus / DGX 접촉:** `docs/ai/deployment_integration_plan.md` §3에 RAG corpus가 DB 서버(외부 :28881)에 위치한다고 명시되어 있고, ai-server 실 `.env`의 `DATABASE_URL` 기본값도 이 DGX DB를 가리킨다(STATE-2026-07-23f). **"앱 경로가 llm_only 모드로 임베딩을 미사용한다"는 주장은 이번 기록 검토에서 확인되지 않았다 — 오히려 EXP-031 재검증(2026-07-23) 중 F2 domain/infer 호출이 실제로 `mode=rag`로 실행되며 임베딩 3콜을 소비하고 DGX DB에 read-only SELECT 성격의 접촉이 발생한 사례가 관측됨(쓰기 없음으로 추정되나 직접 확인은 안 됨). 따라서 이 항목은 `UNVERIFIED`(적어도 관측된 1개 세션에서는 llm_only가 아니라 rag 모드였음)로 표기한다.** 이 구조적 긴장(ai-server가 기본적으로 DGX를 향해 있어 RAG 분기를 타는 어떤 라이브 프로브도 DGX를 건드리게 됨)은 orchestrator/critic 재검토가 필요한 사용자 결정 항목으로 이미 carry되어 있다(STATE-2026-07-23f 사용자 결정 #2).

### (d) ai-server

- **EXP-030 안전 수정 계보:** 72세션 production-route 배터리(EXP-030)를 통해 cluster A(재질문 미방지)·C(risk-grounding 백스톱, ADR-044)가 fixed-live-verified로 확인되었고(`docs/ai/exp030_remediation_validation_report.md` §5), BUG-053(AUD persona AUDIT-C retrieval 미해소)·BUG-055(handoff risk_assessment 통로 부재)·BUG-056(dialogue steering trust-boundary)이 신규 등재되어 여전히 open이다.
- **F5 handoff v4.5 grounding:** `handoff_generator` 프롬프트가 v4.2(fabrication 버전, 실 세션 13722fd0에 상주)→v4.3(BUG-069 메타데이터 인용 규율)→v4.4(BUG-070 §6 placeholder 스윕)→v4.5(자체점검 footer 유출 제거)로 3회 반복 수정되었다. 라이브 재생성 2세션 모두에서 성별/시각/식별자/§9 종단추세 4항목 fabrication이 0으로 확인됨(error.md BUG-069, STATE-2026-07-23g).
- **evidence_verifier 강화:** `_check_metadata_grounding`/`_check_first_visit_longitudinal_trend` 신규 체크가 추가되었으나, 기존 `_is_no_data_placeholder_section`(table-only)와 `_check_dangling_references`(§12 registry-vs-body만 비교)가 §3/§7 불릿형 "미수집" 서술과 §12 근거 인용 drift에 대해 여전히 `warning_count≥3` regenerate 3-attempt를 소진, `requires_human_review=true`로 fail-open 배송된다(BUG-071, open/deferred).

---

## 3. 계약 정렬 이력 (발견·해소된 drift)

| # | 결함(BUG-ID) | 증상 | 해소 방식 | 검증 |
|---|---|---|---|---|
| 1 | BUG-062(safety) | apps/api `SafetyRequest`(message/prev_context) vs ai-server `SafetyInput`(session_id/user_message/conversation_history) — 422 상시 | contract SSOT rename(옵션 B), category-priority 매핑을 `services/safety.py`로 이관 | qa fixed-verified(오프라인, 6 tests), 라이브 재검증에서 어댑터 경유 200 확인 |
| 2 | BUG-063(risk_events.status) | 모델/마이그레이션 소스가 `String(16)`+`pending_reclassify`(17자) 제외 CHECK — 데모 DB는 hand-patch(`varchar(32)`)로만 회피 | 마이그레이션 0012에서 `varchar(32)`+CHECK 확장, 모델 소스 동기화 | qa fixed-verified(fresh-DB 스키마 직접 대조) |
| 3 | BUG-064(role='ai') | Upstage가 `role='ai'`(플랫폼 DB 값)를 거부 — 2턴째부터 400 | interim seam-map(`'ai'`→`'assistant'`) 유지 + CHECK additive-widening(`'assistant'` 추가), full rename은 명시적으로 별도 후속으로 유예 | interim-mitigated, additive-widening-verified |
| 4 | BUG-065(is_minor GENERATED) | `0001`의 `CURRENT_DATE` 비-immutable 표현식 — fresh-DB PG16 부트스트랩 실패, 데모 DB는 hand-patch(`2026` 리터럴)로만 회피 | GENERATED 제거, 앱 계산(`auth.py::_is_minor`)으로 이관 | qa fixed-verified(fresh throwaway pgserver `alembic upgrade head` 성공) |
| 5 | BUG-066(handoff/generate) | apps/api ↔ ai-server 요청/응답 필드명 완전 불일치 — 요청 무음 드롭 + 응답 strict-schema 실패, F5 100% 실패 | `HandoffRequest`/`HandoffResponse` field-identical 재구성, `_build_request`가 실 DB 로우 조립, `extra=forbid`를 `SafetyInput`/`HandoffInput`에 한정 추가 | qa fixed-verified(오프라인) → **라이브 재검증에서 재오픈**(BUG-067/068 발견) → 최종 resolved(2회차 재검증) |
| 6 | BUG-059(crisis_triggered 미전달) | `infer_domain`이 `/ai/domain/infer` 요청에 `crisis_triggered`를 항상 False로 전달(현재 inert) | sibling 호출(`/ai/survey/plan`)과 동일 값(`sess.clinical_escalation_required`) 전달로 정렬 | qa resolved |
| 7 | BUG-060(crisis-signal wire-drop, **critical/blocking**) | ai-server 오케스트레이터 2차 history-aware SafetyClassifier의 실 crisis 판정이 `ChatResponse`에 필드 자체가 없어 wire에서 전면 소실 — RiskEvent/`risk:detected`/escalation 0 | `ChatResponse`/`DialogueOutput`에 `crisis_triggered` 필드 추가, apps/api가 `handle_safety_result`를 재사용해 RiskEvent 생성 + WS 프레임 방출 | qa resolved, clinical-validator CVR-051 blocking→resolved |
| 8 | BUG-061(riskEventId="None") | `autoflush=False`에서 flush 전에 `risk_event.id` 읽어 모든 risk:detected payload가 리터럴 문자열 "None" 방출(pre-gate 포함, 기존 결함) | `db.flush()` 추가 | qa resolved |
| 9 | CVR-051 category-fidelity | crisis-bypass RiskEvent가 실제 트리거(자살/자해)와 무관하게 `OTHER_HARM`(타해)로 하드코드 | 실 category 신호(`SafetyOutput.categories`)를 end-to-end 스레딩, 우선순위 매핑(suicidal_ideation>self_harm>harm_to_others>distress/despair) | qa resolved, clinical-validator resolved-with-findings |
| 10 | BUG-067(critical) | `_extract_slots`가 `role='ai'`를 매핑 없이 전송 — 2번째 슬롯추출 호출부터 400, `clinical_slots` 고갈 | 공유 seam-map helper로 `_extract_slots`+`respond` 단일화 | qa resolved(라이브) |
| 11 | BUG-068(major) | `ai_handoff_timeout_seconds`(45s) < verifier 3-attempt 최악 루프(~48s 관측) — 클라이언트 타임아웃으로 F5 status=failed | 45s→90s로 확장 | qa resolved(라이브) |

계약 정렬 이력 전 항목은 여러 차례 오프라인 게이트(qa) + 임상 게이트(clinical-validator) + 사실검증 게이트(critic)를 순차 통과했으며, 게이트 skip 0(ADR 불요)으로 기록되어 있다(STATE-2026-07-23, STATE-2026-07-23b/c/d/f/g).

---

## 4. 검증 이력 요약

| 검증 | 범위 | 핵심 수치 | 판정 |
|---|---|---|---|
| EXP-030 | 7-VP × 72세션 × 6턴(432콜), production route | non-2xx 0/432, cluster A 회귀 0/432 PASS, steering hit 55/miss 12/partial 186/n-a 179 | qa 기계판정 + CVR-045(adequate-with-findings) |
| EXP-030 표적 셀 | 백스톱(evasive, n=3) + real-survey F5(n=2) + denial(n=1) | 백스톱 3/3 발동, real-survey §5 SI 문항 양성 노출 확인 | CVR-046(A) adequate·CLOSED, (B) adequate, (C) REMAINS UNVERIFIED→denial 셀로 CLOSED-for-instance(narrow) |
| EXP-031 1회차 | 18-screen 라이브 프로브 | working 15+1(F2), degraded 1(S14), not-wired 2, cross-cutting BUG-066 발견 | qa |
| EXP-031 재검증 1/2회차 | fresh-DB 무패치 부트스트랩 + 라이브 F5 파이프라인 | BUG-065 라이브 실증, BUG-066/067/068 최종 폐쇄, 클리니션 `GET /report`=ready+실내용 narrative | qa, REV-019(non-blocking) |
| BUG-069/070/071 웨이브 | v4.3→v4.4→v4.5, 2세션 라이브 × 3회 | 4항목 fabrication 0/2세션 전 라운드, 오프라인 스위트 136→149→155 passed/7 skipped | qa, CVR-054(conditional-yes), REV-020(0 blocking) |
| BUG 처리 현황 | — | fixed-live-verified: BUG-046~051, 060·061·062·063·065·067·068·069·070. resolved: 059·066. open(major): 053·054·055·056·058. open(minor): 071 | error.md 요약표 |

---

## 5. 더 진행해야 할 사항

### (A) 사용자 결정 필요

| # | 항목 | 내용 | 근거 |
|---|---|---|---|
| 1 | **Publish(push+배포 PR)** | 로컬 17커밋 실측 결과 **전량 unpushed**(원격 브랜치 참조 자체 없음). PR #72 상태는 git 로그만으로 확인 불가 — **UNVERIFIED-from-git**. 닫기 권고는 표준 선례(git-ops-on-request-only 메모리)이나 사용자 확인 후 실행 필요 | filemanager 실측 RESULT(2026-07-25) |
| 2 | **handoff.json Master-tip 정정** | `.claude/state/handoff.json`이 Master tip을 `e793581`로 기록하나 실제는 `ab6e91f`(#75 alembic dup-0008 fix 병합, #73/#74/#75 병합이 그 사이 추가 반영됨) — orchestrator가 STATE 엔트리와 함께 정정 필요 | filemanager 실측 RESULT |
| 3 | **DGX-RAG 구조 긴장** | ai-server 실 `.env`가 DGX DB를 기본 지향 — RAG 분기를 타는 어떤 라이브 프로브도 DGX를 건드림. "llm_only 모드" 가정은 이번 기록 검토에서 **미확인/UNVERIFIED**(§2c 참조), 로컬 corpus 지정 여부 결정 필요 | STATE-2026-07-23f 사용자 결정 #2 |
| 4 | **Kakao 키 발급** | Phase 4 병원맵 전제 — 어느 `.env.example`에도 placeholder 없음(과거 `nearby_facilities` 삭제 시 함께 제거), 신규 발급 필요 | `docs/ai/integration_prd_f1f3_hospital.md` §9 결정 #7, §9a #5 |
| 5 | **BUG-058 하네스 재작성 승인** | apps/api conftest `client` fixture가 `starlette.TestClient`의 anyio-portal cross-loop 구조적 결함 — reachable PG에서 44/138 실패. 수정=`httpx.AsyncClient(ASGITransport)` 재작성(~40 call sites, 5 파일 + WS 테스트 별도 결정), 대형 작업이라 사용자 결정 대기 | error.md BUG-058, ADR-047 |
| 6 | **BUG-071 verifier 수렴 설계** | `_is_no_data_placeholder_section`(table-only)을 bullet-list까지 면제 확장 vs 실-claim 검출 과다완화 tradeoff — developer design 결정 필요 | error.md BUG-071 |
| 7 | **메타데이터 풍부화(apps/api gender/시각 실값 전달)** | `HandoffRequest`/`_build_request`가 실 `patient.gender`/세션 시각을 ai-server에 전달하면 현재의 안전 폴백("기록 없음")이 실값으로 개선됨 — apps/api 재시작 필요, 본 웨이브 명시적 유예 | CVR-054 finding 4, STATE-2026-07-23g |
| 8 | **BUG-069 severity 정정(major→critical) 재산정 권고 채택 여부** | CVR-054/REV-020 공히 §9 fabricated baseline 기반 방향성 trend을 BUG-049와 동일 harm 기제로 판단, critical 재산정을 미래 calibration용으로 권고(게이트 재개는 아님) | CVR-054 recommendation 1, REV-020 |
| 9 | **CVR-054 신규 소견 2건 등재 여부** | (a) §12 evidence-registry 인용 오귀속(면담자 질문 vs 환자 실제 발화) — REV-020 정정으로 **2/2 세션** 확인(CVR-054는 1/2로 과소집계). (b) CTRS/severity 내부 불일치(severe GAD-7 panic-with-avoidance가 최저 CTRS+"self-care"로 귀결, §3/§5 자기모순) | CVR-054 findings 5/6, REV-020 issue 5 |

### (B) 개발 잔여(계획 존재)

| # | 항목 | 현황 |
|---|---|---|
| 1 | Phase 4 병원맵 | 옵션 A(백엔드 프록시, apps/api→HIRA/Kakao) 설계 완료·권고, 구현 미착수 — Kakao 키 발급이 선행조건(위 A#4) | `docs/ai/integration_prd_f1f3_hospital.md` §6 |
| 2 | DGX 배포 | 런북 §6(apps/api compose 서비스, `alembic upgrade head` 수동 절차, ENCRYPTION_KEY 공유 SOP) 문서 완비, **실행/집행은 미착수** | `docs/ai/deployment_integration_plan.md` §6 |
| 3 | F4/F5 연동 후속 PRD | F4(종단분석)·F5(handoff report 본문 렌더링 전체)는 F1-F3 PRD에서 명시적으로 out-of-scope로 예고됨 — 별도 PRD 필요 | `docs/ai/integration_prd_f1f3_hospital.md` §1 |
| 4 | F2 rag 모드 실배선 | domain/infer의 RAG 지연 근인 미확정(F2 degraded), `_extract_slots_bg` fire-and-forget 동시성 가설(REV-019 issue 3, qa 확인 필요·미필링) | STATE-2026-07-23f |
| 5 | clinician caveat GET/escalation 소비자 완성 | proxy caveat이 `audit_logs`에 도달하나 clinician 화면 미독출(CVR-050 finding 2), `/clinician/patients` 배지 확장이 저비용 중간 단계로 권고됨(CVR-048 rec 1) | CVR-048, CVR-050 |
| 6 | WS TLS terminator | production `wss://` 강제이나 `infra/`에 TLS terminator 미정의 — 설계 노트만 존재, 구현 후속 필요 | `docs/ai/integration_prd_f1f3_hospital.md` §9a #2 |

### (C) 이월 항목(비차단)

| 항목 | 요지 |
|---|---|
| BUG-054(major, open) | `/ai/slots/extract`가 HTTP 200과 함께 `extracted_slots={}`을 반환해 기존에 추출된 슬롯을 소리 없이 폐기 — finding (b)는 BUG-056으로 승계, 나머지(하네스 병합 결함·triage 서사)가 이 엔트리에 남음(error.md BUG-054) |
| BUG-053 | AUD persona에서 disease-candidate retrieval-ranking이 substance-분류 질환을 top-1으로 못 올려 AUDIT-C가 0/72세션 미해소(roadmap, cluster F #8) |
| CVR-050 finding 1 | `resolve_effective_scale`의 CTRS-boundary safety-net(case 3)이 현 `/domain/infer→/ai/survey/plan` 배선에서 구조적으로 도달 불가 — `crisis_triggered=False`+acute+저신뢰 밴드는 PHQ-4만, SI 항목 없음 |
| EXP-029 계보 minor들 | 문형 수렴(cluster B#4, 0.69%/3/432, 임계값 미설정), grounding filter 과대차단(cluster E, 정직 미보고) |
| apps/api 외부포트 24856 | working assumption(미확정), 반박 시 compose 한 줄만 교체 |
| REV-011 doc-drift | 코드 주석이 `clinical_escalation_required`를 `SessionState` nested로 오기(실제 sibling top-level, 소비자 0 — latent trap) |

---

## 6. 리스크·주의

- **F5 리포트 임상 사용 조건(CVR-054 conditional-yes):** F5 내러티브의 fabrication 축은 닫혔으나, (a) BUG-071 fail-open이 관측된 모든 라이브 세션(2/2)에서 `requires_human_review=true`를 상시 발화 — 변별력 상실로 alert fatigue 위험, (b) 내러티브 단독 소비 시 실 gender/세션 시각 손실 — 결정론적 `patient`/`questionnaires`/`riskSignals` 필드와 병행 열람이 절차적 필수. 이 두 조건이 해소되기 전까지 **F5 내러티브 단독으로 임상 조치를 발동하지 말 것**(CVR-054).
- **"연동 works"와 "F5 리포트 내용 신뢰 가능"은 별개 축이다(REV-019 load-bearing 구분).** 연동(wiring/계약) 층위는 이상 없음으로 재확정됐으나(EXP-031 §7 FINAL, screen-level defect 0), F5 내러티브의 fabrication 축만 이번 웨이브로 닫힌 것이며 BUG-071 fail-open은 **안전 결함이 아니라 품질/효율 결함**(보수적으로 human-review를 과다 요구)으로 성격이 다르다.
- **BUG-071 fail-open의 보수적 posture:** 검증기가 예산을 소진해도 content-bearing 리포트를 반환하고 `requires_human_review=true`로 표시하는 설계 자체는 안전측(과소경보보다 과다경보가 안전)이나, 관측 전량에서 발화하면 신호가치를 상실한다(CVR-054 finding 3).
- **데모 스택 임시성:** 현재 가동 중인 데모 스택의 pgserver는 로컬 파일시스템 기반 휘발성 인스턴스(`experiments/EXP-031/pgdata_fresh_rerun/`)이며, 기존 세션 `13722fd0`에 상주하는 F5 리포트는 v4.5 이전(v4.2, fabrication 버전)으로 생성된 것이 그대로 남아 있다 — 신규 세션만 v4.5 fabrication-free 결과를 반환한다(STATE-2026-07-23g).
- **DGX 실 프로덕션 DB는 이번 커밋 체인이 아직 적용되지 않은 상태**이며(§2c), `docker-compose.dgx.yml`의 `api` 서비스 외부 포트(`24856`)는 미확정 working assumption이다.

---

**Linked doc IDs cited:** `docs/ai/integration_prd_f1f3_hospital.md`, `docs/ai/deployment_integration_plan.md`, `docs/ai/exp030_remediation_validation_report.md`, `experiments/EXP-031/{plan.md,results.md,fix_wave_design.md}`, `error.md` BUG-046~071, `discussion.md` STATE-2026-07-22~23g, ADR-046/047, CVR-047~054, REV-006~020, filemanager 실측 RESULT(2026-07-25, 본 미션 HANDOFF에 인용됨).
